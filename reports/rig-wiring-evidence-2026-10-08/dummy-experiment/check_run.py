"""Read current experiment progress without acquiring control or mutating devices."""
import argparse
import asyncio
import json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

out = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("label")
args = parser.parse_args()

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    if endpoint is None:
        raise RuntimeError("No managed endpoint")
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            state = await HeadlessClient(channel, principal).get_snapshot()
            (out / f"{args.label}.pb").write_bytes(state.SerializeToString())
            names = ("controller_generation", "session", "trial", "participants", "operations", "warnings", "prompts", "metadata")
            values = MessageToDict(state, preserving_proto_field_name=True)
            selected = {name: values.get(name) for name in names}
            (out / f"{args.label}.json").write_text(json.dumps(selected, indent=2), encoding="utf-8")
            print(json.dumps(selected, indent=2))
    finally:
        store.remove_client(principal)

asyncio.run(main())
