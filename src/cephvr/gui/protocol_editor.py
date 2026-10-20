"""Canonical protocol selection, transactions and history for the unified editor."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from cephvr.gui.arena_limits import boundary_document, geometry_description
from cephvr.gui.batch_insertion import Insertion, insert_batch
from cephvr.gui.group_editor import ExpandedPreview
from cephvr.gui.planner_popups import PlannerPopups
from cephvr.gui.program_editing import node_at
from cephvr.gui.protocol_batches import (
    flat_group,
    generated_batch,
    grouped_program,
    subgroup_paths,
)
from cephvr.gui.protocol_controls import PlannerControls
from cephvr.gui.protocol_document import TrialDraft, blank_program, review_program
from cephvr.gui.protocol_groups import make_group
from cephvr.gui.protocol_history import EditHistory, Selection
from cephvr.gui.protocol_nodes import edit_epoch
from cephvr.gui.protocol_timeline import ProgramTimeline
from cephvr.gui.subgroup_structure import edit_subgroup
from cephvr.visual_stimulus.config.models.program_model import (
    ArenaBoundary,
    ArenaFileRegion,
    ArenaSettings,
    Epoch,
    Group,
    Program,
    TrialArenaBoundaries,
)


class ProtocolEditor(PlannerControls):
    changed = pyqtSignal()
    output_preview_requested = pyqtSignal()

    def __init__(self, *, sample: bool = False) -> None:
        super().__init__()
        self.drafts = [
            TrialDraft(
                "Optic flow · sample" if sample else "Trial 1",
                grouped_program(review_program() if sample else blank_program()),
            )
        ]
        self.configuration_schedule_empty = False
        self.histories = [EditHistory()]
        self.index = self.node_index = 0
        self.scope: tuple[int, ...] = ()
        self.selected_paths: tuple[tuple[int, ...], ...] = ()
        self.delete_dialog: QMessageBox | None = None
        self.popups = PlannerPopups(self)
        self.trials.addItem(self.drafts[0].name)
        self.trials.setCurrentRow(0)
        self.trials.currentRowChanged.connect(self.select_trial)
        self.add_button.clicked.connect(self.add_trial)
        self.trials.delete_requested.connect(self.delete_trial)
        self.undo_action.triggered.connect(lambda: self.undo(False))
        self.redo_action.triggered.connect(lambda: self.undo(True))
        self.timeline.block_actions.add.clicked.connect(self.add_group)
        self.group_action.connect(self.edit_group)
        for timeline in (self.timeline, self.hierarchy.contents):
            timeline.block_actions.remove_requested.connect(self.remove_block)
            timeline.epochs_selected.connect(self.select_epochs)
            timeline.context_selected.connect(
                lambda paths: self.select_epochs(paths, open_group=False)
            )
        self.hierarchy.contents.batch_selected.connect(self.select_epochs)
        self.subgroup.committed.connect(self.commit_subgroup)
        self.subgroup.changed.connect(self.refresh_history)
        self.timeline.screens_changed.connect(self.refresh_projectors)
        self.group_editor.committed.connect(self.commit_group)
        self.group_editor.changed.connect(self.refresh_history)
        self.output_preview_button.clicked.connect(self.request_output_preview)
        self.install_menus()
        self.epoch_action.connect(self.edit_epoch)
        self.subgroup.composer.rows[""].parameters.bound.connect(self.bind_arena_limits)
        self.render_selection()

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
            0,
            "",
            self.selected_paths,
            self.drafts[self.index].arena_boundaries_json,
        )

    def error(self, error: object) -> None:
        self.feedback.warn(error)

    def commit(
        self,
        program: Program,
        *,
        selected: int | None = None,
        scope: tuple[int, ...] | None = None,
        paths: tuple[tuple[int, ...], ...] | None = None,
    ) -> None:
        if program != self.program:
            self.histories[self.index].push(self.snapshot())
            self.drafts[self.index].program = program
        if scope is not None:
            self.scope = scope
        if selected is not None:
            self.node_index = selected
        if paths is not None:
            self.selected_paths = paths
        self.render_selection()
        self.changed.emit()

    def commit_group(self, program: Program) -> None:
        if not self.subgroup.dirty:
            self.commit(program)
            return
        # Group fields change independently of the in-progress epoch template.
        if program != self.program:
            self.histories[self.index].push(self.snapshot())
            self.drafts[self.index].program = program
        self.subgroup.source = program
        self.update_timelines()
        self.refresh_history()
        self.changed.emit()

    def commit_subgroup(
        self, program: Program, paths: tuple[tuple[int, ...], ...]
    ) -> None:
        if self.isEnabled():
            if self.subgroup.committing:
                if program != self.program:
                    self.histories[self.index].push(self.snapshot())
                    self.drafts[self.index].program = program
                self.scope, self.node_index = paths[0][:-1], paths[0][-1]
                self.selected_paths = paths
                self.subgroup.accept(program, paths)
                self.update_timelines()
                self.refresh_history()
                self.changed.emit()
            else:
                self.commit(
                    program, scope=paths[0][:-1], selected=paths[0][-1], paths=paths
                )

    def render_selection(self) -> None:
        if not self.scope:
            root = node_at(self.program, (self.node_index,))
            if isinstance(root, Group):
                self.scope, self.node_index = (self.node_index,), 0
                self.selected_paths = (self.path,)
        try:
            valid = self.path in self.selected_paths
            for path in self.selected_paths:
                node_at(self.program, path)
        except (IndexError, ValueError):
            valid = False
        if not valid:
            self.selected_paths = (self.path,)
        if flat_group(self.program, self.scope):
            self.selected_paths = subgroup_paths(self.program, self.selected_paths)
            self.subgroup.bind(self.program, self.selected_paths, self.timeline.screens)
        else:
            self.subgroup.source = None
        self.update_timelines()
        self.refresh_history()

    def update_timelines(self) -> None:
        self.timeline.block_actions.enabled = all(
            isinstance(node, Group) for node in self.program.sequence
        )
        self.timeline.set_program(self.program, self.path[0])
        self.timeline.set_selection(
            tuple(dict.fromkeys((p[0],) for p in self.selected_paths))
        )
        self.hierarchy.bind(
            self.program,
            self.scope,
            self.node_index,
            self.selected_paths,
            self.timeline.screens,
        )
        self.bind_arena_limits()
        self.arrange_mode()
        self.sequence_summary.setText(self.timeline.summary())
        self.fit_timeline_card()

    def bind_arena_limits(self) -> None:
        draft = self.drafts[self.index]
        document = boundary_document(self.program, draft.arena_boundaries_json)
        draft.arena_boundaries_json = document.model_dump_json()
        parameters = self.subgroup.composer.rows[""].parameters
        limits = parameters.arena_limits
        if limits is None or parameters.program is None:
            return
        epoch = node_at(parameters.program, parameters.node_index)
        if not isinstance(epoch, Epoch):
            return
        setting = epoch.settings[parameters.layer_index]
        if not isinstance(setting, ArenaSettings):
            return
        binding = next(
            (b for b in document.bindings if b.instance_id == setting.instance_id),
            ArenaBoundary(
                instance_id=setting.instance_id,
                world_frame_id=setting.world_frame_id,
                region=ArenaFileRegion(kind="arena_file"),
            ),
        )
        limits.bind(
            binding,
            geometry_description(parameters.program, setting, parameters.asset_root),
        )
        try:
            limits.committed.disconnect(self.commit_arena_limits)
            limits.changed.disconnect(self.refresh_history)
        except TypeError:
            pass
        limits.committed.connect(self.commit_arena_limits)
        limits.changed.connect(self.refresh_history)

    def commit_arena_limits(self, binding: ArenaBoundary) -> None:
        draft = self.drafts[self.index]
        document = TrialArenaBoundaries.model_validate_json(draft.arena_boundaries_json)
        bindings = tuple(
            b for b in document.bindings if b.instance_id != binding.instance_id
        ) + (binding,)
        raw = document.model_copy(update={"bindings": bindings}).model_dump_json()
        if raw != draft.arena_boundaries_json:
            self.histories[self.index].push(self.snapshot())
            draft.arena_boundaries_json = raw
            self.refresh_history()
            self.changed.emit()

    def select_epochs(
        self, paths: tuple[tuple[int, ...], ...], *, open_group: bool = True
    ) -> None:
        if not paths:
            return
        source = self.sender()
        anchor = source.anchor if isinstance(source, ProgramTimeline) else 0
        index = source.index if isinstance(source, ProgramTimeline) else 0
        if not self.flush_parameters():
            self.update_timelines()
            return
        self.close_source_dialog()
        chosen = paths[0]
        self.scope, self.node_index = chosen[:-1], chosen[-1]
        self.selected_paths = paths
        if (
            open_group
            and len(paths) == 1
            and isinstance(node_at(self.program, chosen), Group)
        ):
            self.scope, self.node_index = chosen, 0
            first = (*self.scope, 0)
            self.selected_paths = (first,)
            self.hierarchy.contents.setFocus()
        self.render_selection()
        if isinstance(source, ProgramTimeline) and source.scope == chosen[:-1]:
            source.anchor, source.index = anchor, index
            source.reveal_selection()

    def flush_parameters(self) -> bool:
        limits = self.subgroup.composer.rows[""].parameters.arena_limits
        if limits is not None and not limits.apply():
            self.error("Correct the arena wall clearance before continuing")
            return False
        if self.subgroup.dirty:
            self.subgroup.apply()
            if self.subgroup.dirty:
                return False
        return not self.group_editor.dirty or self.group_editor.apply()

    def refresh_history(self) -> None:
        if not hasattr(self, "histories"):
            return
        history = self.histories[self.index]
        limits = self.subgroup.composer.rows[""].parameters.arena_limits
        self.undo_action.setEnabled(
            bool(history.past)
            or self.subgroup.dirty
            or self.group_editor.dirty
            or (limits is not None and limits.dirty)
        )
        self.redo_action.setEnabled(bool(history.future))

    def undo(self, redo: bool = False) -> None:
        if not self.isEnabled():
            return
        self.close_source_dialog()
        limits = self.subgroup.composer.rows[""].parameters.arena_limits
        if limits is not None and limits.dirty:
            limits.dirty = False
            self.bind_arena_limits()
            self.refresh_history()
            return
        if self.subgroup.dirty:
            self.subgroup.discard()
            self.refresh_history()
            return
        if self.group_editor.dirty:
            self.render_selection()
            return
        state = self.histories[self.index].travel(self.snapshot(), redo)
        if state:
            self.drafts[self.index].program = state.program
            self.drafts[self.index].arena_boundaries_json = state.arena_boundaries_json
            self.scope, self.node_index, self.selected_paths = (
                state.scope,
                state.index,
                state.paths,
            )
            self.render_selection()
            self.changed.emit()

    def set_program(self, program: Program) -> None:
        self.close_source_dialog()
        self.drafts[self.index].program = program
        self.histories[self.index] = EditHistory()
        self.scope, self.node_index, self.selected_paths = (), 0, ()
        self.render_selection()
        self.changed.emit()

    def refresh_projectors(self) -> None:
        self.subgroup.composer.set_screens(self.timeline.screens)
        self.update_timelines()

    def add_subgroup(self) -> None:
        if not self.isEnabled() or not flat_group(self.program, self.scope):
            return
        try:
            template = self.subgroup.reference()
            if self.subgroup.dirty:
                self.subgroup.apply()
                if self.subgroup.dirty:
                    return
            if not self.flush_parameters():
                return
            program, paths = insert_batch(
                self.program,
                generated_batch(template),
                self.path,
                Insertion(),
                scope=self.scope,
            )
            self.commit_subgroup(program, paths)
            self.hierarchy.contents.setFocus()
        except (ValueError, TypeError, OSError) as error:
            self.error(error)

    def edit_epoch(self, operation: str) -> None:
        if operation == "add":
            self.add_subgroup()
            return
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            if flat_group(self.program, self.scope):
                program, paths = edit_subgroup(
                    self.program, self.selected_paths, operation
                )
                self.commit_subgroup(program, paths)
            elif (
                not self.scope
                and len(self.selected_paths) == 1
                and isinstance(node_at(self.program, self.path), Group)
            ):
                program, index = edit_epoch(self.program, self.path, operation)
                self.commit(program, selected=index, paths=((index,),))
        except (ValueError, TypeError) as error:
            self.error(error)

    def remove_block(self, paths: tuple[tuple[int, ...], ...]) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            if len(paths[0]) == 1:
                program, index = edit_epoch(self.program, paths[0], "remove")
                self.commit(program, scope=(), selected=index, paths=((index,),))
            else:
                program, selected = edit_subgroup(
                    self.program, subgroup_paths(self.program, paths), "remove"
                )
                self.commit_subgroup(program, selected)
        except (ValueError, TypeError, IndexError) as error:
            self.error(error)

    def edit_group(self, operation: str) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        root = self.path[0]
        if not isinstance(self.program.sequence[root], Group):
            return
        try:
            program, index = edit_epoch(self.program, (root,), operation)
            self.commit(program, scope=(), selected=index, paths=((index,),))
        except (ValueError, TypeError) as error:
            self.error(error)

    def add_stimulus(self, preset: str) -> None:
        from cephvr.gui.stimulus_presets import add_stimulus

        if self.isEnabled() and self.flush_parameters():
            self.commit(
                add_stimulus(self.program, self.path, preset, self.timeline.screens)
            )

    @property
    def expanded_preview(self) -> ExpandedPreview | None:
        return self.popups.expanded

    def close_source_dialog(self) -> None:
        self.subgroup.composer.close_file_dialogs()
        if self.delete_dialog is not None:
            self.delete_dialog.reject()

    def delete_trial(self, target: int | None = None) -> None:
        if not self.isEnabled() or self.delete_dialog is not None:
            return
        target = self.index if target is None else target
        if not 0 <= target < len(self.drafts):
            return
        if target != self.index and not self.flush_parameters():
            return
        draft = self.drafts[target]
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
                or not any(item is draft for item in self.drafts)
            ):
                return
            self.close_source_dialog()
            removed = next(i for i, item in enumerate(self.drafts) if item is draft)
            self.drafts.pop(removed)
            self.histories.pop(removed)
            if self.drafts and removed == len(self.drafts):
                self.drafts[-1].gap_after_seconds = ""
            if removed < self.index:
                self.index -= 1
            if not self.drafts:
                self.drafts.append(
                    TrialDraft("Trial 1", grouped_program(blank_program()))
                )
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
        if self.configuration_schedule_empty and len(self.drafts) == 1:
            self.drafts[0].name = "Trial 1"
            item = self.trials.item(0)
            if item is not None:
                item.setText("Trial 1")
            self.configuration_schedule_empty = False
            self.changed.emit()
            return
        number = 1
        while f"Trial {number}" in {draft.name for draft in self.drafts}:
            number += 1
        name = f"Trial {number}"
        self.drafts.append(TrialDraft(name, grouped_program(blank_program())))
        self.histories.append(EditHistory())
        self.trials.addItem(name)
        self.trials.setCurrentRow(len(self.drafts) - 1)

    def add_group(self) -> None:
        if not self.isEnabled() or not self.flush_parameters():
            return
        try:
            program, index = edit_epoch(
                self.program, (len(self.program.sequence) - 1,), "add"
            )
            program, index = make_group(program, (), index, index, 1, False)
            self.commit(
                program,
                scope=(index,),
                selected=0,
                paths=((index, 0),),
            )
        except (ValueError, TypeError) as error:
            self.error(error)

    def navigate_group(self, scope: tuple[int, ...]) -> None:
        if not self.flush_parameters():
            return
        previous = self.scope
        self.scope = scope
        self.node_index = (
            previous[len(scope)]
            if previous[: len(scope)] == scope and len(previous) > len(scope)
            else 0
        )
        self.selected_paths = (self.path,)
        self.render_selection()

    def enter_group(self) -> None:
        if isinstance(node_at(self.program, self.path), Group):
            self.navigate_group(self.path)

    def open_preview(self) -> None:
        if self.flush_parameters():
            self.popups.open_preview(self.program)

    def request_output_preview(self) -> None:
        if self.isEnabled() and self.flush_parameters():
            self.output_preview_requested.emit()
