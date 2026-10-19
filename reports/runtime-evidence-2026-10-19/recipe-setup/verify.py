import asyncio, dataclasses, json
from pathlib import Path
from google.protobuf.json_format import ParseDict, MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
OUT=Path(__file__).parent
async def main():
 root=default_runtime_root(); endpoint=_existing_endpoint(root)
 store=CredentialStore(root,endpoint.controller_generation); principal=store.provision_client('cli'); results=[]
 try:
  async with loopback_channel(50051,16777216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    assert client.snapshot.session.phase==pb.SESSION_PHASE_CONFIGURATION
    candidate=ParseDict(json.loads((OUT/'candidate.json').read_text()),pb.ExperimentConfiguration())
    for name in ('UpdateConfiguration','SaveConfigurationHistory','Setup'):
     request=rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=candidate) if name=='UpdateConfiguration' else None
     result=await asyncio.wait_for(client.execute(name,request) if request is not None else client.execute(name),120)
     results.append({'command':name,**dataclasses.asdict(result)})
     (OUT/'setup-results.json').write_text(json.dumps(results,indent=2))
     print(json.dumps(results[-1]),flush=True)
     if not result.succeeded:break
    state=await client.get_snapshot()
    (OUT/'after.json').write_text(json.dumps(MessageToDict(state,preserving_proto_field_name=True),indent=2))
    print('Phase:',pb.SessionPhase.Name(state.session.phase),flush=True)
 finally:store.remove_client(principal)
asyncio.run(main())
