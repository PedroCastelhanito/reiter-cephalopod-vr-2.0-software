"""E04 output identities follow resolved Ready settings and exact writer schemas."""

from __future__ import annotations

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.planning import (
    PlanningError,
    WriterSchema,
    build_schema,
    plan_outputs,
)
from tests.controller.support_components import _id


def _prepared_and_ready(
    *, save_visual_stimulus_data: bool
) -> tuple[pb.PreparedSession, dict[str, pb.ReadyReport]]:
    session = pb.SessionContext(controller_generation=_id(), session_id=_id())
    trial = pb.TrialContext(session=session, trial_id=_id(), trial_number=1)
    prepared = pb.PreparedSession(context=session, configuration_revision=3)
    prepared.configuration.backends.add(backend_name="visual_stimulus", enabled=True)
    prepared.trials.add(context=trial, resolved_duration_ns=60_000_000_000)
    report = pb.ReadyReport(
        context=pb.ReportContext(
            backend=pb.BackendContext(
                backend_name="visual_stimulus", backend_generation=_id()
            ),
            work=pb.WorkContext(session=session),
            operation=pb.OperationContext(command_id=_id()),
        ),
        configuration_revision=3,
        required_checks_passed=True,
        resolved_settings=pb.BackendSettings(
            backend_name="visual_stimulus",
            enabled=True,
            visual_stimulus=pb.VisualStimulusSettings(
                save_visual_stimulus_data=save_visual_stimulus_data
            ),
        ),
    )
    return prepared, {"visual_stimulus": report}


def test_planner_preserves_visual_stimulus_save_switch_and_reserves_no_path() -> None:
    prepared, ready = _prepared_and_ready(save_visual_stimulus_data=False)
    outputs = plan_outputs(prepared, ready)
    assert [(x.output_tag, x.extension) for x in outputs] == [("stimulus_LOG", "json")]
    assert not outputs[0].HasField("path")
    assert outputs[0].trial == prepared.trials[0].context
    prepared, ready = _prepared_and_ready(save_visual_stimulus_data=True)
    outputs = plan_outputs(prepared, ready)
    assert [(x.output_tag, x.extension) for x in outputs] == [
        ("stimulus_LOG", "json"),
        ("stimulus_frames", "jsonl"),
        ("stimulus", "mp4"),
    ]


def test_planner_requires_exact_ready_and_resolved_switch() -> None:
    prepared, ready = _prepared_and_ready(save_visual_stimulus_data=False)
    with pytest.raises(PlanningError, match="exact enabled backend Ready"):
        plan_outputs(prepared, {})
    ready["visual_stimulus"].resolved_settings.visual_stimulus.ClearField(
        "save_visual_stimulus_data"
    )
    with pytest.raises(PlanningError, match="resolved save_visual_stimulus_data"):
        plan_outputs(prepared, ready)


def test_schema_requires_actual_writer_definition_for_each_reserved_output() -> None:
    prepared, ready = _prepared_and_ready(save_visual_stimulus_data=False)
    prepared.outputs.extend(plan_outputs(prepared, ready))
    with pytest.raises(PlanningError, match="writer schema unavailable"):
        build_schema(prepared)
    schema = build_schema(
        prepared,
        {
            ("visual_stimulus", "stimulus_LOG", "json"): WriterSchema(
                schema_version=1,
                format="json",
                fields={"schema_version": "integer", "trial_id": "uuid"},
                units={"schema_version": "count"},
                clocks={"host": "cephvr.host.perf_counter_ns.v1"},
            )
        },
    )
    assert schema["schema_version"] == 1
    assert len(schema["outputs"]) == 1
