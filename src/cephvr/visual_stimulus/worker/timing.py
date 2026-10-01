"""Compact per-output software timing evidence, retained with saving disabled."""

from dataclasses import dataclass, field

from cephvr.visual_stimulus.rendering.types import DiagnosticSnapshot, RenderUpdate
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp


@dataclass
class OutputTiming:
    attempts: int = 0
    returned: int = 0
    failed: int = 0
    unknown: int = 0
    submitted_epochs: set[int] = field(default_factory=set)
    starvation_intervals: int = 0
    starving_instances: set[str] = field(default_factory=set)
    diagnostics_count: int = 0
    clipping_counts: dict[str, int] = field(default_factory=dict)

    def diagnostic(self, record: DiagnosticSnapshot) -> None:
        if record.group_id != self.diagnostics_count:
            raise RuntimeError("output clipping diagnostics have a gap or duplicate")
        if len(set(record.stages)) != len(record.stages) or not set(record.stages) <= {
            "alpha",
            "linear_output",
            "device_code",
        }:
            raise ValueError("unknown or repeated output clipping stage")
        self.diagnostics_count += 1
        for stage in record.stages:
            self.clipping_counts[stage] = self.clipping_counts.get(stage, 0) + 1

    def observe(self, output_id: str, update: RenderUpdate) -> None:
        for submission in update.evidence_submissions:
            if submission.output_id != output_id or submission.attempt_index is None:
                continue
            self.attempts += 1
            self.submitted_epochs.add(update.group.epoch_index)
            if submission.phase == "returned":
                self.returned += 1
            elif submission.phase == "failed":
                self.failed += 1
            else:
                self.unknown += 1
        starving = {
            selection.instance_id
            for selection in update.evidence_state.media
            if selection.disposition == "starvation_hold"
        }
        self.starvation_intervals += len(starving - self.starving_instances)
        self.starving_instances = starving

    def report(
        self, trial_id: str, output_id: str, groups: int, elapsed_epochs: set[int]
    ) -> vp.TrialTimingSummary:
        return vp.TrialTimingSummary(
            trial_id=trial_id,
            output_id=output_id,
            render_groups=groups,
            submission_attempts=self.attempts,
            returned_submissions=self.returned,
            failed_submissions=self.failed,
            unknown_submissions=self.unknown,
            epochs_without_submission=len(elapsed_epochs - self.submitted_epochs),
            video_starvation_intervals=self.starvation_intervals,
            alpha_clipped_groups=self.clipping_counts.get("alpha", 0),
            linear_output_clipped_groups=self.clipping_counts.get("linear_output", 0),
            device_code_clipped_groups=self.clipping_counts.get("device_code", 0),
        )
