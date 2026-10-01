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
    ConfigurationState,
    DeviceState,
    LifecycleState,
)


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
        clock: Callable[[], int],
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
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
        self.clock = clock
        self.spawn = spawn

    async def report_acquisition_resolution(
        self, report: svc.AcquisitionResolutionReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        async with self.lifecycle.lock:
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
                max(0, (attempt.setup_deadline_ns - self.clock()) / 1e9),
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
                max(0, (attempt.setup_deadline_ns - self.clock()) / 1e9),
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
