"""Trial-local source-epoch filters for batch patches."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QLineEdit, QSizePolicy, QWidget

from cephvr.gui.components import InlineMessage, combo, equal_row_height, field
from cephvr.gui.epoch_batch import epoch_paths
from cephvr.gui.program_editing import node_at
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program


class EpochTargets(QWidget):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        row = self.grid
        row.setHorizontalSpacing(12)
        self.timeline = True
        row.setContentsMargins(0, 0, 0, 0)
        self.filter = combo(("All epochs", "Epoch label", "Epoch index"))
        self.labels = combo(())
        self.index = QLineEdit()
        self.index.setPlaceholderText("1")
        self.index.setToolTip(
            "One-based source epoch index in trial order; repeated occurrences "
            "share the same source epoch."
        )
        self.label_field = field("Epoch label", self.labels)
        self.index_field = field("Epoch index", self.index)
        self.filter_field = field("Filter", self.filter)
        row.addWidget(self.filter_field, 0, 2)
        row.addWidget(self.label_field, 0, 4)
        row.addWidget(self.index_field, 0, 4)
        for column in (0, 2, 4):
            row.setColumnStretch(column, 1)
        for column in (1, 3):
            row.setColumnMinimumWidth(column, 12)
        row.setHorizontalSpacing(0)
        for widget in (self.filter_field, self.label_field, self.index_field):
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        equal_row_height(self.filter, self.labels, self.index)
        self.message = InlineMessage()
        self._accepted = (0, "", "")
        self.filter.currentIndexChanged.connect(self.update_filter)
        self.labels.currentIndexChanged.connect(self.changed.emit)
        self.index.textEdited.connect(self.changed.emit)
        self.update_visibility()

    def update_visibility(self) -> None:
        self.filter_field.setVisible(not self.timeline)
        self.label_field.setVisible(
            not self.timeline and self.filter.currentIndex() == 1
        )
        self.index_field.setVisible(
            not self.timeline and self.filter.currentIndex() == 2
        )

    def set_timeline(self, timeline: bool) -> None:
        self.timeline = timeline
        self.update_visibility()

    def update_filter(self) -> None:
        self.update_visibility()
        self.changed.emit()

    def refresh(self, program: Program) -> None:
        previous = self.labels.currentText()
        names = sorted(
            {
                epoch.batch_label
                for path in epoch_paths(program)
                if isinstance(epoch := node_at(program, path), Epoch)
                and epoch.batch_label
            }
        )
        self.labels.blockSignals(True)
        self.labels.clear()
        self.labels.addItems(names)
        self.labels.setCurrentIndex(max(0, self.labels.findText(previous)))
        self.labels.blockSignals(False)

    def resolve(self, program: Program) -> tuple[tuple[int, ...], ...]:
        paths = epoch_paths(program)
        if self.filter.currentIndex() == 0:
            result = paths
        elif self.filter.currentIndex() == 1:
            name = self.labels.currentText()
            result = (
                tuple(
                    path
                    for path in paths
                    if isinstance(epoch := node_at(program, path), Epoch)
                    and epoch.batch_label == name
                )
                if name
                else ()
            )
            if not result:
                raise ValueError("No epochs with the selected label in this trial")
        else:
            text = self.index.text().strip()
            if not text.isascii() or not text.isdecimal():
                raise ValueError(f"Enter an epoch index from 1 to {len(paths)}")
            index = int(text)
            if not 1 <= index <= len(paths):
                raise ValueError(
                    f"Epoch index {index} is outside this trial (1–{len(paths)})"
                )
            result = (paths[index - 1],)
        if not result:
            raise ValueError("This trial has no source epochs to edit")
        return result

    def accept(self) -> None:
        self._accepted = (
            self.filter.currentIndex(),
            self.labels.currentText(),
            self.index.text(),
        )
        self.message.clear()

    def restore(self) -> None:
        mode, name, text = self._accepted
        for control in (self.filter, self.labels, self.index):
            control.blockSignals(True)
        self.filter.setCurrentIndex(mode)
        self.labels.setCurrentIndex(max(0, self.labels.findText(name)))
        self.index.setText(text)
        for control in (self.filter, self.labels, self.index):
            control.blockSignals(False)
        self.update_visibility()
