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
                timeout=0,
                write_timeout=0,
            )
        except (OSError, serial.SerialException) as exc:
            raise OSError(
                f"cannot open configured microcontroller port {port}: {exc}"
            ) from exc

    def set_timeouts(self, *, read_seconds: float, write_seconds: float) -> None:
        self._serial.timeout = max(0.0, read_seconds)
        self._serial.write_timeout = max(0.0, write_seconds)

    def write(self, payload: bytes) -> int:
        return int(self._serial.write(payload))

    def read(self, size: int = 1) -> bytes:
        return bytes(self._serial.read(size))

    def cancel_read(self) -> None:
        self._serial.cancel_read()

    def cancel_write(self) -> None:
        self._serial.cancel_write()

    def close(self) -> None:
        self._serial.close()
