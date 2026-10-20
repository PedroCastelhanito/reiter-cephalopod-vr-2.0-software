"""Context-owner upload and nonblocking completion for resident still images."""

from collections.abc import Mapping
from typing import Any

from cephvr.visual_stimulus.resources.image_source import ImageSource


class ImageGpu:
    def __init__(self, outputs: Mapping[str, Any]) -> None:
        self.outputs = outputs
        self._progress: dict[int, tuple[int, int]] = {}

    def upload(self, source: ImageSource, pixels: bytes, textures: list[Any]) -> bool:
        # Limit each render-owner turn to one transfer chunk; driver allocation
        # latency still needs rig measurement and is not a real-time guarantee.
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
        output.activate()
        while len(textures) <= output_index:
            textures.append(None)
        if textures[output_index] is None:
            texture = output.context.texture(
                (source.width, source.height), 4, dtype="f4"
            )
            textures[output_index] = texture
            texture.filter = (0x2601, 0x2601)
            texture.repeat_x = texture.repeat_y = False
        row_bytes = source.width * 16
        rows = min(source.height - row, max(1, 1_048_576 // row_bytes))
        data = memoryview(pixels)[row * row_bytes : (row + rows) * row_bytes]
        textures[output_index].write(
            data, viewport=(0, row, source.width, rows), alignment=1
        )
        row += rows
        if row == source.height:
            output_index, row = output_index + 1, 0
        if output_index == len(self.outputs):
            self._progress.pop(id(textures), None)
            return True
        self._progress[id(textures)] = (output_index, row)
        return False

    def fence(self, fences: list[Any]) -> None:
        from OpenGL import GL

        for output in self.outputs.values():
            output.activate()
            fence = GL.glFenceSync(GL.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
            if not fence:
                raise RuntimeError("image resource completion fence failed")
            fences.append((output, fence))
            GL.glFlush()

    def ready(self, fences: list[Any]) -> bool:
        from OpenGL import GL

        for output, fence in tuple(fences):
            output.activate()
            result = GL.glClientWaitSync(fence, 0, 0)
            if result == GL.GL_WAIT_FAILED:
                raise RuntimeError("image resource completion check failed")
            if result not in (GL.GL_ALREADY_SIGNALED, GL.GL_CONDITION_SATISFIED):
                return False
            GL.glDeleteSync(fence)
            fences.remove((output, fence))
        return True

    def release(self, textures: list[Any], fences: list[Any]) -> None:
        from OpenGL import GL

        self._progress.pop(id(textures), None)
        for output, fence in tuple(fences):
            output.activate()
            GL.glDeleteSync(fence)
            fences.remove((output, fence))
        # Retain each failed resource in place for a truthful cleanup retry.
        for index in range(len(textures) - 1, -1, -1):
            if textures[index] is not None:
                tuple(self.outputs.values())[index].activate()
                textures[index].release()
            del textures[index]
