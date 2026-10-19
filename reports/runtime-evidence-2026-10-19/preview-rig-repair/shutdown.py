"""Bounded normal shutdown of the test generation through its controller."""
import asyncio
import dataclasses
import json
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def main():
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    result = {"controller_generation": endpoint.controller_generation}
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                result["shutdown"] = dataclasses.asdict(
                    await asyncio.wait_for(client.execute("ShutdownApplication"), 90)
                )
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        store.remove_client(principal)
        (Path(__file__).parent / "shutdown.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result))


asyncio.run(main())
