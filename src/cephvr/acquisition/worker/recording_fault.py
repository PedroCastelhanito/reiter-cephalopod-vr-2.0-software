"""Recording-only failure isolation and retry evidence (A02/E06)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Protocol

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control


class RecordingFaultPort(Protocol):
    @property
    def run_future(self) -> Future[list[control.OutputResult]] | None: ...

    def fail_cleanup(
        self, *, deadline_ns: int
    ) -> Future[list[control.OutputResult]]: ...

    def recycle_finished(self, deadline_ns: int) -> None: ...


@dataclass
class RecordingFaultLifecycle:
    """Retain one recording fault episode without owning camera runtime state."""

    warning_occurrence: Callable[[str, str | None, str | None, int, int | None], None]
    report_isolation: Callable[
        [
            control.WorkContext,
            str,
            int,
            tuple[str, ...],
            str,
            bool,
            control.ContinuingFunctionEvidence,
        ],
        None,
    ]
    external_wake: Callable[[], None]
    faulted_session: bool = False
    cleanup_pending: bool = False
    cleanup_deadline_ns: int | None = None
    outputs: list[control.OutputResult] | None = None
    schedule: acq.WorkerSchedule | None = None
    resource_ids: tuple[str, ...] = ()
    _future: Future[list[control.OutputResult]] | None = field(default=None, repr=False)
    _recording: RecordingFaultPort | None = field(default=None, repr=False)

    @property
    def future(self) -> Future[list[control.OutputResult]] | None:
        return self._future

    def observe_failure(
        self,
        schedule: acq.WorkerSchedule,
        recording: RecordingFaultPort,
        *,
        observed_ns: int,
        recovery_deadline_ns: int,
        capture_function: control.ContinuingFunctionEvidence,
        capture_resource_id: str,
        resource_ids: tuple[str, ...],
        detach_recording: Callable[[], None],
    ) -> Future[list[control.OutputResult]] | None:
        if self.faulted_session:
            return self._future
        future = recording.run_future
        if future is None or not future.done():
            return None
        try:
            failure = future.exception()
        except BaseException as exc:
            failure = exc
        details = (
            "recording writer stopped before terminal finalization"
            if failure is None
            else str(failure)[:2048]
        )
        work, command_id = _schedule_identity(schedule)
        if not resource_ids or any(not item for item in resource_ids):
            raise ValueError("recording fault lacks its exact prepared closure")
        required = {
            f"{capture_resource_id.removesuffix('.capture')}.recording",
            *(plan.output_key for plan in schedule.outputs),
        }
        if not required.issubset(resource_ids):
            raise ValueError("retained recording fault closure omits planned outputs")
        resources = resource_ids
        self.faulted_session = True
        self.cleanup_pending = True
        self.cleanup_deadline_ns = recovery_deadline_ns
        self.schedule = schedule
        self.resource_ids = resources
        self._recording = recording
        detach_recording()
        self.warning_occurrence(
            "RECORDING_PIPELINE_FAILURE", None, details, observed_ns, None
        )
        self.report_isolation(
            work,
            command_id,
            observed_ns,
            resources,
            details,
            False,
            capture_function,
        )
        self._future = recording.fail_cleanup(deadline_ns=recovery_deadline_ns)
        self._future.add_done_callback(lambda _future: self.external_wake())
        return self._future

    def reconcile(
        self,
        future: Future[list[control.OutputResult]],
        *,
        observed_ns: int,
        capture_function: control.ContinuingFunctionEvidence,
    ) -> bool:
        """Retain actual output results and confirm local cleanup when proven."""
        if future is not self._future:
            raise RuntimeError("recording cleanup future does not match fault episode")
        try:
            results = future.result()
        except BaseException:
            self.outputs = _unconfirmed_outputs(self.schedule)
            return False
        self.outputs = [
            control.OutputResult.FromString(
                result.SerializeToString(deterministic=True)
            )
            for result in results
        ]
        recording, deadline = self._recording, self.cleanup_deadline_ns
        if recording is not None:
            if deadline is None:
                raise RuntimeError("recording cleanup has no original deadline")
            try:
                recording.recycle_finished(deadline)
            except BaseException:
                # The per-output closure result remains useful evidence even when
                # thread/pool reconciliation is still blocked.
                return False
        self._future = None
        self.cleanup_pending = False
        if self.schedule is not None:
            work, command_id = _schedule_identity(self.schedule)
            resources = self.resource_ids
            self.report_isolation(
                work,
                command_id,
                observed_ns,
                resources,
                "recording resources were reconciled after the isolated fault",
                True,
                capture_function,
            )
        return True


def _schedule_identity(
    schedule: acq.WorkerSchedule,
) -> tuple[control.WorkContext, str]:
    if not schedule.command.target.HasField("work"):
        raise ValueError("recording fault schedule has no exact work context")
    return schedule.command.target.work, schedule.command.command_id


def _unconfirmed_outputs(
    schedule: acq.WorkerSchedule | None,
) -> list[control.OutputResult]:
    if schedule is None:
        return []
    return [
        control.OutputResult(
            output_key=plan.output_key,
            path=plan.path,
            closure=control.OUTPUT_CLOSURE_UNCONFIRMED,
            failure=control.Failure(
                code="RECORDING_PIPELINE_FAILURE",
                message="recording output closure is unconfirmed after a retained fault",
            ),
        )
        for plan in schedule.outputs
    ]


def failed_outputs(
    schedule: acq.WorkerSchedule | None, closure: control.OutputClosure
) -> list[control.OutputResult]:
    if schedule is None:
        return []
    return [
        control.OutputResult(
            output_key=plan.output_key,
            path=plan.path,
            closure=closure,
            failure=control.Failure(
                code="RECORDING_PIPELINE_FAILURE",
                message="recording output was not confirmed closed after a retained failure",
            ),
        )
        for plan in schedule.outputs
    ]


def not_started_outputs(
    schedule: acq.WorkerSchedule | None,
) -> list[control.OutputResult]:
    if schedule is None:
        return []
    return [
        control.OutputResult(
            output_key=plan.output_key,
            path=plan.path,
            closure=control.OUTPUT_CLOSURE_NOT_STARTED,
            failure=control.Failure(
                code="RECORDING_PATH_FENCED",
                message="recording was unavailable before this trial output was launched",
            ),
        )
        for plan in schedule.outputs
    ]
