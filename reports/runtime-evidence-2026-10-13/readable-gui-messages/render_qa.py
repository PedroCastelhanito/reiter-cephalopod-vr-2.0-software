"""Local offscreen GUI presentation evidence; no controller/device connection.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python reports/runtime-evidence-2026-10-13/readable-gui-messages/render_qa.py
"""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QPushButton, QVBoxLayout, QWidget

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.components import LogConsole
from cephvr.gui.main import ManagedGui
from cephvr.gui.managed_prompts import ManagedPrompts
from cephvr.gui.theme import apply_theme


def main() -> None:
    app = QApplication([])
    apply_theme(app)
    output = Path(__file__).parent
    parent = QWidget()
    parent.resize(900, 680)
    state = pb.Snapshot(controller_generation=str(uuid4()), retained_truncated=True)
    state.errors.add(
        error_id=str(uuid4()),
        failure=pb.Failure(message="<unknown> renderer cleanup remains unconfirmed"),
    )
    state.warnings.add(warning_id=str(uuid4()), message="Review output recovery before continuing.")
    prompt = state.prompts.add(prompt_id=str(uuid4()), explanation="Camera recording requires a decision.")
    prompt.permitted_choices.extend(["Continue session", "Abort session"])
    for name in ("SaveConfigurationHistory", "ExecuteCameraCommand"):
        state.operations.add(command=name, complete=True, succeeded=True).context.command_id = str(uuid4())
    prompts = ManagedPrompts(parent, queue_response=lambda *_: False, acknowledged=lambda *_: None, log=lambda *_: None)
    prompts.update(state, require_acknowledgement=True, can_respond=False, connection_epoch=1)
    app.processEvents()
    dialog = prompts.retained_dialog
    assert dialog is not None
    assert dialog.grab().save(str(output / "retained-collapsed.png"))
    details = next(button for button in dialog.findChildren(QPushButton) if "details" in button.text().lower())
    details.click()
    app.processEvents()
    assert dialog.grab().save(str(output / "retained-expanded.png"))
    dialog.reject()
    panel = QWidget()
    panel.setObjectName("Shell")
    layout = QVBoxLayout(panel)
    console = LogConsole(lines=7)
    layout.addWidget(console)
    manager = SimpleNamespace(window=SimpleNamespace(dashboard=SimpleNamespace(log_console=console)), prompts=SimpleNamespace(operation_finished=lambda *_: None))
    command = str(uuid4())
    ManagedGui.command_admitted(manager, "Setup", command)
    ManagedGui.operation_finished(manager, "Setup", command, "completed", "Completed.")
    ManagedGui.operation_finished(manager, "open_display_calibration", str(uuid4()), "failed", "<unknown> renderer failure\nCleanup remains unconfirmed.")
    console.append_entry("MCU command: Completed", "Action: mcu\nMessage: Completed")
    panel.resize(760, 310)
    panel.show()
    app.processEvents()
    assert panel.grab().save(str(output / "activity-log.png"))
    original_menu_exec, original_dialog_exec = QMenu.exec, QDialog.exec

    def select_details(menu, *_args):
        return next(action for action in menu.actions() if action.text() == "View details")

    def capture_details(detail_dialog):
        detail_dialog.show()
        app.processEvents()
        assert detail_dialog.grab().save(str(output / "activity-log-details.png"))
        detail_dialog.hide()
        return 0

    try:
        QMenu.exec, QDialog.exec = select_details, capture_details
        console.setTextCursor(console.document().find("Open display calibration"))
        console.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(), QPoint()))
    finally:
        QMenu.exec, QDialog.exec = original_menu_exec, original_dialog_exec
    panel.close()
    parent.close()


if __name__ == "__main__":
    main()
