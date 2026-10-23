"""Offscreen QA fixtures; no native viewer, device, experiment or saved settings."""

import json
from pathlib import Path

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from cephvr.gui.stimulus_preview_area import StimulusPreviewArea
from cephvr.gui.theme import (
    PHOSPHOR_COLORS, RETRO_FONT, RETRO_SIZES, apply_theme, load_terminal_font, stylesheet,
)
from cephvr.visual_stimulus.config.models.program_model import Hold

app = QApplication([])
load_terminal_font()
apply_theme(app)
app.setFont(QFont("IBM Plex Mono", 10))
app.setStyleSheet(stylesheet(PHOSPHOR_COLORS, RETRO_SIZES, RETRO_FONT))
program = blank_program()
for face in ("Front", "Left", "Right", "Bottom"):
    program = add_stimulus(program, 0, "Sine grating", (face,))
epoch = program.sequence[0]
settings = list(epoch.settings)
bottom = settings[-1]
hold = Hold(kind="hold")
settings[-1] = bottom.model_copy(update={"phase_x": hold, "phase_y": hold,
    "motion": bottom.motion.model_copy(update={"x": hold, "y": hold, "rotation": hold})})
program = program.model_copy(update={"category": "texture_drift",
    "sequence": (epoch.model_copy(update={"settings": tuple(settings)}),)})
timeline = StimulusTimeline()
area = StimulusPreviewArea(timeline)
area.setObjectName("Shell")
area.setProperty("retroConsole", True)
area.setProperty("retroPalette", "amber_phosphor")
area.set_projectors(("Front", "Left", "Right", "Bottom"))
timeline.set_program(program, "", "QA: static Bottom")
timeline.set_advanced(True)
timeline.set_playback(.5, running=False)
destination = Path(__file__).parent
results = {}
for name, mode, height in (("combined", "Combined", 500),
                           ("per-projector", "Per-projector", 560),
                           ("per-projector-compact", "Per-projector", 430)):
    area.mode.setCurrentText(mode)
    area.resize(1500, height)
    area.show()
    for _ in range(3):
        app.processEvents()
    assert area.grab().save(str(destination / f"{name}.png"))
    results[name] = {
        "area": [area.width(), area.height()],
        "targets": {face: [frame.target.width(), frame.target.height()]
                    for face, frame in area.frames.items()},
        "visible_instruments": [face for face, card in timeline.projector_cards.items()
                                if not card.isHidden()],
        "shared_samples": [[sample.name, sample.color] for dial in timeline.shared_dials.values()
                           for sample in dial.samples],
    }
(destination / "layout-measurements.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
area.close()
area.deleteLater()
app.processEvents()
