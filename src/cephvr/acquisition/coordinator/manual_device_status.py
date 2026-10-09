"""Typed acquired-camera state projection and terminal status reports (A10)."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import CoordinatorIdentity, PulseRecord
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger

_STATUS_RESERVATION_BYTES = 16 * 1024


class ManualDeviceStatusReporter:
    """Retain exact camera facts and publish monotone complete device snapshots."""

    def __init__(
        self,
        *,
        identity: CoordinatorIdentity,
        controller: ControllerPort,
        commands: CommandLedger,
        pulse: PulseRecord,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.identity = identity
        self.controller = controller
        self.commands = commands
        self.pulse = pulse
        self.clock = clock
        self._revision = 0
        self._preview_revision = 0
        # A fresh coordinator owns no cameras. Preserve that fact for untouched
        # roles so lease-loss cleanup can distinguish closed from unknown.
        self._views: dict[int, control.CameraDeviceView] = {
            role: control.CameraDeviceView(
                device_open=False,
                preview_running=False,
                preview_prepared=False,
                cleanup_pending=False,
                preview_run_id="",
                preview_visible=False,
            )
            for role in (camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING)
        }
        self._diagnostic: control.MicrocontrollerDiagnosticView | None = None
        self._reports: dict[str, tuple[bytes, wire.AcquisitionDeviceStatusReport]] = {}

    def reserve(self, command: wire.BackendCommand) -> None:
        """Reserve result retention before a manual command can touch hardware."""
        record = self.commands.get(command.command_id)
        if record is None:
            raise ValueError("manual device status requires an admitted command")
        self.commands.reserve_payload(
            _reservation_key(command.command_id),
            _STATUS_RESERVATION_BYTES,
            work_key=record.work_key,
        )
        self._prune_reports()

    def resolve_camera(
        self,
        role: int,
        resolved: camera.CameraResolvedState,
        *,
        device_open: bool,
        preview_prepared: bool = False,
        preview_running: bool = False,
        preview_run_id: str = "",
        cleanup_pending: bool = False,
        configuration_revision: int | None = None,
    ) -> None:
        if role not in (
            camera.CAMERA_ROLE_BEHAVIORAL,
            camera.CAMERA_ROLE_TRACKING,
        ):
            raise ValueError("device projection has an invalid camera role")
        if (
            not resolved.HasField("device")
            or not resolved.device.configured_id
            or not resolved.HasField("applied")
        ):
            raise ValueError("device projection requires actual resolved SDK state")
        view = control.CameraDeviceView(
            device_open=device_open,
            preview_running=preview_running,
            cleanup_pending=cleanup_pending,
            preview_prepared=preview_prepared,
            device=resolved.device,
            applied_settings=resolved.applied.settings,
            preview_run_id=preview_run_id,
            preview_visible=False,
        )
        previous = self._views.get(role)
        if (
            previous is not None
            and preview_run_id
            and previous.preview_run_id == preview_run_id
        ):
            view.preview_visible = previous.preview_visible
            view.preview_visibility_revision = previous.preview_visibility_revision
            view.preview_failure = previous.preview_failure
        if configuration_revision is not None:
            view.applied_configuration_revision = configuration_revision
        view.capabilities.CopyFrom(resolved.capabilities)
        self._views[role] = view

    def owns_hardware(self) -> bool:
        return bool(self._diagnostic is not None and self._diagnostic.active) or any(
            view.device_open or view.preview_running or view.cleanup_pending
            for view in self._views.values()
        )

    def begin_device_access(self, role: int, serial: str) -> control.CameraDeviceView:
        """Retain possible ownership until the worker confirms readback or release."""
        prior = control.CameraDeviceView(device_open=False)
        if role in self._views:
            prior.CopyFrom(self._views[role])
        if not prior.device.configured_id:
            prior.device.configured_id = serial
        pending = control.CameraDeviceView()
        pending.CopyFrom(prior)
        pending.cleanup_pending = True
        self._views[role] = pending
        return prior

    def complete_connection_test(
        self, role: int, prior: control.CameraDeviceView
    ) -> None:
        self._views[role] = control.CameraDeviceView.FromString(
            prior.SerializeToString()
        )

    def update_camera_state(
        self,
        role: int,
        *,
        device_open: bool,
        preview_prepared: bool = False,
        preview_running: bool = False,
        preview_run_id: str = "",
        cleanup_pending: bool = False,
    ) -> None:
        view = self._views.get(role)
        if view is None:
            raise ValueError("device state update lacks retained resolved camera")
        view.device_open = device_open
        view.preview_prepared = preview_prepared
        view.preview_running = preview_running
        view.cleanup_pending = cleanup_pending
        # An explicit empty run confirms release; an absent field is unknown.
        view.preview_run_id = preview_run_id
        if not preview_run_id:
            view.preview_visible = False

    def set_preview_visibility(
        self, role: int, run_id: str, visible: bool, failure: str = ""
    ) -> wire.CameraPreviewVisibility | None:
        view = self._views.get(role)
        if view is None or not run_id or view.preview_run_id != run_id:
            return None
        self._preview_revision += 1
        view.preview_visible = visible
        view.preview_visibility_revision = self._preview_revision
        view.preview_failure = failure.encode("utf-8")[:2048].decode(
            "utf-8", errors="ignore"
        )
        return wire.CameraPreviewVisibility(
            camera=cast(camera.CameraRole, role),
            preview_run_id=run_id,
            revision=self._preview_revision,
            visible=visible,
            observed_monotonic_ns=self.clock(),
            failure=view.preview_failure,
        )

    async def publish_preview_visibility(
        self, observation: wire.CameraPreviewVisibility, *, deadline_ns: int
    ) -> None:
        receipt = await self.controller.report_acquisition_device_status(
            wire.AcquisitionDeviceStatusReport(
                views=control.AcquisitionDeviceViews(source=self.identity.backend),
                preview_visibility=observation,
            ),
            deadline_ns=deadline_ns,
        )
        if receipt.result != control.COMMAND_RESULT_ACCEPTED:
            raise RuntimeError(
                receipt.failure.message or "Preview visibility was rejected"
            )

    def set_diagnostic(self, signal: int, pin: str, active: bool, edges: int) -> None:
        self._diagnostic = control.MicrocontrollerDiagnosticView(
            active=active,
            signal=cast(control.MicrocontrollerSignalKind, signal),
            pin=pin,
            rising_edges=edges,
            observed_monotonic_ns=self.clock(),
        )

    def clear_diagnostic(self) -> None:
        self._diagnostic = None

    async def report(
        self,
        command: wire.BackendCommand,
        *,
        command_name: str,
        succeeded: bool,
        deadline_ns: int,
        failure: str = "",
        exported_pfs_path: str | None = None,
    ) -> control.ReportReceipt:
        fingerprint = _report_fingerprint(
            command,
            command_name,
            succeeded,
            failure,
            exported_pfs_path,
        )
        retained_report = self._reports.get(command.command_id)
        if retained_report is not None:
            if retained_report[0] != fingerprint:
                return _rejected(
                    "DEVICE_STATUS_CONFLICT",
                    "retry differs from the retained device status report",
                )
            status = wire.AcquisitionDeviceStatusReport.FromString(
                retained_report[1].SerializeToString(deterministic=True)
            )
            if self.clock() >= deadline_ns:
                return _rejected(
                    "DEVICE_STATUS_DEADLINE",
                    "device status was retained after its delivery deadline",
                )
            return await self.controller.report_acquisition_device_status(
                status, deadline_ns=deadline_ns
            )
        now = self.clock()
        if not command.command_id or not command_name:
            return _rejected(
                "DEVICE_STATUS_IDENTITY", "device status identity is incomplete"
            )
        self._revision += 1
        context = control.OperationContext(command_id=command.command_id)
        result = control.OperationState(
            context=context,
            work=command.work,
            command=command_name,
            complete=True,
            succeeded=succeeded,
        )
        if not succeeded:
            result.failure.code = "ACQUISITION_OPERATION_FAILED"
            result.failure.message = failure[:2048] or "camera operation failed"
        views = control.AcquisitionDeviceViews(
            source=self.identity.backend,
            state_revision=self._revision,
            observed_monotonic_ns=now,
        )
        for role, retained_view in self._views.items():
            target = (
                views.behavioral
                if role == camera.CAMERA_ROLE_BEHAVIORAL
                else views.tracking
            )
            target.CopyFrom(retained_view)
        if self.pulse.observation is not None:
            views.pulses.CopyFrom(self.pulse.observation)
        if self._diagnostic is not None:
            views.diagnostic.CopyFrom(self._diagnostic)
        status = wire.AcquisitionDeviceStatusReport(
            views=views,
            work=command.work,
            operation=context,
            result=result,
        )
        if succeeded and exported_pfs_path is not None:
            status.exported_pfs_path = exported_pfs_path
        retained_command = self.commands.get(command.command_id)
        if retained_command is None:
            return _rejected(
                "DEVICE_STATUS_RETENTION", "command result retention expired"
            )
        self.commands.reserve_payload(
            _reservation_key(command.command_id),
            _STATUS_RESERVATION_BYTES,
            work_key=retained_command.work_key,
        )
        self._reports[command.command_id] = (
            fingerprint,
            wire.AcquisitionDeviceStatusReport.FromString(
                status.SerializeToString(deterministic=True)
            ),
        )
        self._prune_reports()
        if now >= deadline_ns:
            return _rejected(
                "DEVICE_STATUS_DEADLINE",
                "device status was retained after its delivery deadline",
            )
        return await self.controller.report_acquisition_device_status(
            status, deadline_ns=deadline_ns
        )

    def get_report(self, command_id: str) -> wire.AcquisitionDeviceStatusReport | None:
        retained = self._reports.get(command_id)
        if retained is None or self.commands.get(command_id) is None:
            return None
        return wire.AcquisitionDeviceStatusReport.FromString(
            retained[1].SerializeToString(deterministic=True)
        )

    def finalize_command(self, command_id: str) -> None:
        self.commands.finalize_work(command_id, self.clock())
        self._prune_reports()

    def _prune_reports(self) -> None:
        self.commands.prune(self.clock())
        for command_id in tuple(self._reports):
            if self.commands.get(command_id) is None:
                self._reports.pop(command_id, None)


def _rejected(code: str, message: str) -> control.ReportReceipt:
    return control.ReportReceipt(
        result=control.COMMAND_RESULT_REJECTED,
        failure=control.Failure(code=code, message=message),
    )


def _report_fingerprint(
    command: wire.BackendCommand,
    command_name: str,
    succeeded: bool,
    failure: str,
    exported_pfs_path: str | None,
) -> bytes:
    parts = [
        command.SerializeToString(deterministic=True),
        command_name.encode("utf-8"),
        b"1" if succeeded else b"0",
        failure.encode("utf-8"),
        (exported_pfs_path or "").encode("utf-8"),
    ]
    return b"\0".join(parts)


def _reservation_key(command_id: str) -> str:
    return f"manual-device-status:{command_id}"
