"""Owner-authorized bounded board checks after backup and verified upload."""

import json
import time
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.acquisition.configuration import load_file_policies
from cephvr.acquisition.microcontroller.owner import SerialOwner
from cephvr.acquisition.v1 import camera_pb2
from cephvr.shared.clock import host_time_ns

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
result = {"scope": "COM8 protocol3; generated transitions, no receiver/waveform proof", "checks": {}}


def record(name, value):
    result["checks"][name] = value
    (OUT / "mcu-update-board.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)


def deadline():
    return host_time_ns() + 1_000_000_000


owner = SerialOwner("COM8", load_file_policies(ROOT))
connected = False
try:
    observation = owner.connect(host_time_ns() + 5_000_000_000)
    connected = True
    record("startup", MessageToDict(observation, preserving_proto_field_name=True))
    for kind, pin, hz, role in (("trial_state", "D9", None, None),
                               ("behavioral", "D10", 30, 1),
                               ("tracking", "D11", 60, 2)):
        for cycle in range(2):
            if role is not None:
                requested = camera_pb2.CameraPulseConfiguration(port="COM8")
                settings = getattr(requested, kind)
                settings.pin = pin
                settings.requested_frequency_hz = hz
                record(f"{kind}_{cycle}_configure", MessageToDict(owner.configure(requested, deadline(), active_roles=(role,))))
            started = owner.diagnostic_start(kind, pin, deadline(), frequency_hz=hz)
            record(f"{kind}_{cycle}_start", started)
            assert started[3] == 1, started
            for _ in range(5):
                time.sleep(0.1)
                status = owner.diagnostic_status(deadline())
            record(f"{kind}_{cycle}_status", status)
            assert status[3] >= started[3]
            if hz is None:
                assert status[3] == 1
            else:
                assert status[3] > 1
            stopped = owner.diagnostic_stop(deadline())
            record(f"{kind}_{cycle}_stop", stopped)
            assert not stopped[0] and stopped[3] >= status[3]
    record("final_status", MessageToDict(owner.status(deadline()), preserving_proto_field_name=True))
except Exception as exc:
    record("error", f"{type(exc).__name__}: {exc}")
    raise
finally:
    if connected:
        try:
            record("cleanup_off", MessageToDict(owner.off((1, 2), deadline()), preserving_proto_field_name=True))
        except Exception as exc:
            record("cleanup_off_error", str(exc))
    owner.close(deadline())
    record("serial_closed", True)
