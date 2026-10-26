"""Stack variation editors without sharing labels between different rule methods."""

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from cephvr.gui.batch_variation import BatchVariationRow
from cephvr.gui.theme import SIZES


class VariationCards(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(SIZES.group_gap)
        self.rules: list[BatchVariationRow] = []
        self.hide()

    def append_rule(self, rule: BatchVariationRow) -> None:
        self.rules.append(rule)
        self.body.addWidget(rule)
        self.show()

    def remove_rule(self, rule: BatchVariationRow) -> None:
        self.rules.remove(rule)
        self.body.removeWidget(rule)
        rule.hide()
        rule.deleteLater()
        self.setVisible(bool(self.rules))
