from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
app=QApplication([]);apply_theme(app)
w=DashboardWindow(sample=False,settings=QSettings('/tmp/direct-group-layout.ini',QSettings.Format.IniFormat));ReviewControls(w)
w.page_buttons[1].click();e=w.protocol.editor;e.timeline.set_screens(('Left','Right'))
root=Path(__file__).resolve().parents[3]/'demo_assets'
w.protocol.assets.folders['root'].editor.setText(str(root))
e.group_editor.name.setText('Image and gray');e.group_editor.repetitions.setText('10000');e.group_editor.mark_changed();assert e.group_editor.apply()
f=e.subgroup
for face in ('Left','Right'): f.composer.add_file('Image',str(root/'images/05_circle.png'),face)
f.composer.duration.setText('00:00:01');f.composer.batch_label.setText('Image');f.apply();assert not f.notice.text(),f.notice.text()
e.add_subgroup()
for face in ('Left','Right'):
 p=f.composer.rows[face].parameters;p.set_media_path(next(iter(p.asset_forms)),str(root/'images/01_gray_50.png'))
f.composer.batch_label.setText('Gray');f.apply();assert not f.notice.text(),f.notice.text()
e.select_epochs(((0,0),))
f.add_rule.click()
r=f.rows[0];r.target.setCurrentIndex(r.target.findText('All projectors'));r.method.setCurrentText('Random')
r.random_fields['maximum'].setText('1000');f.apply();assert not f.notice.text(),f.notice.text()
assert f.rows and bool(e.program.sequence[0].body[0].repetition_rules)
e.add_trial();e.add_trial();e.trials.setCurrentRow(0)
w.show()
for width in (1280,720):
 w.resize(width,1100)
 for _ in range(5):app.processEvents()
 w.protocol.config_scroll.verticalScrollBar().setValue(0);app.processEvents()
 w.grab().save(str(Path(__file__).parent/f'overview-{width}.png'))
 QTest.qWait(250)
 w.protocol.config_scroll.verticalScrollBar().setValue(w.protocol.config_scroll.verticalScrollBar().maximum());QTest.qWait(100)
 print(width, w.protocol.config_scroll.verticalScrollBar().maximum(), w.protocol.config_scroll.verticalScrollBar().value())
 w.grab().save(str(Path(__file__).parent/f'editor-{width}.png'))
 assert w.protocol.config_scroll.horizontalScrollBar().maximum()==0
w.close();w.deleteLater();app.processEvents();print('Captured direct group editor with image/gray ×10000 and configured test assets.')
