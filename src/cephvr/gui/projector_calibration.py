"""Compact per-face usable pixel controls sharing the rig's retained drafts."""

from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator, QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QWidget,
)

from cephvr.gui.components import Card, button, field
from cephvr.gui.editing_card import EditingCard
from cephvr.gui.projector_geometry import FACES
from cephvr.gui.theme import SIZES


class AdjustmentEntry(QLineEdit):
    """Whole-pixel entry with a blank measured default and one-pixel stepping."""

    def __init__(self, axis: str, *, size: bool = True) -> None:
        super().__init__()
        self.setPlaceholderText(axis)
        self.minimum = 1 if size else -2147483647
        self.maximum = 2147483647
        self.setValidator(QIntValidator(self.minimum, self.maximum, self))
        self.setToolTip("Up/Down: adjust by 1 px")

    def step_by(self, direction: int) -> None:
        if self.isReadOnly() or not self.isEnabled():
            return
        try:
            value = Decimal(self.text() or self.placeholderText())
            if not value.is_finite() or value != value.to_integral_value():
                return
            stepped = max(self.minimum, min(self.maximum, int(value) + direction))
        except InvalidOperation:
            return
        text = str(stepped)
        if self.text() != text:
            self.setText(text)
            self.textEdited.emit(text)

    def set_limits(self, minimum: int, maximum: int) -> None:
        self.minimum, self.maximum = minimum, maximum
        self.setValidator(QIntValidator(minimum, maximum, self))
        self.cap()

    def cap(self) -> None:
        try:
            value = Decimal(self.text())
            if value.is_finite() and value == value.to_integral_value():
                capped = max(self.minimum, min(self.maximum, int(value)))
                if capped != value:
                    self.setText(str(capped))
        except InvalidOperation:
            pass

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if (
            event is not None
            and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down)
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and not self.isReadOnly()
        ):
            event.accept()
            self.step_by(1 if event.key() == Qt.Key.Key_Up else -1)
        else:
            super().keyPressEvent(event)


class CalibrationCards(Card):
    adjustments_changed = pyqtSignal(str, str)
    launch_requested = pyqtSignal()
    measurement_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, drafts: dict[str, dict[str, str]]) -> None:
        super().__init__("Projection calibration")
        self.drafts = drafts
        self.controls: dict[tuple[str, str], QWidget] = {}
        self.cards: dict[str, EditingCard] = {}
        self.body.setSpacing(SIZES.group_gap)
        for face in FACES:
            card = EditingCard(face, filled=True)
            self.cards[face] = card
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            card.body.addLayout(grid)
            self.body.addWidget(card)
            for col, keys in enumerate(
                (
                    ("flip_x", "flip_y"),
                    ("valid_width_px", "valid_height_px"),
                    ("offset_x_px", "offset_y_px"),
                ),
                1,
            ):
                cell = QWidget()
                layout = QHBoxLayout(cell)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(5)
                for axis, key in zip(("X", "Y"), keys, strict=False):
                    control: QCheckBox | QLineEdit
                    if col == 1:
                        control = QCheckBox(axis)
                        control.toggled.connect(
                            lambda value, f=face, k=key: self.drafts[f].__setitem__(
                                k, str(value)
                            )
                        )
                    else:
                        control = AdjustmentEntry(
                            ("Width" if axis == "X" else "Height") if col == 2 else "0",
                            size=col == 2,
                        )
                        control.setMinimumWidth(0)
                        control.setMaximumWidth(90)
                        control.textChanged.connect(
                            lambda value, f=face, k=key: self.drafts[f].__setitem__(
                                k, value
                            )
                        )
                        control.textEdited.connect(
                            lambda _value, f=face, k=key: self.adjust(f, k)
                        )
                    control.setAccessibleName(f"{face} {key}")
                    self.controls[face, key] = control
                    layout.addWidget(control)
                title = ("Inverse", "Width / Height (px)", "Offset X / Y (px)")[col - 1]
                grid.addWidget(field(title, cell), 0, col - 1)
                grid.setColumnStretch(col - 1, 1)
        self.presentation_button = button("Launch projection calibration")
        self.presentation_button.setToolTip(
            "Prepare calibration files and launch with a connected managed Visual Stimulus renderer"
        )
        self.presentation_button.setEnabled(False)
        self.presentation_button.clicked.connect(self.request_presentation)
        self.measurement_button = button("Launch reference calibration")
        self.measurement_button.setEnabled(False)
        self.measurement_button.clicked.connect(self.request_measurement)
        self.body.insertWidget(1, self.presentation_button)
        self.presentation_view = ""
        self.presentation_active = False
        self.presentation_available = False
        self.presentation_pending = False
        self.outputs: dict[str, tuple[int, int]] = {}

    def refresh_dimensions(self, outputs: dict[str, tuple[int, int]]) -> None:
        from cephvr.gui.projector_extent import valid_pixels

        self.outputs = outputs
        for face, (width, height) in outputs.items():
            for key, limit in (("valid_width_px", width), ("valid_height_px", height)):
                control = self.controls[face, key]
                assert isinstance(control, AdjustmentEntry)
                control.set_limits(1, limit)
            try:
                values = {
                    f"screens.{face}.{k}": float(v) if v else None
                    for k, v in self.drafts[face].items()
                    if k not in ("flip_x", "flip_y")
                }
                for key in ("valid_width_px", "valid_height_px"):
                    values[f"screens.{face}.{key}"] = None
                pixels = valid_pixels(values, face, width, height)
                for key, value in zip(
                    ("valid_width_px", "valid_height_px"), pixels, strict=True
                ):
                    control = self.controls[face, key]
                    assert isinstance(control, QLineEdit)
                    control.setPlaceholderText(str(value))
                    control.setToolTip(
                        "Blank uses measured size. Up/Down: 1 px. Capped at the projector image size."
                    )
            except (ValueError, TypeError):
                pass
            self.cap_offsets(face)

    def cap_offsets(self, face: str) -> None:
        dimensions = self.outputs.get(face)
        if dimensions is None:
            return
        for axis, key, native in zip(
            ("x", "y"), ("valid_width_px", "valid_height_px"), dimensions, strict=True
        ):
            size = self.controls[face, key]
            assert isinstance(size, AdjustmentEntry)
            try:
                pixels = int(size.text() or size.placeholderText())
            except ValueError:
                continue
            limit = max(0, (native - pixels) // 2)
            offset = self.controls[face, f"offset_{axis}_px"]
            assert isinstance(offset, AdjustmentEntry)
            offset.set_limits(-limit, limit)
            offset.setToolTip(
                f"From image center, {-limit} to {limit} px. Positive {axis.upper()}: {'right' if axis == 'x' else 'up'}. Up/Down: 1 px."
            )

    def adjust(self, face: str, key: str) -> None:
        control = self.controls[face, key]
        assert isinstance(control, AdjustmentEntry)
        control.cap()
        self.cap_offsets(face)
        self.adjustments_changed.emit(face, key)

    def request_measurement(self) -> None:
        if not self.presentation_available or self.presentation_pending:
            return
        if self.presentation_active:
            if self.presentation_view == "reference_bars":
                self.close_requested.emit()
        else:
            self.measurement_requested.emit()

    def request_presentation(self) -> None:
        if not self.presentation_available or self.presentation_pending:
            return
        if self.presentation_active:
            if self.presentation_view != "reference_bars":
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
        reference_active = active and view == "reference_bars"
        projection_active = active and view in ("", "frame_grid")
        self.presentation_button.setText(
            "Close" if projection_active else "Launch projection calibration"
        )
        self.measurement_button.setText(
            "Close" if reference_active else "Launch reference calibration"
        )
        self.presentation_button.setEnabled(
            available and not pending and (not active or projection_active)
        )
        self.measurement_button.setEnabled(
            available and not pending and (not active or reference_active)
        )
