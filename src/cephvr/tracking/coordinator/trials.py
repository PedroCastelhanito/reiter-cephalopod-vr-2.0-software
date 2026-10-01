"""E05/E11 scheduled trial activity, cutoff, recording and distinct closure evidence."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from google.protobuf.json_format import MessageToJson

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.transport_deadlines import remaining_seconds
from cephvr.tracking.config.models.records import (
    Header,
    TrackingRecord,
)
from cephvr.tracking.config.models.records import (
    Identity as RecordIdentity,
)
from cephvr.tracking.coordinator.ports import SessionPort
from cephvr.tracking.coordinator.reports import Reports
from cephvr.tracking.coordinator.state import Identity, State
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.recording.writer import TrackingWriter
from cephvr.tracking.types import PrivateFrame
from cephvr.tracking.v1.methods_pb2 import TrackingFirstEvaluation


class RecordSink:
    def __init__(self) -> None:
        self.writer: TrackingWriter | None = None
        self.saving = False

    def admit(self, record: TrackingRecord) -> bool:
        if not self.saving:
            return True
        return self.writer is not None and self.writer.try_admit(
            record, bookkeeping=record.record.kind in ("reset", "discard")
        )


class Trials:
    def __init__(
        self,
        identity: Identity,
        state: State,
        engine: SessionPort,
        executor: ThreadPoolExecutor,
        gate: TrialGate,
        sink: RecordSink,
        reports: Reports,
        clock: Callable[[], int],
    ) -> None:
        (
            self.identity,
            self.state,
            self.engine,
            self.executor,
            self.gate,
            self.sink,
            self.reports,
            self.clock,
        ) = identity, state, engine, executor, gate, sink, reports, clock
        self.task: asyncio.Task[None] | None = None
        self.native: asyncio.Future[None] | None = None
        self.first_task: asyncio.Task[None] | None = None
        self.loop = asyncio.get_running_loop()
        self.stop_deadline: int | None = None
        self.finish_lock = asyncio.Lock()

    def prepare(self, request: wire.PrepareTrialRequest) -> None:
        self.state.trial = wire.PrepareTrialRequest.FromString(
            request.SerializeToString()
        )
        self.state.schedule = self.state.release = None
        self.state.started = self.state.stopped = self.state.finished = None
        self.state.cutoff = None
        self.state.trial_phase = pb.TRIAL_PHASE_READY
        self.state.outputs = []
        self.stop_deadline = None
        self.sink.writer = None
        self.task = None
        self.first_task = None

    def schedule(self, request: wire.ScheduleTrialRequest) -> None:
        state = self.state
        assert state.setup is not None and state.trial is not None
        expected = [
            item
            for item in state.trial.outputs
            if item.backend == self.identity.backend
        ]
        if {item.output_key for item in request.outputs} != {
            item.output_key for item in expected
        }:
            raise ValueError("scheduled output keys differ from prepared reservations")
        if (
            bool(request.outputs) != state.setup.settings.tracking.save_tracking_data
            or len(request.outputs) > 1
        ):
            raise ValueError("tracking output reservation does not match Save setting")
        for output in request.outputs:
            path = Path(output.path)
            root = Path(state.setup.plan.session_directory) / "protocol-data"
            if (
                not output.HasField("path")
                or path.parent.resolve() != root.resolve()
                or path.name != request.trial_file_prefix + "_tracking.jsonl"
                or output.trial != state.trial.plan.context
                or output.backend != self.identity.backend
            ):
                raise ValueError(
                    "tracking output path/scope differs from scheduled reservation"
                )
            state.outputs.append(
                pb.OutputResult(
                    output_key=output.output_key,
                    path=str(path),
                    closure=pb.OUTPUT_CLOSURE_NOT_STARTED,
                    artifact_present=False,
                )
            )
        state.schedule = wire.ScheduleTrialRequest.FromString(
            request.SerializeToString()
        )
        state.trial_phase = pb.TRIAL_PHASE_STARTING

    def release(self, request: wire.ReleaseTrialRequest) -> None:
        self.state.release = wire.ReleaseTrialRequest.FromString(
            request.SerializeToString()
        )
        self.task = asyncio.create_task(self._run())

    def first_evaluation(self, frame: PrivateFrame, disposition: str, now: int) -> None:
        self.loop.call_soon_threadsafe(self._first, frame, disposition, now)

    def _first(self, frame: PrivateFrame, disposition: str, now: int) -> None:
        state = self.state
        if (
            state.started is not None
            or state.release is None
            or frame.work != state.release.command.work
        ):
            return
        state.trial_phase = pb.TRIAL_PHASE_RUNNING
        state.session_phase = pb.SESSION_PHASE_RUNNING
        state.started = pb.StartedReport(
            context=self.reports.context(state.release.command),
            actual_start_monotonic_ns=now,
            first_required_activity=[
                pb.ActivityEvidence(
                    kind="tracking_frame_evaluation",
                    observed_monotonic_ns=now,
                    device_evidence=pb.DeviceProgressEvidence(
                        tracking_evaluation=TrackingFirstEvaluation(
                            source_frame_id=frame.source.frame_id,
                            source_host_receipt_ns=frame.source.host_receipt_ns,
                            reset_generation=str(self.gate.delivery_generation),
                            disposition=disposition,
                        )
                    ),
                )
            ],
        )
        assert state.setup is not None
        self.first_task = asyncio.create_task(
            self.reports.lifecycle(
                pb.LifecycleReport(started=state.started),
                state.release.start_monotonic_ns
                + state.setup.plan.policies.start_evidence_allowance_ns,
            )
        )

    async def _run(self) -> None:
        state = self.state
        assert (
            state.setup is not None
            and state.schedule is not None
            and state.release is not None
        )
        schedule = state.schedule
        while self.clock() < schedule.start_monotonic_ns:
            if state.interrupted or state.cutoff is not None:
                return
            await asyncio.sleep(
                min(0.01, (schedule.start_monotonic_ns - self.clock()) / 1e9)
            )
        if state.interrupted or state.cutoff is not None:
            return
        if self.sink.saving:
            output = state.outputs[0]
            writer = TrackingWriter(
                Path(output.path),
                output.output_key,
                state.setup.tracking_policies.recording,
                clock=self.clock,
            )
            self.sink.writer = writer
            writer.start(self._header())
        self.gate.begin(
            state.release.command.work,
            state.preparation.preparation_generation,
            state.preparation.attached_input.transfer_id,
            schedule.start_monotonic_ns,
            schedule.normal_end_monotonic_ns,
            self.clock(),
        )
        await self.loop.run_in_executor(self.executor, self.engine.begin)
        self.native = self.loop.run_in_executor(self.executor, self.engine.run)
        try:
            await asyncio.shield(self.native)
        finally:
            state.cutoff = self.gate.seal(self.clock())
        await self.finish(
            schedule.normal_end_monotonic_ns
            + state.setup.plan.policies.stop_evidence_allowance_ns
        )

    def cutoff(self, deadline: int) -> None:
        self.stop_deadline = (
            deadline
            if self.stop_deadline is None
            else min(deadline, self.stop_deadline)
        )
        if self.state.cutoff is None:
            self.state.cutoff = (
                min(self.clock(), self.state.schedule.normal_end_monotonic_ns)
                if self.state.schedule
                else self.clock()
            )
            self.gate.seal(self.state.cutoff)

    async def stop(self, deadline: int) -> None:
        self.cutoff(deadline)
        if self.task is not None and not self.task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self.task), remaining_seconds(deadline)
                )
            except TimeoutError:
                raise TimeoutError(
                    "native trial work remains active after original stop deadline"
                ) from None
            except Exception:
                # A failed computation is not evidence of resource release.
                # The same original deadline still governs reconciliation below.
                pass
        elif self.task is not None:
            # Reconcile the retained native owner even after a failed run.
            self.task.exception()
        if self.state.finished is None:
            await self.finish(deadline)

    async def finish(self, deadline: int) -> None:
        async with self.finish_lock:
            await self._finish(deadline)

    async def _finish(self, deadline: int) -> None:
        state = self.state
        if state.finished is not None:
            return
        if self.stop_deadline is not None:
            deadline = min(deadline, self.stop_deadline)
        assert state.trial is not None
        command = state.release.command if state.release else state.trial.command
        if state.stopped is None:
            stopped = await asyncio.wait_for(
                asyncio.shield(
                    self.loop.run_in_executor(
                        self.executor, self.engine.reconcile, deadline
                    )
                ),
                remaining_seconds(deadline),
            )
            if not stopped:
                raise TimeoutError("native leases or pose work remain active")
            state.cutoff = (
                state.cutoff
                if state.cutoff is not None
                else self.gate.seal(self.clock())
            )
            state.trial_phase = pb.TRIAL_PHASE_FINALIZING
            state.stopped = pb.StoppedReport(
                context=self.reports.context(command),
                actual_stop_monotonic_ns=self.clock(),
                trial_activity_stopped=True,
                recording_interval_sealed=True,
                producer_ends=[
                    pb.ProducerRecordingEnd(
                        producer=self.identity.process,
                        source_id="tracking",
                        end_monotonic_ns=state.cutoff,
                    )
                ],
            )
            await self.reports.lifecycle(
                pb.LifecycleReport(stopped=state.stopped), deadline
            )
        assert state.setup is not None
        assert state.cutoff is not None
        finish_deadline = (
            state.cutoff + state.setup.plan.policies.trial_finished.initial_ns
        )
        if self.stop_deadline is not None:
            finish_deadline = min(finish_deadline, self.stop_deadline)
        writer = self.sink.writer
        if writer is not None:
            writer.seal(state.cutoff, interrupted=state.interrupted)
            output = await asyncio.to_thread(writer.finalize, finish_deadline)
            state.outputs = [output]
            if output.closure != pb.OUTPUT_CLOSURE_CLOSED:
                raise RuntimeError(output.failure.message)
        state.finished = pb.FinishedReport(
            context=self.reports.context(command),
            trial_activity_stopped=True,
            outputs=state.outputs,
        )
        state.trial_phase = pb.TRIAL_PHASE_ENDED
        await self.reports.lifecycle(
            pb.LifecycleReport(finished=state.finished), finish_deadline
        )

    def _header(self) -> Header:
        state = self.state
        assert (
            state.setup is not None
            and state.trial is not None
            and state.schedule is not None
        )
        methods = state.preparation.methods.methods_json
        layout = self.engine.image_layout
        return Header(
            kind="header",
            schema_version=1,
            stream_kind="tracking",
            identity=RecordIdentity(
                session_id=state.setup.plan.context.session_id,
                trial_id=state.trial.plan.context.trial_id,
                tracking_process_instance_id=self.identity.process.generation,
                writer_generation=str(uuid4()),
                configuration_revision=state.setup.plan.configuration_revision,
                prepared_generation=state.preparation.preparation_generation,
                source_allocation_id=state.preparation.attached_input.resource_id,
            ),
            trial_start_host_ns=state.schedule.start_monotonic_ns,
            trial_normal_end_host_ns=state.schedule.normal_end_monotonic_ns,
            pipeline_id=cast(
                Literal["water_flow", "fin_flow"],
                state.setup.settings.tracking.pipeline_id,
            ),
            pose_mode="manual"
            if state.setup.settings.tracking.pose_mode == pb.TRACKING_POSE_MODE_MANUAL
            else "automatic",
            prepared_methods_sha256=hashlib.sha256(methods.encode()).hexdigest(),
            prepared_methods_json=methods,
            resolved_settings_json=MessageToJson(
                state.setup.settings.tracking, preserving_proto_field_name=True
            ),
            image_width_px=layout.width,
            image_height_px=layout.height,
        )
