import asyncio
import dataclasses
import json
from pathlib import Path

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    out = Path(__file__).parent
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client('cli')
    try:
        async with loopback_channel(50051, 16777216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                state = await client.get_snapshot()
                assert state.session.phase == pb.SESSION_PHASE_CONFIGURATION and not state.prompts
                baseline = pb.ExperimentConfiguration.FromString((out / 'burst/run-original.pb').read_bytes())
                assert state.configuration_values.current == baseline
                proposed = pb.ExperimentConfiguration.FromString(baseline.SerializeToString())
                acquisition = next(b.acquisition for b in proposed.backends if b.backend_name == 'acquisition')
                acquisition.recording_queue_frames = 17
                result = await client.execute('UpdateConfiguration', rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=state.configuration.revision, proposed=proposed))
                assert result.succeeded and client.snapshot.configuration_values.current == proposed
                (out / 'accepted-configuration.pb').write_bytes(proposed.SerializeToString())
                (out / 'accepted-queue.json').write_text(json.dumps({'controller_generation': endpoint.controller_generation, 'result': dataclasses.asdict(result), 'change': 'only acquisition.recording_queue_frames 10 to 17', 'baseline_preserved_except_queue': True, 'evidence': 'final-sequence/measurement-assessment.json', 'scope': 'measured burst demand times1.2; sustained guarantees not established'}, indent=2))
                print('Accepted and saved queue17; all other original experiment settings preserved', flush=True)
    finally:
        store.remove_client(principal)

asyncio.run(main())
