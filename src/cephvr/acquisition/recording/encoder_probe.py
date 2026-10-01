"""Acquisition compatibility export for the shared registered FFmpeg probe."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.acquisition.identity import FFMPEG_PROBE_ROLE
from cephvr.acquisition.recording.encoder import SupervisedEncoderLauncher
from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.encoder_probe import RegisteredCapabilityProbe


class SupervisedCapabilityProbe(RegisteredCapabilityProbe):
    """Preserve acquisition's established helper API and exact process role."""

    def __init__(
        self,
        launcher: SupervisedEncoderLauncher,
        work: types.WorkContext,
        parent_operation: types.OperationContext,
        resource_released: Callable[[str, bool], None],
    ) -> None:
        super().__init__(
            launcher,
            work,
            parent_operation,
            resource_released,
            role=FFMPEG_PROBE_ROLE,
        )
