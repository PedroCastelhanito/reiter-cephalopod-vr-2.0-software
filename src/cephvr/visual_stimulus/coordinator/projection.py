"""Read-only current and retained coordinator state projections."""

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.commands import CommandLedger

from .state import Identity, State


def project(
    identity: Identity, state: State, ledger: CommandLedger, request: Message
) -> Message:
    query = request.query if isinstance(request, wire.RetainedResultQuery) else request
    if not isinstance(query, wire.BackendQuery) or query.target != identity.backend:
        raise ValueError("wrong Visual Stimulus query target")
    if isinstance(request, wire.RetainedResultQuery):
        record = ledger.get(request.command_id)
        result = wire.RetainedResult(
            found=record is not None, backend=identity.backend, work=query.work
        )
        if record is not None:
            if record.result:
                result.admission.ParseFromString(record.result)
            if record.executor_result:
                result.operation.ParseFromString(record.executor_result)
            for (kind, command_id), report in state.reports.items():
                if command_id == request.command_id and kind in {
                    "ready",
                    "started",
                    "stopped",
                    "finished",
                }:
                    getattr(result, kind).CopyFrom(getattr(report, kind))
        return result
    participant = pb.ParticipantState(
        process=identity.process,
        enabled=True,
        required=True,
        process_running=True,
        connected=True,
        software_version="2.0.0.dev0",
        configuration_module_version="visual-stimulus-config-v2",
        protocol_package="cephvr.control.v1",
        health="interrupted" if state.interrupted else "available",
    )
    for (kind, _), report in state.reports.items():
        payload = getattr(report, kind)
        work = payload.work if kind == "cleanup" else payload.context.work
        requested = query.work
        if requested.WhichOneof("work") is not None:
            if requested.WhichOneof("work") == "trial":
                if work != requested:
                    continue
            else:
                session = work.trial.session if work.HasField("trial") else work.session
                if session != requested.session:
                    continue
        elif state.setup is not None:
            session = work.trial.session if work.HasField("trial") else work.session
            if session != state.setup.plan.context:
                continue
        if kind == "ready":
            participant.ready.CopyFrom(
                pb.ReadinessState(
                    context=report.ready.context,
                    configuration_revision=report.ready.configuration_revision,
                    required_checks_passed=report.ready.required_checks_passed,
                )
            )
        elif kind in {"started", "stopped", "finished", "cleanup"}:
            getattr(participant, kind).CopyFrom(getattr(report, kind))
    return participant
