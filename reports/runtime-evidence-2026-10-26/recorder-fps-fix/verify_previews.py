import asyncio,json
from pathlib import Path
from dataclasses import asdict
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
from cephvr.control.v1 import services_pb2 as rpc
async def main():
 root=default_runtime_root();endpoint=_existing_endpoint(root)
 assert endpoint.controller_generation=='8f1692c3-7016-4b3b-9ebf-9d09fa5fcfc0'
 store=CredentialStore(root,endpoint.controller_generation);principal=store.provision_client('cli');records=[]
 try:
  async with loopback_channel(50051,16777216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    for names in [[],['Left','Front','Right','Bottom'],['Front','Right','Bottom'],['Left','Front','Right','Bottom'],None,['Left','Front','Right','Bottom']]:
     state=client.snapshot
     placement=rpc.PreviewWindowPlacement(x=400,y=400,side=160)
     if names:
      for i,name in enumerate(names): placement.stimulus_tiles.add(surface=name,x=400+i*180,y=400,side=160)
     req=rpc.SetStimulusPreviewRequest(command=client.operator_command(),expected_configuration_revision=state.configuration.revision,visible=names is not None,placement=placement)
     req.command.expected_work.session.CopyFrom(state.session.context)
     outcome=await client.execute('SetStimulusPreview',req)
     assert outcome.succeeded, outcome
     await asyncio.sleep(2.2)
     snap=MessageToDict(await client.get_snapshot(),preserving_proto_field_name=True)
     records.append({'surfaces':names,'outcome':asdict(outcome),'snapshot':snap})
    Path(__file__).with_name('final-preview-samples.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print('Verified',len(records),'preview mode/visibility operations')
 finally: store.remove_client(principal)
asyncio.run(main())
