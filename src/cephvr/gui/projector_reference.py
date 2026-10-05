"""Compact reference row; advanced controls and layer actions stay out of the grid."""

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import button, combo, equal_row_height, label
from cephvr.gui.projector_layers import layer_title, layers_for
from cephvr.gui.reference_fields import reference_fields
from cephvr.gui.reference_layers import ReferenceLayers
from cephvr.gui.stimulus_parameters import StimulusParameters
from cephvr.gui.stimulus_presets import FILE_TYPES
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


class ProjectorReference(QWidget):
    add_requested = pyqtSignal()
    type_requested = pyqtSignal(str)
    remove_requested = pyqtSignal()
    forward_requested = pyqtSignal()
    backward_requested = pyqtSignal()
    layout_changed = pyqtSignal()

    def __init__(self, face: str) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.face = face
        self.indices: list[int] = []
        self.slots = ReferenceLayers()
        self.columns: list[tuple[str, QWidget]] = []
        self.headings: list[QLabel] = []
        self.show_header = True
        self.identity_header = True
        self.narrow = False
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)
        body.addLayout(self.grid)
        self.caption = label(face or "Rig-wide", "label")
        self.caption.setWordWrap(True)
        self.layer = combo(())
        self.layer.setMinimumWidth(0)
        self.layer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.layer.setAccessibleName(f"{face or 'Rig-wide'} layer")
        self.layer.currentIndexChanged.connect(
            lambda: self.select_layer(self.layer.currentData())
        )
        self.stimulus = combo(())
        self.stimulus.setMinimumWidth(0)
        for kind in ("3D arena",) if not face else ("None", *FILE_TYPES[:-1]):
            self.stimulus.addItem(kind.replace("Looming image", "Looming"), kind)
        self.stimulus.currentIndexChanged.connect(self.change_type)
        self.actions_button = button(
            "…", "icon", hint="Layer actions and advanced settings"
        )
        self.actions_button.setAccessibleName(f"{face or 'Rig-wide'} stimulus actions")
        menu = QMenu(self.actions_button)
        add_action = menu.addAction("Add layer")
        assert add_action is not None
        self.add = add_action
        self.add.triggered.connect(self.add_requested)
        remove = menu.addAction("Remove layer")
        move = menu.addMenu("Move layer")
        assert move is not None
        self.move_menu = move
        backward = move.addAction("Move up")
        forward = move.addAction("Move down")
        assert remove is not None and forward is not None and backward is not None
        self.remove, self.forward, self.backward = remove, forward, backward
        self.remove.triggered.connect(self.remove_requested)
        self.forward.triggered.connect(self.forward_requested)
        self.backward.triggered.connect(self.backward_requested)
        menu.addSeparator()
        advanced = menu.addAction("Advanced settings")
        assert advanced is not None
        self.advanced = advanced
        self.advanced.setCheckable(True)
        self.actions_button.setMenu(menu)
        equal_row_height(self.stimulus, self.actions_button)
        self.actions_button.setFixedWidth(self.actions_button.height())
        self.parameters = StimulusParameters(compact=True)
        body.addWidget(self.parameters)
        self.advanced.toggled.connect(self.parameters.more.setChecked)
        self.parameters.bound.connect(self.render_fields)

    def render_fields(self) -> None:
        for heading in self.headings:
            heading.hide()
            heading.deleteLater()
        self.headings.clear()
        self.columns = (
            [("", self.caption)]
            + (
                [("Layer", self.layer), ("Stimulus", self.stimulus)]
                if self.face
                else []
            )
            + reference_fields(self.parameters)
            + [("", self.actions_button)]
        )
        self.headings = [label(title, "label") for title, _ in self.columns]
        self.arrange()
        self.layout_changed.emit()

    @property
    def signature(self) -> tuple[str, ...]:
        return tuple(title for title, _ in self.columns)

    def arrange(self) -> None:
        if not self.columns:
            return
        self.narrow = self.width() < 900
        while self.grid.count():
            self.grid.takeAt(0)
        for col in range(8):
            self.grid.setColumnMinimumWidth(col, 0)
            self.grid.setColumnStretch(col, 0)
        for row in range(6):
            self.grid.setRowMinimumHeight(row, 0)
        header_height = max(h.sizeHint().height() for h in self.headings)
        self.grid.setRowMinimumHeight(0, header_height)
        for index, ((_, control), heading) in enumerate(
            zip(self.columns, self.headings, strict=True)
        ):
            slot = index if self.face or index == 0 else index + 2
            visible = self.identity_header if slot < 4 else self.show_header
            heading.setText(self.columns[index][0] if visible or self.narrow else "")
            heading.setFixedHeight(header_height)
            if self.narrow:
                # Identity and source above three numeric fields on small windows.
                positions = (
                    (0, 0, 1),
                    (0, 1, 1),
                    (0, 2, 1),
                    (2, 0, 4),
                    (4, 0, 1),
                    (4, 1, 1),
                    (4, 2, 1),
                    (0, 3, 1),
                )
                row, col, span = positions[slot]
                self.grid.setRowMinimumHeight(row, header_height)
            else:
                row, col, span = 0, index, 1
            self.grid.addWidget(heading, row, col, 1, span)
            self.grid.addWidget(control, row + 1, col, 1, span)
            heading.show()
            control.show()
        if self.narrow:
            for col in range(3):
                self.grid.setColumnStretch(col, 1)
        else:
            asset_column = 3 if self.face else 1
            for col, width in (
                (0, 74),
                (len(self.columns) - 1, self.actions_button.width()),
            ):
                self.grid.setColumnMinimumWidth(col, width)
            if self.face:
                self.grid.setColumnMinimumWidth(1, 130)
                self.grid.setColumnMinimumWidth(2, 115)
            self.grid.setColumnMinimumWidth(asset_column, 160)
            self.grid.setColumnStretch(asset_column, 1)
            for col in range(asset_column + 1, len(self.columns) - 1):
                self.grid.setColumnMinimumWidth(col, 95)
                self.grid.setColumnStretch(col, 1)
        empty = self.parameters.layer_index < 0

        self.advanced.setEnabled(not empty)
        self.actions_button.setVisible(bool(self.face) or not empty)
        self.parameters.more.hide()
        if not self.narrow:
            controls = [control for _, control in self.columns[1:]]
            equal_row_height(*controls)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        QTimer.singleShot(0, self.align_advanced)

    def align_advanced(self) -> None:
        body = self.layout()
        if body is not None:
            body.activate()
        self.grid.activate()
        anchor = self.layer if self.face else self.columns[1][1]
        inset = max(
            0,
            anchor.mapTo(self, QPoint()).x()
            - self.parameters.mapTo(self, QPoint()).x(),
        )
        margins = self.parameters.advanced_layout.contentsMargins()
        self.parameters.advanced_layout.setContentsMargins(
            inset, margins.top(), margins.right(), margins.bottom()
        )

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        if (self.width() < 900) != self.narrow:
            self.arrange()
        QTimer.singleShot(0, self.align_advanced)

    def bind(self, program: Program, preferred: int | None = None) -> None:
        epoch = program.sequence[0]
        assert isinstance(epoch, Epoch)
        old = -1 if preferred is None else preferred
        previous = self.parameters.program
        if (
            preferred is None
            and previous is not None
            and self.parameters.layer_index >= 0
        ):
            before = previous.sequence[0]
            assert isinstance(before, Epoch)
            identity = before.settings[self.parameters.layer_index].instance_id
            old = next(
                (
                    i
                    for i, setting in enumerate(epoch.settings)
                    if setting.instance_id == identity
                ),
                -1,
            )
        self.indices = [
            i
            for i in layers_for(program, epoch, self.face)
            if (epoch.settings[i].kind == "arena") == (not self.face)
        ]
        identities = [epoch.settings[i].instance_id for i in self.indices]
        self.slots.sync(identities)
        if preferred is not None and preferred in self.indices:
            self.slots.selected = epoch.settings[preferred].instance_id
        elif self.slots.selected not in self.slots.blanks and old in self.indices:
            self.slots.selected = epoch.settings[old].instance_id
        selected = next(
            (
                i
                for i in self.indices
                if epoch.settings[i].instance_id == self.slots.selected
            ),
            -1,
        )
        self.layer.blockSignals(True)
        self.layer.clear()
        for position, identity in enumerate(self.slots.order):
            index = next(
                (i for i in self.indices if epoch.settings[i].instance_id == identity),
                -1,
            )
            title = (
                layer_title(program, epoch.settings[index]).split(" · ")[0]
                if index >= 0
                else "Empty"
            )
            self.layer.addItem(f"{position + 1} · {title}", identity)
        if not self.slots.order:
            self.layer.addItem("—", "")
        self.layer.setCurrentIndex(max(0, self.layer.findData(self.slots.selected)))
        self.layer.setEnabled(len(self.slots.order) > 1)
        self.layer.blockSignals(False)
        kind = (
            layer_title(program, epoch.settings[selected]).split(" · ")[0]
            if selected >= 0
            else "None"
        )
        kind = {"Looming": "Looming image", "3D arena (rig-wide)": "3D arena"}.get(
            kind, kind
        )
        self.stimulus.blockSignals(True)
        self.stimulus.setCurrentIndex(max(0, self.stimulus.findData(kind)))
        self.stimulus.blockSignals(False)
        self.parameters.bind(program, 0, selected, self.face)
        self.remove.setEnabled(
            selected >= 0 or self.slots.selected in self.slots.blanks
        )
        position = self.indices.index(selected) if selected in self.indices else -1
        self.backward.setEnabled(bool(self.face) and position > 0)
        self.forward.setEnabled(
            bool(self.face) and 0 <= position < len(self.indices) - 1
        )
        self.move_menu.setEnabled(self.backward.isEnabled() or self.forward.isEnabled())
        self.add.setEnabled(bool(self.face) or not self.indices)

    def change_type(self) -> None:
        self.type_requested.emit(self.stimulus.currentData())

    def select_layer(self, identity: str | int | None) -> None:
        if isinstance(identity, int):
            program = self.parameters.program
            if program is None or identity not in self.indices:
                return
            epoch = program.sequence[0]
            assert isinstance(epoch, Epoch)
            identity = epoch.settings[identity].instance_id
        if not identity:
            return
        if self.parameters.dirty and not self.parameters.apply():
            self.layer.blockSignals(True)
            self.layer.setCurrentIndex(self.layer.findData(self.slots.selected))
            self.layer.blockSignals(False)
            return
        program = self.parameters.program
        if program is not None:
            self.slots.selected = identity
            if identity not in self.slots.blanks:
                epoch = program.sequence[0]
                assert isinstance(epoch, Epoch)
                index = next(
                    i for i in self.indices if epoch.settings[i].instance_id == identity
                )
                self.bind(program, index)
            else:
                self.bind(program)
