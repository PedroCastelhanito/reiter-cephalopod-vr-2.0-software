"""Per-channel reader thread body: forwards launcher control-channel notifications."""

from __future__ import annotations

import os
import queue

from cephvr.launcher.decisions import (
    LOST_KEY,
    MAX_LINE_BYTES,
    parse_notification_line,
)


def read_notifications(
    handle: int, output: queue.Queue[dict[str, object]], channel: str
) -> None:
    """Forward notifications; any EOF or protocol violation retires the channel."""
    import msvcrt

    def emit(notification: dict[str, object]) -> bool:
        notification["_channel"] = channel
        try:
            output.put_nowait(notification)
        except queue.Full:
            return False
        return True

    def lost(reason: str) -> None:
        marker: dict[str, object] = {"kind": "channel_lost", LOST_KEY: reason}
        while not emit(marker):
            try:
                output.get_nowait()  # The loss marker outranks any queued note.
            except queue.Empty:
                pass

    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    with os.fdopen(fd, "rb", buffering=0) as stream:
        while True:
            try:
                line = stream.readline(MAX_LINE_BYTES + 1)
            except (OSError, ValueError) as exc:
                lost(f"channel read failed: {exc}")
                return
            parsed = parse_notification_line(line)
            if isinstance(parsed, str):
                lost(parsed)
                return
            if not emit(parsed):
                lost("notification queue overflow")
                return
