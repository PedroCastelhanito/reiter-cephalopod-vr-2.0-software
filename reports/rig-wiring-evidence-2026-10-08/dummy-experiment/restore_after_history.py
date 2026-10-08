"""Verify actual shutdown history reload and restore the previous reusable draft."""
import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent
async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    result = {"controller_generation": endpoint.controller_generation}
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                state = await client.get_snapshot()
                if state.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    raise RuntimeError("Configuration phase required")
                result["shutdown_history_marker_reloaded"] = state.configuration_values.current.experiment == "DUMMY_SHUTDOWN_HISTORY_CHECK"
                result["registered_participants"] = [MessageToDict(p, preserving_proto_field_name=True) for p in state.participants]
                original = pb.Snapshot.FromString((OUT / "pre-restart-snapshot.pb").read_bytes()).configuration_values.current
                outcome = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(
                    command=client.operator_command(), expected_revision=state.configuration.revision, proposed=original))
                result["restore"] = dataclasses.asdict(outcome)
                if not outcome.succeeded:
                    raise RuntimeError(outcome.failure)
                result["save_original"] = dataclasses.asdict(await client.execute("SaveConfigurationHistory"))
                result["configuration_restored"] = client.snapshot.configuration_values.current == original
                result["visual_display_state"] = MessageToDict(client.snapshot.visual_stimulus_display, preserving_proto_field_name=True)
    finally:
        store.remove_client(principal)
        (OUT / "history-reload-restoration.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))

asyncio.run(main())
