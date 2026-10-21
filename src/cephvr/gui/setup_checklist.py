"""Retained observed Setup stages; completion always comes from owning evidence."""

import re
from collections.abc import Callable


class SetupChecklist:
    def __init__(
        self, update: Callable[[str, tuple[str, ...], str, str, str], None]
    ) -> None:
        self.update = update
        self.rows: dict[tuple[str, ...], dict[str, tuple[str, str]]] = {}
        self.finished: set[tuple[str, ...]] = set()

    def progress(self, target: str, key: tuple[str, ...], message: str) -> None:
        if key in self.finished:
            return
        # Counts belong to their stage, not a new checklist item per texture.
        stage = re.sub(r"\b\d+/\d+\b", "count", message)
        rows = self.rows.setdefault(key, {})
        if rows.get(stage) != (target, message):
            rows[stage] = (target, message)
            self.update(target, (*key, stage), message, "", "")

    def complete(self, key: tuple[str, ...], result: str, details: str = "") -> None:
        for stage, (target, _message) in self.rows.pop(key, {}).items():
            self.update(target, (*key, stage), "", result, details)
        self.finished.add(key)

    def unconfirmed(self) -> None:
        for key in list(self.rows):
            self.complete(
                key, "Unconfirmed", "Setup ended without step completion evidence."
            )
