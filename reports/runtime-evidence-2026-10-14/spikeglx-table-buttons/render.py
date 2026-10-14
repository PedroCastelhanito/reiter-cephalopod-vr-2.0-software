import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from cephvr.gui.spikeglx import SpikeGLXPanel
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import review_view, Phase
app = QApplication([])
assert QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf') >= 0
apply_theme(app)
panel = SpikeGLXPanel()
panel.apply_view(review_view(Phase.CONFIGURATION))
for name in ('Eye cam', 'Photodiode'):
    panel.add_custom()
    panel.rows[f'custom:custom-{panel.custom_count}'][0].setText(name)
panel.resize(1220, 720)
panel.show()
app.processEvents()
out = Path(__file__).parent
assert panel.grab().save(str(out / 'panel.png'))
buttons = []
for key, control in panel.remove_buttons.items():
    host = panel.table.cellWidget(panel.row_keys.index(key), 6)
    assert control.width() == 26 and control.height() == 26
    assert host.rect().contains(control.geometry())
    assert control.text() == chr(215)
    buttons.append({'key': key, 'button_size': [control.width(), control.height()], 'cell_size': [host.width(), host.height()], 'text': control.text()})
first = next(iter(panel.remove_buttons))
panel.remove_buttons[first].click()
assert first not in panel.rows
panel.apply_view(review_view(Phase.CONFIGURATION, observer=True))
assert not next(iter(panel.remove_buttons.values())).isEnabled()
(out / 'context.json').write_text(json.dumps({'date_jst': '2026-10-14', 'source_revision': 'ffa3edefec43d1d167ab0f6a07434443776cbf71', 'working_tree': 'dirty; existing changes preserved', 'method': 'isolated themed Qt offscreen panel at1220x720; fit/containment, multiplication-sign glyph, deletion and observer probes', 'buttons': buttons, 'initial_render': 'automatic offscreen font discovery rendered boxes both restricted and permitted; explicit Segoe UI application-font load fixes rendering', 'scope': 'appearance/local draft deletion only; no native restart/controller/device commands'}, indent=2) + '\n')
print(json.dumps(buttons))
panel.close()
