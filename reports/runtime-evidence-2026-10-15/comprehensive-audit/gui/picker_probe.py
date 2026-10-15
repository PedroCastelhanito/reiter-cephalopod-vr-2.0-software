"""Bound the owning native roundtrip and retain dialog state before acceptance."""

import faulthandler
import json
import os
import sys
import threading


def report(event, **values):
    print(json.dumps({"event": event, **values}, ensure_ascii=True), flush=True)


def expired():
    report("owned_process_watchdog_expired", seconds=15)
    faulthandler.dump_traceback()
    os._exit(124)


watchdog = threading.Timer(15, expired)
watchdog.daemon = True
watchdog.start()

import pytest
from PyQt6.QtCore import QTimer, Qt


class PickerProbe:
    @pytest.fixture(autouse=True)
    def instrument(self, monkeypatch):
        report("instrument_fixture_started")
        from cephvr.gui import configuration_files

        factory = configuration_files.file_dialog
        timers = []

        def traced_factory(*args, **kwargs):
            report("dialog_factory_called")
            dialog = factory(*args, **kwargs)
            accept = dialog.accept

            def traced_accept():
                report("accept_entered")
                try:
                    report("selected_files", value=dialog.selectedFiles())
                    report("directory", value=dialog.directory().absolutePath())
                    report("visible", value=dialog.isVisible())
                    report(
                        "native_hidden",
                        value=dialog.testAttribute(
                            Qt.WidgetAttribute.WA_DontShowOnScreen
                        ),
                    )
                    report(
                        "timers",
                        value=[
                            {
                                "active": timer.isActive(),
                                "remaining": timer.remainingTime(),
                            }
                            for timer in dialog.findChildren(QTimer)
                        ],
                    )
                except BaseException as error:
                    report("instrumentation_error", error=repr(error))
                    dialog.reject()
                    raise
                cancel = QTimer(dialog)
                cancel.setSingleShot(True)

                def reject():
                    report("bounded_reject_fired")
                    dialog.reject()

                cancel.timeout.connect(reject)
                cancel.start(1500)
                timers.append(cancel)
                accept()
                report("accept_returned")

            monkeypatch.setattr(dialog, "accept", traced_accept)
            return dialog

        monkeypatch.setattr(configuration_files, "file_dialog", traced_factory)
        yield


try:
    result = pytest.main(
        [
            "tests/gui/test_dashboard.py::test_tab_config_buttons_roundtrip_into_fresh_gui[protocol]",
            "-vv",
            "-s",
            "--basetemp=" + sys.argv[1],
            "-o",
            "faulthandler_timeout=10",
        ],
        plugins=[PickerProbe()],
    )
    report("pytest_finished", exitcode=int(result))
finally:
    watchdog.cancel()

raise SystemExit(result)
