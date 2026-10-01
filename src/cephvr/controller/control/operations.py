"""Retained command outcomes and E02 control-lease admission."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.receipts import rejected_admission
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControlState,
    LifecycleState,
)


class ControlOperations:
    """Operate on the controller's authoritative lease and outcome records."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        control: ControlState,
        generation: str,
        max_operation_records: int,
        clock: Callable[[], int],
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration_state = configuration
        self.control = control
        self.generation = generation
        self.max_operation_records = max_operation_records
        self.clock = clock

    def operation(
        self,
        command_id: str,
        name: str,
        *,
        attempt: Attempt | None = None,
        progress: str = "accepted",
        complete: bool = False,
        succeeded: bool | None = None,
        safety: Literal["ordinary", "abort", "shutdown"] = "ordinary",
    ) -> pb.OperationState:
        self.prune_operations()
        reserved = 2 if safety == "ordinary" else 1 if safety == "abort" else 0
        if len(self.control.operations) >= self.max_operation_records - reserved:
            raise RuntimeError("retained operation capacity exhausted")
        if command_id in self.control.operations:
            raise RuntimeError("operator operation ID was already retained")
        operation = pb.OperationState(
            context=pb.OperationContext(command_id=command_id),
            command=name,
            progress=progress,
            complete=complete,
        )
        if attempt is not None:
            operation.work.session.CopyFrom(attempt.context)
        if succeeded is not None:
            operation.succeeded = succeeded
        self.control.operations[command_id] = operation
        if complete:
            self.control.operation_finished_ns[command_id] = self.clock()
        return operation

    def complete_operation(
        self, command_id: str, *, success: bool, progress: str, error: str = ""
    ) -> None:
        operation = self.control.operations.get(command_id)
        if operation is None or operation.complete:
            return
        operation.complete = True
        self.control.operation_finished_ns[command_id] = self.clock()
        operation.succeeded = success
        operation.progress = progress
        if error:
            operation.failure.CopyFrom(
                pb.Failure(code="OPERATION_FAILED", message=error)
            )

    def prune_operations(self) -> None:
        now = self.clock()
        retention = (
            self.configuration_state.policies.command_retention_after_finalization_ns
        )
        if retention <= 0:
            return
        active_session = (
            self.lifecycle.attempt.context.session_id
            if self.lifecycle.attempt is not None
            and not self.lifecycle.session.cleanup_confirmed
            else None
        )
        for command_id, finished_ns in tuple(
            self.control.operation_finished_ns.items()
        ):
            operation = self.control.operations.get(command_id)
            if operation is None:
                self.control.operation_finished_ns.pop(command_id, None)
            elif now - finished_ns >= retention and (
                operation.work.WhichOneof("work") != "session"
                or operation.work.session.session_id != active_session
            ):
                self.control.operations.pop(command_id, None)
                self.control.operation_finished_ns.pop(command_id, None)

    def admission(
        self, command_id: str, *, error: str = "", code: str = "REJECTED"
    ) -> pb.CommandAdmission:
        if error:
            return rejected_admission(command_id, code, error)
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=command_id
        )

    def authorized(
        self,
        command: svc.OperatorCommand,
        *,
        safety: Literal["ordinary", "abort", "shutdown"] = "ordinary",
        targets_work: bool = False,
    ) -> str:
        """Check the lease; work-targeting commands must also name the live work.

        Safety commands always target work, but only by session so that a trial
        transition can never block them.
        """
        if self.lifecycle.authority_lost:
            return "controller authority permanently lost"
        self.prune_operations()
        reserved = 2 if safety == "ordinary" else 1 if safety == "abort" else 0
        if len(self.control.operations) >= self.max_operation_records - reserved:
            return "retained operation capacity exhausted"
        if (
            command.controller_generation != self.generation
            or self.control.owner is None
        ):
            return "controller generation or control lease mismatch"
        if (command.operator.client_id, command.operator.control_generation) != (
            self.control.owner[0],
            self.control.owner[2],
        ):
            return "control lease mismatch"
        if (self.control.owner[0], self.control.owner[1]) not in self.control.watches:
            return "control subscription closed"
        attempt = self.lifecycle.attempt
        if attempt is not None and (targets_work or safety != "ordinary"):
            if not command.HasField("expected_work"):
                return "expected work is required"
            if not self._work_matches(command.expected_work, attempt, safety):
                return "work identity mismatch"
        return ""

    def _work_matches(
        self, work: pb.WorkContext, attempt: Attempt, safety: str
    ) -> bool:
        kind = work.WhichOneof("work")
        if kind == "session":
            return work.session == attempt.context
        if kind != "trial" or work.trial.session != attempt.context:
            return False
        if safety != "ordinary":
            return True
        trial = self.lifecycle.trial
        return (
            trial.HasField("context")
            and work.trial.trial_id == trial.context.trial_id
            and work.trial.trial_number == trial.context.trial_number
        )
