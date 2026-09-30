"""E05 Setup admission, validation and stable output reservation identity."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import ControllerConfiguration
from cephvr.controller.control.configuration import manual_camera_owned
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.lifecycle.setup_execution import SetupExecution
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.ports import BackendPort, SpikeGLXPort
from cephvr.controller.preparation import PreparationHandoff
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControllerLimits,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
    SupervisorState,
)


@dataclass(frozen=True)
class SetupCandidate:
    settings: ControllerConfiguration | None
    limits: ControllerLimits
    file_policies: dict[str, Message]


_CAMERA_OPEN_MESSAGE = "stop camera preview/editing first"


def _recording_root(value: str) -> Path | str:
    """Return the frozen root, or the Setup rejection reason."""
    if not value.strip() or value != value.strip():
        return "recording root unset or invalid"
    root = Path(value)
    if not root.is_absolute():
        return "recording root must be an absolute path"
    if root.is_symlink() or not root.is_dir():
        return "recording root must be an existing non-symlink directory"
    return root


class SetupAdmission:
    """Accept one validated Setup and allocate its complete session identity."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        control: ControlState,
        device: DeviceState,
        supervisor_state: SupervisorState,
        limit_state: LimitsState,
        backends: Mapping[str, BackendPort],
        spikeglx: SpikeGLXPort | None,
        file_policies: Mapping[str, Message],
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]] | None,
        settings_loader: Callable[[], ControllerConfiguration] | None,
        startup_settings: ControllerConfiguration | None,
        validators: Mapping[
            str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
        ],
        generation: str,
        clock: Callable[[], int],
        max_preparation_bytes: int,
        projections: ProjectionStore,
        publisher: SnapshotPublisher,
        control_operations: ControlOperations,
        setup_execution: SetupExecution,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration_state = configuration
        self.control = control
        self.device_state = device
        self.supervisor_state = supervisor_state
        self.limit_state = limit_state
        self.backends = backends
        self.spikeglx = spikeglx
        self.file_policies = file_policies
        self.file_policy_loader = file_policy_loader
        self.settings_loader = settings_loader
        self.startup_settings = startup_settings
        self.validators = validators
        self.generation = generation
        self.clock = clock
        self.max_preparation_bytes = max_preparation_bytes
        self.projections = projections
        self.publisher = publisher
        self.control_operations = control_operations
        self.setup_execution = setup_execution
        self.spawn = spawn

    def required_backends(self) -> dict[str, BackendPort]:
        configured = {
            setting.backend_name
            for setting in self.configuration_state.current.backends
            if setting.enabled
        }
        if "vr" not in configured:
            raise ValueError("VR participant is required in both modes")
        local = configured - {"synchronization"}
        if (
            self.configuration_state.current.mode == pb.SESSION_MODE_CLOSED_LOOP
            and "tracking" not in local
        ):
            raise ValueError("closed-loop VR requires tracking feedback")
        if "tracking" in local and "acquisition" not in local:
            raise ValueError("tracking requires acquisition camera input")
        missing = local - self.backends.keys()
        if missing:
            raise ValueError(
                f"required backend is not registered: {', '.join(sorted(missing))}"
            )
        for name in local:
            status = self.supervisor_state.processes.get(name)
            backend = self.backends[name]
            if (
                status is None
                or status.process.generation != backend.context.backend_generation
                or not status.process_running
                or not status.connected
            ):
                raise ValueError(f"required backend is not operational: {name}")
        if "synchronization" in configured and self.spikeglx is None:
            raise ValueError("paired SpikeGLX adapter is unavailable")
        return {name: self.backends[name] for name in local}

    async def setup(self, command: svc.OperatorCommand) -> pb.CommandAdmission:
        command_id = command.operator.command_id
        if not self.validators:
            return self.control_operations.admission(
                command_id, error="configuration validators unavailable"
            )
        async with self.lifecycle.lock:
            if self.lifecycle.startup_blocker:
                return self.control_operations.admission(
                    command_id, error=self.lifecycle.startup_blocker
                )
            if self.lifecycle.manual_control_cleanup_pending:
                return self.control_operations.admission(
                    command_id, error="manual camera cleanup is still reconciling"
                )
            if manual_camera_owned(self.projections, self.device_state):
                return self.control_operations.admission(
                    command_id, error=_CAMERA_OPEN_MESSAGE
                )
            proposal = deepcopy(self.configuration_state.current)
            expected_revision = self.configuration_state.revision
        candidate = await self._load_candidate(command_id, proposal)
        if isinstance(candidate, pb.CommandAdmission):
            return candidate
        return await self._commit_setup(command, expected_revision, candidate)

    async def _load_candidate(
        self, command_id: str, proposal: pb.ExperimentConfiguration
    ) -> SetupCandidate | pb.CommandAdmission:
        active_names = frozenset(
            item.backend_name for item in proposal.backends if item.enabled
        )
        loaded_settings: ControllerConfiguration | None = None
        candidate_limits = self.limit_state.current
        if self.settings_loader is not None:
            try:
                loaded_settings = await asyncio.wait_for(
                    asyncio.to_thread(self.settings_loader),
                    self.limit_state.current.validation_ns / 1e9,
                )
                baseline = self.startup_settings
                assert baseline is not None
                if (
                    loaded_settings.controller_port != baseline.controller_port
                    or loaded_settings.supervisor_startup != baseline.supervisor_startup
                    or loaded_settings.max_message_bytes != baseline.max_message_bytes
                    or loaded_settings.max_pending_events != baseline.max_pending_events
                    or loaded_settings.max_pending_payload_bytes
                    != baseline.max_pending_payload_bytes
                    or loaded_settings.max_retained_incidents
                    != baseline.max_retained_incidents
                    or loaded_settings.limits_kwargs["max_metadata_operations"]
                    != baseline.limits_kwargs["max_metadata_operations"]
                    or loaded_settings.limits_kwargs["max_metadata_bytes"]
                    != baseline.limits_kwargs["max_metadata_bytes"]
                ):
                    return self.control_operations.admission(
                        command_id,
                        error="startup-only controller settings changed; restart required",
                    )
                candidate_limits = ControllerLimits(**loaded_settings.limits_kwargs)
            except Exception as exc:
                return self.control_operations.admission(
                    command_id, error=f"controller settings unavailable: {exc}"
                )
        try:
            validation = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, proposal)
                        for validator in self.validators.values()
                    )
                ),
                self.limit_state.current.validation_ns / 1e9,
            )
        except Exception as exc:
            return self.control_operations.admission(
                command_id, error=f"configuration validation unavailable: {exc}"
            )
        if any(not result.completed or not result.valid for result in validation):
            reason = next(
                (
                    result.unavailable_reason.message
                    for result in validation
                    if not result.completed and result.unavailable_reason.message
                ),
                "configuration invalid",
            )
            return self.control_operations.admission(command_id, error=reason)
        try:
            file_policies = (
                dict(
                    await asyncio.wait_for(
                        asyncio.to_thread(self.file_policy_loader, active_names),
                        self.limit_state.current.validation_ns / 1e9,
                    )
                )
                if self.file_policy_loader is not None
                else dict(self.file_policies)
            )
        except Exception as exc:
            return self.control_operations.admission(
                command_id, error=f"backend file policies unavailable: {exc}"
            )
        return SetupCandidate(loaded_settings, candidate_limits, file_policies)

    async def _commit_setup(
        self,
        command: svc.OperatorCommand,
        expected_revision: int,
        candidate: SetupCandidate,
    ) -> pb.CommandAdmission:
        command_id = command.operator.command_id
        loaded_settings = candidate.settings
        candidate_limits = candidate.limits
        file_policies = candidate.file_policies
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(command)
            if (
                error
                or self.lifecycle.startup_blocker
                or self.lifecycle.manual_control_cleanup_pending
                or self.configuration_state.revision != expected_revision
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                or not self.lifecycle.session.cleanup_confirmed
                and self.lifecycle.attempt is not None
            ):
                return self.control_operations.admission(
                    command_id,
                    error=error
                    or self.lifecycle.startup_blocker
                    or "Setup unavailable in current phase or blocked cleanup",
                )
            if manual_camera_owned(self.projections, self.device_state):
                return self.control_operations.admission(
                    command_id, error=_CAMERA_OPEN_MESSAGE
                )
            if (
                not self.configuration_state.current.HasField("mode")
                or self.configuration_state.current.mode == pb.SESSION_MODE_UNSPECIFIED
                or not self.configuration_state.current.trials
            ):
                return self.control_operations.admission(
                    command_id, error="explicit mode and trial protocol required"
                )
            try:
                required = self.required_backends()
            except ValueError as exc:
                return self.control_operations.admission(command_id, error=str(exc))
            recording_root = _recording_root(
                self.configuration_state.current.recording_root
            )
            if isinstance(recording_root, str):
                return self.control_operations.admission(
                    command_id, error=recording_root
                )
            now = self.clock()
            try:
                from tzlocal import get_localzone_name

                zone_name = get_localzone_name()
                anchor = datetime.now(ZoneInfo(zone_name))
            except (ImportError, KeyError, ValueError) as exc:
                return self.control_operations.admission(
                    command_id, error=f"IANA local timezone unavailable: {exc}"
                )
            context = pb.SessionContext(
                controller_generation=self.generation, session_id=str(uuid.uuid4())
            )
            prepared = pb.PreparedSession(
                context=context,
                configuration_revision=self.configuration_state.revision,
                configuration=self.configuration_state.current,
                policies=loaded_settings.policies
                if loaded_settings is not None
                else self.configuration_state.policies,
                anchor_monotonic_ns=now,
                anchor_wall_time=anchor.isoformat(),
                local_timezone=zone_name,
            )
            for index, definition in enumerate(
                self.configuration_state.current.trials, 1
            ):
                if definition.trial_number != index:
                    return self.control_operations.admission(
                        command_id, error="trial numbers must be ordered and one-based"
                    )
                trial_context = pb.TrialContext(
                    session=context, trial_id=str(uuid.uuid4()), trial_number=index
                )
                prepared.trials.add(context=trial_context, definition=definition)
            reservation = OutputReservation(
                recording_root,
                self.configuration_state.current.experiment,
                self.configuration_state.current.subject,
                context.session_id,
                self.generation,
                anchor,
            )
            prepared.session_directory = str(reservation.session_directory)
            attempt = Attempt(context, prepared, reservation, required, {})
            attempt.setup_command_id = command_id
            attempt.file_policies = file_policies
            if "tracking" in required:
                tracking_settings = next(
                    (
                        setting.tracking
                        for setting in self.configuration_state.current.backends
                        if setting.backend_name == "tracking" and setting.enabled
                    ),
                    None,
                )
                if tracking_settings is None or not tracking_settings.HasField(
                    "input_camera_role"
                ):
                    return self.control_operations.admission(
                        command_id, error="tracking input camera role unresolved"
                    )
                attempt.setup_operations.update(
                    {name: str(uuid.uuid4()) for name in required}
                )
                attempt.handoff = PreparationHandoff(
                    context,
                    self.configuration_state.revision,
                    {name: backend.context for name, backend in required.items()},
                    attempt.setup_operations,
                    camera=tracking_settings.input_camera_role,
                    closed_loop=self.configuration_state.current.mode
                    == pb.SESSION_MODE_CLOSED_LOOP,
                    max_payload_bytes=self.max_preparation_bytes,
                )
            # Applied only once every rejection check above has passed.
            if loaded_settings is not None:
                self.configuration_state.policies.CopyFrom(loaded_settings.policies)
                self.limit_state.current = candidate_limits
            attempt.setup_deadline_ns = now + self.limit_state.current.setup_ns
            attempt.paired = any(
                setting.backend_name == "synchronization" and setting.enabled
                for setting in self.configuration_state.current.backends
            )
            self.lifecycle.attempt = attempt
            self.lifecycle.session = pb.SessionState(
                phase=pb.SESSION_PHASE_SETTING_UP,
                context=context,
                directory=str(reservation.session_directory),
                trial_count=len(prepared.trials),
            )
            self.lifecycle.trial = pb.TrialState(phase=pb.TRIAL_PHASE_PENDING)
            self.projections.set_scope(
                pb.WorkContext(session=context), self.configuration_state.revision
            )
            self.control.operations[command_id] = pb.OperationState(
                context=pb.OperationContext(command_id=command_id),
                command="Setup",
                work=pb.WorkContext(session=context),
                progress="reserving output namespace",
            )
            self.publisher.publish()
            self.spawn(
                self.setup_execution.run_setup(
                    attempt, command_id, attempt.setup_deadline_ns
                )
            )
            return self.control_operations.admission(command_id)
