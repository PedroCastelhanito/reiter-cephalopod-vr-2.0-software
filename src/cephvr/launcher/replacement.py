"""Owner-confirmed replacement through the existing containment owner (E08)."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID, uuid4

from cephvr.platform.windows.events import AutoResetEvent, event_name
from cephvr.platform.windows.guard import InstanceAlreadyRunning, SingleInstanceGuard
from cephvr.platform.windows.jobs import WindowsLaunchError
from cephvr.shared.clock import host_time_ns, require_int64_ns
from cephvr.shared.credentials import _check_private, _ensure_directory
from cephvr.shared.identity import require_uuid4
from cephvr.shared.recovery import RecoveryStore, _publish, _read


class ReplacementDeclined(WindowsLaunchError):
    """The operator left the existing application running."""


@dataclass(frozen=True)
class LauncherEndpoint:
    controller_generation: str
    supervisor_generation: str
    event_id: str
    replacement_timeout_ns: int
    gui_relaunch_event_id: str = ""

    def __post_init__(self) -> None:
        for generation in (
            self.controller_generation,
            self.supervisor_generation,
            self.event_id,
        ):
            require_uuid4(generation)
        require_int64_ns(self.replacement_timeout_ns)
        if self.replacement_timeout_ns <= 0:
            raise ValueError("replacement timeout must be positive")
        if self.gui_relaunch_event_id:
            require_uuid4(self.gui_relaunch_event_id)


class ReplacementEndpoint:
    """Publish a private stop event while holding the application guard."""

    def __init__(
        self,
        root: Path,
        controller_generation: str,
        supervisor_generation: str,
        timeout_ns: int,
    ) -> None:
        self.root = root
        self.record = LauncherEndpoint(
            controller_generation,
            supervisor_generation,
            str(uuid4()),
            timeout_ns,
            str(uuid4()),
        )
        self.event: AutoResetEvent | None = None
        self.gui_relaunch_event: AutoResetEvent | None = None

    def __enter__(self) -> ReplacementEndpoint:
        _ensure_directory(self.root)
        self.event = AutoResetEvent.create(UUID(self.record.event_id))
        try:
            self.gui_relaunch_event = AutoResetEvent.create(
                UUID(self.record.gui_relaunch_event_id)
            )
            path = self.root / "launcher.json"
            if _read(path) is not None:
                # A crashed prior owner can leave a private descriptor, not authority.
                path.unlink()
            _publish(
                self.root / "launcher.json", json.dumps(asdict(self.record)).encode()
            )
        except BaseException:
            if self.gui_relaunch_event is not None:
                self.gui_relaunch_event.close()
            self.event.close()
            raise
        return self

    def requested(self) -> bool:
        assert self.event is not None
        return self.event.wait(0)

    def gui_relaunch_requested(self) -> bool:
        assert self.gui_relaunch_event is not None
        return self.gui_relaunch_event.wait(0)

    def __exit__(self, *_: object) -> None:
        assert self.event is not None
        try:
            # Still under the guard: a successor cannot have published its endpoint.
            (self.root / "launcher.json").unlink(missing_ok=True)
        finally:
            self.event.close()
            if self.gui_relaunch_event is not None:
                self.gui_relaunch_event.close()


def _existing_endpoint(root: Path) -> LauncherEndpoint:
    _check_private(root, directory=True)
    raw = _read(root / "launcher.json")
    if raw is None:
        raise WindowsLaunchError(
            "Existing runtime has no replacement endpoint. Stop it from its own "
            "terminal or controller before launching this version."
        )
    expected = set(LauncherEndpoint.__dataclass_fields__)
    if set(raw) not in (expected, expected - {"gui_relaunch_event_id"}):
        raise WindowsLaunchError("existing launcher endpoint has invalid fields")
    return LauncherEndpoint(**raw)  # type: ignore[arg-type]


def request_gui_relaunch(root: Path) -> None:
    """Signal the exact running launcher without touching its application job."""
    record = _existing_endpoint(root)
    if not record.gui_relaunch_event_id:
        raise WindowsLaunchError("running launcher does not support GUI relaunch")
    allocation = UUID(record.gui_relaunch_event_id)
    with AutoResetEvent.open(event_name(allocation), allocation) as event:
        event.set()


def acquire_application_guard(root: Path) -> SingleInstanceGuard:
    """Ask once, signal the retained old owner, and require exact exit proof."""
    try:
        return SingleInstanceGuard("application")
    except InstanceAlreadyRunning:
        pass
    if not sys.stdin.isatty():
        raise ReplacementDeclined(
            "CephVR2 is already running. Open an interactive terminal to replace it."
        )
    record = _existing_endpoint(root)
    allocation = UUID(record.event_id)
    # Retain the exact event before asking; a successor never shares this identity.
    with AutoResetEvent.open(event_name(allocation), allocation) as event:
        while True:
            try:
                answer = (
                    input(
                        "CephVR2 is already running. Kill the existing runtime and start "
                        "this one? Unsaved work may be lost. [Y/N]: "
                    )
                    .strip()
                    .lower()
                )
            except EOFError:
                answer = "n"
            if answer in {"y", "n"}:
                break
            print("Please enter Y or N.")
        if answer == "n":
            raise ReplacementDeclined("Existing runtime left running.")
        event.set()
        print("Stopping the existing runtime; waiting for confirmed process exit…")
        deadline = host_time_ns() + record.replacement_timeout_ns
        recovery = RecoveryStore(root)
        while host_time_ns() < deadline:
            receipt = recovery.read_exit_receipt(record.controller_generation)
            if receipt is not None:
                if receipt.supervisor_generation != record.supervisor_generation:
                    raise WindowsLaunchError(
                        "replacement exit receipt generation mismatch"
                    )
                try:
                    return SingleInstanceGuard("application")
                except InstanceAlreadyRunning:
                    pass
            time.sleep(0.05)
    raise WindowsLaunchError(
        "Existing runtime exit could not be confirmed within its shutdown budget; "
        "the requested runtime was not started."
    )
