"""Bounded operator feedback for CPU and graphics Setup stages."""

from collections.abc import Callable


class SetupProgress:
    def __init__(
        self, emit: Callable[[str], None] | None, clock_ns: Callable[[], int]
    ) -> None:
        self.emit, self.clock_ns = emit, clock_ns
        self.stage = ""
        self.message = ""
        self.last_ns = 0

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
            and now - self.last_ns < 1_000_000_000
        ):
            return
        self.emit(message)
        self.stage, self.message, self.last_ns = stage, message, now
