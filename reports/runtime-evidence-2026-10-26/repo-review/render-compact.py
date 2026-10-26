"""Capture the compact per-projector Stimulus preview in each operator theme."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QRect
from PyQt6.QtWidgets import QApplication

from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from cephvr.gui.stimulus_preview_area import StimulusPreviewArea
from cephvr.gui.theme import (
    RETRO_PALETTES,
    apply_theme,
    load_terminal_font,
    retro_stylesheet,
)
from cephvr.gui.view import PreviewView


OUT = Path(__file__).parent
STYLES = ("standard", "retro_console", "amber_phosphor")
SIZE = (700, 350)
PROJECTORS = ("Left", "Front", "Right", "Bottom")

app = QApplication([])
apply_theme(app)
load_terminal_font()

for style in STYLES:
    timeline = StimulusTimeline()
    area = StimulusPreviewArea(timeline)
    area.setProperty("retroConsole", style != "standard")
    area.setProperty("retroPalette", None if style == "standard" else style)
    if style != "standard":
        area.setStyleSheet(retro_stylesheet(RETRO_PALETTES[style][0]))
    area.set_projectors(PROJECTORS)
    program = blank_program()
    for face in PROJECTORS:
        program = add_stimulus(program, 0, "Sine grating", (face,))
    timeline.set_program(program, "", "Drift")
    timeline.set_advanced(True)
    timeline.set_elapsed(12)
    area.apply_view(PreviewView("stimulus", "Stimulus", visible=True), True)
    area.mode.setCurrentText("Per-projector")
    area.resize(*SIZE)
    area.show()
    for _ in range(4):
        app.processEvents()

    path = OUT / f"{style}-stimulus-preview-compact.png"
    if not area.grab().save(str(path)):
        raise RuntimeError(f"Could not save {path}")
    targets = []
    for name, frame in area.frames.items():
        card = timeline.projector_cards[name]
        rects = {
            "frame": QRect(frame.mapTo(area, QPoint()), frame.size()),
            "card": QRect(card.mapTo(area, QPoint()), card.size()),
            "metrics": QRect(frame.metrics.mapTo(area, QPoint()), frame.metrics.size()),
        }
        targets.append(
            f"{name}: frame={frame.width()}x{frame.height()}, "
            f"target={frame.target.width()}x{frame.target.height()}, "
            f"card={card.width()}x{card.height()}, "
            f"contained={all(area.rect().contains(rect) for rect in rects.values())}"
        )
    print(
        f"{path}: style={style}, area={area.width()}x{area.height()}, "
        f"native targets={'; '.join(targets)}"
    )
    area.close()
    timeline.close()
    area.deleteLater()
    timeline.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

print(
    f"Output directory: {OUT.resolve()}\n"
    f"Styles: {', '.join(STYLES)}\n"
    f"Requested area size: {SIZE[0]}x{SIZE[1]}. No runtime or device commands were issued."
)
