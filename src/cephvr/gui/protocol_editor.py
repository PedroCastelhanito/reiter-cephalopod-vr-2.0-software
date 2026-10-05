"""Canonical local document editing, nested selection and undo/redo ownership."""

from collections.abc import Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from cephvr.gui.batch_insertion import Insertion, insert_batch
from cephvr.gui.epoch_batch import epoch_paths
from cephvr.gui.group_dialog import GroupDialog
from cephvr.gui.group_editor import ExpandedPreview
from cephvr.gui.planner_popups import PlannerPopups
from cephvr.gui.prepared_file_picker import PreparedFilePicker
from cephvr.gui.program_editing import node_at
from cephvr.gui.projector_layers import (
    detach_layer,
    layer_title,
    reorder_projector_layer,
)
from cephvr.gui.protocol_controls import PlannerControls
from cephvr.gui.protocol_document import (
    TrialDraft,
    blank_program,
    node_name,
    review_program,
)
from cephvr.gui.protocol_history import EditHistory, Selection
from cephvr.gui.protocol_nodes import edit_epoch, edit_epoch_metadata
from cephvr.gui.stimulus_presets import (
    add_file_stimulus,
    add_stimulus,
    remove_stimulus,
)
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Fixed,
    Group,
    Program,
)


class ProtocolEditor(PlannerControls):
    changed = pyqtSignal()
    output_preview_requested = pyqtSignal()

    def __init__(self, *, sample: bool = False) -> None:
        super().__init__()
        self.drafts = [
            TrialDraft(
                "Optic flow · sample" if sample else "Trial 1",
                review_program() if sample else blank_program(),
            )
        ]
        self.histories = [EditHistory()]
        self.index = self.node_index = 0
        self.scope: tuple[int, ...] = ()
        self.picker = PreparedFilePicker(self)
        self.picker.selected.connect(
            lambda preset, path, fresh: self.add_file(preset, path, new_epoch=fresh)
        )
        self.delete_dialog: QMessageBox | None = None
        self.popups = PlannerPopups(self)
        self.popups.group_committed.connect(self.commit_group)
        self.trials.addItem(self.drafts[0].name)
        self.trials.setCurrentRow(0)
        self.trials.currentRowChanged.connect(self.select_trial)
        self.add_button.clicked.connect(self.add_trial)
        self.delete_trial_button.clicked.connect(self.delete_trial)
        self.undo_action.triggered.connect(lambda: self.undo(False))
        self.redo_action.triggered.connect(lambda: self.undo(True))
        self.selected_paths: tuple[tuple[int, ...], ...] = ()
        self.timeline.epochs_selected.connect(self.select_epochs)
        self.batch_edit.committed.connect(self.commit_batch)
        self.batch_edit.detail_requested.connect(self.open_details)
        self.batch_edit.epochs_requested.connect(self.select_epochs)
        self.create_batch.generated.connect(self.insert_batch)
        self.timeline.screens_changed.connect(self.refresh_projectors)
        self.name.editingFinished.connect(self.edit_duration)
        self.duration.editingFinished.connect(self.edit_duration)
        for control in (self.name, self.duration):
            control.textEdited.connect(lambda: self.undo_action.setEnabled(True))
        self.parameters.committed.connect(self.commit_parameters)
        self.parameters.more.toggled.connect(self.refresh_scope)
        self.scope_controls.committed.connect(self.commit_scopes)
        self.group_editor.committed.connect(self.commit_parameters)
        self.group_editor.enter.connect(self.enter_group)
        self.back_button.clicked.connect(self.leave_group)
        self.group_button.clicked.connect(self.open_group_dialog)
        self.preview_button.clicked.connect(self.open_preview)
        self.output_preview_button.clicked.connect(self.request_output_preview)
        self.install_menus()
        self.selection_menu.aboutToShow.connect(
            lambda: self.selection_menu.populate(
                self.program, self.path, self.timeline.screens
            )
        )
        self.selection_menu.selected.connect(self.select_projector)
        self.epoch_action.connect(self.edit_epoch)
        self.source_requested.connect(
            lambda preset, fresh: self.choose_stimulus(preset, new_epoch=fresh)
        )
        self.layer_action.connect(
            lambda action: (
                self.remove_stimulus()
                if action == "remove"
                else self.reorder_layer(1 if action == "forward" else -1)
            )
        )
        self.render_selection()

    def select_epochs(self, paths: tuple[tuple[int, ...], ...]) -> None:
        if not self.flush_parameters():
            self.timeline.set_selection(self.selected_paths)
            return
        anchor, index = self.timeline.anchor, self.timeline.index
        self.selected_paths = paths
        if paths:
            self.scope, self.node_index = paths[0][:-1], paths[0][-1]
            self.render_selection()
        self.timeline.set_selection(paths)
        self.timeline.anchor, self.timeline.index = anchor, index
        self.timeline.fit_lanes()
        self.batch_edit.bind(self.program, paths, self.timeline.screens)
        self.modes.setCurrentIndex(1)
        self.advanced.hide()

    def commit_batch(self, program: Program) -> None:
        if self.isEnabled():
            paths = self.selected_paths
            self.commit(program)
            self.selected_paths = paths
            self.timeline.set_selection(paths)
            self.batch_edit.bind(program, paths, self.timeline.screens)

    def insert_batch(self, template: Program, placement: Insertion) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            program, paths = insert_batch(self.program, template, self.path, placement)
            self.commit(program, selected=paths[0][0], scope=())
            self.select_epochs(paths)
            self.modes.setCurrentIndex(1)
        except ValueError as error:
            self.create_batch.summary.setText(str(error))

    def open_details(self, face: str, layer: int) -> None:
        self.modes.setCurrentIndex(1)
        self.select_projector(self.node_index, face, layer)
        self.advanced.show()

    @property
    def source_dialog(self) -> QFileDialog | None:
        return self.picker.dialog

    @property
    def target_screens(self) -> tuple[str, ...]:
        return (
            (self.projector_layers.face,)
            if self.projector_layers.face
            else self.timeline.screens
        )

    def select_projector(self, index: int, screen: str, layer: int) -> None:
        if not self.flush_parameters():
            self.projector_layers.bind(
                self.program,
                self.path,
                self.timeline.screens,
                self.parameters.layer_index,
            )
            return
        self.close_source_dialog()
        self.node_index, self.projector_layers.face = index, screen
        self.render_selection(layer=layer)
        self.advanced.show()

    def delete_trial(self) -> None:
        if not self.isEnabled() or self.delete_dialog is not None:
            return
        draft = self.drafts[self.index]
        dialog = QMessageBox(
            QMessageBox.Icon.Question,
            "Delete trial",
            f'Delete "{draft.name}" from the planner? Saved files are kept.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            self,
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)

        def finish(result: int) -> None:
            self.delete_dialog = None
            if (
                result != int(QMessageBox.StandardButton.Yes)
                or not self.isEnabled()
                or self.drafts[self.index] is not draft
            ):
                return
            self.close_source_dialog()
            self.drafts.pop(self.index)
            self.histories.pop(self.index)
            if not self.drafts:
                self.drafts.append(TrialDraft("Trial 1", blank_program()))
                self.histories.append(EditHistory())
            self.index = min(self.index, len(self.drafts) - 1)
            self.trials.blockSignals(True)
            self.trials.clear()
            self.trials.addItems([d.name for d in self.drafts])
            self.trials.setCurrentRow(self.index)
            self.trials.blockSignals(False)
            self.scope, self.node_index = (), 0
            self.render_selection()
            self.changed.emit()

        dialog.finished.connect(finish)
        dialog.finished.connect(dialog.deleteLater)
        self.delete_dialog = dialog
        dialog.open()

    @property
    def program(self) -> Program:
        return self.drafts[self.index].program

    @property
    def path(self) -> tuple[int, ...]:
        return self.scope + (self.node_index,)

    def snapshot(self) -> Selection:
        return Selection(
            self.program,
            self.scope,
            self.node_index,
            self.projector_layers.layer,
            self.projector_layers.face,
        )

    def error(self, error: object) -> None:
        self.feedback.setText(str(error))
        self.feedback.show()

    def commit(
        self,
        program: Program,
        *,
        selected: int | None = None,
        layer: int | None = None,
        refresh: bool = True,
        scope: tuple[int, ...] | None = None,
    ) -> None:
        if program != self.program:
            self.histories[self.index].push(self.snapshot())
            self.drafts[self.index].program = program
        if scope is not None:
            self.scope = scope
        if selected is not None:
            self.node_index = selected
        if refresh:
            self.render_selection(layer=layer)
        else:
            self.parameters.program = program
            self.group_editor.program = program
            self.refresh_scope()
            self.timeline.set_program(
                program,
                self.node_index,
                self.scope,
                self.projector_layers.face,
                self.projector_layers.layer,
            )
            self.refresh_history()
        self.timeline.set_selection(self.selected_paths)
        self.batch_edit.bind(program, self.selected_paths, self.timeline.screens)
        self.sequence_summary.setText(self.timeline.summary())
        self.changed.emit()

    def refresh_history(self) -> None:
        history = self.histories[self.index]
        self.undo_action.setEnabled(bool(history.past) or self.parameters.dirty)
        self.redo_action.setEnabled(bool(history.future))

    def undo(self, redo: bool = False) -> None:
        if not self.isEnabled():
            return
        self.close_source_dialog()
        node = node_at(self.program, self.path)
        pending = isinstance(node, Epoch) and (
            self.name.text().strip().replace(" ", "_") != node.epoch_id
            or (
                isinstance(node.duration, Fixed)
                and self.duration.text().strip() != node.duration.duration.seconds
            )
        )
        if self.parameters.dirty or self.group_editor.dirty or pending:
            self.render_selection()
            return
        state = self.histories[self.index].travel(self.snapshot(), redo)
        if state:
            self.drafts[self.index].program = state.program
            self.scope, self.node_index = state.scope, state.index
            self.projector_layers.face = state.screen
            self.render_selection(layer=state.layer)
            self.changed.emit()

    def set_program(self, program: Program) -> None:
        self.close_source_dialog()
        self.drafts[self.index].program = program
        self.histories[self.index] = EditHistory()
        self.scope, self.node_index = (), 0
        self.selected_paths = ()
        self.render_selection()
        self.changed.emit()

    def select_trial(self, index: int) -> None:
        self.close_source_dialog()
        if index < 0:
            return
        if not self.flush_parameters():
            self.trials.blockSignals(True)
            self.trials.setCurrentRow(self.index)
            self.trials.blockSignals(False)
            return
        self.index, self.node_index, self.scope = index, 0, ()
        self.selected_paths = ()
        self.render_selection()
        self.changed.emit()

    def add_trial(self) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        number = 1
        while f"Trial {number}" in {draft.name for draft in self.drafts}:
            number += 1
        name = f"Trial {number}"
        self.drafts.append(TrialDraft(name, blank_program()))
        self.histories.append(EditHistory())
        self.trials.addItem(name)
        self.trials.setCurrentRow(len(self.drafts) - 1)

    def select_node(self, index: int) -> None:
        self.close_source_dialog()
        if index < 0 or not self.flush_parameters():
            return
        self.node_index = index
        self.render_selection()

    def render_selection(self, *, layer: int | None = None) -> None:
        self.create_batch.bind_trial(self.program)
        node = node_at(self.program, self.path)
        self.bind_metadata(node)
        paths = epoch_paths(self.program)
        if self.path not in self.selected_paths or not all(
            p in paths for p in self.selected_paths
        ):
            self.selected_paths = tuple(
                p for p in paths if p == self.path or p[: len(self.path)] == self.path
            )
        self.batch_edit.bind(self.program, self.selected_paths, self.timeline.screens)
        self.projector_layers.bind(
            self.program, self.path, self.timeline.screens, layer
        )
        self.timeline.set_program(
            self.program,
            self.node_index,
            self.scope,
            self.projector_layers.face,
            self.projector_layers.layer,
        )
        self.timeline.set_selection(self.selected_paths)
        self.context.setText(
            f"{self.projector_layers.face or 'All projectors'}"
            + (
                " (inactive)"
                if self.projector_layers.face
                and self.projector_layers.face not in self.timeline.screens
                else ""
            )
            + (
                " → "
                + layer_title(
                    self.program, node.settings[self.projector_layers.layer]
                ).split(" · ")[0]
                if isinstance(node, Epoch) and self.projector_layers.layer >= 0
                else ""
            )
        )
        self.context.setVisible(isinstance(node, Epoch))
        self.parameters.bind(
            self.program,
            self.path,
            self.projector_layers.layer,
            self.projector_layers.face,
        )
        self.group_editor.bind(self.program, self.path)
        self.refresh_scope()
        rig_arena = (
            isinstance(node, Epoch)
            and self.projector_layers.layer >= 0
            and node.settings[self.projector_layers.layer].kind == "arena"
            and bool(self.projector_layers.face)
        )
        self.parameters.setEnabled(not rig_arena)
        self.details.setText(
            "Arena is rig-wide. Choose All projectors to edit it."
            if rig_arena
            else "Blank interval · configured background"
            if isinstance(node, Epoch) and self.projector_layers.layer < 0
            else ""
        )
        self.details.setVisible(bool(self.details.text()))
        self.rename_action.setEnabled(
            isinstance(node, Epoch) and len(self.selected_paths) == 1
        )
        self.back_button.setVisible(bool(self.scope))
        self.breadcrumb.setVisible(bool(self.scope))
        names = [
            node_name(node_at(self.program, self.scope[: i + 1]))
            for i in range(len(self.scope))
        ]
        self.breadcrumb.setText("Trial" + (" / " + " / ".join(names) if names else ""))
        self.sequence_summary.setText(self.timeline.summary())
        self.feedback.hide()
        self.refresh_history()

    def refresh_projectors(self) -> None:
        self.projector_layers.bind(
            self.program, self.path, self.timeline.screens, self.projector_layers.layer
        )
        self.refresh_scope()
        self.create_batch.composer.set_screens(self.timeline.screens)
        self.batch_edit.bind(self.program, self.selected_paths, self.timeline.screens)

    def refresh_scope(self) -> None:
        if not hasattr(self, "drafts"):
            return
        if self.projector_layers.face or self.projector_layers.layer < 0:
            self.scope_controls.hide()
            return
        self.scope_controls.bind(
            self.program, self.path, self.projector_layers.layer, self.timeline.screens
        )
        self.scope_controls.setVisible(self.parameters.more.isChecked())

    def edit_duration(self) -> None:
        if self.isEnabled():
            if self.apply_epoch_fields():
                self.name.setReadOnly(True)

    def apply_epoch_fields(self) -> bool:
        try:
            candidate = edit_epoch_metadata(
                self.program, self.path, self.name.text(), self.duration.text()
            )
        except (ValueError, TypeError) as error:
            self.error(error)
            return False
        if candidate != self.program:
            self.commit(candidate, refresh=False)
            self.parameters.program = candidate
        self.feedback.hide()
        return True

    def flush_parameters(self) -> bool:
        if self.batch_edit.dirty:
            self.error("Apply or discard the selected epoch changes first")
            return False
        if self.parameters.dirty and not self.parameters.apply():
            return False
        if self.group_editor.dirty and not self.group_editor.apply():
            return False
        return self.apply_epoch_fields()

    def select_layer(self, index: int) -> None:
        if index >= 0 and self.flush_parameters():
            self.render_selection(layer=index)

    def commit_parameters(self, program: Program) -> None:
        isolated = self.parameters.layer_index != self.projector_layers.layer
        self.commit(program, refresh=isolated, layer=self.parameters.layer_index)
        self.refresh_scope()

    def commit_scopes(self, program: Program) -> None:
        if self.parameters.dirty:
            self.error(
                "Finish or undo the pending parameter edit before changing screen scope"
            )
            self.refresh_scope()
            return
        self.commit(program, layer=self.projector_layers.layer)

    def perform(self, action: Callable[[], Program]) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            self.commit(action())
        except (ValueError, TypeError, OSError) as error:
            self.error(error)

    def add_stimulus(self, preset: str) -> None:
        self.perform(
            lambda: add_stimulus(self.program, self.path, preset, self.target_screens)
        )
        node = node_at(self.program, self.path)
        if isinstance(node, Epoch):
            self.render_selection(layer=len(node.settings) - 1)

    def remove_stimulus(self) -> None:
        if (
            not self.isEnabled()
            or not self.flush_parameters()
            or self.projector_layers.layer < 0
        ):
            return
        node = node_at(self.program, self.path)
        if (
            isinstance(node, Epoch)
            and node.settings[self.projector_layers.layer].kind == "arena"
            and self.projector_layers.face
        ):
            self.error("Choose All projectors to remove the rig-wide arena")
            return
        program, layer = detach_layer(
            self.program,
            self.path,
            self.projector_layers.layer,
            self.projector_layers.face,
        )
        self.perform(lambda: remove_stimulus(program, self.path, layer))

    def reorder_layer(self, delta: int) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            if self.projector_layers.layer < 0:
                return
            program, layer = reorder_projector_layer(
                self.program,
                self.path,
                self.projector_layers.layer,
                self.projector_layers.face,
                delta,
            )
            self.commit(program, layer=layer)
        except (ValueError, IndexError) as error:
            self.error(error)

    def edit_epoch(self, operation: str) -> None:
        if len(self.selected_paths) > 1 and operation != "add":
            self.error("Select one source epoch for this structural action")
            return
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            program, index = edit_epoch(self.program, self.path, operation)
            self.commit(program, selected=index)
        except (ValueError, TypeError) as error:
            self.error(error)

    def enter_group(self) -> None:
        if not self.flush_parameters() or not isinstance(
            node_at(self.program, self.path), Group
        ):
            return
        self.scope, self.node_index = self.path, 0
        self.render_selection()

    def leave_group(self) -> None:
        if self.scope and self.flush_parameters():
            self.node_index, self.scope = self.scope[-1], self.scope[:-1]
            self.render_selection()

    def close_source_dialog(self) -> None:
        for dialog in (self.source_dialog, self.group_dialog, self.delete_dialog):
            if dialog is not None:
                dialog.reject()

    def choose_stimulus(self, preset: str, *, new_epoch: bool = False) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            self.picker.open(preset, self.parameters.asset_root, new_epoch)
        except ValueError as error:
            self.error(error)

    def add_file(self, preset: str, path: str, *, new_epoch: bool = False) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            program, index = (
                edit_epoch(self.program, self.path, "add")
                if new_epoch
                else (self.program, self.node_index)
            )
            program = add_file_stimulus(
                program,
                self.scope + (index,),
                preset,
                self.target_screens,
                self.parameters.asset_root,
                path,
            )
            node = node_at(program, self.scope + (index,))
            assert isinstance(node, Epoch)
            self.commit(program, selected=index, layer=len(node.settings) - 1)
        except (OSError, ValueError, TypeError) as error:
            self.error(error)

    @property
    def group_dialog(self) -> GroupDialog | None:
        return self.popups.group

    @property
    def expanded_preview(self) -> ExpandedPreview | None:
        return self.popups.expanded

    def commit_group(self, original: Program, result: Program, selected: int) -> None:
        if self.isEnabled() and self.program == original:
            self.commit(result, selected=selected)

    def open_group_dialog(self) -> None:
        if self.isEnabled() and self.flush_parameters():
            self.popups.open_group(self.program, self.scope, self.node_index)

    def open_preview(self) -> None:
        if self.flush_parameters():
            self.popups.open_preview(self.program)

    def request_output_preview(self) -> None:
        if self.isEnabled() and self.flush_parameters():
            self.output_preview_requested.emit()
