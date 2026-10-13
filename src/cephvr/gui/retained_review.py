"""Plain-text reconnect review dialog with a bounded reading viewport."""

from __future__ import annotations

from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.managed_status import retained_details, retained_summary
from cephvr.gui.theme import COLORS

_CATEGORY_HEADINGS = {
    "Retained errors:",
    "Recoveries:",
    "Incidents:",
    "Pending choices:",
    "Warnings:",
    "Operations needing attention:",
}


class RetainedReviewDialog(QDialog):
    """Present retained controller events and acknowledge only on Continue."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Controller events to review")
        self.setModal(True)
        self.resize(540, 400)
        self.setMinimumSize(460, 320)
        self._details_text = ""
        fit_window_to_screen(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        heading = QLabel("Controller events to review", self)
        heading.setProperty("role", "title")
        subtitle = QLabel(
            "Review retained errors, recovery work, warnings, and pending operations "
            "before continuing.",
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "hint")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        self.summary = QLabel(self)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.summary.setMargin(4)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.summary_scroll = QScrollArea(self)
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.summary_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.summary_scroll.setMinimumHeight(100)
        self.summary_scroll.setWidget(self.summary)
        layout.addWidget(self.summary_scroll, 1)

        actions = QHBoxLayout()
        self.copy_button = QPushButton("Copy details", self)
        self.copy_button.setAutoDefault(False)
        self.copy_button.clicked.connect(self.copy_details)
        self.continue_button = QPushButton("Continue", self)
        self.continue_button.setProperty("role", "primary")
        self.continue_button.setDefault(True)
        self.continue_button.clicked.connect(self.accept)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        actions.addWidget(self.continue_button)
        layout.addLayout(actions)

    def update_snapshot(self, state: pb.Snapshot) -> None:
        """Refresh the displayed and copied material from the latest snapshot."""
        self.summary.setText(self._summary_markup(retained_summary(state)))
        self._details_text = retained_details(
            state, routine_limit=len(state.operations)
        )

    def copy_details(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._details_text)

    @staticmethod
    def _summary_markup(summary: str) -> str:
        """Highlight only known headings; escape every snapshot-derived line."""
        paragraphs: list[str] = []
        for paragraph in summary.split("\n\n"):
            lines = paragraph.splitlines()
            if not lines:
                continue
            first = lines[0]
            if first in _CATEGORY_HEADINGS or first.startswith(
                "Completed operations: "
            ):
                heading = (
                    f'<span style="color:{COLORS.accent}; font-weight:700">'
                    f"{escape(first)}</span>"
                )
                paragraphs.append(
                    "<br>".join([heading, *(escape(line) for line in lines[1:])])
                )
            else:
                paragraphs.append("<br>".join(escape(line) for line in lines))
        return "".join(f'<p style="margin:0 0 8px 0">{item}</p>' for item in paragraphs)
