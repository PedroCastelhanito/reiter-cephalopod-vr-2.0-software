"""Bounded authenticated message-mode named pipes for E08 transports."""

from __future__ import annotations

import ctypes
import hmac
import sys
from collections.abc import Callable
from ctypes import wintypes
from typing import Any, Literal, Protocol

from cephvr.control.v1 import native_transport_pb2 as handshake_pb
from cephvr.platform.windows.byte_stream import OverlappedPipe
from cephvr.platform.windows.byte_stream_native import native_api
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import host_time_ns

PIPE_READMODE_MESSAGE = 0x00000002
FILE_FLAG_OVERLAPPED = 0x40000000
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
ERROR_PIPE_BUSY = 231


class MessagePipe(Protocol):
    def send_bytes(self, payload: bytes, *, deadline_ns: int) -> None: ...
    def recv_bytes(self, *, deadline_ns: int) -> bytes: ...
    def request_cancel(self) -> None: ...
    def close_after_io(self, *, deadline_ns: int) -> None: ...


class _Pipe:
    """One message per native pipe message; no stream framing or reassembly."""

    def __init__(self, endpoint: OverlappedPipe, *, maximum_message_bytes: int) -> None:
        self._endpoint = endpoint
        self.maximum_message_bytes = maximum_message_bytes

    def send_bytes(self, payload: bytes, *, deadline_ns: int) -> None:
        if not payload or len(payload) > self.maximum_message_bytes:
            raise ValueError("pipe message is empty or exceeds its prepared bound")
        self._endpoint.write_message(
            memoryview(bytearray(payload)), deadline_ns=deadline_ns
        )

    def recv_bytes(self, *, deadline_ns: int) -> bytes:
        payload = self._endpoint.read(deadline_ns=deadline_ns)
        if payload is None:
            raise EOFError("named-pipe peer closed")
        if len(payload) > self.maximum_message_bytes:
            raise ValueError("pipe message exceeds its prepared bound")
        return payload

    def request_cancel(self) -> None:
        self._endpoint.request_cancel()

    def close_after_io(self, *, deadline_ns: int) -> None:
        self._endpoint.observe_cancelled(deadline_ns=deadline_ns)
        self._endpoint.close()


def open_message_pipe(
    key: Any,
    *,
    name: str,
    role: Literal["server", "client"],
    expected_peer_instance_id: str,
    startup_nonce: bytes,
    maximum_message_bytes: int,
    deadline_ns: int,
    _api: Any | None = None,
    _pipe_factory: Callable[..., MessagePipe] | None = None,
) -> MessagePipe:
    """Open one message pipe and authenticate the exact process-instance nonce.

    Visual Stimulus feedback uses role=client. Private injected Win32/pipe adapters exist only to
    test path validation and the handshake without claiming Windows execution here.
    """
    if role != "client":
        raise ValueError("this consumer connector supports the client role only")
    if (
        not isinstance(name, str)
        or not name.startswith(r"\\.\pipe\cephvr-")
        or len(name) > 240
        or ".." in name
    ):
        raise ValueError("named-pipe path is outside the local CephVR pipe namespace")
    local_id = getattr(key, "owner_process_instance_id", "")
    if (
        not local_id
        or not expected_peer_instance_id
        or expected_peer_instance_id == local_id
    ):
        raise ValueError(
            "distinct local and registered peer process identities are required"
        )
    if not startup_nonce or len(startup_nonce) > 64:
        raise ValueError("bounded startup nonce is required")
    if maximum_message_bytes <= 0 or maximum_message_bytes > 64 * 1024 * 1024:
        raise ValueError("maximum message size is outside supported bounds")
    if deadline_ns <= host_time_ns():
        raise TimeoutError("named-pipe connection deadline has expired")
    if sys.platform != "win32" and _api is None:
        raise WindowsLaunchError(
            "Windows message pipes are unavailable on this platform"
        )

    api = _api if _api is not None else native_api()
    handle = _connect(api, name, deadline_ns)
    try:
        mode = wintypes.DWORD(PIPE_READMODE_MESSAGE)
        if not api.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
            raise WindowsLaunchError(
                f"SetNamedPipeHandleState failed: {ctypes.get_last_error()}"
            )
        factory = _pipe_factory or _Pipe
        endpoint = factory(
            OverlappedPipe(
                int(handle),
                writable=True,
                readable=True,
                maximum_read_bytes=maximum_message_bytes,
            ),
            maximum_message_bytes=maximum_message_bytes,
        )
        _authenticate_client(
            endpoint,
            local_id=local_id,
            expected_peer_id=expected_peer_instance_id,
            nonce=startup_nonce,
            deadline_ns=deadline_ns,
            maximum_message_bytes=maximum_message_bytes,
        )
        return endpoint
    except BaseException:
        api.CloseHandle(handle)
        raise


def _connect(api: Any, name: str, deadline_ns: int) -> int:
    while True:
        if host_time_ns() >= deadline_ns:
            raise TimeoutError("named-pipe connection deadline expired")
        handle = api.CreateFileW(
            name,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            None,
        )
        if handle and handle != ctypes.c_void_p(-1).value:
            return int(handle)
        error = ctypes.get_last_error()
        if error != ERROR_PIPE_BUSY:
            raise WindowsLaunchError(f"opening named pipe failed: WinError {error}")
        remaining_ms = max(1, min((deadline_ns - host_time_ns()) // 1_000_000, 100))
        if not api.WaitNamedPipeW(name, int(remaining_ms)):
            error = ctypes.get_last_error()
            if error != ERROR_PIPE_BUSY:
                raise WindowsLaunchError(
                    f"waiting for named pipe failed: WinError {error}"
                )


def _authenticate_client(
    pipe: MessagePipe,
    *,
    local_id: str,
    expected_peer_id: str,
    nonce: bytes,
    deadline_ns: int,
    maximum_message_bytes: int,
) -> None:
    challenge = _decode_handshake(
        pipe.recv_bytes(deadline_ns=deadline_ns), maximum_message_bytes
    )
    if (
        challenge.protocol_version != 1
        or challenge.process_instance_id != expected_peer_id
        or not hmac.compare_digest(challenge.startup_nonce, nonce)
        or challenge.accepted
    ):
        raise WindowsLaunchError("named-pipe server identity or startup nonce mismatch")
    hello = handshake_pb.PipeHandshake(
        protocol_version=1,
        process_instance_id=local_id,
        startup_nonce=nonce,
    )
    pipe.send_bytes(
        hello.SerializeToString(deterministic=True), deadline_ns=deadline_ns
    )
    accepted = _decode_handshake(
        pipe.recv_bytes(deadline_ns=deadline_ns), maximum_message_bytes
    )
    if (
        accepted.protocol_version != 1
        or accepted.process_instance_id != expected_peer_id
        or not hmac.compare_digest(accepted.startup_nonce, nonce)
        or not accepted.accepted
    ):
        raise WindowsLaunchError("named-pipe peer rejected exact attachment identity")


def _decode_handshake(
    payload: bytes, maximum_message_bytes: int
) -> handshake_pb.PipeHandshake:
    if not payload or len(payload) > maximum_message_bytes:
        raise ValueError("handshake is empty or exceeds the pipe message bound")
    message = handshake_pb.PipeHandshake()
    try:
        message.ParseFromString(payload)
    except Exception as exc:
        raise ValueError("named-pipe peer sent malformed handshake protobuf") from exc
    if not message.process_instance_id or not message.startup_nonce:
        raise ValueError("named-pipe handshake omitted its process identity or nonce")
    return message
