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
