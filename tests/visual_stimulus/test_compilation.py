"""Deterministic Visual Stimulus expansion, duration, and transition compiler checks."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from tests.visual_stimulus.support import (
    fixture_source,
    make_prepared_trial,
    make_program,
)

from cephvr.visual_stimulus.compiler import (
    expand_program,
    prepared_digest,
    resolve_durations,
    serialize_prepared_trial,
)
from cephvr.visual_stimulus.compiler.durations import (
    DURATION_SAMPLER_ID,
    stafford_workspace_bytes,
)
from cephvr.visual_stimulus.compiler.transitions import compile_boundaries
from cephvr.visual_stimulus.config.models.artifact_models import CompiledEpoch
from cephvr.visual_stimulus.config.models.program_model import (
    Fixed,
    Random,
    TargetTotal,
    Time,
    VideoSettings,
    parse_program_json,
)


class VideoTransitionTests(unittest.TestCase):
    _space = make_program().sequence[0].settings[0].space

    @staticmethod
    def _video(asset_id: str, end_behavior: str = "loop") -> VideoSettings:
        return VideoSettings.model_construct(
            instance_id="video-instance",
            space=VideoTransitionTests._space,
            initial=None,
            width=None,
            height=None,
            opacity=None,
            motion=None,
            reset=False,
            assignments=(),
            feedback=(),
            kind="video",
            asset_id=asset_id,
            sampling="nearest",
            initial_playback=Time(seconds="0"),
            end_behavior=end_behavior,
        )

    @staticmethod
    def _epoch(
        index: int, start: int, settings: tuple[VideoSettings, ...]
    ) -> CompiledEpoch:
        return CompiledEpoch.model_construct(
            occurrence_index=index,
            source_epoch_id=f"epoch-{index}",
            duration_origin="fixed",
            lineage=(),
            scene_id=f"scene-{index}",
            start_ns=start,
            end_ns=start + 1,
            truncated_curves=(),
            settings=settings,
        )

    def test_video_asset_variants_restart_after_absence_but_behavior_change_resumes(
        self,
    ):
        epochs = (
            self._epoch(0, 0, (self._video("movie-a"),)),
            self._epoch(1, 1, ()),
            self._epoch(2, 2, (self._video("movie-a", "hold_final_frame"),)),
            self._epoch(3, 3, (self._video("movie-b"),)),
        )
        boundaries = compile_boundaries(epochs)
        actions = [
            next(
                (
                    item.action
                    for item in boundary.operations
                    if item.instance_id == "video-instance"
                ),
                None,
            )
            for boundary in boundaries
        ]
        self.assertEqual(
            actions,
            ["initialize", "pause", "resume", "restart_incompatible", "deactivate"],
        )


class DurationResolutionTests(unittest.TestCase):
    def test_large_stafford_workspace_is_reserved_before_allocation(self) -> None:
        class Budget:
            def check_cancelled_or_expired(self):
                return None

            def reserve(self, *, owner, cpu_bytes, gpu_bytes):
                self.requested = (owner, cpu_bytes, gpu_bytes)
                raise MemoryError("budget")

            def release(self, *, owner):
                raise AssertionError("unreserved workspace must not be released")

        count = 100_000
        self.assertGreater(stafford_workspace_bytes(count), 900_000_000_000)
        budget = Budget()
        target = TargetTotal(
            kind="target_total_random_epochs",
            total=Time(seconds="150000"),
            minimum=Time(seconds="1"),
            maximum=Time(seconds="2"),
        )
        with patch(
            "cephvr.visual_stimulus.compiler.durations._stafford_unit_sum"
        ) as sampler:
            with self.assertRaises(MemoryError):
                resolve_durations(
                    (Random(kind="random"),) * count,
                    target,
                    "11",
                    budget=budget,
                )
        sampler.assert_not_called()
        self.assertEqual(budget.requested[1], stafford_workspace_bytes(count))

    def test_stafford_golden_and_repeatability(self) -> None:
        target = TargetTotal(
            kind="target_total_random_epochs",
            total=Time(seconds="60"),
            minimum=Time(seconds="10"),
            maximum=Time(seconds="30"),
        )
        occurrences = (Random(kind="random"),) * 3
        first = resolve_durations(occurrences, target, "42")
        second = resolve_durations(occurrences, target, "42")
        self.assertEqual(first, second)
        self.assertEqual(
            first.durations_ns,
            (12_001_198_698, 26_940_834_898, 21_057_966_404),
        )
        self.assertEqual(sum(first.durations_ns), 60_000_000_000)
        self.assertTrue(
            all(
                10_000_000_000 <= value <= 30_000_000_000
                for value in first.durations_ns
            )
        )
        self.assertEqual(first.sampler_id, DURATION_SAMPLER_ID)

    def test_fixed_and_uniquely_constrained_cases(self) -> None:
        fixed = resolve_durations(
            (Fixed(kind="fixed", duration=Time(seconds="30")),) * 2,
            None,
            "0",
        )
        self.assertEqual(fixed.durations_ns, (30_000_000_000,) * 2)
        target = TargetTotal(
            kind="target_total_random_epochs",
            total=Time(seconds="60"),
            minimum=Time(seconds="10"),
            maximum=Time(seconds="60"),
        )
        result = resolve_durations((Random(kind="random"),), target, "5")
        self.assertEqual(result.durations_ns, (60_000_000_000,))
        self.assertEqual(result.origins, ("uniquely_constrained",))
        self.assertFalse(result.variability_possible)

    def test_rejects_infeasible_target_and_explicit_random_epoch(self) -> None:
        target = TargetTotal(
            kind="target_total_random_epochs",
            total=Time(seconds="60"),
            minimum=Time(seconds="31"),
            maximum=Time(seconds="35"),
        )
        with self.assertRaisesRegex(ValueError, "infeasible"):
            resolve_durations((Random(kind="random"),) * 2, target, "5")
        with self.assertRaisesRegex(ValueError, "require target-total"):
            resolve_durations((Random(kind="random"),), None, "5")


class ExpansionTests(unittest.TestCase):
    def _program(self, payload: dict[str, object]):
        source = json.dumps(payload)
        return parse_program_json(source, max_bytes=1_000_000)

    def test_repeated_group_preserves_authored_identity_and_lineage(self) -> None:
        payload = json.loads(fixture_source())
        original = payload["sequence"]
        payload["sequence"] = [
            {
                "kind": "group",
                "group_id": "repeat",
                "repetitions": 2,
                "order": "shuffle_each_repetition",
                "order_unit": "child_blocks",
                "conditions": None,
                "body": original,
            }
        ]
        program = self._program(payload)
        first = expand_program(program, seed_decimal="1234", max_expanded_epochs=8)
        again = expand_program(program, seed_decimal="1234", max_expanded_epochs=8)
        self.assertEqual(first, again)
        self.assertEqual(len(first), 4)
        self.assertEqual([item.source.epoch_id for item in first].count("drift"), 2)
        self.assertTrue(all(item.lineage[0].group_id == "repeat" for item in first))
        self.assertEqual([item.lineage[0].visit_index for item in first], [0, 1, 2, 3])
        with self.assertRaisesRegex(ValueError, "max_expanded_epochs"):
            expand_program(program, seed_decimal="1234", max_expanded_epochs=3)

    def test_repetition_settings_follow_group_visit_and_validate_all_samples(
        self,
    ) -> None:
        payload = json.loads(fixture_source())
        original = payload["sequence"]
        samples = [deepcopy(original[0]["settings"]) for _ in range(2)]
        for sample, opacity in zip(samples, (0.2, 0.8), strict=True):
            sample[0]["opacity"] = {"kind": "constant", "value": opacity}
        original[0]["repetition_settings"] = samples
        payload["sequence"] = [
            {
                "kind": "group",
                "group_id": "repeat",
                "repetitions": 2,
                "order": "shuffle_each_repetition",
                "order_unit": "child_blocks",
                "conditions": None,
                "body": original,
            }
        ]
        program = self._program(payload)
        expanded = expand_program(program, seed_decimal="42", max_expanded_epochs=8)
        chosen = [e for e in expanded if e.source.epoch_id == original[0]["epoch_id"]]
        self.assertEqual([e.settings[0].opacity.value for e in chosen], [0.2, 0.8])
        self.assertEqual([e.lineage[-1].repetition_index for e in chosen], [0, 1])
        self.assertEqual(self._program(json.loads(program.model_dump_json())), program)
        samples.pop()
        with self.assertRaisesRegex(ValueError, "enclosing group repetitions"):
            self._program(payload)
        samples.append(deepcopy(samples[0]))
        samples[1][0]["instance_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "complete settings"):
            self._program(payload)

    def test_compact_random_rules_are_reproducible_and_bounded_only_at_expansion(
        self,
    ) -> None:
        from cephvr.visual_stimulus.config.models.repetition import RepetitionRule
        from cephvr.visual_stimulus.config.repetition_values import sample_at

        rule = RepetitionRule(
            instance_id="texture",
            parameter="Speed",
            minimum="0",
            maximum="1000000",
            precision="1",
            seed="0" * 32,
        )
        self.assertEqual(
            [sample_at(rule, i) for i in (0, 1, 1000000)],
            ["774690", "525904", "367560"],
        )
        self.assertNotEqual(
            sample_at(rule, 0),
            sample_at(rule.model_copy(update={"stream": "other"}), 0),
        )
        payload = json.loads(fixture_source())
        original = payload["sequence"]
        original[0]["repetition_rules"] = [
            rule.model_copy(
                update={
                    "instance_id": original[0]["settings"][0]["instance_id"],
                    "parameter": "Angular speed",
                }
            ).model_dump(mode="json")
        ]
        payload["sequence"] = [
            {
                "kind": "group",
                "group_id": "repeat",
                "repetitions": 3,
                "order": "as_listed",
                "order_unit": "child_blocks",
                "conditions": None,
                "body": original,
            }
        ]
        program = self._program(payload)
        result = expand_program(program, seed_decimal="1", max_expanded_epochs=6)
        self.assertNotEqual(result[0].settings, result[2].settings)
        self.assertEqual(
            result,
            expand_program(
                self._program(json.loads(program.model_dump_json())),
                seed_decimal="2",
                max_expanded_epochs=6,
            ),
        )
        payload["sequence"][0]["repetitions"] = 1000000
        large = self._program(payload)
        self.assertLess(
            len(large.model_dump_json()) - len(program.model_dump_json()), 16
        )
        with patch(
            "cephvr.visual_stimulus.compiler.expansion.resolve_repetition"
        ) as resolve:
            with self.assertRaisesRegex(ValueError, "max_expanded_epochs"):
                expand_program(large, seed_decimal="1", max_expanded_epochs=100000)
            resolve.assert_not_called()

    def test_batch_labels_round_trip_without_changing_expansion(self) -> None:
        payload = json.loads(fixture_source())
        original = self._program(payload)
        self.assertEqual(original.sequence[0].batch_label, "")
        payload["sequence"][0]["batch_label"] = "Adaptation"
        payload["sequence"][0]["subgroup_draft"] = {
            "enabled": True,
            "rules": [
                {
                    "projector": "Left",
                    "layer": 0,
                    "parameter": "Speed",
                    "method": 2,
                    "minimum": "0",
                    "maximum": "10",
                }
            ],
        }
        labelled = self._program(payload)
        reloaded = parse_program_json(labelled.model_dump_json(), max_bytes=1_000_000)
        self.assertEqual(reloaded, labelled)
        old = expand_program(original, seed_decimal="1234", max_expanded_epochs=8)
        new = expand_program(reloaded, seed_decimal="1234", max_expanded_epochs=8)
        self.assertEqual(new[0].source.batch_label, "Adaptation")
        self.assertEqual([e.settings for e in old], [e.settings for e in new])
        self.assertEqual(
            [e.source.duration for e in old], [e.source.duration for e in new]
        )
        payload["sequence"][0]["batch_label"] = "x" * 129
        with self.assertRaises(ValueError):
            self._program(payload)

    def test_condition_values_are_substituted_at_setup(self) -> None:
        payload = json.loads(fixture_source())
        block = payload["sequence"][0]["settings"][0]
        block["width"] = {
            "kind": "constant",
            "value": {"kind": "condition", "group_id": "sizes", "column_id": "width"},
        }
        payload["sequence"] = [
            {
                "kind": "group",
                "group_id": "sizes",
                "repetitions": 1,
                "order": "as_listed",
                "order_unit": "condition_rows",
                "conditions": {
                    "columns": [
                        {"column_id": "width", "value_type": "number", "unit": "mm"}
                    ],
                    "rows": [
                        {
                            "row_id": "small",
                            "cells": [{"column_id": "width", "value": 80.0}],
                        },
                        {
                            "row_id": "large",
                            "cells": [{"column_id": "width", "value": 120.0}],
                        },
                    ],
                },
                "body": payload["sequence"],
            }
        ]
        program = self._program(payload)
        expanded = expand_program(program, seed_decimal="99", max_expanded_epochs=8)
        first_epoch_widths = [
            item.settings[0].width.value
            for item in expanded
            if item.source.epoch_id == "drift"
        ]
        self.assertEqual(first_epoch_widths, [80.0, 120.0])
        row_lineage = [
            item.lineage[0].unit_id
            for item in expanded
            if item.source.epoch_id == "drift"
        ]
        self.assertEqual(row_lineage, ["small", "large"])

    def test_prepared_artifact_and_canonical_bytes(self) -> None:
        prepared = make_prepared_trial()
        digest, length, encoded = prepared_digest(prepared)
        self.assertEqual(encoded, serialize_prepared_trial(prepared))
        self.assertEqual(length, len(encoded))
        self.assertEqual(len(digest), 64)
        self.assertEqual(prepared.resolved_duration_ns, 60_000_000_000)
        self.assertEqual(prepared.boundaries[0].operations[0].action, "initialize")
        self.assertEqual(prepared.boundaries[-1].operations[0].action, "deactivate")


if __name__ == "__main__":
    unittest.main()


def _linked_texture_fixture():
    """Unequal observer distances and inward-facing rectangular screen axes."""
    from cephvr.visual_stimulus.config.models.display_profile import Geometry
    from cephvr.visual_stimulus.config.models.program_model import TextureSettings

    geometry = Geometry.model_validate_json(
        json.dumps(
            {
                "frame_id": "rig-mm",
                "observer_mm": [0, 0, 0],
                "near_mm": 1,
                "far_mm": 1000,
                "positional_tolerance_mm": 0.01,
                "orthogonality_tolerance": 0.001,
                "surfaces": [
                    {
                        "surface_id": face,
                        "bottom_left_mm": bl,
                        "bottom_right_mm": br,
                        "top_right_mm": tr,
                        "top_left_mm": tl,
                    }
                    for face, bl, br, tr, tl in (
                        (
                            "bottom",
                            [-100, -100, -30],
                            [100, -100, -30],
                            [100, 100, -30],
                            [-100, 100, -30],
                        ),
                        (
                            "front",
                            [100, -100, -30],
                            [-100, -100, -30],
                            [-100, -100, 100],
                            [100, -100, 100],
                        ),
                        (
                            "left",
                            [-40, -100, -30],
                            [-40, 100, -30],
                            [-40, 100, 100],
                            [-40, -100, 100],
                        ),
                        (
                            "right",
                            [60, 100, -30],
                            [60, -100, -30],
                            [60, -100, 100],
                            [60, 100, 100],
                        ),
                    )
                ],
            }
        )
    )
    base = make_program().sequence[0].settings[0].model_dump(mode="json")
    settings = []
    for face, period in (("bottom", 100), ("front", 50), ("left", 80), ("right", 120)):
        data = deepcopy(base)
        data.update(
            instance_id=face,
            linked_to=None if face == "bottom" else "bottom",
            pattern={
                "kind": "image_tile",
                "asset_id": face,
                "period_x": {"kind": "constant", "value": period},
                "period_y": {"kind": "constant", "value": period},
                "sampling": "nearest",
            },
            space={
                "kind": "physical_surface",
                "frame_id": "rig-mm",
                "mappings": [{"surface_id": face, "matrix": [[1, 0, 0], [0, 1, 0]]}],
            },
            motion={k: {"kind": "hold"} for k in ("x", "y", "rotation")},
            phase_x={"kind": "hold"},
            phase_y={"kind": "hold"},
            reset=False,
        )
        settings.append(TextureSettings.model_validate_json(json.dumps(data)))
    return geometry, settings


def _texture_rate(value):
    from cephvr.visual_stimulus.config.models.program_model import Constant, Rate

    return Rate(kind="rate", function=Constant(kind="constant", value=float(value)))


def test_linked_translation_unfolds_without_losing_speed_and_keeps_independent_tiles():
    import math

    import pytest

    from cephvr.visual_stimulus.config.texture_links import linked_rates, validate_links

    geometry, settings = _linked_texture_fixture()
    source = settings[0].model_copy(update={"phase_y": _texture_rate(-0.5)})
    validate_links([source, *settings[1:]], resolved=True)
    results = [
        linked_rates(source, t, geometry, source_rotation=0, target_rotation=0)
        for t in settings[1:]
    ]
    # Bottom +Y = rearward: Front flows down; side local X axes oppose.
    assert results[0] == pytest.approx((0, 1, 0))
    assert results[1] == pytest.approx((-50 / 80, 0, 0))
    assert results[2] == pytest.approx((50 / 120, 0, 0))
    for target, result in zip(settings[1:], results, strict=True):
        reverse_source = target.model_copy(
            update={
                "linked_to": None,
                "phase_x": _texture_rate(result[0]),
                "phase_y": _texture_rate(result[1]),
            }
        )
        back = linked_rates(
            reverse_source, settings[0], geometry, source_rotation=0, target_rotation=0
        )
        assert back == pytest.approx((0, -0.5, 0))
        assert math.hypot(
            result[0] * target.pattern.period_x.value,
            result[1] * target.pattern.period_y.value,
        ) == pytest.approx(50)
    assert [s.pattern.asset_id for s in settings] == [
        "bottom",
        "front",
        "left",
        "right",
    ]


def test_linked_clockwise_rotation_uses_rig_distance_and_reverses():
    import math

    import pytest

    from cephvr.visual_stimulus.config.texture_links import linked_rates

    geometry, settings = _linked_texture_fixture()
    for angle in (-90, 90):
        source = settings[0].model_copy(
            update={
                "motion": settings[0].motion.model_copy(
                    update={"rotation": _texture_rate(angle)}
                )
            }
        )
        left, right = [
            linked_rates(source, t, geometry, source_rotation=37, target_rotation=0)
            for t in settings[2:]
        ]
        assert left == pytest.approx((-math.radians(angle) * 40 / 80, 0, 0))
        assert right == pytest.approx((-math.radians(angle) * 60 / 120, 0, 0))
        # For clockwise Bottom, both local X phase rates are positive: Left -Y,
        # Right +Y because their physical local X axes point opposite ways.
        assert (left[0] > 0) == (angle < 0)


def test_link_validation_rejects_competing_or_ambiguous_writers():
    import pytest

    from cephvr.visual_stimulus.config.models.program_model import Hold
    from cephvr.visual_stimulus.config.texture_links import linked_rates, validate_links

    geometry, settings = _linked_texture_fixture()
    source, target = settings[:2]
    for changes, match in (
        ({"linked_to": "missing"}, "active"),
        ({"linked_to": "front"}, "another"),
        ({"phase_x": _texture_rate(1)}, "cannot also own"),
    ):
        with pytest.raises(ValueError, match=match):
            validate_links([source, target.model_copy(update=changes)], resolved=True)
    with pytest.raises(ValueError, match="chains/cycles"):
        validate_links([source.model_copy(update={"linked_to": "front"}), target])
    spin = source.model_copy(
        update={
            "phase_x": _texture_rate(1),
            "motion": source.motion.model_copy(update={"rotation": _texture_rate(1)}),
        }
    )
    with pytest.raises(ValueError, match="separately"):
        validate_links([spin, target], resolved=True)
    singular = source.space.mappings[0].model_copy(
        update={"matrix": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))}
    )
    with pytest.raises(ValueError, match="uniform-scale"):
        linked_rates(
            source.model_copy(
                update={
                    "space": source.space.model_copy(update={"mappings": (singular,)})
                }
            ),
            target,
            geometry,
            source_rotation=0,
            target_rotation=0,
        )
    assert isinstance(target.phase_x, Hold)


def test_link_binding_retains_each_phase_and_orientation_across_stop_and_relink():
    import pytest

    from cephvr.visual_stimulus.config.models.program_model import Hold
    from cephvr.visual_stimulus.rendering.state import InstanceState
    from cephvr.visual_stimulus.rendering.texture_links import bind_texture_links

    geometry, settings = _linked_texture_fixture()
    source = settings[0].model_copy(update={"phase_y": _texture_rate(-0.5)})
    target = settings[2]
    states = {
        s.instance_id: InstanceState.initialize(s, now_ns=0, epoch_start_ns=0)
        for s in (source, target)
    }
    states["left"].values["phase_x"].value = 7
    states["left"].values["rotation"].value = 90
    bind_texture_links(states, geometry, now_ns=0)
    states["left"].advance(2_000_000_000)
    assert states["left"].values["phase_x"].value == pytest.approx(7)
    assert states["left"].values["phase_y"].value == pytest.approx(1.25)
    stopped = source.model_copy(update={"phase_y": Hold(kind="hold")})
    for setting in (stopped, target):
        states[setting.instance_id].transition(
            setting,
            action="continue",
            epoch_start_ns=2_000_000_000,
            now_ns=2_000_000_000,
        )
    bind_texture_links(states, geometry, now_ns=2_000_000_000)
    states["left"].advance(8_000_000_000)
    assert states["left"].values["phase_y"].value == pytest.approx(1.25)
    # Selecting an independent reference does not copy its phase or reset the target.
    independent = target.model_copy(
        update={"linked_to": None, "phase_x": _texture_rate(0.25)}
    )
    states["left"].transition(
        independent,
        action="continue",
        epoch_start_ns=8_000_000_000,
        now_ns=8_000_000_000,
    )
    bind_texture_links(states, geometry, now_ns=8_000_000_000)
    states["left"].advance(10_000_000_000)
    assert states["left"].values["phase_x"].value == pytest.approx(7.5)


def test_compiled_links_execute_real_boundaries_with_retained_orientation():
    from dataclasses import replace

    import pytest
    from tests.visual_stimulus.support import make_compile_context

    from cephvr.visual_stimulus.compiler import compile_trial
    from cephvr.visual_stimulus.config.models.artifact_models import (
        Fingerprint,
        Resource,
        ResourceManifest,
    )
    from cephvr.visual_stimulus.config.models.program_model import Hold
    from cephvr.visual_stimulus.rendering.engine import RendererEngine
    from cephvr.visual_stimulus.rendering.types import (
        DisplayInitialization,
        OutputActivity,
        RenderedOutput,
        RenderPassResult,
    )

    geometry, settings = _linked_texture_fixture()
    source = settings[0].model_copy(update={"phase_y": _texture_rate(-0.5)})
    target = settings[2].model_copy(
        update={
            "initial_phase_x_cycles": 7.0,
            "initial": settings[2].initial.model_copy(update={"rotation_deg": 90.0}),
        }
    )
    data = json.loads(fixture_source())
    data["assets"] = [
        {
            "asset_id": s.instance_id,
            "logical_path": s.instance_id + ".png",
            "profile": "png_uint_v1",
            "color_override": None,
        }
        for s in (source, target)
    ]
    data["instances"] = [
        {"instance_id": s.instance_id, "family": "texture"} for s in (source, target)
    ]
    scene = data["scenes"][0]
    scene["layer_instance_ids"] = [s.instance_id for s in (source, target)]
    data["scenes"] = [scene]
    template = data["sequence"][0]
    data["sequence"] = []
    for index in range(3):
        epoch = deepcopy(template)
        epoch.update(
            epoch_id=f"epoch-{index}",
            scene_id=scene["scene_id"],
            duration={"kind": "fixed", "duration": {"seconds": "20"}},
            settings=[
                (
                    source
                    if index != 1
                    else source.model_copy(update={"phase_y": Hold(kind="hold")})
                ).model_dump(mode="json"),
                target.model_dump(mode="json"),
            ],
        )
        data["sequence"].append(epoch)
    authored = json.dumps(data)
    program = make_program(authored)
    context = make_compile_context(authored)
    # A disabled extra output does not remove geometry or change linked speeds.
    disabled = context.display.outputs[0].model_copy(
        update={"output_id": "off", "device_identity": "edid:off", "enabled": False}
    )
    display = context.display.model_copy(
        update={
            "geometry": geometry,
            "outputs": (*context.display.outputs, disabled),
            "mappings": (
                *context.display.mappings,
                context.display.mappings[0].model_copy(
                    update={"mapping_id": "off-map", "output_id": "off"}
                ),
            ),
        }
    )
    manifest = ResourceManifest(
        format_version=1,
        resources=tuple(
            Resource(
                fingerprint=Fingerprint(
                    resource_id=s.instance_id,
                    logical_path=s.instance_id + ".png",
                    subresource=None,
                    sha256="0" * 64,
                    bytes=1,
                ),
                kind="image",
                profile_id="png_uint_v1",
                dependencies=(),
                interpretation=None,
                cpu_bytes=1,
                gpu_bytes=1,
                provider_compatibility="test-pixels",
            )
            for s in (source, target)
        ),
        provenance=(),
    )
    plan = compile_trial(
        program,
        replace(context, display=display, manifest=manifest),
        max_expanded_epochs=8,
    )
    activity = (OutputActivity("projector/main", 0, 1, 1),)

    class Port:
        def initialize_display(self, selected):
            return DisplayInitialization(
                ("projector/main",),
                (("projector/main", 8, 8, 8),),
                (("projector/main", 100, 100),),
                (("projector/main", 1),),
                activity,
            )

        def prepare_trial(self, artifact, resources):
            pass

        def render(self, scene, states):
            return RenderPassResult(
                (RenderedOutput("projector/main", 100, 100, 8, object()),), (), (), ()
            )

        def present(self, frames):
            return activity

        def show_idle(self, display):
            return activity

    engine = RendererEngine(
        Port(), clock_ns=lambda: 0, resource_provider=lambda _: object()
    )
    engine.initialize_display(display)
    engine.prepare_trial(plan)
    engine.begin_trial(plan.identity.trial_id, 0)
    for seconds, phase_y in (
        (0, 0),
        (10, 6.25),
        (20, 12.5),
        (30, 12.5),
        (40, 12.5),
        (50, 18.75),
    ):
        update = engine.render_tick(seconds * 1_000_000_000)
        values = dict(
            next(s.state for s in update.group.instances if s.instance_id == "left")
        )
        assert values["phase_x"] == pytest.approx(7)
        assert values["phase_y"] == pytest.approx(phase_y)
        assert values["rotation"] == pytest.approx(90)
    engine.stop_trial(60_000_000_000)


def test_linked_spin_pivot_preflight_rejects_unknown_history_until_reset():
    import pytest

    from cephvr.visual_stimulus.compiler.texture_links import validate_link_geometry
    from cephvr.visual_stimulus.config.texture_links import validate_spin_pivot

    geometry, settings = _linked_texture_fixture()
    source, target = settings[0], settings[2]
    spin = source.model_copy(
        update={
            "motion": source.motion.model_copy(update={"rotation": _texture_rate(90)})
        }
    )
    validate_spin_pivot(spin, geometry, (0.0, 0.0))
    for point in (None, (1.0, 0.0)):
        with pytest.raises(ValueError, match="calibrated screen"):
            validate_spin_pivot(spin, geometry, point)
    off_center = geometry.model_copy(update={"observer_mm": (10.0, 0.0, 0.0)})
    validate_spin_pivot(spin, off_center, (0.0, 0.0))
    with pytest.raises(ValueError, match="calibrated screen"):
        validate_spin_pivot(spin, off_center, (10.0, 0.0))
    moved = source.model_copy(
        update={"motion": source.motion.model_copy(update={"x": _texture_rate(1)})}
    )
    epochs = [
        CompiledEpoch(
            occurrence_index=i,
            source_epoch_id=f"epoch-{i}",
            duration_origin="fixed",
            lineage=(),
            scene_id="scene",
            start_ns=i * 10,
            end_ns=(i + 1) * 10,
            truncated_curves=(),
            settings=values,
        )
        for i, values in enumerate(((moved,), (spin, target)))
    ]
    with pytest.raises(ValueError, match="calibrated screen"):
        validate_link_geometry(epochs, compile_boundaries(epochs), geometry)
    epochs[1] = epochs[1].model_copy(
        update={"settings": (spin.model_copy(update={"reset": True}), target)}
    )
    validate_link_geometry(epochs, compile_boundaries(epochs), geometry)


def test_nearly_parallel_linked_spin_has_no_residual_drift():
    import math

    import pytest

    from cephvr.visual_stimulus.config.texture_links import linked_rates

    geometry, settings = _linked_texture_fixture()
    source = settings[0].model_copy(
        update={
            "motion": settings[0].motion.model_copy(
                update={"rotation": _texture_rate(45)}
            )
        }
    )
    epsilon = 1e-6
    c, s = math.cos(epsilon), math.sin(epsilon)
    near_parallel = geometry.surfaces[1].model_copy(
        update={
            "bottom_left_mm": (-100 * c, -100.0, -40 + 100 * s),
            "bottom_right_mm": (100 * c, -100.0, -40 - 100 * s),
            "top_right_mm": (100 * c, 100.0, -40 - 100 * s),
            "top_left_mm": (-100 * c, 100.0, -40 + 100 * s),
        }
    )
    geometry = geometry.model_copy(
        update={
            "surfaces": (geometry.surfaces[0], near_parallel, *geometry.surfaces[2:])
        }
    )
    assert linked_rates(
        source, settings[1], geometry, source_rotation=0, target_rotation=33
    ) == pytest.approx((0, 0, 45), abs=1e-15)


def test_arena_file_geometry_resolves_transforms_and_rejects_invalid_starts():
    from types import SimpleNamespace

    import pytest

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.visual_stimulus.compiler.arena_regions import resolve_arena_regions
    from cephvr.visual_stimulus.config.models.program_model import (
        ArenaBoundary,
        ArenaFileRegion,
        TrialArenaBoundaries,
    )

    setting = add_stimulus(blank_program(), 0, "3D arena", ()).sequence[0].settings[0]
    binding = ArenaBoundary(
        instance_id=setting.instance_id,
        world_frame_id=setting.world_frame_id,
        region=ArenaFileRegion(kind="arena_file", margin_mm=30),
    )
    boundaries = TrialArenaBoundaries(format_version=1, bindings=(binding,))
    geometry = {
        setting.asset_id: json.dumps(
            {"shape": "rectangular", "width": 500, "depth": 400}
        )
    }
    epochs = [SimpleNamespace(settings=(setting,))]
    from cephvr.visual_stimulus.compiler.arena_regions import geometry_vertices

    with patch(
        "cephvr.visual_stimulus.compiler.arena_regions.geometry_vertices",
        wraps=geometry_vertices,
    ) as parse_geometry:
        resolve_arena_regions(boundaries, epochs * 20, geometry)
        assert parse_geometry.call_count == 1
    resolved = resolve_arena_regions(boundaries, epochs, geometry)
    region = resolved.bindings[0].region
    assert region.kind == "convex_polygon_xy" and region.margin_mm == 30
    assert region.vertices_mm == ((-250, -200), (250, -200), (250, 200), (-250, 200))
    assert boundaries.bindings[0].region.kind == "arena_file"
    transform = (
        (-1.0, 0.0, 0.0, 10.0),
        (0.0, 2.0, 0.0, 20.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    moved = setting.model_copy(update={"asset_to_world": transform})
    transformed = resolve_arena_regions(
        boundaries, [SimpleNamespace(settings=(moved,))], geometry
    )
    assert set(transformed.bindings[0].region.vertices_mm) == {
        (-240, -380),
        (260, -380),
        (260, 420),
        (-240, 420),
    }
    for invalid in (
        {},
        {setting.asset_id: '{"shape":"torus"}'},
        {setting.asset_id: '{"shape":"rectangular","width":20,"depth":20}'},
        {setting.asset_id: '{"shape":"rectangular","width":60,"depth":60}'},
        {setting.asset_id: '{"shape":"rectangular","width":-20,"depth":200}'},
    ):
        with pytest.raises((ValueError, KeyError)):
            resolve_arena_regions(boundaries, epochs, invalid)
    outside = setting.model_copy(
        update={
            "initial": setting.initial.model_copy(update={"position_mm": (240.0, 0.0)})
        }
    )
    with pytest.raises(ValueError, match="outside"):
        resolve_arena_regions(
            boundaries, [SimpleNamespace(settings=(outside,))], geometry
        )
    explicit = resolved
    assert resolve_arena_regions(explicit, epochs, {}) == explicit


def test_arena_file_convex_geometry_requires_convex_finite_vertices():
    import pytest

    from cephvr.visual_stimulus.compiler.arena_regions import geometry_vertices

    vertices = [[-100, -100], [100, -100], [0, 100]]
    assert geometry_vertices(
        json.dumps({"shape": "convex_polygon", "vertices_mm": vertices})
    ) == tuple(map(tuple, vertices))
    with pytest.raises(ValueError):
        geometry_vertices(
            json.dumps(
                {
                    "shape": "convex_polygon",
                    "vertices_mm": [[0, 0], [100, 0], [10, 10], [100, 100], [0, 100]],
                }
            )
        )


def test_linked_rotation_depends_on_reference_screen_center_not_observer():
    import math

    import pytest

    from cephvr.visual_stimulus.config.texture_links import (
        linked_rates,
        validate_spin_pivot,
    )
    from cephvr.visual_stimulus.rendering.state import InstanceState
    from cephvr.visual_stimulus.rendering.texture_links import bind_texture_links

    geometry, settings = _linked_texture_fixture()
    source = settings[0].model_copy(
        update={
            "motion": settings[0].motion.model_copy(
                update={"rotation": _texture_rate(90)}
            )
        }
    )
    # Move Bottom's center 10 mm toward Right; the calibrated side planes stay fixed.
    bottom = geometry.surfaces[0]
    shifted = bottom.model_copy(
        update={
            name: (getattr(bottom, name)[0] + 10, *getattr(bottom, name)[1:])
            for name in (
                "bottom_left_mm",
                "bottom_right_mm",
                "top_left_mm",
                "top_right_mm",
            )
        }
    )
    for observer in ((0.0, 0.0, 0.0), (20.0, 15.0, 70.0)):
        rig = geometry.model_copy(
            update={
                "surfaces": (shifted, *geometry.surfaces[1:]),
                "observer_mm": observer,
            }
        )
        validate_spin_pivot(source, rig, (0.0, 0.0))
        for target, radius in ((settings[2], 50), (settings[3], 50)):
            expected = -math.radians(90) * radius / target.pattern.period_x.value
            assert linked_rates(
                source, target, rig, source_rotation=0, target_rotation=0
            ) == pytest.approx((expected, 0, 0))
            states = {
                s.instance_id: InstanceState.initialize(s, now_ns=0, epoch_start_ns=0)
                for s in (source, target)
            }
            bind_texture_links(states, rig, now_ns=0)
            states[target.instance_id].advance(1_000_000_000)
            assert states[target.instance_id].values["phase_x"].value == pytest.approx(
                expected
            )
    # Mapping translation changes the required texture-space pivot, not its rig radius.
    mapping = source.space.mappings[0].model_copy(
        update={"matrix": ((2.0, 0.0, 7.0), (0.0, 2.0, -3.0))}
    )
    mapped = source.model_copy(
        update={"space": source.space.model_copy(update={"mappings": (mapping,)})}
    )
    validate_spin_pivot(mapped, geometry, (7.0, -3.0))
    with pytest.raises(ValueError, match="calibrated screen"):
        validate_spin_pivot(mapped, geometry, (0.0, 0.0))
