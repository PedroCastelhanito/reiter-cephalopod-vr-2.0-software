"""Terminal-style operator log rows: time, fixed-width subject, terse step."""

import re
from datetime import datetime

SUBJECT_WIDTH = 9
STAMP_WIDTH = len("00:00:00  ")
CATEGORY_PREFIX = re.compile(r"^(\[[^\]\r\n]+\]) +")
_SUBJECTS = {
    "Visual stimulus": "STIMULUS",
    "Microcontroller": "MCU",
    "Behavior camera": "BEH CAM",
    "Tracking camera": "TRK CAM",
    "Eye camera": "EYE CAM",
    "Configuration": "CONFIG",
    "Abort Now": "ABORT",
    "Abort now": "ABORT",
}


def terminal_body(message: str) -> str:
    """Format a subject column, using GUI for messages without a subject."""
    if CATEGORY_PREFIX.match(message):
        return message
    subject, separator, step = message.partition(" · ")
    if not separator or not subject.strip():
        subject, step = "GUI", message
    tag = f"[{_SUBJECTS.get(subject, subject.upper())}]"
    return f"{tag:<{SUBJECT_WIDTH + 2}} {step}"


def terminal_row(body: str, now: datetime | None = None) -> str:
    """Prefix a wall-clock stamp; continuation lines align under the body."""
    stamp = (now or datetime.now()).strftime("%H:%M:%S")
    first, *rest = body.split("\n")
    indent = " " * STAMP_WIDTH
    return "\n".join([f"{stamp}  {first}", *(indent + line for line in rest)])
