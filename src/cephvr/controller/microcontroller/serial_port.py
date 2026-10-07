"""Narrow serial transport boundary with a lazy PySerial implementation."""

from __future__ import annotations

from typing import Protocol

from cephvr.platform.windows.serial_timeouts import set_write_timeout
from cephvr.shared.clock import host_time_ns


class SerialPort(Protocol):
    def set_timeouts(self, *, read_seconds: float, write_seconds: float) -> None: ...

    def write(self, payload: bytes) -> int: ...

    def read(self, size: int = 1) -> bytes: ...

    def cancel_read(self) -> None: ...

    def cancel_write(self) -> None: ...

    def close(self) -> None: ...


class PySerialPort:
    """PySerial adapter; importing the optional driver happens only on use."""

    def __init__(self, port: str, baud_rate: int):
        try:
            import serial  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required for Microcontroller device control"
            ) from exc
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baud_rate,
                timeout=0.01,
                write_timeout=0.01,
            )
            self._write_deadline_ns = 0
        except (OSError, serial.SerialException) as exc:
            raise OSError(
                f"cannot open configured microcontroller port {port}: {exc}"
            ) from exc

    def set_timeouts(self, *, read_seconds: float, write_seconds: float) -> None:
        # Windows reconfigures COM on every timeout assignment. That takes much
        # of A11's 100 ms acknowledgement budget even when no byte is read.
        # Keep short read polls, but a complete request may take longer than 10 ms
        # to transmit. Apply its original remaining budget only at write dispatch.
        del read_seconds
        self._write_deadline_ns = host_time_ns() + int(write_seconds * 1e9)

    def write(self, payload: bytes) -> int:
        remaining = (self._write_deadline_ns - host_time_ns()) / 1e9
        if remaining <= 0:
            raise TimeoutError("serial write budget expired before dispatch")
        # PySerial's setter also repeats SetCommState/DTR configuration. Update
        # only COMMTIMEOUTS on the pinned Windows driver's owned handle instead.
        set_write_timeout(self._serial._port_handle, remaining)
        return int(self._serial.write(payload))

    def read(self, size: int = 1) -> bytes:
        if size > 1:
            return bytes(self._serial.read_until(b"\n", size))
        return bytes(self._serial.read(size))

    def cancel_read(self) -> None:
        self._serial.cancel_read()

    def cancel_write(self) -> None:
        self._serial.cancel_write()

    def close(self) -> None:
        self._serial.close()
