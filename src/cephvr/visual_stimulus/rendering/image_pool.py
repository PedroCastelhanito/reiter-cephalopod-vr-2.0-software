"""Setup-owned texture slots and nonblocking pixel-unpack staging for Fold bundles."""

import time
from typing import Any

from cephvr.visual_stimulus.resources.image_schedule import ImageSchedule
from cephvr.visual_stimulus.resources.image_source import ImageSource
from cephvr.visual_stimulus.resources.image_timing import ImageTimings

POOL_OWNER = "visual_stimulus:gpu:image-pool"
STAGING_BUFFERS = 2


def pool_plan(schedule: ImageSchedule) -> tuple[ImageSource, int] | None:
    sources = tuple(schedule.sources.values())
    if not sources or any(not s.output_crops for s in sources):
        return None

    def layout(s: ImageSource) -> tuple[tuple[str, int, int], ...]:
        return tuple((c.output_id, c.width, c.height) for c in s.output_crops)

    if any(layout(s) != layout(sources[0]) for s in sources):
        return None
    anchors = set(schedule.anchors)
    required = len(anchors)
    for trial, rows in schedule.epochs.items():
        for index in range(len(rows)):
            desired = anchors | {
                schedule.aliases[(trial, asset)]
                for row in rows[index : index + 3]
                for _, asset in row
            }
            # One held image per consumer can outlive its scheduled epoch.
            consumers = {instance for instance, _ in rows[index]}
            required = max(required, len(desired) + len(consumers) + 1)
    return sources[0], min(len(sources), required)


class ImagePool:
    def __init__(
        self, outputs: dict[str, Any], source: ImageSource, count: int, chunk: int
    ):
        self.timings = ImageTimings()
        self.outputs = outputs
        self.source = source
        self.count = count
        self.chunk = chunk
        self.owned: list[tuple[Any, Any]] = []
        self.free: list[list[Any]] = []
        self.assigned: dict[int, list[Any]] = {}
        self.staging: dict[str, list[list[Any]]] = {}

    @property
    def gpu_bytes(self) -> int:
        return (
            self.source.gpu_bytes * self.count
            + len(self.outputs) * STAGING_BUFFERS * self.chunk
        )

    def prepare(self, check: Any) -> None:
        crops = {c.output_id: c for c in self.source.output_crops}
        for _ in range(self.count):
            slot: list[Any] = []
            for key, output in self.outputs.items():
                check()
                crop = crops.get(key)
                if crop is None:
                    slot.append(None)
                    continue
                output.activate()
                texture = output.context.texture(
                    (crop.width, crop.height), 4, dtype="f4"
                )
                self.owned.append((output, texture))
                texture.filter = (0x2601, 0x2601)
                texture.repeat_x = texture.repeat_y = False
                slot.append(texture)
            self.free.append(slot)
        for key, output in self.outputs.items():
            output.activate()
            self.staging[key] = []
            for _ in range(STAGING_BUFFERS):
                check()
                buffer = output.context.buffer(reserve=self.chunk, dynamic=True)
                self.owned.append((output, buffer))
                self.staging[key].append([buffer, None])

    def acquire(self, textures: list[Any]) -> bool:
        if id(textures) in self.assigned:
            return True
        if not self.free:
            return False
        slot = self.free.pop()
        self.assigned[id(textures)] = slot
        textures.extend(slot)
        return True

    def recycle(self, textures: list[Any]) -> None:
        slot = self.assigned.pop(id(textures), None)
        if slot is not None:
            self.free.append(slot)
        textures.clear()

    def write(
        self, output_id: str, texture: Any, data: memoryview, viewport: tuple[int, ...]
    ) -> bool:
        from OpenGL import GL

        for stage in self.staging[output_id]:
            buffer, fence = stage
            if fence is not None:
                result = GL.glClientWaitSync(fence, 0, 0)
                if result == GL.GL_WAIT_FAILED:
                    raise RuntimeError("image staging completion check failed")
                if result not in (GL.GL_ALREADY_SIGNALED, GL.GL_CONDITION_SATISFIED):
                    continue
                GL.glDeleteSync(fence)
                stage[1] = None
            started = time.perf_counter_ns()
            buffer.write(data)
            self.timings.record("staging_write", time.perf_counter_ns() - started)
            started = time.perf_counter_ns()
            texture.write(buffer, viewport=viewport, alignment=1)
            self.timings.record("texture_write", time.perf_counter_ns() - started)
            stage[1] = GL.glFenceSync(GL.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
            if not stage[1]:
                raise RuntimeError("image staging fence failed")
            GL.glFlush()
            return True
        return False

    def close(self) -> None:
        from OpenGL import GL

        if self.assigned:
            raise RuntimeError("image pool still has assigned textures")
        for key, stages in self.staging.items():
            self.outputs[key].activate()
            for stage in stages:
                if stage[1] is not None:
                    GL.glDeleteSync(stage[1])
                    stage[1] = None
        while self.owned:
            output, resource = self.owned[-1]
            output.activate()
            resource.release()
            self.owned.pop()
        self.free.clear()
