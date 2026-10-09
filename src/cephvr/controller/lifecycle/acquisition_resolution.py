"""Acquisition Setup resolution readback and effective settings adoption."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Mapping
from copy import deepcopy
from typing import Any

from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.device.readback import CameraReadback
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.lifecycle.setup_execution import SetupExecution
from cephvr.controller.ports import BackendPort
from cephvr.controller.projections import ProjectionStore
from cephvr.controller.receipts import rejected_receipt
from cephvr.controller.resolution import resolved_configuration
from cephvr.controller.state import (
    Attempt,
    ConfigurationEdit,
    ConfigurationState,
    DeviceState,
    LifecycleState,
)
from cephvr.shared.deadlines import remaining_seconds


class AcquisitionResolution:
    """Admit one Setup readback before resource allocation and Ready."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        device: DeviceState,
        backends: Mapping[str, BackendPort],
        camera_readback: CameraReadback,
        projections: ProjectionStore,
        preparation_context: PreparationContext,
        setup_execution: SetupExecution,
        publisher: SnapshotPublisher,
        validators: Mapping[
            str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
        ],
        generation: str,
        clock: Callable[[], int],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
        authorized: Callable[[svc.OperatorCommand], str] = lambda _command: "",
    ) -> None:
        self.lifecycle = lifecycle
        self.configuration_state = configuration
        self.device_state = device
        self.backends = backends
        self.camera_readback = camera_readback
        self.projections = projections
        self.preparation_context = preparation_context
        self.setup_execution = setup_execution
        self.publisher = publisher
        self.validators = validators
        self.generation = generation
        self.clock = clock
        self.spawn = spawn
        self.authorized = authorized

    async def report_acquisition_resolution(
        self, report: svc.AcquisitionResolutionReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        async with self.lifecycle.lock:
            edit = self.device_state.configuration_edit
            if edit is not None and report.operation.command_id == edit.operation_id:
                backend = self.backends.get("acquisition")
                roles = {item.camera for item in report.cameras}
                if (
                    backend is None
                    or report.source != backend.context
                    or report.work.WhichOneof("work") is not None
                    or ingress_ns > edit.deadline_ns
                    or not report.HasField("requested_configuration_revision")
                    or report.requested_configuration_revision != edit.revision
                    or roles != set(edit.expected_cameras)
                    or len(roles) != len(report.cameras)
                    or report.HasField("pulses") != edit.expect_pulses
                ):
                    return rejected_receipt(
                        "EVIDENCE",
                        "live configuration readback identity or batch mismatch",
                    )
                if edit.report is not None:
                    if edit.report.SerializeToString(
                        deterministic=True
                    ) != report.SerializeToString(deterministic=True):
                        return rejected_receipt(
                            "CONFLICT", "changed live configuration readback"
                        )
                    return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
                edit.report = deepcopy(report)
                self.spawn(self.adopt_live_configuration_edit(edit, deepcopy(report)))
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            camera_op = self.device_state.camera_operation
            if (
                camera_op is not None
                and report.operation.command_id == camera_op.child_id
            ):
                backend = self.backends.get("acquisition")
                if (
                    not camera_op.readback_required
                    or backend is None
                    or report.source != backend.context
                    or report.work != camera_op.work
                    or ingress_ns > camera_op.deadline_ns
                    or not report.HasField("requested_configuration_revision")
                    or report.requested_configuration_revision != camera_op.revision
                ):
                    return rejected_receipt(
                        "EVIDENCE", "camera readback operation or deadline mismatch"
                    )
                if camera_op.resolution is not None:
                    if camera_op.resolution.SerializeToString(
                        deterministic=True
                    ) != report.SerializeToString(deterministic=True):
                        return rejected_receipt("CONFLICT", "changed camera readback")
                    return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
                camera_op.resolution = deepcopy(report)
                self.spawn(
                    self.camera_readback.adopt_camera_resolution(
                        camera_op, deepcopy(report)
                    )
                )
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            attempt = self.lifecycle.attempt
            if (
                attempt is None
                or attempt.cancel_requested
                or self.lifecycle.session.phase != pb.SESSION_PHASE_SETTING_UP
                or ingress_ns > attempt.setup_deadline_ns
            ):
                return rejected_receipt("STALE", "no live acquisition Setup resolution")
            backend = attempt.required.get("acquisition")
            requested = (
                attempt.resolution_requested_revision
                if attempt.resolution_received is not None
                else attempt.prepared.configuration_revision
            )
            if (
                backend is None
                or report.source != backend.context
                or report.work.WhichOneof("work") != "session"
                or report.work.session != attempt.context
                or report.operation.command_id
                != attempt.setup_operations.get("acquisition")
                or not report.HasField("requested_configuration_revision")
                or report.requested_configuration_revision != requested
            ):
                return rejected_receipt(
                    "IDENTITY", "acquisition resolution source/work/revision mismatch"
                )
            old = attempt.resolution_received
            if old is not None:
                if old.SerializeToString(
                    deterministic=True
                ) != report.SerializeToString(deterministic=True):
                    return rejected_receipt(
                        "CONFLICT", "changed acquisition resolution"
                    )
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            attempt.resolution_received = deepcopy(report)
            attempt.resolution_requested_revision = (
                attempt.prepared.configuration_revision
            )
            self.spawn(self.adopt_acquisition_resolution(attempt, deepcopy(report)))
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def adopt_live_configuration_edit(
        self, edit: ConfigurationEdit, report: svc.AcquisitionResolutionReport
    ) -> None:
        """Validate, confirm, and commit one retained editable configuration batch."""
        try:
            backend = self.backends["acquisition"]
            expected = edit.expected_cameras
            candidate = resolved_configuration(
                edit.proposed,
                report,
                source=backend.context,
                work=pb.WorkContext(),
                operation_id=edit.operation_id,
                revision=edit.revision,
                expected_cameras=expected,
                expect_pulses=edit.expect_pulses,
            )
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, candidate)
                        for validator in self.validators.values()
                    )
                ),
                remaining_seconds(edit.deadline_ns, clock=self.clock),
            )
            if not results or any(
                not result.completed or not result.valid for result in results
            ):
                raise RuntimeError(
                    "live acquisition readback failed pure configuration validation"
                )
            async with self.lifecycle.lock:
                if (
                    self.device_state.configuration_edit is not edit
                    or self.configuration_state.revision != edit.revision
                    or self.lifecycle.session.phase
                    not in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_READY)
                    or self.lifecycle.authority_lost
                    or self.clock() >= edit.deadline_ns
                    or self.authorized(edit.command)
                ):
                    raise RuntimeError(
                        "live acquisition readback became stale before adoption"
                    )
                new_revision = self.configuration_state.revision + (
                    candidate != self.configuration_state.current
                )
                confirmed = next(
                    item.acquisition
                    for item in candidate.backends
                    if item.backend_name == "acquisition"
                    and item.WhichOneof("settings") == "acquisition"
                )
                confirmation = svc.AcquisitionConfigurationConfirmation(
                    resolution_operation=report.operation,
                    requested_configuration_revision=edit.revision,
                    confirmed_configuration_revision=new_revision,
                    confirmed=confirmed,
                )
                confirmation.command.command_id = str(uuid.uuid4())
                confirmation.command.issuer.CopyFrom(
                    pb.ProcessIdentity(role="controller", generation=self.generation)
                )
                confirmation.command.target.CopyFrom(backend.context)
                confirmation.command.parent_operation.command_id = edit.operation_id
                if report.HasField("pulses"):
                    confirmation.confirmed_pulses.CopyFrom(report.pulses)
                if new_revision != edit.revision:
                    self.configuration_state.current.CopyFrom(candidate)
                    self.configuration_state.revision = new_revision
                    self.projections.set_scope(self.projections.work, new_revision)
                edit.adopted = pb.ExperimentConfiguration.FromString(
                    self.configuration_state.current.SerializeToString(
                        deterministic=True
                    )
                )
                edit.adopted_revision = self.configuration_state.revision
                edit.validation = tuple(
                    pb.ValidationResult.FromString(item.SerializeToString())
                    for item in results
                )
                self.publisher.publish()
            transport_error: Exception | None = None
            reply = None
            for _attempt in range(2):
                remaining = remaining_seconds(edit.deadline_ns, clock=self.clock)
                if remaining <= 0:
                    break
                try:
                    reply = await asyncio.wait_for(
                        backend.confirm_configuration(
                            confirmation, deadline_ns=edit.deadline_ns
                        ),
                        remaining,
                    )
                    break
                except Exception as exc:
                    transport_error = exc
            if reply is None:
                if transport_error is not None:
                    raise RuntimeError(
                        "configuration confirmation outcome is uncertain after exact retry"
                    ) from transport_error
                raise TimeoutError("configuration confirmation deadline elapsed")
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                if transport_error is not None:
                    raise RuntimeError(
                        "configuration confirmation outcome remains uncertain after exact retry"
                    ) from transport_error
                raise RuntimeError(
                    reply.failure.message
                    if reply.HasField("failure")
                    else "acquisition rejected configuration confirmation"
                )
            async with self.lifecycle.lock:
                if (
                    self.device_state.configuration_edit is not edit
                    or self.configuration_state.revision != edit.adopted_revision
                    or self.configuration_state.current != edit.adopted
                    or self.lifecycle.authority_lost
                    or self.authorized(edit.command)
                    or self.clock() >= edit.deadline_ns
                ):
                    raise RuntimeError(
                        "configuration confirmation arrived after the edit was retired"
                    )
                edit.confirmed.set()
        except Exception as exc:
            async with self.lifecycle.lock:
                if self.device_state.configuration_edit is edit:
                    edit.failure = str(exc)
                    edit.confirmed.set()

    async def report_configuration_edit_operation(
        self, report: pb.BackendOperationReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        operation = report.operation
        async with self.lifecycle.lock:
            edit = self.device_state.configuration_edit
            terminal = self.device_state.configuration_edit_terminals.get(
                operation.context.command_id
            )
            if terminal is None:
                return rejected_receipt("STALE", "no matching configuration edit")
            if (
                report.source != terminal.source
                or operation.work.WhichOneof("work") is not None
                or operation.command != "ApplyCameraSettings"
                or not operation.complete
                or not operation.HasField("succeeded")
                or terminal.device_status is None
                or operation.succeeded != terminal.device_status.result.succeeded
            ):
                return rejected_receipt(
                    "EVIDENCE",
                    "configuration edit completion lacks exact status evidence",
                )
            if terminal.operation_result is not None:
                if terminal.operation_result.SerializeToString(
                    deterministic=True
                ) != operation.SerializeToString(deterministic=True):
                    return rejected_receipt(
                        "CONFLICT", "configuration edit completion changed on retry"
                    )
                return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)
            terminal.operation_result = pb.OperationState.FromString(
                operation.SerializeToString(deterministic=True)
            )
            terminal.operation_result_late = ingress_ns > terminal.deadline_ns
            if edit is not None and edit.operation_id == terminal.operation_id:
                edit.operation_result = pb.OperationState.FromString(
                    operation.SerializeToString(deterministic=True)
                )
                if not operation.succeeded and edit.adopted is None:
                    edit.failure = (
                        operation.failure.message
                        if operation.HasField("failure")
                        else "acquisition camera edit failed"
                    )
                    edit.confirmed.set()
            return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def adopt_acquisition_resolution(
        self, attempt: Attempt, report: svc.AcquisitionResolutionReport
    ) -> None:
        try:
            setting = next(
                (
                    item.acquisition
                    for item in attempt.prepared.configuration.backends
                    if item.backend_name == "acquisition" and item.enabled
                ),
                None,
            )
            if setting is None:
                raise RuntimeError("enabled acquisition settings unavailable")
            expected_cameras = frozenset(
                role
                for role, camera_settings in (
                    (camera_pb.CAMERA_ROLE_BEHAVIORAL, setting.behavioral),
                    (camera_pb.CAMERA_ROLE_TRACKING, setting.tracking),
                    (camera_pb.CAMERA_ROLE_EYE_TRACKING, setting.eye_tracking),
                )
                if camera_settings.HasField("enabled") and camera_settings.enabled
            )
            if not expected_cameras:
                raise RuntimeError(
                    "acquisition Setup requires an explicit enabled camera"
                )
            requested_revision = attempt.prepared.configuration_revision
            candidate = resolved_configuration(
                attempt.prepared.configuration,
                report,
                source=attempt.required["acquisition"].context,
                work=pb.WorkContext(session=attempt.context),
                operation_id=attempt.setup_operations["acquisition"],
                revision=requested_revision,
                expected_cameras=expected_cameras,
                expect_pulses=setting.pulses.HasField("port")
                and bool(setting.pulses.port),
            )
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        asyncio.to_thread(validator, candidate)
                        for validator in self.validators.values()
                    )
                ),
                remaining_seconds(attempt.setup_deadline_ns, clock=self.clock),
            )
            if any(not result.completed or not result.valid for result in results):
                raise RuntimeError(
                    "acquisition readback failed pure configuration validation"
                )
            async with self.lifecycle.lock:
                if (
                    self.lifecycle.attempt is not attempt
                    or attempt.cancel_requested
                    or self.configuration_state.revision != requested_revision
                    or self.clock() > attempt.setup_deadline_ns
                ):
                    raise RuntimeError(
                        "acquisition readback arrived after Setup or revision changed"
                    )
                # C12: the candidate stays aside until acquisition accepts it.
                new_revision = self.configuration_state.revision + (
                    candidate != self.configuration_state.current
                )
                confirmed = next(
                    item.acquisition
                    for item in candidate.backends
                    if item.backend_name == "acquisition" and item.enabled
                )
                confirmation = svc.AcquisitionConfigurationConfirmation(
                    command=self.preparation_context.handoff_command(
                        attempt, "acquisition", str(uuid.uuid4())
                    ),
                    resolution_operation=report.operation,
                    requested_configuration_revision=requested_revision,
                    confirmed_configuration_revision=new_revision,
                    confirmed=confirmed,
                )
                if report.HasField("pulses"):
                    confirmation.confirmed_pulses.CopyFrom(report.pulses)
            reply = await asyncio.wait_for(
                attempt.required["acquisition"].confirm_configuration(
                    confirmation, deadline_ns=attempt.setup_deadline_ns
                ),
                remaining_seconds(attempt.setup_deadline_ns, clock=self.clock),
            )
            if reply.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    f"acquisition rejected readback confirmation: {reply.failure.message}"
                )
            async with self.lifecycle.lock:
                if self.lifecycle.attempt is not attempt or attempt.cancel_requested:
                    return
                if (
                    self.configuration_state.revision != requested_revision
                    or self.clock() > attempt.setup_deadline_ns
                ):
                    raise RuntimeError(
                        "acquisition readback arrived after Setup or revision changed"
                    )
                if new_revision != self.configuration_state.revision:
                    self.configuration_state.current.CopyFrom(candidate)
                    self.configuration_state.revision = new_revision
                    self.projections.set_scope(
                        pb.WorkContext(session=attempt.context), new_revision
                    )
                attempt.prepared.configuration.CopyFrom(candidate)
                attempt.prepared.configuration_revision = new_revision
                if attempt.handoff is not None:
                    attempt.handoff.revision = new_revision
                attempt.resolution_confirmed = True
                self.publisher.publish()
                attempt.changed.set()
        except Exception as exc:
            await self.setup_execution.fail_setup(
                attempt, attempt.setup_command_id, f"acquisition readback: {exc}"
            )
