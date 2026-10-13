"""Small helpers for role-owned MCU output rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cephvr.gui.microcontroller import MicrocontrollerPanel

ROLE_OUTPUTS = (
    ("behavioral", "Behavior cam"),
    ("tracking", "Tracking cam"),
    ("eye_tracking", "Eye tracking"),
)


class MicrocontrollerSignals:
    def __init__(self, panel: MicrocontrollerPanel) -> None:
        self.panel = panel

    def invalidate(self) -> None:
        return

    def refresh(self, editable: bool) -> None:
        panel = self.panel
        active = bool(
            panel.review_tests
            or panel.managed_test_key
            or panel.pending_test_key
            or panel.connection_pending
            or panel.upload_pending
        )
        for key, _label in ROLE_OUTPUTS:
            panel.output_remove[key].setEnabled(editable and not active)
            panel.pin_editors[key].setEnabled(editable and not active)

    def remove(self, key: str) -> None:
        panel = self.panel
        if (
            key in panel.pin_editors
            and panel.can_review
            and not (
                panel.review_tests
                or panel.managed_test_key
                or panel.pending_test_key
                or panel.connection_pending
                or panel.upload_pending
            )
        ):
            panel.set_role_pin(key, "")
