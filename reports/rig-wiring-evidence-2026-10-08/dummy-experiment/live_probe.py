"""Read actual authenticated controller state without claiming control."""

import asyncio
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent

async def run():
    record = {}
    endpoint = _existing_endpoint(default_runtime_root())
    if endpoint is None:
        raise RuntimeError("No managed runtime endpoint")
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal, rpc_timeout_s=5)
            state = await client.get_snapshot()
            (OUT / "original-snapshot.pb").write_bytes(state.SerializeToString())
            record = MessageToDict(state, preserving_proto_field_name=True)
            for backend in record.get("configuration_values", {}).get("current", {}).get("backends", []):
                for role in ("behavioral", "tracking"):
                    device = backend.get("acquisition", {}).get(role, {}).get("device", {})
                    if "pfs_baseline" in device:
                        device["pfs_baseline"] = "<retained; omitted>"
            print(json.dumps({k: record.get(k) for k in ("controller_generation", "session", "control", "warnings")}, indent=2))
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        print(record["error"])
    finally:
        store.remove_client(principal)
        (OUT / "live-probe.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

asyncio.run(run())
