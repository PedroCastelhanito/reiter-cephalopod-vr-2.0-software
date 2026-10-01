"""Small native CPU calculations; no cameras, models or GPU emulation product."""

import math
from dataclasses import replace

import numpy as np
import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.tracking.config.models import methods as m
from cephvr.tracking.config.models.records import Point, PoseUse, SourceFrame, Triplet
from cephvr.tracking.methods.contour import ContourPose
from cephvr.tracking.methods.flow_buffers import grid_mapping, host_arrays
from cephvr.tracking.methods.geometry import EllipseGeometry
from cephvr.tracking.methods.images import GrayPreparation
from cephvr.tracking.methods.outline import outline, project_sections
from cephvr.tracking.methods.proxy import FlowProxy
from cephvr.tracking.methods.screening import screen
from cephvr.tracking.types import (
    FlowLease,
    FlowProxyInput,
    HostFlowView,
    ImageLayout,
    PrivateFrame,
)
from cephvr.tracking.v1 import pose_pb2 as pose


def layout(w=48, h=48):
    return ImageLayout(w, h, w, "gray", "uint8", 8, "lsb", 0, 255, "source")


def limits():
    return m.FileLimits(
        schema_version=1,
        max_document_bytes=65536,
        max_asset_bytes=1000000,
        max_native_bytes=16 * 1024 * 1024,
        maximum_message_bytes=65536,
        pose_progress_timeout_s=2.0,
        movement_progress_timeout_s=2.0,
    )


def frame(array, image_layout=None, index=1):
    return PrivateFrame(
        SourceFrame(frame_id=index, host_receipt_ns=index * 10000000),
        pb.WorkContext(),
        "1",
        image_layout or layout(array.shape[1], array.shape[0]),
        memoryview(array).toreadonly(),
        str(index),
    )


def settings():
    return m.WaterFlowSettings(
        schema_version=1,
        sections=m.ArcSectionSettings(schema_version=1, count=4),
        quality=m.LocalMedianSettings(
            schema_version=1,
            radius_cells=1,
            minimum_neighbors=1,
            noise_floor_px=0.1,
            maximum_normalized_residual=100.0,
            maximum_native_cost=None,
        ),
        support=m.SectionFlowSupportSettings(
            schema_version=1, minimum_accepted_area_fraction=0.1
        ),
        smoothing=m.ExponentialSmoothingSettings(
            schema_version=1, time_constant_s=0.08
        ),
    )


def geometry(tip_x=18):
    owner = EllipseGeometry()
    owner.prepare(
        m.EllipseSettings(
            schema_version=2,
            front_fraction=0.6,
            taper=0.0,
            squareness=2.0,
            inner_clearance_fraction=0.1,
            outer_extent_fraction=0.75,
        ),
        layout(),
        limits(),
    )
    value = owner.compute(
        Triplet(
            tip=Point(x_px=float(tip_x), y_px=24.0),
            left_base=Point(x_px=float(tip_x + 12), y_px=20.0),
            right_base=Point(x_px=float(tip_x + 12), y_px=28.0),
        )
    )
    assert value is not None
    return owner, value


def sample(value, mapping, dx=1, dy=0, index=2):
    data = np.empty((mapping.grid_height, mapping.grid_width, 2), dtype="<i2")
    data[:] = (dx * 32, dy * 32)
    lease = FlowLease(
        str(index),
        "1",
        pb.WorkContext(),
        mapping.mapping_id,
        SourceFrame(frame_id=index - 1, host_receipt_ns=(index - 1) * 10000000),
        SourceFrame(frame_id=index, host_receipt_ns=index * 10000000),
        mapping.grid_width,
        mapping.grid_height,
        1,
        mapping.grid_width * 4,
        str(index),
        "int16x2",
        "little",
        "host",
        1 / 32,
        "input_pixel_displacement",
        "buffer",
        None,
        None,
        None,
        None,
        None,
    )
    use = PoseUse(
        disposition="manual",
        manual_geometry_id="manual",
        observation_id=None,
        check_host_ns=index * 10000000,
        pose_source_host_ns=None,
        age_ns=None,
        maximum_age_ns=None,
    )
    return FlowProxyInput(
        pb.WorkContext(),
        "1",
        lease,
        HostFlowView(str(index), memoryview(data).toreadonly(), None, None),
        mapping,
        use,
        value,
    )


def test_source_depth_and_half_up_flow_quantization():
    source = np.array([[0, 2048 << 4, 4095 << 4]], dtype="<u2")
    image_layout = ImageLayout(3, 1, 6, "gray", "uint16", 12, "msb", 0, 4095, "mono12")
    prepare = GrayPreparation(image_layout)
    assert prepare.source_gray(frame(source, image_layout)).tolist() == [
        [0.0, 2048.0, 4095.0]
    ]
    assert prepare.feature(frame(source, image_layout)).tolist() == [[0, 128, 255]]


def test_circle_arc_origin_direction_and_distance_band():
    curve = outline(10, 10, 0, 2, 10000)
    assert (
        abs(np.linalg.norm(np.diff(curve, axis=0), axis=1).sum() - 20 * math.pi)
        / (20 * math.pi)
        < 0.00011
    )
    assert project_sections(
        np.array([[-8, 8], [8, 8], [8, -8], [-8, -8]]), curve, 4, 4096
    ).tolist() == [0, 1, 2, 3]
    owner, value = geometry()
    assert np.asarray(value.band_mask).sum() > 0
    assert not np.asarray(value.band_mask).flags.writeable
    assert not owner.close(0)
    owner.release(value)
    assert owner.close(0)
    with pytest.raises(ValueError):
        owner.release(value)


def test_original_neighbor_screening_outlier_and_no_fallback():
    data = np.zeros((5, 5, 2))
    data[2, 2] = (100, 0)
    quality = settings().quality.model_copy(
        update={"minimum_neighbors": 4, "maximum_normalized_residual": 2.0}
    )
    accepted, counts = screen(data, np.ones((5, 5), bool), None, None, quality, 65536)
    assert not accepted[2, 2] and accepted[2, 1]
    assert counts.median_rejected == 1 and counts.neighbor_unevaluable == 4
    assert counts.accepted == 20


def test_proxy_translation_units_filter_duplicate_and_invalid_clearing():
    _, value = geometry()
    mapping = grid_mapping(48, 48, 1)
    proxy = FlowProxy()
    proxy.prepare(settings(), layout(), mapping, limits())
    first = proxy.compute(sample(value, mapping))
    assert first.validity == "valid" and first.raw.forward_drive == pytest.approx(-100)
    assert first.raw.turn_drive == pytest.approx(0, abs=1e-10)
    second_sample = sample(value, mapping, dx=2, index=3)
    second = proxy.compute(second_sample)
    assert second.filter_disposition == "continued"
    assert second.filtered_average.forward_drive == pytest.approx(
        -200 + 100 * (-math.expm1(-0.125)) / 0.125
    )
    assert proxy.compute(second_sample) is second
    invalid = proxy.compute(replace(sample(value, mapping, index=4), geometry=None))
    assert invalid.validity == "invalid" and invalid.filtered_average is None
    assert proxy.compute(sample(value, mapping, index=5)).filter_disposition == "seeded"


def test_clipping_uses_intended_support_and_readback_span_checks():
    _, value = geometry(tip_x=0)
    mapping = grid_mapping(48, 48, 1)
    proxy = FlowProxy()
    strict = settings().model_copy(
        update={
            "support": m.SectionFlowSupportSettings(
                schema_version=1, minimum_accepted_area_fraction=1.0
            )
        }
    )
    proxy.prepare(strict, layout(), mapping, limits())
    result = proxy.compute(sample(value, mapping))
    assert result.validity == "invalid"
    assert any(s.visible_area_px2 < s.intended_area_px2 for s in result.sections)
    s = sample(value, mapping)
    with pytest.raises(ValueError):
        host_arrays(replace(s.flow, row_pitch_bytes=1), s.host_view)


def test_contour_observed_triplet_and_clipped_component_rejection():
    image = np.zeros((48, 48), dtype=np.uint8)
    image[18:30, 10:35] = 200
    adapter = ContourPose()
    reference = pose.SubjectReferenceSettings(
        image_width_px=48,
        image_height_px=48,
        anterior=pose.ImagePoint(x_px=40, y_px=24),
        posterior=pose.ImagePoint(x_px=5, y_px=24),
        medial_left=pose.ImagePoint(x_px=24, y_px=5),
        medial_right=pose.ImagePoint(x_px=24, y_px=40),
    )
    adapter.prepare(
        m.ContourSettings(
            schema_version=2,
            minimum_axis_anisotropy=0.1,
            threshold_level=100.0,
            foreground_polarity="bright",
            minimum_area_px2=10,
            maximum_area_px2=1000,
            geometry_quality=m.LandmarkQuality(
                minimum_axis_px=1.0,
                minimum_base_width_px=1.0,
                minimum_triangle_area_px2=1.0,
            ),
        ),
        layout(),
        pose.PoseSearchRegion(x_px=0, y_px=0, width_px=48, height_px=48),
        reference,
        "",
        limits(),
    )
    candidates = adapter.compute(frame(image))
    assert len(candidates) == 1
    assert candidates[0].landmarks[1] == (34.0, 18.0)
    image[18:30, :35] = 200
    assert adapter.compute(frame(image)) == ()


def test_native_block_centres_include_partial_edge_blocks():
    mapping = grid_mapping(5, 6, 4)
    positions = np.asarray(mapping.sample_xy_px)
    np.testing.assert_array_equal(
        positions, [[[1.5, 1.5], [4, 1.5]], [[1.5, 4.5], [4, 4.5]]]
    )
    np.testing.assert_array_equal(
        np.asarray(mapping.footprint_xyxy_px)[-1, -1], [3.5, 3.5, 4.5, 5.5]
    )
    assert not positions.flags.writeable


@pytest.mark.parametrize("channels", ["gray", "rgb"])
def test_model_letterbox_preserves_native_range_and_pixel_centres(channels):
    from cephvr.tracking.config.models.methods import ModelManifest, ModelSettings
    from cephvr.tracking.methods.model_tensor import ModelTensor
    from cephvr.tracking.v1.pose_pb2 import PoseSearchRegion

    count = 1 if channels == "gray" else 3
    manifest = ModelManifest(
        schema_version=1,
        adapter="onnx_triplet_v1",
        model={"relative_path": "model.onnx"},
        external_weights=(),
        input_name="image",
        output_name="landmarks",
        input_width_px=10,
        input_height_px=10,
        channels=channels,
        mean=(0.0,) * count,
        std=(1.0,) * count,
        padding_source_fraction=(0.25,) * count,
        maximum_candidates=2,
    )
    image = np.full((4, 8), 255, dtype=np.uint8)
    source = frame(image)
    tensor = ModelTensor(
        manifest,
        source.layout,
        PoseSearchRegion(x_px=0, y_px=0, width_px=8, height_px=4),
    )
    result = tensor.prepare(source)
    np.testing.assert_array_equal(result[:, :, 2:7], 1.0)
    np.testing.assert_array_equal(result[:, :, :2], 0.25)
    settings = ModelSettings(
        schema_version=1,
        manifest={"relative_path": "model.json"},
        device_ordinal=0,
        minimum_candidate_score=0.5,
        minimum_landmark_score=0.5,
        geometry_quality={
            "minimum_axis_px": 1,
            "minimum_base_width_px": 1,
            "minimum_triangle_area_px2": 1,
        },
    )
    points = [(1, 1), (6, 0), (6, 3)]
    row = [1.0]
    for x, y in points:
        row.extend(
            [
                (x + 0.5) * tensor.sx - 0.5 + tensor.left,
                (y + 0.5) * tensor.sy - 0.5 + tensor.top,
                1.0,
            ]
        )
    candidates = tensor.candidates(np.array([[row]], dtype=np.float32), settings)
    np.testing.assert_allclose(candidates[0].landmarks, points)
