"""Display-only log severity and syntax coloring, independent of log storage."""

import re
from collections.abc import Callable

from PyQt6.QtGui import QColor, QSyntaxHighlighter, QTextBlock, QTextDocument

_ERROR = re.compile(
    r"\b(error|exception|traceback|failed|failure|fault|rejected|cannot)\b", re.I
)
_NEGATED = re.compile(r"\b(no|0|zero|without|not)$", re.I)


def log_block_is_error(block: QTextBlock) -> bool:
    explicit = getattr(block.userData(), "error", None)
    if isinstance(explicit, bool):
        return explicit
    text = block.text()
    for match in _ERROR.finditer(text):
        preceding = text[: match.start()].rstrip()
        if not _NEGATED.search(preceding):
            return True
    return False


class LogHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument, color: Callable[[], str]) -> None:
        super().__init__(document)
        self.color = color

    def highlightBlock(self, text: str | None) -> None:
        if text and log_block_is_error(self.currentBlock()):
            self.setFormat(0, len(text), QColor(self.color()))
