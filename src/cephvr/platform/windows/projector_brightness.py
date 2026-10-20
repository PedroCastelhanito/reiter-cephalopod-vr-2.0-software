"""Registered one-shot TI SDK invocation with exact native cleanup."""

import json
import os
import sys
import threading
from pathlib import Path
from typing import Protocol

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.encoder_process import WindowsEncoderProcess
from cephvr.shared.native_helper_identity import PROJECTOR_BRIGHTNESS_ROLE
from cephvr.shared.native_helpers import release_native_helper
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher

RESULT_PREFIX = "CEPHVR_BRIGHTNESS_RESULT="


def _diagnostics(process: WindowsEncoderProcess) -> str:
    lines = [
        line
        for line in process.stdout_text.splitlines()
        if not line.startswith(RESULT_PREFIX)
    ]
    return "\n".join([*lines, *process.diagnostic_tail])[-6000:]


class BrightnessPort(Protocol):
    result: dict[str, object] | None
    diagnostics: str

    @property
    def cleanup_complete(self) -> bool: ...

    def adjust(
        self, current_ma: int, operation: control.OperationContext, *, deadline_ns: int
    ) -> None: ...

    def cancel(self) -> None: ...

    def reset_cancel(self) -> None: ...


def brightness_command(current_ma: int) -> list[str]:
    if not 101 <= current_ma <= 2500:
        raise ValueError("Projector LED current must be between 101 and 2500 mA")
    if sys.platform != "win32":
        raise RuntimeError(
            "Projector brightness requires Windows and the TI DLP EVM SDK"
        )
    executable = (
        Path(os.environ["WINDIR"]) / "SysWOW64/WindowsPowerShell/v1.0/powershell.exe"
    )
    return [
        str(executable),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(__file__).with_suffix(".ps1")),
        "-Current",
        str(current_ma),
    ]


def brightness_result(output: str, current_ma: int) -> dict[str, object]:
    """Reject missing, malformed or incomplete machine evidence."""
    lines = [
        line[len(RESULT_PREFIX) :]
        for line in output.splitlines()
        if line.startswith(RESULT_PREFIX)
    ]
    if len(lines) != 1:
        raise ValueError("Projector helper did not return one structured result")
    result = json.loads(lines[0])
    if (
        not isinstance(result, dict)
        or type(result.get("schema_version")) is not int
        or result.get("schema_version") != 1
        or type(result.get("requested_ma")) is not int
        or result.get("requested_ma") != current_ma
    ):
        raise ValueError("Projector helper result identity/version is invalid")
    entries = result.get("interfaces")
    count = result.get("discovered_interfaces")
    if (
        type(count) is not int
        or not 1 <= count <= 64
        or not isinstance(entries, list)
        or len(entries) != count
        or type(result.get("success")) is not bool
    ):
        raise ValueError("Projector helper interface accounting is incomplete")
    all_confirmed = True
    for index, entry in enumerate(entries):
        if (
            not isinstance(entry, dict)
            or type(entry.get("index")) is not int
            or entry.get("index") != index
        ):
            raise ValueError("Projector helper interface identity is invalid")
        if any(
            not isinstance(entry.get(key), str) or len(entry[key]) > 2048
            for key in ("name", "id", "error")
        ):
            raise ValueError("Projector helper interface text is invalid")
        if any(
            type(entry.get(key)) is not bool
            for key in ("confirmed", "release_confirmed")
        ):
            raise ValueError("Projector helper confirmation is invalid")
        rgb = entry.get("readback_ma")
        if rgb is not None and (
            not isinstance(rgb, dict)
            or set(rgb) != {"red", "green", "blue"}
            or any(type(v) is not int or not 0 <= v <= 65535 for v in rgb.values())
        ):
            raise ValueError("Projector helper RGB readback is invalid")
        if entry["confirmed"]:
            clamped = current_ma > 1023 and rgb == dict.fromkeys(
                ("red", "green", "blue"), 1023
            )
            if (
                not rgb
                or (
                    not clamped
                    and rgb != dict.fromkeys(("red", "green", "blue"), current_ma)
                )
                or entry.get("clamped") is not clamped
            ):
                raise ValueError(
                    "Projector helper confirmation differs from RGB readback"
                )
        elif entry.get("clamped") is not None:
            raise ValueError(
                "Unconfirmed projector cannot have a confirmed clamp state"
            )
        all_confirmed &= entry["confirmed"] and entry["release_confirmed"]
    if result["success"] != all_confirmed:
        raise ValueError(
            "Projector helper overall result contradicts interface evidence"
        )
    return result


class WindowsProjectorBrightness:
    """Own one registered adjustment and retain uncertain launches as blockers."""

    def __init__(self, launcher: SupervisedEncoderLauncher) -> None:
        self.launcher = launcher
        self.result: dict[str, object] | None = None
        self.diagnostics = ""
        self._cancel = threading.Event()
        self._process: WindowsEncoderProcess | None = None
        self._plans: dict[str, wire.PlanLaunchRequest] = {}
        self._release_commands: dict[str, str] = {}
        launcher.registered_plan = lambda plan: self._plans.__setitem__(
            plan.command_id, plan
        )

    @property
    def cleanup_complete(self) -> bool:
        return not (self._process or self._plans or self.launcher.pending_plans)

    def adjust(
        self, current_ma: int, operation: control.OperationContext, *, deadline_ns: int
    ) -> None:
        if not self.cleanup_complete:
            raise RuntimeError("Previous projector native cleanup is unconfirmed")
        if self._cancel.is_set():
            raise RuntimeError("Projector adjustment cancelled before native launch")
        self.result, self.diagnostics = None, ""
        try:
            self.launcher.bind_operation(control.WorkContext(), operation)
            self._process = self.launcher.launch(
                brightness_command(current_ma),
                deadline_ns=deadline_ns,
                role=PROJECTOR_BRIGHTNESS_ROLE,
                capture_stdout=True,
            )
            process = self._process
            process.close_stdin(deadline_ns=deadline_ns)
            while self.launcher.windows_jobs.process_running(
                process.child.pid, process.child.creation_time_100ns
            ):
                if self._cancel.wait(0.02):
                    raise RuntimeError(
                        "Projector adjustment cancelled; hardware state unconfirmed"
                    )
                if self.launcher.clock_ns() >= deadline_ns - 2_000_000_000:
                    raise TimeoutError(
                        "Projector adjustment exceeded its original operation budget"
                    )
            code = process.wait(deadline_ns=deadline_ns)
            self.diagnostics = _diagnostics(process)
            self.result = brightness_result(process.stdout_text, current_ma)
            if code or not self.result["success"]:
                raise RuntimeError(
                    self.diagnostics or "TI projector SDK command failed"
                )
        finally:
            self.close(deadline_ns=deadline_ns)

    def cancel(self) -> None:
        self._cancel.set()

    def reset_cancel(self) -> None:
        if not self.cleanup_complete:
            raise RuntimeError("Previous projector native cleanup is unconfirmed")
        self.result, self.diagnostics = None, ""
        self._cancel.clear()

    def close(self, *, deadline_ns: int) -> None:
        process = self._process
        if process is not None:
            if not process.cleanup_complete:
                self.launcher.windows_jobs.terminate_job(process.job_name)
                process.close_stdin(deadline_ns=deadline_ns)
                process.wait(deadline_ns=deadline_ns)
            self.diagnostics = _diagnostics(process)
        for plan in self.launcher.pending_plans:
            self._plans[plan.command_id] = plan
        self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
        for launch_id in tuple(self._plans):
            release_native_helper(
                self.launcher,
                self._plans[launch_id],
                process,
                self._release_commands,
                deadline_ns=deadline_ns,
            )
            self._plans.pop(launch_id)
            self._release_commands.pop(launch_id, None)
        self._process = None
