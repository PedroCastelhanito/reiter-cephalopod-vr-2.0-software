"""Offscreen production-dialog QA; no controller or device connection.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python reports/runtime-evidence-2026-10-13/readable-gui-messages/dialog-compact/render_qa.py
"""
from pathlib import Path
from uuid import uuid4

from PyQt6.QtWidgets import QApplication, QWidget

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_prompts import ManagedPrompts
from cephvr.gui.theme import apply_theme


def main():
    app = QApplication([])
    apply_theme(app)
    directory = Path(__file__).parent
    parent = QWidget()
    state = pb.Snapshot(controller_generation=str(uuid4()), retained_truncated=True)
    state.errors.add(error_id=str(uuid4()), failure=pb.Failure(message="<unknown> renderer cleanup remains unconfirmed\n<b>payload</b> & quoted text remain literal."))
    state.warnings.add(warning_id=str(uuid4()), message="Review output recovery before continuing.")
    prompt = state.prompts.add(prompt_id=str(uuid4()), explanation="Camera recording requires a decision.")
    prompt.permitted_choices.extend(["Continue session", "Abort session"])
    for name in ("SaveConfigurationHistory", "ExecuteCameraCommand"):
        state.operations.add(command=name, complete=True, succeeded=True).context.command_id = str(uuid4())
    acknowledgements = []
    prompts = ManagedPrompts(parent, queue_response=lambda *_: False, acknowledged=lambda *identity: acknowledgements.append(identity), log=lambda *_: None)
    prompts.update(state, require_acknowledgement=True, can_respond=False, connection_epoch=1)
    app.processEvents()
    dialog = prompts.retained_dialog
    assert dialog is not None
    assert not hasattr(dialog, "details") and not hasattr(dialog, "details_toggle")
    assert dialog.grab().save(str(directory / "collapsed.png"))
    state.errors.add(error_id="latest-error", failure=pb.Failure(message="Latest exact failure\n<markup> remains literal"))
    for i in range(50):
        state.operations.add(command="Setup", complete=True, succeeded=True).context.command_id = f"routine-{i}"
    for i in range(45):
        state.warnings.add(warning_id=f"warning-{i}", message=f"Retained diagnostic warning {i}; full message preserved.")
    prompts.update(state, require_acknowledgement=True, can_respond=False, connection_epoch=1)
    app.processEvents()
    dialog.copy_button.click()
    copied = app.clipboard().text()
    assert "latest-error" in copied and "routine-49" in copied and "warning-44" in copied
    assert "<markup> remains literal" in copied and not acknowledgements
    (directory / "copied-details.txt").write_text(copied)
    assert dialog.grab().save(str(directory / "long-report.png"))
    assert dialog.copy_button.isVisible() and dialog.continue_button.isVisible()
    assert dialog.summary_scroll.verticalScrollBar().maximum() > 0
    dialog.reject()
    assert not acknowledgements
    parent.close()


if __name__ == "__main__":
    main()
