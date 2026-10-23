"""Foreground Windows launch probe; no devices, controller or saved-state writes."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QPushButton

from cephvr.gui.splash import StartupSplash
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

ROOT = Path(__file__).resolve().parent
capture = subprocess.Popen(
    [
        shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "warning",
        "-f", "gdigrab", "-framerate", "60", "-draw_mouse", "0",
        "-video_size", "1920x1080", "-offset_x", "0", "-offset_y", "0",
        "-i", "desktop", "-t", "30", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "18", "-pix_fmt", "yuv420p", str(ROOT / "native-verified.mp4"),
    ],
    creationflags=subprocess.CREATE_NO_WINDOW,
)
app = QApplication(sys.argv[:1])
apply_theme(app)
app.setQuitOnLastWindowClosed(False)
launcher = QPushButton("Launch native Dashboard")
launcher.setWindowTitle("CephVR startup verification")
launcher.resize(400, 120)
styles = iter(("standard", "retro_console", "amber_phosphor"))
results = []
windows = []


class Paints(QObject):
    def eventFilter(self, watched, event):
        if windows and watched is windows[-1][0] and event.type() == QEvent.Type.Paint:
            windows[-1][2].append(
                {"opacity": watched.windowOpacity(), "maximized": watched.isMaximized()}
            )
        return False


observer = Paints()
app.installEventFilter(observer)


def launch():
    style = next(styles, None)
    print("launch", style, flush=True)
    if style is None:
        (ROOT / "native-probe-results.json").write_text(json.dumps(results, indent=2))
        app.removeEventFilter(observer)
        for window, splash, _ in windows:
            window.deleteLater()
            splash.deleteLater()
        windows.clear()
        launcher.deleteLater()
        QTimer.singleShot(0, app.quit)
        return
    launcher.hide()
    settings = QSettings(str(ROOT / "isolated-probe.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/style", style)
    splash = StartupSplash(settings)
    splash.begin()
    print("splash", style, flush=True)
    window = DashboardWindow(settings=settings)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    paints = []
    windows.append((window, splash, paints))
    splash.reveal(window)
    print("revealed", style, len(paints), flush=True)
    window.raise_()
    window.activateWindow()
    results.append({"style": style, "paints": paints})
    QTimer.singleShot(4000, advance)


def advance():
    windows[-1][0].close()
    launch()


launcher.clicked.connect(launch)
launcher.show()
QTimer.singleShot(2000, launch)
code = app.exec()
print("event loop exited", code, flush=True)
capture.wait()
raise SystemExit(code)
