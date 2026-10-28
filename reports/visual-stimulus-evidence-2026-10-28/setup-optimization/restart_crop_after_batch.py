import asyncio,json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
OUT=Path(__file__).parent/'crop-batch-restart';OUT.mkdir(exist_ok=True)
async def main():
    ep=_existing_endpoint(default_runtime_root()); store=CredentialStore(default_runtime_root(),ep.controller_generation); principal=store.provision_client('cli')
    try:
        async with loopback_channel(50051,67108864) as channel:
            c=HeadlessClient(channel,principal)
            async with c.control(takeover=True):
                assert c.snapshot.session.phase==pb.SESSION_PHASE_CONFIGURATION
                assert c.snapshot.session.cleanup_confirmed or not c.snapshot.session.HasField('context')
                (OUT/'before-restart.json').write_text(json.dumps(MessageToDict(c.snapshot,preserving_proto_field_name=True),indent=2))
                result=await asyncio.wait_for(c.execute('ShutdownApplication'),60)
                print(result,flush=True)
    finally:store.remove_client(principal)
asyncio.run(main())
