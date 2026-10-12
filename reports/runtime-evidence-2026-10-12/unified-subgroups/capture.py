"""Reproducible offscreen layout inspection; no device or backend commands."""
from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, Qt
from PyQt6.QtWidgets import QApplication

from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings('/tmp/unified-subgroup-capture.ini', QSettings.Format.IniFormat))
ReviewControls(window)
window.page_buttons[1].click()
editor = window.protocol.editor
editor.timeline.set_screens(('Left', 'Right'))
editor.timeline.choose(0, Qt.KeyboardModifier.NoModifier)
editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
form = editor.subgroup
form.composer.batch_label.setText('Optic flow')
form.repetitions.setText('60')
form.apply()
assert not form.notice.text(), form.notice.text()
editor.group_editor.repetitions.setText('300')
editor.group_editor.mark_changed()
assert editor.group_editor.apply()
window.show()
for width in (1280, 720):
    window.resize(width, 1100)
    for _ in range(6):
        app.processEvents()
    window.protocol.config_scroll.verticalScrollBar().setValue(0)
    app.processEvents()
    window.grab().save(str(Path(__file__).parent / f'overview-{width}.png'))
    window.protocol.config_scroll.ensureWidgetVisible(form.add_button)
    for _ in range(3):
        app.processEvents()
    window.grab().save(str(Path(__file__).parent / f'editor-{width}.png'))
    assert window.protocol.config_scroll.horizontalScrollBar().maximum() == 0
window.close()
window.deleteLater()
app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
print('Captured overview and unified form at 1280 and 720 pixels; no horizontal page overflow.')
