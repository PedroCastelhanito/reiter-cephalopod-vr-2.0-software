"""Read-only supervisor recovery evidence with an operator credential."""
import asyncio
import json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, services_pb2_grpc as transport
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50052, 16_777_216) as channel:
            stub = transport.SupervisorServiceStub(channel)
            result = await stub.GetRecoveryState(rpc.RecoveryQuery(
                expected_supervisor={"role": "supervisor", "generation": endpoint.supervisor_generation}),
                metadata=principal.metadata(), timeout=5)
            data = MessageToDict(result, preserving_proto_field_name=True)
            (Path(__file__).parent / "supervisor-recovery.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(json.dumps(data, indent=2)[-20000:])
    finally:
        store.remove_client(principal)

asyncio.run(main())
