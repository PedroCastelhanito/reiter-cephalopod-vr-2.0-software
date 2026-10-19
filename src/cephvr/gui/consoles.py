"""Shared HUD and log widgets with fitted text and bounded entry details."""

from math import ceil

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import (
    QContextMenuEvent,
    QPaintEvent,
    QResizeEvent,
    QTextBlockUserData,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
)

from cephvr.gui.log_colors import LogHighlighter
from cephvr.gui.retro_instruments import (
    PromptGutter,
    blink,
    prompt_cursor,
    terminal_marks,
)
from cephvr.gui.theme import SIZES, colors_for, retro_console


class Console(QPlainTextEdit):
    def __init__(self, *, lines: int = 6, grow: bool = True) -> None:
        super().__init__()
        self.setProperty("role", "console")
        document = self.document()
        assert document is not None
        self._plain_margin = document.documentMargin()
        self.gutter_width = 0
        self.gutter = PromptGutter(self)
        self.setTabChangesFocus(True)
        self.setReadOnly(True)
        self.setMaximumBlockCount(256)
        height = lines * (SIZES.console_font + 5) + 32
        if grow:
            self.setMinimumHeight(height)
        else:
            self.setFixedHeight(height)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding if grow else QSizePolicy.Policy.Fixed,
        )

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        size.setHeight(self.minimumHeight())
        return size

    def set_entry_prompts(self, enabled: bool) -> None:
        """Reserve a visual prompt gutter without rewriting retained text blocks."""
        document = self.document()
        assert document is not None
        document.setDocumentMargin(self._plain_margin)
        self.gutter_width = self.fontMetrics().horizontalAdvance("> ") if enabled else 0
        self.setViewportMargins(self.gutter_width, 0, 0, 0)
        self.gutter.place(self.gutter_width)
        viewport = self.viewport()
        assert viewport is not None
        viewport.update()

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.gutter.place(self.gutter_width)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        if not retro_console(self) or event is None:
            return
        terminal_marks(self, event)


class FittedConsole(Console):
    """Fit the rendered text, including wrapped lines, without consuming spare height."""

    def __init__(self) -> None:
        super().__init__(lines=1, grow=False)
        self.textChanged.connect(self.fit_height)

    def fit_height(self) -> None:
        document = self.document()
        assert document is not None
        layout = document.documentLayout()
        assert layout is not None
        block = document.begin()
        height = 2 * (self.frameWidth() + document.documentMargin())
        while block.isValid():
            height += layout.blockBoundingRect(block).height()
            block = block.next()
        target = ceil(height)
        if self.height() != target:
            self.setFixedHeight(target)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.fit_height()


class LogConsole(Console):
    """Follow new messages only while the reader is already at the bottom."""

    def __init__(self, *, lines: int = 7) -> None:
        super().__init__(lines=lines)
        self.preview_compact = False
        self._expanded_minimum = self.minimumHeight()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll = self.verticalScrollBar()
        assert scroll is not None
        scroll.setObjectName("ConsoleLogScroll")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        document = self.document()
        assert document is not None
        self.highlighter = LogHighlighter(document, lambda: colors_for(self).error)
        blink().toggled.connect(self.blink_cursor)

    def set_entry_prompts(self, enabled: bool) -> None:
        super().set_entry_prompts(enabled)
        self.highlighter.rehighlight()
        if self.preview_compact:
            self._fit_four_lines()

    def _fit_four_lines(self) -> None:
        self.ensurePolished()
        document = self.document()
        viewport = self.viewport()
        assert document is not None and viewport is not None
        chrome = self.height() - viewport.height()
        self.setFixedHeight(
            ceil(
                4 * self.fontMetrics().lineSpacing()
                + 2 * document.documentMargin()
                + chrome
            )
        )

    def set_preview_compact(self, compact: bool, *, follow: bool = True) -> None:
        changed = compact != self.preview_compact
        self.preview_compact = compact
        if compact:
            self._fit_four_lines()
        else:
            self.setMaximumHeight(16777215)
            self.setMinimumHeight(self._expanded_minimum)
        if changed and compact and follow:
            self.scroll_to_latest()
            QTimer.singleShot(0, self.scroll_to_latest)

    def scroll_to_latest(self) -> None:
        scroll = self.verticalScrollBar()
        assert scroll is not None
        scroll.setValue(scroll.maximum())

    def blink_cursor(self) -> None:
        viewport = self.viewport()
        if viewport is not None and retro_console(self):
            viewport.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        if retro_console(self) and blink().on:
            prompt_cursor(self)

    def appendPlainText(self, text: str | None) -> None:
        if not text:
            return
        vertical = self.verticalScrollBar()
        horizontal = self.horizontalScrollBar()
        assert vertical is not None and horizontal is not None
        following = vertical.value() >= vertical.maximum()
        x = horizontal.value()
        anchor = self.firstVisibleBlock()
        document = self.document()
        assert document is not None
        preceding_lines = 0
        block = document.begin()
        while block.isValid() and block != anchor:
            preceding_lines += block.lineCount()
            block = block.next()
        line_offset = max(0, vertical.value() - preceding_lines)
        super().appendPlainText(text)
        position = 0
        if not following and anchor.isValid():
            block = document.begin()
            while block.isValid() and block != anchor:
                position += block.lineCount()
                block = block.next()
            position += line_offset
        vertical.setValue(vertical.maximum() if following else position)
        horizontal.setValue(x)

    def append_entry(
        self, summary: str, details: str, *, error: bool | None = None
    ) -> None:
        """Append a concise row with diagnostics bound to its document block."""
        summary = summary.replace("\r\n", "\n").replace("\r", "\n")
        summary = " · ".join(summary.splitlines())
        self.appendPlainText(summary)
        document = self.document()
        assert document is not None
        block = document.lastBlock()
        block.setUserData(_LogDetails(details, error=error))
        self.highlighter.rehighlightBlock(block)
        self.setToolTip(
            "Right-click or use the context-menu key on an entry for details."
        )

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        if event is None:
            return
        cursor = (
            self.textCursor()
            if event.reason() == QContextMenuEvent.Reason.Keyboard
            else self.cursorForPosition(event.pos())
        )
        data = cursor.block().userData()
        keyboard = event.reason() == QContextMenuEvent.Reason.Keyboard
        local_position = (
            self.cursorRect(cursor).bottomRight() if keyboard else event.pos()
        )
        menu = self.createStandardContextMenu(local_position)
        if menu is None:
            return
        if isinstance(data, _LogDetails):
            menu.addSeparator()
            view_action = menu.addAction("View details")
            copy_action = menu.addAction("Copy details")
        else:
            view_action = copy_action = None
        global_position = (
            self.mapToGlobal(local_position) if keyboard else event.globalPos()
        )
        chosen = menu.exec(global_position)
        if isinstance(data, _LogDetails) and chosen == view_action:
            dialog = QDialog(self)
            dialog.setWindowTitle("Log entry details")
            layout = QVBoxLayout(dialog)
            detail_view = QPlainTextEdit(dialog)
            detail_view.setTabChangesFocus(True)
            detail_view.setProperty("role", "source")
            detail_view.setReadOnly(True)
            detail_view.setPlainText(data.details)
            layout.addWidget(detail_view)
            dialog.resize(640, 360)
            dialog.exec()
            dialog.deleteLater()
        elif isinstance(data, _LogDetails) and chosen == copy_action:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(data.details)
        menu.deleteLater()


class _LogDetails(QTextBlockUserData):
    def __init__(self, details: str, *, error: bool | None = None) -> None:
        super().__init__()
        self.details = details
        self.error = error
