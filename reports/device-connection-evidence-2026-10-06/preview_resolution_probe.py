"""Resolve the saved camera request through the SDK, without grabbing or pulses."""
import json
import traceback
from pathlib import Path

from google.protobuf.json_format import ParseDict, MessageToDict
from cephvr.control.v1 import types_pb2 as control
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.camera.basler import BaslerCameraAdapter
from cephvr.acquisition.worker.camera_resolution import resolve_camera

folder = Path(__file__).parent
snapshot = json.loads((folder / "preview-failure-snapshot.json").read_text())
configuration = ParseDict(snapshot["configuration_values"]["current"], control.ExperimentConfiguration())
setting = next(b.acquisition.behavioral for b in configuration.backends if b.backend_name == "acquisition")
adapter = BaslerCameraAdapter()
result = {"method": "SDK resolution only; no grabbing or MCU outputs"}
try:
    resolved = resolve_camera(adapter, acq.WorkerResolveCamera(requested=setting.device, configuration_revision=1))
    result["resolved"] = MessageToDict(resolved, preserving_proto_field_name=True)
except Exception:
    result["failure"] = traceback.format_exc()
finally:
    adapter.close()
    result["closed"] = True
    (folder / "preview-resolution-probe.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "resolved"}, indent=2))
