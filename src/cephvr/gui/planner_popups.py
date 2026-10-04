"""Planner group/expansion windows with explicit program inputs."""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from cephvr.gui.group_dialog import GroupDialog
from cephvr.gui.group_editor import ExpandedPreview
from cephvr.visual_stimulus.config.models.program_model import Program


class PlannerPopups(QObject):
    group_committed = pyqtSignal(object, object, int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.group: GroupDialog | None = None
        self.expanded: ExpandedPreview | None = None

    def open_group(self, program: Program, scope: tuple[int, ...], index: int) -> None:
        if self.group is not None:
            self.group.raise_()
            return
        parent = self.parent()
        assert isinstance(parent, QWidget)
        dialog = GroupDialog(program, scope, index, parent)
        dialog.committed.connect(
            lambda result, selected: self.group_committed.emit(
                program, result, selected
            )
        )
        dialog.finished.connect(lambda: setattr(self, "group", None))
        dialog.finished.connect(dialog.deleteLater)
        self.group = dialog
        dialog.open()

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
