"""Native V19 missing-saved-identity injection and exact restoration."""

import asyncio
import dataclasses
import json
from pathlib import Path
from time import monotonic

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
result = {"method": "injected missing saved native interface; no physical unplug"}

def keep(name, value):
    result[name] = value
    (OUT / "display-issue.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    keep("controller_generation", endpoint.controller_generation)
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                state = await client.get_snapshot()
                if state.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    raise RuntimeError("Configuration required")
                original = pb.ExperimentConfiguration.FromString(state.configuration_values.current.SerializeToString())
                candidate = pb.ExperimentConfiguration.FromString(original.SerializeToString())
                visual = next(b.visual_stimulus for b in candidate.backends if b.backend_name == "visual_stimulus")
                profile = json.loads(visual.display.profile_json)
                profile["outputs"][0]["device_identity"] += "-rig-check-unavailable-20261013"
                visual.display.profile_json = json.dumps(profile)

                async def update(configuration, name):
                    current = await client.get_snapshot()
                    request = rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=current.configuration.revision, proposed=configuration)
                    outcome = await client.execute("UpdateConfiguration", request)
                    keep(name + "_update", dataclasses.asdict(outcome))
                    if not outcome.succeeded:
                        raise RuntimeError(outcome.failure)
                    end = monotonic() + 75
                    while monotonic() < end:
                        current = await client.get_snapshot()
                        display = current.visual_stimulus_display
                        if display.requested_revision == current.configuration.revision and display.complete:
                            keep(name + "_display", MessageToDict(display, preserving_proto_field_name=True))
                            keep(name + "_session", MessageToDict(current.session, preserving_proto_field_name=True))
                            (OUT / f"display-{name}.pb").write_bytes(current.SerializeToString())
                            return current
                        await asyncio.sleep(0.1)
                    raise TimeoutError("display result was not confirmed")

                try:
                    current = await update(candidate, "missing")
                    keep("configuration_available_with_issue", current.session.phase == pb.SESSION_PHASE_CONFIGURATION and bool(current.visual_stimulus_display.issues))
                finally:
                    current = await update(original, "restored")
                    keep("exact_configuration_restored", current.configuration_values.current == original)
                    keep("all_four_idle_ready", current.visual_stimulus_display.complete and len(current.visual_stimulus_display.outputs) == 4 and all(o.resources_ready for o in current.visual_stimulus_display.outputs))
    finally:
        store.remove_client(principal)

asyncio.run(main())
