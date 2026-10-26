"""Isolated Qt layout evidence; no runtime or device commands."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

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
load_terminal_font()
apply_theme(app)
composer = EpochComposer()
composer.setProperty("retroConsole", True)
composer.setProperty("retroPalette", "amber_phosphor")
composer.setStyleSheet(retro_stylesheet(PHOSPHOR_COLORS) + phosphor_stylesheet())
composer.set_screens(("Front", "Left", "Right", "Bottom"))
program = blank_program()
for face in composer.screens:
    program = add_stimulus(program, 0, "Texture", (face,))
epoch = program.sequence[0]
epoch = epoch.model_copy(
    update={
        "settings": [
            setting.model_copy(update={"linked_to": epoch.settings[-1].instance_id})
            if i < 3
            else setting
            for i, setting in enumerate(epoch.settings)
        ]
    }
)
program = program.model_copy(update={"sequence": [epoch]})
composer.program = program
composer.refresh_rows()
composer.resize(1400, 1050)
composer.show()
app.processEvents()
for face in composer.screens:
    row = composer.rows[face]
    for edit in row.parameters.asset_forms.values():
        edit.blockSignals(True)
        edit.setText("GaussianNoise_scale_15_primary_color_0.7.texture.json")
        edit.blockSignals(False)
bottom = composer.rows["Bottom"]
bottom.actions_button.setChecked(True)
for _ in range(3):
    app.processEvents()
composer.grab().save(str(Path(__file__).with_name("amber.png")))
composer.resize(520, 1500)
for _ in range(3):
    app.processEvents()
composer.grab().save(str(Path(__file__).with_name("narrow.png")))
composer.close()
