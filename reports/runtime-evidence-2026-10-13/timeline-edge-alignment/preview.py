"""Isolated interactive presentation preview; no controller or device connection."""
import sys
import tempfile
from pathlib import Path
from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
from cephvr.gui.protocol_document import review_program
from cephvr.gui.protocol_batches import grouped_program
app = QApplication([])
apply_theme(app)
settings_dir = tempfile.TemporaryDirectory(prefix='cephvr-timeline-review-')
settings = QSettings(str(Path(settings_dir.name) / 'preview.ini'), QSettings.Format.IniFormat)
window = DashboardWindow(sample=True, settings=settings)
controls = ReviewControls(window, simulate_projectors=True)
editor = window.protocol.editor
window.page_buttons[1].click()
window.resize(1320, 1000)
window.show()
window.raise_()
window.activateWindow()
def ready():
    app.processEvents()
    editor.set_program(grouped_program(review_program()))
    editor.group_editor.name.setText('Adaptation')
    editor.group_editor.repetitions.setText('50')
    editor.group_editor.apply()
    for name in ('Stimulus', 'Rest'):
        editor.add_group()
        editor.group_editor.name.setText(name)
        editor.group_editor.apply()
    editor.select_epochs(((0, 0),))
    app.processEvents()
    for timeline in (editor.timeline, editor.hierarchy.contents):
        assert abs(timeline.block_actions.add.geometry().right() + 1 - timeline.width()) <= 1
    assert editor.hierarchy.contents.width() == editor.subgroup.composer.width()
    print('GEOMETRY_OK both add buttons flush right; sequence and composer widths match', flush=True)
    window.grab().save(str(Path(__file__).with_name('dashboard.png')))
    editor.timeline_card.grab().save(str(Path(__file__).with_name('timeline.png')))
    print(f'PREVIEW_READY visible={window.isVisible()} card_height={editor.timeline_card.height()}', flush=True)
    if '--live' not in sys.argv:
        app.quit()
QTimer.singleShot(300, ready)
app.exec()
