"""Repeat/variation authoring dialog; all results are canonical program edits."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import button, combo, field, label
from cephvr.gui.program_editing import nodes_at
from cephvr.gui.protocol_document import node_name
from cephvr.gui.protocol_groups import Variation, make_group
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Group,
    Node,
    Program,
)


class VariationRow(QWidget):
    def __init__(self, targets: list[tuple[str, tuple[int, ...], int, str]]) -> None:
        super().__init__()
        self.targets = targets
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.target = combo(tuple(t[0] for t in targets))
        self.parameter = combo(("Speed", "Direction", "Rotation"))
        self.values = QLineEdit()
        self.values.setPlaceholderText("10, 20, 30")
        for caption, control in (
            ("Epoch / layer", self.target),
            ("Parameter", self.parameter),
            ("Values", self.values),
        ):
            control.setMinimumWidth(0)
            control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            row.addWidget(field(caption, control), 1)
        self.remove = button("×", hint="Remove variation")
        row.addWidget(self.remove)
        self.target.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        if not self.targets:
            self.setEnabled(False)
            return
        arena = self.targets[self.target.currentIndex()][3] == "arena"
        model = self.parameter.model()
        assert isinstance(model, QStandardItemModel)
        for i in range(self.parameter.count()):
            item = model.item(i)
            assert item is not None
            item.setEnabled(not arena or i < 3)
        if arena and self.parameter.currentIndex() >= 3:
            self.parameter.setCurrentIndex(0)

    def read(self) -> Variation:
        if not self.targets:
            raise ValueError("Add a stimulus before creating a variation")
        _, path, layer, _ = self.targets[self.target.currentIndex()]
        return Variation(
            path,
            layer,
            "Angular speed"
            if self.parameter.currentText() == "Rotation"
            else self.parameter.currentText(),
            tuple(float(v.strip()) for v in self.values.text().split(",")),
        )


class GroupDialog(QDialog):
    committed = pyqtSignal(object, int)

    def __init__(
        self, program: Program, scope: tuple[int, ...], selected: int, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Repeat / vary sequence")
        self.resize(730, 320)
        self.program, self.scope = program, scope
        body = QVBoxLayout(self)
        row = QHBoxLayout()
        names = tuple(node_name(n) for n in nodes_at(program, scope))
        self.first, self.last = combo(names), combo(names)
        self.first.setCurrentIndex(selected)
        self.last.setCurrentIndex(selected)
        self.repetitions = QLineEdit("1")
        self.order = combo(("As listed", "Shuffle each repetition"))
        for title, control in (
            ("From", self.first),
            ("Through", self.last),
            ("Repeat count", self.repetitions),
            ("Order", self.order),
        ):
            control.setMinimumWidth(0)
            row.addWidget(field(title, control), 1)
        body.addLayout(row)
        body.addWidget(
            label(
                "Select consecutive epochs. Variations repeat the entire selected sequence, including blank intervals.",
                wrap=True,
            )
        )
        self.rows_layout = QVBoxLayout()
        body.addLayout(self.rows_layout)
        self.rows: list[VariationRow] = []
        self.targets: list[tuple[str, tuple[int, ...], int, str]] = []

        def visit(nodes: tuple[Node, ...], prefix: tuple[int, ...]) -> None:
            for index, node in enumerate(nodes):
                path = prefix + (index,)
                if isinstance(node, Group):
                    visit(node.body, path)
                elif isinstance(node, Epoch):
                    for layer, setting in enumerate(node.settings):
                        self.targets.append(
                            (
                                f"{node.epoch_id} / {setting.instance_id}",
                                path,
                                layer,
                                setting.kind,
                            )
                        )

        visit(nodes_at(program, scope), scope)
        controls = QHBoxLayout()
        self.add_rule = button("+ Vary parameter")
        self.add_rule.setEnabled(bool(self.targets))
        self.add_rule.clicked.connect(self.add_variation)
        controls.addWidget(self.add_rule)
        self.combine = combo(("Pair values by position", "All combinations"))
        self.combine.hide()
        controls.addWidget(self.combine)
        controls.addStretch()
        body.addLayout(controls)
        self.message = label("", wrap=True)
        body.addWidget(self.message)
        body.addWidget(
            label(
                "Without variations, shuffle changes child-block order. Use As listed to preserve a stimulus → blank sequence.",
                wrap=True,
            )
        )
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        self.create_button = button("Create group")
        self.create_button.clicked.connect(self.apply)
        actions.addWidget(cancel)
        actions.addWidget(self.create_button)
        body.addLayout(actions)

    def add_variation(self) -> None:
        row = VariationRow(self.targets)
        row.remove.clicked.connect(lambda: self.remove_variation(row))
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        self.combine.setVisible(len(self.rows) > 1)

    def remove_variation(self, row: VariationRow) -> None:
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self.combine.setVisible(len(self.rows) > 1)

    def apply(self) -> None:
        try:
            program, selected = make_group(
                self.program,
                self.scope,
                self.first.currentIndex(),
                self.last.currentIndex(),
                int(self.repetitions.text()),
                self.order.currentIndex() == 1,
                tuple(row.read() for row in self.rows),
                self.combine.currentIndex() == 1,
            )
        except (ValueError, TypeError, IndexError) as error:
            self.message.setText(str(error))
            return
        self.committed.emit(program, selected)
        self.accept()
