"""Isolated COM8 firmware watchdog/read-only D2 test after application exit proof."""

import json
import time
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.controller.microcontroller.config import load_serial_policies
from cephvr.controller.microcontroller.owner import SerialOwner
from cephvr.shared.clock import host_time_ns

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
result = {"scope": "COM8 isolated firmware watchdog; no electrical latency or receiver proof", "checks": {}}


def record(name, value):
    result["checks"][name] = value
    (OUT / "board-watchdog.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


def deadline():
    return host_time_ns() + 1_000_000_000


owner = SerialOwner("COM8", load_serial_policies(ROOT))
connected = False
try:
    startup = owner.connect(host_time_ns() + 5_000_000_000)
    connected = True
    record("startup", MessageToDict(startup, preserving_proto_field_name=True))
    record("D2_start", owner.diagnostic_start("projector_flip", "D2", deadline()))
    time.sleep(0.4)
    record("D2_status", owner.diagnostic_status(deadline()))
    record("D2_stop", owner.diagnostic_stop(deadline()))
    requested = camera_pb2.CameraPulseConfiguration(port="COM8")
    requested.behavioral.pin = "D10"
    requested.behavioral.requested_frequency_hz = 30
    requested.tracking.pin = "D11"
    requested.tracking.requested_frequency_hz = 60
    record("configure", MessageToDict(owner.configure(requested, deadline(), active_roles=(1, 2)), preserving_proto_field_name=True))
    enabled = owner.on((1, 2), deadline())
    record("ON", MessageToDict(enabled, preserving_proto_field_name=True))
    assert enabled.outcome == mcu.PULSE_COMMAND_OUTCOME_APPLIED
    before = host_time_ns()
    time.sleep(3.4)
    after = owner.status(deadline())
    record("host_silence_ns", host_time_ns() - before)
    record("after_silence", MessageToDict(after, preserving_proto_field_name=True))
    assert after.state.watchdog_stopped
    assert not after.state.behavioral.running and not after.state.tracking.running
finally:
    if connected:
        record("cleanup_OFF", MessageToDict(owner.off((1, 2), deadline()), preserving_proto_field_name=True))
    owner.close(deadline())
    record("serial_closed", True)
