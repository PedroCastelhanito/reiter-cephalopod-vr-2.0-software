"""Projector cards reuse the owning stimulus controls and validation."""

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QResizeEvent, QStandardItemModel
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import SelectionBox, button, combo, equal_row_height, label
from cephvr.gui.editing_card import EditingSurface
from cephvr.gui.icons import device_icon
from cephvr.gui.projector_layers import layer_title, layers_for
from cephvr.gui.reference_fields import reference_fields
from cephvr.gui.reference_layers import ReferenceLayers
from cephvr.gui.stimulus_parameters import StimulusParameters
from cephvr.gui.stimulus_presets import FILE_TYPES
from cephvr.gui.theme import colors_for
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


class LayerSelector(SelectionBox):
    """Layer choices and management actions share one dropdown."""

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("chevron", True)
        self.menu = QMenu(self)
        self.operations = QMenu(self)

    def showPopup(self) -> None:
        self.menu.clear()
        for index in range(self.count()):
            action = self.menu.addAction(self.itemText(index))
            assert action is not None
            action.setCheckable(True)
            action.setChecked(index == self.currentIndex())
            action.setToolTip(self.itemData(index, Qt.ItemDataRole.ToolTipRole) or "")
            action.triggered.connect(
                lambda checked=False, i=index: self.setCurrentIndex(i)
            )
        self.menu.addSeparator()
        self.menu.addActions(self.operations.actions())
        self.menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def hidePopup(self) -> None:
        self.menu.hide()
        super().hidePopup()


class ProjectorReference(EditingSurface):
    add_requested = pyqtSignal()
    type_requested = pyqtSignal(str)
    remove_requested = pyqtSignal()
    forward_requested = pyqtSignal()
    backward_requested = pyqtSignal()

    def __init__(self, face: str) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.face = face
        self.indices: list[int] = []
        self.slots = ReferenceLayers()
        self.columns: list[tuple[str, QWidget]] = []
        self.headings: list[QLabel] = []
        self.narrow = False
        self.compact = False
        body = QVBoxLayout(self)
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(0)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)
        body.addLayout(self.grid)
        self.caption = label(face or "Rig-wide", "projector-title")
        self.caption.setWordWrap(True)
        self.layer = LayerSelector()
        self.layer.setFixedWidth(64)
        self.layer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.layer.setAccessibleName(f"{face or 'Rig-wide'} layer")
        self.layer.currentIndexChanged.connect(
            lambda: self.select_layer(self.layer.currentData())
        )
        self.side = QWidget()
        self.side.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        self.side_grid = QGridLayout(self.side)
        self.side_grid.setContentsMargins(0, 0, 0, 0)
        self.side_grid.setVerticalSpacing(6)
        self.identity_label = label("Projector" if face else "Space", "label")
        self.layer_label = label("Layer", "label")
        self.editing_label.hide()
        self.stimulus = combo(())
        self.stimulus.setMinimumWidth(0)
        for kind in ("3D arena",) if not face else ("None", *FILE_TYPES[:-1]):
            self.stimulus.addItem(kind.replace("Looming image", "Looming"), kind)
        self.stimulus.currentIndexChanged.connect(self.change_type)
        self.actions_button = button("", "icon", hint="Advanced settings")
        self.actions_button.setProperty("iconName", "configure")
        self.actions_button.setAccessibleName(f"{face or 'Rig-wide'} advanced settings")
        self.actions_button.setCheckable(True)
        menu = self.layer.operations
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
        equal_row_height(self.stimulus, self.actions_button)
        self.actions_button.setFixedWidth(self.actions_button.height())
        self.parameters = StimulusParameters(compact=True)
        body.addWidget(self.parameters)
        self.actions_button.toggled.connect(self.parameters.more.setChecked)
        self.parameters.more.toggled.connect(self.actions_button.setChecked)
        self.parameters.bound.connect(self.render_fields)

    def minimumSizeHint(self) -> QSize:
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

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
        if self.parameters.motion_source is not None:
            self.parameters.motion_source.currentIndexChanged.connect(
                self.motion_source_changed
            )
        self.arrange()

    def motion_source_changed(self) -> None:
        self.arrange()

    def visible_columns(self) -> list[tuple[str, QWidget]]:
        source = self.parameters.motion_source
        if source is None:
            return self.columns
        linked = source.currentText() == "Linked"
        hidden = (
            {title for title, _ in self.columns}
            - {"", "Layer", "Stimulus", "Asset", "Motion source", "Linked to"}
            if linked
            else {"Linked to"}
        )
        return [
            (title, control) for title, control in self.columns if title not in hidden
        ]

    @property
    def signature(self) -> tuple[str, ...]:
        return tuple(title for title, _ in self.visible_columns())

    def arrange(self) -> None:
        if not self.columns:
            return
        self.narrow = self.width() < 900
        self.compact = self.width() < 650
        columns = self.visible_columns()
        # One grid owns both rows so their columns cannot drift independently.
        for layout in (self.grid, self.side_grid):
            while layout.count():
                layout.takeAt(0)
            for col in range(12):
                layout.setColumnMinimumWidth(col, 0)
                layout.setColumnStretch(col, 0)
            for row in range(16):
                layout.setRowMinimumHeight(row, 0)
        self.actions_button.setIcon(device_icon("configure", colors_for(self).muted))
        heading_height = max(heading.sizeHint().height() for heading in self.headings)
        controls = [control for _, control in columns if control is not self.caption]
        equal_row_height(*controls)
        control_height = self.stimulus.height()
        self.caption.setFixedHeight(control_height)
        first = 0 if self.compact else 1
        top = 1 if self.compact else 0
        action_col = first + 4
        source = self.parameters.motion_source
        self_asset = bool(
            source is not None
            and source.currentText() == "Self"
            and self.parameters.asset_forms
        )
        if self_asset:
            asset = next(control for title, control in columns if title == "Asset")
            asset_layout = asset.layout()
            assert asset_layout is not None
            browse_item = asset_layout.itemAt(1)
            assert browse_item is not None
            browse = browse_item.widget()
            assert browse is not None
            # Reserve Browse separately so parameter fields end at the path edge.
            self.grid.setColumnMinimumWidth(
                action_col,
                browse.width() + asset_layout.spacing() - self.grid.horizontalSpacing(),
            )
            action_col += 1
        if self.compact:
            self.side_grid.addWidget(self.identity_label, 0, 0)
            self.side_grid.addWidget(self.caption, 1, 0)
            self.side_grid.addWidget(self.layer_label, 0, 1)
            self.side_grid.addWidget(self.layer, 1, 1)
            self.side_grid.setColumnStretch(0, 1)
            self.side_grid.setColumnMinimumWidth(1, 64)
            self.grid.addWidget(self.side, 0, first, 1, 5)
            self.side.show()
        else:
            self.side.hide()
            self.grid.addWidget(self.identity_label, 0, 0)
            self.grid.addWidget(self.caption, 1, 0)
            self.grid.addWidget(self.layer_label, 3, 0)
            self.grid.addWidget(self.layer, 4, 0)
            self.grid.setColumnMinimumWidth(0, 84)
        self.identity_label.show()
        self.caption.show()
        self.layer_label.setVisible(bool(self.face))
        self.layer.setVisible(bool(self.face))
        self.grid.setColumnMinimumWidth(action_col, self.actions_button.width())
        for col in range(first, first + 4):
            self.grid.setColumnStretch(col, 1)
        if not self.narrow:
            self.grid.setColumnMinimumWidth(first, 246)
            self.grid.setColumnStretch(first, 0)
        self.grid.setRowMinimumHeight(top + 2, 6)
        parameters = [
            column
            for column in columns
            if column[0] and column[0] not in {"Layer", "Stimulus", "Asset"}
        ]
        count = 2 if self.narrow else 4
        for (title, control), heading in zip(self.columns, self.headings, strict=True):
            if control in (self.caption, self.layer):
                heading.hide()
                continue
            if (title, control) not in columns:
                heading.hide()
                control.hide()
                continue
            heading.setText(title)
            if control is self.stimulus:
                row, col, span = top, first, 2 if self.narrow else 1
            elif title == "Asset":
                span = 2 if self.narrow and self.face else 3 if self.face else 4
                span += int(self_asset)
                row, col = top, action_col - span
            elif control is self.actions_button:
                row, col, span = top, action_col, 1
            elif not title or self.parameters.layer_index < 0:
                heading.hide()
                control.hide()
                continue
            else:
                parameter = parameters.index((title, control))
                batch, slot = divmod(parameter, count)
                in_batch = min(count, len(parameters) - batch * count)
                unit = 4 // count
                row, col = top + 3 + 2 * batch, first + slot * unit
                span = unit if slot < in_batch - 1 else 4 - slot * unit
                if title == "Motion source":
                    control.setMinimumWidth(0 if self.narrow else 246)
                    control.setMaximumWidth(16777215 if self.narrow else 246)
            self.grid.setRowMinimumHeight(row, heading_height)
            self.grid.addWidget(heading, row, col, 1, span)
            self.grid.addWidget(control, row + 1, col, 1, span)
            heading.setVisible(bool(title))
            control.show()
        empty = self.parameters.layer_index < 0
        self.actions_button.setEnabled(not empty)
        self.actions_button.setVisible(bool(self.face) or not empty)
        self.parameters.more.hide()
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        QTimer.singleShot(0, self.align_advanced)

    def align_advanced(self) -> None:
        if self.parameters.layer_index < 0:
            return
        body = self.layout()
        if body is not None:
            body.activate()
        self.grid.activate()
        self.side_grid.activate()
        anchor = self.stimulus if self.face else self.columns[1][1]
        inset = max(
            0,
            anchor.mapTo(self, QPoint()).x()
            - self.parameters.mapTo(self, QPoint()).x(),
        )
        margins = self.parameters.advanced_layout.contentsMargins()
        asset = next(control for title, control in self.columns if title == "Asset")
        right = max(
            0,
            self.parameters.width()
            + self.parameters.mapTo(self, QPoint()).x()
            - asset.mapTo(self, QPoint()).x()
            - asset.width(),
        )
        self.parameters.advanced_layout.setContentsMargins(
            inset, margins.top(), right, margins.bottom()
        )

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        if (self.width() < 900) != self.narrow or (self.width() < 650) != self.compact:
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
            self.layer.addItem(str(position + 1), identity)
            self.layer.setItemData(position, title, Qt.ItemDataRole.ToolTipRole)
        if not self.slots.order:
            self.layer.addItem("—", "")
        self.layer.setCurrentIndex(max(0, self.layer.findData(self.slots.selected)))
        self.layer.setEnabled(True)
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
        model = self.stimulus.model()
        if isinstance(model, QStandardItemModel):
            for i in range(self.stimulus.count()):
                item = model.item(i)
                if item is not None:
                    item.setEnabled(
                        not (
                            program.category == "media_presentation"
                            and self.stimulus.itemData(i) == "Looming image"
                        )
                    )
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
