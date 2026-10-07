"""Bounded, sessionless live Tracking diagnostic over the ordered input ring."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from cephvr.acquisition.v1 import camera_pb2 as acq_camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1.messages_pb2 import FRAME_BUFFER_KIND_TRACKING
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.clock import host_time_ns
from cephvr.shared.identity import require_uuid4
from cephvr.shared.transport_deadlines import remaining_seconds
from cephvr.tracking.processing.diagnostics import DiagnosticPipeline
from cephvr.tracking.v1 import services_pb2 as wire


class TrackingDiagnostic:
    """Own one diagnostic identity and one latest exact source-frame copy."""

    def __init__(
        self,
        identity: control.ProcessIdentity,
        *,
        recovery_ns: int,
        clock: Callable[[], int] = host_time_ns,
    ) -> None:
        if recovery_ns <= 0:
            raise ValueError("Tracking diagnostic recovery budget must be positive")
        self.identity, self.recovery_ns, self.clock = identity, recovery_ns, clock
        self.command: wire.TrackingDiagnosticCommand | None = None
        self.pipeline: DiagnosticPipeline | None = None
        self.latest = wire.TrackingDiagnosticFrame()
        self.stage_status: list[wire.TrackingDiagnosticStageStatus] = []
        self.active = False
        self.close_confirmed = True
        self.input_frames = self.evaluated_frames = self.lapped_frames = 0
        self.last_duration_ns = self.maximum_duration_ns = 0
        self.failure = ""
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="tracking-diagnostic"
        )

    async def begin(
        self, request: wire.TrackingDiagnosticCommand, *, deadline_ns: int
    ) -> None:
        if self.active or not self.close_confirmed:
            raise ValueError("a Tracking diagnostic is already active or closing")
        require_uuid4(request.diagnostic_id)
        require_uuid4(request.frames.buffer.preview.acquisition_run_id)
        buffer = request.frames.buffer
        if (
            buffer.kind != FRAME_BUFFER_KIND_TRACKING
            or buffer.camera != acq_camera.CAMERA_ROLE_TRACKING
            or buffer.consumer != self.identity
            or request.frames.sync.target != self.identity
            or buffer.configuration_revision != request.configuration_revision
            or buffer.preview.controller.role != "controller"
            or not request.source_camera_serial
            or request.maximum_frame_bytes <= 0
            or request.maximum_overlay_items <= 0
        ):
            raise ValueError("Tracking diagnostic input scope or bounds are invalid")
        if request.settings.input_camera_role != acq_camera.CAMERA_ROLE_TRACKING:
            raise ValueError("diagnostic settings select another camera")
        deadline_ns = min(
            deadline_ns,
            request.deadline_monotonic_ns
            if request.deadline_monotonic_ns
            else deadline_ns,
        )
        if deadline_ns <= host_time_ns():
            raise TimeoutError("Tracking diagnostic original deadline expired")
        _validate_stages(request)
        self.command = wire.TrackingDiagnosticCommand.FromString(
            request.SerializeToString(deterministic=True)
        )
        self.command.deadline_monotonic_ns = deadline_ns
        self.close_confirmed = False
        if (buffer.image.width, buffer.image.height) != (
            request.settings.image_scale.image_width_px
            if request.settings.HasField("image_scale")
            else buffer.image.width,
            request.settings.image_scale.image_height_px
            if request.settings.HasField("image_scale")
            else buffer.image.height,
        ):
            raise ValueError("image scale dimensions differ from the acquired source")
        self.pipeline = DiagnosticPipeline(self.command, self.identity)
        loop = asyncio.get_running_loop()
        prepare_future = loop.run_in_executor(self._executor, self.pipeline.prepare)
        try:
            await asyncio.wait_for(
                asyncio.shield(prepare_future), remaining_seconds(deadline_ns)
            )
        except Exception:
            released = False
            if prepare_future.done() and host_time_ns() < deadline_ns:
                close_future = loop.run_in_executor(
                    self._executor, self.pipeline.close, deadline_ns
                )
                try:
                    released = await asyncio.wait_for(
                        asyncio.shield(close_future), remaining_seconds(deadline_ns)
                    )
                except TimeoutError:
                    released = False
            self.failure = "diagnostic preparation failed"
            if released:
                self.pipeline = None
                self.command = None
                self.close_confirmed = True
            raise
        self.stage_status = self.pipeline.status
        self.latest = wire.TrackingDiagnosticFrame(
            diagnostic_id=request.diagnostic_id,
            configuration_revision=request.configuration_revision,
            preview_run_id=buffer.preview.acquisition_run_id,
            available=False,
            unavailable_reason="waiting for the first acquired frame",
        )
        self.input_frames = self.evaluated_frames = self.lapped_frames = 0
        self.last_duration_ns = self.maximum_duration_ns = 0
        self.failure = ""
        self.active, self.close_confirmed = True, False
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="tracking-diagnostic")

    async def _run(self) -> None:
        assert self.command is not None and self.pipeline is not None
        while not self._stop.is_set():
            try:
                (
                    result,
                    inputs,
                    evaluated,
                    lapped,
                ) = await asyncio.get_running_loop().run_in_executor(
                    self._executor, self.pipeline.next_frame
                )
                self.input_frames = inputs
                self.evaluated_frames = evaluated
                self.lapped_frames = lapped
                if result is not None:
                    self.latest = result
                    self.last_duration_ns = self.pipeline.last_duration_ns
                    self.maximum_duration_ns = self.pipeline.maximum_duration_ns
            except Exception as exc:
                self.failure = f"{type(exc).__name__}: {exc}"[:512]
                self.active = False
                self._stop.set()
                deadline = self.clock() + self.recovery_ns
                if self.pipeline is not None:
                    try:
                        cleanup = asyncio.get_running_loop().run_in_executor(
                            self._executor, self.pipeline.close, deadline
                        )
                        closed = await asyncio.wait_for(
                            asyncio.shield(cleanup), remaining_seconds(deadline)
                        )
                    except Exception:
                        closed = False
                    if closed:
                        self.pipeline = None
                        self.close_confirmed = True
                break
            await asyncio.sleep(0.002)

    async def close(
        self, diagnostic_id: str, preview_run_id: str, *, deadline_ns: int
    ) -> bool:
        command = self.command
        if command is None:
            return True
        if (diagnostic_id, preview_run_id) != (
            command.diagnostic_id,
            command.frames.buffer.preview.acquisition_run_id,
        ):
            raise ValueError("close names another diagnostic or preview run")
        self._stop.set()
        task = self._task
        if task is not None:
            try:
                await asyncio.wait_for(
                    asyncio.shield(task), remaining_seconds(deadline_ns)
                )
            except TimeoutError:
                self.active = False
                return False
            self._task = None
        if self.pipeline is None:
            released = True
        elif host_time_ns() >= deadline_ns:
            released = False
        else:
            close_future = asyncio.get_running_loop().run_in_executor(
                self._executor, self.pipeline.close, deadline_ns
            )
            try:
                released = await asyncio.wait_for(
                    asyncio.shield(close_future), remaining_seconds(deadline_ns)
                )
            except TimeoutError:
                released = False
        if released:
            self.pipeline = None
            self.active = False
            self.close_confirmed = True
        return released

    def state(self) -> wire.TrackingDiagnosticState:
        command = self.command
        if command is None:
            return wire.TrackingDiagnosticState(close_confirmed=True)
        attachment = command.frames
        return wire.TrackingDiagnosticState(
            diagnostic_id=command.diagnostic_id,
            configuration_revision=command.configuration_revision,
            preview_run_id=attachment.buffer.preview.acquisition_run_id,
            acquisition_run_id=attachment.buffer.preview.acquisition_run_id,
            camera_role=attachment.buffer.camera,
            tracking_frames=acq.AttachedResource(
                resource_id=attachment.buffer.allocation_id,
                transfer_id=attachment.sync.transfer_id,
            ),
            active=self.active,
            close_confirmed=self.close_confirmed,
            stages=self.stage_status,
            input_frames=self.input_frames,
            evaluated_frames=self.evaluated_frames,
            lapped_frames=self.lapped_frames,
            last_processing_duration_ns=self.last_duration_ns,
            max_processing_duration_ns=self.maximum_duration_ns,
            failure_message=self.failure or None,
        )

    def latest_frame(
        self, query: wire.TrackingDiagnosticQuery
    ) -> wire.TrackingDiagnosticFrame:
        command = self.command
        if command is None or not self.active:
            raise ValueError("Tracking diagnostic is not active")
        if (
            query.diagnostic_id != command.diagnostic_id
            or query.configuration_revision != command.configuration_revision
            or query.preview_run_id != command.frames.buffer.preview.acquisition_run_id
            or query.controller_generation
            != command.frames.buffer.preview.controller.generation
            or query.viewer != command.authorized_gui_viewer
            or query.client_id != query.viewer.generation
        ):
            raise ValueError("viewer query is outside the authorized diagnostic scope")
        return wire.TrackingDiagnosticFrame.FromString(
            self.latest.SerializeToString(deterministic=True)
        )


def _validate_stages(request: wire.TrackingDiagnosticCommand) -> None:
    allowed = {
        wire.TRACKING_DIAGNOSTIC_STAGE_POSE,
        wire.TRACKING_DIAGNOSTIC_STAGE_SAMPLING_REGION,
        wire.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,
        wire.TRACKING_DIAGNOSTIC_STAGE_FLOW_QUALITY,
        wire.TRACKING_DIAGNOSTIC_STAGE_LOCOMOTION,
    }
    selected = list(request.selected_stages)
    if len(set(selected)) != len(selected) or set(selected) - allowed:
        raise ValueError("diagnostic stage selection is duplicated or unknown")
