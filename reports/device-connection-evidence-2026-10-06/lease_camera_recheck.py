"""Restore the draft and exercise closed-camera tests across control lease release."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import ParseDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.device_requests import import_camera_preset
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def run():
    output = Path(__file__).parent
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    result = {"generation": sys.argv[1], "checks": []}
    try:
        proposed = ParseDict(json.loads((output / "pending-preserved-draft.json").read_text()), pb.ExperimentConfiguration())
        async with loopback_channel(50051, 16_777_216) as channel:
            for cycle in range(2):
                client = HeadlessClient(channel, principal)
                async with client.control():
                    if cycle == 0:
                        outcome = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                            command=client.operator_command(), expected_revision=client.snapshot.configuration.revision,
                            proposed=proposed,
                        ))
                        result["draft_restored"] = asdict(outcome)
                        if not outcome.succeeded:
                            raise RuntimeError(outcome.failure)
                        selected = next(b.acquisition.behavioral.device for b in proposed.backends if b.backend_name == "acquisition")
                        if selected.pfs_source_filename:
                            await import_camera_preset(client, 1, selected.pfs_source_filename)
                            result["pfs_import_and_finish"] = "passed"
                    for role in (1, 2):
                        outcome = await client.execute("ExecuteCameraCommand", rpc.CameraCommandRequest(
                            command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision,
                            camera=role, kind=rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
                        ))
                        result["checks"].append({"cycle": cycle, "camera": role, **asdict(outcome)})
                        if not outcome.succeeded:
                            raise RuntimeError(outcome.failure)
                result[f"cycle_{cycle}_lease_released"] = client.release_failure is None
                await asyncio.sleep(2)
            state = await client.get_snapshot()
            result["cleanup_operations"] = [
                {"complete": item.complete, "succeeded": item.succeeded, "failure": item.failure.message}
                for item in state.operations if item.command == "ReleaseManualCameraState"
            ]
            result["camera_state"] = {
                role: {field: getattr(getattr(state.acquisition_devices, role), field)
                       for field in ("device_open", "preview_running", "cleanup_pending")}
                for role in ("behavioral", "tracking")
            }
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        store.remove_client(principal)
        (output / "lease-camera-recheck.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


asyncio.run(asyncio.wait_for(run(), 55))
