"""One bounded writer thread per camera worker (A07/A08)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from queue import Full, Queue
from threading import Lock, Thread, get_ident
from typing import Generic, TypeVar

from cephvr.acquisition.recording.session import RecordingSession
from cephvr.acquisition.recording.session_contracts import (
    EndMarkerSource,
    PulseEvidence,
    RecordingCompletionContext,
)
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control

_T = TypeVar("_T")


@dataclass(slots=True)
class _Call(Generic[_T]):
    operation: Callable[[RecordingSession | None], _T]
    result: Future[_T]


class RecordingOwnerThread:
    """Serialize every recording session method away from camera SDK ownership."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("recording control handoff capacity must be positive")
        self._queue: Queue[_Call[object] | None] = Queue(maxsize=capacity)
        self._thread: Thread | None = None
        self._session: RecordingSession | None = None
        self._thread_id: int | None = None
        self._closed = False
        self._finished = False
        self._state_lock = Lock()
        self._closing = False
        self._shutdown_enqueued = False

    @property
    def thread_id(self) -> int | None:
        return self._thread_id

    def start(self) -> None:
        if self._thread is not None or self._closed:
            raise RuntimeError("recording owner thread cannot be started")
        self._thread = Thread(
            target=self._run, name="cephvr-recording-owner", daemon=False
        )
        self._thread.start()

    def install(self, session: RecordingSession) -> Future[None]:
        def install_session(_current: RecordingSession | None) -> None:
            if _current is not None:
                raise RuntimeError("prior recording session is still installed")
            self._session = session
            self._finished = False

        return self._submit_without_session(install_session)

    def prepare(self) -> Future[None]:
        return self._submit(lambda session: session.prepare())

    def schedule(
        self, schedule: acq.WorkerSchedule, *, deadline_ns: int
    ) -> Future[None]:
        return self._submit(
            lambda session: session.schedule(schedule, deadline_ns=deadline_ns)
        )

    def release(self, release: acq.WorkerRelease, *, deadline_ns: int) -> Future[None]:
        return self._submit(
            lambda session: session.release(release, deadline_ns=deadline_ns)
        )

    def run(
        self,
        end_marker: EndMarkerSource,
        pulse_evidence: Callable[[], PulseEvidence],
        completion_context: Callable[[], RecordingCompletionContext],
        *,
        deadline_ns: int,
    ) -> Future[list[control.OutputResult]]:
        def run(session: RecordingSession) -> list[control.OutputResult]:
            result = session.run(
                end_marker, pulse_evidence, completion_context, deadline_ns=deadline_ns
            )
            self._finished = True
            return result

        return self._submit(run)

    def cancel_before_start(
        self, *, deadline_ns: int
    ) -> Future[list[control.OutputResult]]:
        def cancel(session: RecordingSession) -> list[control.OutputResult]:
            result = session.cancel_before_start(deadline_ns=deadline_ns)
            self._finished = True
            return result

        return self._submit(cancel)

    def fail_cleanup(self, *, deadline_ns: int) -> Future[list[control.OutputResult]]:
        """Retry failed session cleanup while retaining writer-thread ownership."""

        def cleanup(session: RecordingSession) -> list[control.OutputResult]:
            results = session.fail_cleanup(deadline_ns=deadline_ns)
            self._finished = True
            return results

        return self._submit(cleanup)

    def remove_finished(self) -> Future[None]:
        def remove(_session: RecordingSession | None) -> None:
            if _session is None:
                raise RuntimeError("recording session is not installed")
            if not self._finished:
                raise RuntimeError("recording session has not closed its outputs")
            self._session = None
            self._finished = False

        return self._submit_without_session(remove)

    def close(self, timeout: float | None) -> bool:
        with self._state_lock:
            if self._closed:
                return self._thread is None or not self._thread.is_alive()
            self._closing = True
            thread = self._thread
            if thread is None:
                self._closed = True
                return True
            if not self._shutdown_enqueued:
                try:
                    self._queue.put_nowait(None)
                    self._shutdown_enqueued = True
                except Full as exc:
                    raise RuntimeError(
                        "recording control queue is full during shutdown"
                    ) from exc
        thread.join(timeout)
        if thread.is_alive():
            return False
        with self._state_lock:
            self._closed = True
        return True

    def _submit(self, operation: Callable[[RecordingSession], _T]) -> Future[_T]:
        def invoke(session: RecordingSession | None) -> _T:
            if session is None:
                raise RuntimeError("recording session is not installed")
            return operation(session)

        return self._submit_without_session(invoke)

    def _submit_without_session(
        self, operation: Callable[[RecordingSession | None], _T]
    ) -> Future[_T]:
        with self._state_lock:
            if self._thread is None or self._closed or self._closing:
                raise RuntimeError("recording owner thread is not active")
            result: Future[_T] = Future()
            call = _Call(
                lambda session: operation(session),
                result,
            )
            try:
                self._queue.put_nowait(call)  # type: ignore[arg-type]
            except Full as exc:
                raise RuntimeError("recording control queue is full") from exc
        return result

    def _run(self) -> None:
        self._thread_id = get_ident()
        while True:
            call = self._queue.get()
            if call is None:
                return
            if not call.result.set_running_or_notify_cancel():
                continue
            try:
                call.result.set_result(call.operation(self._session))
            except BaseException as exc:
                call.result.set_exception(exc)
