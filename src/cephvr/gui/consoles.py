"""Shared HUD and log widgets with fitted text and bounded entry details."""

from math import ceil

from PyQt6.QtCore import QMimeData, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QContextMenuEvent,
    QPaintEvent,
    QResizeEvent,
    QTextBlock,
    QTextBlockUserData,
    QTextCursor,
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
from cephvr.gui.log_format import (
    CATEGORY_PREFIX,
    STAMP_WIDTH,
    SUBJECT_WIDTH,
    terminal_body,
    terminal_row,
)
from cephvr.gui.log_wrap import unwrap_row, wrap_row
from cephvr.gui.retro_instruments import (
    ColumnHeader,
    PromptGutter,
    blink,
    prompt_cursor,
    terminal_marks,
)
from cephvr.gui.theme import SIZES, colors_for, minimal_frames, retro_console


class Console(QPlainTextEdit):
    def __init__(self, *, lines: int = 6, grow: bool = True) -> None:
        super().__init__()
        self.setProperty("role", "console")
        document = self.document()
        assert document is not None
        self._plain_margin = document.documentMargin()
        self.gutter_width = 0
        self.header_height = 0
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
        self.setViewportMargins(self.gutter_width, self.header_height, 0, 0)
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
        self._last_body: str | None = None
        self._category_width = SUBJECT_WIDTH + 2
        self._actions: dict[tuple[str, ...], QTextBlock] = {}
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
        self.column_header = ColumnHeader(self, self.column_titles)
        # Indent of the wraps currently in the document; 0 means rows are unwrapped.
        self._wrap_indent = 0
        self.setUndoRedoEnabled(False)
        blink().toggled.connect(self.blink_cursor)

    def rewrap(self, first: QTextBlock | None = None) -> None:
        """Hang wrapped rows under the message column in Amber phosphor (display only).

        Rewraps from `first` (all rows by default) and keeps the reader's position."""
        document = self.document()
        vertical = self.verticalScrollBar()
        assert document is not None and vertical is not None
        indent = STAMP_WIDTH + self._category_width + 1 if minimal_frames(self) else 0
        advance = self.fontMetrics().horizontalAdvance(" ")
        viewport = self.viewport()
        columns = viewport.width() // advance - 1 if viewport and advance else 0
        following = vertical.value() >= vertical.maximum()
        anchor = self.firstVisibleBlock().blockNumber()
        previous, self._wrap_indent = self._wrap_indent, indent
        block = first if first is not None else document.begin()
        while block.isValid():
            text = block.text()
            row = unwrap_row(text, previous)
            shown = wrap_row(row, columns, indent) if indent else row
            if shown != text:
                cursor = QTextCursor(block)
                cursor.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.insertText(shown)
            block = block.next()
        if following:
            vertical.setValue(vertical.maximum())
            return
        lines, block = 0, document.begin()
        while block.isValid() and block.blockNumber() < anchor:
            lines += block.lineCount()
            block = block.next()
        vertical.setValue(lines)

    def createMimeDataFromSelection(self) -> QMimeData | None:
        """Copy rows as stored: drop display-only wraps."""
        if not self._wrap_indent:
            return super().createMimeDataFromSelection()
        # Qt's selection mime data regenerates its text, so return plain text only;
        # selectedText() reports entry breaks as U+2029.
        text = unwrap_row(self.textCursor().selectedText(), self._wrap_indent)
        data = QMimeData()
        data.setText(text.replace("\u2029", "\n"))
        return data

    def column_titles(self) -> str:
        """Titles over the stamp, category and message columns of terminal rows."""
        return (
            "TIME".ljust(STAMP_WIDTH)
            + "SOURCE".ljust(self._category_width + 1)
            + "MESSAGE"
        )

    def set_column_header(self, enabled: bool) -> None:
        """Reserve a top viewport margin for column titles (Amber phosphor only)."""
        self.ensurePolished()
        self.header_height = self.fontMetrics().lineSpacing() + 8 if enabled else 0
        self.setViewportMargins(self.gutter_width, self.header_height, 0, 0)
        self.column_header.place(self.header_height)
        self.gutter.place(self.gutter_width)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.column_header.place(self.header_height)
        if self._wrap_indent:
            self.rewrap()

    def set_entry_prompts(self, enabled: bool) -> None:
        super().set_entry_prompts(enabled)
        self.rewrap()
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
        # Read-only logs show the block caret only while focused for copy/selection.
        if retro_console(self) and blink().on and self.hasFocus():
            prompt_cursor(self)

    def setPlainText(self, text: str | None) -> None:
        self._last_body = None
        self._category_width = SUBJECT_WIDTH + 2
        self._actions.clear()
        bodies = [terminal_body(line) for line in (text or "").splitlines() if line]
        for body in bodies:
            prefix = CATEGORY_PREFIX.match(body)
            if prefix is not None:
                self._category_width = max(self._category_width, len(prefix[1]))
        self._wrap_indent = 0
        super().setPlainText(
            "\n".join(terminal_row(self._align_categories(body)) for body in bodies)
        )
        self.rewrap()

    def clear(self) -> None:
        self._last_body = None
        self._category_width = SUBJECT_WIDTH + 2
        self._actions.clear()
        super().clear()

    def appendPlainText(self, text: str | None) -> None:
        """Append a timestamped row, skipping an exact repeat of the last row."""
        if not text:
            return
        first, separator, rest = text.partition("\n")
        body = self._align_categories(terminal_body(first) + separator + rest)
        if body != self._last_body:
            self._append_row(body)

    def _append_row(self, body: str) -> None:
        body = self._align_categories(body)
        self._last_body = body
        text = terminal_row(body)
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
        last = document.lastBlock().blockNumber()
        super().appendPlainText(text)
        if self._wrap_indent:
            self.rewrap(document.findBlockByNumber(last + 1))
        position = 0
        if not following and anchor.isValid():
            block = document.begin()
            while block.isValid() and block != anchor:
                position += block.lineCount()
                block = block.next()
            position += line_offset
        vertical.setValue(vertical.maximum() if following else position)
        horizontal.setValue(x)

    def _align_categories(self, body: str) -> str:
        prefix = CATEGORY_PREFIX.match(body)
        if prefix is None:
            return body
        width = max(self._category_width, len(prefix[1]))
        if width > self._category_width:
            vertical, horizontal = self.verticalScrollBar(), self.horizontalScrollBar()
            assert vertical is not None and horizontal is not None
            y, x = vertical.value(), horizontal.value()
            following = y >= vertical.maximum()
            anchor = self.firstVisibleBlock()
            document = self.document()
            assert document is not None
            block = document.begin()
            while block.isValid():
                existing = CATEGORY_PREFIX.match(block.text()[STAMP_WIDTH:])
                if existing is not None:
                    old_lines = block.lineCount()
                    cursor = QTextCursor(block)
                    cursor.setPosition(
                        block.position() + STAMP_WIDTH + len(existing[1])
                    )
                    cursor.setPosition(
                        block.position() + STAMP_WIDTH + existing.end(),
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    cursor.insertText(" " * (width - len(existing[1]) + 1))
                    if block.blockNumber() < anchor.blockNumber():
                        y += block.lineCount() - old_lines
                block = block.next()
            vertical.setValue(vertical.maximum() if following else y)
            horizontal.setValue(x)
            self._category_width = width
            if self._wrap_indent:
                # Realign existing wraps to the wider message column.
                self.rewrap()
        return f"{prefix[1]:<{width}} {body[prefix.end() :]}"

    def append_entry(
        self, summary: str, details: str, *, error: bool | None = None
    ) -> None:
        """Append a concise row with diagnostics bound to its document block."""
        summary = summary.replace("\r\n", "\n").replace("\r", "\n")
        first, *rest = summary.splitlines() or [""]
        self._append_row(" · ".join([terminal_body(first), *rest]))
        document = self.document()
        assert document is not None
        block = document.lastBlock()
        block.setUserData(_LogDetails(details, error=error))
        self.highlighter.rehighlightBlock(block)
        self.setToolTip(
            "Right-click or use the context-menu key on an entry for details."
        )

    def action_entry(
        self, key: tuple[str, ...], message: str, result: str = "", details: str = ""
    ) -> None:
        """Bind progress to a retained block and append its observed result in place."""
        self._actions = {k: b for k, b in self._actions.items() if b.isValid()}
        block = self._actions.get(key)
        if result:
            if block is None:
                if message and result != "Done" and details:
                    self.append_entry(
                        f"{message} [{result}]",
                        details,
                        error=result in {"Failed", "Rejected", "Unconfirmed"},
                    )
                return
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertText(f" [{result}]")
            if details:
                block.setUserData(
                    _LogDetails(
                        details, error=result in {"Failed", "Rejected", "Unconfirmed"}
                    )
                )
                self.setToolTip(
                    "Right-click or use the context-menu key on an entry for details."
                )
            self.highlighter.rehighlightBlock(block)
            self._actions.pop(key, None)
            self._last_body = None
            return
        if block is not None:
            body = self._align_categories(terminal_body(message))
            vertical, horizontal = self.verticalScrollBar(), self.horizontalScrollBar()
            assert vertical is not None and horizontal is not None
            y, x = vertical.value(), horizontal.value()
            following = y >= vertical.maximum()
            before_anchor = block.blockNumber() < self.firstVisibleBlock().blockNumber()
            old_lines = block.lineCount()
            cursor = QTextCursor(block)
            cursor.setPosition(block.position() + STAMP_WIDTH)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            cursor.insertText(body)
            if self._wrap_indent:
                self.rewrap(block)
            if before_anchor:
                y += block.lineCount() - old_lines
            vertical.setValue(vertical.maximum() if following else y)
            horizontal.setValue(x)
            self._last_body = None
            return
        self._append_row(terminal_body(message))
        document = self.document()
        assert document is not None
        self._actions[key] = document.lastBlock()

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
