"""Setup requests, registration context and worker identity catalogues."""

from __future__ import annotations

import uuid

from cephvr.control.v1 import services_pb2 as svc
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import Attempt, ConfigurationState, SupervisorState


class PreparationContext:
    """Build exact Setup and supervisor registration identities."""

    def __init__(
        self,
        *,
        configuration: ConfigurationState,
        supervisor: SupervisorState,
        generation: str,
        supervisor_generation: str,
    ) -> None:
        self.configuration_state = configuration
        self.supervisor_state = supervisor
        self.generation = generation
        self.supervisor_generation = supervisor_generation

    def setup_request(
        self, attempt: Attempt, backend: BackendPort, operation_id: str
    ) -> svc.SetupSessionRequest:
        request = svc.SetupSessionRequest()
        request.command.command_id = operation_id
        request.command.issuer.role = "controller"
        request.command.issuer.generation = self.generation
        request.command.target.CopyFrom(backend.context)
        request.command.work.session.CopyFrom(attempt.context)
        request.command.parent_operation.command_id = operation_id
        request.plan.CopyFrom(attempt.prepared)
        for setting in attempt.prepared.configuration.backends:
            if setting.backend_name == backend.context.backend_name:
                request.settings.CopyFrom(setting)
                break
        name = backend.context.backend_name
        if name == "acquisition":
            policy = attempt.file_policies.get(name)
            if (
                policy is None
                or policy.DESCRIPTOR != request.acquisition_policies.DESCRIPTOR
            ):
                raise RuntimeError("acquisition file policies unavailable")
            request.acquisition_policies.ParseFromString(policy.SerializeToString())
        elif name == "tracking":
            policy = attempt.file_policies.get(name)
            if (
                policy is None
                or policy.DESCRIPTOR != request.tracking_policies.DESCRIPTOR
            ):
                raise RuntimeError("tracking file policies unavailable")
            request.tracking_policies.ParseFromString(policy.SerializeToString())
        elif name == "vr":
            policy = attempt.file_policies.get(name)
            if policy is None or policy.DESCRIPTOR != request.vr_policies.DESCRIPTOR:
                raise RuntimeError("VR file policies unavailable")
            request.vr_policies.ParseFromString(policy.SerializeToString())
            if attempt.handoff is not None and attempt.handoff.closed_loop:
                tracking = attempt.handoff.tracking
                if tracking is None or not tracking.HasField("feedback"):
                    raise RuntimeError("closed-loop VR feedback descriptor unavailable")
                request.feedback_attachment.CopyFrom(tracking.feedback)
        return request

    def catalogues_match_ready(self, attempt: Attempt) -> bool:
        for name, backend in attempt.required.items():
            health = self.supervisor_state.processes.get(name)
            ready = attempt.ready.get(name)
            if health is None or ready is None or not health.HasField("last_heartbeat"):
                return False
            heartbeat = health.last_heartbeat
            if (
                heartbeat.source.role != name
                or heartbeat.source.generation != backend.context.backend_generation
                or heartbeat.work.WhichOneof("work") != "session"
                or heartbeat.work.session != attempt.context
                or not heartbeat.HasField("cleanup_resources_revision")
                or tuple(
                    item.SerializeToString(deterministic=True)
                    for item in heartbeat.cleanup_resources
                )
                != tuple(
                    item.SerializeToString(deterministic=True)
                    for item in ready.cleanup_resources
                )
            ):
                return False
        return True

    def handoff_command(
        self, attempt: Attempt, name: str, command_id: str
    ) -> svc.BackendCommand:
        request = svc.BackendCommand(command_id=command_id)
        request.issuer.role = "controller"
        request.issuer.generation = self.generation
        request.target.CopyFrom(attempt.required[name].context)
        request.work.session.CopyFrom(attempt.context)
        request.parent_operation.command_id = attempt.setup_operations[name]
        return request

    def registration(
        self, attempt: Attempt, command_id: str
    ) -> svc.RegisterContextRequest:
        request = svc.RegisterContextRequest(command_id=str(uuid.uuid4()))
        request.context.controller.role = "controller"
        request.context.controller.generation = self.generation
        request.context.supervisor.role = "supervisor"
        request.context.supervisor.generation = self.supervisor_generation
        request.context.work.session.CopyFrom(attempt.context)
        request.context.operation.command_id = command_id
        request.context.required_participants.extend(
            backend.context for backend in attempt.required.values()
        )
        request.context.session_directory = str(attempt.reservation.session_directory)
        request.context.paired_spikeglx = attempt.paired
        request.context.outputs.extend(attempt.prepared.outputs)
        request.context.policies.CopyFrom(self.configuration_state.policies)
        worker_owners = self.worker_owners(attempt)
        for name, report in attempt.ready.items():
            owner = attempt.required[name].context
            allowed = {(name, owner.backend_generation)} | worker_owners[name]
            for function in report.prepared_functions:
                if (function.owner.role, function.owner.generation) not in allowed:
                    raise RuntimeError(
                        "Ready prepared function owner differs from registered backend"
                    )
                request.context.prepared_functions.add().CopyFrom(function)
            for resource in report.cleanup_resources:
                if (resource.owner.role, resource.owner.generation) not in allowed:
                    raise RuntimeError(
                        "Ready cleanup resource owner differs from registered backend"
                    )
                request.context.cleanup_resources.add().CopyFrom(resource)
        return request

    def worker_owners(self, attempt: Attempt) -> dict[str, frozenset[tuple[str, str]]]:
        top_level = {
            (name, backend.context.backend_generation): name
            for name, backend in attempt.required.items()
        }
        statuses = {
            (status.process.role, status.process.generation): status
            for status in self.supervisor_state.all_processes
            if status.process.role
            and status.process.generation
            and status.process_running
            and status.connected
        }
        connected = [
            status
            for status in self.supervisor_state.all_processes
            if status.process.role
            and status.process.generation
            and status.process_running
            and status.connected
        ]
        if len(statuses) != len(connected):
            raise RuntimeError(
                "supervisor status repeats an operational process identity"
            )
        result: dict[str, set[tuple[str, str]]] = {
            name: set() for name in attempt.required
        }
        for identity, status in statuses.items():
            if identity in top_level:
                continue
            visited = {identity}
            current = status
            while current.HasField("launch_owner"):
                parent = (current.launch_owner.role, current.launch_owner.generation)
                if parent in visited:
                    raise RuntimeError("supervisor worker ancestry contains a cycle")
                if parent in top_level:
                    result[top_level[parent]].add(identity)
                    break
                visited.add(parent)
                next_status = statuses.get(parent)
                if next_status is None:
                    break
                current = next_status
        return {name: frozenset(workers) for name, workers in result.items()}

    def registered_workers(self, attempt: Attempt) -> frozenset[tuple[str, str]]:
        return frozenset(
            worker
            for workers in self.worker_owners(attempt).values()
            for worker in workers
        )
