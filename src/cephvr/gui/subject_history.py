"""Read-only look at earlier sessions of a Subject ID in the output directory.

Mirrors the controller's `<root>/<YYYYMMDD>_<experiment>/<subject>-<HHMMSS>` layout
for a hint only; a reused ID can never overwrite a session, so this is advice.
"""

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cephvr.controller.metadata.files import safe_component
from cephvr.controller.metadata.types import StorageError

SCAN_LIMIT = 5000
EXPERIMENT_DIRECTORY = re.compile(r"^(\d{8})_(.+)$")


@dataclass(frozen=True)
class SubjectSessions:
    count: int
    latest: str
    same_experiment_today: bool


def find_subject_sessions(
    root: str, subject: str, experiment: str, today: date
) -> SubjectSessions | None:
    """Earlier sessions for this Subject ID, or None when none are found or readable."""
    root, subject, experiment = root.strip(), subject.strip(), experiment.strip()
    if not root or not subject:
        return None
    try:
        safe_subject = safe_component(subject)
    except StorageError:
        return None
    try:
        today_name = f"{today:%Y%m%d}_{safe_component(experiment)}"
    except StorageError:
        today_name = ""
    session = re.compile(rf"^{re.escape(safe_subject)}-(\d{{6}})$")
    found: list[tuple[str, str, str]] = []
    same_today = False
    scanned = 0
    try:
        with os.scandir(Path(root)) as experiments:
            for entry in experiments:
                scanned += 1
                if scanned > SCAN_LIMIT:
                    break
                match = EXPERIMENT_DIRECTORY.match(entry.name)
                if not match:
                    continue
                if not entry.is_dir(follow_symlinks=False):
                    continue
                with os.scandir(entry.path) as children:
                    for child in children:
                        scanned += 1
                        if scanned > SCAN_LIMIT:
                            break
                        hit = session.match(child.name)
                        if hit and child.is_dir(follow_symlinks=False):
                            found.append((match.group(1), match.group(2), hit.group(1)))
                            same_today = same_today or entry.name == today_name
    except OSError:
        return None
    if not found:
        return None
    stamp, name, clock = max(found, key=lambda item: (item[0], item[2], item[1]))
    latest = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]} {name} {clock[:2]}:{clock[2:4]}"
    return SubjectSessions(len(found), latest, same_today)
