"""Bounded native review-only Monitor/Amber transition reproduction; no rig API."""
import faulthandler
import json
import time
import sys
import traceback
from pathlib import Path
from dataclasses import replace

from PyQt6.QtCore import QTimer, QEvent
from PyQt6.QtWidgets import QApplication
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
from cephvr.gui.view import Phase

OUT = Path(__file__).resolve().parent
trace = (OUT / "style-reproduction-fault.log").open("w", encoding="utf-8")
faulthandler.enable(file=trace, all_threads=True)
faulthandler.dump_traceback_later(25, file=trace)

def record(event, **values):
    row = {"event": event, "host_ns": time.perf_counter_ns(), **values}
    with (OUT / "style-reproduction-events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)

def exception_hook(kind, error, tb):
    with (OUT / "style-reproduction-exceptions.log").open("a", encoding="utf-8") as stream:
        traceback.print_exception(kind, error, tb, file=stream)
    sys.__excepthook__(kind, error, tb)

sys.excepthook = exception_hook
app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=None)
window.setWindowTitle("CephVR disposable style reproduction")
window.resize(1440, 940)
window.appearance.select("retro_console", persist=False)
window.show()

def monitor():
    record("before_monitor")
    window.apply_view(replace(window.dashboard.view, phase=Phase.RUNNING))
    record("after_monitor", runtime_layout=window.dashboard.runtime_layout)

def amber():
    record("before_amber")
    window.appearance.actions["amber_phosphor"].trigger()
    record("after_amber", style=window.appearance.name)
    assert window.appearance.name == "amber_phosphor"

def finish():
    record("finish", visible=window.isVisible(), runtime_layout=window.dashboard.runtime_layout)
    window.grab().save(str(OUT / "style-reproduction.png"))
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.quit()

QTimer.singleShot(1000, monitor)
QTimer.singleShot(3000, amber)
QTimer.singleShot(8000, finish)
QTimer.singleShot(20000, app.quit)
record("event_loop_start", platform=app.platformName())
result = app.exec()
record("event_loop_end", exit_code=result)
faulthandler.cancel_dump_traceback_later()
trace.flush()
raise SystemExit(result)
