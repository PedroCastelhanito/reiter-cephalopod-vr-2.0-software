"""Exact prepared output and cleanup declarations shared by Visual Stimulus lifecycle owners."""

from __future__ import annotations

from cephvr.control.v1 import types_pb2 as pb


def output_plans(
    backend: pb.BackendContext, trials: list[pb.TrialPlan], saving: bool
) -> tuple[pb.OutputPlan, ...]:
    tags: tuple[tuple[str, str], ...] = (("stimulus_LOG", "json"),)
    if saving:
        tags += (("stimulus_frames", "jsonl"), ("stimulus", "mp4"))
    return tuple(
        pb.OutputPlan(
            backend=backend,
            trial=trial.context,
            output_key=f"{trial.context.trial_id}:visual_stimulus:{tag}",
            output_tag=tag,
            extension=extension,
        )
        for trial in trials
        for tag, extension in tags
    )


def function_scopes(
    owner: pb.ProcessIdentity,
    worker: pb.ProcessIdentity,
    outputs: tuple[pb.OutputPlan, ...],
) -> tuple[pb.PreparedFunctionScope, ...]:
    keys = [output.output_key for output in outputs]
    renderer = pb.PreparedFunctionScope(
        resource_id="visual_stimulus:renderer",
        owner=owner,
        essential_to_stimulus_control=True,
        feedback_hold_required_on_loss=False,
        bounded_uncertainty_supported=False,
        lifecycle_sources=["renderer"],
        authorized_reporters=[worker],
        affected_closure_resource_ids=["visual_stimulus:renderer", *keys],
    )
    return (
        renderer,
        *(
            pb.PreparedFunctionScope(
                resource_id=output.output_key,
                owner=owner,
                essential_to_stimulus_control=False,
                feedback_hold_required_on_loss=False,
                bounded_uncertainty_supported=False,
                affected_closure_resource_ids=[output.output_key],
                authorized_reporters=[
                    owner if output.output_tag == "stimulus_LOG" else worker
                ],
            )
            for output in outputs
        ),
    )
