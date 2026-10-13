"""Atomic runtime GUI drafts, independent of controller acceptance and transport."""

from pathlib import Path

from cephvr.gui.configuration_files import read_snapshot, write_snapshot
from cephvr.gui.gui_snapshot import GuiSnapshot


def history_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config/runtime_gui.json"


class GuiHistory:
    def __init__(self, snapshots: GuiSnapshot, path: Path) -> None:
        self.snapshots = snapshots
        self.path = path
        self.restore_attempted = False
        self.restore_failed = False

    def restore(self) -> bool:
        """Restore once after inventory and the initial controller base are installed."""
        if self.restore_attempted:
            return False
        self.restore_attempted = True
        if not self.path.exists():
            return False
        try:
            data = self.snapshots.validate(read_snapshot(str(self.path)))
            self.snapshots.restore(data)
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            self.restore_failed = True
            raise
        return True

    def save(self) -> None:
        """A failed restore cannot silently replace the previous saved draft."""
        if self.restore_failed or (not self.restore_attempted and self.path.exists()):
            raise ValueError(
                f"Previous GUI configuration could not be restored; preserved at {self.path}. "
                "Use Save GUI as to retain the current draft separately."
            )
        data = self.snapshots.validate(self.snapshots.capture())
        write_snapshot(str(self.path), data)
        if read_snapshot(str(self.path)) != data:
            raise OSError("Saved GUI configuration could not be verified")
