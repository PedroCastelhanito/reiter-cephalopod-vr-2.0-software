"""Pending native I/O ownership, cancellation and bounded cleanup."""

from __future__ import annotations

import ctypes
import time
from typing import Any
from unittest.mock import Mock

import pytest

from cephvr.platform.windows import byte_stream
from cephvr.platform.windows.byte_stream_native import (
    WAIT_OBJECT_0,
    WAIT_TIMEOUT,
    NativePendingIO,
    Overlapped,
)
from cephvr.platform.windows.jobs import WindowsLaunchError


def test_idle_read_observation_resumes_the_same_pending_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.WaitForSingleObject.side_effect = [WAIT_TIMEOUT, WAIT_OBJECT_0]
    fake.GetOverlappedResult.side_effect = _read_three_bytes
    fake.CloseHandle.return_value = True
    monkeypatch.setattr(byte_stream, "native_api", lambda: fake)
    pipe = byte_stream.OverlappedPipe(41, writable=False, maximum_read_bytes=8)
    buffer = ctypes.create_string_buffer(8)
    ctypes.memmove(ctypes.addressof(buffer), b"abc", 3)
    pending = NativePendingIO(71, Overlapped(), buffer, False, 2**63 - 1)
    pipe._pending = pending

    with pytest.raises(TimeoutError):
        pipe.read(deadline_ns=2**63 - 1)

    assert pipe._pending is pending
    assert pipe.read(deadline_ns=2**63 - 1) == b"abc"
    fake.CloseHandle.assert_called_once_with(71)


def test_cleanup_cancels_then_observes_before_releasing_pending_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.CancelIoEx.return_value = True
    fake.WaitForSingleObject.return_value = WAIT_OBJECT_0
    fake.GetOverlappedResult.return_value = False
    fake.CloseHandle.return_value = True
    monkeypatch.setattr(byte_stream, "native_api", lambda: fake)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 995, raising=False)
    pipe = byte_stream.OverlappedPipe(42, writable=False, maximum_read_bytes=8)
    buffer = ctypes.create_string_buffer(8)
    pending = NativePendingIO(72, Overlapped(), buffer, False, 2**63 - 1)
    pipe._pending = pending

    pipe.request_cancel()
    assert pipe._pending is pending
    assert not pending.completed
    pipe.observe_cancelled(deadline_ns=2**63 - 1)

    assert pipe._pending is None
    assert pending.completed
    fake.CancelIoEx.assert_called_once()
    fake.CloseHandle.assert_called_once_with(72)


def test_late_write_timeout_can_be_observed_during_bounded_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.CancelIoEx.return_value = True
    fake.WaitForSingleObject.side_effect = [WAIT_TIMEOUT, WAIT_OBJECT_0]
    fake.GetOverlappedResult.return_value = False
    fake.CloseHandle.return_value = True
    monkeypatch.setattr(byte_stream, "native_api", lambda: fake)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 995, raising=False)
    ticks = iter((90, 95, 150, 151, 160, 161))
    monkeypatch.setattr(time, "perf_counter_ns", lambda: next(ticks))
    pipe = byte_stream.OverlappedPipe(43, writable=True, maximum_read_bytes=8)
    pending = NativePendingIO(
        73, Overlapped(), ctypes.create_string_buffer(8), True, 100
    )
    pipe._pending = pending

    with pytest.raises(TimeoutError):
        pipe._observe(pending, deadline_ns=100)
    assert pending.late is False

    pipe.observe_cancelled(deadline_ns=200)

    assert pipe._pending is None
    assert pending.completed
    assert pending.late
    # The write timed out first (which cancelled it); cleanup then observed it.
    assert fake.WaitForSingleObject.call_count == 2
    fake.CancelIoEx.assert_called_once()
    fake.CloseHandle.assert_called_once_with(73)


def _read_three_bytes(
    _handle: int, _overlapped: object, transferred_pointer: Any, _wait: bool
) -> bool:
    pointer = ctypes.cast(transferred_pointer, ctypes.POINTER(ctypes.c_ulong))
    pointer.contents.value = 3
    return True


FAR = 2**63 - 1


def _pipe(monkeypatch: pytest.MonkeyPatch, fake: Mock, **kw: Any) -> Any:
    monkeypatch.setattr(byte_stream, "native_api", lambda: fake)
    return byte_stream.OverlappedPipe(9, writable=True, maximum_read_bytes=8, **kw)


def _pending(size: int = 8, deadline: int = FAR) -> NativePendingIO:
    return NativePendingIO(
        70, Overlapped(), ctypes.create_string_buffer(size), True, deadline
    )


def _gor(count: int, ok: bool) -> Any:
    def call(_h: int, _o: object, pointer: Any, _w: bool) -> bool:
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ulong)).contents.value = count
        return ok

    return call


def test_stop_event_ends_wait_and_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Mock()
    fake.WaitForMultipleObjects.return_value = WAIT_OBJECT_0 + 1
    fake.CancelIoEx.return_value = True
    pipe = _pipe(monkeypatch, fake, stop_event=33)
    pending = _pending()
    pipe._pending = pending
    with pytest.raises(WindowsLaunchError, match="stop"):
        pipe._observe(pending, deadline_ns=FAR)
    fake.CancelIoEx.assert_called_once()
    assert pending.cancel_requested and pipe._pending is pending
    fake.WaitForSingleObject.assert_not_called()


def test_cleanup_wait_ignores_signalled_stop_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.WaitForSingleObject.return_value = WAIT_OBJECT_0
    fake.GetOverlappedResult.side_effect = _gor(0, False)
    fake.CloseHandle.return_value = True
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 995, raising=False)
    pipe = _pipe(monkeypatch, fake, stop_event=33)
    pending = _pending()
    pending.cancel_requested = True
    pipe._pending = pending
    pipe.observe_cancelled(deadline_ns=FAR)
    assert pipe._pending is None
    fake.WaitForMultipleObjects.assert_not_called()


def test_no_stop_event_keeps_single_object_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.WaitForSingleObject.return_value = WAIT_TIMEOUT
    fake.CancelIoEx.return_value = True
    pipe = _pipe(monkeypatch, fake)
    pending = _pending()
    pipe._pending = pending
    with pytest.raises(TimeoutError):
        pipe._observe(pending, deadline_ns=FAR)
    fake.WaitForMultipleObjects.assert_not_called()


def test_cancelled_write_with_partial_bytes_retires_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.WaitForSingleObject.return_value = WAIT_OBJECT_0
    fake.GetOverlappedResult.side_effect = _gor(3, False)
    fake.CloseHandle.return_value = True
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 995, raising=False)
    pipe = _pipe(monkeypatch, fake)
    pending = _pending()
    pending.cancel_requested = True
    pipe._pending = pending
    pipe.observe_cancelled(deadline_ns=FAR)
    with pytest.raises(WindowsLaunchError, match="3 of 8 bytes"):
        pipe.write(bytearray(b"12345678"), deadline_ns=FAR)


def test_cancelled_write_with_zero_bytes_keeps_pipe_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.WaitForSingleObject.return_value = WAIT_OBJECT_0
    fake.GetOverlappedResult.side_effect = _gor(0, False)
    fake.CloseHandle.return_value = True
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 995, raising=False)
    pipe = _pipe(monkeypatch, fake)
    pending = _pending()
    pending.cancel_requested = True
    pipe._pending = pending
    pipe.observe_cancelled(deadline_ns=FAR)
    assert pipe._retired is None


def test_late_full_write_is_unconfirmed_and_retires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = Mock()
    fake.WaitForSingleObject.return_value = WAIT_OBJECT_0
    fake.GetOverlappedResult.side_effect = _gor(8, True)
    fake.CloseHandle.return_value = True
    ticks = iter((10, 11, 500, 501))
    monkeypatch.setattr(time, "perf_counter_ns", lambda: next(ticks))
    pipe = _pipe(monkeypatch, fake)
    pending = _pending(deadline=100)
    pipe._pending = pending
    with pytest.raises(TimeoutError, match="8 of 8"):
        pipe._observe(pending, deadline_ns=100)
    assert pipe._retired is not None


def test_cancel_request_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Mock()
    fake.CancelIoEx.return_value = True
    pipe = _pipe(monkeypatch, fake)
    pipe._pending = _pending()
    pipe.request_cancel()
    pipe.request_cancel()
    fake.CancelIoEx.assert_called_once()
