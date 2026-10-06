"""Owner-authorized Behavior-only D10/Line4 preview, stop, and cleanup check."""
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import ParseDict, MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def run():
    folder = Path(__file__).parent
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    result = {"generation": sys.argv[1], "scope": "Behavior only: D10 to Line4"}
    try:
        proposed = ParseDict(json.loads((folder / "preview-preserved-draft.json").read_text()), pb.ExperimentConfiguration())
        acquisition = next(b.acquisition for b in proposed.backends if b.backend_name == "acquisition")
        assert acquisition.behavioral.device.settings.trigger_source == "Line4"
        assert acquisition.pulses.behavioral.pin == "D10"
        assert not acquisition.tracking.enabled
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control():
                restored = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                    command=client.operator_command(), expected_revision=client.snapshot.configuration.revision,
                    proposed=proposed,
                ))
                result["draft_restored"] = asdict(restored)
                if not restored.succeeded:
                    raise RuntimeError(restored.failure)
                started = await client.execute("ExecuteCameraCommand", rpc.CameraCommandRequest(
                    command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision,
                    camera=1, kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW,
                ))
                result["start"] = asdict(started)
                state = await client.get_snapshot()
                result["after_start"] = MessageToDict(state.acquisition_devices, preserving_proto_field_name=True)
                if not started.succeeded:
                    raise RuntimeError(started.failure)
                await asyncio.sleep(2)
                state = await client.get_snapshot()
                result["running"] = MessageToDict(state.acquisition_devices, preserving_proto_field_name=True)
                stopped = await client.execute("ExecuteCameraCommand", rpc.CameraCommandRequest(
                    command=client.operator_command(), expected_configuration_revision=state.configuration.revision,
                    camera=1, kind=rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW,
                    preview_run_id=state.acquisition_devices.behavioral.preview_run_id,
                ))
                result["stop"] = asdict(stopped)
                if not stopped.succeeded:
                    raise RuntimeError(stopped.failure)
            result["control_released"] = client.release_failure is None
            await asyncio.sleep(2)
            state = await client.get_snapshot()
            result["final_devices"] = MessageToDict(state.acquisition_devices, preserving_proto_field_name=True)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        store.remove_client(principal)
        (folder / "behavior-preview-check.json").write_text(json.dumps(result, indent=2))
        print(json.dumps({k: v for k, v in result.items() if k not in ("after_start", "running", "final_devices")}, indent=2))


asyncio.run(asyncio.wait_for(run(), 75))
