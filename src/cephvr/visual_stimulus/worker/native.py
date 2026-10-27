"""Native process assembly: only focused operations cross feature boundaries."""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.platform.windows.file_sync import (
    WindowsFileSyncOwner,
    WindowsVideoSyncFactory,
)
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.platform.windows.python_runtime import (
    module_arguments,
    resolve_python_executable,
)
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher
from cephvr.visual_stimulus.feedback.native import NativeFeedback
from cephvr.visual_stimulus.identity import SPARSE_NOISE_ROLE
from cephvr.visual_stimulus.recording.native import NativeRecording
from cephvr.visual_stimulus.rendering.native import ModernGLPort
from cephvr.visual_stimulus.resources.session import NativePreparation

from .bootstrap import WorkerBootstrap
from .lifecycle import LifecycleDriver
from .ports import ReportPort
from .sparse_noise import (
    HELPER_MODULE,
    LOOKAHEAD_PATTERNS,
    NativeSparseNoise,
    sparse_process_factory,
)


class Declarations:
    """Late-bind a single explicit catalogue operation before any native creation."""

    def __init__(self) -> None:
        self.operation: Callable[[str, str | None], None] | None = None

    def __call__(self, resource: str, path: str | None) -> None:
        if self.operation is None:
            raise RuntimeError("native resource creation before catalogue assembly")
        self.operation(resource, path)


def assemble_driver(
    bootstrap: WorkerBootstrap,
    reports: ReportPort,
    cancelled: threading.Event,
    shutdown: Callable[[], None],
    supervisor: rpc.SupervisorServiceStub,
) -> LifecycleDriver:
    declare = Declarations()
    port = ModernGLPort(
        bootstrap.software_root, announce=declare, clock_ns=host_time_ns
    )
    files = WindowsFileSyncOwner()
    ffmpeg = shutil.which("ffmpeg")
    recording = NativeRecording(
        ffmpeg_executable=Path(ffmpeg).resolve() if ffmpeg else None,
        supervisor=supervisor,
        owner=Principal(
            "visual_stimulus_renderer",
            bootstrap.context.worker.generation,
            bootstrap.token,
        ),
        owner_identity=bootstrap.context.worker,
        windows_jobs=WindowsJobs(),
        file_sync_owner=files,
        renderer=port,
        video_sync_factory=WindowsVideoSyncFactory(files),
        nvenc_owner=NvencProbeOwner(),
        clock_ns=host_time_ns,
    )
    owner = Principal(
        "visual_stimulus_renderer", bootstrap.context.worker.generation, bootstrap.token
    )
    sparse_noise = NativeSparseNoise(
        launcher=SupervisedEncoderLauncher(
            supervisor=supervisor,
            owner=owner,
            owner_identity=bootstrap.context.worker,
            windows_jobs=WindowsJobs(),
            file_sync_owner=files,
            process_factory=sparse_process_factory(0),
            allowed_roles=frozenset({SPARSE_NOISE_ROLE}),
            # Owns no output file, like a probe.
            probe_roles=frozenset({SPARSE_NOISE_ROLE}),
            clock_ns=host_time_ns,
        ),
        argv=lambda: [
            str(resolve_python_executable()),
            *module_arguments(HELPER_MODULE, []),
        ],
        graphics=port,
        lookahead=LOOKAHEAD_PATTERNS,
    )
    preparation = NativePreparation(
        port,
        renderer_generation=bootstrap.context.worker.generation,
        clock_ns=host_time_ns,
        cancelled=cancelled,
        review_encoding_provider=recording.review_encoding_provider,
    )
    driver = LifecycleDriver(
        worker=bootstrap.context.worker,
        owner=bootstrap.context.owner,
        controller=bootstrap.controller,
        policies=bootstrap.policies,
        engine=preparation.engine,
        preparation=preparation,
        recording=recording,
        feedback=NativeFeedback(
            local_process_instance_id=bootstrap.context.worker.generation,
            clock_ns=host_time_ns,
        ),
        reports=reports,
        cancelled=cancelled,
        clock=host_time_ns,
        shutdown=shutdown,
        sparse_noise=sparse_noise,
    )
    port.preview_changed = driver.preview_changed
    port.preview_rates = driver.preview_rates
    declare.operation = driver.announce
    return driver
