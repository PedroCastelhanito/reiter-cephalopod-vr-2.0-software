"""Bounded native trial/end/abort check with independent SpikeGLX samples."""
import asyncio
import ctypes as ct
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.synchronization.diagnostic import _load_sdk, _sdk_package, _required

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
events = []
stop = threading.Event()
chunks = []
sampler = {}

def record(kind, value):
    events.append({'host_monotonic_ns': time.perf_counter_ns(), 'kind': kind, 'value': value})
    (OUT / 'trial-events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
    print(kind + ': ' + json.dumps(value), flush=True)

def save(name, value):
    (OUT / name).write_text(json.dumps(MessageToDict(value, preserving_proto_field_name=True), indent=2), encoding='utf-8')

def collect():
    sdk = _load_sdk(_sdk_package(ROOT)); h = sdk.c_sglx_createHandle()
    try:
        _required(sdk.c_sglx_connect(h, b'169.254.240.108', 4142), sdk, h, 'connect')
        factor = ct.c_double()
        _required(sdk.c_sglx_getStreamI16ToVolts(ct.byref(factor), h, 1, 0, 0), sdk, h, 'volts')
        sampler.update(sample_rate=sdk.c_sglx_getStreamSampleRate(h, 1, 0), volts_per_int16=factor.value, stream='onebox', stream_index=0, channel=0)
        channels = (ct.c_int * 1)(0)
        while not stop.is_set():
            p = ct.POINTER(ct.c_short)(); n = ct.c_int()
            head = sdk.c_sglx_fetchLatest(ct.byref(p), ct.byref(n), h, 1, 0, 30000, channels, 1, 1)
            assert head > 0 and n.value > 0, (head, n.value, sdk.c_sglx_getError(h))
            chunks.append((time.perf_counter_ns(), head, np.ctypeslib.as_array(p, shape=(n.value,)).copy()))
            stop.wait(.2)
    except Exception as exc:
        sampler['error'] = repr(exc)
    finally:
        sdk.c_sglx_close(h); sdk.c_sglx_destroyHandle(h)
        np.savez_compressed(OUT / 'onebox0-channel0.npz', host_ns=np.array([x[0] for x in chunks],dtype=np.int64), heads=np.array([x[1] for x in chunks],dtype=np.uint64), values=np.stack([x[2] for x in chunks]) if chunks else np.empty((0,0)))
        (OUT / 'sampler.json').write_text(json.dumps(sampler, indent=2), encoding='utf-8')

async def command(client, name, request=None):
    result = await asyncio.wait_for(client.execute(name, request), 90)
    record(name, asdict(result))
    assert result.succeeded, result

async def update(client, config):
    await command(client, 'UpdateConfiguration', rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=config))

async def run():
    root = default_runtime_root(); endpoint = _existing_endpoint(root)
    assert endpoint.controller_generation == '128c64c4-47ea-4fbb-9a42-919c225145e4'
    store = CredentialStore(root, endpoint.controller_generation); principal = store.provision_client('cli')
    saved_path = ROOT / 'config/last_configuration.json'; saved_bytes = saved_path.read_bytes()
    (OUT / 'operator-saved-before.json').write_bytes(saved_bytes)
    thread = threading.Thread(target=collect, daemon=True); thread.start()
    try:
        async with loopback_channel(50051,16777216) as ch:
            client = HeadlessClient(ch,principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                original = pb.ExperimentConfiguration.FromString(client.snapshot.configuration_values.current.SerializeToString())
                save('operator-runtime-before.json',original)
                try:
                    for label, abort in (('normal',False),('abort',True)):
                        candidate = pb.ExperimentConfiguration.FromString(original.SerializeToString())
                        candidate.subject = 'PULSETEST'; candidate.experiment = 'trial_signal_' + label
                        folder = OUT / 'recordings'; folder.mkdir(exist_ok=True)
                        candidate.recording_root = str(folder)
                        del candidate.trials[1:]; del candidate.gaps[:]
                        program = json.loads(candidate.trials[0].stimulus.program.program_json)
                        group = program['sequence'][0]
                        assert group['kind'] == 'group'
                        group['repetitions'] = 1
                        group['body'] = [group['body'][0]]
                        group['body'][0]['duration'] = {'kind':'fixed','duration':{'seconds':'60'}}
                        program['sequence'] = [group]
                        candidate.trials[0].stimulus.program.program_json = json.dumps(program)
                        next(b for b in candidate.backends if b.backend_name == 'synchronization').enabled = False
                        await update(client,candidate)
                        await command(client,'Setup')
                        save(label+'-ready.json',client.snapshot)
                        record(label+'_ready',MessageToDict(client.snapshot.microcontroller,preserving_proto_field_name=True))
                        await asyncio.sleep(2)
                        await command(client,'StartSession')
                        await asyncio.wait_for(client._wait(lambda s:s.session.phase==pb.SESSION_PHASE_RUNNING),20)
                        save(label+'-running.json',client.snapshot)
                        record(label+'_running',MessageToDict(client.snapshot.trial,preserving_proto_field_name=True))
                        if abort:
                            await asyncio.sleep(4)
                            await command(client,'AbortNow')
                        await asyncio.wait_for(client._wait(lambda s:s.session.phase==pb.SESSION_PHASE_ENDED and s.session.cleanup_confirmed),100)
                        save(label+'-ended.json',client.snapshot)
                        record(label+'_ended',MessageToDict(client.snapshot.microcontroller,preserving_proto_field_name=True))
                        await asyncio.sleep(2)
                        await command(client,'NewSession')
                finally:
                    if client.snapshot.session.phase in (pb.SESSION_PHASE_STARTING,pb.SESSION_PHASE_RUNNING):
                        await command(client,'AbortNow')
                    if client.snapshot.session.phase == pb.SESSION_PHASE_FINALIZING:
                        await asyncio.wait_for(client._wait(lambda s:s.session.phase==pb.SESSION_PHASE_ENDED and s.session.cleanup_confirmed),90)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_ENDED and client.snapshot.session.cleanup_confirmed:
                        await command(client,'NewSession')
                    if client.snapshot.session.phase in (pb.SESSION_PHASE_SETTING_UP,pb.SESSION_PHASE_READY):
                        await command(client,'CancelSetup')
                    save('verification-final-state.json',client.snapshot)
                    if client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION:
                        await update(client,original)
                        assert client.snapshot.configuration_values.current == original
                        if json.loads(saved_path.read_bytes()).get('configuration') == json.loads(saved_bytes).get('configuration'):
                            saved_path.write_bytes(saved_bytes)
                        record('restoration',{'runtime_equal':True,'saved_bytes_equal':saved_path.read_bytes()==saved_bytes})
    except Exception as exc:
        record('error',repr(exc)); raise
    finally:
        stop.set(); thread.join(timeout=10)
        store.remove_client(principal)

if __name__ == '__main__':
    asyncio.run(run())
