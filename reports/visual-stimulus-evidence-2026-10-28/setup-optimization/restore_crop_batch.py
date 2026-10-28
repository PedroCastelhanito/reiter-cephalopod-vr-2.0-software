import asyncio,json
from pathlib import Path
from dataclasses import asdict
from google.protobuf.json_format import ParseDict,MessageToDict
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import services_pb2 as rpc,types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
BASE=Path(__file__).parent
async def main():
 ep=_existing_endpoint(default_runtime_root()); store=CredentialStore(default_runtime_root(),ep.controller_generation); principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,67108864) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    assert client.snapshot.session.phase==pb.SESSION_PHASE_CONFIGURATION
    assert not client.snapshot.session.HasField('context') or client.snapshot.session.cleanup_confirmed
    original=ParseDict(json.loads((BASE/'crop-live-final/before.json').read_text())['configuration_values']['current'],pb.ExperimentConfiguration())
    result=await asyncio.wait_for(client.execute('UpdateConfiguration',rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=original)),60)
    assert result.succeeded,result
    assert client.snapshot.configuration_values.current==original
    (BASE/'crop-batch/restored.json').write_text(json.dumps(MessageToDict(client.snapshot,preserving_proto_field_name=True),indent=2),encoding='utf-8')
    (BASE/'crop-batch/restore-result.json').write_text(json.dumps(asdict(result),indent=2),encoding='utf-8')
    print(result,flush=True)
 finally:store.remove_client(principal)
asyncio.run(main())
