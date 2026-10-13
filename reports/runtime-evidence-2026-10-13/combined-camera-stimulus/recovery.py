"""Inspect/reconcile only this diagnostic's exact failed session."""
import asyncio
import dataclasses
import json
from pathlib import Path
import sys
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
OUT=Path(__file__).parent
async def main():
    endpoint=_existing_endpoint(default_runtime_root())
    store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
    principal=store.provision_client('cli')
    try:
        async with loopback_channel(50051,16777216) as channel:
            client=HeadlessClient(channel,principal)
            async with client.control(takeover=True):
                s=client.snapshot
                context=dict(generation=s.controller_generation,session=MessageToDict(s.session,preserving_proto_field_name=True),prompts=[MessageToDict(p,preserving_proto_field_name=True) for p in s.prompts])
                print(json.dumps(context,indent=2),flush=True)
                (OUT/'recovery-state.json').write_text(json.dumps(context,indent=2))
                if sys.argv[1]=='inspect': return
                known=[json.loads((OUT/name).read_text())['checks']['setup_state']['session']['context'] for name in ('context-bind-combined.json','thread-off-handoff-failed.json','ready-scope-start-failed.json','unlocked-start-failed.json','native-copy-repeat-failed.json','early-off-probe-failed.json','boundary-fixed-repeat-cleanup-failed.json')]
                for prompt in s.prompts:
                    if not any(prompt.setup.session_id==item['session_id'] and prompt.setup.controller_generation==item['controller_generation'] for item in known):
                        raise RuntimeError('Prompt is not this exact failed diagnostic session')
                    outcome=await client.execute('RespondToPrompt',rpc.PromptResponse(command=client.operator_command(),prompt_id=prompt.prompt_id,setup=prompt.setup,setup_operation=prompt.operation,choice='continue'))
                    print('recovery',json.dumps(dataclasses.asdict(outcome)),flush=True)
                    if not outcome.succeeded: raise RuntimeError(outcome.failure)
                if client.snapshot.session.phase!=pb.SESSION_PHASE_CONFIGURATION: raise RuntimeError('Configuration required before restore')
                original=pb.Snapshot.FromString((OUT/'before.pb').read_bytes()).configuration_values.current
                outcome=await client.execute('UpdateConfiguration',rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=original))
                print('restoration',json.dumps(dataclasses.asdict(outcome)),flush=True)
                print('configuration_equal',client.snapshot.configuration_values.current==original,flush=True)
    finally: store.remove_client(principal)
asyncio.run(main())
