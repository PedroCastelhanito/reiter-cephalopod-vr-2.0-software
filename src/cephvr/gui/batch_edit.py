"""Epoch-wide duration and independent projector patches for selected source epochs."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.batch_edit_rows import PARAMETERS, ProjectorEditRow, supports
from cephvr.gui.components import button, combo, field, label
from cephvr.gui.epoch_batch import (
    LayerTarget,
    apply_batch,
    epoch_paths,
    family,
    matching_layer,
)
from cephvr.gui.formatting import clock_duration, parse_clock_duration
from cephvr.gui.prepared_file_picker import PreparedFilePicker
from cephvr.gui.program_editing import node_at
from cephvr.gui.projector_layers import layers_for
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Program


class BatchEdit(QWidget):
    committed = pyqtSignal(object)
    detail_requested = pyqtSignal(str, int)
    epochs_requested = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.program: Program | None = None
        self.paths: tuple[tuple[int, ...], ...] = ()
        self.screens: tuple[str, ...] = ()
        self.faces: tuple[str, ...] = ()
        self.rows: dict[str, ProjectorEditRow] = {}
        self.asset_root = ""
        self.bound_scope = self.bound_parameter = 0
        self.picker_row: ProjectorEditRow | None = None
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        self.selection = label("", "label", wrap=True)
        body.addWidget(self.selection)
        selectors = QHBoxLayout()
        self.epoch_scope = combo(("Timeline selection",))
        self.epoch_scope.currentIndexChanged.connect(self.select_scope)
        selectors.addWidget(field("Epochs", self.epoch_scope), 1)
        self.parameter = combo(("Duration",))
        self.parameter.currentIndexChanged.connect(self.show_parameter)
        selectors.addWidget(field("Parameter", self.parameter), 1)
        body.addLayout(selectors)
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
        body.addWidget(self.duration_row)
        self.projector_header = QWidget()
        headings = QHBoxLayout(self.projector_header)
        headings.setContentsMargins(0, 0, 0, 0)
        face_heading = label("Projector", "label")
        face_heading.setMinimumWidth(84)
        headings.addWidget(face_heading)
        headings.addWidget(label("Layer", "label"), 2)
        headings.addWidget(label("Value", "label"), 3)
        headings.addSpacing(36)
        body.addWidget(self.projector_header)
        self.projector_host = QWidget()
        self.projector_rows = QVBoxLayout(self.projector_host)
        self.projector_rows.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.projector_host)
        self.asset_picker = PreparedFilePicker(self)
        self.asset_picker.selected.connect(self.set_asset)
        self.message = label("", wrap=True)
        body.addWidget(self.message)
        actions = QHBoxLayout()
        self.details = button("All parameters…")
        self.details.clicked.connect(self.open_details)
        actions.addWidget(self.details)
        actions.addStretch()
        self.reset = button("Discard changes")
        self.reset.clicked.connect(self.discard)
        self.apply_button = button("Apply")
        self.apply_button.clicked.connect(self.apply)
        actions.addWidget(self.reset)
        actions.addWidget(self.apply_button)
        body.addLayout(actions)

    @property
    def dirty(self) -> bool:
        return self.duration_check.isChecked() or any(
            row.dirty for row in self.rows.values()
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
        discovered = set(screens)
        available: set[str] = set()
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
                available.update(
                    name for name in PARAMETERS[1:] if supports(family(setting), name)
                )
        self.faces = tuple(
            dict.fromkeys((*screens, *sorted(discovered - set(screens))))
        )
        if arena:
            self.faces += ("",)
        previous = self.parameter.currentText()
        self.parameter.blockSignals(True)
        self.parameter.clear()
        self.parameter.addItems(
            ["Duration", *(p for p in PARAMETERS[1:] if p in available)]
        )
        self.parameter.setCurrentIndex(max(0, self.parameter.findText(previous)))
        self.parameter.blockSignals(False)
        self.selection.setText(
            f"{len(paths)} epoch{'s' if len(paths) != 1 else ''} selected"
            + (
                " · changes also affect their repetitions"
                if any(len(path) > 1 for path in paths)
                else ""
            )
        )
        self.apply_button.setText(
            f"Apply to {len(paths)} epoch{'s' if len(paths) != 1 else ''}"
        )
        self.details.setEnabled(len(paths) == 1)
        self.refresh_duration()
        self.rebuild_rows()
        self.show_parameter()

    def discard(self) -> None:
        if self.program is not None:
            self.bind(self.program, self.paths, self.screens)
            self.message.clear()

    def scoped_paths(self, key: str) -> tuple[tuple[int, ...], ...]:
        assert self.program is not None
        return tuple(
            path
            for path in epoch_paths(self.program)
            if key == "all"
            or getattr(node_at(self.program, path), "batch_label", "")
            == key.removeprefix("label:")
        )

    def refresh_scopes(self) -> None:
        assert self.program is not None
        previous = self.epoch_scope.currentData() or "timeline"
        labels: dict[str, int] = {}
        for path in epoch_paths(self.program):
            name = getattr(node_at(self.program, path), "batch_label", "")
            if name:
                labels[name] = labels.get(name, 0) + 1
        self.epoch_scope.blockSignals(True)
        self.epoch_scope.clear()
        self.epoch_scope.addItem("Timeline selection", "timeline")
        self.epoch_scope.addItem("All epochs", "all")
        for name, count in sorted(labels.items()):
            self.epoch_scope.addItem(f"{name} ({count})", "label:" + name)
        if previous != "timeline" and self.scoped_paths(previous) != self.paths:
            previous = "timeline"
        self.epoch_scope.setCurrentIndex(max(0, self.epoch_scope.findData(previous)))
        self.bound_scope = self.epoch_scope.currentIndex()
        self.epoch_scope.blockSignals(False)

    def select_scope(self) -> None:
        if self.dirty:
            self.epoch_scope.blockSignals(True)
            self.epoch_scope.setCurrentIndex(self.bound_scope)
            self.epoch_scope.blockSignals(False)
            self.message.setText(
                "Apply or discard changes before changing epoch targets"
            )
            return
        key = self.epoch_scope.currentData()
        if self.program is not None and key and key != "timeline":
            self.epochs_requested.emit(self.scoped_paths(key))
        self.bound_scope = self.epoch_scope.currentIndex()

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
        if values and len(set(values)) == 1 and values[0] != "Variable":
            self.duration.setText(values[0])
        else:
            self.duration.setPlaceholderText(
                "Mixed" if len(set(values)) > 1 else values[0] if values else ""
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
                if supports(kind, parameter):
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
        parameter = self.parameter.currentText()
        if self.asset_picker.dialog is not None:
            self.asset_picker.dialog.reject()
            self.picker_row = None
        duration = parameter == "Duration"
        self.duration_row.setVisible(duration)
        self.projector_header.setVisible(not duration)
        self.projector_host.setVisible(not duration)
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
            self.message.setText(str(error))

    def set_asset(self, _kind: str, path: str, _fresh: bool) -> None:
        if self.picker_row is not None and self.isEnabled():
            self.picker_row.set_asset(path)

    def apply(self) -> None:
        if not self.isEnabled() or self.program is None:
            return
        try:
            parameter = self.parameter.currentText()
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
            self.message.setText(str(error))
            return
        self.committed.emit(program)

    def open_details(self) -> None:
        if self.dirty:
            self.message.setText(
                "Apply or discard changes before opening all parameters"
            )
            return
        if self.program is None or len(self.paths) != 1:
            return
        target = next(
            (row.target for row in self.rows.values() if row.target is not None), None
        )
        if target is None:
            target = next(
                (
                    candidate
                    for face in self.faces
                    for candidate in self.targets_for(face, "Asset")
                ),
                None,
            )
        if target is not None:
            try:
                layer = matching_layer(self.program, self.paths[0], target)
                self.detail_requested.emit(target.face, layer)
            except ValueError as error:
                self.message.setText(str(error))
