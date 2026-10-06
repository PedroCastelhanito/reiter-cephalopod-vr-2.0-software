"""Native SDK event duplication and blocking wake compatibility on Windows."""

from __future__ import annotations

import sys
from threading import Event, Timer

import pytest

from cephvr.acquisition.camera.wait import PylonWaitGate, _control_wait
from cephvr.platform.windows.events import ManualResetEvent

pytestmark = [
    pytest.mark.windows,
    pytest.mark.skipif(sys.platform != "win32", reason="Win32 event binding"),
]


def test_native_pylon_wait_duplicate_lifetime_and_blocking_wakeup() -> None:
    pylon = pytest.importorskip("pypylon.pylon")
    pytest.importorskip("cephvr.acquisition.camera.pylon_wait_binding")
    event = ManualResetEvent.create()
    wait_object = _control_wait(event)
    waits = pylon.WaitObjects()
    waits.Add(wait_object)
    assert not waits.WaitForAny(0)
    event.set()
    assert waits.WaitForAny(0)
    event.clear()
    assert not waits.WaitForAny(0)
    event.set()
    event.close()
    assert waits.WaitForAny(0), "SDK duplicate must survive original handle closure"
    waits.RemoveAll()
    del wait_object

    gate = PylonWaitGate()
    gate._pylon = pylon
    acknowledgement = Event()
    timers: list[Timer] = []

    def schedule(wake):
        def signal() -> None:
            acknowledgement.set()
            wake()

        timer = Timer(0.05, signal)
        timers.append(timer)
        timer.start()
        return acknowledgement

    try:
        gate.verify_blocking_control_wakeup(schedule, 1_000_000_000)
        assert acknowledgement.is_set()
    finally:
        for timer in timers:
            timer.join()
        gate.close()
