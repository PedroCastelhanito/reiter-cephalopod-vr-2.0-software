"""E07 effective configuration edits and reusable history persistence."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable, Coroutine, Mapping
from pathlib import Path
from typing import Any

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.device.release_evidence import manual_state_open
from cephvr.controller.lifecycle.cleanup import CleanupWorkflow
from cephvr.controller.metadata.documents import message_dict
from cephvr.controller.metadata.files import atomic_json as _atomic_json
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.state import (
    ConfigurationState,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
)
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb

_EDITABLE_PHASES = (
    pb.SESSION_PHASE_CONFIGURATION,
    pb.SESSION_PHASE_READY,
)


def manual_camera_owned(projections: ProjectionStore, device: DeviceState) -> bool:
    """True while a camera operation, editing owner or manual preview is open."""
    if device.camera_operation is not None:
        return True
    views = projections.devices
    return views is not None and (
        views.diagnostic.active
        or any(
            manual_state_open(camera) for camera in (views.behavioral, views.tracking)
        )
    )


def _acquisition_settings(
    configuration: pb.ExperimentConfiguration,
) -> list[bytes]:
    return [
        item.SerializeToString(deterministic=True)
        for item in configuration.backends
        if item.backend_name == "acquisition"
    ]


def camera_participation_only(
    current: pb.ExperimentConfiguration, proposed: pb.ExperimentConfiguration
) -> bool:
    """Validate a flags-only edit without treating device settings as ready."""
    expected = pb.ExperimentConfiguration()
    expected.CopyFrom(current)
    existing = [
        item for item in expected.backends if item.backend_name == "acquisition"
    ]
    selected = [
        item for item in proposed.backends if item.backend_name == "acquisition"
    ]
    if len(existing) != 1 or len(selected) != 1:
        return False
    before, after = existing[0], selected[0]
    if not before.HasField("acquisition") or not after.HasField("acquisition"):
        return False
    before.enabled = after.enabled
    for role in ("behavioral", "tracking"):
        target, source = (
            getattr(before.acquisition, role),
            getattr(after.acquisition, role),
        )
        if source.HasField("enabled"):
            target.enabled = source.enabled
        elif target.HasField("enabled"):
            target.ClearField("enabled")
    return expected == proposed and expected != current


class ConfigurationCommands:
    """Validate current settings and persist explicit history commands."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        control: ControlState,
        device: DeviceState,
        limits: LimitsState,
        validators: Mapping[
            str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
        ],
        cleanup: CleanupWorkflow,
        projections: ProjectionStore,
        publisher: SnapshotPublisher,
        operations: ControlOperations,
        configuration_history_path: Path | None,
        clock: Callable[[], int],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
        microcontroller_active: Callable[[], bool] = lambda: False,
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration_state = configuration
        self.control = control
        self.device_state = device
        self.limit_state = limits
        self.validators = validators
        self.cleanup = cleanup
        self.projections = projections
        self.publisher = publisher
        self.control_operations = operations
        self.configuration_history_path = configuration_history_path
        self.clock = clock
        self.spawn = spawn
        self.microcontroller_active = microcontroller_active
        # C11: saves run one at a time; a timed-out writer thread that has not
        # started replacing the file skips once a newer save was issued.
        self._history_lock = asyncio.Lock()
        self._history_writer_lock = threading.Lock()
        self._history_seq = 0

    def _write_history(self, seq: int, path: Path, payload: bytes) -> None:
        with self._history_writer_lock:
            if seq == self._history_seq:
                _atomic_json(path, payload, replace=True)

    async def update_configuration(
        self, request: svc.UpdateConfigurationRequest
    ) -> pb.CommandAdmission:
        command_id = request.command.operator.command_id
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(request.command)
            if (
                error
                or request.expected_revision != self.configuration_state.revision
                or self.lifecycle.session.phase not in _EDITABLE_PHASES
            ):
                return self.control_operations.admission(
                    command_id,
                    error=error or "configuration revision or phase mismatch",
                )
            blocker = self._ownership_blocker()
            if blocker:
                return self.control_operations.admission(command_id, error=blocker)
            revision = self.control.revision
            participation_only = camera_participation_only(
                self.configuration_state.current, request.proposed
            )
            validators = tuple(
                validator
                for name, validator in self.validators.items()
                if not (participation_only and name == "acquisition")
            )
            if not validators and not participation_only:
                return self.control_operations.admission(
                    command_id, error="configuration validator unavailable"
                )
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, request.proposed)
                        for validator in validators
                    )
                ),
                self.limit_state.current.validation_ns / 1e9,
            )
            if participation_only:
                results.append(
                    pb.ValidationResult(
                        completed=True,
                        valid=True,
                        component="acquisition",
                        configuration_module_version="camera-participation-v1",
                    )
                )
        except Exception as exc:
            return self.control_operations.admission(
                command_id, error=f"configuration validation unavailable: {exc}"
            )
        if any(not result.completed or not result.valid for result in results):
            first_issue = next(
                (issue for result in results for issue in result.issues), None
            )
            detail = (
                f": {first_issue.field_path}: {first_issue.failure.message}"
                if first_issue is not None
                else ""
            )
            return self.control_operations.admission(
                command_id, error=f"configuration validation failed{detail}"
            )
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(request.command)
            if (
                error
                or request.expected_revision != self.configuration_state.revision
                or self.control.revision != revision
                or self.lifecycle.session.phase not in _EDITABLE_PHASES
            ):
                return self.control_operations.admission(
                    command_id,
                    error=error
                    or "configuration changes were not applied: "
                    "configuration or session phase changed during validation",
                )
            blocker = self._ownership_blocker()
            if blocker:
                return self.control_operations.admission(command_id, error=blocker)
            if request.proposed == self.configuration_state.current:
                self.configuration_state.retain_validation(results)
                self.control_operations.operation(
                    command_id,
                    "UpdateConfiguration",
                    progress="configuration already current",
                    complete=True,
                    succeeded=True,
                )
                self.publisher.publish()
                return self.control_operations.admission(command_id)
            if (
                manual_camera_owned(self.projections, self.device_state)
                or self.microcontroller_active()
            ) and _acquisition_settings(request.proposed) != _acquisition_settings(
                self.configuration_state.current
            ):
                return self.control_operations.admission(
                    command_id,
                    error=(
                        "stop Microcontroller diagnostics to edit camera or pulse settings"
                        if self.microcontroller_active()
                        else "stop camera preview/editing to edit camera or pulse settings"
                    ),
                )
            if (
                self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
                and self.lifecycle.attempt is not None
            ):
                attempt = self.lifecycle.attempt
                attempt.cancel_requested = True
                if attempt.handoff is not None:
                    attempt.handoff.retire()
                self.lifecycle.session.phase = pb.SESSION_PHASE_SETTING_UP
                self.spawn(self.cleanup.cancel_attempt(attempt))
            self.configuration_state.current.CopyFrom(request.proposed)
            self.configuration_state.revision += 1
            self.configuration_state.retain_validation(results)
            self.projections.set_scope(
                self.projections.work, self.configuration_state.revision
            )
            self.control_operations.operation(
                command_id,
                "UpdateConfiguration",
                progress="configuration revision committed",
                complete=True,
                succeeded=True,
            )
            if self.device_state.display_pending is not None:
                self.control_operations.complete_operation(
                    self.device_state.display_pending[0],
                    success=False,
                    progress="display initialization superseded",
                    error="configuration revision changed",
                )
                self.device_state.display_pending = None
                self.projections.expected_display = None
            self.publisher.publish()
            return self.control_operations.admission(command_id)

    def _ownership_blocker(self) -> str:
        """Keep accepted revisions stable while an owner still holds resources."""
        if self.lifecycle.inventory_update_pending:
            return "SpikeGLX inventory persistence is still unresolved"
        if self.lifecycle.manual_control_cleanup_pending:
            return "manual device cleanup is still reconciling"
        attempt = self.lifecycle.attempt
        if (
            attempt is not None
            and self.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
            and attempt.closure.done
            and not attempt.closure.clean
            and not self.lifecycle.session.cleanup_confirmed
        ):
            return "session cleanup is unresolved; configuration cannot change"
        if (
            self.control.tracking_diagnostic.active
            or not self.control.tracking_diagnostic.closed
        ):
            return (
                "Tracking diagnostic must confirm closure before configuration changes"
            )
        if (
            self.device_state.calibration_blocked
            or self.device_state.calibration_pending
        ):
            return (
                "Display calibration must confirm closure before configuration changes"
            )
        calibration = self.projections.display
        if (
            calibration is not None
            and calibration.HasField("calibration")
            and (
                calibration.calibration.state
                != visual_stimulus_pb.DISPLAY_CALIBRATION_STATE_IDLE
                or not calibration.calibration.HasField("idle")
                or not calibration.calibration.idle
                or not calibration.calibration.HasField("resources_closed")
                or not calibration.calibration.resources_closed
            )
        ):
            return (
                "Display calibration must confirm closure before configuration changes"
            )
        return ""

    async def save_configuration_history(
        self, command: svc.OperatorCommand
    ) -> pb.CommandAdmission:
        deadline_ns = self.clock() + self.limit_state.current.history_ns
        return await self._save_configuration_history(command, deadline_ns)

    async def _persist_history(self, deadline_ns: int) -> None:
        async with asyncio.timeout(max(0, (deadline_ns - self.clock()) / 1e9)):
            async with self._history_lock:
                async with self.lifecycle.lock:
                    path = self.configuration_history_path
                    if path is None:
                        raise ValueError("configuration history path unavailable")
                    document = {
                        "format_version": 1,
                        "configuration": message_dict(self.configuration_state.current),
                    }
                    self._history_seq += 1
                    seq = self._history_seq
                payload = json.dumps(
                    document, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
                await asyncio.to_thread(self._write_history, seq, path, payload)

    async def save_history_on_shutdown(self, deadline_ns: int) -> None:
        """Share the bounded writer without delaying interruption or asking for input."""
        if self.configuration_history_path is None:
            return
        try:
            await self._persist_history(deadline_ns)
        except Exception as exc:
            async with self.lifecycle.lock:
                self.control.add_warning(
                    "configuration_history",
                    f"shutdown save unconfirmed or failed: {str(exc) or type(exc).__name__}",
                )
                self.publisher.publish()

    async def _save_configuration_history(
        self, command: svc.OperatorCommand, deadline_ns: int
    ) -> pb.CommandAdmission:
        async with self.lifecycle.lock:
            error = self.control_operations.authorized(command)
            if error or self.configuration_history_path is None:
                return self.control_operations.admission(
                    command.operator.command_id,
                    error=error or "configuration history path unavailable",
                )
            self.control_operations.operation(
                command.operator.command_id,
                "SaveConfigurationHistory",
                progress="writing reusable configuration history",
            )
            self.publisher.publish()
        try:
            await self._persist_history(deadline_ns)
        except Exception as exc:
            async with self.lifecycle.lock:
                self.control.add_warning(
                    "configuration_history", f"save unconfirmed or failed: {exc}"
                )
                self.control_operations.complete_operation(
                    command.operator.command_id,
                    success=False,
                    progress="history save unconfirmed or failed",
                    error=str(exc),
                )
                self.publisher.publish()
            return self.control_operations.admission(
                command.operator.command_id,
                error=f"configuration history save unconfirmed or failed: {exc}",
            )
        async with self.lifecycle.lock:
            self.control_operations.complete_operation(
                command.operator.command_id,
                success=True,
                progress="reusable configuration history saved",
            )
            self.publisher.publish()
        return self.control_operations.admission(command.operator.command_id)
