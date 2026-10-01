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
