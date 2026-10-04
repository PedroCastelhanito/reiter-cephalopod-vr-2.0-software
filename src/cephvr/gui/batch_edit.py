"""Explicit, patch-only editing of selected source epochs."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import button, combo, field, label
from cephvr.gui.epoch_batch import (
    LayerTarget,
    apply_batch,
    epoch_paths,
    family,
    matching_layer,
    parameter_value,
)
from cephvr.gui.paths import PathEdit
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
        self.targets: list[LayerTarget] = []
        self.asset_root = ""
        self.bound_face = self.bound_layer = 0
        self.bound_scope = 0
        self.fields: dict[str, tuple[QCheckBox, QLineEdit]] = {}
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        self.selection = label("", "label", wrap=True)
        body.addWidget(self.selection)
        row = QHBoxLayout()
        self.epoch_scope = combo(("Timeline selection",))
        self.epoch_scope.currentIndexChanged.connect(self.select_scope)
        row.addWidget(field("Epochs", self.epoch_scope), 2)
        self.face = combo(("All projectors",))
        self.layer = combo(())
        row.addWidget(field("Projector", self.face), 1)
        row.addWidget(field("Layer", self.layer), 2)
        body.addLayout(row)
        self.asset_row = QWidget()
        asset_layout = QHBoxLayout(self.asset_row)
        asset_layout.setContentsMargins(0, 0, 0, 0)
        self.asset_check = QCheckBox("Asset")
        self.asset_path = PathEdit()
        self.asset_path.setReadOnly(True)
        self.asset_button = button("Replace…")
        self.asset_picker = PreparedFilePicker(self)
        self.asset_picker.selected.connect(
            lambda kind, path, fresh: self.set_asset(path)
        )
        self.asset_button.clicked.connect(self.choose_asset)
        asset_layout.addWidget(self.asset_check)
        asset_layout.addWidget(self.asset_path, 1)
        asset_layout.addWidget(self.asset_button)
        body.addWidget(self.asset_row)
        self.values = QGridLayout()
        self.values.setHorizontalSpacing(18)
        self.values.setVerticalSpacing(12)
        body.addLayout(self.values)
        self.message = label("", wrap=True)
        body.addWidget(self.message)
        actions = QHBoxLayout()
        self.details = button("All parameters…")
        self.details.clicked.connect(self.open_details)
        actions.addWidget(self.details)
        actions.addStretch()
        self.reset = button("Discard changes")
        self.reset.clicked.connect(self.refresh_fields)
        self.apply_button = button("Apply")
        self.apply_button.clicked.connect(self.apply)
        actions.addWidget(self.reset)
        actions.addWidget(self.apply_button)
        body.addLayout(actions)
        self.face.currentIndexChanged.connect(self.refresh_layers)
        self.layer.currentIndexChanged.connect(self.refresh_fields)

    def bind(
        self,
        program: Program,
        paths: tuple[tuple[int, ...], ...],
        screens: tuple[str, ...],
    ) -> None:
        for check, _ in self.fields.values():
            check.setChecked(False)
        self.asset_check.setChecked(False)
        self.program, self.paths = program, paths
        self.refresh_scopes()
        faces = set(screens)
        for path in paths:
            node = node_at(program, path)
            if isinstance(node, Epoch):
                for setting in node.settings:
                    faces.update(
                        f.title() for f in surfaces(setting.model_dump(mode="json"))
                    )
        previous = self.face.currentData() or ""
        self.face.blockSignals(True)
        self.face.clear()
        self.face.addItem("All projectors", "")
        for face in sorted(faces):
            self.face.addItem(
                face + (" (inactive)" if face not in screens else ""), face
            )
        self.face.setCurrentIndex(max(0, self.face.findData(previous)))
        self.face.blockSignals(False)
        self.selection.setText(
            f"{len(paths)} epoch{'s' if len(paths) != 1 else ''} selected"
            + (
                " · changes also affect their repetitions"
                if any(len(p) > 1 for p in paths)
                else ""
            )
        )
        self.apply_button.setText(
            f"Apply to {len(paths)} epoch{'s' if len(paths) != 1 else ''}"
        )
        self.details.setEnabled(len(paths) == 1)
        self.refresh_layers()

    def scoped_paths(self, key: str) -> tuple[tuple[int, ...], ...]:
        assert self.program is not None
        return tuple(
            p
            for p in epoch_paths(self.program)
            if key == "all"
            or getattr(node_at(self.program, p), "batch_label", "")
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

    @property
    def dirty(self) -> bool:
        return self.asset_check.isChecked() or any(
            check.isChecked() for check, _ in self.fields.values()
        )

    def choose_asset(self) -> None:
        if self.target:
            try:
                self.asset_picker.open(self.target.family, self.asset_root, False)
            except ValueError as error:
                self.message.setText(str(error))

    def set_asset(self, path: str) -> None:
        if self.isEnabled():
            self.asset_path.setText(path)
            self.asset_check.setChecked(True)

    def refresh_layers(self) -> None:
        if self.dirty:
            self.face.blockSignals(True)
            self.face.setCurrentIndex(self.bound_face)
            self.face.blockSignals(False)
            self.message.setText("Apply or discard changes before changing projector")
            return
        if self.program is None:
            return
        previous = self.layer.currentText()
        keys: set[tuple[str, int]] = set()
        face = self.face.currentData() or ""
        for path in self.paths:
            node = node_at(self.program, path)
            if not isinstance(node, Epoch):
                continue
            counts: dict[str, int] = {}
            for index in layers_for(self.program, node, face):
                kind = family(node.settings[index])
                ordinal = counts.get(kind, 0)
                keys.add((kind, ordinal))
                counts[kind] = ordinal + 1
        self.targets = [
            LayerTarget(face, kind, ordinal) for kind, ordinal in sorted(keys)
        ]
        self.layer.blockSignals(True)
        self.layer.clear()
        self.layer.addItems(
            [
                f"{t.family.replace('Looming image', 'Looming')} · layer {t.ordinal + 1}"
                for t in self.targets
            ]
        )
        self.layer.setCurrentIndex(max(0, self.layer.findText(previous)))
        self.layer.blockSignals(False)
        self.refresh_fields()

    @property
    def target(self) -> LayerTarget | None:
        i = self.layer.currentIndex()
        return self.targets[i] if 0 <= i < len(self.targets) else None

    def refresh_fields(self) -> None:
        if self.sender() is self.layer and self.dirty:
            self.layer.blockSignals(True)
            self.layer.setCurrentIndex(self.bound_layer)
            self.layer.blockSignals(False)
            self.message.setText("Apply or discard changes before changing layer")
            return
        self.bound_face, self.bound_layer = (
            self.face.currentIndex(),
            self.layer.currentIndex(),
        )
        self.asset_check.setChecked(False)
        self.asset_path.setText("")
        self.asset_path.setPlaceholderText("Keep existing files")
        self.asset_row.setVisible(self.target is not None)
        while self.values.count():
            item = self.values.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.deleteLater()
        self.fields.clear()
        if self.program is None:
            return
        names = ["Duration"]
        target = self.target
        if target:
            names += (
                ["Start size", "End size", "Growth duration"]
                if target.family == "Looming image"
                else ["Playback start"]
                if target.family == "Video"
                else ["Speed", "Direction"]
            )
            names += ["Angular speed"]
            if target.family != "3D arena":
                names += ["Opacity"]
        for index, name in enumerate(names):
            cell = QWidget()
            layout = QVBoxLayout(cell)
            layout.setContentsMargins(0, 0, 0, 0)
            values: list[str] = []
            units: set[str] = set()
            for path in self.paths:
                try:
                    epoch = node_at(self.program, path)
                    assert isinstance(epoch, Epoch)
                    value: object
                    if name == "Duration":
                        value = (
                            epoch.duration.duration.seconds
                            if isinstance(epoch.duration, Fixed)
                            else "Variable"
                        )
                        unit = "s"
                    else:
                        assert target is not None
                        setting = epoch.settings[
                            matching_layer(self.program, path, target)
                        ].model_dump(mode="json")
                        value = parameter_value(setting, name)
                        length = (
                            "mm"
                            if setting["kind"] == "arena"
                            or setting["space"]["kind"] == "physical_surface"
                            else "°"
                        )
                        unit = {
                            "Speed": length + "/s",
                            "Direction": "°",
                            "Angular speed": "°/s",
                            "Start size": length,
                            "End size": length,
                            "Growth duration": "s",
                            "Playback start": "s",
                        }.get(name, "")
                    values.append(
                        f"{value:g}" if isinstance(value, (float, int)) else str(value)
                    )
                    units.add(unit)
                except (ValueError, KeyError, AssertionError):
                    values.append("Custom / unavailable")
            unit = next(iter(units)) if len(units) == 1 else "mixed units"
            check = QCheckBox(name + (f" ({unit})" if unit else ""))
            edit = QLineEdit()
            edit.setMinimumWidth(0)
            if (
                values
                and len(set(values)) == 1
                and values[0] not in ("Custom / unavailable", "Variable")
            ):
                edit.setText(values[0])
            else:
                edit.setPlaceholderText(
                    "Mixed" if len(set(values)) > 1 else (values[0] if values else "")
                )
            edit.textEdited.connect(lambda text, box=check: box.setChecked(True))
            check.setToolTip("Only checked fields will change")
            if len(units) > 1:
                check.setEnabled(False)
                edit.setEnabled(False)
            layout.addWidget(check)
            layout.addWidget(edit)
            self.fields[name] = check, edit
            self.values.addWidget(cell, index // 3, index % 3)
        self.message.clear()

    def apply(self) -> None:
        if not self.isEnabled() or self.program is None:
            return
        try:
            changes = {
                k: edit.text().strip()
                for k, (check, edit) in self.fields.items()
                if check.isChecked()
            }
            if self.asset_check.isChecked():
                changes["Asset"] = self.asset_path.text()
            program = apply_batch(
                self.program, self.paths, self.target, changes, self.asset_root
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
        if self.program is not None and len(self.paths) == 1 and self.target:
            try:
                layer = matching_layer(self.program, self.paths[0], self.target)
                self.detail_requested.emit(self.target.face, layer)
            except ValueError as error:
                self.message.setText(str(error))
