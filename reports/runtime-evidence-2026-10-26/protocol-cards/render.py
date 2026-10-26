"""Offscreen visual evidence; does not connect to the running application."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from cephvr.gui.epoch_composer import EpochComposer
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from cephvr.gui.theme import (
    PHOSPHOR_COLORS,
    apply_theme,
    load_terminal_font,
    phosphor_stylesheet,
    retro_stylesheet,
)

app = QApplication([])
apply_theme(app)
load_terminal_font()
composer = EpochComposer()
composer.setObjectName("Page")
composer.setProperty("retroConsole", True)
composer.setProperty("retroPalette", "amber_phosphor")
composer.setStyleSheet(retro_stylesheet(PHOSPHOR_COLORS) + phosphor_stylesheet())
composer.set_screens(("Front", "Left", "Right", "Bottom"))
program = blank_program()
for face, kind in zip(composer.screens, ("Image", "Texture", "Video", "Looming image"), strict=True):
    program = add_stimulus(program, 0, kind, (face,))
composer.program = program
composer.refresh_rows()
composer.show()
for width in (1400, 780, 520):
    composer.resize(width, 1)
    app.processEvents()
    composer.rows["Left"].stimulus.setFocus()
    app.processEvents()
    assert composer.grab().save(str(Path(__file__).with_name(f"amber-{width}.png")))
composer.close()
composer.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
print("Rendered three Amber layouts; widgets released.")
