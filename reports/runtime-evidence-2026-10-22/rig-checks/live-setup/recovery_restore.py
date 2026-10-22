"""Preserving recovery of the exact failed test session, then guarded restoration."""
import asyncio
import hashlib
import json
from pathlib import Path
from dataclasses import asdict
from google.protobuf.json_format import MessageToDict, ParseDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb, services_pb2 as rpc
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
OUT=Path(__file__).resolve().parent

def save(name,value):
 (OUT/name).write_text(json.dumps(MessageToDict(value,preserving_proto_field_name=True),indent=2),encoding='utf-8')

async def main():
 baseline=json.loads((OUT/'latest-baseline-snapshot.json').read_text())
 original=ParseDict(baseline['configuration_values']['current'],pb.ExperimentConfiguration())
 saved=(OUT/'latest-baseline-history.json').read_bytes()
 history=Path('config/last_configuration.json')
 assert history.read_bytes()==saved, 'history changed; preserve it'
 endpoint=_existing_endpoint(default_runtime_root())
 assert endpoint.controller_generation != baseline['controller_generation']
 store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
 principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,16777216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    save('recovery-before.json',client.snapshot)
    prompt=next(p for p in client.snapshot.prompts if 'recover' in p.permitted_choices)
    assert prompt.setup.controller_generation==baseline['controller_generation']
    assert prompt.setup.session_id=='76f65fbf-f9b5-4f3c-ba9d-df1d7fbe86aa'
    result=await asyncio.wait_for(client.execute('RespondToPrompt',rpc.PromptResponse(command=client.operator_command(),prompt_id=prompt.prompt_id,setup=prompt.setup,setup_operation=prompt.operation,choice='recover')),120)
    print('preserving_recovery',asdict(result),flush=True)
    assert result.succeeded
    await asyncio.wait_for(client._wait(lambda s:s.session.phase==pb.SESSION_PHASE_CONFIGURATION and not s.prompts),30)
    assert not client.snapshot.session.HasField('context')
    assert client.snapshot.controller_generation==endpoint.controller_generation
    assert history.read_bytes()==saved, 'history changed; preserve it'
    if client.snapshot.configuration_values.current!=original:
     result=await client.execute('UpdateConfiguration',rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=original))
     print('restore_configuration',asdict(result),flush=True)
     assert result.succeeded
    assert client.snapshot.configuration_values.current==original
    assert history.read_bytes()==saved
    save('recovery-restored.json',client.snapshot)
    result={'preserved_failed_session':prompt.setup.session_id,'runtime_equal':True,'history_bytes_equal':True,'history_sha256':hashlib.sha256(saved).hexdigest(),'prior_unknown_closure_not_upgraded':True}
    (OUT/'recovery-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
 finally:
  store.remove_client(principal)
asyncio.run(main())
