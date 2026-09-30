"""Bounded single-request serial exchange and request/reply identity handling."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from .protocol import FirmwareRejected, ProtocolError, Reply, parse_reply, request_line
from .serial_port import PySerialPort, SerialPort


class ChannelError(RuntimeError):
    """A serial request failed before a valid matched reply completed."""


class ChannelDeadline(ChannelError):
    """No request was dispatched before the applicable original deadline."""


class ChannelTimeout(ChannelError):
    """A request was dispatched, but its complete reply missed its deadline."""


class ChannelTransportFailure(ChannelError):
    """A serial read, write or handle operation failed."""


class ChannelCancelled(ChannelError):
    """A request was cancelled; cancellation does not prove output state."""


@dataclass(frozen=True)
class Exchange:
    reply: Reply | None
    request_id: str
    dispatched_ns: int
    completed_ns: int | None


class SerialChannel:
    """One bounded link; callers own its thread and all lifecycle policy."""

    def __init__(
        self,
        name: str,
        baud_rate: int,
        ack_timeout_ns: int,
        *,
        clock: Callable[[], int],
        serial_port: SerialPort | None = None,
    ) -> None:
        self.name = name
        self.baud_rate = baud_rate
        self.ack_timeout_ns = ack_timeout_ns
        self.clock = clock
        self._provided_port = serial_port
        self.port: SerialPort | None = None
        self.connection_id: str | None = None
        self._counter = 0
        self.unmatched_replies = 0
        self.malformed_replies = 0
        self.last_valid_reply_ns: int | None = None
        self.last_exchange: Exchange | None = None
        self._cancel_requested = threading.Event()
        self._finished = threading.Event()
        self._finished.set()
        self._state_lock = threading.Lock()
        self._request_active = False

    def cancel_request(self) -> bool:
        """Thread-safe cancellation signal for the current blocking serial call."""
        with self._state_lock:
            if not self._request_active:
                return False
            self._cancel_requested.set()
            port = self.port
        if port is not None:
            errors: list[Exception] = []
            for cancel in (port.cancel_read, port.cancel_write):
                try:
                    cancel()
                except Exception as exc:
                    errors.append(exc)
            if errors:
                raise ChannelTransportFailure(
                    f"serial cancellation request failed: {errors[0]}"
                ) from errors[0]
        return True

    def wait_for_request_completion(self, timeout_seconds: float) -> bool:
        """Wait until the serial-owner thread has returned from its blocked I/O call."""
        return self._finished.wait(max(0.0, timeout_seconds))

    def open(self, deadline_ns: int) -> None:
        if self.clock() >= deadline_ns:
            raise ChannelDeadline("connection deadline expired before opening the port")
        try:
            self.port = self._provided_port or PySerialPort(self.name, self.baud_rate)
        except Exception as exc:
            raise ChannelTransportFailure(
                f"cannot open configured port: {exc}"
            ) from exc
        self.connection_id = str(uuid.uuid4())
        self._counter = 0

    def request(
        self,
        verb: str,
        fields: dict[str, str],
        deadline_ns: int,
        *,
        read_only: bool = False,
        dispatch_before_ns: int | None = None,
    ) -> Exchange:
        with self._state_lock:
            if self._request_active:
                raise ChannelTransportFailure(
                    "serial owner already has an outstanding request"
                )
            self._request_active = True
            self._cancel_requested.clear()
            self._finished.clear()
        try:
            return self._perform_request(
                verb,
                fields,
                deadline_ns,
                read_only=read_only,
                dispatch_before_ns=dispatch_before_ns,
            )
        finally:
            with self._state_lock:
                self._request_active = False
                self._finished.set()

    def _perform_request(
        self,
        verb: str,
        fields: dict[str, str],
        deadline_ns: int,
        *,
        read_only: bool,
        dispatch_before_ns: int | None,
    ) -> Exchange:
        if self.port is None or self.connection_id is None:
            raise ChannelTransportFailure("serial port is not open")
        now = self.clock()
        if now >= deadline_ns:
            raise ChannelDeadline("original operation deadline expired before dispatch")
        if self._counter >= (1 << 64) - 1:
            raise ChannelTransportFailure(
                "request counter exhausted; reconnect for a fresh ID namespace"
            )
        self._counter += 1
        request_id = f"{self.connection_id}-{self._counter}"
        payload = request_line(verb, request_id, fields)
        command_deadline = min(deadline_ns, now + self.ack_timeout_ns)
        dispatched = self.clock()
        if dispatched >= command_deadline:
            raise ChannelDeadline("acknowledgement deadline expired before dispatch")
        if dispatch_before_ns is not None and dispatched < dispatch_before_ns:
            raise ChannelDeadline("scheduled boundary is not due")
        if self._cancel_requested.is_set():
            raise ChannelCancelled("request cancelled before serial dispatch")
        self.port.set_timeouts(
            read_seconds=(command_deadline - dispatched) / 1e9,
            write_seconds=(command_deadline - dispatched) / 1e9,
        )
        self.last_exchange = Exchange(None, request_id, dispatched, None)
        try:
            sent = self.port.write(payload)
        except Exception as exc:
            raise ChannelTransportFailure(f"serial write failed: {exc}") from exc
        write_completed = self.clock()
        if self._cancel_requested.is_set():
            raise ChannelCancelled(
                "request cancellation completed after serial write returned"
            )
        if sent != len(payload):
            raise ChannelTransportFailure(
                "serial write did not accept the complete request"
            )
        if write_completed >= command_deadline:
            raise ChannelTimeout(
                "serial write returned after its acknowledgement deadline"
            )

        line = bytearray()
        too_long = False
        while self.clock() < command_deadline:
            remaining = max(0, command_deadline - self.clock()) / 1e9
            self.port.set_timeouts(read_seconds=remaining, write_seconds=remaining)
            try:
                byte = self.port.read(1)
            except Exception as exc:
                raise ChannelTransportFailure(f"serial read failed: {exc}") from exc
            received_ns = self.clock()
            if self._cancel_requested.is_set():
                raise ChannelCancelled(
                    "request cancellation completed after serial read returned"
                )
            if not byte:
                if received_ns >= command_deadline:
                    break
                continue
            if received_ns >= command_deadline:
                break
            if byte == b"\n":
                if too_long:
                    self.malformed_replies += 1
                    line.clear()
                    too_long = False
                    continue
                line.append(byte[0])
                try:
                    reply = parse_reply(bytes(line))
                except ProtocolError:
                    self.malformed_replies += 1
                    line.clear()
                    continue
                line.clear()
                if reply.request_id != request_id:
                    self.unmatched_replies += 1
                    continue
                completed = received_ns
                if completed >= command_deadline:
                    break
                exchange = Exchange(reply, request_id, dispatched, completed)
                self.last_exchange = exchange
                if not reply.ok:
                    raise FirmwareRejected(reply.error_code or "UNKNOWN_ERROR")
                self.last_valid_reply_ns = completed
                return exchange
            if len(line) + 1 > 512:
                too_long = True
            elif not too_long:
                line.append(byte[0])
        if read_only:
            exchange = Exchange(None, request_id, dispatched, None)
            self.last_exchange = exchange
            return exchange
        raise ChannelTimeout(
            f"no matched complete acknowledgement for {verb} before deadline"
        )

    def probe(self, verb: str, deadline_ns: int) -> Exchange:
        """Retry a read-only startup probe with a fresh ID inside its original deadline."""
        if verb not in ("CAPS", "STATUS"):
            raise ValueError("only read-only CAPS and STATUS probes may be retried")
        last_error: BaseException | None = None
        while self.clock() < deadline_ns:
            try:
                result = self.request(verb, {}, deadline_ns, read_only=True)
            except ChannelCancelled:
                raise
            except FirmwareRejected as exc:
                raise ChannelTransportFailure(
                    f"MCU rejected startup {verb}: {exc.code}"
                ) from exc
            except (ChannelError, ProtocolError) as exc:
                last_error = exc
                continue
            if result.reply is not None:
                return result
        detail = f": {last_error}" if last_error else ""
        raise ChannelTimeout(
            f"no valid {verb} response before original deadline{detail}"
        )

    def close(self) -> None:
        """Close the handle; propagate failure so the caller retains cleanup evidence."""
        if self.port is not None:
            self.port.close()
            self.port = None
        self.connection_id = None
        self.last_valid_reply_ns = None
