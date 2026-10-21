"""Read-only four-row tail of the dashboard log, including in-place updates."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QPlainTextEdit

from cephvr.gui.consoles import FittedConsole


class PreviewLog(FittedConsole):
    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("Latest four runtime log lines")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setPlainText("\n\n\n")

    def show_tail(self, source: QTextDocument) -> None:
        block = source.lastBlock()
        lines: list[str] = []
        while block.isValid() and len(lines) < 4:
            lines.append(block.text())
            block = block.previous()
        lines.reverse()
        text = "\n".join(lines + [""] * (4 - len(lines)))
        if self.toPlainText() != text:
            self.setPlainText(text)
            self.setToolTip(text.strip())
