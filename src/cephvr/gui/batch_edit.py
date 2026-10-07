"""Epoch-wide duration and independent projector patches for selected source epochs."""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.batch_edit_rows import ProjectorEditRow
from cephvr.gui.components import (
    button,
    combo,
    equal_row_height,
    field,
    label,
)
from cephvr.gui.epoch_batch import (
    LayerTarget,
    apply_batch,
    family,
)
from cephvr.gui.epoch_selection import EpochSelection
from cephvr.gui.epoch_targets import EpochTargets
from cephvr.gui.formatting import clock_duration, parse_clock_duration
from cephvr.gui.notices import FormNotice
from cephvr.gui.prepared_file_picker import PreparedFilePicker
from cephvr.gui.program_editing import node_at
from cephvr.gui.projector_layers import layers_for
from cephvr.gui.stimulus_columns import editable_parameters
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Program


class BatchEdit(QWidget):
    committed = pyqtSignal(object)
    epochs_requested = pyqtSignal(object)
    epoch_action = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.program: Program | None = None
        self.paths: tuple[tuple[int, ...], ...] = ()
        self._timeline_paths: tuple[tuple[int, ...], ...] = ()
        self.screens: tuple[str, ...] = ()
        self.faces: tuple[str, ...] = ()
        self.rows: dict[str, ProjectorEditRow] = {}
        self.asset_root = ""
        self.bound_scope = self.bound_parameter = 0
        self.picker_row: ProjectorEditRow | None = None
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.targets = EpochTargets()
        selectors = self.targets.grid
        self.epoch_scope = combo(("Timeline selection",))
        self.epoch_scope.currentIndexChanged.connect(self.select_scope)
        self.scope_field = field("Epochs", self.epoch_scope)
        self.scope_field.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum
        )
        selectors.addWidget(self.scope_field, 0, 0)
        self.parameter = combo(("Duration",))
        self.parameter.currentIndexChanged.connect(self.show_parameter)
        self.parameter_field = field("Parameter", self.parameter)
        body.addWidget(self.targets)
        self.targets.changed.connect(self.select_targets)
        body.addWidget(self.targets.message)
        self.selection_form = EpochSelection()
        self.selection_form.committed.connect(self.committed.emit)
        body.addWidget(self.selection_form)
        self.duration_row = QWidget()
        duration_layout = QVBoxLayout(self.duration_row)
        duration_layout.setContentsMargins(0, 0, 0, 0)
        self.duration_check = QCheckBox()
        self.duration_check.hide()
        self.duration = QLineEdit()
        self.fields = {"Duration": (self.duration_check, self.duration)}
        self.duration.textEdited.connect(
            lambda _text: self.duration_check.setChecked(True)
        )
        duration_layout.addWidget(field("Value (hh:mm:ss)", self.duration))
        duration_layout.addWidget(self.duration_check)
        parameter_row = QGridLayout()
        parameter_row.setHorizontalSpacing(0)
        for column in (0, 2, 4):
            parameter_row.setColumnStretch(column, 1)
        for column in (1, 3):
            parameter_row.setColumnMinimumWidth(column, 12)
        parameter_row.addWidget(self.parameter_field, 0, 0, Qt.AlignmentFlag.AlignTop)
        parameter_row.addWidget(
            self.duration_row, 0, 2, 1, 3, Qt.AlignmentFlag.AlignTop
        )
        self.parameter_row = QWidget()
        self.parameter_row.setLayout(parameter_row)
        parameter_row.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.parameter_row)
        self.projector_header = QWidget()
        headings = QHBoxLayout(self.projector_header)
        headings.setContentsMargins(0, 0, 0, 0)
        headings.addSpacing(84)
        headings.addWidget(label("Layer", "label"), 2)
        headings.addWidget(label("Value", "label"), 3)
        headings.addSpacing(36)
        self.projector_host = QWidget()
        self.projector_rows = QVBoxLayout(self.projector_host)
        self.projector_rows.setContentsMargins(0, 0, 0, 0)
        projector_values = QWidget()
        values = QVBoxLayout(projector_values)
        values.setContentsMargins(0, 0, 0, 0)
        values.setSpacing(8)
        values.addWidget(self.projector_header)
        values.addWidget(self.projector_host)
        self.projector_values = projector_values
        parameter_row.addWidget(projector_values, 0, 2, 1, 3, Qt.AlignmentFlag.AlignTop)
        self.asset_picker = PreparedFilePicker(self)
        self.asset_picker.selected.connect(self.set_asset)
        self.message = FormNotice()
        body.addWidget(self.message)
        self.epoch_actions = QWidget()
        epoch_actions = QHBoxLayout(self.epoch_actions)
        epoch_actions.setContentsMargins(0, 0, 0, 0)
        epoch_actions.addStretch()
        self.duplicate_epoch_button = button("Duplicate")
        self.remove_epoch_button = button("Delete")
        for control, operation, key in (
            (self.duplicate_epoch_button, "duplicate", "Ctrl+D"),
            (self.remove_epoch_button, "remove", "Backspace"),
        ):
            control.setToolTip(f"{control.text()} selected epoch ({key})")
            control.clicked.connect(
                lambda checked=False, op=operation: self.epoch_action.emit(op)
            )
            epoch_actions.addWidget(control)
        equal_row_height(
            self.epoch_scope,
            self.parameter,
            self.targets.filter,
            self.targets.labels,
            self.targets.index,
            self.duplicate_epoch_button,
            self.remove_epoch_button,
        )
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()
        self.reset = button("Discard")
        self.reset.clicked.connect(self.discard)
        self.apply_button = button("Apply", "primary")
        self.apply_button.clicked.connect(self.apply)
        actions.addWidget(self.reset)
        actions.addWidget(self.apply_button)
        self.batch_actions = QWidget()
        self.batch_actions.setLayout(actions)

    @property
    def dirty(self) -> bool:
        return (
            (
                self.selection_form.dirty
                if self.epoch_scope.currentData() == "timeline"
                else False
            )
            or self.duration_check.isChecked()
            or any(row.dirty for row in self.rows.values())
        )

    def bind(
        self,
        program: Program,
        paths: tuple[tuple[int, ...], ...],
        screens: tuple[str, ...],
    ) -> None:
        self.program, self.paths, self.screens = program, paths, screens
        if self.asset_picker.dialog is not None:
            self.asset_picker.dialog.reject()
        self.picker_row = None
        self.duration_check.setChecked(False)
        self.refresh_scopes()
        if self.epoch_scope.currentData() == "timeline":
            self._timeline_paths = paths
        discovered = set(screens)
        available: dict[str, None] = {}
        arena = False
        for path in paths:
            epoch = node_at(program, path)
            if not isinstance(epoch, Epoch):
                continue
            for setting in epoch.settings:
                if setting.kind == "arena":
                    arena = True
                else:
                    discovered.update(
                        face.title()
                        for face in surfaces(setting.model_dump(mode="json"))
                    )
                available.update(dict.fromkeys(editable_parameters(setting)))
        self.faces = tuple(
            dict.fromkeys((*screens, *sorted(discovered - set(screens))))
        )
        if arena:
            self.faces += ("",)
        previous = self.parameter.currentData()
        self.parameter.blockSignals(True)
        self.parameter.clear()
        for key in ("Duration", *available):
            self.parameter.addItem("Rotation" if key == "Angular speed" else key, key)
        self.parameter.setCurrentIndex(max(0, self.parameter.findData(previous)))
        self.parameter.blockSignals(False)
        self.apply_button.setToolTip(
            f"Apply to {len(paths)} epoch{'s' if len(paths) != 1 else ''}"
        )
        self.refresh_duration()
        self.rebuild_rows()
        self.show_parameter()
        self.refresh_epoch_actions()
        if self.epoch_scope.currentData() == "timeline" and len(paths) == 1:
            self.selection_form.bind(program, paths[0], screens)

    def refresh_epoch_actions(self) -> None:
        timeline = self.epoch_scope.currentData() == "timeline"
        self.epoch_actions.setVisible(timeline)
        self.targets.set_timeline(timeline)
        self.targets.message.setVisible(
            not timeline and bool(self.targets.message.text())
        )
        single = timeline and len(self.paths) == 1
        self.selection_form.setVisible(single)
        self.parameter_field.setVisible(not single)
        self.parameter_row.setVisible(not single)
        for control in (self.duplicate_epoch_button, self.remove_epoch_button):
            control.setEnabled(timeline and len(self.paths) == 1)

    def discard(self) -> None:
        if self.program is not None:
            self.selection_form.discard()
            self.bind(self.program, self.paths, self.screens)
            self.message.clear()

    def refresh_scopes(self) -> None:
        assert self.program is not None
        previous = self.epoch_scope.currentData() or "timeline"
        self.targets.refresh(self.program)
        if previous == "target":
            try:
                if self.targets.resolve(self.program) != self.paths:
                    previous = "timeline"
            except ValueError:
                previous = "timeline"
        self.epoch_scope.blockSignals(True)
        self.epoch_scope.clear()
        self.epoch_scope.addItem("Timeline selection", "timeline")
        self.epoch_scope.addItem("Target epochs", "target")
        self.epoch_scope.setCurrentIndex(max(0, self.epoch_scope.findData(previous)))
        self.bound_scope = self.epoch_scope.currentIndex()
        self.refresh_epoch_actions()
        self.epoch_scope.blockSignals(False)
        self.apply_button.setEnabled(True)

    def select_targets(self) -> None:
        if self.program is None or self.epoch_scope.currentData() != "target":
            return
        if self.dirty:
            self.targets.restore()
            self.targets.message.setText(
                "Apply or discard changes before changing epoch targets"
            )
            self.targets.message.show()
            return
        try:
            paths = self.targets.resolve(self.program)
        except ValueError:
            self.targets.message.clear()
            self.apply_button.setEnabled(True)
            return
        self.targets.accept()
        self.targets.message.hide()
        self.apply_button.setEnabled(True)
        self.epochs_requested.emit(paths)

    def select_scope(self) -> None:
        pending_selection = (
            self.epoch_scope.itemData(self.bound_scope) == "timeline"
            and self.selection_form.dirty
        )
        if self.dirty or pending_selection:
            self.epoch_scope.blockSignals(True)
            self.epoch_scope.setCurrentIndex(self.bound_scope)
            self.epoch_scope.blockSignals(False)
            self.message.setText(
                "Apply or discard changes before changing epoch targets"
            )
            return
        key = self.epoch_scope.currentData()
        if self.program is not None and key == "target":
            self.select_targets()
        elif self.program is not None and key == "timeline":
            self.epochs_requested.emit(self._timeline_paths)
        self.bound_scope = self.epoch_scope.currentIndex()
        self.refresh_epoch_actions()
        self.show_parameter()

    def refresh_duration(self) -> None:
        assert self.program is not None
        values = []
        for path in self.paths:
            epoch = node_at(self.program, path)
            assert isinstance(epoch, Epoch)
            values.append(
                clock_duration(epoch.duration.duration.seconds)
                if isinstance(epoch.duration, Fixed)
                else "Variable"
            )
        self.duration.clear()
        self.duration.setPlaceholderText("hh:mm:ss")
        self.duration.setToolTip(
            "Enter duration as hh:mm:ss; fractional seconds are allowed"
        )
        if values and len(set(values)) == 1 and values[0] != "Variable":
            self.duration.setText(values[0])
        else:
            self.duration.setToolTip(
                ("Mixed durations" if len(set(values)) > 1 else "Variable duration")
                + " — enter hh:mm:ss to replace the targeted durations"
            )

    def targets_for(self, face: str, parameter: str) -> list[LayerTarget]:
        assert self.program is not None
        keys: set[tuple[str, int]] = set()
        for path in self.paths:
            epoch = node_at(self.program, path)
            if not isinstance(epoch, Epoch):
                continue
            counts: dict[str, int] = {}
            for index in layers_for(self.program, epoch, face):
                kind = family(epoch.settings[index])
                if (kind == "3D arena") != (face == ""):
                    continue
                ordinal = counts.get(kind, 0)
                counts[kind] = ordinal + 1
                if parameter in editable_parameters(epoch.settings[index]):
                    keys.add((kind, ordinal))
        return [LayerTarget(face, kind, ordinal) for kind, ordinal in sorted(keys)]

    def rebuild_rows(self) -> None:
        while self.projector_rows.count():
            item = self.projector_rows.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.deleteLater()
        self.rows.clear()
        for face in self.faces:
            row = ProjectorEditRow(face)
            row.browse_requested.connect(self.choose_asset)
            row.change_requested.connect(self.choose_layer)
            self.projector_rows.addWidget(row)
            self.rows[face] = row

    def show_parameter(self) -> None:
        if self.dirty and self.sender() is self.parameter:
            self.parameter.blockSignals(True)
            self.parameter.setCurrentIndex(self.bound_parameter)
            self.parameter.blockSignals(False)
            self.message.setText("Apply or discard changes before changing parameter")
            return
        parameter = self.parameter.currentData()
        if self.asset_picker.dialog is not None:
            self.asset_picker.dialog.reject()
            self.picker_row = None
        duration = parameter == "Duration"
        single = self.epoch_scope.currentData() == "timeline" and len(self.paths) == 1
        self.duration_row.setVisible(duration and not single)
        self.projector_header.setVisible(not duration and not single)
        self.projector_host.setVisible(not duration and not single)
        self.projector_values.setVisible(not duration and not single)
        if self.program is not None and not duration:
            for face, row in self.rows.items():
                row.bind(
                    self.program,
                    self.paths,
                    parameter,
                    self.targets_for(face, parameter),
                )
        self.bound_parameter = self.parameter.currentIndex()
        self.message.clear()

    def choose_layer(self, row: ProjectorEditRow) -> None:
        if self.dirty:
            row.restore_layer()
            self.message.setText("Apply or discard changes before changing layer")
            return
        row.refresh_value()

    def choose_asset(self, row: ProjectorEditRow) -> None:
        if row.target is None or not self.isEnabled():
            return
        try:
            self.picker_row = row
            self.asset_picker.open(row.target.family, self.asset_root, False)
        except ValueError as error:
            self.message.warn(str(error))

    def set_asset(self, _kind: str, path: str, _fresh: bool) -> None:
        if self.picker_row is not None and self.isEnabled():
            self.picker_row.set_asset(path)

    def apply(self) -> None:
        if not self.isEnabled() or self.program is None:
            return
        if self.epoch_scope.currentData() == "timeline" and len(self.paths) == 1:
            self.selection_form.apply()
            return
        try:
            if self.epoch_scope.currentData() == "target":
                if self.targets.resolve(self.program) != self.paths:
                    raise ValueError("Choose valid target epochs before applying")
            parameter = self.parameter.currentData()
            if parameter == "Duration":
                if not self.duration_check.isChecked():
                    raise ValueError("Enter a duration to apply")
                program = apply_batch(
                    self.program,
                    self.paths,
                    None,
                    {"Duration": parse_clock_duration(self.duration.text().strip())},
                )
            else:
                changed = [row for row in self.rows.values() if row.dirty]
                if not changed:
                    raise ValueError("Edit at least one projector value")
                program = self.program
                for row in changed:
                    if row.target is None:
                        raise ValueError(f"Choose a layer for {row.face or '3D arena'}")
                    value = row.value.text().strip()
                    if parameter == "Asset":
                        source = Path(value)
                        value = str(
                            source
                            if source.is_absolute()
                            else Path(self.asset_root) / source
                        )
                    program = apply_batch(
                        program,
                        self.paths,
                        row.target,
                        {parameter: value},
                        self.asset_root,
                    )
        except (ValueError, TypeError, IndexError, OSError) as error:
            self.message.warn(str(error))
            return
        self.committed.emit(program)
