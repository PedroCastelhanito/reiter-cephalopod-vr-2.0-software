"""Bounded operator feedback for CPU and graphics Setup stages."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

# StaleImageBundle contract bound per progress report; the rest wait for the next.
STALE_BUNDLES_PER_REPORT = 64


@dataclass(slots=True)
class PreparationMetrics:
    """Cumulative CPU preparation measurements for one Setup, including cache hits."""

    source_seconds: float = 0.0
    image_seconds: float = 0.0
    compile_seconds: float = 0.0
    sources_hashed: int = 0
    fingerprints_reused: int = 0
    images_inspected: int = 0
    images_validated: int = 0
    validations_reused: int = 0


class SetupProgress:
    def __init__(
        self,
        emit: Callable[..., None] | None,
        clock_ns: Callable[[], int],
        cadence_ns: int = 1_000_000_000,
    ) -> None:
        self.emit, self.clock_ns = emit, clock_ns
        self.cadence_ns = cadence_ns
        self.stage = ""
        self.message = ""
        self.last_ns = 0
        self.stale: list[Any] = []

    def stale_bundles(self, entries: Iterable[Any]) -> None:
        """Queue replaced bundles for the next emitted report; unsent ones stay kept."""
        self.stale.extend(entries)

    def update(
        self, stage: str, completed: int | None = None, total: int | None = None
    ) -> None:
        if self.emit is None:
            return
        message = stage if completed is None else f"{stage}: {completed}/{total}"
        now = self.clock_ns()
        if message == self.message or (
            stage == self.stage
            and completed != total
            and now - self.last_ns < self.cadence_ns
        ):
            return
        if self.stale:
            sent = self.stale[:STALE_BUNDLES_PER_REPORT]
            self.emit(message, tuple(sent))
            del self.stale[: len(sent)]
        else:
            self.emit(message)
        self.stage, self.message, self.last_ns = stage, message, now
