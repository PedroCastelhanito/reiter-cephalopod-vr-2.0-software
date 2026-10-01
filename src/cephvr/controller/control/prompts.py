"""Operator responses to Setup, incident, and startup recovery prompts."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from copy import deepcopy
from typing import Any, Literal, cast

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.incident.coordination import IncidentCoordinator
from cephvr.controller.incident.registry import (
    IncidentCapacityError,
    StaleIncidentChoice,
)
from cephvr.controller.lifecycle.interruption import InterruptionWorkflow
from cephvr.controller.state import (
    RETAINED_LIMIT,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.identity import require_uuid4


class OperatorPrompts:
    """Validate one live choice while preserving ownership and prompt revision."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        incidents: IncidentState,
        control: ControlState,
        limit_state: LimitsState,
        control_operations: ControlOperations,
        incident_coordinator: IncidentCoordinator,
        interruption: InterruptionWorkflow,
        publisher: SnapshotPublisher,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.incident_state = incidents
        self.control = control
        self.limit_state = limit_state
        self.control_operations = control_operations
        self.incidents = incident_coordinator
        self.interruption = interruption
        self.publisher = publisher
        self.spawn = spawn

    async def install_startup_recovery(
        self,
        prompt: pb.Prompt | None,
        handler: Callable[[], Awaitable[None]] | None,
        blocker: str | None,
        completion_warning: str | None = None,
        notice: str | None = None,
    ) -> None:
        if (prompt is None) != (handler is None):
            raise ValueError(
                "startup recovery prompt and handler must be installed together"
            )
        if prompt is not None:
            if (
                not blocker
                or set(prompt.permitted_choices) != {"continue", "cancel"}
                or not prompt.HasField("setup")
                or not prompt.HasField("operation")
            ):
                raise ValueError(
                    "startup recovery requires a concrete bounded prompt and blocker"
                )
            for identity in (
                prompt.prompt_id,
                prompt.setup.controller_generation,
                prompt.setup.session_id,
                prompt.operation.command_id,
            ):
                require_uuid4(identity)
        async with self.lifecycle.lock:
            if (
                self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
                or self.lifecycle.startup_recovery_running
            ):
                raise RuntimeError("startup recovery authority unavailable")
            self.lifecycle.startup_prompt = (
                deepcopy(prompt) if prompt is not None else None
            )
            self.lifecycle.startup_recovery_handler = handler
            self.lifecycle.startup_blocker = blocker or ""
            self.lifecycle.startup_warning_id = str(uuid.uuid4()) if blocker else ""
            self.lifecycle.startup_completion_warning = completion_warning
            if notice:
                self.control.add_warning("recovery", notice)
            self.publisher.publish()

    async def respond_to_prompt(
        self, request: svc.PromptResponse
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(request.command)
            startup_prompt = self.lifecycle.startup_prompt
            if (
                startup_prompt is not None
                and request.prompt_id == startup_prompt.prompt_id
            ):
                if (
                    error
                    or self.lifecycle.session.shutdown_requested
                    or self.lifecycle.startup_recovery_running
                    or self.lifecycle.startup_recovery_handler is None
                    or request.setup != startup_prompt.setup
                    or request.setup_operation != startup_prompt.operation
                    or request.HasField("expected_incident_revision")
                    or request.choice not in startup_prompt.permitted_choices
                ):
                    return self.control_operations.admission(
                        command_id,
                        error=error
                        or "startup recovery prompt identity, state or choice mismatch",
                    )
                operation = self.control_operations.operation(
                    command_id,
                    "StartupRecovery",
                    progress="reservation recovery accepted",
                    complete=request.choice == "cancel",
                    succeeded=True if request.choice == "cancel" else None,
                )
                operation.work.session.CopyFrom(startup_prompt.setup)
                if request.choice == "cancel":
                    operation.progress = (
                        "recovery deferred; reservation and blocker preserved"
                    )
                else:
                    self.lifecycle.startup_recovery_running = True
                    self.spawn(
                        self.run_startup_recovery(
                            command_id, self.lifecycle.startup_recovery_handler
                        )
                    )
                self.publisher.publish()
                return self.control_operations.admission(command_id)
            incident_item = self.incident_state.incident_prompts.get(request.prompt_id)
            if incident_item is not None:
                prompt, owner = incident_item
                if (
                    error
                    or owner is not self.lifecycle.attempt
                    or owner.incidents is None
                    or request.setup != owner.context
                    or request.setup_operation != prompt.operation
                    or not request.HasField("expected_incident_revision")
                    or request.choice not in prompt.permitted_choices
                ):
                    return self.control_operations.admission(
                        command_id,
                        error=error
                        or "runtime incident prompt identity or choice mismatch",
                    )
                try:
                    updated = owner.incidents.choose(
                        prompt.runtime_incident.incident_id,
                        request.expected_incident_revision,
                        cast(
                            Literal["continue_session", "abort_session", "acknowledge"],
                            request.choice,
                        ),
                        session_active=self.lifecycle.session.phase
                        in (pb.SESSION_PHASE_STARTING, pb.SESSION_PHASE_RUNNING),
                    )
                except (StaleIncidentChoice, IncidentCapacityError) as exc:
                    return self.control_operations.admission(command_id, error=str(exc))
                self.incident_state.incident_prompts.pop(request.prompt_id, None)
                owner.changed.set()
                self.publisher.publish()
                if owner.writer is not None:
                    self.spawn(
                        self.incidents.log_incident(
                            owner,
                            "incident_decision",
                            {
                                "incident_id": updated.incident_id,
                                "incident_revision": updated.revision,
                                "choice": request.choice,
                                "client_id": request.command.operator.client_id,
                                "affected_resources": list(updated.affected_resources),
                            },
                        )
                    )
                if request.choice == "abort_session":
                    self.spawn(
                        self.interruption.interrupt(
                            owner, f"operator aborted incident {updated.incident_id}"
                        )
                    )
                self.control_operations.operation(
                    command_id,
                    "RespondToPrompt",
                    attempt=owner,
                    progress="runtime incident choice retained",
                    complete=True,
                    succeeded=True,
                )
                self.publisher.publish()
                return self.control_operations.admission(command_id)
            item = self.incident_state.prompts.get(request.prompt_id)
            if error or item is None:
                return self.control_operations.admission(
                    command_id, error=error or "prompt unavailable"
                )
            prompt, future, attempt = item
            if (
                attempt is not self.lifecycle.attempt
                or request.setup != attempt.context
                or request.setup_operation != prompt.operation
                or request.choice not in prompt.permitted_choices
                or future.done()
            ):
                return self.control_operations.admission(
                    command_id, error="prompt choice or Setup identity mismatch"
                )
            future.set_result(request.choice)
            self.control_operations.operation(
                command_id,
                "RespondToPrompt",
                attempt=attempt,
                progress="Setup prompt choice retained",
                complete=True,
                succeeded=True,
            )
            self.publisher.publish()
            return self.control_operations.admission(command_id)

    async def run_startup_recovery(
        self, command_id: str, handler: Callable[[], Awaitable[None]]
    ) -> None:
        error = ""
        try:
            await asyncio.wait_for(
                handler(),
                (
                    self.limit_state.current.setup_cancel_ns
                    + self.limit_state.current.recovery_ns
                )
                / 1e9,
            )
        except Exception as exc:
            error = str(exc)
        async with self.lifecycle.lock:
            self.lifecycle.startup_recovery_running = False
            if (
                self.lifecycle.authority_lost
                or self.lifecycle.session.shutdown_requested
            ):
                error = (
                    error
                    or "controller authority or shutdown changed during startup recovery"
                )
            if error:
                self.control_operations.complete_operation(
                    command_id,
                    success=False,
                    progress="startup recovery remains blocked",
                    error=error,
                )
                self.control.add_warning("startup_recovery", error)
            else:
                self.control_operations.complete_operation(
                    command_id,
                    success=True,
                    progress="startup reservation recovery confirmed",
                )
                self.lifecycle.startup_blocker = ""
                self.lifecycle.startup_prompt = None
                self.lifecycle.startup_recovery_handler = None
                self.lifecycle.startup_warning_id = ""
                if self.lifecycle.startup_completion_warning:
                    self.control.add_warning(
                        "startup_recovery", self.lifecycle.startup_completion_warning
                    )
                self.lifecycle.startup_completion_warning = None
                if self.lifecycle.attempt is None:
                    self.lifecycle.session.cleanup_confirmed = True
            self.control.warnings = self.control.warnings[-RETAINED_LIMIT:]
            self.publisher.publish()
