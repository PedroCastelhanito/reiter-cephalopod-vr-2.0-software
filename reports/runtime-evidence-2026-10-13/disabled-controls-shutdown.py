import asyncio
import json
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.shared.recovery import RecoveryStore

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    generation = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(), generation)
    principal = store.provision_client('cli')
    result = {'generation': generation, 'scope': 'owner-requested normal runtime shutdown'}
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                saved = await client.execute('SaveConfigurationHistory')
                result['accepted_history_saved'] = saved.succeeded
                outcome = await client.execute('ShutdownApplication')
                result['shutdown_succeeded'] = outcome.succeeded
    finally:
        store.remove_client(principal)
    for _ in range(200):
        receipt = RecoveryStore(default_runtime_root()).read_exit_receipt(generation)
        if receipt is not None and receipt.all_owned_processes_absent:
            result['all_owned_processes_absent'] = True
            break
        await asyncio.sleep(.1)
    Path(__file__).with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result), flush=True)
    if not result.get('all_owned_processes_absent'):
        raise RuntimeError('Exact runtime exit not confirmed')

asyncio.run(main())
