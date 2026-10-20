"""Owner-authorized, digest-pinned upload through the managed controller."""
import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent
IMAGE = OUT / 'firmware/cephvr2_mcu.ino.hex'
data = {'authorization': 'Owner explicitly authorized protocol6 upload to COM8 after cleanup and trial verification, 2026-10-20.'}

def record(key, value):
    data[key] = value
    (OUT / 'deployment.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(key + ': ' + json.dumps(value), flush=True)

def view(value):
    return MessageToDict(value, preserving_proto_field_name=True)

async def run():
    assert hashlib.sha256(IMAGE.read_bytes()).hexdigest() == 'abf43ffb37d6129c78b7be5d2daba2f133700f0f71b9d2126d15253d10defa36'
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client('cli')
    try:
        async with loopback_channel(50051, 16777216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                record('controller_generation', endpoint.controller_generation)
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                for prompt in tuple(client.snapshot.prompts):
                    assert prompt.setup.controller_generation == '3fdf6ced-0c03-44f7-b02a-08f634f18b49'
                    assert 'recover' in prompt.permitted_choices
                    record('recovery_prompt', view(prompt))
                    outcome = await client.execute('RespondToPrompt', rpc.PromptResponse(
                        command=client.operator_command(), prompt_id=prompt.prompt_id,
                        setup=prompt.setup, setup_operation=prompt.operation, choice='recover'))
                    record('recovery', asdict(outcome))
                    assert outcome.succeeded
                state = await client.get_snapshot()
                (OUT / 'clean-configuration.json').write_text(json.dumps(view(state), indent=2), encoding='utf-8')
                assert state.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert not state.prompts
                acquisition = next(b.acquisition for b in state.configuration_values.current.backends if b.backend_name == 'acquisition')
                assert acquisition.pulses.port == 'COM8'
                assert not state.microcontroller.cleanup_pending
                record('upload', await dispatch_device_action(client, 'mcu_upload', {'path': str(IMAGE)}, principal))
                state = await client.get_snapshot()
                record('microcontroller', view(state.microcontroller))
                record('operations', [view(op) for op in state.operations])
                record('spikeglx_connection', await dispatch_device_action(client, 'spikeglx_connection', {}, principal))
    except Exception as exc:
        record('error', repr(exc))
        raise
    finally:
        store.remove_client(principal)

asyncio.run(run())
