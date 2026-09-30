"""Overlapped byte-stream pipes for supervised FFmpeg stdin/progress/stderr (E08)."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from cephvr.platform.windows.byte_stream_factory import (
    InheritedEndpoint,
    PipeConstructionOwner,
    create_child_endpoint,
)
from cephvr.platform.windows.byte_stream_native import (
    ERROR_IO_PENDING,
    ERROR_NOT_FOUND,
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    NativePendingIO,
    Overlapped,
    check,
    native_api,
    wait_ms,
)
from cephvr.platform.windows.jobs import WindowsLaunchError

EVENT_ALL_ACCESS = 0x001F0003
_MAX_DWORD = 0xFFFFFFFF
_EOF_ERRORS = frozenset({109, 232})
_CANCELLED_ERRORS = frozenset({995, 109, 232})
__all__ = ["InheritedEndpoint", "OverlappedPipe", "PipeConstructionOwner"]


class OverlappedPipe:
    """One parent-side overlapped byte endpoint; pending buffers remain pinned."""

    def __init__(
        self,
        handle: int,
        *,
        writable: bool,
        maximum_read_bytes: int,
        stop_event: int | None = None,
    ) -> None:
        if maximum_read_bytes <= 0:
            raise ValueError("native pipe read limit must be positive")
        self.handle = handle
        self.writable = writable
        self.maximum_read_bytes = maximum_read_bytes
        self._closed = False
        self._pending: NativePendingIO | None = None
        # Optional manual-reset stop event: waits end as soon as it is signalled.
        self._stop_event = stop_event
        # Set when a write may have been partly or ambiguously delivered.
        self._retired: str | None = None

    @classmethod
    def create_child_endpoint(
        cls,
        *,
        parent_writable: bool,
        owner: PipeConstructionOwner,
        deadline_ns: int,
        maximum_read_bytes: int = 64 * 1024,
    ) -> InheritedEndpoint:
        return create_child_endpoint(
            cls,
            parent_writable=parent_writable,
            owner=owner,
            deadline_ns=deadline_ns,
            maximum_read_bytes=maximum_read_bytes,
        )

    @property
    def has_pending_io(self) -> bool:
        return self._pending is not None

    def write(self, data: bytes | memoryview, *, deadline_ns: int) -> None:
        if not self.writable or self._closed:
            raise WindowsLaunchError("byte-stream endpoint is not writable")
        if self._retired is not None:
            raise WindowsLaunchError(f"byte-stream endpoint retired: {self._retired}")
        if self._pending is not None:
            raise WindowsLaunchError("prior native pipe write remains unresolved")
        view = memoryview(data).cast("B")
        if not view.contiguous or view.readonly:
            raise TypeError(
                "raw frame writes require a contiguous writable pinned buffer"
            )
        offset = 0
        while offset < len(view):
            amount = min(len(view) - offset, _MAX_DWORD)
            section = view[offset : offset + amount]
            buffer = (ctypes.c_char * amount).from_buffer(section)
            transferred = self._start_and_wait(
                buffer, amount, write=True, deadline_ns=deadline_ns
            )
            if transferred <= 0:
                raise WindowsLaunchError("overlapped pipe write made no progress")
            offset += transferred
            if offset < len(view) and time.perf_counter_ns() >= deadline_ns:
                self._retired = f"{offset} of {len(view)} bytes written"
                raise TimeoutError(f"pipe write deadline passed after {self._retired}")

    def read(self, *, deadline_ns: int) -> bytes | None:
        if self.writable or self._closed:
            raise WindowsLaunchError("byte-stream endpoint is not readable")
        pending = self._pending
        if pending is not None:
            if pending.writing:
                raise WindowsLaunchError("native pipe write is pending on a read pipe")
            transferred = self._observe(pending, deadline_ns=deadline_ns)
            if transferred == 0:
                return None
            return ctypes.string_at(ctypes.addressof(pending.buffer), transferred)
        size = self.maximum_read_bytes
        buffer = ctypes.create_string_buffer(size)
        transferred = self._start_and_wait(
            buffer, size, write=False, deadline_ns=deadline_ns
        )
        if transferred == 0:
            return None
        return buffer.raw[:transferred]

    def observe_cancelled(self, *, deadline_ns: int) -> None:
        """Cancel and observe a pending operation before releasing its owner."""
        pending = self._pending
        if pending is None:
            return
        self.request_cancel()
        try:
            self._observe(pending, deadline_ns=deadline_ns, cleanup=True)
        except TimeoutError as exc:
            raise WindowsLaunchError(
                "cancelled pipe I/O remains unconfirmed; resources retained"
            ) from exc

    def request_cancel(self) -> None:
        """Request cancellation without releasing the pending operation owner."""
        pending = self._pending
        if pending is None or pending.completed or pending.cancel_requested:
            return
        if not pending.completed:
            api = native_api()
            if not api.CancelIoEx(self.handle, ctypes.byref(pending.overlapped)):
                error = ctypes.get_last_error()
                if error != ERROR_NOT_FOUND:
                    raise WindowsLaunchError(f"CancelIoEx failed: WinError {error}")
            pending.cancel_requested = True

    def close(self) -> None:
        if self._closed:
            return
        if self._pending is not None:
            raise WindowsLaunchError(
                "native handle still owns an unobserved I/O operation"
            )
        if not native_api().CloseHandle(self.handle):
            raise WindowsLaunchError(
                f"closing byte-stream handle failed: WinError {ctypes.get_last_error()}"
            )
        self._closed = True

    def _start_and_wait(
        self,
        buffer: ctypes.Array[ctypes.c_char],
        size: int,
        *,
        write: bool,
        deadline_ns: int,
    ) -> int:
        if self._pending is not None:
            raise WindowsLaunchError(
                "native I/O remains pending; observe it before reuse"
            )
        if time.perf_counter_ns() >= deadline_ns:
            raise TimeoutError("native pipe I/O deadline already expired")
        api = native_api()
        from cephvr.platform.windows.security import owner_only_security_attributes

        security, security_backing = owner_only_security_attributes(EVENT_ALL_ACCESS)
        event = api.CreateEventW(ctypes.byref(security), True, False, None)
        _ = security_backing
        check(event, "CreateEventW")
        overlapped = Overlapped()
        overlapped.hEvent = event
        pointer = ctypes.cast(buffer, ctypes.c_void_p)
        if write:
            ok = api.WriteFile(
                self.handle, pointer, size, None, ctypes.byref(overlapped)
            )
        else:
            ok = api.ReadFile(
                self.handle, pointer, size, None, ctypes.byref(overlapped)
            )
        pending = NativePendingIO(int(event), overlapped, buffer, write, deadline_ns)
        if not ok and ctypes.get_last_error() != ERROR_IO_PENDING:
            code = ctypes.get_last_error()
            pending.error_code = code
            pending.transferred = 0
            pending.completed = True
            self._pending = pending
            return self._retire_failed_start(pending, code)
        self._pending = pending
        return self._observe(pending, deadline_ns=deadline_ns)

    def _observe(
        self,
        pending: NativePendingIO,
        *,
        deadline_ns: int,
        cleanup: bool = False,
    ) -> int:
        api = native_api()
        # A write's operation deadline is immutable: cleanup may observe and
        # release a cancelled OVERLAPPED later, but can never make that write
        # timely.  Reads use each call's observation deadline so idle readers
        # can retain and resume the same native operation.
        selected_deadline = (
            deadline_ns if cleanup or not pending.writing else pending.deadline_ns
        )
        if not pending.completed:
            if time.perf_counter_ns() >= selected_deadline:
                raise TimeoutError("native pipe observation deadline expired")
            remaining = selected_deadline - time.perf_counter_ns()
            stop = self._stop_event if not cleanup else None
            if stop is None:
                result = api.WaitForSingleObject(pending.event, wait_ms(remaining))
            else:
                handles = (wintypes.HANDLE * 2)(pending.event, stop)
                result = api.WaitForMultipleObjects(
                    2, handles, False, wait_ms(remaining)
                )
            if stop is not None and result == WAIT_OBJECT_0 + 1:
                # Stop wins: cancel; the caller observes the cancellation later.
                self.request_cancel()
                raise WindowsLaunchError("native pipe I/O stopped by stop event")
            if result != WAIT_OBJECT_0:
                if result != WAIT_TIMEOUT:
                    raise WindowsLaunchError(
                        f"wait for pipe I/O failed: WinError {ctypes.get_last_error()}"
                    )
                # Read deadlines bound this observation only. Preserve the same
                # OVERLAPPED, buffer and event so a later read resumes it.
                if not pending.writing and not cleanup:
                    raise TimeoutError("overlapped pipe read observation timed out")
                if pending.writing and not cleanup:
                    self.request_cancel()
                raise TimeoutError("overlapped pipe I/O missed its deadline")
            transferred = wintypes.DWORD()
            if not api.GetOverlappedResult(
                self.handle,
                ctypes.byref(pending.overlapped),
                ctypes.byref(transferred),
                False,
            ):
                code = ctypes.get_last_error()
                if (
                    not (
                        (cleanup or pending.cancel_requested)
                        and code in _CANCELLED_ERRORS
                    )
                    and code not in _EOF_ERRORS
                ):
                    pending.completed = True
                    pending.error_code = code
                    self._close_completed_event(pending)
                    if pending.writing:
                        self._retired = f"write outcome unconfirmed (WinError {code})"
                    raise WindowsLaunchError(
                        f"GetOverlappedResult failed: WinError {code}"
                    )
                pending.error_code = code
                # A cancelled or broken operation still reports what moved.
                pending.transferred = int(transferred.value)
            else:
                pending.transferred = int(transferred.value)
            pending.completed = True
            if pending.writing and time.perf_counter_ns() > pending.deadline_ns:
                pending.late = True
            if pending.writing:
                self._retire_uncertain_write(pending)
            if time.perf_counter_ns() > selected_deadline and not cleanup:
                raise TimeoutError(
                    "overlapped pipe I/O completed after its deadline"
                    + (f" ({self._retired})" if self._retired else "")
                )
        if not self._close_completed_event(pending):
            raise WindowsLaunchError(
                f"closing completed I/O event failed: WinError {ctypes.get_last_error()}"
            )
        if self._pending is pending:
            self._pending = None
        cancellation_allowed = cleanup or pending.cancel_requested
        if (
            not cleanup
            and pending.error_code is not None
            and pending.error_code
            not in (
                _EOF_ERRORS
                | (_CANCELLED_ERRORS if cancellation_allowed else frozenset())
            )
        ):
            raise WindowsLaunchError(
                f"overlapped pipe I/O failed: WinError {pending.error_code}"
            )
        if pending.late and not cleanup:
            raise TimeoutError(
                "overlapped pipe write completed after its deadline"
                + (f" ({self._retired})" if self._retired else "")
            )
        return pending.transferred or 0

    def _retire_uncertain_write(self, pending: NativePendingIO) -> None:
        """Retire the pipe when a late, cancelled or failed write moved any bytes."""
        moved = pending.transferred or 0
        if moved > 0 and (pending.late or pending.error_code is not None):
            self._retired = (
                f"{moved} of {ctypes.sizeof(pending.buffer)} bytes transferred "
                "by an interrupted write"
            )

    def _retire_failed_start(self, pending: NativePendingIO, code: int) -> int:
        if code in _EOF_ERRORS:
            pending.transferred = 0
            if not self._close_completed_event(pending):
                raise WindowsLaunchError(
                    f"closing completed I/O event failed: WinError {ctypes.get_last_error()}"
                )
            if self._pending is pending:
                self._pending = None
            return 0
        if not self._close_completed_event(pending):
            raise WindowsLaunchError(
                f"closing failed-operation event failed: WinError {ctypes.get_last_error()}"
            )
        if self._pending is pending:
            self._pending = None
        raise WindowsLaunchError(f"overlapped pipe I/O failed: WinError {code}")

    def _close_completed_event(self, pending: NativePendingIO) -> bool:
        if pending.event == 0:
            return True
        if not native_api().CloseHandle(pending.event):
            return False
        pending.event = 0
        return True
