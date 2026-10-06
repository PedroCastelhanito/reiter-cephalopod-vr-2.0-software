"""Full single-source epoch editing through the shared reference composer."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from cephvr.gui.components import InlineMessage, equal_row_height, field
from cephvr.gui.epoch_composer import EpochComposer
from cephvr.gui.formatting import clock_duration
from cephvr.gui.program_editing import data_node, node_at, unique_id, validate
from cephvr.gui.projector_layers import detach_layer
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Program


class SelectionComposer(EpochComposer):
    variable_duration = False

    def duration_value(self) -> Fixed:
        if self.variable_duration:
            return Fixed.model_validate(
                {"kind": "fixed", "duration": {"seconds": "60"}}
            )
        return super().duration_value()

    def isolate(self, face: str) -> bool:
        row = self.rows[face]
        if row.parameters.layer_index < 0:
            return True
        try:
            original = self.reference_value()
            self.program, layer = detach_layer(
                original, 0, row.parameters.layer_index, face
            )
            if self.program is not original:
                self.refresh_rows(face, layer)
            return True
        except ValueError as exc:
            self.message.setText(str(exc))
            return False

    def change_type(self, face: str, kind: str) -> None:
        if self.isEnabled() and self.isolate(face):
            super().change_type(face, kind)

    def remove_layer(self, face: str) -> None:
        if self.isEnabled() and self.isolate(face):
            super().remove_layer(face)


class EpochSelection(QWidget):
    committed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        self.source: Program | None = None
        self.path: tuple[int, ...] = ()
        self._binding = False
        self._dirty = False
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 8, 0, 0)
        body.setSpacing(16)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.composer = SelectionComposer()
        identity = QWidget()
        identity.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        self.identity_grid = QGridLayout(identity)
        row = self.identity_grid
        row.setHorizontalSpacing(12)
        row.setVerticalSpacing(12)
        self.identity_fields: list[QWidget] = []
        row.setContentsMargins(0, 0, 0, 0)
        for caption, editor in (
            ("Stimulus mode", self.composer.mode),
            ("Duration (hh:mm:ss)", self.composer.duration),
            ("Batch label", self.composer.batch_label),
        ):
            editor.setMinimumWidth(0)
            self.identity_fields.append(field(caption, editor))
        self.composer.set_generation_controls(identity)
        body.addWidget(self.composer)
        self.message = InlineMessage()
        body.addWidget(self.message)
        equal_row_height(
            self.composer.mode, self.composer.duration, self.composer.batch_label
        )
        for index, widget in enumerate(self.identity_fields):
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
            self.identity_grid.addWidget(widget, 0, index * 2)
            self.identity_grid.setColumnStretch(index * 2, 1)
        self.identity_grid.setHorizontalSpacing(0)
        for column in (1, 3):
            self.identity_grid.setColumnMinimumWidth(column, 12)
        self.composer.changed.connect(self.mark_changed)
        self.composer.duration.textEdited.connect(self.mark_changed)
        self.composer.batch_label.textEdited.connect(self.mark_changed)

    @property
    def dirty(self) -> bool:
        return self._dirty or any(
            row.parameters.dirty for row in self.composer.rows.values()
        )

    def mark_changed(self) -> None:
        if not self._binding:
            self._dirty = True
            self.changed.emit()

    def bind(
        self, program: Program, path: tuple[int, ...], screens: tuple[str, ...]
    ) -> None:
        self._binding = True
        self.source, self.path = program, path
        self.composer.close_file_dialogs()
        epoch = node_at(program, path)
        assert isinstance(epoch, Epoch)
        fixed = isinstance(epoch.duration, Fixed)
        self.composer.variable_duration = not fixed
        self.composer.duration.setReadOnly(not fixed)
        self.composer.duration.setText(
            clock_duration(epoch.duration.duration.seconds)
            if isinstance(epoch.duration, Fixed)
            else "Variable"
        )
        duration = self.composer.duration_value()
        self.composer.reference_duration_ns = duration.duration.ns()
        self.composer.batch_label.setText(epoch.batch_label or "")
        # A reference is not a complete trial; keep its placeholder valid under E05.
        blank = blank_program().sequence[0]
        assert isinstance(blank, Epoch)
        placeholder = blank.duration
        self.composer.program = program.model_copy(
            update={"sequence": (epoch.model_copy(update={"duration": placeholder}),)}
        )
        self.composer.pending_assets.clear()
        arena = any(setting.kind == "arena" for setting in epoch.settings)
        self.composer.mode.blockSignals(True)
        self.composer.mode.setCurrentIndex(int(arena))
        self.composer.active_mode = int(arena)
        self.composer.mode.blockSignals(False)
        for setting in epoch.settings:
            if setting.kind != "arena":
                for face in surfaces(setting.model_dump(mode="json")):
                    name = face.title()
                    if name not in self.composer.rows:
                        self.composer.add_row(name)
        self.composer.set_screens(screens)
        for row in self.composer.rows.values():
            row.parameters.duration_override = duration
        self.composer.refresh_rows()
        self.message.clear()
        self._dirty = False
        self._binding = False

    def discard(self) -> None:
        if self.source is not None:
            self.bind(self.source, self.path, self.composer.screens)
            self.changed.emit()

    def apply(self) -> None:
        if not self.isEnabled() or self.source is None:
            return
        try:
            reference = self.composer.value()
            source = node_at(self.source, self.path)
            assert isinstance(source, Epoch)
            data = self.source.model_dump(mode="json")
            incoming = reference.model_dump(mode="json")
            epoch = incoming["sequence"][0]
            epoch["epoch_id"] = source.epoch_id
            epoch["duration"] = (
                self.composer.duration_value()
                if isinstance(source.duration, Fixed)
                else source.duration
            ).model_dump(mode="json")
            epoch["batch_label"] = self.composer.batch_label.text().strip()
            # Changed composition must not rewrite scenes used by sibling epochs.
            for key, identity in (
                ("assets", "asset_id"),
                ("instances", "instance_id"),
                ("input_channels", "channel_id"),
                ("scenes", "scene_id"),
            ):
                known = {item[identity]: item for item in data[key]}
                for item in incoming[key]:
                    old = known.get(item[identity])
                    if old == item:
                        continue
                    if old is not None:
                        if key != "scenes":
                            raise ValueError(
                                f"The edit would change a shared {key} definition"
                            )
                        item[identity] = unique_id(data, "scene")
                        epoch["scene_id"] = item[identity]
                    data[key].append(item)
                    known[item[identity]] = item
            data_node(data, self.path).update(epoch)
            result = validate(data)
        except (ValueError, TypeError, IndexError, OSError) as exc:
            self.message.setText(str(exc))
            return
        self.committed.emit(result)
