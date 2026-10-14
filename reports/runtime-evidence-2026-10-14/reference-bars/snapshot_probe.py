"""Read-only authenticated native calibration evidence; never submit device work."""
import asyncio
import json
import sys
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16777216) as channel:
            state = await HeadlessClient(channel, principal).get_snapshot()
            record = {"controller_generation": state.controller_generation,
                      "session": MessageToDict(state.session, preserving_proto_field_name=True),
                      "display": MessageToDict(state.visual_stimulus_display, preserving_proto_field_name=True)}
            (Path(__file__).parent / (sys.argv[1] + ".json")).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(record["display"].get("calibration", {})))
    finally:
        store.remove_client(principal)

asyncio.run(main())
