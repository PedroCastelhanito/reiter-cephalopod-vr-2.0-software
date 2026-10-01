"""GPU-side ordering when a composite samples textures written in shared contexts."""

from collections.abc import Mapping
from typing import Any, Protocol


class ActiveOutput(Protocol):
    def activate(self) -> None: ...


def order_shared_outputs(
    outputs: Mapping[str, ActiveOutput], pending: list[Any]
) -> None:
    from OpenGL import GL

    # No CPU wait or glFinish: producer flush submits work, server waits order
    # the capture context after every producing context's final output writes.
    for output in outputs.values():
        output.activate()
        fence = GL.glFenceSync(GL.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
        if not fence:
            raise RuntimeError("could not fence composite producer output")
        pending.append(fence)
        GL.glFlush()
    next(iter(outputs.values())).activate()
    for fence in tuple(pending):
        GL.glWaitSync(fence, 0, GL.GL_TIMEOUT_IGNORED)
        GL.glDeleteSync(fence)
        pending.remove(fence)


def release_fences(pending: list[Any]) -> None:
    if not pending:
        return
    from OpenGL import GL

    for fence in tuple(pending):
        GL.glDeleteSync(fence)
        pending.remove(fence)
