"""Python worker executable resolver used by the acquisition worker registry."""

from __future__ import annotations

from pathlib import Path

from cephvr.acquisition.v1 import camera_pb2


class PythonWorkerExecutables:
    """Resolve accepted acquisition camera roles to this managed interpreter."""

    def __init__(self, interpreter: Path) -> None:
        self.interpreter = interpreter.resolve()

    def resolve_worker(self, role: int) -> tuple[Path, bool, str]:
        if role not in {
            camera_pb2.CAMERA_ROLE_BEHAVIORAL,
            camera_pb2.CAMERA_ROLE_TRACKING,
        }:
            raise ValueError("unsupported worker camera role")
        return self.interpreter, True, "grpc_shutdown"
