"""Acquisition compatibility adapter for the shared Windows FFmpeg process owner."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cephvr.acquisition.recording.negotiation import (
    VideoNegotiation,
    VideoNegotiationExpectation,
)
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.byte_stream import OverlappedPipe
from cephvr.platform.windows.encoder_process import (
    WindowsEncoderProcess as _WindowsEncoderProcess,
)
from cephvr.platform.windows.encoder_process import (
    _remaining,
    _wait_process,
)
from cephvr.platform.windows.file_sync import WindowsFileSyncOwner
from cephvr.platform.windows.jobs import SuspendedProcess, WindowsJobs
from cephvr.shared.auth import Principal


class WindowsEncoderProcess(_WindowsEncoderProcess):
    """Preserve acquisition's negotiated-stream validation on the shared process."""

    def __init__(
        self,
        *,
        supervisor: services_pb2_grpc.SupervisorServiceStub,
        owner: Principal,
        owner_identity: types.ProcessIdentity,
        windows_jobs: WindowsJobs,
        launch_id: str,
        child: SuspendedProcess,
        job_name: str,
        input_pipe: OverlappedPipe,
        progress_pipe: OverlappedPipe,
        stderr_pipe: OverlappedPipe,
        output_path: Path | None,
        output_absent_before_launch: bool,
        capture_stdout: bool = False,
        negotiation: VideoNegotiationExpectation | None = None,
        stdout_max_bytes: int = 2 * 1024 * 1024,
        file_sync_owner: WindowsFileSyncOwner,
        diagnostic_tail_max_lines: int,
        diagnostic_tail_max_bytes: int,
        clock_ns: Callable[[], int],
    ) -> None:
        super().__init__(
            supervisor=supervisor,
            owner=owner,
            owner_identity=owner_identity,
            windows_jobs=windows_jobs,
            launch_id=launch_id,
            child=child,
            job_name=job_name,
            input_pipe=input_pipe,
            progress_pipe=progress_pipe,
            stderr_pipe=stderr_pipe,
            output_path=output_path,
            output_absent_before_launch=output_absent_before_launch,
            capture_stdout=capture_stdout,
            negotiation=(
                VideoNegotiation(negotiation) if negotiation is not None else None
            ),
            stdout_max_bytes=stdout_max_bytes,
            file_sync_owner=file_sync_owner,
            diagnostic_tail_max_lines=diagnostic_tail_max_lines,
            diagnostic_tail_max_bytes=diagnostic_tail_max_bytes,
            clock_ns=clock_ns,
        )


__all__ = ["WindowsEncoderProcess", "_remaining", "_wait_process"]
