"""Paint the splash before importing the managed frontend."""

import sys

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from cephvr.gui.splash import StartupSplash


def main() -> int:
    """Paint before importing the managed frontend; reuse its bootstrap protocol."""
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CephVR2.0 Dashboard")
    splash = StartupSplash(QSettings("CephVR", "Frontend"))
    splash.begin()
    try:
        from cephvr.gui.main import main as managed_main

        return managed_main(splash=splash)
    finally:
        splash.timer.stop()
        splash.close()


if __name__ == "__main__":
    raise SystemExit(main())
