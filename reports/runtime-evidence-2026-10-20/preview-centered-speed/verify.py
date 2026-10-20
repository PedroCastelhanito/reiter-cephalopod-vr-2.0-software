"""Offscreen planned-motion render and Qt timer cadence; no runtime/devices."""

import hashlib
import json
import subprocess
from pathlib import Path
from time import monotonic

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.protocol_document import review_program
from cephvr.gui.appearance import load_terminal_font
from cephvr.gui.theme import apply_theme, stylesheet, RETRO_COLORS

root = Path(__file__).resolve().parents[3]
output = Path(__file__).resolve().parent
app = QApplication([])
load_terminal_font()
apply_theme(app)
timeline = StimulusTimeline()
timeline.resize(1300, 400)
timeline.set_program(review_program(), "", "Trial 1")
timeline.show()
app.processEvents()
timeline.set_playback(12, running=True)
ticks = []
timeline.timer.timeout.connect(lambda: ticks.append(monotonic()))
QTest.qWait(1250)
assert 5 <= len(ticks) <= 7, ticks
assert 13 <= timeline.plot.elapsed <= 13.4
timeline.set_playback(12.13, running=False)
app.processEvents()
assert timeline.grab().save(str(output / "centered-speed.png"))
timeline.setProperty("retroConsole", True)
timeline.setStyleSheet(stylesheet(RETRO_COLORS))
timeline.set_elapsed(12.13)
app.processEvents()
assert timeline.grab().save(str(output / "centered-speed-retro.png"))
timeline.timer.stop()
paths = [
    "src/cephvr/gui/preview_timeline.py",
    "src/cephvr/gui/preview_motion_plot.py",
    "src/cephvr/gui/window.py",
    "tests/gui/test_preview_timeline.py",
]
result = {
    "date": "2026-10-20",
    "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "scope": "Dirty shared checkout; offscreen planning fixture only, no runtime restart or devices.",
    "source_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
    "timer": {"configured_ms": timeline.timer.interval(), "ticks_in_1250ms": len(ticks), "intervals_s": [b-a for a,b in zip(ticks, ticks[1:])]},
    "tests": "QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/gui/test_preview_timeline.py -q -m 'not windows and not rig' --basetemp=.pytest_tmp_centered_speed: 16 passed",
    "static": "Ruff check/format: 4 files pass; mypy --platform win32: 3 sources pass; boundaries: 739 modules, zero violations; git diff --check passes (existing CRLF notices).",
    "initial_failure": "Fractional endpoint rounding produced12.129999999999999; fixed by retaining exact right endpoint. Final16 checks pass.",
    "limits": "Existing tests/gui/test_dashboard.py was already zero bytes and preserved. New standalone timeline fixture avoids concurrent Dashboard tests. No full GUI or rig acceptance.",
}
(output / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result["timer"]))
timeline.close()
