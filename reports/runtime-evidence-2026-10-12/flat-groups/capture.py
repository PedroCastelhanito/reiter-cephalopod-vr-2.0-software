from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent, QSettings
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
app=QApplication([])
apply_theme(app)
w=DashboardWindow(sample=True, settings=QSettings("/tmp/flat-group-capture.ini", QSettings.Format.IniFormat))
ReviewControls(w)
w.page_buttons[1].click()
e=w.protocol.editor
e.timeline.choose(0, Qt.KeyboardModifier.NoModifier)
e.create_batch.composer.duration.setText("00:00:02")
e.create_batch.repetitions.setText("3")
e.create_batch.composer.batch_label.setText("Images")
e.create_batch.generate()
e.create_batch.composer.batch_label.setText("Uniform")
e.create_batch.generate()
e.hierarchy.batch_picker.activated.emit(1)
w.show()
for width in (1280,720):
 w.resize(width,1100)
 for _ in range(6):app.processEvents()
 w.grab().save(str(Path(__file__).parent/f"edit-{width}.png"))
 e.modes.setCurrentIndex(0)
 for _ in range(5):app.processEvents()
 w.protocol.config_scroll.ensureWidgetVisible(e.create_batch.generation_controls)
 for _ in range(3):app.processEvents()
 w.grab().save(str(Path(__file__).parent/f"generate-{width}.png"))
 e.hierarchy.batch_picker.activated.emit(1)
w.close()
w.deleteLater()
app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
print("Captured edit and generation at both widths")
