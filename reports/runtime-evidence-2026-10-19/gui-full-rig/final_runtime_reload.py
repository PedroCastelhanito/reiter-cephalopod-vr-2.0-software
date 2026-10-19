"""One idle-only supported source reload; no device or trial actions."""
import asyncio
import dataclasses
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent
FILES = ('config/last_configuration.json', 'config/runtime_gui.json')

async def main(stage):
    runtime_root = default_runtime_root()
    endpoint = _existing_endpoint(runtime_root)
    store = CredentialStore(runtime_root, endpoint.controller_generation)
    principal = store.provision_client('cli')
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                view = client.snapshot
                snapshot = MessageToDict(view, preserving_proto_field_name=True)
                (OUT / f'final-reload-{stage}-snapshot.json').write_text(json.dumps(snapshot, indent=2)+'\n')
                assert view.session.phase == pb.SESSION_PHASE_CONFIGURATION, 'Active session preserved; reload refused'
                for role in ('behavioral', 'tracking', 'eye_tracking'):
                    camera = getattr(view.acquisition_devices, role)
                    assert not (camera.device_open or camera.preview_running or camera.cleanup_pending), f'{role} not idle'
                remote = await client.stub.CheckSpikeGLXConnection(
                    rpc.SpikeGLXConnectionQuery(client_id=principal.generation),
                    metadata=principal.metadata(), timeout=8,
                )
                remote_data = MessageToDict(remote, preserving_proto_field_name=True)
                assert remote.connected and not remote.running and not remote.error, remote_data
                data = {'utc':datetime.now(timezone.utc).isoformat(), 'controller_generation':view.controller_generation,
                        'session':snapshot['session'], 'spikeglx':remote_data}
                if stage == 'before':
                    for name in FILES:
                        (OUT / ('final-reload-before-'+Path(name).name)).write_bytes(Path(name).read_bytes())
                    outcome = await asyncio.wait_for(client.execute('ShutdownApplication'), 40)
                    data['shutdown'] = dataclasses.asdict(outcome)
                    assert outcome.succeeded, outcome
                    (OUT/'final-reload-before.json').write_text(json.dumps(data,indent=2)+'\n')
                else:
                    before = json.loads((OUT/'final-reload-before-snapshot.json').read_text())
                    assert snapshot['configuration_values']['current'] == before['configuration_values']['current'], 'Authoritative settings changed'
                    assert view.controller_generation != before['controller_generation'], 'Generation did not change'
                    data['authoritative_configuration_equal'] = True
                    data['before_controller_generation'] = before['controller_generation']
                    data['saved_configuration'] = {}
                    for name in FILES:
                        prior = (OUT / ('final-reload-before-'+Path(name).name)).read_bytes()
                        path = Path(name)
                        rewritten = path.read_bytes() != prior
                        if rewritten:
                            (OUT / ('final-reload-post-save-'+path.name)).write_bytes(path.read_bytes())
                            path.write_bytes(prior)
                        data['saved_configuration'][name] = {'byte_equal':path.read_bytes()==prior,'shutdown_save_rewritten':rewritten,'sha256':hashlib.sha256(prior).hexdigest()}
                    source = Path('src/cephvr/tracking/diagnostic.py')
                    data['source_sha256'] = {str(source):hashlib.sha256(source.read_bytes()).hexdigest()}
                    data['all_cameras_closed_preview_stopped_cleanup_clear'] = True
                    (OUT/'final-runtime-reload.json').write_text(json.dumps(data,indent=2)+'\n')
                print(json.dumps(data,indent=2),flush=True)
    finally:
        store.remove_client(principal)

asyncio.run(main(sys.argv[1]))
