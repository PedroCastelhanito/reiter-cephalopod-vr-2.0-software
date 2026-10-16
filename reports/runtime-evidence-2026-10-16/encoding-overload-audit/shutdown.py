"""Normal bounded shutdown of an explicitly named audit generation."""
import argparse
import asyncio
import dataclasses
import json
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

parser=argparse.ArgumentParser()
parser.add_argument("generation")
parser.add_argument("label")
args=parser.parse_args()
out=Path(__file__).parent/(args.label+".json")
assert not out.exists()

async def main():
    endpoint=_existing_endpoint(default_runtime_root())
    assert endpoint and endpoint.controller_generation==args.generation
    store=CredentialStore(default_runtime_root(),args.generation)
    principal=store.provision_client("cli")
    try:
        async with loopback_channel(50051,16_777_216) as channel:
            client=HeadlessClient(channel,principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase==pb.SESSION_PHASE_CONFIGURATION and not client.snapshot.prompts
                result=await asyncio.wait_for(client.execute("ShutdownApplication"),90)
                out.write_text(json.dumps({"generation":args.generation,"result":dataclasses.asdict(result)},indent=2)+"\n",encoding="utf-8")
                assert result.succeeded
    finally:
        store.remove_client(principal)

asyncio.run(main())
