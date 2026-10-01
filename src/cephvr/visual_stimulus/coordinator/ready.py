"""Validate worker summaries against the coordinator's canonical Setup artifacts."""

from collections.abc import Mapping

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb

from .state import Prepared


def validate_ready(
    payload: pb.ReadyReport,
    work: pb.WorkContext,
    setup: wire.SetupSessionRequest,
    prepared: Mapping[str, Prepared],
) -> None:
    expected_ids = (
        {trial.context.trial_id for trial in setup.plan.trials}
        if work.WhichOneof("work") == "session"
        else {work.trial.trial_id}
    )
    reported_ids = [trial.context.trial_id for trial in payload.resolved_trials]
    if set(reported_ids) != expected_ids or len(reported_ids) != len(expected_ids):
        raise ValueError("Ready omitted, duplicated or changed the prepared trial set")
    for trial in payload.resolved_trials:
        original = next(
            (
                item
                for item in setup.plan.trials
                if item.context.trial_id == trial.context.trial_id
            ),
            None,
        )
        if original is None:
            raise ValueError("Ready refers to an unknown trial")
        preserved = pb.TrialPlan.FromString(trial.SerializeToString())
        expected = pb.TrialPlan.FromString(original.SerializeToString())
        for field in ("resolved_duration_ns", "resolved_stimulus"):
            preserved.ClearField(field)
            expected.ClearField(field)
        if preserved != expected:
            raise ValueError("Ready changed controller-owned trial inputs")
        artifact = prepared.get(trial.context.trial_id)
        if artifact is None or artifact.handle != trial.resolved_stimulus.prepared:
            raise ValueError("Ready lacks matching retained artifact")
        plan = artifact.plan
        occurrences = trial.resolved_stimulus.occurrences
        if (
            trial.context != artifact.trial
            or trial.resolved_duration_ns != plan.resolved_duration_ns
            or trial.resolved_stimulus.seed_decimal != plan.seed_decimal
            or len(occurrences) != len(plan.epochs)
        ):
            raise ValueError("Ready summary differs from canonical preparation")
        for occurrence, epoch in zip(occurrences, plan.epochs, strict=True):
            if (
                occurrence.index,
                occurrence.epoch_id,
                occurrence.scene_id,
                occurrence.start_offset_ns,
                occurrence.duration_ns,
            ) != (
                epoch.occurrence_index,
                epoch.source_epoch_id,
                epoch.scene_id,
                epoch.start_ns,
                epoch.end_ns - epoch.start_ns,
            ):
                raise ValueError("Ready occurrence differs from prepared schedule")
            if [
                (
                    visit.group_id,
                    visit.repetition_index,
                    visit.unit_id,
                    visit.visit_index,
                )
                for visit in occurrence.lineage
            ] != [
                (
                    visit.group_id,
                    visit.repetition_index,
                    visit.unit_id,
                    visit.visit_index,
                )
                for visit in epoch.lineage
            ]:
                raise ValueError("Ready lineage differs from prepared schedule")
