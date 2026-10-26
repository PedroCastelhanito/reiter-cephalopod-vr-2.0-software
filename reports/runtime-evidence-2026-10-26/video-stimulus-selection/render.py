"""Inspect configured camera/projection footprints without runtime connections."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from cephvr.gui.theme import apply_theme
from cephvr.gui.protocol_document import TrialDraft, blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from cephvr.gui.view import DashboardView, Phase, PreviewView
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True)
window.appearance.select("amber_phosphor", persist=False)
window.resize(1920, 1032)
camera = window.devices.cameras.drafts[0]
program = blank_program()
for face in ("Left", "Front", "Right", "Bottom"):
    program = add_stimulus(program, 0, "Sine grating", (face,))
window.protocol.editor.drafts = [TrialDraft("Motion", program)]
window.recordings.install_values({camera.key: True})
views = (
    PreviewView(camera.key, camera.role, active=True, reason="Available after Setup"),
    PreviewView("stimulus", "Visual stimulus", active=True, reason="Available after Setup"),
)
window.apply_view(
    DashboardView(
        phase=Phase.CONFIGURATION, connected=True, has_control=True, previews=views
    )
)
window.show()
window.dashboard.set_runtime_layout(True)
workspace = window.dashboard.preview_workspace
workspace.advanced_toggle.setChecked(True)
workspace.stimulus_area.set_projectors(("Left", "Front", "Right", "Bottom"))
workspace.stimulus_area.mode.setCurrentText("Per-projector")
for selected in (True, False):
    workspace.controls["stimulus"].click()
    app.processEvents()
    app.processEvents()
    assert workspace.preview_host.isVisible()
    assert tuple(window.preview_slot.frames) == (camera.key,)
    assert all(
        frame.isVisibleTo(workspace) == selected
        for frame in workspace.stimulus_area.frames.values()
    )
    path = Path(__file__).with_name("projection-on.png" if selected else "projection-off.png")
    assert window.grab().save(str(path))
    print("Projection", selected, "camera frames", tuple(window.preview_slot.frames))
window.close()
