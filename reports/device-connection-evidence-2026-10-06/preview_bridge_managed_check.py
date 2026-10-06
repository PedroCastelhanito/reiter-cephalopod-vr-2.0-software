"""Restore the operator draft and verify connections after the wait-bridge repair."""
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import ParseDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def run():
    folder = Path(__file__).parent
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    result = {"generation": sys.argv[1], "checks": []}
    try:
        proposed = ParseDict(json.loads((folder / "preview-preserved-draft.json").read_text()), pb.ExperimentConfiguration())
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control():
                outcome = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                    command=client.operator_command(), expected_revision=client.snapshot.configuration.revision,
                    proposed=proposed,
                ))
                result["draft_restored"] = asdict(outcome)
                if not outcome.succeeded:
                    raise RuntimeError(outcome.failure)
                for role in (1, 2):
                    outcome = await client.execute("ExecuteCameraCommand", rpc.CameraCommandRequest(
                        command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision,
                        camera=role, kind=rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
                    ))
                    result["checks"].append({"camera": role, **asdict(outcome)})
                    if not outcome.succeeded:
                        raise RuntimeError(outcome.failure)
            result["control_released"] = client.release_failure is None
            await asyncio.sleep(2)
            state = await client.get_snapshot()
            result["camera_state"] = {
                role: {field: getattr(getattr(state.acquisition_devices, role), field)
                       for field in ("device_open", "preview_running", "cleanup_pending")}
                for role in ("behavioral", "tracking")
            }
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        store.remove_client(principal)
        (folder / "preview-bridge-managed-check.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


asyncio.run(asyncio.wait_for(run(), 55))
