"""Isolate native picker startup/rejection/destruction without a rig or pytest."""

import argparse
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget

from cephvr.gui.configuration_files import ConfigurationFiles

parser = argparse.ArgumentParser()
parser.add_argument("--delay-ms", type=int, default=0)
parser.add_argument("--flush-child-first", action="store_true")
parser.add_argument("--qt-dialog", action="store_true")
parser.add_argument("--plain", action="store_true")
parser.add_argument("--cycles", type=int, default=20)
args = parser.parse_args()
app = QApplication([])
for cycle in range(args.cycles):
    print(cycle, "create", flush=True)
    parent = QWidget()
    parent.resize(600, 400)
    parent.show()
    app.processEvents()
    files = ConfigurationFiles(parent, "Probe", "probe.json", capture=lambda: {}, validate=lambda value: value, apply=lambda value: None, available=lambda: True)
    if args.qt_dialog:
        app.setAttribute(__import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    print(cycle, "open", flush=True)
    if args.plain:
        original_dialog = QFileDialog(parent, "Plain Qt native probe")
        original_dialog.finished.connect(original_dialog.deleteLater)
        original_dialog.open()
    else:
        files.choose(save=False)
        original_dialog = files.dialog
    assert original_dialog is not None
    if args.delay_ms:
        QTest.qWait(args.delay_ms)
    print(cycle, "reject", flush=True)
    if args.plain:
        original_dialog.reject()
    else:
        files.set_enabled(False)
        assert files.dialog is None
    if args.flush_child_first:
        print(cycle, "flush dialog deferred deletion", flush=True)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    print(cycle, "destroy parent", flush=True)
    parent.close()
    parent.deleteLater()
    app.processEvents()
    print(cycle, "parent events returned", flush=True)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
print("completed", args.cycles, flush=True)
