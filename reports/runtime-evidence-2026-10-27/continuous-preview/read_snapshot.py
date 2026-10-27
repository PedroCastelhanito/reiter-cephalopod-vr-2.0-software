"""Authenticated read-only native-test snapshot; never acquires control."""
import asyncio,json,sys,tomllib
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
async def main():
    root=Path(__file__).resolve().parents[3]
    endpoint=_existing_endpoint(default_runtime_root())
    assert endpoint.controller_generation == sys.argv[1]
    output=Path(sys.argv[2]).resolve()
    assert output.is_relative_to(root) and not output.exists()
    store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
    principal=store.provision_client("cli")
    try:
        settings=tomllib.loads((root/"config/backends/experiment_config.toml").read_text(encoding="utf-8"))
        async with loopback_channel(settings["rpc"]["port"],settings["rpc"]["max_message_bytes"]) as channel:
            snapshot=await HeadlessClient(channel,principal).get_snapshot()
            assert snapshot.controller_generation == sys.argv[1]
            output.write_text(json.dumps(MessageToDict(snapshot,preserving_proto_field_name=True),indent=2),encoding="utf-8")
            print(snapshot.session.phase,[(role,getattr(snapshot.acquisition_devices,role).preview_run_id) for role in ("behavioral","tracking")])
    finally:
        store.remove_client(principal)
asyncio.run(main())
