"""Backend-neutral registered-process capability probe lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProbeResult:
    returncode: int
    stdout: str
    stderr: str


class ProbeProcess(Protocol):
    stdout_text: str
    diagnostic_tail: tuple[str, ...]

    def close_stdin(self, *, deadline_ns: int) -> None: ...
    def wait(self, *, deadline_ns: int) -> int: ...
    def terminate(self, *, deadline_ns: int) -> None: ...


class ProbeLauncher(Protocol):
    def bind_operation(self, work: object, parent_operation: object) -> None: ...
    def launch(
        self,
        argv: Sequence[str],
        *,
        deadline_ns: int,
        role: str,
        output_path: None,
        capture_stdout: bool,
    ) -> ProbeProcess: ...
    def terminate_unconfirmed(self, *, deadline_ns: int) -> None: ...


class RegisteredCapabilityProbe:
    """Run bounded help commands as children of the retained supervisor plan."""

    def __init__(
        self,
        launcher: Any,
        work: Any,
        parent_operation: Any,
        resource_released: Callable[[str, bool], None],
        *,
        role: str,
    ) -> None:
        self.launcher = launcher
        self.work = work
        self.parent_operation = parent_operation
        self.resource_released = resource_released
        self.role = role
        self._unresolved: list[ProbeProcess] = []

    def run(
        self, executable: str, args: Sequence[str], *, deadline_ns: int
    ) -> ProbeResult:
        if self._unresolved:
            raise RuntimeError("prior capability helper cleanup remains unresolved")
        self.launcher.bind_operation(self.work, self.parent_operation)
        try:
            process = self.launcher.launch(
                (executable, *args),
                deadline_ns=deadline_ns,
                role=self.role,
                output_path=None,
                capture_stdout=True,
            )
        except BaseException:
            self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
            raise
        self._unresolved.append(process)
        process.close_stdin(deadline_ns=deadline_ns)
        exit_code = process.wait(deadline_ns=deadline_ns)
        result = ProbeResult(
            exit_code, process.stdout_text, "\n".join(process.diagnostic_tail)
        )
        self.resource_released(
            f"ffmpeg:{getattr(process, 'launch_id', 'registered-child')}", True
        )
        self._unresolved.remove(process)
        return result

    def retry_cleanup(self, *, deadline_ns: int) -> None:
        self.launcher.terminate_unconfirmed(deadline_ns=deadline_ns)
        for process in tuple(self._unresolved):
            process.terminate(deadline_ns=deadline_ns)
            self.resource_released(
                f"ffmpeg:{getattr(process, 'launch_id', 'registered-child')}", True
            )
            self._unresolved.remove(process)
