"""Isolated screen-dimension card capture, without runtime/device commands."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

from cephvr.gui.projector_geometry import FACES, ScreenGeometryEditor
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
editor = ScreenGeometryEditor()
editor.setProperty("retroConsole", True)
editor.setProperty("retroPalette", "amber_phosphor")
editor.setStyleSheet(retro_stylesheet(PHOSPHOR_COLORS) + phosphor_stylesheet())
for face, values in zip(
    FACES, ((94, 85, 192), (126, 85, 192), (126, 85, 192), (126, 94, 115.2)), strict=True
):
    for key, value in zip(("width", "height", "distance"), values, strict=True):
        editor.fields[face, key].setText(str(value))
editor.show()
for width in (620, 420):
    editor.resize(width, editor.sizeHint().height())
    editor.fields["Left", "width"].setFocus()
    app.processEvents()
    editor.grab().save(str(Path(__file__).with_name(f"screen-dimensions-{width}.png")))
editor.close()
