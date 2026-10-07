"""Single-window retained-state acknowledgement and exact prompt responses."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_status import retained_summary


class ManagedPrompts:
    """Own prompt windows while the manager supplies authority and transport."""

    def __init__(
        self,
        parent: QWidget,
        *,
        queue_response: Callable[[bytes, str], bool],
        acknowledged: Callable[[int, str], None],
        log: Callable[[str], None],
    ) -> None:
        self.parent = parent
        self.queue_response = queue_response
        self.acknowledged = acknowledged
        self.log = log
        self.snapshot: pb.Snapshot | None = None
        self.retained_dialog: QMessageBox | None = None
        self.prompt_dialog: QDialog | None = None
        self.prompt_label: QLabel | None = None
        self.prompt_choices: QHBoxLayout | None = None
        self.prompt_id = ""
        self.prompt_buttons: list[QPushButton] = []
        self.pending_prompt_ids: set[str] = set()
        self.queued_prompt_id = ""
        self.connection_epoch = 0
        self.controller_generation = ""
        self.can_respond = False
        self._retained_dialog_serial = 0
        self._retained_dialog_identity: tuple[int, str] | None = None

    def update(
        self,
        snapshot: pb.Snapshot,
        *,
        require_acknowledgement: bool,
        can_respond: bool,
        connection_epoch: int = 0,
    ) -> None:
        self.snapshot = snapshot
        self.connection_epoch = connection_epoch
        self.controller_generation = snapshot.controller_generation
        self.can_respond = can_respond and not require_acknowledgement
        identity = (connection_epoch, snapshot.controller_generation)
        if self._retained_dialog_identity != identity:
            self.invalidate_retained_summary()
        if require_acknowledgement:
            self._show_retained_summary(identity)
            if self.prompt_dialog is not None:
                self.prompt_dialog.hide()
            return
        if self.retained_dialog is not None:
            self.retained_dialog.hide()
        self._update_prompt(snapshot, can_respond=can_respond)

    def review_retained_summary(self) -> None:
        if self.snapshot is not None:
            self._show_retained_summary(
                (self.connection_epoch, self.controller_generation)
            )

    def review_prompt(self, *, can_respond: bool) -> None:
        if self.snapshot is not None:
            self._update_prompt(self.snapshot, can_respond=can_respond, reopen=True)

    def hide_prompt(self) -> None:
        self.can_respond = False
        self.snapshot = None
        if self.prompt_dialog is not None:
            self.prompt_dialog.hide()

    def operation_finished(self, action: str) -> None:
        if action != "respond_prompt":
            return
        self.pending_prompt_ids.discard(self.queued_prompt_id)
        self.queued_prompt_id = ""
        if self.snapshot is not None:
            self._update_prompt(self.snapshot, can_respond=self.can_respond)

    def invalidate_retained_summary(self) -> None:
        """Dismiss a reconnect dialog so it cannot acknowledge a later connection."""
        dialog, self.retained_dialog = self.retained_dialog, None
        self._retained_dialog_identity = None
        self._retained_dialog_serial += 1
        if dialog is not None:
            dialog.reject()

    def _show_retained_summary(self, identity: tuple[int, str]) -> None:
        if self.snapshot is None:
            return
        if (
            self.retained_dialog is not None
            and self._retained_dialog_identity == identity
        ):
            self.retained_dialog.setInformativeText(retained_summary(self.snapshot))
            self.retained_dialog.raise_()
            self.retained_dialog.activateWindow()
            return
        self.invalidate_retained_summary()
        dialog = QMessageBox(self.parent)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Controller state while disconnected")
        dialog.setText("Review retained controller events before continuing.")
        dialog.setInformativeText(retained_summary(self.snapshot))
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        dialog.setModal(True)
        self._retained_dialog_serial += 1
        serial = self._retained_dialog_serial
        dialog.finished.connect(
            lambda result: self._retained_dialog_finished(identity, serial, result)
        )
        self.retained_dialog = dialog
        self._retained_dialog_identity = identity
        dialog.open()

    def _retained_dialog_finished(
        self, identity: tuple[int, str], serial: int, result: int
    ) -> None:
        if (
            self._retained_dialog_serial != serial
            or self._retained_dialog_identity != identity
        ):
            return
        self.retained_dialog = None
        self._retained_dialog_identity = None
        if result == int(QMessageBox.StandardButton.Ok):
            self.acknowledged(*identity)

    def _update_prompt(
        self,
        snapshot: pb.Snapshot,
        *,
        can_respond: bool,
        reopen: bool = False,
    ) -> None:
        if not snapshot.prompts:
            self.prompt_id = ""
            if self.prompt_dialog is not None:
                self.prompt_dialog.hide()
            return
        prompt = snapshot.prompts[0]
        stamped = prompt.SerializeToString()
        self._ensure_prompt_dialog()
        assert self.prompt_dialog is not None
        assert self.prompt_label is not None
        assert self.prompt_choices is not None
        self.prompt_id = prompt.prompt_id
        consequence = (
            prompt.runtime_incident.consequence
            if prompt.HasField("runtime_incident")
            else ""
        )
        extra = f"\n\n{consequence}" if consequence else ""
        self.prompt_label.setText(
            prompt.explanation + extra
            if prompt.explanation
            else "Choose how the controller should proceed." + extra
        )
        self.prompt_dialog.setWindowTitle(
            "Controller requires a decision"
            + (
                f" ({len(snapshot.prompts)} active)"
                if len(snapshot.prompts) > 1
                else ""
            )
        )
        for button in self.prompt_buttons:
            self.prompt_choices.removeWidget(button)
            button.hide()
            button.deleteLater()
        self.prompt_buttons.clear()
        allowed = can_respond and prompt.prompt_id not in self.pending_prompt_ids
        for choice in prompt.permitted_choices:
            button = QPushButton(choice, self.prompt_dialog)
            button.setEnabled(allowed)
            button.clicked.connect(
                lambda _checked=False, value=choice, encoded=stamped: self._respond(
                    encoded, value
                )
            )
            self.prompt_choices.addWidget(button)
            self.prompt_buttons.append(button)
        if reopen or not self.prompt_dialog.isVisible():
            self.prompt_dialog.show()
            self.prompt_dialog.raise_()

    def _ensure_prompt_dialog(self) -> None:
        if self.prompt_dialog is not None:
            return
        dialog = QDialog(self.parent)
        dialog.setWindowTitle("Controller requires a decision")
        layout = QVBoxLayout(dialog)
        prompt_label = QLabel(dialog)
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)
        choices = QHBoxLayout()
        layout.addLayout(choices)
        close = QPushButton("Close", dialog)
        close.clicked.connect(dialog.hide)
        layout.addWidget(close)
        self.prompt_dialog = dialog
        self.prompt_label = prompt_label
        self.prompt_choices = choices

    def _respond(self, stamped_prompt: bytes, choice: str) -> None:
        if self.snapshot is None:
            return
        prompt_id = self.prompt_id
        for button in self.prompt_buttons:
            button.setEnabled(False)
        if not self.queue_response(stamped_prompt, choice):
            self.log(
                f"Prompt {prompt_id}: response was not queued; reopen the prompt to retry."
            )
            for button in self.prompt_buttons:
                button.setEnabled(True)
            return
        self.pending_prompt_ids.add(prompt_id)
        self.queued_prompt_id = prompt_id
