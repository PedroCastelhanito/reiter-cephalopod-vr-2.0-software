"""Family-specific parameters with atomic canonical-model commits."""

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.arena_limits import ArenaLimits
from cephvr.gui.arena_movement import ArenaMovement
from cephvr.gui.components import Card, button, equal_row_height, label
from cephvr.gui.epoch_motion import EpochMotion
from cephvr.gui.feedback_mappings import FeedbackMappings
from cephvr.gui.file_dialogs import file_dialog, open_file_dialog
from cephvr.gui.grating_appearance import GratingAppearance
from cephvr.gui.grating_motion import GratingMotion
from cephvr.gui.image_parameters import ImageParameters
from cephvr.gui.looming_size import LoomingSize
from cephvr.gui.motion_source import MotionSource
from cephvr.gui.notices import FormNotice
from cephvr.gui.paths import PathEdit
from cephvr.gui.program_editing import NodePath, data_node, node_at
from cephvr.gui.projector_layers import projector_edit
from cephvr.gui.sparse_noise_layer import SparseNoiseLayer
from cephvr.gui.stimulus_asset_paths import (
    AssetPathResolver,
    apply_asset_edits,
    apply_link,
    replace_tile,
)
from cephvr.gui.stimulus_binding import (
    AdvancedParts,
    Binding,
    advanced_parts,
    primary_parts,
)
from cephvr.gui.stimulus_fades import StimulusFades
from cephvr.gui.stimulus_files import (
    resolve_stimulus_file,
)
from cephvr.gui.stimulus_form import ValueEditor
from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.config.models.parameter_catalogue import parameter_units
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Fixed,
    Program,
    Settings,
    parse_program_json,
)
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES


class StimulusParameters(QWidget):
    committed = pyqtSignal(object)
    bound = pyqtSignal()
    media_selected = pyqtSignal()

    def __init__(self, *, compact: bool = False) -> None:
        super().__init__()
        self.compact = compact
        self.external_controls: list[QWidget] = []
        self.program: Program | None = None
        self.dirty = False
        self.asset_root = ""
        self.sparse_layer: SparseNoiseLayer | None = None
        self.file_dialog: QFileDialog | None = None
        self.node_index: NodePath = 0
        self.layer_index = 0
        self.duration_override: Fixed | None = None
        self.projector = ""
        self.forms: list[
            ValueEditor
            | EpochMotion
            | GratingMotion
            | GratingAppearance
            | LoomingSize
            | ArenaMovement
            | ImageParameters
        ] = []
        self.asset_forms: dict[str, PathEdit] = {}
        self.pending_profiles: dict[str, str] = {}
        self.resolver = AssetPathResolver()
        self.arena_limits: ArenaLimits | None = None
        self.feedback: FeedbackMappings | None = None
        self.tracking_available = True
        self.retain = QCheckBox("Retain state")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.units = label("", wrap=True)
        self.units.hide()
        self.file_rows: list[QWidget] = []
        self.primary = QVBoxLayout()
        self.primary.setContentsMargins(0, 0, 0, 0)
        self.media = QVBoxLayout()
        self.media.setContentsMargins(0, 0, 0, 0)
        self.body.addLayout(self.media)
        self.body.addLayout(self.primary)
        self.more = QCheckBox("More settings")
        self.more.toggled.connect(self.show_more)
        self.body.addWidget(self.more)
        self.advanced = QWidget()
        self.advanced_layout = QVBoxLayout(self.advanced)
        self.advanced_layout.setContentsMargins(0, 16, 0, 12)
        self.advanced_card = Card("Advanced settings", compact=True)
        self.advanced_layout.addWidget(self.advanced_card)
        self.extra_body = self.advanced_card.body
        self.extra_body.setSpacing(SIZES.group_gap)
        self.closed_loop = False
        self.fades: StimulusFades | None = None
        self.motion_source: MotionSource | None = None
        self.body.addWidget(self.advanced)
        row = QHBoxLayout()
        self.message = FormNotice()
        row.addWidget(self.message, 1)
        self.reset_button = button("Reset")
        self.reset_button.clicked.connect(self.reset)
        row.addWidget(self.reset_button)
        self.apply_button = button("Apply changes")
        self.apply_button.clicked.connect(self.apply)
        row.addWidget(self.apply_button)
        self.body.addLayout(row)
        self.apply_button.hide()
        self.reset_button.hide()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.focusChanged.connect(self.finish_edit)

    def set_closed_loop(self, closed: bool) -> None:
        self.closed_loop = closed and self.tracking_available
        if self.feedback is not None:
            self.feedback.setVisible(self.tracking_available)
            self.feedback.set_closed_loop(self.closed_loop)

    def show_more(self, checked: bool) -> None:
        grating = any(
            isinstance(form, GratingMotion) for form in self.forms
        ) and not any(isinstance(form, GratingAppearance) for form in self.forms)
        self.more.setVisible(not grating and not self.compact)
        self.advanced.setVisible(checked and not grating)

    def mark_changed(self) -> None:
        self.dirty = True
        self.message.clear()
        self.message.show()
        QTimer.singleShot(0, self.auto_apply)

    def auto_apply(self) -> None:
        if (
            self.dirty
            and self.isEnabled()
            and not isinstance(QApplication.focusWidget(), QLineEdit)
        ):
            self.apply()

    def finish_edit(self, previous: QWidget | None, current: QWidget | None) -> None:
        if (
            self.dirty
            and previous is not None
            and (
                self.isAncestorOf(previous)
                or any(
                    w is previous or w.isAncestorOf(previous)
                    for w in self.external_controls
                )
            )
        ):
            self.apply()

    def close_file_dialog(self) -> None:
        if self.file_dialog is not None:
            self.file_dialog.reject()

    def clear(self) -> None:
        """Drop the previous layer's controls and per-layer state."""
        self.close_file_dialog()
        if self.feedback is not None:
            self.feedback.dialog.reject()
        for control in self.external_controls:
            control.hide()
            control.deleteLater()
        self.external_controls.clear()
        for layout in (self.primary, self.extra_body):
            while layout.count() > (1 if layout is self.extra_body else 0):
                item = layout.takeAt(1 if layout is self.extra_body else 0)
                if item is not None and (widget := item.widget()) is not None:
                    widget.deleteLater()
        self.sparse_layer = None
        for row in self.file_rows:
            self.media.removeWidget(row)
            row.deleteLater()
        self.file_rows.clear()
        for old_form in self.forms:
            old_form.deleteLater()
        self.forms.clear()
        self.asset_forms.clear()
        self.pending_profiles.clear()
        self.motion_source = None
        self.feedback = None
        self.arena_limits = None
        self.fades = None
        self.message.clear()
        self.message.setVisible(not self.compact)
        self.reset_button.hide()

    def bind(
        self,
        program: Program,
        node_index: NodePath,
        layer_index: int,
        projector: str = "",
    ) -> None:
        self.projector = projector
        self.clear()
        self.dirty = False
        self.program, self.node_index, self.layer_index = (
            program,
            node_index,
            layer_index,
        )
        node = node_at(program, node_index)
        if not isinstance(node, Epoch) or not node.settings or layer_index < 0:
            self.hide()
            self.bound.emit()
            return
        self.show()
        binding = Binding.create(program, node, layer_index, compact=self.compact)
        values = binding.values
        self.show_units(binding.setting)
        motion_values = binding.motion_values(projector)
        primary = primary_parts(binding, motion_values, projector)
        for form in primary.forms:
            form.changed.connect(self.mark_changed)
        self.forms.extend(primary.forms)
        for widget in primary.primary:
            self.primary.addWidget(widget)
        for widget in primary.hidden:
            widget.setParent(self)
            widget.hide()
        for form in primary.forms:
            if isinstance(form, ArenaMovement):
                form.setVisible(self.tracking_available)
        if binding.sparse:
            self.add_sparse_layer(binding.setting)
        advanced = advanced_parts(
            binding,
            motion_values,
            duration=self.duration_override or node.duration,
            closed_loop=self.closed_loop,
        )
        self.add_advanced(advanced, values)
        self.add_media_rows(program, values, sparse=binding.sparse)
        if values.get("grating", False):
            self.more.setChecked(False)
        self.show_more(self.more.isChecked())
        self.bound.emit()

    def add_sparse_layer(self, setting: Settings) -> None:
        self.sparse_layer = layer = SparseNoiseLayer(setting)
        layer.edited.connect(self.mark_changed)
        self.extra_body.addWidget(layer)

    def add_advanced(self, parts: AdvancedParts, values: dict[str, Any]) -> None:
        assert parts.retain is not None and parts.feedback is not None
        self.retain = parts.retain
        self.retain.toggled.connect(self.mark_changed)
        for widget in parts.widgets:
            self.extra_body.addWidget(widget)
        for form in parts.forms:
            form.changed.connect(self.mark_changed)
        self.forms.extend(parts.forms)
        for widget in parts.primary:
            self.primary.addWidget(widget)
        if parts.appearance is not None:
            self.linked_to = parts.appearance.linked_to
            self.fades = parts.appearance.fades
            self.linked_to.currentIndexChanged.connect(self.update_link_controls)
            self.linked_to.currentIndexChanged.connect(self.mark_changed)
            self.update_link_controls()
            self.fades.changed.connect(self.mark_changed)
        self.arena_limits = parts.arena_limits
        self.feedback = parts.feedback
        self.feedback.setVisible(self.tracking_available)
        self.feedback.changed.connect(self.mark_changed)

    def add_media_rows(
        self, program: Program, values: dict[str, Any], *, sparse: bool
    ) -> None:
        pattern = values.get("pattern", {})
        if isinstance(values.get("asset_id"), dict) or isinstance(
            pattern.get("asset_id"), dict
        ):
            return
        wanted = {values.get("asset_id"), pattern.get("asset_id")}
        for asset in program.assets:
            if asset.asset_id not in wanted or sparse:
                continue
            path_control = PathEdit(filename_only=self.compact)
            path_control.setText(asset.logical_path)
            path_control.setAccessibleName("Stimulus file")
            path_control.textEdited.connect(self.mark_changed)
            browse = button("Replace…")
            equal_row_height(path_control, browse)
            browse.clicked.connect(
                lambda checked=False, identity=asset.asset_id: self.choose_media(
                    identity
                )
            )
            file_row = QWidget()
            file_layout = QHBoxLayout(file_row)
            file_layout.setContentsMargins(0, 0, 0, 0)
            file_layout.addWidget(path_control, 1)
            file_layout.addWidget(browse)
            self.file_rows.append(file_row)
            self.media.addWidget(file_row)
            self.asset_forms[asset.asset_id] = path_control

    def show_units(self, setting: Settings) -> None:
        units = parameter_units(setting)
        parts = [f"Position / size: {units['x']}", "rotation: deg"]
        if "frequency" in units or "frequency_x" in units:
            parts.append(
                f"frequency: {units.get('frequency', units.get('frequency_x'))}"
            )
        if "phase_x" in units:
            parts.append("phase: cycles")
        self.units.setText(" · ".join(parts))
        self.advanced.setToolTip(self.units.text())

    def update_link_controls(self) -> None:
        linked = self.linked_to.currentData() is not None
        for form in self.forms:
            if isinstance(form, (GratingMotion, GratingAppearance)):
                form.setEnabled(not linked)
                if isinstance(form, GratingMotion):
                    form.orientation.setEnabled(not linked)
                    form.speed.setEnabled(not linked)
            if isinstance(form, EpochMotion):
                form.setEnabled(not linked)
                for control in (form.speed, form.direction, form.angular):
                    control.setEnabled(not linked and not form.custom.isChecked())
                form.setToolTip(
                    "Movement follows the selected reference screen" if linked else ""
                )

    def candidate(self, *, replacing_asset: str | None = None) -> dict[str, Any]:
        assert self.program is not None
        if self.motion_source is not None:
            self.motion_source.validate()
        candidate = self.program.model_dump(mode="json")
        setting = data_node(candidate, self.node_index)["settings"][self.layer_index]
        for form in self.forms:
            setting.update(form.read())
        if self.sparse_layer is not None:
            setting.update(self.sparse_layer.read())
        apply_asset_edits(
            candidate,
            setting,
            self.node_index,
            self.layer_index,
            {identity: edit.text() for identity, edit in self.asset_forms.items()},
            self.pending_profiles,
            root=self.asset_root,
            compact=self.compact,
            replacing_asset=replacing_asset,
            resolver=self.resolver,
        )
        if self.fades is not None:
            setting["opacity"] = self.fades.read()
            if setting["kind"] == "texture":
                apply_link(setting, self.linked_to.currentData())
        if setting["kind"] not in ("video", "arena"):
            setting["reset"] = not self.retain.isChecked()
        for form in self.forms:
            if isinstance(form, ArenaMovement):
                form.add_inputs(candidate)
        if self.feedback is not None:
            self.feedback.patch(setting, candidate)
        return candidate

    def apply(self) -> bool:
        if not self.isEnabled() or self.program is None:
            return False
        try:
            candidate = self.candidate()
            program = parse_program_json(
                json.dumps(candidate), max_bytes=DEFAULT_DOCUMENT_BYTES
            )
            program, selected = projector_edit(
                self.program, program, self.node_index, self.layer_index, self.projector
            )
        except (ValueError, TypeError, OSError) as error:
            # Focus/layer changes also call this; the epoch Add/Apply owns warnings.
            self.message.setText(str(error))
            self.message.show()
            self.reset_button.setText("Discard invalid edit")
            self.reset_button.show()
            self.message.setToolTip(str(error))
            return False
        isolated = selected != self.layer_index
        self.layer_index = selected
        self.dirty = False
        self.program = program
        node = node_at(program, self.node_index)
        if isinstance(node, Epoch):
            self.show_units(node.settings[self.layer_index])
            for form in self.forms:
                if isinstance(form, (LoomingSize, ArenaMovement)):
                    form.accept(node.settings[self.layer_index].model_dump(mode="json"))
        if isinstance(node, Epoch) and self.feedback is not None:
            self.feedback.accept(
                node.settings[self.layer_index],
                [channel.model_dump(mode="json") for channel in program.input_channels],
            )
        self.message.clear()
        self.message.setVisible(not self.compact)
        self.reset_button.hide()
        self.message.setToolTip("")
        self.committed.emit(program)
        current_assets = {asset.asset_id for asset in program.assets}
        if (
            isolated
            or not set(self.asset_forms).issubset(current_assets)
            or self.pending_profiles
        ):
            self.bind(program, self.node_index, self.layer_index, self.projector)
        return True

    def reset(self) -> None:
        if self.program is not None and self.isEnabled():
            self.bind(self.program, self.node_index, self.layer_index, self.projector)

    def choose_media(self, asset_id: str) -> None:
        if not self.isEnabled():
            return
        if not self.asset_root or not Path(self.asset_root).is_dir():
            self.message.warn("Choose the asset root folder first")
            self.message.show()
            return
        if self.file_dialog is not None:
            self.file_dialog.raise_()
            return
        dialog = file_dialog(self, "Select stimulus media", self.asset_root)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter(
            "Stimulus files (*.png *.tif *.tiff *.jpg *.jpeg *.mp4 *.mkv *.glb *.json)"
        )
        dialog.fileSelected.connect(lambda path: self.set_media_path(asset_id, path))
        dialog.finished.connect(lambda: setattr(self, "file_dialog", None))
        dialog.finished.connect(dialog.deleteLater)
        self.file_dialog = dialog
        open_file_dialog(dialog)

    def set_media_path(self, asset_id: str, path: str) -> None:
        if not self.isEnabled() or asset_id not in self.asset_forms:
            return
        try:
            assert self.program is not None
            node = node_at(self.program, self.node_index)
            assert isinstance(node, Epoch)
            settings = node.settings[self.layer_index]
            selected = resolve_stimulus_file(
                self.asset_root,
                path,
                texture=settings.kind == "texture",
                grating=settings.kind == "texture" and settings.grating,
            )
            if selected.tile_width_mm is not None:
                candidate = self.candidate(replacing_asset=asset_id)
                replace_tile(candidate, self.node_index, self.layer_index, selected)
                program = parse_program_json(
                    json.dumps(candidate), max_bytes=DEFAULT_DOCUMENT_BYTES
                )
                program, self.layer_index = projector_edit(
                    self.program,
                    program,
                    self.node_index,
                    self.layer_index,
                    self.projector,
                )
                self.committed.emit(program)
                self.bind(program, self.node_index, self.layer_index, self.projector)
                self.media_selected.emit()
                return
        except (OSError, ValueError, TypeError) as error:
            self.message.warn(f"Cannot select stimulus file · {error}")
            self.message.show()
            self.message.setToolTip(str(error))
            return
        editor = self.asset_forms[asset_id]
        editor.setText(selected.path)
        self.pending_profiles[asset_id] = selected.profile
        self.mark_changed()
        if self.apply():
            self.media_selected.emit()
