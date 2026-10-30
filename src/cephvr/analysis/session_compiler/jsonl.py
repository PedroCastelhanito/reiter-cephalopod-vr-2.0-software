"""Append-only JSON Lines reading shared by every recorded stream (A07, V12, T19)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

JSON = dict[str, Any]


def _reject_constant(name: str) -> float:
    raise ValueError(f"non-finite JSON number {name}")


class JsonlFile:
    """Iterate complete lines; a crash-truncated final line is discarded, not parsed.

    ``truncated`` becomes true after iteration when bytes followed the last LF.
    JSON integers stay exact Python ints, so int64 nanoseconds never pass through float.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.truncated = False
        self.line_count = 0

    def __iter__(self) -> Iterator[JSON]:
        with self.path.open("rb") as handle:
            for raw in handle:
                if not raw.endswith(b"\n"):
                    self.truncated = True
                    return
                self.line_count += 1
                try:
                    yield json.loads(raw, parse_constant=_reject_constant)
                except ValueError as error:
                    raise ValueError(
                        f"{self.path.name}: line {self.line_count}: {error}"
                    ) from None


def read_json(path: Path) -> JSON:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{Path(path).name}: expected a JSON object")
    return value
