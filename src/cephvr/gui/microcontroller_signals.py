"""Editing and presence of the fixed MCU signal rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cephvr.gui.components import button, remove_button

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
        self.editors = {
            "trial-state": panel.trial_pin,
            **panel.pin_editors,
        }
        self.rows = {
            "trial-state": (panel.output_table, 0),
            **{key: (panel.output_table, row) for key, row in panel.role_rows.items()},
        }
        self.add_buttons = []
        for key, name in (("trial-state", "Trial state"),):
            remove = remove_button(f"Remove {name}")
            remove.clicked.connect(
                lambda _checked=False, signal=key: self.remove(signal)
            )
            panel.output_remove[key] = remove
            table, row = self.rows[key]
            table.set_control(row, 4, remove)
        for card, keys, title in (
            (
                panel.triggers,
                ("trial-state", *(key for key, _ in ROLE_OUTPUTS)),
                "Add output",
            ),
        ):
            control = button(title, "secondary")
            card.body.addWidget(control)
            self.add_buttons.append((control, keys))

    def invalidate(self) -> None:
        return

    def editable(self) -> bool:
        panel = self.panel
        return panel.can_review and not (
            panel.review_tests
            or panel.managed_test_key
            or panel.pending_test_key
            or panel.connection_pending
            or panel.upload_pending
        )

    def refresh(self, editable: bool) -> None:
        deferred_control = self.panel.enable_controls["projector-flip"]
        deferred_control.blockSignals(True)
        deferred_control.setChecked(False)
        deferred_control.blockSignals(False)
        self.panel.input_table.setRowHidden(0, True)
        self.panel.flip_pin.setEnabled(False)
        self.panel.enable_controls["projector-flip"].setEnabled(False)
        self.panel.test_buttons["projector-flip"].setEnabled(False)
        for key, editor in self.editors.items():
            present = bool(editor.text().strip())
            table, row = self.rows[key]
            # Keep an editor visible while the operator replaces its pin number.
            table.setRowHidden(row, not present and not editor.hasFocus())
            self.panel.output_remove[key].setEnabled(editable)
        for control, keys in self.add_buttons:
            control.setEnabled(
                editable and any(not self.editors[key].text().strip() for key in keys)
            )
        self.panel.input_table.fit_rows(hide_empty_header=True)
        self.panel.output_table.fit_rows(hide_empty_header=True)

    def remove(self, key: str) -> None:
        if key not in self.editors or not self.editable():
            return
        # Fixed I/O is disabled; camera participation remains owned by Cameras.
        if key in self.panel.enable_controls:
            self.panel.enable_controls[key].setChecked(False)
        self.editors[key].clearFocus()
        self.editors[key].clear()
        self.panel.save_pins()
        self.panel.refresh_tests()
