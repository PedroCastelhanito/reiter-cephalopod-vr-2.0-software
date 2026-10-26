"""Offscreen plot typography and pretrial state; no backend/device connections."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QEvent
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
from cephvr.visual_stimulus.config.models.program_model import Constant, Rate

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
epoch = program.sequence[0]
settings = list(epoch.settings)
settings[-1] = settings[-1].model_copy(
    update={"motion": settings[-1].motion.model_copy(
        update={"rotation": Rate(kind="rate", function=Constant(kind="constant", value=-10))}
    )}
)
program = program.model_copy(update={"sequence": (epoch.model_copy(update={"settings": tuple(settings)}),)})
workspace.timeline.set_program(program, "", "Draft")
workspace.stimulus_area.set_projectors(faces)
workspace.advanced_toggle.setChecked(True)
for control in workspace.projector_controls.values():
    control.setChecked(True)
workspace.apply_views(
    (PreviewView("stimulus", "Visual stimulus", active=True, reason="Available after Setup"),),
    allowed=True,
)
workspace.controls["stimulus"].click()
workspace.show()
for running in (False, True):
    workspace.timeline.set_playback(0 if running else None, running=running)
    app.processEvents()
    app.processEvents()
    samples = workspace.timeline.dial_samples
    assert samples
    assert any(sample.vector for sample in samples) == running
    path = Path(__file__).with_name("running.png" if running else "ready.png")
    assert workspace.grab().save(str(path))
workspace.stimulus_area.mode.setCurrentText("Per-projector")
app.processEvents()
app.processEvents()
assert workspace.grab().save(str(Path(__file__).with_name("per-projector.png")))
workspace.close()
workspace.timeline.timer.stop()
workspace.deleteLater()
app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
