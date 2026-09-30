"""Pure launcher decisions: registration deadline, channel loss, backstop arming (E08).

The launcher owns only containment and exit deadlines. Win32 calls stay in
``main``; this module holds the clock- and message-driven choices so they can
be tested without Windows.
"""

from __future__ import annotations

import json

MAX_LINE_BYTES = 8192
LOST_KEY = "_lost_reason"


def parse_notification_line(line: bytes) -> dict[str, object] | str:
    """Return the notification, or the reason the line violates the protocol."""
    if not line:
        return "eof"
    if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
        return "oversized or unterminated line"
    try:
        notification = json.loads(line)
    except (UnicodeError, json.JSONDecodeError):
        return "malformed JSON"
    if not isinstance(notification, dict):
        return "notification is not an object"
    notification.pop(LOST_KEY, None)  # reserved for the reader's own marker
    return notification


class LauncherDecisions:
    """Deadline and channel state; every method takes the caller's clock reading."""

    def __init__(
        self,
        *,
        supervisor_generation: str,
        controller_generation: str,
        backstop_ns: int,
        registration_window_ns: int,
        launched_ns: int,
    ) -> None:
        self._supervisor_generation = supervisor_generation
        self._controller_generation = controller_generation
        self._backstop_ns = backstop_ns
        self._window_ns = registration_window_ns
        # Until bootstrap completes the same window bounds the supervisor itself.
        self._registration_deadline_ns = launched_ns + registration_window_ns
        self.shutdown_deadline_ns: int | None = None
        self.controller: tuple[int, int] | None = None
        self.lost_channels: dict[str, str] = {}

    def arm(self, now: int, deadline_ns: int | None = None) -> None:
        candidate = now + self._backstop_ns if deadline_ns is None else deadline_ns
        current = self.shutdown_deadline_ns
        self.shutdown_deadline_ns = (
            candidate if current is None else min(current, candidate)
        )

    def bootstrap_finished(self, now: int, *, ok: bool) -> None:
        """The supervisor plans the controller next; E08 gives that one window."""
        if not ok:
            self.arm(now)
            return
        self._registration_deadline_ns = now + self._window_ns

    def registration_expired(self, now: int) -> bool:
        return self.controller is None and now >= self._registration_deadline_ns

    def tick(self, now: int) -> None:
        if self.registration_expired(now):
            self.arm(now)  # Final bound; the supervisor's ack timeout reports it.

    def on_register_controller(
        self, now: int, note: dict[str, object]
    ) -> tuple[int, int] | None:
        """Return the (pid, creation time) to retain and acknowledge, else None."""
        if note.get("_channel") != "supervisor":
            return None
        if (
            note.get("supervisor_generation") != self._supervisor_generation
            or note.get("controller_generation") != self._controller_generation
        ):
            return None
        pid, created = note.get("pid"), note.get("creation_time_100ns")
        if type(pid) is not int or type(created) is not int:
            return None
        if self.controller is not None:
            if self.controller != (pid, created):
                self.arm(now)
            return None
        if self.registration_expired(now):
            return None  # Late registration is refused so startup fails visibly.
        return pid, created

    def controller_acknowledged(self, pid: int, created: int) -> None:
        self.controller = (pid, created)

    def on_channel_lost(self, now: int, channel: str, reason: str) -> None:
        """Supervisor loss arms the backstop; controller loss is the supervisor's."""
        self.lost_channels.setdefault(channel, reason)
        if channel == "supervisor":
            self.arm(now)

    def on_shutdown(self, now: int, note: dict[str, object]) -> None:
        channel = note.get("_channel")
        if note.get("supervisor_generation") != self._supervisor_generation:
            return
        if channel == "controller" and (
            note.get("controller_generation") != self._controller_generation
        ):
            return
        if channel not in ("supervisor", "controller"):
            return
        claimed = note.get("deadline_monotonic_ns")
        limit = now + self._backstop_ns
        self.arm(
            now,
            min(limit, claimed) if isinstance(claimed, int) and claimed > 0 else limit,
        )
