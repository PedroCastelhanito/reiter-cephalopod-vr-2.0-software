"""Read current controller state without control takeover or device commands."""

import argparse
import asyncio
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

parser = argparse.ArgumentParser()
parser.add_argument("--label", required=True)
options = parser.parse_args()
out = Path(__file__).parent


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint is not None
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            snapshot = await HeadlessClient(channel, principal).get_snapshot()
            (out/(options.label+".pb")).write_bytes(snapshot.SerializeToString())
            data = MessageToDict(snapshot, preserving_proto_field_name=True)
            (out/(options.label+".json")).write_text(json.dumps(data, indent=2)+"\n")
            print(json.dumps({"generation": snapshot.controller_generation, "session": data.get("session"), "prompts": data.get("prompts", [])}, indent=2))
    finally:
        store.remove_client(principal)


asyncio.run(main())
