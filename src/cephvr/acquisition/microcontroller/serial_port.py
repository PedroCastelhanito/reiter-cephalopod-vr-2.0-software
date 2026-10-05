"""Narrow serial transport boundary with a lazy PySerial implementation."""

from __future__ import annotations

from typing import Protocol


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
                "pyserial is required for acquisition microcontroller control"
            ) from exc
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baud_rate,
                timeout=0.01,
                write_timeout=0.01,
            )
        except (OSError, serial.SerialException) as exc:
            raise OSError(
                f"cannot open configured microcontroller port {port}: {exc}"
            ) from exc

    def set_timeouts(self, *, read_seconds: float, write_seconds: float) -> None:
        # Windows reconfigures COM on every timeout assignment. That takes much
        # of A11's 100 ms acknowledgement budget even when no byte is read.
        # Fixed short native polls stay bounded by the channel's host deadline.
        del read_seconds, write_seconds

    def write(self, payload: bytes) -> int:
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
