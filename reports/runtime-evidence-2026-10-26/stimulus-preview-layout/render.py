"""Offscreen themed footprints and planned plots; no renderer/device connection."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from cephvr.gui.previews import PreviewWorkspace
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from cephvr.gui.theme import (
    COLORS, RETRO_PALETTES, apply_theme, load_terminal_font,
    phosphor_stylesheet, retro_stylesheet,
)
from cephvr.gui.view import PreviewView

app = QApplication([])
load_terminal_font()
apply_theme(app)
for style in ("standard", "retro_console", "amber_phosphor"):
    workspace = PreviewWorkspace(None)
    colors = RETRO_PALETTES[style][0] if style != "standard" else COLORS
    workspace.setProperty("retroConsole", style != "standard")
    workspace.setProperty("retroPalette", style)
    sheet = retro_stylesheet(colors) if style != "standard" else ""
    if style == "amber_phosphor":
        sheet += phosphor_stylesheet()
    workspace.setStyleSheet(
        sheet + f"QWidget#PreviewWorkspace {{background: {colors.window};}}"
    )
    faces = ("Left", "Front", "Right", "Bottom")
    program = blank_program()
    for face in faces:
        program = add_stimulus(program, 0, "Sine grating", (face,))
    workspace.stimulus_area.set_projectors(faces)
    workspace.timeline.set_program(program, "", "Layout review")
    workspace.advanced_toggle.setChecked(True)
    workspace.apply_views(
        (PreviewView("stimulus", "Stimulus", active=True, reason="Available after Setup"),),
        allowed=True,
    )
    workspace.controls["stimulus"].click()
    workspace.show()
    for mode, width, height in (
        ("Combined", 1600, 900),
        ("Combined", 900, 700),
        ("Per-projector", 1600, 900),
    ):
        workspace.resize(width, height)
        workspace.stimulus_area.mode.setCurrentText(mode)
        for _ in range(5):
            app.processEvents()
        path = Path(__file__).with_name(f"{style}-{mode}-{width}.png")
        assert workspace.grab().save(str(path))
        print(path.name, workspace.size().width(), workspace.size().height())
    workspace.close()
    workspace.deleteLater()
    app.processEvents()
