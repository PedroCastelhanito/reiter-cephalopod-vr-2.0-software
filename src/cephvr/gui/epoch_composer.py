"""One reference epoch with independent, visible per-projector editors."""

import json

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import combo
from cephvr.gui.formatting import parse_clock_duration
from cephvr.gui.notices import FormNotice
from cephvr.gui.prepared_file_picker import PreparedFilePicker
from cephvr.gui.program_editing import validate
from cephvr.gui.projector_layers import reorder_projector_layer
from cephvr.gui.projector_reference import ProjectorReference
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.reference_draft import reference_mode, replace_reference
from cephvr.gui.stimulus_fades import retime_fades
from cephvr.gui.stimulus_presets import add_file_stimulus, remove_stimulus
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Program


class EpochComposer(QWidget):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.program = blank_program()
        self.screens: tuple[str, ...] = ()
        self.rows: dict[str, ProjectorReference] = {}
        self.asset_root = ""
        self.closed_loop = False
        self.pending_assets: set[str] = set()
        self.active_mode = 0
        self.reference_duration_ns = 60_000_000_000
        self.picker_face = ""
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(16)
        self.duration = QLineEdit("00:01:00")
        self.mode = combo(("Per-projector stimuli", "3D arena"))
        self.batch_label = QLineEdit()
        self.batch_label.setPlaceholderText("Optional · e.g. Adaptation")
        self.batch_label.setMaxLength(128)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.references = QVBoxLayout()
        self.references.setSpacing(8)
        self.body.addLayout(self.references)
        self.picker = PreparedFilePicker(self)
        self.picker.selected.connect(
            lambda preset, path, fresh: self.add_file(preset, path, self.picker_face)
        )
        self.message = FormNotice()
        self.body.addWidget(self.message)
        self.duration.editingFinished.connect(self.update_duration)
        self.add_row("")
        self.refresh_rows()

    def set_generation_controls(self, controls: QWidget) -> None:
        """Place batch operations between epoch identity and stimulus references."""
        self.body.insertWidget(0, controls)
        self.body.insertSpacing(1, 8)

    def add_row(self, face: str) -> None:
        reference = ProjectorReference(face)
        reference.parameters.asset_root = self.asset_root
        reference.parameters.duration_override = self.duration_value()
        reference.parameters.set_closed_loop(self.closed_loop)
        reference.parameters.committed.connect(
            lambda program: self.accept(program, reference)
        )
        reference.type_requested.connect(lambda kind: self.change_type(face, kind))
        reference.parameters.media_selected.connect(lambda: self.asset_ready(face))
        reference.parameters.bound.connect(lambda: self.clear_pending_path(face))
        reference.add_requested.connect(lambda: self.add_empty_layer(face))
        reference.remove_requested.connect(lambda: self.remove_layer(face))
        reference.forward_requested.connect(lambda: self.reorder(face, 1))
        reference.backward_requested.connect(lambda: self.reorder(face, -1))
        self.rows[face] = reference
        reference.layout_changed.connect(self.update_headers)
        self.references.addWidget(reference)
        reference.bind(self.program)

    def set_closed_loop(self, closed: bool) -> None:
        self.closed_loop = closed
        for row in self.rows.values():
            row.parameters.set_closed_loop(closed)

    def set_asset_root(self, path: str) -> None:
        self.asset_root = path
        for row in self.rows.values():
            row.parameters.asset_root = path

    def close_file_dialogs(self) -> None:
        for row in self.rows.values():
            row.parameters.close_file_dialog()
        if self.picker.dialog is not None:
            self.picker.dialog.reject()

    def set_screens(self, screens: tuple[str, ...]) -> None:
        self.screens = screens
        for face in screens:
            if face not in self.rows:
                self.add_row(face)
        self.show_rows()

    def show_rows(self) -> None:
        for face, row in self.rows.items():
            active = face in self.screens
            row.setVisible(
                (not face)
                if self.active_mode
                else bool(face) and (active or bool(row.indices))
            )
            row.caption.setText(
                face + (" (inactive)" if not active else "") if face else "Rig-wide"
            )
            if face:
                row.add.setEnabled(active)
                row.stimulus.setEnabled(active)
        self.update_headers()
        self.message.status(
            "Enable projectors in Devices to add 2D stimuli"
            if not self.screens and not self.active_mode
            else ""
        )

    def update_headers(self) -> None:
        previous: tuple[str, ...] = ()
        for face, row in self.rows.items():
            if (bool(face) == bool(self.active_mode)) or (
                face and face not in self.screens and not row.indices
            ):
                continue
            row.identity_header = not previous
            row.show_header = row.signature != previous
            previous = row.signature
            row.arrange()

    def refresh_rows(self, face: str = "", preferred: int | None = None) -> None:
        for name, row in self.rows.items():
            row.bind(self.program, preferred if face == name else None)
        self.show_rows()

    def accept(self, program: Program, source: ProjectorReference) -> None:
        # Rows author disjoint layers; rebase their drafts without rebuilding fields.
        inputs_changed = self.program.input_channels != program.input_channels
        self.program = program
        epoch = program.sequence[0]
        assert isinstance(epoch, Epoch)
        for row in self.rows.values():
            if row is not source:
                row.parameters.program = program
                if inputs_changed and not row.parameters.dirty:
                    row.bind(program)

        self.changed.emit()

    def update_duration(self) -> None:
        try:
            duration = self.duration_value()
            epoch = self.program.sequence[0]
            assert isinstance(epoch, Epoch)
            if self.reference_duration_ns != duration.duration.ns():
                settings = [s.model_dump(mode="json") for s in epoch.settings]
                retime_fades(
                    settings, self.reference_duration_ns, duration.duration.ns()
                )
                changed = Epoch.model_validate_json(
                    json.dumps(
                        {
                            **epoch.model_dump(mode="json"),
                            "settings": settings,
                        }
                    )
                )
                self.reference_duration_ns = duration.duration.ns()
                for row in self.rows.values():
                    row.parameters.duration_override = duration
                self.program = self.program.model_copy(update={"sequence": (changed,)})
                self.refresh_rows()
            self.message.clear()
            self.changed.emit()
        except ValueError as error:
            self.message.setText(str(error))

    def duration_value(self) -> Fixed:
        value = Fixed.model_validate(
            {
                "kind": "fixed",
                "duration": {"seconds": parse_clock_duration(self.duration.text())},
            }
        )
        if value.duration.ns() <= 0:
            raise ValueError("Epoch duration must be positive")
        return value

    def reference_value(self) -> Program:
        for face, row in self.rows.items():
            if row.parameters.dirty and not row.parameters.apply():
                raise ValueError(
                    f"{face or 'Rig-wide'} · {row.parameters.message.text()}"
                )
        self.update_duration()
        if self.message.text():
            raise ValueError(self.message.text())
        return self.program

    def value(self) -> Program:
        program = reference_mode(self.reference_value(), bool(self.active_mode))
        epoch = program.sequence[0]
        assert isinstance(epoch, Epoch)
        if any(s.instance_id in self.pending_assets for s in epoch.settings):
            raise ValueError("Choose an asset for each stimulus before adding epochs")
        return program

    def clear_pending_path(self, face: str) -> None:
        row = self.rows[face]
        epoch = self.program.sequence[0]
        assert isinstance(epoch, Epoch)
        index = row.parameters.layer_index
        if index >= 0 and epoch.settings[index].instance_id in self.pending_assets:
            for editor in row.parameters.asset_forms.values():
                editor.clear()
                editor.setPlaceholderText("Choose file…")

    def asset_ready(self, face: str) -> None:
        epoch = self.program.sequence[0]
        assert isinstance(epoch, Epoch)
        self.pending_assets.discard(
            epoch.settings[self.rows[face].parameters.layer_index].instance_id
        )
        self.rows[face].bind(self.program)
        self.changed.emit()

    def change_type(self, face: str, kind: str) -> None:
        if not self.isEnabled():
            return
        row = self.rows[face]
        try:
            original = self.reference_value()
            epoch = original.sequence[0]
            assert isinstance(epoch, Epoch)
            old = row.parameters.layer_index
            old_id = epoch.settings[old].instance_id if old >= 0 else ""
            self.program, selected = replace_reference(original, old, kind, face)
            if selected >= 0:
                epoch = self.program.sequence[0]
                assert isinstance(epoch, Epoch)
                row.slots.fill(epoch.settings[selected].instance_id, old_id)
                data = self.program.model_dump(mode="json")
                scene = next(
                    s for s in data["scenes"] if s["scene_id"] == epoch.scene_id
                )
                if face:
                    ordered = [
                        key for key in row.slots.order if key not in row.slots.blanks
                    ]
                    # Preserve other projectors' positions while ordering this row's layers.
                    positions = [
                        i
                        for i, key in enumerate(scene["layer_instance_ids"])
                        if key in ordered
                    ]
                    for position, identity in zip(positions, ordered, strict=True):
                        scene["layer_instance_ids"][position] = identity
                self.program = validate(data)
            self.pending_assets.discard(old_id)
            if selected >= 0:
                epoch = self.program.sequence[0]
                assert isinstance(epoch, Epoch)
                self.pending_assets.add(epoch.settings[selected].instance_id)
            self.refresh_rows(face, selected)
            self.changed.emit()
        except ValueError as error:
            row.stimulus.blockSignals(True)
            epoch = self.program.sequence[0]
            assert isinstance(epoch, Epoch)
            from cephvr.gui.epoch_batch import family

            previous = (
                family(epoch.settings[row.parameters.layer_index])
                if row.parameters.layer_index >= 0
                else "None"
            )
            row.stimulus.setCurrentIndex(max(0, row.stimulus.findData(previous)))
            row.stimulus.blockSignals(False)
            self.message.setText(str(error))

    def change_mode(self, index: int) -> None:
        try:
            self.reference_value()
        except ValueError as error:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.active_mode)
            self.mode.blockSignals(False)
            self.message.setText(str(error))
            return
        self.close_file_dialogs()
        self.active_mode = index
        if index and not self.rows[""].indices:
            self.change_type("", "3D arena")
        self.show_rows()
        self.changed.emit()

    def add_empty_layer(self, face: str) -> None:
        if not self.isEnabled() or (face and face not in self.screens):
            return
        row = self.rows[face]
        if row.parameters.dirty and not row.parameters.apply():
            return
        row.slots.add()
        row.bind(self.program)
        self.show_rows()
        self.changed.emit()

    def choose(self, kind: str, face: str) -> None:
        if self.picker.dialog is not None:
            self.picker.dialog.raise_()
            return
        try:
            self.picker_face = face
            self.picker.open(kind, self.asset_root, False)
        except ValueError as error:
            self.message.warn(error)

    def add_file(self, kind: str, path: str, face: str) -> None:
        if not self.isEnabled():
            return
        try:
            reference = self.reference_value()
        except ValueError as error:
            self.message.setText(str(error))
            return
        try:
            if kind != "3D arena" and face not in self.screens:
                raise ValueError("Choose an enabled projector")
            self.program = add_file_stimulus(
                reference,
                0,
                kind,
                (face,) if face else self.screens,
                self.asset_root,
                path,
            )
            epoch = self.program.sequence[0]
            assert isinstance(epoch, Epoch)
            self.refresh_rows(face, len(epoch.settings) - 1)
            self.changed.emit()
        except (ValueError, OSError) as error:
            self.message.warn(error)

    def remove_layer(self, face: str) -> None:
        row = self.rows[face]
        if row.slots.remove_blank():
            row.bind(self.program)
            self.changed.emit()
            return
        if row.parameters.layer_index < 0:
            return
        try:
            self.program = remove_stimulus(
                self.reference_value(), 0, row.parameters.layer_index
            )
            self.refresh_rows()
            self.changed.emit()
        except ValueError as error:
            self.message.setText(str(error))

    def reorder(self, face: str, delta: int) -> None:
        row = self.rows[face]
        if row.parameters.layer_index < 0:
            return
        try:
            self.program, selected = reorder_projector_layer(
                self.reference_value(),
                0,
                row.parameters.layer_index,
                face,
                delta,
            )
            self.refresh_rows(face, selected)
            self.changed.emit()
        except ValueError as error:
            self.message.setText(str(error))
