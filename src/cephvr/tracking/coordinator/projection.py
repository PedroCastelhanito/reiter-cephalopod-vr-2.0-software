"""Current and retained administrative views; protected descriptors stay private."""

from __future__ import annotations

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.commands import CommandLedger
from cephvr.tracking.v1 import preparation_pb2
from cephvr.tracking.v1 import services_pb2 as tracking

from .state import Identity, State


def project(
    identity: Identity,
    state: State,
    ledger: CommandLedger,
    method: str,
    request: Message,
) -> Message:
    if isinstance(request, tracking.TrackingPreparationQuery):
        command = request.command
        if (
            command.target != identity.backend
            or state.setup is None
            or command.work != state.setup.command.work
        ):
            raise ValueError("preparation query scope mismatch")
        return preparation_pb2.TrackingPreparationState.FromString(
            state.preparation.SerializeToString()
        )
    if isinstance(request, wire.BackendQuery):
        if request.target != identity.backend:
            raise ValueError("state query targets another generation")
        result = pb.ParticipantState(
            process=identity.process,
            enabled=True,
            required=True,
            process_running=True,
            connected=True,
            health="failed" if state.error else "responsive",
            session_phase=state.session_phase,
            trial_phase=state.trial_phase,
            outputs=state.outputs,
            configuration_module_version="tracking-config-v1",
            software_version="2.0.0.dev0",
            capabilities=["tracking"],
            protocol_package="cephvr.control.v1",
        )
        if state.ready is not None:
            result.ready.CopyFrom(
                pb.ReadinessState(
                    context=state.ready.context,
                    configuration_revision=state.ready.configuration_revision,
                    required_checks_passed=state.ready.required_checks_passed,
                )
            )
        for name in ("started", "stopped", "finished", "cleanup"):
            value = getattr(state, name)
            if value is not None:
                getattr(result, name).CopyFrom(value)
        if state.error is not None:
            result.errors.append(state.error)
        result.outstanding_obligations.extend(
            item.resource
            for item in state.resources
            if state.cleanup is None
            or not any(
                x.resource == item.resource and x.released
                for x in state.cleanup.resources
            )
        )
        return result
    if isinstance(request, wire.RetainedResultQuery):
        if request.query.target != identity.backend:
            raise ValueError("retained query targets another generation")
        record = ledger.get(request.command_id)
        retained = wire.RetainedResult(
            found=record is not None, backend=identity.backend, work=request.query.work
        )
        if record is None:
            return retained
        scope = (
            request.query.work.trial.trial_id
            if request.query.work.HasField("trial")
            else request.query.work.session.session_id
        )
        if record.work_key != scope:
            raise ValueError("retained command belongs to another work scope")
        if record.result is not None:
            retained.admission.ParseFromString(record.result)
        if record.executor_result is not None:
            retained.operation.ParseFromString(record.executor_result)
        for name in ("ready", "started", "stopped", "finished"):
            saved = state.retained.get(f"tracking:{request.command_id}:{name}")
            value = None if saved is None else getattr(saved, name)
            if (
                value is not None
                and value.context.operation.command_id == request.command_id
                and value.context.work == request.query.work
            ):
                getattr(retained, name).CopyFrom(value)
        if (
            state.preparation_report is not None
            and state.preparation_report.source.operation.command_id
            == request.command_id
            and state.preparation_report.source.work == request.query.work
        ):
            retained.data_preparation.CopyFrom(state.preparation_report)
        if retained.HasField("finished"):
            retained.outputs.extend(retained.finished.outputs)
        return retained
    raise ValueError("unsupported Tracking query")
