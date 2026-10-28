"""One reference-composer form for creating and editing selected epoch subgroups."""

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from cephvr.gui.batch_create import BatchCreate
from cephvr.gui.epoch_selection import SelectionComposer
from cephvr.gui.notices import passive_validation
from cephvr.gui.program_editing import data_node, drop_unused_assets, node_at, validate
from cephvr.gui.protocol_batches import generated_batch
from cephvr.gui.subgroup_operations import update_subgroup
from cephvr.gui.subgroup_repetitions import rebuild_repetitions
from cephvr.visual_stimulus.config.models.authoring import SubgroupDraft
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Fixed,
    Program,
)


class SubgroupEditor(BatchCreate):
    compact_random = True
    committed = pyqtSignal(object, object)
    changed = pyqtSignal()

    def __init__(self) -> None:
        self._binding = True
        self.source: Program | None = None
        self.paths: tuple[tuple[int, ...], ...] = ()
        self.baseline: Program | None = None
        self._reference: Program | None = None
        self._texts: tuple[str, ...] = ()
        self._rules = SubgroupDraft()
        self._previewing = False
        self.committing = False
        super().__init__(
            append_only=True, composer=SelectionComposer(), show_copies=False
        )
        self.summary.hide()
        self.add_button.clicked.disconnect()
        self.add_button.hide()
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.auto_apply)
        application = QApplication.instance()
        assert isinstance(application, QApplication)
        application.focusChanged.connect(self.finish_edit)
        self.composer.duration.editingFinished.connect(self.queue_update)
        self.composer.batch_label.editingFinished.connect(self.queue_update)
        self.parameter_fields[3].findChildren(QLabel)[0].setText("Name")
        self.composer.batch_label.setPlaceholderText("Optional subgroup name")
        self.composer.changed.connect(self.changed.emit)
        for control in (
            self.composer.duration,
            self.composer.batch_label,
        ):
            control.textEdited.connect(self.changed.emit)
        self._binding = False

    def add_variation_from(self, reference: Program) -> None:
        super().add_variation_from(reference)
        row = self.rows[-1]
        for control in (
            row.values,
            row.asset_folder.editor,
            *row.random_fields.values(),
        ):
            control.editingFinished.connect(self.queue_update)
        row.asset_folder.path_selected.connect(self.queue_update)

    def queue_update(self) -> None:
        if not self._binding and not self._previewing:
            self.update_timer.start(0)

    def auto_apply(self) -> None:
        if not self._binding and self.dirty:
            with passive_validation():
                self.apply()
            self.update_timer.stop()

    def finish_edit(self, previous: QWidget | None, current: QWidget | None) -> None:
        if previous is not None and self.isAncestorOf(previous):
            self.queue_update()

    def text_values(self) -> tuple[str, ...]:
        return (
            self.composer.duration.text(),
            self.composer.batch_label.text(),
        )

    def random_count(self) -> int:
        return max(1, len(self.paths))

    def rule_draft(self, *, samples: bool = True) -> SubgroupDraft:
        rules = tuple(row.draft() for row in self.rows)
        if not samples:
            rules = tuple(
                rule.model_copy(update={"sample_key": (), "samples": ()})
                for rule in rules
            )
        return SubgroupDraft(enabled=bool(rules), rules=rules)

    @property
    def dirty(self) -> bool:
        return self.source is not None and (
            self.text_values() != self._texts
            or self.composer.program != self._reference
            or self.rule_draft(samples=False) != self._rules
            or any(row.parameters.dirty for row in self.composer.rows.values())
        )

    def bind(
        self,
        program: Program,
        paths: tuple[tuple[int, ...], ...],
        screens: tuple[str, ...],
    ) -> None:
        self._binding = True
        self.update_timer.stop()
        self.source, self.paths = program, paths
        self.composer.close_file_dialogs()
        for row in tuple(self.rows):
            self.remove_variation(row)
        if paths:
            composer = self.composer
            assert isinstance(composer, SelectionComposer)
            composer.bind_epoch(program, paths[0], screens)
            self.repetitions.setText("1")
            self._reference = composer.program
            epoch = node_at(program, paths[0])
            self.baseline = composer.program.model_copy(update={"sequence": (epoch,)})
            self._texts = self.text_values()
            assert isinstance(epoch, Epoch)
            draft = epoch.subgroup_draft or SubgroupDraft()
            for rule in draft.rules if draft.enabled else ():
                self.add_variation_from(composer.program)
                self.rows[-1].restore(rule)
            self._rules = self.rule_draft(samples=False)
        self.notice.clear()
        self._binding = False
        self.refresh_preview()

    def queue_preview(self) -> None:
        if not self._binding and not self._previewing:
            super().queue_preview()
            self.changed.emit()
            if not isinstance(QApplication.focusWidget(), QLineEdit):
                self.queue_update()

    def refresh_preview(self) -> None:
        if self._binding:
            return
        if self.rows:
            self._previewing = True
            try:
                super().refresh_preview()
            finally:
                self._previewing = False
        self.summary.hide()

    def reference(self) -> Program:
        reference = self.composer.value()
        epoch = reference.sequence[0]
        assert isinstance(epoch, Epoch)
        original = (
            node_at(self.source, self.paths[0]) if self.source and self.paths else epoch
        )
        duration = (
            original.duration
            if isinstance(original, Epoch) and not isinstance(original.duration, Fixed)
            else self.composer.duration_value()
        )
        return reference.model_copy(
            update={
                "sequence": (
                    epoch.model_copy(
                        update={
                            "duration": duration,
                            "batch_label": self.composer.batch_label.text().strip(),
                        }
                    ),
                )
            }
        )

    def generate(self) -> None:
        self.apply()

    def apply(self) -> None:
        if (
            not self.isEnabled()
            or not self.dirty
            or self.source is None
            or self.baseline is None
            or not self.paths
        ):
            return
        try:
            identities = {
                node.batch_id
                for path in self.paths
                if isinstance(node := node_at(self.source, path), Epoch)
            }
            rules_changed = self.rule_draft(samples=False) != self._rules
            if rules_changed and len(identities) > 1:
                # Rules are stored per batch identity; a mixed selection cannot keep them.
                raise ValueError("Select one subgroup to change its variation rules")
            reference = self.reference()
            candidate = self.candidate() if self.rows else None
            for row in self.rows:
                if row.parameter.currentData() != "Asset":
                    continue
                kinds = tuple(
                    sorted(
                        {
                            "grating"
                            if (setting := row.settings[row.targets[i][2]]).kind
                            == "texture"
                            and setting.grating
                            else setting.kind
                            for i in row.target_indices()
                        }
                    )
                )
                assets = row.asset_folder.load(
                    self.source, self.composer.asset_root, kinds
                )
                known = {asset.asset_id: asset for asset in reference.assets}
                for asset in assets:
                    if asset.asset_id in known and known[asset.asset_id] != asset:
                        raise ValueError(
                            "Asset variation identity conflicts with an existing asset"
                        )
                    known[asset.asset_id] = asset
                reference = reference.model_copy(
                    update={"assets": tuple(known.values())}
                )
            variants = (
                generated_batch(candidate)
                if candidate is not None
                and rules_changed
                and any(row.method.currentData() != 2 for row in self.rows)
                else None
            )
            count = len(variants.sequence) if variants else len(self.paths)
            program, paths = update_subgroup(
                self.source,
                self.paths,
                self.baseline,
                reference,
                count,
                variants=variants,
            )
            if len(identities) == 1:
                data = program.model_dump(mode="json")
                draft = self.rule_draft()
                for index, path in enumerate(paths):
                    data_node(data, path)["subgroup_draft"] = (
                        draft.model_dump(mode="json")
                        if index == 0 and draft.rules
                        else None
                    )
                program = validate(data)
            program = rebuild_repetitions(program, paths[0][:-1])
            data = program.model_dump(mode="json")
            drop_unused_assets(data, {asset.asset_id for asset in program.assets})
            program = validate(data)
        except (ValueError, TypeError, IndexError, OSError) as error:
            self.notice.warn(error)
            return
        self.update_timer.stop()
        self.committing = True
        try:
            self.committed.emit(program, paths)
        finally:
            self.committing = False

    def accept(self, program: Program, paths: tuple[tuple[int, ...], ...]) -> None:
        # Rebase the template without rebuilding the field the operator moves to.
        self.source, self.paths = program, paths
        reference = self.reference()
        epoch = node_at(program, paths[0])
        template = self.composer.program.sequence[0]
        assert isinstance(epoch, Epoch) and isinstance(template, Epoch)
        if epoch.subgroup_draft is not None:
            for variation, rule in zip(
                self.rows, epoch.subgroup_draft.rules, strict=True
            ):
                variation.random_seed, variation.seed_key = rule.seed, rule.sample_key
        self.composer.program = program.model_copy(
            update={
                "sequence": (template.model_copy(update={"scene_id": epoch.scene_id}),)
            }
        )
        for row in self.composer.rows.values():
            row.parameters.program = self.composer.program
        self.baseline = self.composer.program.model_copy(
            update={
                "sequence": (
                    reference.sequence[0].model_copy(
                        update={"scene_id": epoch.scene_id}
                    ),
                )
            }
        )
        self._reference = self.composer.program
        self._texts = self.text_values()
        self._rules = self.rule_draft(samples=False)
        self.notice.clear()
        self.update_timer.stop()

    def discard(self) -> None:
        if self.source is not None:
            self.bind(self.source, self.paths, self.composer.screens)
            self.changed.emit()
