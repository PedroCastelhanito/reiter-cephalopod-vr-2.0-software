import asyncio,dataclasses,json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import services_pb2 as rpc,types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
OUT=Path(__file__).parent
async def main():
 root=default_runtime_root();endpoint=_existing_endpoint(root);store=CredentialStore(root,endpoint.controller_generation);principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,16777216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    state=client.snapshot
    assert not any(x.backend_name=='synchronization' and x.enabled for x in state.configuration_values.current.backends)
    assert len(state.prompts)==1
    prompt=state.prompts[0]
    assert prompt.explanation.startswith('Recover unfinished session at ')
    response=rpc.PromptResponse(command=client.operator_command(),prompt_id=prompt.prompt_id,setup=prompt.setup,setup_operation=prompt.operation,choice='continue')
    result=await asyncio.wait_for(client.execute('RespondToPrompt',response),90)
    (OUT/'recovery.json').write_text(json.dumps(dataclasses.asdict(result),indent=2));print('Recovery',dataclasses.asdict(result),flush=True)
    assert result.succeeded
    result=await asyncio.wait_for(client.execute('Setup'),120)
    (OUT/'setup-final.json').write_text(json.dumps(dataclasses.asdict(result),indent=2));print('Setup',dataclasses.asdict(result),flush=True)
    state=await client.get_snapshot();(OUT/'after.json').write_text(json.dumps(MessageToDict(state,preserving_proto_field_name=True),indent=2));print('Phase',pb.SessionPhase.Name(state.session.phase),flush=True)
 finally:store.remove_client(principal)
asyncio.run(main())
