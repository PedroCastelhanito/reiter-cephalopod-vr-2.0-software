"""Retain bounded worker warning views and heartbeat health snapshots."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable

from cephvr.acquisition.coordinator.evidence_helpers import (
    _report_rejected,
    _work_within_launch,
    record_for_source,
)
from cephvr.acquisition.ports import ControllerPort
from cephvr.acquisition.state import SessionRecord, WorkerRecord
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


class WorkerTelemetryReports:
    def __init__(
        self,
        *,
        backend: control.BackendContext,
        workers: dict[int, WorkerRecord],
        commands: CommandLedger,
        current_session: Callable[[], SessionRecord | None],
        controller: ControllerPort,
        lock: asyncio.Lock,
        health_silence_ns: int,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        self.backend = backend
        self.workers = workers
        self.commands = commands
        self.current_session = current_session
        self.controller = controller
        self.lock = lock
        self.clock = clock
        if health_silence_ns <= 0:
            raise ValueError("camera-rate health silence bound must be positive")
        self.health_silence_ns = health_silence_ns
        self._pending_camera_rates: dict[
            int, tuple[str, control.CameraAcquisitionRate]
        ] = {}
        self._camera_rate_task: asyncio.Task[None] | None = None

    def _record(self, source: acq.WorkerContext) -> WorkerRecord:
        return record_for_source(source, self.workers)

    async def report_warnings(
        self,
        report: acq.WorkerWarningReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        try:
            record = self._record(report.source)
            view = report.view
            if (
                view.producer != report.source.worker
                or view.camera != report.source.camera
                or view.work != report.source.work
            ):
                raise ValueError("warning view differs from registered worker context")
            if ingress_ns > deadline_ns:
                raise ValueError("worker warning report missed its original deadline")
            async with self.lock:
                if not record.retain_warning_view(view, self.commands):
                    return _report_rejected(
                        "STALE_WARNING", "worker warning revision is stale"
                    )
            return await self.controller.report_acquisition_warnings(
                wire.AcquisitionWarningReport(source=self.backend, view=view),
                deadline_ns=deadline_ns,
            )
        except (ValueError, RuntimeError) as exc:
            return _report_rejected("INVALID_WARNING", str(exc))

    async def report_heartbeat(
        self,
        heartbeat: control.HeartbeatReport,
        *,
        deadline_ns: int,
        ingress_ns: int,
    ) -> control.ReportReceipt:
        try:
            if ingress_ns > deadline_ns:
                raise ValueError("worker heartbeat missed its original deadline")
            record = next(
                item
                for item in self.workers.values()
                if item.launch.worker == heartbeat.source
            )
            if (
                not _work_within_launch(heartbeat.work, record.launch.work)
                or len(heartbeat.health_summary) > 2048
            ):
                raise ValueError("worker heartbeat differs from its registered context")
            saved = control.HeartbeatReport.FromString(
                heartbeat.SerializeToString(deterministic=True)
            )
            session = self.current_session()
            rate_is_current = not saved.HasField("camera_acquisition_rate") or (
                _valid_camera_rate(
                    saved.camera_acquisition_rate,
                    record,
                    session,
                    heartbeat.work,
                    ingress_ns,
                    self.health_silence_ns,
                )
            )
            if not rate_is_current:
                saved.ClearField("camera_acquisition_rate")
            if session is not None and _work_within_launch(
                heartbeat.work, session.work
            ):
                expected_work = (
                    session.trial.work if session.trial is not None else session.work
                )
                preparation = (
                    record.child_operations.get(record.trial.preparation.command_id)
                    if record.trial is not None and record.trial.preparation is not None
                    else None
                )
                handoff_liveness = (
                    session.trial is not None
                    and heartbeat.work == session.work
                    and preparation is not None
                    and preparation.kind == "prepare_trial"
                    and preparation.work == expected_work
                    and preparation.parent_operation == session.trial.preparation
                    and preparation.deadline_ns is not None
                    and ingress_ns <= preparation.deadline_ns
                    and heartbeat.HasField("session_phase")
                    and heartbeat.session_phase == control.SESSION_PHASE_READY
                    and not heartbeat.HasField("active_error")
                    and not heartbeat.continuing_functions
                    and not heartbeat.workers
                    and not heartbeat.cleanup_resources
                    and not heartbeat.HasField("cleanup_resources_revision")
                    and (
                        record.heartbeat is None
                        or record.heartbeat.work == session.work
                    )
                )
                cleanup_liveness = (
                    heartbeat.work == session.work
                    and heartbeat.HasField("session_phase")
                    and heartbeat.session_phase == control.SESSION_PHASE_ENDED
                    and not heartbeat.HasField("active_error")
                    and not heartbeat.continuing_functions
                    and not heartbeat.workers
                    and not heartbeat.cleanup_resources
                    and not heartbeat.HasField("cleanup_resources_revision")
                    and (
                        session.cleanup_complete
                        or any(
                            child.kind == "cleanup"
                            and child.work == session.work
                            and child.parent_operation.command_id
                            == session.cleanup_command_id
                            and child.deadline_ns is not None
                            and ingress_ns <= child.deadline_ns
                            for child in record.child_operations.values()
                        )
                    )
                )
                if heartbeat.work != expected_work and not (
                    handoff_liveness or cleanup_liveness
                ):
                    raise ValueError("worker heartbeat carries stale acquisition work")
            elif record.launch.work.WhichOneof("work") is None and (
                heartbeat.work.WhichOneof("work") is not None
            ):
                raise ValueError(
                    "sessionless worker heartbeat cannot claim session work"
                )
            previous = record.heartbeat
            if previous is not None:
                if heartbeat.sent_monotonic_ns < previous.sent_monotonic_ns:
                    raise ValueError("worker heartbeat timestamp moved backwards")
                if heartbeat.sent_monotonic_ns == previous.sent_monotonic_ns:
                    comparable = control.HeartbeatReport.FromString(
                        previous.SerializeToString(deterministic=True)
                    )
                    current_without_rate = control.HeartbeatReport.FromString(
                        saved.SerializeToString(deterministic=True)
                    )
                    comparable.ClearField("camera_acquisition_rate")
                    current_without_rate.ClearField("camera_acquisition_rate")
                    if comparable != current_without_rate:
                        raise ValueError(
                            "same worker heartbeat timestamp changed payload"
                        )
                    return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
            if saved.HasField("camera_acquisition_rate"):
                rate = saved.camera_acquisition_rate
                self._pending_camera_rates[record.context.camera] = (
                    record.launch.worker.generation,
                    control.CameraAcquisitionRate.FromString(
                        rate.SerializeToString(deterministic=True)
                    ),
                )
            async with self.lock:
                record.heartbeat = saved
            if saved.HasField("camera_acquisition_rate"):
                self._start_camera_rate_delivery()
            else:
                self._pending_camera_rates.pop(record.context.camera, None)
            return control.ReportReceipt(result=control.COMMAND_RESULT_ACCEPTED)
        except StopIteration:
            return _report_rejected(
                "UNREGISTERED_WORKER", "worker heartbeat is unregistered"
            )
        except ValueError as exc:
            return _report_rejected("INVALID_HEARTBEAT", str(exc))

    def _start_camera_rate_delivery(self) -> None:
        if self._camera_rate_task is None or self._camera_rate_task.done():
            self._camera_rate_task = asyncio.create_task(
                self._deliver_camera_rates(), name="acquisition-camera-rate"
            )

    async def _deliver_camera_rates(self) -> None:
        while self._pending_camera_rates:
            role, (generation, rate) = next(iter(self._pending_camera_rates.items()))
            self._pending_camera_rates.pop(role, None)
            session = self.current_session()
            record = self.workers.get(role)
            if record is None or record.launch.worker.generation != generation:
                continue
            latest = record.heartbeat
            if latest is None or not _valid_camera_rate(
                rate,
                record,
                session,
                latest.work,
                self.clock(),
                self.health_silence_ns,
            ):
                continue
            views = control.AcquisitionDeviceViews(source=self.backend)
            report = wire.AcquisitionDeviceStatusReport(
                views=views, camera_acquisition_rate=rate
            )
            try:
                await self.controller.report_acquisition_device_status(
                    report, deadline_ns=rate.valid_until_monotonic_ns
                )
            except Exception:
                # Rate display is optional telemetry; later heartbeats replace it.
                continue


def _valid_camera_rate(
    rate: control.CameraAcquisitionRate,
    record: WorkerRecord,
    session: SessionRecord | None,
    heartbeat_work: control.WorkContext,
    ingress_ns: int,
    health_silence_ns: int,
) -> bool:
    if (
        not record.alive
        or rate.camera != record.context.camera
        or not rate.acquisition_run_id
        or not rate.device_id
        or rate.observed_monotonic_ns <= 0
        or not rate.HasField("valid_until_monotonic_ns")
        or rate.valid_until_monotonic_ns
        != rate.observed_monotonic_ns + health_silence_ns
        or rate.observed_monotonic_ns > ingress_ns
        or ingress_ns >= rate.valid_until_monotonic_ns
        or not rate.HasField("received_fps")
        or not math.isfinite(rate.received_fps)
        or rate.received_fps <= 0
    ):
        return False
    preview = record.preview
    if preview is not None and preview.started:
        resolved = preview.resolved_camera
        return bool(
            preview.run_id == rate.acquisition_run_id
            and not preview.stopping
            and record.alive
            and resolved is not None
            and resolved.device.configured_id == rate.device_id
            and heartbeat_work.WhichOneof("work") is None
        )
    if (
        session is None
        or not record.alive
        or session.interrupted
        or session.setup_cancelled
        or session.cleanup_complete
        or rate.acquisition_run_id != session.work.session.session_id
    ):
        return False
    if not _work_within_launch(heartbeat_work, session.work):
        return False
    resolved = session.camera_resolutions.get(record.context.camera)
    return bool(
        resolved is not None
        and resolved.device.configured_id == rate.device_id
        and record.context.camera in session.required_cameras
    )
