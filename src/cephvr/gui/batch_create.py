"""Reference composition and optional canonical variation generation."""

from dataclasses import replace

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.batch_insertion import Insertion
from cephvr.gui.batch_values import materialize_values
from cephvr.gui.batch_variation import BatchVariationRow
from cephvr.gui.components import Card, button, combo, equal_row_height, field, label
from cephvr.gui.epoch_batch import epoch_paths
from cephvr.gui.epoch_composer import EpochComposer
from cephvr.gui.notices import FormNotice, passive_validation
from cephvr.gui.program_editing import node_at
from cephvr.gui.projector_layers import layer_title, layers_for
from cephvr.gui.protocol_groups import make_group
from cephvr.gui.stimulus_scope import surfaces
from cephvr.gui.theme import SIZES
from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Fixed,
    Node,
    Program,
)


class BatchCreate(QWidget):
    generated = pyqtSignal(object, object)

    def __init__(self) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        self.composer = EpochComposer()
        body.addWidget(self.composer)
        self.vary = QCheckBox("Enable")
        self.variation_host = Card("Variation rules", compact=True)
        self.variation_host.body.addWidget(self.vary)
        self.variation_content = QWidget()
        self.variation_body = QVBoxLayout(self.variation_content)
        self.variation_body.setContentsMargins(0, SIZES.section_toggle_gap, 0, 0)
        self.variation_host.body.addWidget(self.variation_content)
        self.rows: list[BatchVariationRow] = []
        self.rule_ids: dict[BatchVariationRow, list[str]] = {}
        self.add_rule = button("+ Add variation rule")
        self.add_rule.clicked.connect(self.add_variation)
        self.variation_body.addWidget(self.add_rule)
        self.variation_content.hide()
        self.vary.toggled.connect(self.variation_content.setVisible)
        self.vary.toggled.connect(self.queue_preview)
        body.addWidget(self.variation_host)
        self.generation_controls = QWidget()
        self.generation_controls.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        generation = QVBoxLayout(self.generation_controls)
        generation.setContentsMargins(0, 0, 0, 0)
        self.generation_grid = QGridLayout()
        self.generation_grid.setContentsMargins(0, 0, 0, 0)
        self.generation_grid.setHorizontalSpacing(12)
        self.generation_grid.setVerticalSpacing(12)
        self.parameter_fields: list[QWidget] = []
        self.repetitions = QLineEdit("1")
        self.repetitions.setMaxLength(3)
        self.insert = combo(())
        for title, mode in (
            ("Append to end", "append"),
            ("After selected block", "after"),
            ("Before selected block", "before"),
            ("At beginning", "start"),
            ("Replace trial", "replace"),
            ("After every N blocks", "stride"),
            ("After label…", "label"),
        ):
            self.insert.addItem(title, mode)
        self.target_label = combo(())
        self.target_label.setMinimumWidth(0)
        self.target_field = field("Target label", self.target_label)
        self.target_field.hide()
        self.target_label.currentIndexChanged.connect(self.arrange_insertion)
        self.label_counts: dict[str, int] = {}
        self.stride = QLineEdit("5")
        self.stride.setMaximumWidth(95)
        self.stride_field = field("N blocks", self.stride)
        self.stride_field.hide()
        self.insert.currentIndexChanged.connect(self.arrange_insertion)
        for caption, control in (
            ("Stimulus mode", self.composer.mode),
            ("Duration (hh:mm:ss)", self.composer.duration),
            ("Repetitions", self.repetitions),
            ("Batch label", self.composer.batch_label),
            ("Insert", self.insert),
        ):
            control.setMinimumWidth(0)
            widget = field(caption, control)
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
            self.parameter_fields.append(widget)
        equal_row_height(
            self.composer.mode,
            self.composer.duration,
            self.repetitions,
            self.composer.batch_label,
            self.insert,
            self.target_label,
            self.stride,
        )
        generation.addLayout(self.generation_grid)
        self.arrange_fields()
        self.insertion_hint = label("", wrap=True)
        self.insertion_hint.hide()
        generation.addWidget(self.insertion_hint)
        self.composer.set_generation_controls(self.generation_controls)
        self.notice = FormNotice()
        body.addWidget(self.notice)
        self.summary = label("", wrap=True)
        self.summary.setToolTip("Generated epochs retain their listed order")
        actions = QHBoxLayout()
        actions.addWidget(self.summary, 1)
        self.add_button = button("Add epochs")
        self.add_button.clicked.connect(self.generate)
        actions.addWidget(self.add_button)
        body.addLayout(actions)
        self.composer.changed.connect(self.queue_preview)
        self.composer.batch_label.textChanged.connect(self.queue_preview)
        self.repetitions.textChanged.connect(self.queue_preview)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(120)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.refresh_preview()

    def arrange_insertion(self) -> None:
        mode = self.insert.currentData()
        self.stride_field.setVisible(mode == "stride")
        self.target_field.setVisible(mode == "label")
        self.insertion_hint.setVisible(
            mode in ("stride", "replace", "before", "after", "label")
        )
        self.insertion_hint.setText(
            f"Add this batch after each of {self.label_counts.get(self.target_label.currentText(), 0)} matching epochs (within repeat groups)."
            if mode == "label"
            else "Insert one generated block per interval; append any remaining blocks. Groups count as one block."
            if mode == "stride"
            else "Replace all epochs in the current trial. Use Ctrl+Z to undo."
            if mode == "replace"
            else "An epoch inside a group selects its whole top-level group for insertion."
        )
        self.add_button.setText("Replace trial" if mode == "replace" else "Add epochs")
        self.arrange_fields()

    def arrange_fields(self) -> None:
        fields = self.parameter_fields + (
            [self.stride_field]
            if self.insert.currentData() == "stride"
            else [self.target_field]
            if self.insert.currentData() == "label"
            else []
        )
        while self.generation_grid.count():
            self.generation_grid.takeAt(0)
        for col in range(6):
            self.generation_grid.setColumnStretch(col, 0)
        columns = 3 if self.width() < 760 else len(fields)
        weights = (3, 2, 1, 3, 3, 2)
        for i, widget in enumerate(fields):
            self.generation_grid.addWidget(
                widget,
                i // columns,
                i % columns,
                alignment=Qt.AlignmentFlag.AlignBottom,
            )
            self.generation_grid.setColumnStretch(
                i % columns, weights[i] if columns > 3 else 1
            )

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.arrange_fields()

    def bind_trial(self, program: Program) -> None:
        previous = self.target_label.currentText()
        counts: dict[str, int] = {}
        for path in epoch_paths(program):
            epoch = node_at(program, path)
            assert isinstance(epoch, Epoch)
            if epoch.batch_label:
                counts[epoch.batch_label] = counts.get(epoch.batch_label, 0) + 1
        self.label_counts = counts
        self.target_label.blockSignals(True)
        self.target_label.clear()
        self.target_label.addItems(sorted(counts))
        self.target_label.setCurrentIndex(max(0, self.target_label.findText(previous)))
        self.target_label.blockSignals(False)
        self.arrange_insertion()

    def queue_preview(self) -> None:
        self.preview_timer.start()

    def add_variation(self) -> None:
        try:
            reference = self.composer.value()
        except ValueError as error:
            self.notice.setText(str(error))
            return
        node = reference.sequence[0]
        assert isinstance(node, Epoch)
        targets: list[tuple[str, tuple[int, ...], int, str]] = [
            (
                (
                    " / ".join(f.title() for f in surfaces(s.model_dump(mode="json")))
                    or "Rig-wide"
                )
                + f" · {layer_title(reference, s)} · {i + 1}",
                (0,),
                i,
                s.kind,
            )
            for i, s in enumerate(node.settings)
        ]
        projectors = (
            {"Rig-wide": list(range(len(node.settings)))}
            if any(s.kind == "arena" for s in node.settings)
            else {
                face: layers_for(reference, node, face)
                for face in self.composer.screens
            }
        )
        row = BatchVariationRow(targets, projectors, node.settings)
        self.rule_ids[row] = [s.instance_id for s in node.settings]
        row.remove.clicked.connect(lambda: self.remove_variation(row))
        row.changed.connect(self.queue_preview)
        self.rows.append(row)
        self.variation_body.insertWidget(len(self.rows) - 1, row)
        self.queue_preview()

    def remove_variation(self, row: BatchVariationRow) -> None:
        self.rows.remove(row)
        self.rule_ids.pop(row)
        self.variation_body.removeWidget(row)
        row.deleteLater()
        self.queue_preview()

    def candidate(self) -> Program:
        program = self.composer.value()
        repetitions = int(self.repetitions.text())
        if not 1 <= repetitions <= 999:
            raise ValueError("Use 1–999 repetitions in the authoring editor")
        active_rows = self.rows if self.vary.isChecked() else []
        random_rows = [row for row in active_rows if row.method.currentIndex() == 2]
        rules = tuple(
            rule
            for row in active_rows
            if row not in random_rows
            for rule in row.read_rules()
        )
        if random_rows:
            counts = {len(rule.values) for rule in rules}
            if len(counts) > 1 or 0 in counts:
                raise ValueError(
                    "Paired variations require equally long, nonempty value lists"
                )
            count = next(iter(counts), 1) * repetitions
            if count > 2000:
                raise ValueError(
                    "The authoring editor supports at most 2000 expanded epochs"
                )
            # Sample each repeated epoch once; fixed lists retain their batch order.
            rules = tuple(
                replace(rule, values=rule.values * repetitions) for rule in rules
            )
            rules += tuple(
                rule for row in random_rows for rule in row.read_rules(count)
            )
        # Reject stale targets rather than varying a replacement layer by accident.
        node = program.sequence[0]
        assert isinstance(node, Epoch)
        for row in active_rows:
            for index in row.target_indices():
                layer = row.targets[index][2]
                if (
                    layer >= len(node.settings)
                    or node.settings[layer].instance_id != self.rule_ids[row][index]
                ):
                    raise ValueError(
                        "A varied layer changed; remove and recreate its variation rule"
                    )
        if rules:
            program = materialize_values(
                program, rules, max_variations=2000 if random_rows else 512
            )
        if repetitions != 1 and not random_rows:
            program, _ = make_group(
                program,
                (),
                0,
                len(program.sequence) - 1,
                repetitions,
                False,
            )
        duration = self.composer.duration_value()

        def timed(nodes: tuple[Node, ...]) -> tuple[Node, ...]:
            return tuple(
                node.model_copy(
                    update={
                        "duration": duration,
                        "batch_label": self.composer.batch_label.text().strip(),
                    }
                )
                if isinstance(node, Epoch)
                else node.model_copy(update={"body": timed(node.body)})
                for node in nodes
            )

        # Template duration may be below the trial minimum; validate the assembled trial on insertion.
        program = program.model_copy(update={"sequence": timed(program.sequence)})
        expand_program(program, seed_decimal="0", max_expanded_epochs=2000)
        return program

    def refresh_preview(self) -> None:
        try:
            with passive_validation():
                epochs = expand_program(
                    self.candidate(), seed_decimal="0", max_expanded_epochs=2000
                )
            fixed = all(isinstance(e.source.duration, Fixed) for e in epochs)
            total = sum(
                e.source.duration.duration.ns()
                for e in epochs
                if isinstance(e.source.duration, Fixed)
            )
            self.summary.setText(
                f"{len(epochs)} epochs · {total / 1e9:g} s"
                if fixed
                else f"{len(epochs)} epochs · duration resolved at Setup"
            )
            self.add_button.setEnabled(True)
        except (ValueError, TypeError, IndexError) as error:
            self.notice.setText(str(error))
            self.summary.clear()
            self.add_button.setEnabled(True)

    def generate(self) -> None:
        if not self.isEnabled():
            return
        try:
            program = self.candidate()
        except (ValueError, TypeError, IndexError) as error:
            self.notice.warn(error)
            return
        try:
            stride = (
                int(self.stride.text()) if self.insert.currentData() == "stride" else 1
            )
            if not 1 <= stride <= 2000:
                raise ValueError("Use an insertion interval between 1 and 2000 blocks")
        except ValueError as error:
            self.notice.warn(error)
            return
        self.generated.emit(
            program,
            Insertion(
                self.insert.currentData(), stride, self.target_label.currentText()
            ),
        )
