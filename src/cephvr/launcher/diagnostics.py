"""Best-effort launcher evidence, separate from authoritative exit receipts."""

from __future__ import annotations

import faulthandler
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TextIO

from cephvr.shared.clock import host_time_ns
from cephvr.shared.credentials import _ensure_directory
from cephvr.shared.identity import require_uuid4
from cephvr.shared.recovery import _publish


class LauncherDiagnostics:
    """Flush sparse lifecycle records; diagnostic failures never change cleanup."""

    def __init__(self, root: Path, controller: str, supervisor: str) -> None:
        self.controller = require_uuid4(controller)
        self.supervisor = require_uuid4(supervisor)
        self.path = root / "diagnostics" / f"launcher-{self.controller}.log"
        self.stream: TextIO | None = None
        self.owns_fault_handler = False

    def __enter__(self) -> LauncherDiagnostics:
        try:
            _ensure_directory(self.path.parent)
            _publish(self.path, b"")
            self.stream = self.path.open("a", encoding="utf-8")
            # Preserve a handler installed by the embedding interpreter/debugger.
            if not faulthandler.is_enabled():
                faulthandler.enable(file=self.stream, all_threads=True)
                self.owns_fault_handler = True
        except (OSError, RuntimeError, ValueError) as exc:
            self._warn(exc)
        self.record(
            "launcher_started",
            pid=os.getpid(),
            parent_pid=os.getppid(),
            controller_generation=self.controller,
            supervisor_generation=self.supervisor,
            native_faults_to_log=self.owns_fault_handler,
        )
        return self

    @staticmethod
    def _warn(exc: BaseException) -> None:
        try:
            print(f"Launcher diagnostics unavailable: {exc}", file=sys.stderr)
        except (OSError, ValueError):
            pass

    def record(self, event: str, **details: object) -> None:
        if self.stream is None:
            return
        try:
            self.stream.write(
                json.dumps(
                    {
                        "utc": datetime.now(UTC).isoformat(),
                        "monotonic_ns": host_time_ns(),
                        "event": event,
                        **details,
                    }
                )
                + "\n"
            )
            self.stream.flush()
        except (OSError, ValueError) as exc:
            self._warn(exc)

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.record(
            "launcher_exit", outcome="exception" if error is not None else "returned"
        )
        try:
            if self.stream is not None and error is not None:
                traceback.print_exception(kind, error, trace, file=self.stream)
                self.stream.flush()
        except (OSError, ValueError) as exc:
            self._warn(exc)
        finally:
            if self.owns_fault_handler:
                faulthandler.disable()
            if self.stream is not None:
                try:
                    self.stream.close()
                except OSError as exc:
                    self._warn(exc)
