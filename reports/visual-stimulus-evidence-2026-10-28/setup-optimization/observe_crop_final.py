import asyncio,json,time
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
OUT=Path(__file__).parent/'crop-live-final'
async def main():
    endpoint=_existing_endpoint(default_runtime_root()); store=CredentialStore(default_runtime_root(),endpoint.controller_generation); principal=store.provision_client('cli')
    try:
        async with loopback_channel(50051,67108864) as channel:
            client=HeadlessClient(channel,principal)
            for i in range(40):
                s=await asyncio.wait_for(client.get_snapshot(),15)
                record={'host_ns':time.perf_counter_ns(),'phase':pb.SessionPhase.Name(s.session.phase),'cleanup':s.session.cleanup_confirmed,'trial':MessageToDict(s.trial,preserving_proto_field_name=True),'preview':MessageToDict(s.stimulus_preview,preserving_proto_field_name=True),'participants':[MessageToDict(p,preserving_proto_field_name=True) for p in s.participants]}
                with (OUT/'observations.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
                print(record['phase'],[p.get('preparation_progress','') for p in record['participants']],flush=True)
                if s.session.phase==pb.SESSION_PHASE_CONFIGURATION:break
                await asyncio.sleep(15)
    finally:store.remove_client(principal)
asyncio.run(main())
