"""Compact per-face correction table, sharing the rig's retained drafts."""

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

from cephvr.gui.components import Card, button
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.tables import DataTable


class AdjustmentEntry(QLineEdit):
    """Step corrections without rounding imported drafts or partial typed input."""

    def __init__(self, axis: str, *, scale: bool) -> None:
        super().__init__()
        self.setPlaceholderText(axis)
        self.decimals = 2 if scale else 1
        self.step = Decimal("0.01" if scale else "0.1")
        self.default = Decimal(1 if scale else 0)
        self.scale = scale
        self.setToolTip(f"Up/Down: adjust by {self.step}{'' if scale else ' px'}")

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if (
            event is None
            or event.key() not in (Qt.Key.Key_Up, Qt.Key.Key_Down)
            or event.modifiers() != Qt.KeyboardModifier.NoModifier
            or self.isReadOnly()
        ):
            super().keyPressEvent(event)
            return
        event.accept()
        try:
            value = Decimal(self.text()) if self.text().strip() else self.default
            if not value.is_finite():
                return
            direction = 1 if event.key() == Qt.Key.Key_Up else -1
            value = (value + direction * self.step).quantize(self.step)
        except InvalidOperation:
            return
        if self.scale and value <= 0:
            return
        text = f"{value:.{self.decimals}f}"
        self.setText(text)
        self.textEdited.emit(text)


class CalibrationTable(Card):
    adjustments_changed = pyqtSignal(str, str)
    launch_requested = pyqtSignal()
    measurement_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, drafts: dict[str, dict[str, str]]) -> None:
        super().__init__("Screen calibration")
        self.drafts = drafts
        self.controls: dict[tuple[str, str], QWidget] = {}
        self.table = DataTable(len(FACES), 4)
        self.table.setHorizontalHeaderLabels(
            ["Screen", "Inverse", "Scale X / Y", "Offset X / Y (px)"]
        )
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for row, face in enumerate(FACES):
            self.table.setItem(row, 0, QTableWidgetItem(face))
            for col, keys in enumerate(
                (
                    ("flip_x", "flip_y"),
                    ("scale_u", "scale_v"),
                    ("offset_x", "offset_y"),
                ),
                1,
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
                        control = AdjustmentEntry(axis, scale=col == 2)
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
        self.presentation_button = button("Adjust frame and grid")
        self.presentation_button.setToolTip(
            "Prepare calibration files and launch with a connected managed Visual Stimulus renderer"
        )
        self.presentation_button.setEnabled(False)
        self.presentation_button.clicked.connect(self.request_presentation)
        self.measurement_button = button("Measure reference bars")
        self.measurement_button.setEnabled(False)
        self.measurement_button.clicked.connect(self.request_measurement)
        actions = QHBoxLayout()
        actions.addWidget(self.measurement_button)
        actions.addWidget(self.presentation_button)
        self.body.addLayout(actions)
        self.presentation_view = ""
        self.presentation_active = False
        self.presentation_available = False
        self.presentation_pending = False

    def request_measurement(self) -> None:
        if (
            self.presentation_available
            and not self.presentation_pending
            and not self.presentation_active
        ):
            self.measurement_requested.emit()

    def request_presentation(self) -> None:
        if not self.presentation_available or self.presentation_pending:
            return
        if self.presentation_active:
            self.close_requested.emit()
        else:
            self.launch_requested.emit()

    def set_presentation_state(
        self, *, active: bool, available: bool, pending: bool = False, view: str = ""
    ) -> None:
        """Show confirmed renderer state, never infer it from a button click."""
        self.presentation_view = view
        self.presentation_active = active
        self.presentation_available = available
        self.presentation_pending = pending
        self.presentation_button.setText("Close" if active else "Adjust frame and grid")
        self.presentation_button.setEnabled(available and not pending)
        self.measurement_button.setEnabled(available and not pending and not active)
