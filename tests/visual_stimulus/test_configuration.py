"""Visual Stimulus configuration boundary checks without graphics or media initialization."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from cephvr.visual_stimulus.configuration import (
    load_defaults,
    load_file_policies,
    validate_configuration,
    validate_display_profile,
)

_ROOT = Path(__file__).resolve().parents[2]


class VisualStimulusConfigurationTests(unittest.TestCase):
    def test_predictable_clipping_warns_without_rejecting_or_rewriting(self) -> None:
        from tests.visual_stimulus.support import fixture_source

        from cephvr.control.v1 import types_pb2 as pb

        source = json.loads(fixture_source())
        source["sequence"][0]["settings"][0]["mean_linear_rgb"] = [2.0, 0.5, 0.5]
        authored = json.dumps(source)
        candidate = pb.ExperimentConfiguration(mode=pb.SESSION_MODE_OPEN_LOOP)
        candidate.backends.add(
            backend_name="visual_stimulus",
            enabled=True,
            visual_stimulus=pb.VisualStimulusSettings(save_visual_stimulus_data=False),
        )
        trial = candidate.trials.add(trial_number=1)
        trial.stimulus.program.program_json = authored
        trial.stimulus.arena_boundaries.boundaries_json = (
            '{"format_version":1,"bindings":[]}'
        )
        result = validate_configuration(candidate)
        self.assertTrue(result.completed and result.valid)
        self.assertEqual(
            [issue.failure.code for issue in result.issues], ["PREDICTABLE_CLIPPING"]
        )
        self.assertEqual(trial.stimulus.program.program_json, authored)

    def test_default_and_file_policy_values_are_typed(self) -> None:
        defaults = load_defaults(_ROOT)
        self.assertTrue(defaults.HasField("save_visual_stimulus_data"))
        self.assertTrue(defaults.save_visual_stimulus_data)
        policies = load_file_policies(_ROOT)
        self.assertEqual(policies.contract_version, 1)
        self.assertEqual(policies.limits.max_expanded_epochs, 100_000)
        self.assertEqual(policies.max_result_age_ns, 350_000_000)
        self.assertEqual(policies.record_sync_interval_ns, 1_000_000_000)
        self.assertTrue(policies.HasField("pacing_refresh_hz"))
        self.assertEqual(policies.pacing_refresh_hz, 60.0)
        self.assertFalse(policies.HasField("pacing_output_id"))

    def test_display_validation_returns_exact_output_ids(self) -> None:
        surface = {
            "bottom_left_mm": [-10.0, 10.0, 100.0],
            "bottom_right_mm": [10.0, 10.0, 100.0],
            "top_right_mm": [10.0, -10.0, 100.0],
            "top_left_mm": [-10.0, -10.0, 100.0],
        }
        profile = {
            "format_version": 1,
            "geometry": {
                "frame_id": "frame",
                "observer_mm": [0.0, 0.0, 0.0],
                "near_mm": 1.0,
                "far_mm": 1000.0,
                "positional_tolerance_mm": 0.1,
                "orthogonality_tolerance": 0.01,
                "surfaces": [
                    {"surface_id": name, **surface}
                    for name in ("front", "left", "right", "bottom")
                ],
            },
            "outputs": [
                {
                    "output_id": "projector/main",
                    "device_identity": "edid:one",
                    "width_px": 100,
                    "height_px": 100,
                    "refresh_numerator": 60,
                    "refresh_denominator": 1,
                    "rgb_bits_per_channel": 8,
                }
            ],
            "mappings": [
                {
                    "mapping_id": f"map-{name}",
                    "surface_id": name,
                    "output_id": "projector/main",
                    "viewport": {"x": 0, "y": 0, "width": 100, "height": 100},
                    "geometric_profile": {"logical_path": f"geometry/{name}.json"},
                }
                for name in ("front", "left", "right", "bottom")
            ],
            "photometric_mode": "uncalibrated",
            "idle_linear_rgb": [0.0, 0.0, 0.0],
            "photodiode_output_id": "projector/main",
        }
        import json

        self.assertEqual(
            validate_display_profile(json.dumps(profile)), frozenset({"projector/main"})
        )
        profile["photodiode_output_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown photodiode output"):
            validate_display_profile(json.dumps(profile))


if __name__ == "__main__":
    unittest.main()


def test_output_subsets_preserve_rig_geometry_and_calibrated_mappings():
    from itertools import product

    import pytest
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
    from cephvr.visual_stimulus.rendering.arena import off_axis_view_projection

    source = json.loads(valid_display_json())
    prototype = source["outputs"][0]
    source["outputs"] = [
        dict(prototype, output_id=f"projector/{name}", device_identity=f"edid:{name}")
        for name in ("front", "left", "right", "bottom")
    ]
    for mapping, output in zip(source["mappings"], source["outputs"], strict=True):
        mapping["output_id"] = output["output_id"]
    source["photodiode_output_id"] = None
    source["photodiode_patch"] = None
    source["presentation_mode"] = "all_outputs_vsync"
    full = DisplayProfile.model_validate_json(json.dumps(source))
    matrices = [
        off_axis_view_projection(full, surface) for surface in full.geometry.surfaces
    ]
    for choices in product((False, True), repeat=4):
        if not any(choices):
            continue
        for output, enabled in zip(source["outputs"], choices, strict=True):
            output["enabled"] = enabled
        selected = DisplayProfile.model_validate_json(json.dumps(source))
        assert selected.geometry == full.geometry
        assert selected.mappings == full.mappings
        assert len(selected.active_outputs) == sum(choices)
        assert {m.output_id for m in selected.active_mappings} == {
            o.output_id for o in selected.active_outputs
        }
        assert [
            off_axis_view_projection(selected, surface)
            for surface in selected.geometry.surfaces
        ] == matrices
        assert validate_display_profile(
            json.dumps(source), max_bytes=1_000_000
        ) == frozenset(o.output_id for o in selected.active_outputs)
    for output in source["outputs"]:
        output["enabled"] = False
    with pytest.raises(ValueError, match="at least one"):
        DisplayProfile.model_validate_json(json.dumps(source))
    source["outputs"][1]["enabled"] = True
    source["photodiode_output_id"] = source["outputs"][0]["output_id"]
    with pytest.raises(ValueError, match="photodiode output must be enabled"):
        DisplayProfile.model_validate_json(json.dumps(source))


def test_reference_guide_and_seam_view_are_bounded_profile_fields():
    import pytest
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.config.calibration_adjustments import (
        LIVE_ADJUSTABLE_VIEWS,
    )
    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

    source = json.loads(valid_display_json())
    output = source["outputs"][0]
    width, height = output["width_px"], output["height_px"]

    def parsed(**changes):
        source["outputs"][0]["reference_bars"] = dict(
            x_length_px=10, y_length_px=10, **changes
        )
        return DisplayProfile.model_validate_json(json.dumps(source))

    guided = parsed(guide_width_px=width // 2, guide_height_px=height // 2)
    assert guided.outputs[0].reference_bars.guide_width_px == width // 2
    assert parsed().outputs[0].reference_bars.guide_height_px is None
    with pytest.raises(ValueError, match="both width and height"):
        parsed(guide_width_px=10)
    with pytest.raises(ValueError, match="exceed the output"):
        parsed(guide_width_px=width + 1, guide_height_px=10)
    parsed()  # Restore valid bars after the rejected guides.
    source["calibration_view"] = "seam_check"
    assert DisplayProfile.model_validate_json(json.dumps(source)).calibration_view == (
        "seam_check"
    )
    assert LIVE_ADJUSTABLE_VIEWS == {"frame_grid", "seam_check"}
    source["calibration_view"] = "unknown_view"
    with pytest.raises(ValueError):
        DisplayProfile.model_validate_json(json.dumps(source))


def test_projective_mesh_keeps_corners_lines_and_perspective_spacing():
    import pytest

    from cephvr.visual_stimulus.config.calibration_adjustments import (
        CalibrationAdjustmentRejected,
        is_convex_quadrilateral,
        projective_mesh,
        validated_adjustments,
    )

    rectangle = ((0.1, 0.2), (0.9, 0.2), (0.1, 0.8), (0.9, 0.8))
    uniform = projective_mesh(rectangle, 3, 3)
    assert [(round(x, 9), round(y, 9)) for _, _, x, y in uniform] == [
        (0.1, 0.2), (0.5, 0.2), (0.9, 0.2),
        (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
        (0.1, 0.8), (0.5, 0.8), (0.9, 0.8),
    ]  # fmt: skip
    trapezoid = ((0.0, 0.0), (1.0, 0.0), (0.25, 1.0), (0.75, 1.0))
    mesh = projective_mesh(trapezoid, 9, 9)
    for index, corner in zip((0, 8, 72, 80), trapezoid, strict=True):
        assert mesh[index][2:] == pytest.approx(corner)
    left_edge = [mesh[9 * row][2:] for row in range(9)]
    for x, y in left_edge:  # the left edge stays on the straight line x = y / 4
        assert x == pytest.approx(0.25 * y)
    gaps = [b[1] - a[1] for a, b in zip(left_edge, left_edge[1:], strict=False)]
    assert all(later < earlier for earlier, later in zip(gaps, gaps[1:], strict=False))
    centre = [mesh[9 * row + 4][2] for row in range(9)]
    assert centre == pytest.approx([0.5] * 9)  # symmetry is preserved
    assert is_convex_quadrilateral(trapezoid)
    assert not is_convex_quadrilateral(((0, 0), (1, 0), (0.5, 0.2), (0.7, 1)))
    assert not is_convex_quadrilateral(((0, 0), (1, 0), (0, 0), (1, 0)))
    with pytest.raises(ValueError, match="convex"):
        projective_mesh(((0, 0), (1, 0), (0.5, 0.2), (0.7, 1)), 3, 3)
    flat = [x for corner in trapezoid for x in corner]
    assert validated_adjustments([("front", flat)])["front"] == trapezoid
    for bad in (
        [0, 0, 1, 0, 0.5, 0.2, 0.7, 1],
        [0, 0, 1, 1, 0, 0, 1, 1],
        [0, 0, 1, 0, 0, 1, 1.5, 1],
    ):
        with pytest.raises(CalibrationAdjustmentRejected):
            validated_adjustments([("front", bad)])


def test_photodiode_visibility_is_independent_of_pacing_and_disabled_target():
    import pytest
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

    source = json.loads(valid_display_json())
    output = dict(
        source["outputs"][0],
        output_id="projector/off",
        device_identity="edid:off",
        enabled=False,
    )
    source["outputs"].append(output)
    source["mappings"].append(
        dict(source["mappings"][0], mapping_id="off-map", output_id="projector/off")
    )
    source.update(
        photodiode_enabled=False,
        photodiode_output_id="projector/off",
        pacing_output_id="projector/main",
    )
    display = DisplayProfile.model_validate_json(json.dumps(source))
    display.require_trial_marker()
    assert display.marker_output_id is None
    assert display.selected_pacing_output_id == "projector/main"
    source["photodiode_output_id"] = "projector/disconnected"
    DisplayProfile.model_validate_json(json.dumps(source)).require_trial_marker()
    source["photodiode_enabled"] = True
    with pytest.raises(ValueError, match="unknown photodiode"):
        DisplayProfile.model_validate_json(json.dumps(source))
    source["photodiode_enabled"] = False
    source["pacing_output_id"] = "projector/off"
    with pytest.raises(ValueError, match="pacing output"):
        DisplayProfile.model_validate_json(json.dumps(source))


def test_file_pacing_overlays_stable_output_and_checks_native_rate():
    import pytest
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
    from cephvr.visual_stimulus.configuration import resolve_pacing_profile

    source = json.loads(valid_display_json())
    source["pacing_output_id"] = None
    display = DisplayProfile.model_validate_json(json.dumps(source))
    resolved = resolve_pacing_profile(
        json.dumps(source),
        max_bytes=1_000_000,
        refresh_hz=60.0,
        output_id="projector/main",
    )
    assert resolved.selected_pacing_output_id == "projector/main"
    assert display.pacing_output_id is None
    assert resolved.pacing_output_id == "projector/main"
    source["outputs"][0]["refresh_numerator"] = 60_000
    source["outputs"][0]["refresh_denominator"] = 1_001
    fractional = resolve_pacing_profile(
        json.dumps(source),
        max_bytes=1_000_000,
        refresh_hz=60.0,
        output_id="projector/main",
    )
    assert fractional.outputs[0].refresh_numerator == 60_000
    assert fractional.outputs[0].refresh_denominator == 1_001
    source["photodiode_enabled"] = False
    source["photodiode_output_id"] = None
    source.pop("pacing_output_id", None)
    disabled_marker = resolve_pacing_profile(
        json.dumps(source),
        max_bytes=1_000_000,
        refresh_hz=60.0,
        output_id="projector/main",
    )
    assert disabled_marker.marker_output_id is None
    assert disabled_marker.selected_pacing_output_id == "projector/main"
    with pytest.raises(ValueError, match="does not match configured target"):
        resolve_pacing_profile(
            json.dumps(source),
            max_bytes=1_000_000,
            refresh_hz=75.0,
            output_id="projector/main",
        )
    with pytest.raises(ValueError, match="pacing output"):
        resolve_pacing_profile(
            json.dumps(source),
            max_bytes=1_000_000,
            refresh_hz=60.0,
            output_id="projector/missing",
        )


def test_all_output_vsync_without_pacer_preserves_common_recording_rate():
    import pytest
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.configuration import resolve_pacing_profile

    source = json.loads(valid_display_json())
    source.update(
        presentation_mode="all_outputs_vsync",
        photodiode_enabled=False,
        photodiode_output_id=None,
        pacing_output_id=None,
    )
    second = dict(
        source["outputs"][0], output_id="second", device_identity="second-device"
    )
    source["outputs"].append(second)
    source["mappings"].append(
        dict(source["mappings"][0], mapping_id="second-map", output_id="second")
    )
    resolved = resolve_pacing_profile(
        json.dumps(source), max_bytes=1_000_000, refresh_hz=60.0, output_id=None
    )
    resolved.require_trial_marker()
    assert resolved.selected_pacing_output_id is None
    assert resolved.review_refresh_rate() == (60, 1)
    second["refresh_numerator"] = 30
    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

    with pytest.raises(ValueError, match="common nominal"):
        DisplayProfile.model_validate_json(json.dumps(source)).review_refresh_rate()
    with pytest.raises(ValueError, match="configured target"):
        resolve_pacing_profile(
            json.dumps(source), max_bytes=1_000_000, refresh_hz=60.0, output_id=None
        )
    source["presentation_mode"] = "photodiode_only_vsync"
    with pytest.raises(ValueError, match="pacing output"):
        resolve_pacing_profile(
            json.dumps(source), max_bytes=1_000_000, refresh_hz=60.0, output_id=None
        )


def test_review_reduction_scales_capture_tiles_without_changing_display() -> None:
    from types import SimpleNamespace as NS

    import pytest

    from cephvr.shared.ffmpeg_types import EncodingOptionsError
    from cephvr.visual_stimulus.recording.encoding import _composite_geometry

    outputs = tuple(
        NS(width_px=1280, height_px=1000, output_id=str(i)) for i in range(4)
    )
    display = NS(active_outputs=outputs)
    full = _composite_geometry(display, (4096, 4096))
    reduced = _composite_geometry(display, (4096, 4096), 2)
    assert full[:3] == (2560, 2000, 1)
    assert reduced[:3] == (1280, 1000, 2)
    assert reduced[0] * reduced[1] * 4 == full[0] * full[1]
    assert all((o.width_px, o.height_px) == (1280, 1000) for o in outputs)
    assert reduced[3] == (
        ("0", 0, 500, 640, 500),
        ("1", 640, 500, 640, 500),
        ("2", 0, 0, 640, 500),
        ("3", 640, 0, 640, 500),
    )
    # Apply extra reduction after the existing encoder-fit divisor.
    assert _composite_geometry(display, (1300, 1100), 2)[:3] == (640, 500, 4)
    for factor in (0, -1, True, 2000):
        with pytest.raises(EncodingOptionsError):
            _composite_geometry(display, (4096, 4096), factor)
    assert load_file_policies(_ROOT).review_scale_factor == 2
