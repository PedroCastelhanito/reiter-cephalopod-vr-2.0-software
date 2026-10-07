"""Inspect/edit existing groups and preview canonical expansion without backend I/O."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QTextOption
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import button, combo, field, label
from cephvr.gui.condition_values import ConditionValues
from cephvr.gui.notices import FormNotice
from cephvr.gui.program_editing import NodePath, node_at
from cephvr.gui.protocol_groups import motion_numbers, update_group
from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import (
    Fixed,
    Group,
    Program,
)


class GroupEditor(QWidget):
    committed = pyqtSignal(object)
    enter = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.program: Program | None = None
        self.path: NodePath = 0
        self.conditions: ConditionValues | None = None
        self.dirty = False
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.repetitions = QLineEdit()
        self.order = combo(("As listed", "Shuffle each repetition"))
        row = QHBoxLayout()
        row.addWidget(field("Repeat count", self.repetitions))
        row.addWidget(field("Order", self.order))
        self.body.addLayout(row)
        self.summary = label("", wrap=True)
        self.body.addWidget(self.summary)
        enter = button("Edit epochs in group")
        enter.clicked.connect(self.enter)
        self.body.addWidget(enter)
        self.more = button("Edit condition values…")
        self.more.setCheckable(True)
        self.more.toggled.connect(self.show_conditions)
        self.body.addWidget(self.more)
        self.message = FormNotice()
        self.body.addWidget(self.message)
        self.apply_button = button("Apply group changes")
        self.apply_button.clicked.connect(self.apply)
        self.body.addWidget(self.apply_button)
        self.repetitions.textEdited.connect(self.mark_changed)
        self.order.currentIndexChanged.connect(self.mark_changed)
        self.repetitions.editingFinished.connect(self.apply_if_dirty)
        self.order.activated.connect(self.apply_if_dirty)

    def bind(self, program: Program, path: NodePath) -> None:
        self.program, self.path = program, path
        node = node_at(program, path)
        self.setVisible(isinstance(node, Group))
        if not isinstance(node, Group):
            self.dirty = False
            return
        if self.conditions:
            self.body.removeWidget(self.conditions)
            self.conditions.deleteLater()
            self.conditions = None
        self.repetitions.setText(str(node.repetitions))
        self.order.setCurrentIndex(node.order != "as_listed")
        self.refresh_summary(node)
        self.more.setChecked(False)
        self.more.setVisible(node.conditions is not None)
        if node.conditions:
            self.conditions = ConditionValues(node)
            self.conditions.changed.connect(self.mark_changed)
            self.body.insertWidget(self.body.count() - 2, self.conditions)
            self.conditions.hide()
        self.dirty = False
        self.message.clear()

    def refresh_summary(self, node: Group) -> None:
        count = len(node.conditions.rows) if node.conditions else len(node.body)
        self.summary.setText(
            f"{count} {'conditions; each runs the full sequence' if node.conditions else 'child blocks; shuffle changes their order'} · {len(node.body)} authored blocks"
        )

    def show_conditions(self, checked: bool) -> None:
        if self.conditions:
            self.conditions.setVisible(checked)

    def mark_changed(self) -> None:
        self.dirty = True

    def apply_if_dirty(self) -> None:
        if self.dirty:
            self.apply()

    def apply(self) -> bool:
        if not self.isEnabled() or self.program is None:
            return False
        try:
            program = update_group(
                self.program,
                self.path,
                int(self.repetitions.text()),
                self.order.currentIndex() == 1,
                self.conditions.read() if self.conditions else None,
            )
        except (ValueError, TypeError) as error:
            self.message.warn(str(error))
            return False
        self.program, self.dirty = program, False
        node = node_at(program, self.path)
        assert isinstance(node, Group)
        self.refresh_summary(node)
        self.message.status("Draft updated")
        self.committed.emit(program)
        return True


class ExpandedPreview(QDialog):
    def __init__(self, program: Program, parent: QWidget) -> None:
        super().__init__(parent)
        self.program = program
        self.setWindowTitle("Expanded sequence · authoring example")
        self.resize(730, 550)
        body = QVBoxLayout(self)
        body.addWidget(
            label(
                "Authoring example only. Setup owns the retained experiment seed and final prepared order. This seed is not saved into the protocol.",
                wrap=True,
            )
        )
        row = QHBoxLayout()
        self.seed = QLineEdit("0")
        row.addWidget(field("Example seed", self.seed))
        refresh = button("Update example")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        body.addLayout(row)
        self.output = QPlainTextEdit()
        self.output.setProperty("role", "source")
        self.output.setReadOnly(True)
        self.output.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        body.addWidget(self.output)
        self.close_button = button("Close")
        self.close_button.clicked.connect(self.close)
        body.addWidget(self.close_button)
        self.refresh()

    def refresh(self) -> None:
        try:
            seed = int(self.seed.text())
            if not 0 <= seed < 2**128:
                raise ValueError("Use a nonnegative seed below 2^128")
            epochs = expand_program(
                self.program, seed_decimal=str(seed), max_expanded_epochs=2000
            )
            lines = []
            cursor = 0
            known = True
            for i, epoch in enumerate(epochs):
                if isinstance(epoch.source.duration, Fixed) and known:
                    duration = epoch.source.duration.duration.ns()
                    timing = f"{cursor / 1e9:g}–{(cursor + duration) / 1e9:g} s"
                    cursor += duration
                else:
                    known = False
                    timing = "timing unresolved until Setup"
                lineage = " / ".join(
                    f"{v.group_id}: repeat {v.repetition_index + 1}, {v.unit_id}"
                    for v in epoch.lineage
                )
                parameters = []
                for setting in epoch.settings:
                    try:
                        speed, direction, angular = motion_numbers(
                            setting.model_dump(mode="json")
                        )
                    except ValueError:
                        continue
                    unit = (
                        "mm/s"
                        if setting.kind == "arena"
                        or setting.space.kind == "physical_surface"
                        else "deg/s"
                    )
                    parameters.append(
                        f"{setting.instance_id}: {speed:g} {unit}, {direction:g}°, {angular:g}°/s"
                    )
                lines.append(
                    f"{i + 1}. {epoch.source.epoch_id} · {timing}"
                    + (f"\n   {lineage}" if lineage else "")
                    + ("\n   " + "; ".join(parameters) if parameters else "")
                )
            self.output.setPlainText("\n".join(lines))
        except (ValueError, TypeError) as error:
            self.output.setPlainText(str(error))
