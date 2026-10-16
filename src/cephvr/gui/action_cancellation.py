"""Cooperative GUI intent cancellation; never cancels an in-flight transport call."""

from dataclasses import dataclass, field
from threading import Event
from typing import Any

from PyQt6.QtWidgets import QPushButton

from cephvr.client.session import ClientError


class ActionCancelled(ClientError):
    pass


@dataclass
class Cancellation:
    requested: Event = field(default_factory=Event)


def checkpoint(options: dict[str, Any]) -> None:
    token = options.get("cancellation")
    if isinstance(token, Cancellation) and token.requested.is_set():
        raise ActionCancelled("Cancellation requested")


class PendingAction:
    """One button owns one immutable request token until terminal evidence."""

    def __init__(self) -> None:
        self.button: QPushButton | None = None
        self.token: Cancellation | None = None
        self.label = ""
        self.tooltip = ""

    def begin(self, button: QPushButton) -> Cancellation:
        assert self.token is None
        self.button = button
        self.label = button.text()
        self.tooltip = button.toolTip()
        self.token = Cancellation()
        return self.token

    def cancel(self, button: QPushButton) -> bool:
        if button is not self.button or self.token is None:
            return False
        if button.isEnabled():
            self.token.requested.set()
            self.refresh(True)
        return True

    def refresh(self, allowed: bool) -> None:
        if self.button is not None and self.token is not None:
            requested = self.token.requested.is_set()
            self.button.setText("Cancelling…" if requested else "Cancel")
            self.button.setEnabled(allowed and not requested)
            self.button.setToolTip("Wait for the current call and confirmed cleanup")

    def finish(self) -> None:
        if self.button is not None:
            self.button.setText(self.label)
            self.button.setToolTip(self.tooltip)
        self.button = None
        self.token = None
