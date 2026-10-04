"""Reference composition and optional canonical variation generation."""

from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QTimer, pyqtSignal
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
from cephvr.gui.components import button, combo, field, label
from cephvr.gui.epoch_batch import epoch_paths
from cephvr.gui.epoch_composer import EpochComposer
from cephvr.gui.group_dialog import VariationRow
from cephvr.gui.program_editing import node_at, unique_id, validate
from cephvr.gui.projector_layers import layer_title
from cephvr.gui.protocol_groups import Variation, make_group
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Fixed,
    Node,
    Program,
)


class BatchVariationRow(VariationRow):
    """A reference-layer rule with explicit values or a bounded numeric sweep."""

    def __init__(self, targets: list[tuple[str, tuple[int, ...], int, str]]) -> None:
        super().__init__(targets)
        self.method = combo(("Values", "Sweep (min, max, step)"))
        layout = self.layout()
        assert isinstance(layout, QHBoxLayout)
        layout.insertWidget(2, field("Method", self.method), 1)
        self.method.currentIndexChanged.connect(self.update_hint)

    def update_hint(self) -> None:
        self.values.setPlaceholderText(
            "0, 10, 2" if self.method.currentIndex() else "10, 20, 30"
        )

    def read(self) -> Variation:
        rule = super().read()
        if self.method.currentIndex() == 0:
            return rule
        try:
            start, stop, step = (
                Decimal(part.strip()) for part in self.values.text().split(",")
            )
        except (InvalidOperation, ValueError) as error:
            raise ValueError("Sweep needs min, max, step") from error
        if (
            not all(value.is_finite() for value in (start, stop, step))
            or step <= 0
            or stop < start
        ):
            raise ValueError("Sweep needs finite min ≤ max and positive step")
        count = int((stop - start) // step) + 1
        if count > 512:
            raise ValueError("Sweep exceeds 512 values")
        return Variation(
            rule.path,
            rule.layer,
            rule.parameter,
            tuple(float(start + i * step) for i in range(count)),
        )


class BatchCreate(QWidget):
    generated = pyqtSignal(object, object)

    def __init__(self) -> None:
        super().__init__()
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        self.composer = EpochComposer()
        body.addWidget(self.composer)
        self.vary = QCheckBox("Variation rules")
        body.addWidget(self.vary)
        self.variation_host = QWidget()
        self.variation_body = QVBoxLayout(self.variation_host)
        self.variation_body.setContentsMargins(0, 0, 0, 0)
        self.rows: list[BatchVariationRow] = []
        self.rule_ids: dict[BatchVariationRow, list[str]] = {}
        self.add_rule = button("+ Add variation rule")
        self.add_rule.clicked.connect(self.add_variation)
        self.variation_body.addWidget(self.add_rule)
        self.combine = combo(("Pair values by position", "All combinations"))
        self.variation_body.addWidget(field("Combine", self.combine))
        self.variation_host.hide()
        self.vary.toggled.connect(self.variation_host.setVisible)
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
            self.parameter_fields.append(field(caption, control))
        generation.addLayout(self.generation_grid)
        self.arrange_fields()
        self.insertion_hint = label("", wrap=True)
        self.insertion_hint.hide()
        generation.addWidget(self.insertion_hint)
        self.composer.set_generation_controls(self.generation_controls)
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
        self.combine.currentIndexChanged.connect(self.queue_preview)
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
            else "Replace all epochs in the current trial. Undo is available in Actions."
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
            self.generation_grid.addWidget(widget, i // columns, i % columns)
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
            self.summary.setText(str(error))
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
        row = BatchVariationRow(targets)
        self.rule_ids[row] = [s.instance_id for s in node.settings]
        row.remove.clicked.connect(lambda: self.remove_variation(row))
        row.values.textChanged.connect(self.queue_preview)
        row.method.currentIndexChanged.connect(self.queue_preview)
        row.target.currentIndexChanged.connect(self.queue_preview)
        row.parameter.currentIndexChanged.connect(self.queue_preview)
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
        rules = tuple(row.read() for row in self.rows) if self.vary.isChecked() else ()
        # Reject stale targets rather than varying a replacement layer by accident.
        node = program.sequence[0]
        assert isinstance(node, Epoch)
        for row, rule in zip(self.rows if rules else (), rules, strict=True):
            original = self.rule_ids[row][row.target.currentIndex()]
            if (
                rule.layer >= len(node.settings)
                or node.settings[rule.layer].instance_id != original
            ):
                raise ValueError(
                    "A varied layer changed; remove and recreate its variation rule"
                )
        if rules:
            program, _ = make_group(
                program, (), 0, 0, 1, False, rules, self.combine.currentIndex() == 1
            )
            expanded = expand_program(
                program, seed_decimal="0", max_expanded_epochs=2000
            )
            data = program.model_dump(mode="json")
            data["sequence"] = []
            for occurrence in expanded:
                epoch = occurrence.source.model_dump(mode="json")
                epoch["epoch_id"] = unique_id(data, "Epoch")
                epoch["settings"] = [
                    setting.model_dump(mode="json") for setting in occurrence.settings
                ]
                data["sequence"].append(epoch)
            program = validate(data)
        if repetitions != 1:
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
            self.summary.setText(str(error))
            self.add_button.setEnabled(False)

    def generate(self) -> None:
        if not self.isEnabled():
            return
        try:
            program = self.candidate()
        except (ValueError, TypeError, IndexError) as error:
            self.summary.setText(str(error))
            return
        try:
            stride = (
                int(self.stride.text()) if self.insert.currentData() == "stride" else 1
            )
            if not 1 <= stride <= 2000:
                raise ValueError("Use an insertion interval between 1 and 2000 blocks")
        except ValueError as error:
            self.summary.setText(str(error))
            return
        self.generated.emit(
            program,
            Insertion(
                self.insert.currentData(), stride, self.target_label.currentText()
            ),
        )
