"""Create and retain supervised-child pipe endpoints before ownership transfer."""

from __future__ import annotations

import ctypes
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cephvr.platform.windows.byte_stream_native import (
    ERROR_IO_PENDING,
    ERROR_NOT_FOUND,
    WAIT_OBJECT_0,
    Overlapped,
    check,
    native_api,
    wait_ms,
)
from cephvr.platform.windows.jobs import WindowsLaunchError

if TYPE_CHECKING:
    from cephvr.platform.windows.byte_stream import OverlappedPipe

PIPE_ACCESS_INBOUND = 0x00000001
PIPE_ACCESS_OUTBOUND = 0x00000002
FILE_FLAG_OVERLAPPED = 0x40000000
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
PIPE_TYPE_BYTE = 0
PIPE_READMODE_BYTE = 0
PIPE_WAIT = 0
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
HANDLE_FLAG_INHERIT = 1
EVENT_ALL_ACCESS = 0x001F0003
ERROR_PIPE_CONNECTED = 535


@dataclass
class InheritedEndpoint:
    parent: OverlappedPipe
    child_handle: int

    @property
    def inherited_handle(self) -> int:
        return self.child_handle

    def close_child_copy(self) -> None:
        if self.child_handle:
            if not native_api().CloseHandle(self.child_handle):
                raise WindowsLaunchError(
                    "closing inherited endpoint failed: "
                    f"WinError {ctypes.get_last_error()}"
                )
            self.child_handle = 0

    def close_parent(self) -> None:
        self.parent.close()


@dataclass(eq=False)
class _NativeHandle:
    value: int


@dataclass
class NativeConnect:
    server: int
    event: int
    overlapped: Overlapped


class PipeConstructionOwner:
    """Retain every partial pipe-construction handle until close is observed."""

    def __init__(self) -> None:
        self._handles: list[_NativeHandle] = []
        self._connect: NativeConnect | None = None

    def retain(self, handle: int) -> _NativeHandle:
        record = _NativeHandle(handle)
        self._handles.append(record)
        return record

    @property
    def cleanup_blocked(self) -> bool:
        return bool(self._handles) or self._connect is not None

    def transfer(self, handle: int) -> None:
        self._handles[:] = [item for item in self._handles if item.value != handle]

    def retry_cleanup(self, *, deadline_ns: int) -> None:
        api = native_api()
        pending = self._connect
        if pending is not None:
            if not api.CancelIoEx(pending.server, ctypes.byref(pending.overlapped)):
                error = ctypes.get_last_error()
                if error != ERROR_NOT_FOUND:
                    raise WindowsLaunchError(
                        f"cancelling pipe connection failed: WinError {error}"
                    )
            remaining = deadline_ns - time.perf_counter_ns()
            if (
                remaining <= 0
                or api.WaitForSingleObject(pending.event, wait_ms(remaining))
                != WAIT_OBJECT_0
            ):
                raise WindowsLaunchError(
                    "named-pipe connection remains pending; handles retained"
                )
            transferred = wintypes.DWORD()
            if not api.GetOverlappedResult(
                pending.server,
                ctypes.byref(pending.overlapped),
                ctypes.byref(transferred),
                False,
            ):
                error = ctypes.get_last_error()
                if error not in {995, ERROR_PIPE_CONNECTED}:
                    raise WindowsLaunchError(
                        f"observing pipe connection failed: WinError {error}"
                    )
            self._connect = None
        for record in tuple(self._handles):
            if not api.CloseHandle(record.value):
                raise WindowsLaunchError(
                    f"closing partial pipe handle failed: WinError {ctypes.get_last_error()}"
                )
            self._handles.remove(record)


def create_child_endpoint(
    pipe_type: type[OverlappedPipe],
    *,
    parent_writable: bool,
    owner: PipeConstructionOwner,
    deadline_ns: int,
    maximum_read_bytes: int,
) -> InheritedEndpoint:
    """Connect one overlapped named-pipe pair and transfer only parent ownership."""
    import sys

    if sys.platform != "win32":
        raise WindowsLaunchError("overlapped byte streams require Windows")
    api = native_api()
    name = rf"\\.\pipe\cephvr-{uuid.uuid4()}"
    from cephvr.platform.windows.security import (
        owner_only_inheritable_security_attributes,
        owner_only_security_attributes,
    )

    security, security_backing = owner_only_inheritable_security_attributes()
    _ = security_backing
    direction = PIPE_ACCESS_OUTBOUND if parent_writable else PIPE_ACCESS_INBOUND
    server = api.CreateNamedPipeW(
        name,
        direction | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1,
        64 * 1024,
        64 * 1024,
        0,
        ctypes.byref(security),
    )
    check(server, "CreateNamedPipeW")
    server_value = int(server)
    owner.retain(server_value)
    desired = GENERIC_READ if parent_writable else GENERIC_WRITE
    child = api.CreateFileW(
        name,
        desired,
        0,
        ctypes.byref(security),
        OPEN_EXISTING,
        0,
        None,
    )
    if child == ctypes.c_void_p(-1).value:
        raise WindowsLaunchError(
            f"CreateFileW(pipe client) failed: WinError {ctypes.get_last_error()}"
        )
    child_value = int(child)
    owner.retain(child_value)
    security, security_backing = owner_only_security_attributes(EVENT_ALL_ACCESS)
    event = api.CreateEventW(ctypes.byref(security), True, False, None)
    _ = security_backing
    check(event, "CreateEventW(named-pipe connection)")
    event_value = int(event)
    owner.retain(event_value)
    overlapped = Overlapped()
    overlapped.hEvent = event
    connected = api.ConnectNamedPipe(server, ctypes.byref(overlapped))
    if not connected:
        error = ctypes.get_last_error()
        if error == ERROR_IO_PENDING:
            owner._connect = NativeConnect(server_value, event_value, overlapped)
            remaining = deadline_ns - time.perf_counter_ns()
            if (
                remaining <= 0
                or api.WaitForSingleObject(event, wait_ms(remaining)) != WAIT_OBJECT_0
            ):
                raise TimeoutError("named-pipe connection missed its deadline")
            transferred = wintypes.DWORD()
            if not api.GetOverlappedResult(
                server, ctypes.byref(overlapped), ctypes.byref(transferred), False
            ):
                raise WindowsLaunchError(
                    "observing named-pipe connection failed: "
                    f"WinError {ctypes.get_last_error()}"
                )
            owner._connect = None
        elif error != ERROR_PIPE_CONNECTED:
            raise WindowsLaunchError(f"ConnectNamedPipe failed: WinError {error}")
    if not api.CloseHandle(event):
        raise WindowsLaunchError(
            f"closing named-pipe event failed: WinError {ctypes.get_last_error()}"
        )
    owner.transfer(event_value)
    if not api.SetHandleInformation(server, HANDLE_FLAG_INHERIT, 0):
        raise WindowsLaunchError(
            f"SetHandleInformation failed: WinError {ctypes.get_last_error()}"
        )
    owner.transfer(server_value)
    owner.transfer(child_value)
    return InheritedEndpoint(
        pipe_type(
            server_value,
            writable=parent_writable,
            maximum_read_bytes=maximum_read_bytes,
        ),
        child_value,
    )
