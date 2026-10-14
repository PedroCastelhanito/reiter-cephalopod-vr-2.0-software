import asyncio,dataclasses,json
from pathlib import Path
from cephvr.client.session import HeadlessClient,loopback_channel
from cephvr.control.v1 import services_pb2 as rpc,types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore,default_runtime_root
async def main():
 endpoint=_existing_endpoint(default_runtime_root()); store=CredentialStore(default_runtime_root(),endpoint.controller_generation); principal=store.provision_client('cli')
 try:
  async with loopback_channel(50051,16777216) as channel:
   client=HeadlessClient(channel,principal)
   async with client.control(takeover=True):
    for _ in range(60):
     if client.snapshot.visual_stimulus_display.complete:break
     await asyncio.sleep(.5);await client.get_snapshot()
    assert client.snapshot.visual_stimulus_display.complete
    assert client.snapshot.session.phase==pb.SESSION_PHASE_CONFIGURATION
    for prompt in client.snapshot.prompts:
     print('recovery_prompt',prompt,flush=True)
     assert set(prompt.permitted_choices)=={'continue','cancel'} and prompt.setup.controller_generation in {'801a2154-e268-4095-a710-b1b0ef3c03c4','066e58dc-5ba0-4268-869a-28ead06a4d0f','964bf477-7c16-4307-97f4-2fdffd57177a','bb4c3f6a-9090-4086-b6ee-71e78616cbfd','e8f8e138-67cd-4a6d-aff1-2ccee251c0ea','4312f70c-fb4a-43bd-9c52-483908cd2603','eacf4c70-910f-4c6f-82b1-c7f8527aea56','4a1fc86b-c89f-4cb9-b12b-b760654436a0','30645d86-accc-4df3-a29b-70b12f9d9012','921dbb6e-b845-452b-9a4d-fcadd9079fb0','0de05a85-aad5-4c46-9eec-5708b8dde94e','53d8525a-060d-4c12-90c5-085443051c8c'}
     recovered=await client.execute('RespondToPrompt',rpc.PromptResponse(command=client.operator_command(),prompt_id=prompt.prompt_id,setup=prompt.setup,setup_operation=prompt.operation,choice='continue'))
     print('recovery',json.dumps(dataclasses.asdict(recovered)),flush=True)
     assert recovered.succeeded
    assert not client.snapshot.prompts
    original=pb.ExperimentConfiguration.FromString((Path(__file__).parent/'burst/run-original.pb').read_bytes())
    result=await client.execute('UpdateConfiguration',rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=original))
    print(json.dumps(dataclasses.asdict(result)),flush=True)
    assert result.succeeded and client.snapshot.configuration_values.current==original
 finally:store.remove_client(principal)
asyncio.run(main())
