"""Screen selection and explicit per-screen conversion for the selected layer."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QVBoxLayout, QWidget

from cephvr.gui.components import button, label
from cephvr.gui.program_editing import NodePath, node_at
from cephvr.gui.stimulus_scope import FACES, change_scope, split_screens, surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


class ScreenScope(QWidget):
    committed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(label("Screens", "label"))
        row = self.grid = QGridLayout()
        body.addLayout(row)
        self.checks: dict[str, QCheckBox] = {}
        for index, face in enumerate(FACES):
            check = QCheckBox(face.title())
            check.clicked.connect(self.edit)
            row.addWidget(check, index // 2, index % 2)
            self.checks[face] = check
        self.split = button("Per-screen settings…")
        self.split.clicked.connect(self.separate)
        body.addWidget(self.split, alignment=Qt.AlignmentFlag.AlignLeft)
        self.message = label("", wrap=True)
        body.addWidget(self.message)
        self.program: Program | None = None
        self.path: NodePath = 0
        self.layer = 0
        self.enabled_screens: tuple[str, ...] = ()

    def bind(
        self, program: Program, path: NodePath, layer: int, enabled: tuple[str, ...]
    ) -> None:
        self.program, self.path, self.layer, self.enabled_screens = (
            program,
            path,
            layer,
            enabled,
        )
        node = node_at(program, path)
        self.setVisible(isinstance(node, Epoch) and bool(node.settings))
        if not isinstance(node, Epoch) or not node.settings:
            return
        setting = node.settings[layer]
        arena = setting.kind == "arena"
        faces = surfaces(setting.model_dump(mode="json"))
        visible = 0
        for face, check in self.checks.items():
            active = face.title() in enabled
            self.grid.removeWidget(check)
            check.setVisible(active or face in faces)
            if active or face in faces:
                self.grid.addWidget(check, visible // 2, visible % 2)
                visible += 1
            check.setChecked(face in faces)
            check.setText(face.title() + ("" if active else " (inactive)"))
            check.setEnabled(not arena and (active or face in faces))
        self.split.setVisible(not arena and len(faces) > 1)
        self.message.setText(
            "Arena uses enabled rig screens."
            if arena
            else "Inactive targets are retained."
            if any(f.title() not in enabled for f in faces)
            else ""
        )
        self.message.setVisible(bool(self.message.text()))

    def edit(self) -> None:
        if self.program is None or not self.isEnabled():
            return
        try:
            result = change_scope(
                self.program,
                self.path,
                self.layer,
                [f for f, c in self.checks.items() if c.isChecked()],
            )
        except ValueError as error:
            self.bind(self.program, self.path, self.layer, self.enabled_screens)
            self.message.setText(str(error))
            self.message.show()
            return
        self.committed.emit(result)

    def separate(self) -> None:
        if self.program is not None and self.isEnabled():
            try:
                self.committed.emit(split_screens(self.program, self.path, self.layer))
            except ValueError as error:
                self.message.setText(str(error))
