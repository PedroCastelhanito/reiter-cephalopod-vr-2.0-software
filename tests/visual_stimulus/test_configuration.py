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
    def test_presentation_category_rejects_executable_motion(self) -> None:
        from copy import deepcopy

        from tests.visual_stimulus.support import fixture_source

        from cephvr.visual_stimulus.config.models.program_model import Program

        source = json.loads(fixture_source())
        source["category"] = "media_presentation"
        setting = source["sequence"][0]["settings"][0]
        setting["motion"] = {axis: {"kind": "hold"} for axis in ("x", "y", "rotation")}
        setting["phase_x"] = setting["phase_y"] = {"kind": "hold"}
        setting["width"] = setting["height"] = {"kind": "constant", "value": 10}
        setting["feedback"] = []
        Program.model_validate_json(json.dumps(source))
        for key, value in (
            ("phase_x", {"kind": "rate", "function": {"kind": "constant", "value": 1}}),
            ("width", {"kind": "ramp", "initial": 10, "slope_per_s": 1}),
            (
                "motion",
                {
                    "x": {"kind": "rate", "function": {"kind": "constant", "value": 1}},
                    "y": {"kind": "hold"},
                    "rotation": {"kind": "hold"},
                },
            ),
        ):
            candidate = deepcopy(source)
            candidate["sequence"][0]["settings"][0][key] = value
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "presentation"),
            ):
                Program.model_validate_json(json.dumps(candidate))
        legacy = deepcopy(source)
        del legacy["category"]
        self.assertIsNone(Program.model_validate_json(json.dumps(legacy)).category)

    def test_protocol_category_must_match_across_trials(self) -> None:
        from tests.visual_stimulus.support import fixture_source

        from cephvr.control.v1 import types_pb2 as pb

        candidate = pb.ExperimentConfiguration(mode=pb.SESSION_MODE_OPEN_LOOP)
        candidate.backends.add(
            backend_name="visual_stimulus",
            enabled=True,
            visual_stimulus=pb.VisualStimulusSettings(save_visual_stimulus_data=False),
        )
        for number, category in enumerate(("texture_drift", "navigation_3d"), 1):
            source = json.loads(fixture_source())
            source["category"] = category
            trial = candidate.trials.add(trial_number=number)
            trial.stimulus.program.program_json = json.dumps(source)
            trial.stimulus.arena_boundaries.boundaries_json = (
                '{"format_version":1,"bindings":[]}'
            )
        result = validate_configuration(candidate)
        self.assertFalse(result.valid)
        self.assertTrue(
            any(
                "same protocol category" in issue.failure.message
                for issue in result.issues
            )
        )

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
        self.assertEqual(policies.projection.near_mm, 1)
        self.assertEqual(policies.projection.far_mm, 250)
        self.assertEqual(policies.projection.positional_tolerance_mm, 0.000166)
        self.assertEqual(policies.projection.orthogonality_tolerance, 0.000001)

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


def test_per_output_pulses_validate_targets_bounds_and_vsync():
    import pytest
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
    from cephvr.visual_stimulus.config.pacing import apply_pacing_settings

    source = json.loads(valid_display_json())
    patch = source.pop("photodiode_patch")
    source["photodiode_output_id"] = None
    prototype = source["outputs"][0]
    names = ("front", "left", "right", "bottom")
    source["outputs"] = [
        dict(prototype, output_id=name, device_identity=name) for name in names
    ]
    for mapping, name in zip(source["mappings"], names, strict=True):
        mapping["output_id"] = name
    source["photodiode_patches"] = {name: patch for name in ("front", "left")}
    display = DisplayProfile.model_validate_json(json.dumps(source))
    display.require_trial_marker()
    assert set(display.marker_patches) == {"front", "left"}
    assert [display.requested_swap_interval(name) for name in names] == [1, 1, 0, 0]
    assert display.selected_pacing_output_id is None
    assert display.review_refresh_rate() == (60, 1)
    assert apply_pacing_settings(display, refresh_hz=60.0, output_id=None) == display
    for mode, intervals in (("free_run", [0] * 4), ("all_outputs_vsync", [1] * 4)):
        selected = DisplayProfile.model_validate_json(
            json.dumps(dict(source, presentation_mode=mode))
        )
        assert [selected.requested_swap_interval(name) for name in names] == intervals
    for invalid in (
        {"missing": patch},
        {"front": dict(patch, rect=dict(x=999999, y=0, width=1, height=1))},
    ):
        with pytest.raises(ValueError):
            DisplayProfile.model_validate_json(
                json.dumps(dict(source, photodiode_patches=invalid))
            )
    disabled = [dict(o, enabled=o["output_id"] != "left") for o in source["outputs"]]
    with pytest.raises(ValueError, match="enabled"):
        DisplayProfile.model_validate_json(json.dumps(dict(source, outputs=disabled)))
    inactive = DisplayProfile.model_validate_json(
        json.dumps(
            dict(
                source,
                outputs=disabled,
                photodiode_enabled=False,
                pacing_output_id="front",
            )
        )
    )
    assert not inactive.marker_patches
    assert [inactive.requested_swap_interval(name) for name in names] == [0] * 4
    assert len(inactive.photodiode_patches) == 2


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


def test_free_run_keeps_nominal_recording_rate_and_disables_every_swap():
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.configuration import resolve_pacing_profile

    source = json.loads(valid_display_json())
    source.update(
        presentation_mode="free_run",
        photodiode_enabled=False,
        photodiode_output_id=None,
        pacing_output_id=None,
    )
    resolved = resolve_pacing_profile(
        json.dumps(source), max_bytes=1_000_000, refresh_hz=60.0, output_id=None
    )
    resolved.require_trial_marker()
    assert resolved.review_refresh_rate() == (60, 1)
    assert all(
        resolved.requested_swap_interval(o.output_id) == 0
        for o in resolved.active_outputs
    )
    source.update(
        photodiode_enabled=True, photodiode_output_id=source["outputs"][0]["output_id"]
    )
    resolved = resolve_pacing_profile(
        json.dumps(source), max_bytes=1_000_000, refresh_hz=60.0, output_id=None
    )
    assert all(
        resolved.requested_swap_interval(o.output_id) == 0
        for o in resolved.active_outputs
    )
    for mode, expected in (("photodiode_only_vsync", 1), ("all_outputs_vsync", 1)):
        source["presentation_mode"] = mode
        resolved = resolve_pacing_profile(
            json.dumps(source), max_bytes=1_000_000, refresh_hz=60.0, output_id=None
        )
        assert (
            resolved.requested_swap_interval(source["outputs"][0]["output_id"])
            == expected
        )
        assert resolved.requested_swap_interval("other") == (
            1 if mode == "all_outputs_vsync" else 0
        )


def test_file_projection_overrides_saved_profile_and_reloads(tmp_path):
    import pytest
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.shared.config import ConfigurationError
    from cephvr.visual_stimulus.config.pacing import resolve_pacing_profile
    from cephvr.visual_stimulus.config.projection import policy_projection
    from cephvr.visual_stimulus.configuration import load_projection_settings

    config = tmp_path / "config/backends/visual_stimulus_config.toml"
    policy = tmp_path / "contracts/policy/visual_stimulus_policy.toml"
    config.parent.mkdir(parents=True)
    policy.parent.mkdir(parents=True)
    original = (_ROOT / config.relative_to(tmp_path)).read_text()
    config.write_text(original)
    policy.write_bytes((_ROOT / policy.relative_to(tmp_path)).read_bytes())
    limits = load_file_policies(tmp_path)
    source = json.loads(valid_display_json())
    source["geometry"].update(near_mm=5000, far_mm=1, orthogonality_tolerance=2)
    saved = json.dumps(source)
    resolved = resolve_pacing_profile(
        saved,
        max_bytes=1_000_000,
        refresh_hz=60.0,
        output_id=None,
        projection=policy_projection(limits.projection),
    )
    assert resolved.geometry.far_mm == 250
    assert resolved.geometry.near_mm == 1
    assert json.loads(saved)["geometry"]["near_mm"] == 5000
    config.write_text(original.replace("far_mm = 250.0", "far_mm = 1000.0"))
    assert load_projection_settings(tmp_path)["far_mm"] == 1000
    assert limits.projection.far_mm == 250
    for replacement in ("0", "nan", "true"):
        config.write_text(original.replace("near_mm = 1.0", "near_mm = " + replacement))
        with pytest.raises(ConfigurationError, match="projection.near_mm"):
            load_file_policies(tmp_path)
    config.write_text(original.replace("far_mm = 250.0", "far_mm = 0.5"))
    with pytest.raises(ConfigurationError, match="must precede"):
        load_file_policies(tmp_path)
    config.write_text(
        original.replace(
            "orthogonality_tolerance = 0.000001", "orthogonality_tolerance = 1"
        )
    )
    with pytest.raises(ConfigurationError, match="must be below 1"):
        load_projection_settings(tmp_path)


def test_review_reduction_scales_capture_tiles_without_changing_display() -> None:
    from types import SimpleNamespace as NS

    import pytest

    from cephvr.visual_stimulus.config.models.display_profile import PixelRect
    from cephvr.visual_stimulus.config.review_layout import (
        fit_review_layout,
        recording_layout,
        validate_layout,
    )

    outputs = tuple(
        NS(
            width_px=1000 if i == 3 else 1280,
            height_px=1280 if i == 3 else 1000,
            output_id=str(i),
            rgb_bits_per_channel=8,
        )
        for i in range(4)
    )
    mappings = tuple(
        NS(
            output_id=str(i),
            mapping_id=str(i),
            surface_id=face,
            viewport=PixelRect(
                x=0, y=0, width=outputs[i].width_px, height=outputs[i].height_px
            ),
        )
        for i, face in enumerate(("left", "front", "right", "bottom"))
    )
    display = NS(active_outputs=outputs, active_mappings=mappings)
    full = fit_review_layout(display, (4096, 4096))
    reduced = fit_review_layout(display, (4096, 4096), 2)
    assert (full.composite_width, full.composite_height) == (2560, 2000)
    assert (reduced.composite_width, reduced.composite_height) == (1280, 1000)
    assert all(t.rect.width == 640 and t.rect.height == 500 for t in reduced.tiles)
    assert (reduced.tiles[3].rect.width, reduced.tiles[3].rect.height) == (640, 500)
    assert reduced.tiles[3].rotation_clockwise_degrees == 90
    assert all(
        (t.source_rect.width, t.source_rect.height) == (o.width_px, o.height_px)
        for t, o in zip(reduced.tiles, outputs, strict=True)
    )
    assert [(t.cell.x, t.cell.y) for t in reduced.tiles] == [
        (0, 500),
        (640, 500),
        (0, 0),
        (640, 0),
    ]
    assert [t.label for t in reduced.tiles] == ["Left", "Front", "Right", "Bottom"]
    assert all(t.rect == t.cell for t in reduced.tiles)
    assert (
        sum(t.rect.width * t.rect.height for t in reduced.tiles)
        == reduced.composite_width * reduced.composite_height
    )
    legacy = recording_layout(display, layout_version=2)
    validate_layout(display, legacy)
    assert legacy.tiles[0].cell.height > legacy.tiles[0].rect.height
    fitted = fit_review_layout(display, (1300, 1100), 2)
    assert (
        fitted.composite_width,
        fitted.composite_height,
        fitted.scale_denominator,
    ) == (640, 500, 4)
    for factor in (0, -1, True, 2000):
        with pytest.raises(ValueError):
            fit_review_layout(display, (4096, 4096), factor)
    assert load_file_policies(_ROOT).review_scale_factor == 2


def test_review_crops_use_calibration_and_fit_mixed_aspect_without_rotation():
    from types import SimpleNamespace as NS

    from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
    from cephvr.visual_stimulus.config.models.display_profile import PixelRect
    from cephvr.visual_stimulus.config.review_layout import (
        review_layout,
        validate_layout,
    )

    outputs = tuple(
        NS(output_id=face, width_px=1000, height_px=800, rgb_bits_per_channel=8)
        for face in ("bottom", "right", "front", "left")
    )
    viewport = PixelRect(x=100, y=80, width=800, height=640)
    mappings = tuple(
        NS(
            output_id=o.output_id,
            mapping_id=o.output_id,
            surface_id=o.output_id,
            viewport=viewport,
        )
        for o in outputs
    )
    display = NS(active_outputs=outputs, active_mappings=mappings)
    profiles = {
        o.output_id: GeometricProfile.model_construct(
            valid_area=(0.2, 0.25, 0.8, 0.75),
            intended_coverage=((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        for o in outputs
    }
    profiles["bottom"] = profiles["bottom"].model_copy(
        update={"valid_area": (0.4, 0.1, 0.6, 0.9)}
    )
    profiles["front"] = profiles["front"].model_copy(
        update={
            "valid_area": None,
            "intended_coverage": (
                (0.25, 0.25),
                (0.75, 0.25),
                (0.75, 0.75),
                (0.25, 0.75),
            ),
        }
    )
    layout = review_layout(display, 2, profiles)
    validate_layout(display, layout)
    assert [t.output_id for t in layout.tiles] == ["left", "front", "right", "bottom"]
    left, front, right, bottom = layout.tiles
    assert left.source_rect == PixelRect(x=200, y=200, width=600, height=400)
    assert front.source_rect == PixelRect(x=300, y=240, width=400, height=320)
    assert bottom.source_rect == PixelRect(x=400, y=80, width=200, height=640)
    assert (layout.composite_width, layout.composite_height) == (800, 520)
    assert (bottom.rect.width, bottom.rect.height) == (100, 320)
    assert bottom.rect.x == 350
    assert left.rect.y == 320
    assert left.rect.y == right.rect.y == front.rect.y
    assert left.rect.y > bottom.rect.y and left.rect.x < front.rect.x < right.rect.x
    # Cropping has no image input, so black content cannot change the layout.
    assert review_layout(display, 2, profiles) == layout
