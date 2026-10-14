"""Authenticated, bounded sessionless preview cycles with original settings."""
import asyncio
import dataclasses
import json
from pathlib import Path
import sys
import socket
import time
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent
async def main():
    ready_deadline = time.monotonic() + 30
    while True:
        try:
            with socket.create_connection(('127.0.0.1', 50051), timeout=.5):
                break
        except OSError:
            if time.monotonic() >= ready_deadline:
                raise RuntimeError('Controller listener did not become ready')
            await asyncio.sleep(.5)
    endpoint = _existing_endpoint(default_runtime_root())
    if endpoint is None:
        raise RuntimeError('No managed runtime')
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client('cli')
    results = []
    def keep(label, value):
        results.append(dict(label=label, value=value))
        (OUT / ('measurement-' + sys.argv[1] + '.json')).write_text(json.dumps(results, indent=2))
        print(label, json.dumps(value), flush=True)
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                if client.snapshot.session.phase != pb.SESSION_PHASE_CONFIGURATION or client.snapshot.prompts:
                    raise RuntimeError('Idle Configuration without prompts required')
                original = client.snapshot.configuration_values.current.SerializeToString()
                keep('generation', endpoint.controller_generation)
                if sys.argv[1] == 'inspect':
                    baseline = pb.Snapshot.FromString((OUT / 'before.pb').read_bytes()).configuration_values.current
                    keep('configuration_matches_baseline', client.snapshot.configuration_values.current == baseline)
                    keep('phase', pb.SessionPhase.Name(client.snapshot.session.phase))
                    keep('prompts', len(client.snapshot.prompts))
                    keep('cameras_released', {name: not getattr(client.snapshot.acquisition_devices, name).device_open and not getattr(client.snapshot.acquisition_devices, name).preview_run_id and not getattr(client.snapshot.acquisition_devices, name).cleanup_pending for name in ('behavioral','tracking')})
                    (OUT / 'measurement-restored.pb').write_bytes(client.snapshot.SerializeToString())
                    return
                if sys.argv[1] == 'shutdown':
                    keep('shutdown', dataclasses.asdict(await client.execute('ShutdownApplication')))
                    return
                acq = next(b.acquisition for b in client.snapshot.configuration_values.current.backends if b.backend_name == 'acquisition')
                cameras = [(role, getattr(acq, name).device.device_id) for role, name in ((3,'eye_tracking'),(1,'behavioral'),(2,'tracking')) if getattr(acq, name).device.device_id]
                for cycle in range(2):
                    for role, serial in cameras:
                        await asyncio.sleep(2)
                        started = False
                        try:
                            keep(f'{cycle}-{serial}-start', await asyncio.wait_for(dispatch_device_action(client, 'camera', dict(role=role, kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW, show_preview=False), principal), 40))
                            started = True
                            await asyncio.sleep(3 + (cycle % 3) * .007)
                        finally:
                            device = getattr(client.snapshot.acquisition_devices, {1:'behavioral',2:'tracking',3:'eye_tracking'}[role])
                            if device.preview_run_id or device.device_open or device.cleanup_pending:
                                keep(f'{cycle}-{serial}-stop', await asyncio.wait_for(dispatch_device_action(client, 'camera', dict(role=role, kind=rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW), principal), 40))
                        if not started:
                            raise RuntimeError('Camera failed to start')
                keep('configuration_unchanged', client.snapshot.configuration_values.current.SerializeToString() == original)
                (OUT / 'measurement-final.pb').write_bytes(client.snapshot.SerializeToString())
    finally:
        store.remove_client(principal)
asyncio.run(main())
