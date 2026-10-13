import asyncio
import json
from pathlib import Path
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.control.v1 import types_pb2 as pb

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client('cli')
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            state = await HeadlessClient(channel, principal).get_snapshot()
        settings = next(b.acquisition for b in state.configuration_values.current.backends if b.backend_name == 'acquisition')
        result = {'scope':'read-only, no control claim or device commands', 'generation':state.controller_generation, 'phase':pb.SessionPhase.Name(state.session.phase), 'revision':state.configuration.revision, 'roles':{role:{'serial':getattr(settings,role).device.device_id,'enabled':getattr(settings,role).enabled,'pin':getattr(settings.pulses,role).pin} for role in ('behavioral','tracking','eye_tracking')}, 'control_holder_role':None}
        if state.control.holder_client_id:
            holder = store.lookup(state.control.holder_client_id)
            result['control_holder_role'] = holder.role if holder else 'unknown'
        saved = Path('config/runtime_gui.json')
        if saved.exists():
            data = json.loads(saved.read_text(encoding='utf-8'))
            result['local_gui_roles'] = [{'serial':c['serial'],'role':c['role'],'enabled':c['enabled']} for c in data['experiment']['cameras']]
        Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result),flush=True)
    finally:
        store.remove_client(principal)

asyncio.run(main())
