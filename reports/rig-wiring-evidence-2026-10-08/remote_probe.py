"""Read-only managed remote connection and pulse inventory; no remote mutation."""

import asyncio
import json
import sys
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
result = {"controller_generation": sys.argv[1]}


async def run():
    store = CredentialStore(default_runtime_root(), sys.argv[1])
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                inventory = await client.stub.GetSpikeGLXInventory(rpc.SpikeGLXInventoryRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision), metadata=principal.metadata(), timeout=5)
                result["inventory"] = MessageToDict(inventory, preserving_proto_field_name=True)
            try:
                remote = await client.stub.CheckSpikeGLXConnection(rpc.SpikeGLXConnectionQuery(client_id=principal.generation), metadata=principal.metadata(), timeout=8)
                result["connection"] = MessageToDict(remote, preserving_proto_field_name=True)
            except Exception as exc:
                result["connection_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        store.remove_client(principal)
        (OUT / "spikeglx-readonly.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))


asyncio.run(run())
