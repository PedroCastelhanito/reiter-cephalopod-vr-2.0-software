"""Offscreen draft-only preview; never creates a runtime/device connection."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from cephvr.gui.previews import PreviewWorkspace
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from cephvr.gui.theme import (
    PHOSPHOR_COLORS,
    apply_theme,
    load_terminal_font,
    phosphor_stylesheet,
    retro_stylesheet,
)
from cephvr.gui.view import PreviewView

app = QApplication([])
load_terminal_font()
apply_theme(app)
workspace = PreviewWorkspace(None)
workspace.setProperty("retroConsole", True)
workspace.setProperty("retroPalette", "amber_phosphor")
workspace.setStyleSheet(
    retro_stylesheet(PHOSPHOR_COLORS)
    + phosphor_stylesheet()
    + f"QWidget#PreviewWorkspace {{ background: {PHOSPHOR_COLORS.window}; }}"
)
workspace.resize(1600, 900)
faces = ("Left", "Front", "Right", "Bottom")
program = blank_program()
for face in faces:
    program = add_stimulus(program, 0, "Sine grating", (face,))
workspace.stimulus_area.set_projectors(faces)
workspace.timeline.set_program(program, "", "Draft")
workspace.advanced_toggle.setChecked(True)
workspace.apply_views(
    (
        PreviewView(
            "stimulus", "Stimulus", active=True, reason="Available after Setup"
        ),
    ),
    allowed=False,
)
workspace.show()
for mode in ("Combined", "Per-projector"):
    workspace.stimulus_area.mode.setCurrentText(mode)
    app.processEvents()
    app.processEvents()
    assert workspace.timeline.elapsed is None
    assert workspace.timeline.active_sources == set(faces)
    output = Path(__file__).with_name(mode.lower() + ".png")
    assert workspace.grab().save(str(output))
    print(mode, "elapsed", workspace.timeline.elapsed, "sources", faces)
workspace.close()
