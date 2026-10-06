"""Exercise camera Use independently of settings; no capture or pulse commands."""

import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.credentials import CredentialStore, default_runtime_root

output = Path(__file__).parent


def retain(state):
    document = MessageToDict(state, preserving_proto_field_name=True)
    document.pop("configuration_values", None)
    with (output / "enablement-runtime-events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(document) + "\n")


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    result = {"captured_at": datetime.now().astimezone().isoformat(), "generation": sys.argv[1]}
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal, on_snapshot=retain)
            async with client.control():
                current = client.snapshot.configuration_values.current
                proposed = pb.ExperimentConfiguration()
                proposed.CopyFrom(current)
                entry = next(item for item in proposed.backends if item.backend_name == "acquisition")
                entry.enabled = True
                entry.acquisition.behavioral.enabled = True
                entry.acquisition.tracking.enabled = True
                result["enable"] = asdict(await asyncio.wait_for(client.execute(
                    "UpdateConfiguration", rpc.UpdateConfigurationRequest(
                        command=client.operator_command(),
                        expected_revision=client.snapshot.configuration.revision,
                        proposed=proposed,
                    ),
                ), 8))
                print(json.dumps({"enable": result["enable"]}), flush=True)
                if not result["enable"]["succeeded"]:
                    return
                await asyncio.sleep(25)
                state = await client.get_snapshot()
                result["alive_after_25_seconds"] = True
                result["phase"] = pb.SessionPhase.Name(state.session.phase)
                settings = next(item.acquisition for item in state.configuration_values.current.backends if item.backend_name == "acquisition")
                result["camera_use"] = {"behavioral": settings.behavioral.enabled, "tracking": settings.tracking.enabled}
                result["trigger_source_present"] = {role: getattr(settings, role).device.settings.HasField("trigger_source") for role in ("behavioral", "tracking")}
                # Restore this test's participation choices; hardware was never opened.
                restored = pb.ExperimentConfiguration()
                restored.CopyFrom(state.configuration_values.current)
                original = next(item for item in current.backends if item.backend_name == "acquisition")
                selected = next(item for item in restored.backends if item.backend_name == "acquisition")
                selected.enabled = original.enabled
                for role in ("behavioral", "tracking"):
                    target, source = getattr(selected.acquisition, role), getattr(original.acquisition, role)
                    if source.HasField("enabled"):
                        target.enabled = source.enabled
                    elif target.HasField("enabled"):
                        target.ClearField("enabled")
                result["restore"] = asdict(await asyncio.wait_for(client.execute(
                    "UpdateConfiguration", rpc.UpdateConfigurationRequest(
                        command=client.operator_command(),
                        expected_revision=client.snapshot.configuration.revision,
                        proposed=restored,
                    ),
                ), 8))
            result["release_failure"] = client.release_failure
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        store.remove_client(principal)
        (output / "enablement-runtime.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)


asyncio.run(asyncio.wait_for(run(), 50))
