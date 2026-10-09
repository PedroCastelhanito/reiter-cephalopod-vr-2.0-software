"""E07/A10 orchestration for edits while the acquisition backend owns devices."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping

from google.protobuf.message import Message

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.device.release_evidence import (
    load_file_policies,
    manual_state_open,
)
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    RETAINED_LIMIT,
    ConfigurationEdit,
    ConfigurationEditTerminal,
    ConfigurationState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.deadlines import remaining_seconds

_EDITABLE_PHASES = (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_READY)


class OwnedCameraEdits:
    """Send a single exact batch and commit only after readback confirmation."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        limits: LimitsState,
        projections: ProjectionStore,
        operations: ControlOperations,
        publisher: SnapshotPublisher,
        backend: BackendPort | None,
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]] | None,
        generation: str,
        clock: Callable[[], int],
        microcontroller_active: Callable[[], bool],
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration = configuration
        self.device = device
        self.limits = limits
        self.projections = projections
        self.operations = operations
        self.publisher = publisher
        self.backend = backend
        self.file_policy_loader = file_policy_loader
        self.generation = generation
        self.clock = clock
        self.microcontroller_active = microcontroller_active

    async def apply(
        self,
        request: svc.UpdateConfigurationRequest,
        *,
        ownership_blocker: Callable[[], str] | None = None,
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        if self.backend is None or self.file_policy_loader is None:
            return self.operations.admission(
                command_id, error="acquisition live-edit endpoint unavailable"
            )
        if self.device.camera_operation is not None or self.microcontroller_active():
            return self.operations.admission(
                command_id,
                error="finish the active camera or Microcontroller operation before editing",
            )
        current_backend = _acquisition_entry(self.configuration.current)
        proposed_backend = _acquisition_entry(request.proposed)
        if current_backend is None or proposed_backend is None:
            return self.operations.admission(
                command_id, error="acquisition configuration is ambiguous"
            )
        current = current_backend.acquisition
        proposed = proposed_backend.acquisition
        owned = _owned_camera_roles(self.projections)
        roles = frozenset(
            role
            for role, name in (
                (camera.CAMERA_ROLE_BEHAVIORAL, "behavioral"),
                (camera.CAMERA_ROLE_TRACKING, "tracking"),
            )
            if role in owned
            and getattr(current, name).device != getattr(proposed, name).device
        )
        pulse_changed = current.pulses != proposed.pulses
        deadline_ns = self.clock() + (
            self.limits.current.setup_ns + self.limits.current.recovery_ns
        )
        try:
            policies = await load_file_policies(
                self.file_policy_loader,
                remaining_seconds(deadline_ns, clock=self.clock),
            )
        except Exception as exc:
            return self.operations.admission(
                command_id, error=f"acquisition file policy unavailable: {exc}"
            )
        async with self.lifecycle.lock:
            if (
                self.operations.authorized(request.command)
                or request.expected_revision != self.configuration.revision
                or self.lifecycle.session.phase not in _EDITABLE_PHASES
                or self.device.configuration_edit is not None
                or self.device.camera_operation is not None
                or self.microcontroller_active()
                or (ownership_blocker is not None and ownership_blocker())
                or _owned_camera_roles(self.projections) != owned
            ):
                return self.operations.admission(
                    command_id,
                    error="configuration edit became stale or ownership changed",
                )
            edit = ConfigurationEdit(
                command=svc.OperatorCommand.FromString(
                    request.command.SerializeToString(deterministic=True)
                ),
                command_id=command_id,
                operation_id=str(uuid.uuid4()),
                revision=request.expected_revision,
                deadline_ns=deadline_ns,
                expected_cameras=roles,
                expect_pulses=pulse_changed,
                proposed=pb.ExperimentConfiguration.FromString(
                    request.proposed.SerializeToString(deterministic=True)
                ),
            )
            self.device.configuration_edit = edit
            self.device.configuration_edit_terminals[edit.operation_id] = (
                ConfigurationEditTerminal(
                    operation_id=edit.operation_id,
                    source=pb.BackendContext.FromString(
                        self.backend.context.SerializeToString(deterministic=True)
                    ),
                    deadline_ns=deadline_ns,
                )
            )
            while len(self.device.configuration_edit_terminals) > RETAINED_LIMIT:
                self.device.configuration_edit_terminals.pop(
                    next(iter(self.device.configuration_edit_terminals))
                )
        acquisition = svc.AcquisitionCameraSettingsCommand(
            configuration_revision=request.expected_revision,
            accepted_base_revision=request.expected_revision,
            file_policies=policies,
        )
        acquisition.accepted_base_settings.CopyFrom(current)
        acquisition.command.command_id = edit.operation_id
        acquisition.command.issuer.CopyFrom(
            pb.ProcessIdentity(role="controller", generation=self.generation)
        )
        acquisition.command.target.CopyFrom(self.backend.context)
        acquisition.command.parent_operation.command_id = command_id
        for role in sorted(roles):
            name = "behavioral" if role == camera.CAMERA_ROLE_BEHAVIORAL else "tracking"
            setting = getattr(proposed, name)
            policy = next(
                (item for item in policies.cameras if item.camera == role), None
            )
            if not setting.HasField("device") or policy is None:
                await self._retire(
                    edit,
                    "camera assignment or policy missing",
                    not_dispatched=True,
                )
                return self.operations.admission(
                    command_id, error="owned camera assignment or policy unavailable"
                )
            item = acquisition.cameras.add(camera=role)
            item.requested.CopyFrom(setting.device)
            item.transport.CopyFrom(policy.transport)
        if pulse_changed:
            pulse = acquisition.pulses
            pulse.requested.CopyFrom(proposed.pulses)
            views = self.projections.devices
            pulse.behavioral_active = bool(
                views is not None
                and views.behavioral.HasField("preview_running")
                and views.behavioral.preview_running
                and proposed.behavioral.device.frame_timing
                == camera.FRAME_TIMING_EXTERNAL_TRIGGER
            )
            pulse.tracking_active = bool(
                views is not None
                and views.tracking.HasField("preview_running")
                and views.tracking.preview_running
                and proposed.tracking.device.frame_timing
                == camera.FRAME_TIMING_EXTERNAL_TRIGGER
            )
        try:
            admission = await asyncio.wait_for(
                self.backend.apply_camera_settings(
                    acquisition, deadline_ns=deadline_ns
                ),
                remaining_seconds(deadline_ns, clock=self.clock),
            )
            if admission.result != pb.COMMAND_RESULT_ACCEPTED:
                if await self._confirmed_commit(edit):
                    return await self._finish_committed(edit)
                detail = (
                    admission.failure.message
                    if admission.HasField("failure")
                    else "backend rejected edit"
                )
                await self._retire(
                    edit,
                    detail,
                    not_dispatched=(
                        admission.result == pb.COMMAND_RESULT_REJECTED
                        and admission.command_id == edit.operation_id
                    ),
                )
                return self.operations.admission(
                    command_id,
                    error=f"acquisition configuration edit failed: {detail}",
                )
            await asyncio.wait_for(
                edit.confirmed.wait(), remaining_seconds(deadline_ns, clock=self.clock)
            )
            if edit.failure:
                if await self._confirmed_commit(edit):
                    return await self._finish_committed(edit)
                raise RuntimeError(edit.failure)
            async with self.lifecycle.lock:
                if (
                    self.device.configuration_edit is not edit
                    or edit.adopted is None
                    or edit.adopted_revision is None
                    or not edit.confirmed.is_set()
                    or edit.failure
                    or self.configuration.revision != edit.adopted_revision
                    or self.configuration.current != edit.adopted
                ):
                    raise RuntimeError(
                        "configuration edit confirmation became stale before completion"
                    )
                self.configuration.retain_validation(list(edit.validation))
                self.projections.set_scope(
                    self.projections.work, self.configuration.revision
                )
                self.device.configuration_edit = None
                self.operations.operation(
                    command_id,
                    "UpdateConfiguration",
                    progress="configuration revision committed after acquisition readback",
                    complete=True,
                    succeeded=True,
                )
                self.publisher.publish()
            return self.operations.admission(command_id)
        except asyncio.CancelledError:
            if await self._confirmed_commit(edit):
                await self._finish_committed(edit)
                raise
            await self._retire(edit, "configuration edit was cancelled")
            raise
        except Exception as exc:
            detail = str(exc) or type(exc).__name__
            if await self._confirmed_commit(edit):
                return await self._finish_committed(edit)
            await self._retire(edit, detail)
            return self.operations.admission(
                command_id, error=f"acquisition configuration edit failed: {detail}"
            )

    async def _confirmed_commit(self, edit: ConfigurationEdit) -> bool:
        async with self.lifecycle.lock:
            return bool(
                self.device.configuration_edit is edit
                and edit.adopted is not None
                and edit.adopted_revision == self.configuration.revision
                and edit.adopted == self.configuration.current
            )

    async def _finish_committed(self, edit: ConfigurationEdit) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            if (
                self.device.configuration_edit is not edit
                or edit.adopted is None
                or edit.adopted_revision != self.configuration.revision
                or edit.adopted != self.configuration.current
            ):
                return self.operations.admission(
                    edit.command_id,
                    error="confirmed configuration edit lost its retained commit",
                )
            self.configuration.retain_validation(list(edit.validation))
            self.projections.set_scope(
                self.projections.work, self.configuration.revision
            )
            self.device.configuration_edit = None
            self.operations.operation(
                edit.command_id,
                "UpdateConfiguration",
                progress="configuration committed; acquisition device operation outcome requires reconciliation",
                complete=True,
                succeeded=True,
            )
            self.publisher.publish()
            return self.operations.admission(edit.command_id)

    async def _retire(
        self,
        edit: ConfigurationEdit,
        failure: str,
        *,
        not_dispatched: bool = False,
    ) -> None:
        async with self.lifecycle.lock:
            if self.device.configuration_edit is edit:
                edit.failure = failure
                edit.confirmed.set()
                self.device.configuration_edit = None
                if not_dispatched:
                    terminal = self.device.configuration_edit_terminals.get(
                        edit.operation_id
                    )
                    if (
                        terminal is not None
                        and terminal.device_status is None
                        and terminal.operation_result is None
                        and edit.report is None
                        and edit.adopted is None
                    ):
                        self.device.configuration_edit_terminals.pop(
                            edit.operation_id, None
                        )


def _acquisition_entry(
    configuration: pb.ExperimentConfiguration,
) -> pb.BackendSettings | None:
    entries = [
        item
        for item in configuration.backends
        if item.backend_name == "acquisition"
        and item.WhichOneof("settings") == "acquisition"
    ]
    return entries[0] if len(entries) == 1 else None


def _owned_camera_roles(projections: ProjectionStore) -> frozenset[int]:
    views = projections.devices
    if views is None or projections.work.WhichOneof("work") is not None:
        return frozenset()
    return frozenset(
        role
        for role, view in (
            (camera.CAMERA_ROLE_BEHAVIORAL, views.behavioral),
            (camera.CAMERA_ROLE_TRACKING, views.tracking),
        )
        if manual_state_open(view)
    )
