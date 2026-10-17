"""Open the saved local Review and retain bounded native startup evidence."""

import json
from pathlib import Path

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication

from cephvr.gui.layouts import show_maximized
from cephvr.gui.review import ReviewControls, ReviewDashboardWindow
from cephvr.gui.review_draft import draft_path, load_review_draft
from cephvr.gui.theme import apply_theme

app = QApplication([])
app.setApplicationName("CephVR2.0 Dashboard")
apply_theme(app)
window = ReviewDashboardWindow(sample=True, settings=QSettings("CephVR", "Frontend"))
controls = ReviewControls(window, simulate_projectors=True, fake_previews=True)
load_review_draft(window, draft_path())
window.appearance.select("retro_console", persist=False)
show_maximized(window)
window.raise_()
window.activateWindow()


def retain_startup():
    result = {
        "date": "2026-10-17",
        "source_revision": "uncommitted working tree",
        "method": "native macOS Qt, saved local review draft, Retro, synthetic previews",
        "maximized": window.isMaximized(),
        "frame": window.frameGeometry().getRect(),
        "available": window.screen().availableGeometry().getRect(),
        "scope": "startup state and native frame bounds; no real devices or Windows acceptance",
    }
    Path(__file__).with_name("retro-startup-native.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result), flush=True)


QTimer.singleShot(500, retain_startup)
app.exec()
