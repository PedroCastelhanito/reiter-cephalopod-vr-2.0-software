"""Owner-requested running Dashboard presentation; local fixtures only."""

import argparse
from dataclasses import replace
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.retro_instruments import blink
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase
from cephvr.gui.window import DashboardWindow

parser = argparse.ArgumentParser()
parser.add_argument("--interactive", action="store_true")
args = parser.parse_args()
app = QApplication([])
apply_theme(app)
# Base shell avoids overwriting the user's saved Review draft on closure.
window = DashboardWindow(sample=True, device_review=True)
window.setWindowTitle("CephVR 2.0 · SIMULATED ongoing experiment · design review")
appearance = ReviewAppearance(window, window.dashboard, window.page_header, None)
appearance.select("retro_console")
controls = ReviewControls(window)
dashboard = window.dashboard
dashboard.age.setText("90")
dashboard.subject_size.setText("42")
dashboard.sex.setCurrentText("Female")
dashboard.output_root.setText("D:/CephVR/REVIEW/CEPH-007/session-001")
controls.set_phase(Phase.RUNNING)
window.apply_view(replace(dashboard.view, reservation_status="Held (sample)",
                          output_status="Open (sample)", metadata_status="Synced (sample)"))
dashboard.log_console.setPlainText("\n".join([
    "LOCAL REVIEW · SIMULATED experiment; no controller connection.",
    "00:00  Setup complete · cameras, stimulus and tracking ready.",
    "00:00  Session started · six planned trials; outputs reserved.",
    "00:00  Trial 1/6 started · Baseline / Optic flow.",
    "02:30  Trial 1/6 completed · outputs closed; metadata synced.",
    "02:30  Trial 2/6 started · camera and stimulus outputs open.",
    "03:18  Trial 2/6 running · 00:48 elapsed in current trial.",
]))
assert dashboard.view.phase == Phase.RUNNING
assert not dashboard.command_buttons["Setup"].isEnabled()
assert not dashboard.command_buttons["Start"].isEnabled()
assert dashboard.command_buttons["Stop"].isEnabled()
assert not dashboard.subject_id.isEnabled()
assert dashboard.trial_position.index == 2 and dashboard.trial_position.count == 6
assert not dashboard.view.connected and dashboard.view.sample
root = Path(__file__).parent
if not args.interactive:
    for width in (1440, 720):
        window.resize(width, 940)
        window.show()
        for _ in range(5):
            app.processEvents()
        if not args.interactive:
            blink().timer.stop()
            blink().on = True
        window.grab().save(str(root / f"running-{width}.png"))
window.resize(1440, 940)
if args.interactive:
    window.show()
    window.raise_()
    window.activateWindow()
    app.exec()
else:
    window.hide()
    window.deleteLater()
    app.processEvents()
print("Running fixture gates, contents and renders verified; no controller commands.")
