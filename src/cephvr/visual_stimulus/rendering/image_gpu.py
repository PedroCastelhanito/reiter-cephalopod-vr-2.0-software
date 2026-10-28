"""Context-owner upload and nonblocking completion for resident still images."""

import time
from collections.abc import Mapping
from typing import Any

from cephvr.visual_stimulus.resources.image_source import ImageSource, PixelBuffer

UPLOAD_CHUNK_BYTES = 1_048_576
UPLOAD_CHUNKS_PER_TURN = 4
UPLOAD_TURN_NS = 2_000_000


class ImageGpu:
    def __init__(self, outputs: Mapping[str, Any]) -> None:
        self.outputs = outputs
        self._progress: dict[int, tuple[int, int]] = {}
        self.pool: Any = None
        from cephvr.visual_stimulus.resources.image_timing import ImageTimings

        self.timings = ImageTimings()

    def prepare_pool(self, schedule: Any, budget: Any, announce: Any) -> None:
        from .image_pool import POOL_OWNER, ImagePool, pool_plan

        plan = pool_plan(schedule)
        if plan is None:
            return
        source, count = plan
        self.pool = ImagePool(dict(self.outputs), source, count, UPLOAD_CHUNK_BYTES)
        self.pool.timings = self.timings
        announce(POOL_OWNER, None)
        budget.reserve(owner=POOL_OWNER, cpu_bytes=0, gpu_bytes=self.pool.gpu_bytes)
        self.pool.prepare(budget.check_cancelled_or_expired)

    def close_pool(self, budget: Any) -> str | None:
        from .image_pool import POOL_OWNER

        if self.pool is None:
            return None
        self.pool.close()
        budget.release(owner=POOL_OWNER)
        self.pool = None
        return POOL_OWNER

    def upload(
        self, source: ImageSource, pixels: PixelBuffer, textures: list[Any]
    ) -> bool:
        if self.pool is not None and not self.pool.acquire(textures):
            return False
        started = time.perf_counter_ns()
        until = started + UPLOAD_TURN_NS
        for _ in range(UPLOAD_CHUNKS_PER_TURN):
            if self._upload_chunk(source, pixels, textures):
                self.timings.record("upload", time.perf_counter_ns() - started)
                return True
            if time.perf_counter_ns() >= until:
                break
        self.timings.record("upload", time.perf_counter_ns() - started)
        return False

    def _upload_chunk(
        self, source: ImageSource, pixels: PixelBuffer, textures: list[Any]
    ) -> bool:
        output_index, row = self._progress.get(id(textures), (0, 0))
        outputs = tuple(self.outputs.items())
        while output_index < len(outputs) and (
            source.output_ids is not None
            and outputs[output_index][0] not in source.output_ids
        ):
            output_index += 1
        if output_index == len(outputs):
            self._progress.pop(id(textures), None)
            return True
        output = outputs[output_index][1]
        crop = next(
            (c for c in source.output_crops if c.output_id == outputs[output_index][0]),
            None,
        )
        width, height = (
            (source.width, source.height) if crop is None else (crop.width, crop.height)
        )
        offset = 0 if crop is None else crop.offset
        started = time.perf_counter_ns()
        output.activate()
        self.timings.record("activation", time.perf_counter_ns() - started)
        while len(textures) <= output_index:
            textures.append(None)
        if textures[output_index] is None:
            texture = output.context.texture((width, height), 4, dtype="f4")
            textures[output_index] = texture
            texture.filter = (0x2601, 0x2601)
            texture.repeat_x = texture.repeat_y = False
        row_bytes = width * 16
        rows = min(height - row, max(1, UPLOAD_CHUNK_BYTES // row_bytes))
        data = memoryview(pixels)[
            offset + row * row_bytes : offset + (row + rows) * row_bytes
        ]
        if self.pool is not None:
            if not self.pool.write(
                outputs[output_index][0],
                textures[output_index],
                data,
                (0, row, width, rows),
            ):
                return False
        else:
            textures[output_index].write(
                data, viewport=(0, row, width, rows), alignment=1
            )
        row += rows
        if row == height:
            output_index, row = output_index + 1, 0
            while output_index < len(outputs) and (
                source.output_ids is not None
                and outputs[output_index][0] not in source.output_ids
            ):
                output_index += 1
        if output_index == len(self.outputs):
            self._progress.pop(id(textures), None)
            return True
        self._progress[id(textures)] = (output_index, row)
        return False

    def fence(self, textures: list[Any], fences: list[Any]) -> None:
        from OpenGL import GL

        started = time.perf_counter_ns()
        # Only allocating contexts can have submitted work using this image.
        for output, texture in zip(self.outputs.values(), textures, strict=False):
            if texture is None:
                continue
            output.activate()
            fence = GL.glFenceSync(GL.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
            if not fence:
                raise RuntimeError("image resource completion fence failed")
            fences.append((output, fence))
            GL.glFlush()
        self.timings.record("fence", time.perf_counter_ns() - started)

    def ready(self, fences: list[Any]) -> bool:
        from OpenGL import GL

        started = time.perf_counter_ns()
        for output, fence in tuple(fences):
            output.activate()
            result = GL.glClientWaitSync(fence, 0, 0)
            if result == GL.GL_WAIT_FAILED:
                raise RuntimeError("image resource completion check failed")
            if result not in (GL.GL_ALREADY_SIGNALED, GL.GL_CONDITION_SATISFIED):
                self.timings.record("ready", time.perf_counter_ns() - started)
                return False
            GL.glDeleteSync(fence)
            fences.remove((output, fence))
        self.timings.record("ready", time.perf_counter_ns() - started)
        return True

    def release(self, textures: list[Any], fences: list[Any]) -> None:
        from OpenGL import GL

        self._progress.pop(id(textures), None)
        for output, fence in tuple(fences):
            output.activate()
            GL.glDeleteSync(fence)
            fences.remove((output, fence))
        # Retain each failed resource in place for a truthful cleanup retry.
        if self.pool is not None:
            self.pool.recycle(textures)
            return
        for index in range(len(textures) - 1, -1, -1):
            if textures[index] is not None:
                tuple(self.outputs.values())[index].activate()
                textures[index].release()
            del textures[index]
