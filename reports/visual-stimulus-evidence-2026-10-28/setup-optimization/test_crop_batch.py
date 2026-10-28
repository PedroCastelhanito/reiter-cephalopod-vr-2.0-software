"""Owner-authorized 600-image Setup, bounded240-second playback, then Abort and cleanup."""
import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from google.protobuf.json_format import MessageToDict, ParseDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.gui.protocol_snapshot import validate_protocol
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).parent / 'crop-batch'
OUT.mkdir(exist_ok=True)
PROTOCOL = Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json')


def record(kind, value):
    item = dict(host_ns=time.perf_counter_ns(), kind=kind, value=value)
    with (OUT / 'events.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(item)+'\n')
    print(json.dumps(item), flush=True)


def save(name, snapshot):
    (OUT / name).write_text(json.dumps(MessageToDict(snapshot,
        preserving_proto_field_name=True), indent=2), encoding='utf-8')


async def main():
    raw = PROTOCOL.read_bytes()
    document = validate_protocol(json.loads(raw))
    assert len(document['trials']) == 1
    assets = document['trials'][0]['program']['assets']
    assert len(assets) == 600 and all(a['color_override']['transfer']=='linear' for a in assets)
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client('cli')
    last = None

    def observe(snapshot):
        nonlocal last
        key = (snapshot.session.phase, snapshot.session.cleanup_confirmed,
               tuple((o.command, o.progress, o.complete) for o in snapshot.operations))
        if key != last:
            last = key
            record('state', dict(phase=pb.SessionPhase.Name(snapshot.session.phase),
                cleanup=snapshot.session.cleanup_confirmed,
                operations=[dict(command=o.command,progress=o.progress,complete=o.complete) for o in snapshot.operations]))

    try:
        async with loopback_channel(50051, 67_108_864) as channel:
            client = HeadlessClient(channel, principal, on_snapshot=observe)
            async with client.control(takeover=True):
                assert client.snapshot.controller_generation == endpoint.controller_generation
                assert all(hasattr(client.stub, method) for method in ('Setup','StartSession','AbortNow','CancelSetup','UpdateConfiguration'))
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert client.snapshot.session.cleanup_confirmed or not client.snapshot.session.HasField('context')
                save('before.json', client.snapshot)
                original = ParseDict(json.loads((Path(__file__).parent/'crop-live-final'/'before.json').read_text(encoding='utf-8'))['configuration_values']['current'], pb.ExperimentConfiguration())
                candidate = pb.ExperimentConfiguration.FromString(original.SerializeToString())
                candidate.mode = pb.SESSION_MODE_OPEN_LOOP
                candidate.asset_root = document['asset_root']
                del candidate.trials[:]
                del candidate.gaps[:]
                for number, draft in enumerate(document['trials'], 1):
                    trial = candidate.trials.add(trial_number=number)
                    trial.stimulus.program.program_json = json.dumps(draft['program'])
                    if draft['path']:
                        trial.stimulus.program.logical_source_reference = draft['path']
                    if draft['stimulus_seed_decimal']:
                        trial.stimulus.stimulus_seed_decimal = draft['stimulus_seed_decimal']
                    trial.stimulus.arena_boundaries.boundaries_json = draft['arena_boundaries_json'] or '{"format_version":1,"bindings":[]}'
                    if draft['gap_after_seconds']:
                        candidate.gaps.add(after_trial_number=number, minimum_duration_ns=int(Decimal(draft['gap_after_seconds'])*1_000_000_000))
                for backend in candidate.backends:
                    if backend.backend_name != 'visual_stimulus':
                        backend.enabled = False
                record('protocol', dict(path=str(PROTOCOL),sha256=hashlib.sha256(raw).hexdigest()))
                applied = await asyncio.wait_for(client.execute('UpdateConfiguration', rpc.UpdateConfigurationRequest(
                    command=client.operator_command(), expected_revision=client.snapshot.configuration.revision,
                    proposed=candidate)), 60)
                record('apply', asdict(applied))
                assert applied.succeeded, applied
                save('applied.json', client.snapshot)
                try:
                    setup = await asyncio.wait_for(client.execute('Setup'), 1200)
                    record('setup', asdict(setup))
                    save('setup.json', client.snapshot)
                    assert setup.succeeded, setup
                    started = await asyncio.wait_for(client.execute('StartSession'), 60)
                    record('start', asdict(started))
                    assert started.succeeded, started
                    for second in range(240):
                        await asyncio.sleep(1)
                        if second % 20 == 0:
                            record('playback', dict(second=second,phase=pb.SessionPhase.Name(client.snapshot.session.phase)))
                        assert client.snapshot.session.phase in (pb.SESSION_PHASE_RUNNING,pb.SESSION_PHASE_STARTING), pb.SessionPhase.Name(client.snapshot.session.phase)
                    save('running.json',client.snapshot)
                finally:
                    if client.snapshot.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                        cancelled = await asyncio.wait_for(client.execute('CancelSetup') if client.snapshot.session.phase == pb.SESSION_PHASE_READY else client.cancel_current_work(), 60)
                        record('cancel', asdict(cancelled))
                    await asyncio.wait_for(client._wait(lambda s:
                        s.session.phase == pb.SESSION_PHASE_CONFIGURATION and s.session.cleanup_confirmed), 60)
                    save('after-cleanup.json', client.snapshot)
                    record('cleanup', dict(confirmed=client.snapshot.session.cleanup_confirmed))
                    restored = await asyncio.wait_for(client.execute('UpdateConfiguration', rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=original)), 60)
                    record('restore', asdict(restored))
                    assert restored.succeeded, restored
    finally:
        store.remove_client(principal)


asyncio.run(main())

