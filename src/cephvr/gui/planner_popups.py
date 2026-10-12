"""Planner expansion window with explicit program inputs."""

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QWidget

from cephvr.gui.group_editor import ExpandedPreview
from cephvr.visual_stimulus.config.models.program_model import Program


class PlannerPopups(QObject):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.expanded: ExpandedPreview | None = None

    def open_preview(self, program: Program) -> None:
        if self.expanded is not None:
            self.expanded.close()
        parent = self.parent()
        assert isinstance(parent, QWidget)
        dialog = ExpandedPreview(program, parent)
        dialog.finished.connect(lambda: setattr(self, "expanded", None))
        dialog.finished.connect(dialog.deleteLater)
        self.expanded = dialog
        dialog.open()
