"""Explicit rig-only CUDA/NVOF smoke test; no camera or experiment acceptance."""

import sys
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.windows,
    pytest.mark.rig,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows NVIDIA rig only"),
]


def test_native_flow_lease_and_same_image_pair():
    import numpy as np

    from cephvr.control.v1.types_pb2 import WorkContext
    from cephvr.shared.clock import host_time_ns
    from cephvr.tracking.config.models.methods import FileLimits, FlowSettings
    from cephvr.tracking.config.models.records import SourceFrame
    from cephvr.tracking.configuration import load_file_policies
    from cephvr.tracking.methods.flow_buffers import host_arrays
    from cephvr.tracking.methods.nvidia import NvidiaFlow
    from cephvr.tracking.types import ImageLayout, PrivateFrame

    from .support import ROOT, manual_settings

    settings = manual_settings()
    stage = next(item for item in settings.stages if item.stage_id == "image_flow")
    flow_settings = FlowSettings.model_validate_json(stage.settings_json)
    limits = FileLimits.model_validate_json(load_file_policies(ROOT).limits_json)
    layout = ImageLayout(
        128, 128, 128, "gray", "uint8", 8, "lsb", 0, 255, "rig-native-test"
    )
    image = np.random.default_rng(731).integers(0, 256, (128, 128), dtype=np.uint8)
    image.flags.writeable = False
    work = WorkContext()
    work.trial.trial_id = str(uuid4())
    now = host_time_ns()
    frames = [
        PrivateFrame(
            SourceFrame(frame_id=i, host_receipt_ns=now + i * 10**6),
            work,
            "1",
            layout,
            memoryview(image),
            str(uuid4()),
        )
        for i in range(2)
    ]
    flow = NvidiaFlow()
    lease = None
    try:
        flow.prepare(flow_settings, layout, limits)
        flow.reset("1")
        assert flow.establish_baseline(frames[0], host_time_ns() + 5 * 10**9)
        lease = flow.compute_pair(*frames)
        assert flow.wait_complete(lease, host_time_ns() + 5 * 10**9)
        vectors, _, _ = host_arrays(lease, flow.host_view(lease))
        assert vectors.shape == (32, 32, 2) and vectors.dtype == np.dtype("<i2")
        assert np.isfinite(vectors).all()
        flow.release(lease)
        lease = None
    finally:
        if lease is not None and flow.wait_complete(lease, host_time_ns() + 5 * 10**9):
            flow.release(lease)
        assert flow.close(host_time_ns() + 5 * 10**9), "native resources remain owned"
