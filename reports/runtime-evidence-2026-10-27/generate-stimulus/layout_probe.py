"""Bounded native layout probe; no devices or runtime services."""
import json
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QSettings
from cephvr.gui.window import DashboardWindow
from cephvr.gui.theme import apply_theme, RETRO_PALETTES, retro_stylesheet, phosphor_stylesheet
from cephvr.generate_stimulus.window import AuthoringWindow

app = QApplication([])
apply_theme(app)
root = Path(__file__).parent
if os.environ.get("QT_SCALE_FACTOR"):
    root = root / "layout-scaled"
    root.mkdir(exist_ok=True)
window = DashboardWindow(sample=True, settings=QSettings(str(root / "layout-probe.ini"), QSettings.Format.IniFormat))
window.resize(1440, 960)
window.show()
window.open_stimulus_authoring()
editor = window.authoring_page.editor
standalone = AuthoringWindow(root)
checks = {}
def amber():
    window.appearance.select("amber_phosphor", persist=False)
    QTimer.singleShot(500, standard)
def standard():
    window.grab().save(str(root / "layout-embedded-amber.png"))
    checks["sidebar_width"] = window.page_buttons[-1].parentWidget().width()
    window.appearance.select("standard", persist=False)
    editor.tabs.setCurrentIndex(1)
    QTimer.singleShot(700, narrow)
def narrow():
    window.grab().save(str(root / "layout-embedded-standard.png"))
    checks["viewport_error"] = editor.viewport.error
    standalone.resize(720, 700)
    standalone.show()
    QTimer.singleShot(700, standalone_amber)
def standalone_amber():
    standalone.grab().save(str(root / "layout-standalone-narrow.png"))
    checks["narrow_mode"] = standalone.columns.mode
    checks["preview_size"] = [standalone.image.width(), standalone.image.height()]
    colors = RETRO_PALETTES["amber_phosphor"][0]
    standalone.setProperty("retroConsole", True)
    standalone.setProperty("retroPalette", "amber_phosphor")
    standalone.setStyleSheet(retro_stylesheet(colors) + phosphor_stylesheet(colors))
    standalone.resize(1280, 850)
    QTimer.singleShot(500, finish)
def finish():
    standalone.grab().save(str(root / "layout-standalone-amber.png"))
    (root / "layout-check.json").write_text(json.dumps(checks, indent=2))
    print(checks)
    standalone.close()
    window.close()
    app.quit()
QTimer.singleShot(1000, amber)
app.exec()
