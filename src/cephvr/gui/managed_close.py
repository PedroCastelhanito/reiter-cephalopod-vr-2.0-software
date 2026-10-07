"""Explicit operator choices for managed GUI close failures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from PyQt6.QtWidgets import QMessageBox, QWidget

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_configuration import ManagedConfiguration
from cephvr.gui.managed_configuration_transport import configuration_update_plan

SaveFailureChoice = Literal["retry", "discard"] | None


@dataclass(frozen=True)
class CloseRequestResult:
    """One explicit close decision; UI owns the resulting dialog or wait state."""

    kind: Literal["pending", "cancelled", "failed"]
    message: str = ""


def request_managed_close(
    state: pb.Snapshot | None,
    configuration: ManagedConfiguration,
    *,
    send: Callable[..., bool],
    confirm_discard: Callable[[], bool],
    log: Callable[[str], None],
) -> CloseRequestResult:
    """Prepare one history save while keeping phase and draft ownership explicit."""
    if state is None:
        return CloseRequestResult("failed", "Controller connection is unavailable.")
    if state.session.phase not in (
        pb.SESSION_PHASE_CONFIGURATION,
        pb.SESSION_PHASE_READY,
    ):
        if (configuration.dirty or configuration.stale) and not confirm_discard():
            return CloseRequestResult("cancelled")
        if not send("save_configuration_history"):
            return CloseRequestResult("failed", "Controller connection is unavailable.")
        return CloseRequestResult("pending")
    if configuration.stale:
        if not confirm_discard():
            return CloseRequestResult("cancelled")
        if not send("save_configuration_history"):
            return CloseRequestResult("failed", "Controller connection is unavailable.")
        return CloseRequestResult("pending")
    try:
        proposal = configuration.collect(state.configuration_values.current)
    except (ValueError, TypeError, AttributeError) as error:
        return CloseRequestResult("failed", str(error))
    plan = configuration_update_plan(
        proposal,
        state.configuration_values.current,
        state.session.phase,
        "save_configuration_history",
    )
    if plan != "submit":
        if plan == "preserve":
            log(
                "Closing with unsent local edits; controller history will contain "
                "only its last accepted configuration."
            )
        if not send("save_configuration_history"):
            return CloseRequestResult("failed", "Controller connection is unavailable.")
        return CloseRequestResult("pending")
    if not send(
        "submit_configuration",
        base_revision=configuration.revision,
        proposal=proposal.SerializeToString(deterministic=True),
        edit_serial=configuration.edit_serial,
        after_action="save_configuration_history",
    ):
        return CloseRequestResult("failed", "Controller connection is unavailable.")
    return CloseRequestResult("pending")


def save_failure_choice(parent: QWidget, reason: str) -> SaveFailureChoice:
    """Return only a button the operator explicitly selected; dismissal is inert."""
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle("Configuration not saved")
    dialog.setText("The last configuration could not be saved.")
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
