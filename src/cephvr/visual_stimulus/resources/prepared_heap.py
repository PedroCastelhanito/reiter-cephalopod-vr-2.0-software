"""Keep the prepared renderer graph out of recurring cyclic-GC scans."""

import gc
from collections.abc import Callable


class PreparedHeap:
    def __init__(self) -> None:
        self._owned = False

    def prepare(self, check: Callable[[], None]) -> None:
        check()
        if self._owned:
            return
        if gc.get_freeze_count():
            raise RuntimeError("renderer prepared heap is already owned")
        # Reclaim Setup garbage before retaining the live graph for this session.
        gc.collect()
        check()
        gc.freeze()
        self._owned = True

    def release(self) -> None:
        if self._owned:
            gc.unfreeze()
            self._owned = False
