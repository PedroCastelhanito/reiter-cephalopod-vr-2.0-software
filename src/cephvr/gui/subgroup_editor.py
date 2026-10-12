"""One reference-composer form for creating and editing selected epoch subgroups."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel

from cephvr.gui.batch_create import BatchCreate
from cephvr.gui.components import button
from cephvr.gui.epoch_selection import SelectionComposer
from cephvr.gui.program_editing import data_node, node_at, validate
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
        super().__init__(
            append_only=True, composer=SelectionComposer(), show_copies=False
        )
        self.summary.hide()
        self.add_button.clicked.disconnect()
        self.add_button.setText("Apply")
        self.add_button.clicked.connect(self.apply)
        self.reset = button("Discard")
        self.reset.clicked.connect(self.discard)
        layout = self.layout()
        assert layout is not None
        item = layout.itemAt(layout.count() - 1)
        assert item is not None
        actions = item.layout()
        assert isinstance(actions, QHBoxLayout)
        actions.insertWidget(actions.count() - 1, self.reset)
        actions.insertStretch(0, 1)
        self.parameter_fields[3].findChildren(QLabel)[0].setText("Name")
        self.composer.batch_label.setPlaceholderText("Optional subgroup name")
        self.composer.changed.connect(self.changed.emit)
        for control in (
            self.composer.duration,
            self.composer.batch_label,
        ):
            control.textEdited.connect(self.changed.emit)
        self._binding = False

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
        return SubgroupDraft(enabled=self.vary.isChecked(), rules=rules)

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
        self.source, self.paths = program, paths
        self.composer.close_file_dialogs()
        self.vary.setChecked(False)
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
            for rule in draft.rules:
                self.add_variation_from(composer.program)
                self.rows[-1].restore(rule)
            self.vary.setChecked(draft.enabled)
            self._rules = self.rule_draft(samples=False)
        self.notice.clear()
        self._binding = False
        self.refresh_preview()

    def queue_preview(self) -> None:
        if not self._binding and not self._previewing:
            super().queue_preview()
            self.changed.emit()

    def refresh_preview(self) -> None:
        if self._binding:
            return
        if self.vary.isChecked():
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
            or self.source is None
            or self.baseline is None
            or not self.paths
        ):
            return
        try:
            reference = self.reference()
            candidate = self.candidate() if self.vary.isChecked() else None
            variants = (
                generated_batch(candidate)
                if candidate is not None
                and self.rule_draft(samples=False) != self._rules
                and any(row.method.currentIndex() != 2 for row in self.rows)
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
            identities = {
                node.batch_id
                for path in self.paths
                if isinstance(node := node_at(self.source, path), Epoch)
            }
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
        except (ValueError, TypeError, IndexError, OSError) as error:
            self.notice.warn(error)
            return
        self.committed.emit(program, paths)

    def discard(self) -> None:
        if self.source is not None:
            self.bind(self.source, self.paths, self.composer.screens)
            self.changed.emit()
