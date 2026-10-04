"""Shared path display and asynchronous directory selection for local drafts."""

from pathlib import Path, PurePosixPath

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPaintEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QStyle,
    QStyleOptionFrame,
    QStylePainter,
    QWidget,
)

from cephvr.gui.components import button, equal_row_height
from cephvr.gui.theme import SIZES


class PathEdit(QLineEdit):
    """Elide only the unfocused painting; text/copy/edit always retain the full path."""

    def __init__(self, *, filename_only: bool = False) -> None:
        super().__init__()
        self.filename_only = filename_only
        self.textChanged.connect(self.setToolTip)

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        if (self.hasFocus() and not self.filename_only) or not self.text():
            super().paintEvent(event)
            return
        option = QStyleOptionFrame()
        self.initStyleOption(option)
        painter = QStylePainter(self)
        painter.drawPrimitive(QStyle.PrimitiveElement.PE_PanelLineEdit, option)
        style = self.style()
        assert style is not None
        rect = style.subElementRect(QStyle.SubElement.SE_LineEditContents, option, self)
        rect.adjust(2, 0, -2, 0)
        text = self.fontMetrics().elidedText(
            PurePosixPath(self.text().replace("\\", "/")).name
            if self.filename_only
            else self.text(),
            Qt.TextElideMode.ElideMiddle,
            rect.width(),
        )
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text
        )


class PathField(QWidget):
    path_selected = pyqtSignal(str)

    def __init__(self, *, title: str, placeholder: str, file_filter: str = "") -> None:
        super().__init__()
        self.title = title
        self.file_filter = file_filter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SIZES.field_x_gap)
        self.editor = PathEdit()
        self.editor.setPlaceholderText(placeholder)
        self.browse = button("Browse…", hint=title)
        equal_row_height(self.editor, self.browse)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.browse)
        self.browse.clicked.connect(self.choose_path)
        self.dialog: QFileDialog | None = None

    def choose_path(self) -> None:
        if not self.isEnabled():
            return
        if self.dialog is not None:
            self.dialog.raise_()
            return
        current = Path(self.editor.text()).expanduser()
        dialog = QFileDialog(self, self.title)
        if self.file_filter:
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            dialog.setNameFilter(self.file_filter)
            current = current.parent
        else:
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            dialog.setOption(QFileDialog.Option.ShowDirsOnly)
        dialog.setOption(QFileDialog.Option.ReadOnly)
        dialog.setDirectory(str(current if current.is_dir() else Path.home()))
        dialog.fileSelected.connect(
            lambda path: self.select_path(path) if self.dialog is dialog else None
        )
        dialog.finished.connect(self.finished)
        dialog.finished.connect(dialog.deleteLater)
        self.dialog = dialog
        dialog.open()

    def select_path(self, path: str) -> None:
        if self.isEnabled() and path:
            self.editor.setText(path)
            self.path_selected.emit(path)

    def finished(self, result: int) -> None:
        self.dialog = None


class DirectoryField(PathField):
    def __init__(self) -> None:
        super().__init__(
            title="Select output directory", placeholder="Set output directory"
        )


class PresetField(PathField):
    def __init__(self) -> None:
        super().__init__(
            title="Select camera parameter file",
            placeholder="Select a Pylon parameter file (.pfs)",
            file_filter="Pylon parameter files (*.pfs)",
        )
