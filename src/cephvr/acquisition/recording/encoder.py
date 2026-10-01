"""Acquisition compatibility launcher using shared registered-process mechanics."""

from __future__ import annotations

import time
from collections.abc import Callable

from cephvr.acquisition.identity import FFMPEG_ROLES
from cephvr.acquisition.recording.encoder_process import WindowsEncoderProcess
from cephvr.acquisition.recording.negotiation import VideoNegotiationExpectation
from cephvr.control.v1 import services_pb2_grpc
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.file_sync import WindowsFileSyncOwner
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.supervised_encoder import (
    FFMPEG_PROBE_ROLE,
    FFMPEG_ROLE,
)
from cephvr.shared.supervised_encoder import (
    SupervisedEncoderLauncher as _SupervisedEncoderLauncher,
)


class SupervisedEncoderLauncher(_SupervisedEncoderLauncher):
    """Preserve acquisition API while selecting its stream-validation adapter."""

    def __init__(
        self,
        *,
        supervisor: services_pb2_grpc.SupervisorServiceStub,
        owner: Principal,
        owner_identity: types.ProcessIdentity,
        windows_jobs: WindowsJobs,
        file_sync_owner: WindowsFileSyncOwner,
        diagnostic_tail_max_lines: int = 100,
        diagnostic_tail_max_bytes: int = 64 * 1024,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        super().__init__(
            supervisor=supervisor,
            owner=owner,
            owner_identity=owner_identity,
            windows_jobs=windows_jobs,
            file_sync_owner=file_sync_owner,
            process_factory=WindowsEncoderProcess,
            allowed_roles=FFMPEG_ROLES,
            diagnostic_tail_max_lines=diagnostic_tail_max_lines,
            diagnostic_tail_max_bytes=diagnostic_tail_max_bytes,
            clock_ns=clock_ns,
        )


__all__ = [
    "FFMPEG_PROBE_ROLE",
    "FFMPEG_ROLE",
    "SupervisedEncoderLauncher",
    "VideoNegotiationExpectation",
]
