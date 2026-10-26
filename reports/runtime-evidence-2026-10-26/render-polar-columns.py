from pathlib import Path
from PyQt6.QtWidgets import QApplication
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.stimulus_preview_area import StimulusPreviewArea
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
from PyQt6.QtGui import QFont, QFontDatabase
from cephvr.gui.theme import RETRO_PALETTES, retro_stylesheet
app=QApplication([])
font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/consola.ttf')
app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0],10))
t=StimulusTimeline();a=StimulusPreviewArea(t)
a.setProperty('retroConsole', True);a.setProperty('retroPalette','retro_console');a.setStyleSheet(retro_stylesheet(RETRO_PALETTES['retro_console'][0]))
a.set_projectors(('Left','Front','Right','Bottom'));p=blank_program()
for face in ('Left','Front','Right','Bottom'): p=add_stimulus(p,0,'Sine grating',(face,))
t.set_program(p,'','Drift');t.set_advanced(True);t.set_elapsed(12);a.mode.setCurrentText('Per-projector');a.resize(1100,430);a.show()
for _ in range(3): app.processEvents()
e=Path('reports/runtime-evidence-2026-10-26/polar-column-heading');e.mkdir(exist_ok=True);a.grab().save(str(e/'columns.png'));a.close();t.close()
