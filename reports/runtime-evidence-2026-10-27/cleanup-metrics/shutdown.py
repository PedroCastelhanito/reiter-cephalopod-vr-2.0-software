"""Normal bounded shutdown of an explicitly named audit generation."""

import argparse
import asyncio
import dataclasses
import json
import tomllib
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

parser = argparse.ArgumentParser()
parser.add_argument("generation")
parser.add_argument("label")
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
settings = tomllib.loads((root / "config/backends/experiment_config.toml").read_text())
out = Path(__file__).parent / (args.label + ".json")
assert not out.exists()


async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    assert endpoint and endpoint.controller_generation == args.generation
    store = CredentialStore(default_runtime_root(), args.generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(
            settings["rpc"]["port"], settings["rpc"]["max_message_bytes"]
        ) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert client.snapshot.controller_generation == args.generation
                assert (
                    client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                    and not client.snapshot.prompts
                )
                assert not client.snapshot.session.cleanup_blockers
                assert all(item.complete for item in client.snapshot.operations)
                result = await asyncio.wait_for(
                    client.execute("ShutdownApplication"), 90
                )
                out.write_text(
                    json.dumps(
                        {
                            "generation": args.generation,
                            "result": dataclasses.asdict(result),
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                assert result.succeeded
    finally:
        store.remove_client(principal)


asyncio.run(main())
