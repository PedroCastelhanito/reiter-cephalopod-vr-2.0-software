"""Single camera/capture/lifecycle owner with a bounded, wakeable command handoff."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition, Event, Thread, get_ident

from .ports import WorkerOperationTicket


@dataclass
class _Pending:
    operation: str
    request: object
    deadline_ns: int
    committed: bool = False


class _Ticket(WorkerOperationTicket):
    def __init__(self, owner: SerializedCameraOwner, pending: _Pending) -> None:
        self._owner = owner
        self._pending = pending
        self._done = False

    def commit(self) -> None:
        if self._done:
            raise RuntimeError("owner ticket already resolved")
        self._done = True
        self._owner._commit(self._pending)

    def cancel(self) -> None:
        if self._done:
            return
        self._done = True
        self._owner._cancel(self._pending)


class SerializedCameraOwner:
    """Run all mutable camera and capture operations on one dedicated thread.

    The operation handler owns concrete lifecycle operations; capture_once performs
    a joint SDK/control wait and frame handoff on this same thread.
    """

    def __init__(
        self,
        *,
        capacity: int,
        safety_capacity: int,
        execute: Callable[[str, object, int], None],
        capture_once: Callable[[Callable[[], bool]], bool],
        capture_active: Callable[[], bool],
        next_deadline_ns: Callable[[], int | None],
        advance_due_stages: Callable[[], None],
        wait_control: Callable[[int], None],
        wake_control: Callable[[], None],
        clear_control: Callable[[], None],
        operation_failed: Callable[[str, BaseException], None],
        owner_failed: Callable[[BaseException], None],
        idle_maintenance_interval_ns: int,
    ) -> None:
        if capacity <= 0 or safety_capacity <= 0 or idle_maintenance_interval_ns <= 0:
            raise ValueError("worker command and safety capacities must be positive")
        self._capacity = capacity
        self._safety_capacity = safety_capacity
        self._execute = execute
        self._capture_once = capture_once
        self._capture_active = capture_active
        self._next_deadline_ns = next_deadline_ns
        self._advance_due_stages = advance_due_stages
        self._wait_control = wait_control
        self._wake_control = wake_control
        self._clear_control = clear_control
        self._operation_failed = operation_failed
        self._owner_failed = owner_failed
        self._idle_maintenance_interval_ns = idle_maintenance_interval_ns
        self._condition = Condition()
        self._normal: deque[_Pending] = deque()
        self._safety: deque[_Pending] = deque()
        self._thread: Thread | None = None
        self._stopping = Event()
        self._failure: BaseException | None = None
        self._owner_thread_id: int | None = None
        self._external_wake_generation = 0
        self._external_wake_consumed = 0

    @property
    def owner_thread_id(self) -> int | None:
        return self._owner_thread_id

    @property
    def stopped(self) -> bool:
        thread = self._thread
        return thread is None or not thread.is_alive()

    def start(self) -> None:
        with self._condition:
            if self._thread is not None:
                raise RuntimeError("camera owner already started")
            self._thread = Thread(
                target=self._run, name="cephvr-camera-owner", daemon=False
            )
            self._thread.start()

    def reserve(
        self, operation: str, request: object, deadline_ns: int
    ) -> WorkerOperationTicket:
        with self._condition:
            if self._failure is not None:
                raise RuntimeError("camera owner thread failed") from self._failure
            if self._thread is None or self._stopping.is_set():
                raise RuntimeError("camera owner is not accepting commands")
            safety = operation in {
                "InterruptSession",
                "Cleanup",
                "Shutdown",
                "StopTrial",
                "StopPreview",
                "CancelSetup",
            }
            queue = self._safety if safety else self._normal
            capacity = self._safety_capacity if safety else self._capacity
            if len(queue) >= capacity:
                raise RuntimeError("worker operation handoff capacity is full")
            pending = _Pending(operation, request, deadline_ns)
            queue.append(pending)
            return _Ticket(self, pending)

    def _commit(self, pending: _Pending) -> None:
        with self._condition:
            if not self._contains(pending) or pending.committed:
                raise RuntimeError("worker operation reservation is stale")
            pending.committed = True
            self._condition.notify_all()
            self._wake_control()

    def _cancel(self, pending: _Pending) -> None:
        with self._condition:
            queue = (
                self._safety
                if pending.operation
                in {
                    "InterruptSession",
                    "Cleanup",
                    "Shutdown",
                    "StopTrial",
                    "StopPreview",
                    "CancelSetup",
                }
                else self._normal
            )
            if pending in queue and not pending.committed:
                queue.remove(pending)
                self._condition.notify_all()

    def external_wake(self) -> None:
        """Signal camera/control waiters under the same handoff lock as clear."""
        with self._condition:
            self._external_wake_generation += 1
            self._wake_control()
            self._condition.notify_all()

    def acknowledge_control_if_idle(self) -> bool:
        """Clear a manual-reset wake only while the command queues are empty."""
        with self._condition:
            if self._has_ready_locked() or self._external_wake_pending_locked():
                return False
            self._clear_control()
            if self._has_ready_locked() or self._external_wake_pending_locked():
                self._wake_control()
                return False
            return True

    def stop(self, timeout: float | None = None) -> bool:
        self._stopping.set()
        with self._condition:
            self._condition.notify_all()
        try:
            self._wake_control()
        except Exception:
            # Shutdown may have closed the SDK control event on this same owner
            # thread. The condition notification still wakes an idle owner loop.
            if not self._stopping.is_set():
                raise
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run(self) -> None:
        self._owner_thread_id = get_ident()
        try:
            while not self._stopping.is_set():
                pending = self._take_safety_ready()
                if pending is not None:
                    try:
                        self._execute(
                            pending.operation, pending.request, pending.deadline_ns
                        )
                    except BaseException as exc:
                        self._operation_failed(pending.operation, exc)
                    continue
                with self._condition:
                    observed_external_generation = self._external_wake_generation
                self._advance_due_stages()
                with self._condition:
                    self._external_wake_consumed = observed_external_generation
                pending = self._take_ready()
                if pending is not None:
                    try:
                        self._execute(
                            pending.operation, pending.request, pending.deadline_ns
                        )
                    except BaseException as exc:
                        self._operation_failed(pending.operation, exc)
                    continue
                if self._capture_active():
                    # Camera wait, retrieval, and SDK lifetime remain on this thread.
                    self._capture_once(self.capture_handoff)
                    continue
                deadline = self._next_deadline_ns()
                from cephvr.shared.clock import host_time_ns

                idle_refresh = host_time_ns() + self._idle_maintenance_interval_ns
                if deadline is None or idle_refresh < deadline:
                    deadline = idle_refresh
                if deadline is not None:
                    now_ns = host_time_ns()
                    if deadline <= now_ns:
                        self._advance_due_stages()
                        next_deadline = self._next_deadline_ns()
                        if (
                            next_deadline is not None
                            and next_deadline <= host_time_ns()
                        ):
                            raise RuntimeError(
                                "due worker stage did not advance its deadline"
                            )
                        continue
                    self.acknowledge_control_if_idle()
                    self._wait_control(deadline - now_ns)
                    continue
                self.acknowledge_control_if_idle()
                with self._condition:
                    self._condition.wait_for(
                        lambda: (
                            self._stopping.is_set()
                            or self._has_ready_locked()
                            or self._external_wake_pending_locked()
                        )
                    )
        except BaseException as exc:
            self._failure = exc
            self._stopping.set()
            self._owner_failed(exc)
            self._wake_control()
            with self._condition:
                self._condition.notify_all()

    def _take_ready(self) -> _Pending | None:
        with self._condition:
            queue = self._safety if self._safety else self._normal
            if not queue or not queue[0].committed:
                return None
            return queue.popleft()

    def _take_safety_ready(self) -> _Pending | None:
        with self._condition:
            if not self._safety or not self._safety[0].committed:
                return None
            return self._safety.popleft()

    def _contains(self, pending: _Pending) -> bool:
        return pending in self._safety or pending in self._normal

    def _has_ready_locked(self) -> bool:
        return bool(
            (self._safety and self._safety[0].committed)
            or (self._normal and self._normal[0].committed)
        )

    def _external_wake_pending_locked(self) -> bool:
        return self._external_wake_generation > self._external_wake_consumed

    def capture_handoff(self) -> bool:
        """Recheck commands and reset the control wake atomically after SDK wait."""
        with self._condition:
            if self._has_ready_locked() or self._external_wake_pending_locked():
                return False
            self._clear_control()
            if self._has_ready_locked() or self._external_wake_pending_locked():
                self._wake_control()
                return False
            return True
