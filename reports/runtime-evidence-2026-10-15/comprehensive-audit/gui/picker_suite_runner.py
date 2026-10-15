"""Bound a native GUI pytest selection without changing its dialogs or assertions."""

import faulthandler
import os
import sys
import threading

import pytest


def expired():
    faulthandler.dump_traceback()
    os._exit(124)


watchdog = threading.Timer(int(sys.argv[1]), expired)
watchdog.daemon = True
watchdog.start()
try:
    result = pytest.main(sys.argv[2:])
finally:
    watchdog.cancel()
raise SystemExit(result)
