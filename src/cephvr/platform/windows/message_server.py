"""E08 bounded message listener using shared overlapped ownership and authentication."""

from __future__ import annotations

import ctypes
import hmac
import sys
from ctypes import wintypes

from cephvr.control.v1 import native_transport_pb2 as wire
from cephvr.platform.windows.byte_stream import OverlappedPipe
from cephvr.platform.windows.byte_stream_factory import (
    NativeConnect,
    PipeConstructionOwner,
)
from cephvr.platform.windows.byte_stream_native import Overlapped, native_api, wait_ms
from cephvr.platform.windows.message_pipe import MessagePipe, _decode_handshake, _Pipe
from cephvr.platform.windows.security import owner_only_security_attributes
from cephvr.shared.clock import host_time_ns


class MessageListener:
    def __init__(self, name: str, maximum: int) -> None:
        self.owner = PipeConstructionOwner()
        self.endpoint: MessagePipe | None = None
        if sys.platform != "win32":
            raise RuntimeError("message pipe listener requires Windows")
        if (
            not name.startswith(r"\\.\pipe\cephvr-")
            or ".." in name
            or len(name) > 240
            or not 0 < maximum <= 64 * 1024 * 1024
        ):
            raise ValueError("invalid bounded local pipe descriptor")
        self.maximum = maximum
        self.api = native_api()
        security, backing = owner_only_security_attributes(0x001F01FF)
        self.security_backing = backing
        handle = self.api.CreateNamedPipeW(
            name,
            3 | 0x40000000 | 0x00080000,
            4 | 2 | 8,
            1,
            maximum,
            maximum,
            0,
            ctypes.byref(security),
        )
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = int(handle)
        self.owner.retain(self.handle)
        event_security, event_backing = owner_only_security_attributes(0x001F0003)
        event = self.api.CreateEventW(ctypes.byref(event_security), True, False, None)
        self.event_backing = event_backing
        if not event:
            raise ctypes.WinError(ctypes.get_last_error())
        self.event = int(event)
        self.owner.retain(self.event)
        pending = Overlapped()
        pending.hEvent = event
        self.pending = pending
        connected = self.api.ConnectNamedPipe(handle, ctypes.byref(pending))
        if not connected:
            error = ctypes.get_last_error()
            if error == 997:
                self.owner._connect = NativeConnect(self.handle, self.event, pending)
            elif error != 535:
                raise ctypes.WinError(error)

    def accept(self, local: str, peer: str, nonce: bytes, deadline: int) -> MessagePipe:
        if self.owner._connect is not None:
            remaining = deadline - host_time_ns()
            if (
                remaining <= 0
                or self.api.WaitForSingleObject(self.event, wait_ms(remaining)) != 0
            ):
                raise TimeoutError("feedback peer connection deadline expired")
            transferred = wintypes.DWORD()
            if not self.api.GetOverlappedResult(
                self.handle,
                ctypes.byref(self.pending),
                ctypes.byref(transferred),
                False,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            self.owner._connect = None
        if not self.api.CloseHandle(self.event):
            raise ctypes.WinError(ctypes.get_last_error())
        self.owner.transfer(self.event)
        self.endpoint = _Pipe(
            OverlappedPipe(
                self.handle,
                writable=True,
                readable=True,
                maximum_read_bytes=self.maximum,
            ),
            maximum_message_bytes=self.maximum,
        )
        self.owner.transfer(self.handle)
        challenge = wire.PipeHandshake(
            protocol_version=1, process_instance_id=local, startup_nonce=nonce
        )
        self.endpoint.send_bytes(challenge.SerializeToString(), deadline_ns=deadline)
        hello = _decode_handshake(
            self.endpoint.recv_bytes(deadline_ns=deadline), self.maximum
        )
        if (
            hello.protocol_version != 1
            or hello.process_instance_id != peer
            or hello.accepted
            or not hmac.compare_digest(hello.startup_nonce, nonce)
        ):
            raise ValueError("feedback consumer generation/nonce mismatch")
        challenge.accepted = True
        self.endpoint.send_bytes(challenge.SerializeToString(), deadline_ns=deadline)
        return self.endpoint

    def cancel(self) -> None:
        if self.endpoint is not None:
            self.endpoint.request_cancel()
        elif self.owner._connect is not None:
            self.api.CancelIoEx(self.handle, ctypes.byref(self.pending))

    def close(self, deadline: int) -> None:
        if self.endpoint is not None:
            self.endpoint.close_after_io(deadline_ns=deadline)
            self.endpoint = None
        self.owner.retry_cleanup(deadline_ns=deadline)
