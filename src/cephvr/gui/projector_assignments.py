"""Machine-local display assignment drafts; never controller configuration history."""

from __future__ import annotations

import json
from collections.abc import Callable

from PyQt6.QtCore import QSettings, QSignalBlocker
from PyQt6.QtWidgets import QComboBox

_KEY = "projectors/assignments"
_FACES = frozenset({"Front", "Left", "Right", "Bottom"})
_LIMIT = 1024 * 1024


def validate_assignments(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("display assignments must be an object")
    result: dict[str, str] = {}
    used: set[str] = set()
    for identity, face in value.items():
        if (
            not isinstance(identity, str)
            or not identity.strip()
            or not isinstance(face, str)
            or face not in _FACES | {"Unassigned"}
            or face in used
        ):
            raise ValueError("display assignments contain invalid or duplicate roles")
        result[identity] = face
        if face != "Unassigned":
            used.add(face)
    return result


def _unique_members(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("display assignments contain duplicate members")
        result[key] = value
    return result


class AssignmentPreferences:
    def __init__(
        self, settings: QSettings | None, report: Callable[[str], None]
    ) -> None:
        self.settings = settings
        self.report = report

    def restore(self, current: dict[str, str]) -> dict[str, str]:
        if self.settings is None:
            return current
        raw = self.settings.value(_KEY)
        if raw is None:
            return current
        try:
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > _LIMIT:
                raise ValueError("display assignment preferences exceed their limit")
            document = json.loads(raw, object_pairs_hook=_unique_members)
            if (
                not isinstance(document, dict)
                or set(document) != {"version", "assignments"}
                or type(document["version"]) is not int
                or document["version"] != 1
            ):
                raise ValueError("display assignment preferences format is unsupported")
            saved = validate_assignments(document["assignments"])
        except (ValueError, TypeError) as exc:
            self.report(f"Saved display assignments were not restored: {exc}")
            return current
        claimed = set(saved.values()) & _FACES
        return {
            key: "Unassigned" if face in claimed else face
            for key, face in current.items()
            if key not in saved
        } | saved

    def save(self, assignments: dict[str, str]) -> None:
        if self.settings is None:
            return
        try:
            raw = json.dumps(
                {"version": 1, "assignments": validate_assignments(assignments)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if len(raw.encode("utf-8")) > _LIMIT:
                raise ValueError("display assignment preferences exceed their limit")
            self.settings.setValue(_KEY, raw)
            self.settings.sync()
            if self.settings.status() != QSettings.Status.NoError:
                raise OSError("frontend preferences write failed")
        except (OSError, ValueError) as exc:
            self.report(f"Display assignments were not saved: {exc}")


def sync_assignment_controls(
    assignments: dict[str, str], controls: dict[str, QComboBox]
) -> None:
    for identity, control in controls.items():
        blocker = QSignalBlocker(control)
        control.setCurrentText(assignments.get(identity, "Unassigned"))
        del blocker
