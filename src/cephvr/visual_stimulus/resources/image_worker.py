"""One bounded off-thread still-image decode/conversion handoff."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .budget import BoundedBudget

if TYPE_CHECKING:
    from .image_source import ImageSource


@dataclass(frozen=True, slots=True)
class ImageResult:
    key: str
    pixels: bytes | None
    error: BaseException | None


class ImageWorker:
    """A single admitted job/result; its reservation survives until owner release."""

    def __init__(
        self,
        budget: BoundedBudget,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.budget = budget
        self.clock_ns = clock_ns
        self._condition = threading.Condition()
        self._closing = threading.Event()
        self._job: tuple[ImageSource, int | None] | None = None
        self._result: ImageResult | None = None
        self._thread = threading.Thread(
            target=self._run, name="visual-stimulus-image-loader", daemon=True
        )
        self._thread.start()

    @property
    def busy(self) -> bool:
        with self._condition:
            return self._job is not None

    def request(self, source: ImageSource, deadline_ns: int | None = None) -> bool:
        with self._condition:
            if self._closing.is_set() or self._job is not None:
                return False
            self.budget.reserve(
                owner="visual_stimulus:image-loader",
                cpu_bytes=source.cpu_bytes,
                gpu_bytes=0,
            )
            self._job = (source, deadline_ns)
            self._condition.notify()
            return True

    def result(self) -> ImageResult | None:
        with self._condition:
            return self._result

    def release_result(self) -> None:
        with self._condition:
            if self._result is None:
                raise RuntimeError("image result is not complete")
            self._result = None
            self._job = None
            self.budget.release(owner="visual_stimulus:image-loader")
            self._condition.notify()

    def _run(self) -> None:
        pixels: bytes | None = None
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: (
                        self._closing.is_set()
                        or (self._job is not None and self._result is None)
                    )
                )
                if self._closing.is_set():
                    return
                assert self._job is not None
                source, deadline = self._job

            def check(deadline: int | None = deadline) -> None:
                if self._closing.is_set() or (
                    self.budget.cancelled is not None and self.budget.cancelled.is_set()
                ):
                    raise InterruptedError("image loading cancelled")
                if deadline is not None and self.clock_ns() >= deadline:
                    raise TimeoutError("image loading missed Setup deadline")

            try:
                check()
                pixels = source.load(check)
                check()
                result = ImageResult(source.key, pixels, None)
            except BaseException as exc:
                result = ImageResult(
                    source.key, None, RuntimeError(f"{type(exc).__name__}: {exc}")
                )
            with self._condition:
                self._result = result
                pixels = None
                del result
                self._condition.wait_for(
                    lambda: self._closing.is_set() or self._result is None
                )

    def close(self, deadline_ns: int) -> bool:
        self._closing.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(max(0.0, (deadline_ns - self.clock_ns()) / 1e9))
        if self._thread.is_alive():
            return False
        with self._condition:
            self._result = None
            self._job = None
            self.budget.release(owner="visual_stimulus:image-loader")
        return True
