"""Read-only protocol inventory and authenticated runtime snapshot."""
import asyncio
import hashlib
import json
import time
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.protocol_snapshot import validate_protocol
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent


async def main():
    inventory = []
    for path in Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols').glob('*.json'):
        raw = path.read_bytes()
        start = time.perf_counter()
        value = validate_protocol(json.loads(raw))
        assets = [asset for trial in value['trials'] for asset in trial['program']['assets']]
        inventory.append(dict(name=path.name, sha256=hashlib.sha256(raw).hexdigest(),
                              bytes=len(raw), trials=len(value['trials']),
                              validation_ms=(time.perf_counter()-start)*1000,
                              missing_assets=[a['logical_path'] for a in assets
                                  if not (Path(value['asset_root']) / a['logical_path']).is_file()]))
    (OUT / 'protocol-inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    print(json.dumps(inventory, indent=2), flush=True)
    runtime = default_runtime_root()
    endpoint = _existing_endpoint(runtime)
    store = CredentialStore(runtime, endpoint.controller_generation)
    principal = store.provision_client('cli')
    try:
        async with loopback_channel(50051, 67_108_864) as channel:
            snapshot = await asyncio.wait_for(HeadlessClient(channel, principal).get_snapshot(), 15)
            assert snapshot.controller_generation == endpoint.controller_generation
            (OUT / 'baseline-snapshot.json').write_text(json.dumps(MessageToDict(snapshot,
                preserving_proto_field_name=True), indent=2), encoding='utf-8')
            print(json.dumps(dict(generation=snapshot.controller_generation,
                phase=pb.SessionPhase.Name(snapshot.session.phase),
                cleanup_confirmed=snapshot.session.cleanup_confirmed,
                operations=[dict(command=o.command, complete=o.complete,
                    succeeded=o.succeeded, failure=o.failure.message) for o in snapshot.operations],
                trials=len(snapshot.configuration_values.current.trials))), flush=True)
    finally:
        store.remove_client(principal)


asyncio.run(main())
