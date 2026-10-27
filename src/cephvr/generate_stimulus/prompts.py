"""Modal prompts with explicit buttons and Cancel as the safe default."""

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

Button = QMessageBox.StandardButton


def _run(box: QMessageBox) -> Button:
    box.setDefaultButton(Button.Cancel)
    box.setEscapeButton(Button.Cancel)
    cancel = box.button(Button.Cancel)
    assert cancel is not None
    cancel.setProperty("stopAction", True)
    box.exec()
    clicked = box.clickedButton()
    return Button.Cancel if clicked is None else box.standardButton(clicked)


def ask_unsaved(parent: QWidget, title: str, text: str) -> str:
    """Return "save", "discard" or "cancel"."""
    box = QMessageBox(
        QMessageBox.Icon.Question,
        title,
        text,
        Button.Save | Button.Discard | Button.Cancel,
        parent,
    )
    save = box.button(Button.Save)
    assert save is not None
    save.setText("Save as…")
    return {Button.Save: "save", Button.Discard: "discard"}.get(_run(box), "cancel")


def ask_reset(parent: QWidget, title: str, text: str, action: str) -> bool:
    """Confirm a destructive action."""
    box = QMessageBox(
        QMessageBox.Icon.Question, title, text, Button.Yes | Button.Cancel, parent
    )
    yes = box.button(Button.Yes)
    assert yes is not None
    yes.setText(action)
    return _run(box) == Button.Yes


def save_file_name(parent: QWidget, title: str, suggested: str) -> str:
    """JSON save dialog whose overwrite check sees the final, suffixed name."""
    dialog = QFileDialog(parent, title, suggested, "JSON (*.json)")
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setDefaultSuffix("json")
    return dialog.selectedFiles()[0] if dialog.exec() else ""
