"""The selected group's fields and compact source-epoch timeline."""

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from cephvr.gui.components import label
from cephvr.gui.group_editor import GroupEditor
from cephvr.gui.protocol_batches import flat_group
from cephvr.gui.protocol_timeline import ProgramTimeline
from cephvr.visual_stimulus.config.models.program_model import Program


class ProtocolHierarchy(QWidget):
    def __init__(self) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        self.group = GroupEditor()
        row = QHBoxLayout()
        self.contents_title = label("Epochs", "label")
        row.addWidget(self.contents_title, 1)
        body.addLayout(row)
        self.contents = ProgramTimeline(details=False)
        self.contents.setAccessibleName("Group contents")
        body.addWidget(self.contents)
        self.scope_note = label("", wrap=True)
        body.addWidget(self.scope_note)
        self.scope: tuple[int, ...] = ()

    def bind(
        self,
        program: Program,
        scope: tuple[int, ...],
        index: int,
        paths: tuple[tuple[int, ...], ...],
        screens: tuple[str, ...],
    ) -> None:
        self.scope = scope
        self.group.setVisible(bool(scope))
        if scope:
            self.group.bind(program, scope)
            self.contents.screens = screens
            self.contents.block_actions.enabled = flat_group(program, scope)
            self.contents.block_actions.add.setToolTip("Add subgroup")
            self.contents.block_actions.add.setAccessibleName("Add subgroup")
            self.contents.set_program(program, index, scope)
            self.contents.set_selection(paths)
        else:
            self.group.dirty = False
        self.contents_title.setVisible(bool(scope))
        self.contents.setVisible(bool(scope))
        editable = flat_group(program, scope)
        self.scope_note.setVisible(not editable)
        self.scope_note.setText(
            "Imported structure is preserved. Select a flat group to edit its epochs."
            if not editable
            else ""
        )
