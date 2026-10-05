"""Exclusive, bounded serial diagnostics for the local rig review window."""

from __future__ import annotations

import asyncio
import queue
import re
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from cephvr.acquisition.config.file_policies import load_file_policies
from cephvr.acquisition.microcontroller.bridge import SerialOwnerBridge
from cephvr.acquisition.microcontroller.owner import SerialOwner
from cephvr.acquisition.microcontroller.serial_port import PySerialPort
from cephvr.acquisition.v1.microcontroller_pb2 import MicrocontrollerObservation
from cephvr.shared.clock import host_time_ns

_ROOT = Path(__file__).resolve().parents[3]
_KINDS = {"trial-state": "trial_state", "projector-flip": "projector_flip"}


class ReviewMcu(QThread):
    """Keep the local diagnostic's serial owner outside the Qt UI thread."""

    connection_result = pyqtSignal(bool, str)
    diagnostic_result = pyqtSignal(str, bool, int)
    command_failed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._requests: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._bridge: SerialOwnerBridge | None = None
        self._port = ""
        self._active_key = ""
        self._expiry: asyncio.Task[None] | None = None

    def request(self, action: str, **options: Any) -> None:
        self._requests.put((action, options))

    def shutdown(self) -> None:
        if self.isRunning():
            self.request("quit")
            self.wait(5000)

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        try:
            while True:
                action, options = await asyncio.to_thread(self._requests.get)
                if action == "quit":
                    break
                key = str(options.get("key", action))
                try:
                    if action == "connect":
                        observation = await self._connect(str(options["port"]))
                        self._emit_connection(observation)
                    elif action == "start":
                        await self._start(options)
                    elif action == "stop":
                        await self._stop(key)
                    elif action == "status" and key == self._active_key:
                        await self._status(key)
                except Exception as exc:
                    if action == "connect":
                        self.connection_result.emit(False, f"Connection failed: {exc}")
                    else:
                        self.command_failed.emit(key, str(exc))
                    if action in {"connect", "start"} and not self._active_key:
                        await self._close()
        finally:
            if self._expiry is not None:
                self._expiry.cancel()
            if self._active_key and self._bridge is not None:
                try:
                    await self._bridge.diagnostic_stop(deadline_ns=_deadline())
                except Exception as exc:
                    self.command_failed.emit(
                        self._active_key, f"Stop unconfirmed on close: {exc}"
                    )
            await self._close()

    async def _connect(self, port: str) -> MicrocontrollerObservation:
        if not re.fullmatch(r"COM[1-9][0-9]*", port):
            raise ValueError("Select a Windows COM port")
        if self._bridge is not None and port == self._port:
            return await self._bridge.status(deadline_ns=_deadline())
        await self._close()
        policies = load_file_policies(_ROOT)
        self._bridge = SerialOwnerBridge(
            lambda: SerialOwner(
                port,
                policies,
                serial_port=PySerialPort(port, policies.serial_baud_rate),
            )
        )
        self._port = port
        return await self._bridge.connect(deadline_ns=host_time_ns() + 4_000_000_000)

    async def _start(self, options: dict[str, Any]) -> None:
        key = str(options["key"])
        if self._active_key:
            raise ValueError("Another pin diagnostic is active")
        pin = str(options["pin"]).strip().upper()
        if re.fullmatch(r"[0-9]+", pin):
            pin = f"D{pin}"
        if not re.fullmatch(r"D(?:[2-9]|1[0-3])", pin):
            raise ValueError("Use an Arduino Uno pin D2–D13")
        role = str(options.get("role", "")).lower()
        kind = _KINDS.get(
            key,
            "behavioral"
            if role == "behavior cam"
            else "tracking"
            if role == "tracking cam"
            else role,
        )
        if kind not in {"trial_state", "projector_flip", "behavioral", "tracking"}:
            raise ValueError("Unknown diagnostic signal")
        observation = await self._connect(str(options["port"]))
        self._emit_connection(observation)
        assert self._bridge is not None
        active, _, _, edges = await self._bridge.diagnostic_start(
            kind,
            pin,
            frequency_hz=options.get("frequency_hz"),
            deadline_ns=_deadline(),
        )
        self._active_key = key if active else ""
        self.diagnostic_result.emit(key, active, edges)
        if active:
            self._expiry = asyncio.create_task(self._after_expiry(key))

    async def _after_expiry(self, key: str) -> None:
        await asyncio.sleep(2.2)
        self.request("status", key=key)

    async def _status(self, key: str) -> None:
        assert self._bridge is not None
        active, _, _, edges = await self._bridge.diagnostic_status(
            deadline_ns=_deadline()
        )
        self._active_key = key if active else ""
        self.diagnostic_result.emit(key, active, edges)

    async def _stop(self, key: str) -> None:
        if key != self._active_key or self._bridge is None:
            return
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        active, _, _, edges = await self._bridge.diagnostic_stop(
            deadline_ns=_deadline()
        )
        self._active_key = key if active else ""
        self.diagnostic_result.emit(key, active, edges)

    async def _close(self) -> None:
        bridge, self._bridge = self._bridge, None
        self._port = ""
        if bridge is not None:
            try:
                await bridge.close(deadline_ns=host_time_ns() + 2_000_000_000)
            except Exception as exc:
                self.command_failed.emit("connection", f"Port close unconfirmed: {exc}")

    def _emit_connection(self, observation: MicrocontrollerObservation) -> None:
        self.connection_result.emit(
            True,
            f"{observation.port}: {observation.capabilities.firmware}, "
            f"protocol {observation.capabilities.protocol_version}; "
            "outputs stopped. Pin test still required.",
        )


def _deadline() -> int:
    return host_time_ns() + 1_000_000_000
