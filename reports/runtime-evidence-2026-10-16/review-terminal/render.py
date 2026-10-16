"""Offscreen appearance evidence; local fixtures, no controller/device commands."""
from dataclasses import replace
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from cephvr.gui.retro_instruments import blink
from cephvr.gui.review import ReviewDashboardWindow
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, review_view

app = QApplication([])
apply_theme(app)
window = ReviewDashboardWindow(sample=True)
window.appearance.select("retro_console")
window.apply_view(replace(review_view(Phase.READY), camera_status="Ready",
                          stimulus_status="Waiting", tracking_status="Failed",
                          trial_index=3, trial_count=8))
window.dashboard.log_console.clear()
window.appearance.update_status()
root = Path(__file__).parent
for width in (1440, 720):
    window.resize(width, 940)
    window.show()
    for _ in range(5):
        app.processEvents()
    blink().timer.stop()
    blink().on = True
    window.grab().save(str(root / f"retro-{width}.png"))
window.appearance.crt_action.setChecked(False)
app.processEvents()
window.grab().save(str(root / "crt-off-720.png"))
window.hide()
window.deleteLater()
app.processEvents()
