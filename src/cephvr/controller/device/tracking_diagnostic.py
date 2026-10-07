"""Controller ownership for pre-Setup Tracking diagnostics and exact input transfers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from uuid import uuid4

from google.protobuf.message import Message

from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acquisition_wire
from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.tracking_diagnostic_state import (
    copy_status as _copy_status,
)
from cephvr.controller.device.tracking_diagnostic_state import (
    matches_status as _matches_status,
)
from cephvr.controller.device.tracking_diagnostic_state import (
    reject as _reject,
)
from cephvr.controller.device.tracking_diagnostic_state import (
    tracking_settings as _tracking_settings,
)
from cephvr.controller.ports import BackendPort, SupervisorPort
from cephvr.controller.projections import ProjectionError, ProjectionStore
from cephvr.controller.state import (
    ConfigurationState,
    ControlState,
    DeviceState,
    LifecycleState,
    LimitsState,
    SupervisorState,
)
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.models.methods import FileLimits
from cephvr.tracking.v1 import services_pb2 as tracking
from cephvr.tracking.v1.methods_pb2 import TrackingFilePolicies


class TrackingDiagnosticController:
    def __init__(
        self,
        *,
        generation: str,
        lifecycle: LifecycleState,
        configuration: ConfigurationState,
        control: ControlState,
        device: DeviceState,
        supervisor: SupervisorState,
        limits: LimitsState,
        backends: Mapping[str, BackendPort],
        supervisor_peer: SupervisorPort | None,
        projections: ProjectionStore,
        file_policy_loader: Callable[[frozenset[str]], Mapping[str, Message]] | None,
        publish: Callable[[], None],
        maximum_frame_bytes: int,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.generation = generation
        self.lifecycle, self.configuration, self.control = (
            lifecycle,
            configuration,
            control,
        )
        self.device, self.supervisor, self.limits = device, supervisor, limits
        self.backends, self.projections = backends, projections
        self.supervisor_peer = supervisor_peer
        self.file_policy_loader, self.publish, self.clock = (
            file_policy_loader,
            publish,
            clock,
        )
        if maximum_frame_bytes <= 0:
            raise ValueError("tracking diagnostic frame bound must be positive")
        self.maximum_frame_bytes = maximum_frame_bytes
        self._attachment: svc.PreviewAttachmentResult | None = None
        self._viewer = pb.ProcessIdentity()
        self._tracking_transfer_operation = ""
        self._diagnostic_command: tracking.TrackingDiagnosticCommand | None = None

    async def begin(
        self, request: svc.BeginTrackingDiagnosticRequest
    ) -> pb.CommandAdmission:
        operator = request.command
        error = self._authorize(operator)
        if error:
            return _reject(operator.operator.command_id, error)
        async with self.lifecycle.lock:
            if request.expected_configuration_revision != self.configuration.revision:
                return _reject(
                    operator.operator.command_id, "configuration revision changed"
                )
            if (
                self.lifecycle.attempt is not None
                or self.lifecycle.session.phase != pb.SESSION_PHASE_CONFIGURATION
            ):
                return _reject(
                    operator.operator.command_id,
                    "Tracking diagnostic is only available before Setup",
                )
            if (
                self.control.tracking_diagnostic.active
                or not self.control.tracking_diagnostic.closed
            ):
                return _reject(
                    operator.operator.command_id,
                    "another Tracking diagnostic has not confirmed closure",
                )
            accepted_settings = _tracking_settings(self.configuration.current)
            if accepted_settings is None:
                return _reject(operator.operator.command_id, "Tracking is unconfigured")
            settings = pb.BackendSettings.FromString(
                accepted_settings.SerializeToString(deterministic=True)
            )
            if request.HasField("diagnostic_settings"):
                settings.tracking.CopyFrom(request.diagnostic_settings)
            if settings.tracking.input_camera_role != camera_pb2.CAMERA_ROLE_TRACKING:
                return _reject(
                    operator.operator.command_id,
                    "Tracking diagnostic requires the assigned Tracking camera",
                )
            devices = self.projections.devices
            if (
                devices is None
                or not devices.tracking.preview_running
                or devices.tracking.preview_run_id != request.preview_run_id
                or devices.tracking.applied_configuration_revision
                != self.configuration.revision
                or not devices.tracking.HasField("device")
                or not devices.tracking.device.physical_id
            ):
                return _reject(
                    operator.operator.command_id,
                    "exact Tracking camera preview is unavailable",
                )
            tracking_backend = self.backends.get("tracking")
            acquisition = self.backends.get("acquisition")
            if tracking_backend is None or acquisition is None:
                return _reject(
                    operator.operator.command_id,
                    "Tracking or Acquisition endpoint is unavailable",
                )
            tracking_endpoint = getattr(
                getattr(tracking_backend, "registration", None), "endpoint", ""
            )
            if not tracking_endpoint:
                return _reject(
                    operator.operator.command_id,
                    "registered Tracking endpoint is unavailable for direct viewing",
                )
            selected = tuple(request.selected_stages)
            if len(set(selected)) != len(selected):
                return _reject(
                    operator.operator.command_id,
                    "diagnostic stages must be distinct",
                )
            viewer = pb.ProcessIdentity(
                role="gui", generation=operator.operator.client_id
            )
            tracking_run = request.preview_run_id
            revision = self.configuration.revision
            camera_serial = devices.tracking.device.physical_id
            policies = await self._file_policies()
            if policies is None:
                return _reject(
                    operator.operator.command_id, "Tracking file policy is unavailable"
                )
            file_limits = FileLimits.model_validate_json(policies.limits_json)
            operation_id = str(uuid4())
            diagnostic_id = str(uuid4())
            tracking_identity = pb.ProcessIdentity(
                role="tracking", generation=tracking_backend.context.backend_generation
            )
            try:
                self.projections.expect_preview(
                    operation_id,
                    tracking_identity,
                    tracking_run,
                    camera_pb2.CAMERA_ROLE_TRACKING,
                    kind=acquisition_wire.FRAME_BUFFER_KIND_TRACKING,
                )
            except (ProjectionError, ValueError) as exc:
                return _reject(operator.operator.command_id, str(exc))
            self._viewer = viewer
            self._tracking_transfer_operation = operation_id
            self._diagnostic_command = tracking.TrackingDiagnosticCommand(
                diagnostic_id=diagnostic_id,
                configuration_revision=revision,
                selected_stages=[
                    tracking.TrackingDiagnosticStage.Name(int(stage))
                    for stage in selected
                ],
            )
            self._attachment = None
            self.control.tracking_diagnostic.CopyFrom(
                pb.TrackingDiagnosticState(
                    diagnostic_id=diagnostic_id,
                    configuration_revision=revision,
                    preview_run_id=tracking_run,
                    source_camera_serial=camera_serial,
                    tracking_endpoint=tracking_endpoint,
                    tracking_process=tracking_identity,
                    active=False,
                    closed=False,
                    stages=[
                        pb.TrackingDiagnosticStageStatus(
                            stage=stage,
                            state=pb.TRACKING_DIAGNOSTIC_STAGE_STATE_UNSPECIFIED,
                            reason="diagnostic begin is pending",
                        )
                        for stage in selected
                    ],
                )
            )
            self._publish_locked()
        deadline = self.clock() + self.limits.current.registration_ns
        attach = svc.AcquisitionTrackingDiagnosticAttachmentCommand(
            command=svc.BackendCommand(
                command_id=operation_id,
                issuer=pb.ProcessIdentity(
                    role="controller", generation=self.generation
                ),
                target=acquisition.context,
                parent_operation=pb.OperationContext(
                    command_id=operator.operator.command_id
                ),
            ),
            configuration_revision=revision,
            preview_run_id=tracking_run,
            tracking_consumer=tracking_identity,
        )
        request_to_tracking: tracking.TrackingDiagnosticCommand | None = None
        begin_attempted = False
        attachment_rpc_pending = False
        attachment_admitted = False
        try:
            attachment_rpc_pending = True
            admission = await acquisition.attach_tracking_diagnostic_input(
                attach, deadline_ns=deadline
            )
            attachment_rpc_pending = False
            if admission.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    admission.failure.message or "Acquisition rejected Tracking input"
                )
            attachment_admitted = True
            attachment = await self._wait_for_attachment(
                tracking_identity, tracking_run, deadline
            )
            if attachment is None:
                raise TimeoutError("ordered Tracking ring transfer was not confirmed")
            async with self.lifecycle.lock:
                if not self._scope_current(
                    operator, revision, tracking_run, camera_serial
                ):
                    raise RuntimeError(
                        "lease, configuration or Tracking preview changed during attachment"
                    )
            request_to_tracking = tracking.TrackingDiagnosticCommand(
                command=svc.BackendCommand(
                    command_id=str(uuid4()),
                    issuer=pb.ProcessIdentity(
                        role="controller", generation=self.generation
                    ),
                    target=tracking_backend.context,
                    parent_operation=pb.OperationContext(
                        command_id=operator.operator.command_id
                    ),
                ),
                deadline_monotonic_ns=deadline,
                configuration_revision=revision,
                diagnostic_id=diagnostic_id,
                selected_stages=[
                    tracking.TrackingDiagnosticStage.Name(int(stage))
                    for stage in selected
                ],
                frames=attachment.attachment,
                maximum_frame_bytes=min(
                    file_limits.max_native_bytes, self.maximum_frame_bytes
                ),
                settings=settings.tracking,
                file_policies=policies,
                asset_root=self.configuration.current.asset_root,
                source_camera_serial=camera_serial,
                maximum_overlay_items=256,
                authorized_gui_viewer=viewer,
            )
            self._diagnostic_command = tracking.TrackingDiagnosticCommand.FromString(
                request_to_tracking.SerializeToString(deterministic=True)
            )
            begin_attempted = True
            begun = await tracking_backend.begin_tracking_diagnostic(
                request_to_tracking, deadline_ns=deadline
            )
            if begun.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(
                    begun.failure.message or "Tracking rejected diagnostic"
                )
            expected_state = pb.TrackingDiagnosticState(
                diagnostic_id=diagnostic_id,
                configuration_revision=revision,
                preview_run_id=tracking_run,
            )
            accepted_state = await self._wait_for_status(
                tracking_backend,
                expected_state,
                attachment,
                viewer,
                deadline,
                active=True,
            )
            if accepted_state is None:
                raise RuntimeError(
                    "Tracking did not confirm the exact active diagnostic input"
                )
            async with self.lifecycle.lock:
                if not self._scope_current(
                    operator, revision, tracking_run, camera_serial
                ):
                    raise RuntimeError(
                        "lease, configuration or Tracking preview changed during diagnostic start"
                    )
                self.control.tracking_diagnostic.CopyFrom(
                    pb.TrackingDiagnosticState(
                        diagnostic_id=diagnostic_id,
                        configuration_revision=revision,
                        preview_run_id=tracking_run,
                        source_camera_serial=camera_serial,
                        tracking_endpoint=tracking_endpoint,
                        tracking_process=tracking_identity,
                    )
                )
                _copy_status(self.control.tracking_diagnostic, accepted_state)
                self._publish_locked()
            return pb.CommandAdmission(
                command_id=operator.operator.command_id,
                result=pb.COMMAND_RESULT_ACCEPTED,
            )
        except Exception as exc:
            confirmed_closed = (
                not attachment_rpc_pending
                and not begin_attempted
                and (not attachment_admitted or self._attachment is not None)
            )
            release_error = ""
            if begin_attempted and request_to_tracking is not None:
                try:
                    close = tracking.CloseTrackingDiagnosticCommand(
                        command=svc.BackendCommand(
                            command_id=str(uuid4()),
                            issuer=pb.ProcessIdentity(
                                role="controller", generation=self.generation
                            ),
                            target=tracking_backend.context,
                            parent_operation=pb.OperationContext(
                                command_id=operator.operator.command_id
                            ),
                        ),
                        deadline_monotonic_ns=deadline,
                        configuration_revision=revision,
                        diagnostic_id=diagnostic_id,
                        preview_run_id=tracking_run,
                    )
                    if self.clock() < deadline:
                        await tracking_backend.close_tracking_diagnostic(
                            close, deadline_ns=deadline
                        )
                        final = await self._wait_for_status(
                            tracking_backend,
                            self.control.tracking_diagnostic,
                            self._attachment,
                            viewer,
                            deadline,
                            active=False,
                        )
                        confirmed_closed = final is not None
                except Exception:
                    confirmed_closed = False
            if (
                confirmed_closed
                and self._attachment is not None
                and self._attachment.available
            ):
                try:
                    await self._report_release(
                        tracking_identity,
                        tracking_run,
                        self._attachment.attachment,
                        deadline=deadline,
                    )
                except Exception as release_exc:
                    confirmed_closed = False
                    release_error = str(release_exc)
            if confirmed_closed:
                self.projections.cancel_preview_expectation(operation_id)
                async with self.lifecycle.lock:
                    self._attachment = None
                    self._diagnostic_command = None
                    self.control.tracking_diagnostic.closed = True
                    self.control.tracking_diagnostic.active = False
                    self.control.tracking_diagnostic.failure = str(exc)[:512]
                    self._publish_locked()
            else:
                async with self.lifecycle.lock:
                    self.control.tracking_diagnostic.active = False
                    self.control.tracking_diagnostic.closed = False
                    self.control.tracking_diagnostic.failure = (
                        f"{exc}; diagnostic close or transfer release remains unconfirmed"
                        f"{': ' + release_error if release_error else ''}"[:512]
                    )
                    self._publish_locked()
            return _reject(operator.operator.command_id, str(exc))

    async def close(
        self, request: svc.CloseTrackingDiagnosticRequest
    ) -> pb.CommandAdmission:
        operator = request.command
        error = self._authorize(operator)
        if error:
            return _reject(operator.operator.command_id, error)
        async with self.lifecycle.lock:
            state = self.control.tracking_diagnostic
            if (
                (request.diagnostic_id, request.preview_run_id)
                != (
                    state.diagnostic_id,
                    state.preview_run_id,
                )
                or request.expected_configuration_revision
                != state.configuration_revision
            ):
                return _reject(
                    operator.operator.command_id,
                    "close names a stale Tracking diagnostic",
                )
            if state.closed:
                return pb.CommandAdmission(
                    command_id=operator.operator.command_id,
                    result=pb.COMMAND_RESULT_ACCEPTED,
                )
            backend = self.backends.get("tracking")
            attachment = self._attachment
            viewer = self._viewer
        if backend is None:
            return _reject(
                operator.operator.command_id,
                "Tracking diagnostic ownership evidence is incomplete",
            )
        deadline = self.clock() + self.limits.current.registration_ns
        if attachment is None:
            attachment = await self._wait_for_attachment(
                pb.ProcessIdentity(
                    role="tracking", generation=backend.context.backend_generation
                ),
                request.preview_run_id,
                deadline,
            )
        if attachment is None or not attachment.available:
            return _reject(
                operator.operator.command_id,
                "Tracking diagnostic transfer ownership remains unconfirmed",
            )
        error = await self._close_owned(
            state,
            backend,
            attachment,
            viewer,
            operator.operator.command_id,
            deadline,
        )
        if error:
            return _reject(operator.operator.command_id, error)
        return pb.CommandAdmission(
            command_id=operator.operator.command_id, result=pb.COMMAND_RESULT_ACCEPTED
        )

    async def owner_lost(self) -> None:
        """Stop diagnostics and release acquisition input when control is lost."""
        async with self.lifecycle.lock:
            state = pb.TrackingDiagnosticState.FromString(
                self.control.tracking_diagnostic.SerializeToString()
            )
            backend = self.backends.get("tracking")
            attachment = self._attachment
            viewer = self._viewer
        if state.closed or backend is None:
            return
        deadline = self.clock() + self.limits.current.recovery_ns
        if attachment is None and state.diagnostic_id and state.preview_run_id:
            attachment = await self._wait_for_attachment(
                pb.ProcessIdentity(
                    role="tracking", generation=backend.context.backend_generation
                ),
                state.preview_run_id,
                deadline,
            )
        if attachment is None or not attachment.available:
            return
        await self._close_owned(
            state,
            backend,
            attachment,
            viewer,
            str(uuid4()),
            deadline,
        )

    async def _close_owned(
        self,
        state: pb.TrackingDiagnosticState,
        backend: BackendPort,
        attachment: svc.PreviewAttachmentResult,
        viewer: pb.ProcessIdentity,
        parent_command_id: str,
        deadline: int,
    ) -> str:
        close = tracking.CloseTrackingDiagnosticCommand(
            command=svc.BackendCommand(
                command_id=str(uuid4()),
                issuer=pb.ProcessIdentity(
                    role="controller", generation=self.generation
                ),
                target=backend.context,
                parent_operation=pb.OperationContext(command_id=parent_command_id),
            ),
            deadline_monotonic_ns=deadline,
            configuration_revision=state.configuration_revision,
            diagnostic_id=state.diagnostic_id,
            preview_run_id=state.preview_run_id,
        )
        try:
            admission = await backend.close_tracking_diagnostic(
                close, deadline_ns=deadline
            )
            if admission.result != pb.COMMAND_RESULT_ACCEPTED:
                return admission.failure.message or "Tracking rejected close"
            status = await self._wait_for_status(
                backend,
                state,
                attachment,
                viewer,
                deadline,
                active=False,
            )
            if status is None:
                return "Tracking source release is not confirmed"
            await self._report_release(
                pb.ProcessIdentity(
                    role="tracking", generation=backend.context.backend_generation
                ),
                state.preview_run_id,
                attachment.attachment,
                deadline=deadline,
            )
            async with self.lifecycle.lock:
                self.control.tracking_diagnostic.active = False
                self.control.tracking_diagnostic.closed = True
                _copy_status(self.control.tracking_diagnostic, status)
                self._attachment = None
                self._publish_locked()
        except Exception as exc:
            return str(exc)
        return ""

    async def query(
        self, request: svc.TrackingDiagnosticQuery
    ) -> pb.TrackingDiagnosticState:
        async with self.lifecycle.lock:
            state = pb.TrackingDiagnosticState.FromString(
                self.control.tracking_diagnostic.SerializeToString()
            )
            viewer = request.viewer
            if (
                request.controller_generation != self.generation
                or request.client_id != viewer.generation
                or viewer.role != "gui"
                or viewer != self._viewer
                or (
                    request.configuration_revision,
                    request.diagnostic_id,
                    request.preview_run_id,
                )
                != (
                    state.configuration_revision,
                    state.diagnostic_id,
                    state.preview_run_id,
                )
            ):
                raise ValueError(
                    "Tracking diagnostic viewer query is stale or unauthorized"
                )
            backend = self.backends.get("tracking")
        if backend is None:
            raise ValueError("Tracking endpoint is unavailable")
        status = await backend.get_tracking_diagnostic_state(
            self._backend_query(state, viewer),
            deadline_ns=self.clock() + self.limits.current.registration_ns,
        )
        if not _matches_status(status, state, self._attachment):
            raise ValueError("Tracking diagnostic status names different resources")
        async with self.lifecycle.lock:
            current = self.control.tracking_diagnostic
            if current.diagnostic_id == state.diagnostic_id and _matches_status(
                status, state, self._attachment
            ):
                _copy_status(current, status)
                self._publish_locked()
                return pb.TrackingDiagnosticState.FromString(
                    current.SerializeToString()
                )
        raise ValueError("Tracking diagnostic changed during status query")

    async def _file_policies(self) -> TrackingFilePolicies | None:
        if self.file_policy_loader is None:
            return None
        try:
            resolved = await asyncio.wait_for(
                asyncio.to_thread(self.file_policy_loader, frozenset({"tracking"})),
                self.limits.current.validation_ns / 1e9,
            )
            value = resolved.get("tracking")
            if not isinstance(value, TrackingFilePolicies):
                return None
            return TrackingFilePolicies.FromString(
                value.SerializeToString(deterministic=True)
            )
        except Exception:
            return None

    async def _wait_for_attachment(
        self, consumer: pb.ProcessIdentity, run_id: str, deadline: int
    ) -> svc.PreviewAttachmentResult | None:
        while self.clock() < deadline:
            query = svc.PreviewAttachmentQuery(
                client_id=consumer.generation,
                controller_generation=self.generation,
                consumer=consumer,
                preview_run_id=run_id,
            )
            try:
                result = self.projections.preview(query)
            except (ProjectionError, ValueError):
                result = None
            if result is not None and result.available:
                self._attachment = result
                return result
            await asyncio.sleep(0.005)
        return None

    async def _report_release(
        self,
        consumer: pb.ProcessIdentity,
        run_id: str,
        attachment: acquisition_wire.FrameBufferAttachment,
        *,
        deadline: int,
    ) -> None:
        report = svc.PreviewConsumerReport(
            client_id=consumer.generation,
            controller_generation=self.generation,
            consumer=consumer,
            preview_run_id=run_id,
            allocation_id=attachment.buffer.allocation_id,
            transfer_id=attachment.sync.transfer_id,
            result=svc.PREVIEW_CONSUMER_RESULT_RELEASED,
        )
        async with self.lifecycle.lock:
            self.projections.preview_result(report)
        recipients = (self.backends.get("acquisition"), self.supervisor_peer)
        if any(recipient is None for recipient in recipients):
            raise RuntimeError(
                "both Acquisition and supervisor release owners are required"
            )
        acquisition, supervisor = recipients
        assert acquisition is not None and supervisor is not None
        remaining = (deadline - self.clock()) / 1e9
        if remaining <= 0:
            raise TimeoutError("original diagnostic release deadline expired")
        results = await asyncio.wait_for(
            asyncio.gather(
                acquisition.report_preview_consumer_state(report),
                supervisor.report_preview_consumer_state(report),
            ),
            timeout=remaining,
        )
        if any(result.result != pb.COMMAND_RESULT_ACCEPTED for result in results):
            raise RuntimeError("a preview release owner rejected the exact transfer")

    async def _wait_for_status(
        self,
        backend: BackendPort,
        expected: pb.TrackingDiagnosticState,
        attachment: svc.PreviewAttachmentResult | None,
        viewer: pb.ProcessIdentity,
        deadline: int,
        *,
        active: bool,
    ) -> tracking.TrackingDiagnosticState | None:
        while self.clock() < deadline:
            status = await backend.get_tracking_diagnostic_state(
                self._backend_query(expected, viewer), deadline_ns=deadline
            )
            if not _matches_status(status, expected, attachment):
                raise RuntimeError(
                    "Tracking response names different diagnostic resources"
                )
            if status.active is active and status.close_confirmed is not active:
                return status
            await asyncio.sleep(min(0.01, max(0.0, (deadline - self.clock()) / 1e9)))
        return None

    def _backend_query(
        self, state: pb.TrackingDiagnosticState, viewer: pb.ProcessIdentity
    ) -> tracking.TrackingDiagnosticQuery:
        return tracking.TrackingDiagnosticQuery(
            client_id=viewer.generation,
            viewer=viewer,
            controller_generation=self.generation,
            configuration_revision=state.configuration_revision,
            diagnostic_id=state.diagnostic_id,
            preview_run_id=state.preview_run_id,
        )

    def _authorize(self, command: svc.OperatorCommand) -> str:
        if (
            command.controller_generation != self.generation
            or self.control.owner is None
            or (command.operator.client_id, command.operator.control_generation)
            != (self.control.owner[0], self.control.owner[2])
            or (self.control.owner[0], self.control.owner[1])
            not in self.control.watches
        ):
            return "controller lease or watch is no longer authorized"
        return ""

    def _scope_current(
        self,
        command: svc.OperatorCommand,
        revision: int,
        run_id: str,
        camera_serial: str,
    ) -> bool:
        devices = self.projections.devices
        return bool(
            not self._authorize(command)
            and self.configuration.revision == revision
            and self.lifecycle.attempt is None
            and self.lifecycle.session.phase == pb.SESSION_PHASE_CONFIGURATION
            and devices is not None
            and devices.tracking.preview_running
            and devices.tracking.preview_run_id == run_id
            and devices.tracking.applied_configuration_revision == revision
            and devices.tracking.HasField("device")
            and devices.tracking.device.physical_id == camera_serial
        )

    def _publish_locked(self) -> None:
        self.control.revision += 1
        self.publish()
