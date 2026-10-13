"""Explicit operator choices for managed GUI close failures."""

from __future__ import annotations

from typing import Literal

from PyQt6.QtWidgets import QMessageBox, QWidget

SaveFailureChoice = Literal["retry", "discard"] | None


def save_failure_choice(parent: QWidget, reason: str) -> SaveFailureChoice:
    """Return only a button the operator explicitly selected; dismissal is inert."""
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle("GUI configuration not saved")
    dialog.setText("The GUI configuration could not be saved.")
    dialog.setInformativeText(reason)
    retry = dialog.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
    discard = dialog.addButton(
        "Close without saving", QMessageBox.ButtonRole.DestructiveRole
    )
    dialog.exec()
    selected = dialog.clickedButton()
    if selected is retry:
        return "retry"
    if selected is discard:
        return "discard"
    return None
