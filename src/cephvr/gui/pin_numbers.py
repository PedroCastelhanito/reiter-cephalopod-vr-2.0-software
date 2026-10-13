"""Numeric Uno pin editors with canonical firmware tokens at submission."""

import re

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import QLineEdit


def firmware_pin(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[0-9]+", value):
        return f"D{int(value)}"
    return value


def pin_number(value: str) -> str:
    match = re.fullmatch(r"D([0-9]+)", value)
    return match[1] if match else value


class PinNumber(QLineEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setPlaceholderText("Pin")
        self.setValidator(
            QRegularExpressionValidator(QRegularExpression("[0-9]*"), self)
        )

    def setText(self, text: str | None) -> None:
        text = text or ""
        super().setText(pin_number(text))
