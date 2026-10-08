"""Read-only confirmation of GUI close/history and unchanged native configuration."""
import asyncio
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict, ParseDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent
async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            state = await HeadlessClient(channel, principal).get_snapshot()
        original = pb.Snapshot.FromString((OUT / "pre-restart-snapshot.pb").read_bytes()).configuration_values.current
        history = json.loads((OUT.parents[2] / "config/last_configuration.json").read_text(encoding="utf-8"))
        saved = ParseDict(history["configuration"], pb.ExperimentConfiguration())
        result = {
            "controller_generation": endpoint.controller_generation,
            "original_configuration_preserved": state.configuration_values.current == original,
            "history_preserves_original": saved == original,
            "session": MessageToDict(state.session, preserving_proto_field_name=True),
            "operations": [MessageToDict(o, preserving_proto_field_name=True) for o in state.operations],
            "devices": MessageToDict(state.acquisition_devices, preserving_proto_field_name=True),
            "microcontroller": MessageToDict(state.microcontroller, preserving_proto_field_name=True),
        }
        (OUT / "final-native-state.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k not in ("operations", "devices", "microcontroller")}, indent=2))
    finally:
        store.remove_client(principal)

asyncio.run(main())
