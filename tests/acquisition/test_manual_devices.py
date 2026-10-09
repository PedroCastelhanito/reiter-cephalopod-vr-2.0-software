"""Manual device access and retained status delivery."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from cephvr.acquisition.coordinator.manual_device_recovery import (
    ManualDeviceRecovery,
)
from cephvr.acquisition.coordinator.manual_device_status import (
    ManualDeviceStatusReporter,
)
from cephvr.acquisition.coordinator.manual_session_access import (
    manual_configuration_available,
)
from cephvr.acquisition.state import (
    ConfigurationRecord,
    CoordinatorIdentity,
    PulseRecord,
    SessionRecord,
    SessionSlot,
)
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.acquisition.v1 import runtime_pb2
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger


def _id() -> str:
    return str(uuid4())


def test_failed_camera_work_queries_exact_retained_child_with_fresh_deadline() -> None:
    parent = control.OperationContext(command_id="failed-edit")
    context = acq.WorkerContext(
        worker=control.ProcessIdentity(
            role="behavioral_camera_worker", generation=_id()
        ),
        owner=control.ProcessIdentity(role="acquisition", generation=_id()),
        camera=camera.CAMERA_ROLE_BEHAVIORAL,
    )
    child = SimpleNamespace(
        command_id="late-start",
        parent_operation=parent,
        kind="start_preview",
        deadline_ns=100,
        report=None,
        work=control.WorkContext(),
    )
    retained = acq.WorkerRetainedResult(found=True)
    observed: list[tuple[acq.WorkerRetainedResultQuery, int]] = []

    class _Port:
        async def get_retained_result(self, request, *, deadline_ns):
            observed.append((request, deadline_ns))
            return retained

    worker = SimpleNamespace(
        context=context,
        port=_Port(),
        child_operations={child.command_id: child},
    )

    class _Resolution:
        async def failed_operation(self):
            return parent

    reconciled: list[tuple[object, object, int, int]] = []

    async def reconcile(record, operation, result, deadline_ns, ingress_ns):
        reconciled.append((record, operation, deadline_ns, ingress_ns))
        assert result is retained
        return True

    async def run() -> None:
        recovery = ManualDeviceRecovery(
            workers=SimpleNamespace(workers={camera.CAMERA_ROLE_BEHAVIORAL: worker}),
            resolution=_Resolution(),  # type: ignore[arg-type]
            pulse=PulseRecord(),
            serial=SimpleNamespace(),  # type: ignore[arg-type]
            clock=lambda: 500,
        )
        recovery.bind_retained_operation_reconciler(reconcile)
        await recovery.recover_failed_device_work(deadline_ns=900)

    asyncio.run(run())

    assert len(observed) == 1
    query, fresh_deadline = observed[0]
    assert fresh_deadline == 900
    assert query.query.target == context
    assert query.command_id == child.command_id
    assert child.deadline_ns == 100
    assert reconciled == [(worker, child, 900, 500)]


def test_quiescence_needs_live_off_state_or_bound_closed_claim_proof() -> None:
    from cephvr.acquisition.coordinator.manual_device_recovery import (
        ManualDeviceRecovery,
    )
    from cephvr.acquisition.coordinator.manual_pulse_observation import (
        invalidate_released_idle_proof,
    )
    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu

    state = mcu.MicrocontrollerState()
    state.behavioral.running = False
    state.tracking.running = False
    pulse = PulseRecord(
        released_idle_state=state,
        released_idle_connection_id="closed-connection",
    )
    recovery = ManualDeviceRecovery(
        workers=SimpleNamespace(workers={}),
        resolution=SimpleNamespace(),  # type: ignore[arg-type]
        pulse=pulse,
        serial=SimpleNamespace(),  # type: ignore[arg-type]
        clock=lambda: 10,
    )
    roles = {camera.CAMERA_ROLE_BEHAVIORAL, camera.CAMERA_ROLE_TRACKING}

    assert recovery.device_work_quiescent(required_pulse_roles=roles)

    invalidate_released_idle_proof(pulse)
    assert not recovery.device_work_quiescent(required_pulse_roles=roles)
    assert not recovery.device_work_quiescent(required_pulse_roles=roles)


class _Controller:
    def __init__(self) -> None:
        self.reports: list[wire.AcquisitionDeviceStatusReport] = []

    async def report_acquisition_device_status(
        self,
        request: wire.AcquisitionDeviceStatusReport,
        *,
        deadline_ns: int,
    ) -> control.ReportReceipt:
        _ = deadline_ns
        retained = wire.AcquisitionDeviceStatusReport.FromString(
            request.SerializeToString(deterministic=True)
        )
        self.reports.append(retained)
        return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)


def test_device_status_retry_replays_original_report_and_is_queryable() -> None:
    controller = _Controller()
    command_id = _id()
    generation = _id()
    ledger = CommandLedger(
        generation,
        10_000,
        max_records=8,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    ledger.admit(
        command_id,
        b"ApplyCameraSettings\0request",
        1,
        work_key=command_id,
        deadline_ns=10_000,
    )
    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=generation
        ),
        process=control.ProcessIdentity(role="acquisition", generation=generation),
        controller=control.ProcessIdentity(role="controller", generation=_id()),
        supervisor=control.ProcessIdentity(role="supervisor", generation=_id()),
        tracking=control.ProcessIdentity(role="tracking", generation=_id()),
    )
    clock = [10]
    reporter = ManualDeviceStatusReporter(
        identity=identity,
        controller=controller,  # type: ignore[arg-type]
        commands=ledger,
        pulse=PulseRecord(
            observation=mcu.MicrocontrollerObservation(
                state=mcu.MicrocontrollerState(
                    behavioral=mcu.PulseOutputState(enabled=True, running=True)
                )
            )
        ),
        clock=lambda: clock[0],
    )
    command = wire.BackendCommand(
        command_id=command_id,
        work=control.WorkContext(),
    )
    reporter.reserve(command)

    async def report_twice() -> None:
        first = await reporter.report(
            command,
            command_name="apply_camera_settings",
            succeeded=True,
            deadline_ns=1000,
        )
        clock[0] = 20
        second = await reporter.report(
            command,
            command_name="apply_camera_settings",
            succeeded=True,
            deadline_ns=1000,
        )
        assert first.result == control.COMMAND_RESULT_ACCEPTED
        assert second.result == control.COMMAND_RESULT_ACCEPTED

    asyncio.run(report_twice())
    assert len(controller.reports) == 2
    assert controller.reports[0] == controller.reports[1]
    assert controller.reports[0].views.state_revision == 1
    assert controller.reports[0].views.observed_monotonic_ns == 10
    for role in ("behavioral", "tracking"):
        view = getattr(controller.reports[0].views, role)
        for field in (
            "device_open",
            "preview_running",
            "preview_prepared",
            "cleanup_pending",
        ):
            assert view.HasField(field)
            assert not getattr(view, field)
    prior = reporter.begin_device_access(camera.CAMERA_ROLE_BEHAVIORAL, "serial")
    assert prior.device.configured_id == "serial"
    assert reporter._views[camera.CAMERA_ROLE_BEHAVIORAL].cleanup_pending
    assert not reporter._views[camera.CAMERA_ROLE_TRACKING].cleanup_pending
    reporter.complete_connection_test(camera.CAMERA_ROLE_BEHAVIORAL, prior)
    assert not reporter._views[camera.CAMERA_ROLE_BEHAVIORAL].cleanup_pending
    assert controller.reports[0].views.pulses.state.behavioral.enabled
    assert controller.reports[0].views.pulses.state.behavioral.running
    retained = reporter.get_report(command_id)
    assert retained == controller.reports[0]

    from cephvr.controller.device.release_evidence import stop_preview_confirmed

    resolved = camera.CameraResolvedState()
    resolved.device.configured_id = "serial"
    resolved.applied.settings.SetInParent()
    reporter.resolve_camera(camera.CAMERA_ROLE_BEHAVIORAL, resolved, device_open=False)
    view = reporter._views[camera.CAMERA_ROLE_BEHAVIORAL]
    assert stop_preview_confirmed(view, "finished-run")
    reporter.update_camera_state(camera.CAMERA_ROLE_BEHAVIORAL, device_open=False)
    assert stop_preview_confirmed(view, "finished-run")


def _session() -> SessionRecord:
    return SessionRecord(
        work=control.WorkContext(
            session=control.SessionContext(
                session_id="00000000-0000-4000-8000-000000000001"
            )
        ),
        operation=control.OperationContext(
            command_id="00000000-0000-4000-8000-000000000002"
        ),
        configuration_revision=4,
        required_cameras=set(),
    )


def test_manual_configuration_requires_local_cleanup_proof_not_delivery_receipt() -> (
    None
):
    slot = SessionSlot()
    assert manual_configuration_available(slot)

    session = _session()
    slot.current = session
    assert not manual_configuration_available(slot)

    session.cleanup_complete = True
    assert manual_configuration_available(slot)
    assert slot.current is session


def test_connection_check_retains_unknown_cleanup_until_worker_confirms() -> None:
    from cephvr.acquisition.v1 import camera_pb2 as camera

    reporter = ManualDeviceStatusReporter(
        identity=CoordinatorIdentity(
            backend=control.BackendContext(),
            process=control.ProcessIdentity(),
            controller=control.ProcessIdentity(),
            supervisor=control.ProcessIdentity(),
            tracking=control.ProcessIdentity(),
        ),
        controller=_Controller(),
        commands=CommandLedger(
            _id(),
            10_000,
            max_records=8,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        ),
        pulse=PulseRecord(),
        clock=lambda: 10,
    )
    role = camera.CAMERA_ROLE_BEHAVIORAL
    prior = reporter.begin_device_access(role, "CAM-1")
    assert not prior.device_open
    assert reporter._views[role].cleanup_pending
    # A failed worker operation leaves this flag in the reported device view.
    reporter.complete_connection_test(role, prior)
    assert not reporter._views[role].cleanup_pending
    assert not reporter._views[role].device_open


def test_camera_edit_quiesces_external_pulses_before_partial_sdk_failure(
    monkeypatch,
) -> None:
    from cephvr.acquisition.coordinator.configuration_resolution import (
        ConfigurationResolution,
    )
    from cephvr.acquisition.coordinator.manual_devices import ManualDevices
    from cephvr.acquisition.coordinator.state import ConfigurationRecord, WorkerPreview
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from cephvr.control.v1 import services_pb2 as wire
    from cephvr.shared.clock import host_time_ns
    from cephvr.shared.commands import CommandLedger

    role = camera.CAMERA_ROLE_BEHAVIORAL
    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=_id()
    )
    controller_identity = control.ProcessIdentity(role="controller", generation=_id())
    identity = CoordinatorIdentity(
        backend=backend,
        process=control.ProcessIdentity(role="acquisition", generation=_id()),
        controller=controller_identity,
        supervisor=control.ProcessIdentity(role="supervisor", generation=_id()),
        tracking=control.ProcessIdentity(role="tracking", generation=_id()),
    )
    settings = control.AcquisitionSettings()
    settings.behavioral.device.device_id = "CAM-1"
    settings.behavioral.device.frame_timing = camera.FRAME_TIMING_EXTERNAL_TRIGGER
    policies = runtime_pb2.AcquisitionFilePolicies()
    policies.cameras.add(camera=role)
    config = ConfigurationRecord(settings, policies, revision=7)
    commands = CommandLedger(
        _id(),
        10_000,
        max_records=8,
        max_bytes=1_000_000,
        result_reservation_bytes=4096,
    )
    reports: list[wire.AcquisitionDeviceStatusReport] = []

    class _Controller:
        async def report_acquisition_device_status(self, report, *, deadline_ns):
            _ = deadline_ns
            reports.append(
                wire.AcquisitionDeviceStatusReport.FromString(
                    report.SerializeToString(deterministic=True)
                )
            )
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

        async def report_acquisition_resolution(self, *_args, **_kwargs):
            raise AssertionError("a failed SDK edit must not report a full readback")

        async def report_lifecycle(self, report, *, deadline_ns):
            _ = deadline_ns
            operation = report.operation.operation
            assert operation.command == "ApplyCameraSettings"
            assert operation.succeeded is False
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    controller = _Controller()
    pulse_state = mcu.MicrocontrollerState(
        behavioral=mcu.PulseOutputState(enabled=True, running=True)
    )
    pulse = PulseRecord(
        observation=mcu.MicrocontrollerObservation(
            connection_id="connection-1", state=pulse_state
        )
    )
    events: list[str] = []

    class _Serial:
        async def off(
            self,
            roles,
            *,
            scheduled_boundary_ns,
            stop_issued_ns,
            deadline_ns,
        ):
            _ = scheduled_boundary_ns, stop_issued_ns
            events.append(f"off:{roles}")
            return mcu.PulseCommandEvidence(
                connection_id="connection-1",
                request_id="off-1",
                outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED,
                applied=True,
                dispatched_monotonic_ns=deadline_ns - 2,
                acknowledged_monotonic_ns=deadline_ns - 1,
                resulting_state=mcu.MicrocontrollerState(
                    behavioral=mcu.PulseOutputState(enabled=True, running=False)
                ),
            )

        async def status(self, *, deadline_ns):
            _ = deadline_ns
            return pulse.observation

    resolved = camera.CameraResolvedState()
    resolved.configuration_revision = 7
    resolved.device.configured_id = "CAM-1"
    resolved.device.physical_id = "physical-1"
    resolved.applied.device_id = "CAM-1"
    resolved.applied.frame_timing = camera.FRAME_TIMING_FREE_RUNNING
    resolved.applied.settings.SetInParent()
    resolved.capabilities.SetInParent()
    resolved.layout.width = 640
    resolved.layout.height = 480
    child = SimpleNamespace(
        command_id="child-edit",
        camera=role,
        work=control.WorkContext(),
        parent_operation=control.OperationContext(command_id="edit-op"),
        kind="apply_camera",
        configuration_revision=7,
        requested_device_id="CAM-1",
        deadline_ns=None,
        resolved_camera=resolved,
    )

    class _WorkerPort:
        async def edit_camera(self, _request, *, deadline_ns):
            _ = deadline_ns
            events.append("camera-edit")
            return control.CommandAdmission(result=control.COMMAND_RESULT_ACCEPTED)

    preview_start = control.OperationContext(command_id="preview-start")
    worker = SimpleNamespace(
        context=acq.WorkerContext(
            worker=control.ProcessIdentity(role="behavioral_camera_worker"),
            owner=identity.process,
            camera=role,
        ),
        preview=WorkerPreview(
            run_id="preview-1",
            configuration_revision=7,
            start_operation=preview_start,
            resolved_camera=resolved,
            started=True,
            preview_output_bit_depth=8,
        ),
        child_operations={
            preview_start.command_id: SimpleNamespace(
                kind="start_preview",
                parent_operation=control.OperationContext(command_id="prior-preview"),
                report=control.OperationState(
                    context=preview_start,
                    complete=True,
                    succeeded=True,
                ),
            )
        },
        lifecycle_evidence={
            ("preview", "started"): acq.WorkerLifecycleEvidence(
                operation=preview_start,
                started=acq.WorkerStartedEvidence(actual_start_monotonic_ns=1),
            )
        },
    )
    worker.context.work.SetInParent()

    class _Workers:
        workers = {role: worker}

    class _Preview:
        async def pause_for_pulse_change(self, roles, *, deadline_ns, parent_operation):
            assert parent_operation.command_id == request.command.command_id
            _ = deadline_ns
            events.append(f"pause:{roles}")
            worker.preview = None
            from cephvr.acquisition.coordinator.state import PausedPreview

            return (PausedPreview(role, resolved, 8),)

        async def resume_after_pulse_change(self, *_args, **_kwargs):
            raise AssertionError("failed SDK edits do not restart previews")

    lock = asyncio.Lock()
    resolution = ConfigurationResolution(
        identity=identity,
        configuration=config,
        controller=controller,  # type: ignore[arg-type]
        lock=lock,
        clock=host_time_ns,
    )
    reporter = ManualDeviceStatusReporter(
        identity=identity,
        controller=controller,  # type: ignore[arg-type]
        commands=commands,
        pulse=pulse,
        clock=host_time_ns,
    )
    manual = ManualDevices(
        identity=identity,
        configuration=config,
        session_slot=SessionSlot(),
        workers=_Workers(),  # type: ignore[arg-type]
        controller=controller,  # type: ignore[arg-type]
        resolution=resolution,
        device_status=reporter,
        pulse=pulse,
        serial=_Serial(),  # type: ignore[arg-type]
        preview=_Preview(),  # type: ignore[arg-type]
        lock=lock,
        clock=host_time_ns,
    )

    async def reject_edit(_child, _deadline, _lock, _clock):
        return SimpleNamespace(succeeded=False)

    def retain(_worker, **kwargs):
        _ = kwargs
        return acq.WorkerCommand(), child, _WorkerPort()

    monkeypatch.setattr(
        "cephvr.acquisition.coordinator.manual_devices.wait_child_operation",
        reject_edit,
    )
    monkeypatch.setattr(
        "cephvr.acquisition.coordinator.manual_devices.retain_worker_command",
        retain,
    )

    command_id = _id()
    commands.admit(
        command_id,
        b"camera-settings-command",
        host_time_ns(),
        work_key=command_id,
    )
    request = wire.AcquisitionCameraSettingsCommand(
        configuration_revision=7,
        accepted_base_revision=7,
        file_policies=policies,
    )
    request.accepted_base_settings.CopyFrom(settings)
    request.command.command_id = command_id
    request.command.issuer.CopyFrom(controller_identity)
    request.command.target.CopyFrom(backend)
    request.command.parent_operation.command_id = "update-op"
    application = request.cameras.add(camera=role)
    application.requested.CopyFrom(config.settings.behavioral.device)
    application.requested.frame_timing = camera.FRAME_TIMING_FREE_RUNNING
    application.transport.SetInParent()
    deadline_ns = host_time_ns() + 5_000_000_000

    admission = asyncio.run(manual.apply(request, deadline_ns=deadline_ns))

    assert admission.result == control.COMMAND_RESULT_REJECTED, (
        admission.failure.message
    )
    assert events == [f"pause:{(role,)}", f"off:{(role,)}", "camera-edit"], (
        admission.failure.message
    )
    assert not pulse.observation.state.behavioral.running
    assert reports and reports[-1].result.succeeded is False
    assert worker.preview is None


def test_pulse_only_edit_uses_exact_resolution_and_terminal_status() -> None:
    from cephvr.acquisition.coordinator.configuration_resolution import (
        ConfigurationResolution,
    )
    from cephvr.acquisition.coordinator.manual_devices import ManualDevices
    from cephvr.acquisition.state import ConfigurationRecord
    from cephvr.control.v1 import services_pb2 as wire
    from cephvr.shared.clock import host_time_ns

    backend = control.BackendContext(
        backend_name="acquisition", backend_generation=_id()
    )
    controller_identity = control.ProcessIdentity(role="controller", generation=_id())
    identity = CoordinatorIdentity(
        backend=backend,
        process=control.ProcessIdentity(role="acquisition", generation=_id()),
        controller=controller_identity,
        supervisor=control.ProcessIdentity(role="supervisor", generation=_id()),
        tracking=control.ProcessIdentity(role="tracking", generation=_id()),
    )
    settings = control.AcquisitionSettings()
    settings.pulses.port = "COM8"
    settings.pulses.behavioral.pin = "D10"
    settings.pulses.behavioral.requested_frequency_hz = 20.0
    policies = runtime_pb2.AcquisitionFilePolicies()
    configuration = ConfigurationRecord(settings, policies, revision=7)
    commands = CommandLedger(
        _id(), 10_000, max_records=8, max_bytes=1_000_000, result_reservation_bytes=4096
    )
    pulse = PulseRecord()
    resolution: ConfigurationResolution

    class _Controller:
        reports: list[wire.AcquisitionResolutionReport] = []
        statuses: list[wire.AcquisitionDeviceStatusReport] = []

        async def report_acquisition_resolution(self, report, *, deadline_ns):
            _ = deadline_ns
            self.reports.append(
                wire.AcquisitionResolutionReport.FromString(
                    report.SerializeToString(deterministic=True)
                )
            )
            confirmation = wire.AcquisitionConfigurationConfirmation(
                resolution_operation=report.operation,
                requested_configuration_revision=7,
                confirmed_configuration_revision=7,
                confirmed=settings,
                confirmed_pulses=report.pulses,
            )
            confirmation.command.command_id = "confirm-pulse-edit"
            confirmation.command.issuer.CopyFrom(controller_identity)
            confirmation.command.target.CopyFrom(backend)
            confirmation.command.parent_operation.CopyFrom(report.operation)
            result = await resolution.confirm(confirmation, deadline_ns=100)
            return control.ReportReceipt(result=result.result)

        async def report_acquisition_device_status(self, report, *, deadline_ns):
            _ = deadline_ns
            self.statuses.append(
                wire.AcquisitionDeviceStatusReport.FromString(
                    report.SerializeToString(deterministic=True)
                )
            )
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

        async def report_lifecycle(self, report, *, deadline_ns):
            _ = report, deadline_ns
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)

    controller = _Controller()
    resolution = ConfigurationResolution(
        identity=identity,
        configuration=configuration,
        controller=controller,  # type: ignore[arg-type]
        lock=asyncio.Lock(),
        clock=lambda: 10,
    )
    reporter = ManualDeviceStatusReporter(
        identity=identity,
        controller=controller,  # type: ignore[arg-type]
        commands=commands,
        pulse=pulse,
        clock=lambda: 10,
    )

    class _Workers:
        workers: dict[int, object] = {}

        async def retire_completed_session(self, *_args, **_kwargs):
            return None

    class _Serial:
        async def connect(self, *, deadline_ns):
            _ = deadline_ns
            return mcu.MicrocontrollerObservation(port="COM8")

        async def configure(
            self,
            requested,
            *,
            active_roles,
            deadline_ns,
            resolution_operation,
            requested_configuration_revision,
        ):
            _ = deadline_ns
            assert active_roles == ()
            assert requested == edited
            assert resolution_operation.command_id == request.command.command_id
            assert requested_configuration_revision == request.configuration_revision
            return mcu.MicrocontrollerObservation(
                port="COM8", state=mcu.MicrocontrollerState()
            )

    class _UnusedPreview:
        pass

    edited = camera.CameraPulseConfiguration()
    edited.CopyFrom(settings.pulses)
    edited.behavioral.requested_frequency_hz = 25.0
    request = wire.AcquisitionCameraSettingsCommand(
        configuration_revision=7,
        accepted_base_revision=7,
        file_policies=policies,
        pulses=wire.PulseSettingsApplication(requested=edited),
    )
    request.accepted_base_settings.CopyFrom(settings)
    request.command.command_id = _id()
    request.command.issuer.CopyFrom(controller_identity)
    request.command.target.CopyFrom(backend)
    request.command.parent_operation.command_id = "operator-edit"
    commands.admit(
        request.command.command_id,
        b"pulse-only-edit",
        host_time_ns(),
        work_key=request.command.command_id,
    )
    manual = ManualDevices(
        identity=identity,
        configuration=configuration,
        session_slot=SessionSlot(),
        workers=_Workers(),  # type: ignore[arg-type]
        controller=controller,  # type: ignore[arg-type]
        resolution=resolution,
        device_status=reporter,
        pulse=pulse,
        serial=_Serial(),  # type: ignore[arg-type]
        preview=_UnusedPreview(),  # type: ignore[arg-type]
        lock=resolution.lock,
        clock=lambda: 10,
    )

    admission = asyncio.run(
        manual.apply(request, deadline_ns=host_time_ns() + 5_000_000_000)
    )

    assert admission.result == control.COMMAND_RESULT_ACCEPTED
    assert len(controller.reports) == 1
    assert not controller.reports[0].cameras
    assert controller.reports[0].pulses.requested == edited
    assert len(controller.statuses) == 1 and controller.statuses[0].result.succeeded


def test_manual_command_installs_current_draft_but_rejects_stale_or_owned_changes() -> (
    None
):
    from types import SimpleNamespace

    from cephvr.acquisition.coordinator.manual_configuration import ManualConfiguration

    identity = CoordinatorIdentity(
        backend=control.BackendContext(
            backend_name="acquisition", backend_generation=_id()
        ),
        process=control.ProcessIdentity(),
        controller=control.ProcessIdentity(role="controller", generation=_id()),
        supervisor=control.ProcessIdentity(),
        tracking=control.ProcessIdentity(),
    )
    configuration = ConfigurationRecord(
        control.AcquisitionSettings(), runtime_pb2.AcquisitionFilePolicies(), revision=1
    )
    configuration.settings.pulses.port = "COM8"
    owned = [False]
    owner = ManualConfiguration(
        configuration,
        identity,
        SessionSlot(),
        SimpleNamespace(owns_hardware=lambda: owned[0]),
        lambda: 10,
    )
    request = wire.AcquisitionMicrocontrollerCommand(
        configuration_revision=2, kind=wire.MICROCONTROLLER_COMMAND_KIND_CONNECT
    )
    request.command.command_id = _id()
    request.command.parent_operation.command_id = _id()
    request.command.issuer.CopyFrom(identity.controller)
    request.command.target.CopyFrom(identity.backend)
    request.settings.pulses.port = "COM9"
    request.requested.CopyFrom(request.settings.pulses)
    assert owner.install(request, 100) is None
    assert configuration.revision == 2 and configuration.settings.pulses.port == "COM9"
    request.configuration_revision = 1
    request.settings.pulses.port = "COM7"
    assert owner.install(request, 100).result == control.COMMAND_RESULT_REJECTED
    request.configuration_revision = 3
    owned[0] = True
    assert owner.install(request, 100).result == control.COMMAND_RESULT_REJECTED
    assert configuration.settings.pulses.port == "COM9"
    request.settings.CopyFrom(configuration.settings)
    assert owner.install(request, 100) is None  # unrelated controller revision
    assert configuration.revision == 3
