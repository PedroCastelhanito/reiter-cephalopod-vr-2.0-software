"""V13 offline replay interface; declaration only, no runtime implementation."""
from typing import Protocol
from evidence_model import ReplayRequest, ReplayReport
class OfflineReplay(Protocol):
    def export(self, request: ReplayRequest) -> ReplayReport:
        """Read complete evidence lines (discard an incomplete final line), validate
        coverage/dependencies, then create new lossless files. Without the closing
        line only partial replay "up to render group N" is available."""
        ...
