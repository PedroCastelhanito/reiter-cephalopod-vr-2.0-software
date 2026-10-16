"""Read-only domain-projection and setting-validation mismatch probes."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import tomllib

from cephvr.acquisition.config.values import _validate_microcontroller_defaults
from cephvr.acquisition.v1 import camera_pb2
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.microcontroller.config import load_serial_policies
from cephvr.gui.managed_display_operations import required_inventory_roles as gui_roles
from cephvr.synchronization.inventory_validation import required_inventory_roles as backend_roles

configuration = pb.ExperimentConfiguration()
backend = configuration.backends.add(backend_name="acquisition", enabled=True)
backend.acquisition.eye_tracking.enabled = True
backend.acquisition.eye_tracking.device.frame_timing = camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
roles = {"gui": sorted(gui_roles(configuration)), "backend": sorted(backend_roles(configuration))}
values = tomllib.loads(Path("config/backends/microcontroller_config.toml").read_text(), parse_float=Decimal)["microcontroller"]
values["ack_timeout_ms"] = Decimal("1.5")
with patch("cephvr.controller.microcontroller.config.load_microcontroller_pair", return_value=SimpleNamespace(config={"microcontroller": values})):
    serial = load_serial_policies(Path("."))
try:
    _validate_microcontroller_defaults(values)
except ValueError as exc:
    defaults = {"accepted": False, "message": str(exc)}
else:
    defaults = {"accepted": True}
result = {
    "method": "Direct pure projections and validators; injected values only, no host file mutation, sockets, devices or runtime acceptance.",
    "eye_required_roles": roles,
    "fractional_ack_timeout_ms": {"input": "Decimal('1.5')", "controller_resolved_ns": serial.serial_ack_timeout_ns, "acquisition_defaults": defaults},
    "assessment": "Duplicated domain functions demonstrably disagree. This does not choose which numeric setting type should be accepted.",
}
assert roles["gui"] != roles["backend"]
assert serial.serial_ack_timeout_ns == 1_500_000 and not defaults["accepted"]
Path(__file__).with_name("reproduction.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
