"""One-shot authenticated evidence capture; never claims control or issues commands."""
import asyncio
import json
import sys
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def main():
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            state = await HeadlessClient(channel, principal).get_snapshot()
        data = MessageToDict(state, preserving_proto_field_name=True)
        output = Path(__file__).parent / (sys.argv[1] + ".json")
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        devices = data.get("acquisition_devices", {})
        print(json.dumps({
            "session": data.get("session"),
            "cameras": {role: {k: v for k, v in devices.get(role, {}).items()
                if k in ("device_open", "preview_running", "preview_visible",
                         "preview_run_id", "cleanup_pending")}
                for role in ("behavioral", "tracking", "eye_tracking")},
            "operations": data.get("operations"),
        }, indent=2))
    finally:
        store.remove_client(principal)


asyncio.run(main())
