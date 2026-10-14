"""Render the Review appearance options without opening devices or saving drafts.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python reports/runtime-evidence-2026-10-15/retro-console/capture.py
PNG outputs are local-only evidence under the repository image ignore rule.
"""

import argparse
import json
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from cephvr.gui.review import ReviewControls, ReviewDashboardWindow
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, review_view


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    directory = parser.parse_args().output_dir
    directory.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    window = ReviewDashboardWindow(sample=True)
    ReviewControls(window, simulate_projectors=True)
    window.resize(1440, 940)
    window.show()
    images = {}
    for name, style in (
        ("standard", "standard"),
        ("retro-console", "retro_console"),
        ("returned-standard", "standard"),
    ):
        window.appearance.select(style, persist=False)
        for _ in range(8):
            app.processEvents()
        images[name] = window.grab().toImage()
        images[name].save(str(directory / f"{name}.png"))
    window.appearance.select("retro_console", persist=False)
    window.resize(720, 940)
    for _ in range(8):
        app.processEvents()
    window.grab().save(str(directory / "retro-narrow.png"))
    print(json.dumps({"standard_round_trip_pixels_equal": images["standard"] == images["returned-standard"]}))
    window.resize(1440, 940)
    window.activateWindow()
    window.dashboard.subject_id.setFocus()
    for _ in range(8):
        app.processEvents()
    window.grab().save(str(directory / "retro-focused.png"))
    window.apply_view(review_view(Phase.RUNNING))
    for _ in range(8):
        app.processEvents()
    window.grab().save(str(directory / "retro-trial.png"))
    window.tracking.annotation.close()
    window.hide()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


if __name__ == "__main__":
    main()
