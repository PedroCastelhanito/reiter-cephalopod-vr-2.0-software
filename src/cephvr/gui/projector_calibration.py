"""Compact per-face valid-area table, sharing the rig's retained drafts."""

from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidgetItem,
    QWidget,
)

from cephvr.gui.components import Card, button, label
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.tables import DataTable

VIEW_TITLES = {
    "reference_bars": "Reference bars",
    "frame_grid": "Frame and grid",
    "seam_check": "Seam check",
}
MARGIN_PAIRS = (("margin_left", "margin_right"), ("margin_top", "margin_bottom"))
KEYSTONE_PAIR = ("keystone_h", "keystone_v")
EDGE_NAMES = {
    "margin_left": "left",
    "margin_right": "right",
    "margin_top": "top",
    "margin_bottom": "bottom",
    "keystone_h": "horizontal keystone",
    "keystone_v": "vertical keystone",
}
KEYSTONE_HINTS = {
    "keystone_h": (
        "Horizontal keystone: pixels by which the top edge of the valid area is "
        "narrower than the bottom edge. Negative: the bottom edge is narrower."
    ),
    "keystone_v": (
        "Vertical keystone: pixels by which the right edge of the valid area is "
        "shorter than the left edge. Negative: the left edge is shorter."
    ),
}


def _parse_margin(text: str, *, signed: bool = False) -> Decimal | None:
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() and (signed or value >= 0) else None


class MarginEntry(QLineEdit):
    """One valid-area edge or keystone in output pixels; empty means automatic/none.

    Up/Down step by 1 px (Shift: 10 px) without rounding typed input; invalid text is
    outlined instead of being silently ignored. Keystone entries are signed.
    """

    def __init__(self, edge: str, *, signed: bool = False, hint: str = "") -> None:
        super().__init__()
        self.edge = edge
        self.signed = signed
        self.step = Decimal(1)
        if signed:
            self.setPlaceholderText("0")
            self.setToolTip(f"{hint} Up/Down: 1 px, Shift+Up/Down: 10 px.")
        else:
            self.setPlaceholderText("auto")
            self.set_hint(None)
        self.textChanged.connect(self.mark_validity)

    def set_hint(self, automatic: float | None) -> None:
        """Show the automatic margin as the placeholder; None when unknown."""
        if automatic is None:
            self.setPlaceholderText("0")
            detail = "No measurement yet: the edge starts at the projector border."
        elif automatic < 0:
            self.setPlaceholderText("short")
            detail = "The projection is smaller than the screen on this axis."
        else:
            self.setPlaceholderText(f"{automatic:.1f}")
            detail = "Centered from the measurement."
        self.setToolTip(
            f"Pixels hidden at the {self.edge} edge of the projected image "
            f"(the part that falls off the screen). Empty = automatic. {detail} "
            "Up/Down: 1 px, Shift+Up/Down: 10 px."
        )

    def mark_validity(self, text: str) -> None:
        invalid = (
            bool(text.strip())
            and _parse_margin(text.strip(), signed=self.signed) is None
        )
        if self.property("invalid") != invalid:
            self.setProperty("invalid", invalid)
            style = self.style()
            if style is not None:
                style.unpolish(self)
                style.polish(self)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if (
            event is None
            or event.key() not in (Qt.Key.Key_Up, Qt.Key.Key_Down)
            or event.modifiers()
            not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier)
            or self.isReadOnly()
        ):
            super().keyPressEvent(event)
            return
        event.accept()
        text = self.text().strip()
        start = (
            _parse_margin(text, signed=self.signed)
            if text
            else _parse_margin(self.placeholderText(), signed=self.signed)
        )
        if start is None:
            start = Decimal(0) if not text else None
        if start is None:
            return
        step = self.step * (
            10 if event.modifiers() == Qt.KeyboardModifier.ShiftModifier else 1
        )
        direction = 1 if event.key() == Qt.Key.Key_Up else -1
        value = start + direction * step
        if not self.signed:
            value = max(Decimal(0), value)
        value = value.quantize(Decimal("0.1"))
        result = format(value.normalize(), "f")
        self.setText(result)
        self.textEdited.emit(result)


class CalibrationTable(Card):
    adjustments_changed = pyqtSignal(str, str)
    launch_requested = pyqtSignal()
    seam_requested = pyqtSignal()
    measurement_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, drafts: dict[str, dict[str, str]]) -> None:
        super().__init__("Screen calibration")
        self.drafts = drafts
        self.controls: dict[tuple[str, str], QWidget] = {}
        self.table = DataTable(len(FACES), 5)
        self.table.setHorizontalHeaderLabels(
            [
                "Screen",
                "Inverse",
                "Left / Right (px)",
                "Top / Bottom (px)",
                "Keystone H / V (px)",
            ]
        )
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for row, face in enumerate(FACES):
            self.table.setItem(row, 0, QTableWidgetItem(face))
            for col, keys in enumerate(
                (("flip_x", "flip_y"), *MARGIN_PAIRS, KEYSTONE_PAIR), 1
            ):
                cell = QWidget()
                layout = QHBoxLayout(cell)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(5)
                for axis, key in zip(("X", "Y"), keys, strict=True):
                    control: QCheckBox | QLineEdit
                    if col == 1:
                        control = QCheckBox(axis)
                        control.toggled.connect(
                            lambda value, f=face, k=key: self.drafts[f].__setitem__(
                                k, str(value)
                            )
                        )
                    else:
                        control = MarginEntry(
                            EDGE_NAMES[key],
                            signed=key in KEYSTONE_PAIR,
                            hint=KEYSTONE_HINTS.get(key, ""),
                        )
                        control.textEdited.connect(
                            lambda _value, f=face, k=key: self.adjustments_changed.emit(
                                f, k
                            )
                        )
                        control.setMinimumWidth(0)
                        control.setMaximumWidth(90)
                        control.textChanged.connect(
                            lambda value, f=face, k=key: self.drafts[f].__setitem__(
                                k, value
                            )
                        )
                    control.setAccessibleName(f"{face} {key}")
                    self.controls[face, key] = control
                    layout.addWidget(control)
                self.table.set_control(row, col, cell)
        self.table.fit_rows()
        self.body.addWidget(self.table)
        self.presentation_button = button("Show frame and grid")
        self.presentation_button.setToolTip(
            "Prepare calibration files and show the grid on the selected projectors"
        )
        self.presentation_button.setEnabled(False)
        self.presentation_button.clicked.connect(self.request_presentation)
        self.seam_button = button("Show seam check")
        self.seam_button.setToolTip(
            "Bold lines that cross the screen boundaries: they should continue unbroken"
        )
        self.seam_button.setEnabled(False)
        self.seam_button.clicked.connect(self.request_seam)
        self.reset_button = button("Reset valid areas")
        self.reset_button.setToolTip(
            "Clear every margin back to automatic and remove all keystone"
        )
        self.reset_button.clicked.connect(self.reset_margins)
        self.measurement_button = button("Show reference bars")
        self.measurement_button.setEnabled(False)
        self.measurement_button.clicked.connect(self.request_measurement)
        actions = QWidget()
        actions_row = QHBoxLayout(actions)
        actions_row.setContentsMargins(0, 0, 0, 0)
        for action in (self.presentation_button, self.seam_button, self.reset_button):
            actions_row.addWidget(action, 1)
        self.status = label("", "muted")
        self.status.setWordWrap(True)
        self.body.insertWidget(1, actions)
        self.body.insertWidget(2, self.status)
        self.presentation_view = ""
        self.presentation_active = False
        self.presentation_available = False
        self.presentation_pending = False
        self.presentation_unknown = False
        self.detail = ""
        self.detail_is_error = False
        self.refresh_status()

    def set_auto_margins(self, face: str, margins: tuple[float | None, ...]) -> None:
        for key, value in zip(
            (key for pair in MARGIN_PAIRS for key in pair), margins, strict=True
        ):
            control = self.controls[face, key]
            assert isinstance(control, MarginEntry)
            control.set_hint(value)

    def reset_margins(self) -> None:
        """Clear every margin and keystone; each is reported like a typed edit."""
        for (face, key), control in self.controls.items():
            if (
                isinstance(control, MarginEntry)
                and control.isEnabled()
                and control.text()
            ):
                control.setText("")
                self.adjustments_changed.emit(face, key)

    def set_detail(self, text: str, *, error: bool = False) -> None:
        """Short live-adjustment outcome shown under the buttons."""
        self.detail, self.detail_is_error = text, error
        self.refresh_status()

    def refresh_status(self) -> None:
        if self.presentation_pending:
            state = "Working…"
        elif self.presentation_unknown:
            state = "Renderer state unknown. Press Close to recover."
        elif self.presentation_active:
            title = VIEW_TITLES.get(self.presentation_view, "Calibration")
            state = f"{title} active."
        else:
            state = "No calibration shown."
        self.status.setText(f"{state} {self.detail}".strip())
        role = "error" if self.detail_is_error or self.presentation_unknown else "muted"
        if self.status.property("role") != role:
            self.status.setProperty("role", role)
            style = self.status.style()
            if style is not None:
                style.unpolish(self.status)
                style.polish(self.status)

    def request_measurement(self) -> None:
        if (
            self.presentation_available
            and not self.presentation_pending
            and not self.presentation_active
        ):
            self.measurement_requested.emit()

    def request_seam(self) -> None:
        if (
            self.presentation_available
            and not self.presentation_pending
            and not self.presentation_active
        ):
            self.seam_requested.emit()

    def request_presentation(self) -> None:
        if not self.presentation_available or self.presentation_pending:
            return
        if self.presentation_active:
            self.close_requested.emit()
        else:
            self.launch_requested.emit()

    def set_presentation_state(
        self,
        *,
        active: bool,
        available: bool,
        pending: bool = False,
        view: str = "",
        unknown: bool = False,
    ) -> None:
        """Show confirmed renderer state, never infer it from a button click."""
        self.presentation_view = view
        self.presentation_active = active
        self.presentation_available = available
        self.presentation_pending = pending
        self.presentation_unknown = unknown
        if not active:
            self.detail, self.detail_is_error = "", False
        self.presentation_button.setText(
            "Close calibration" if active else "Show frame and grid"
        )
        self.presentation_button.setEnabled(available and not pending)
        idle = available and not pending and not active
        self.measurement_button.setEnabled(idle)
        self.seam_button.setEnabled(idle)
        self.refresh_status()
