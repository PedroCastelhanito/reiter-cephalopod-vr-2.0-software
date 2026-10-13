"""Bounded managed workflow audit; preserve settings and report real outcomes."""
import argparse
import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.gui.managed_device_commands import dispatch_device_action
from cephvr.gui.managed_display_operations import (
    capture_display_calibration_intent, open_display_calibration_request,
    close_display_calibration_request, update_display_calibration_request,
)
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.visual_stimulus.v1.messages_pb2 import DisplayCalibrationAdjustment

OUT = Path(__file__).parent.resolve()
parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['calibration', 'cameras', 'protocol', 'stimulus', 'restore', 'recover', 'shutdown'])
args = parser.parse_args()
result = {'method': 'authenticated managed controller; real hardware; no firmware upload', 'checks': {}}

def keep(name, value):
    result['checks'][name] = value
    (OUT / (args.mode + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(name, json.dumps(value), flush=True)

def view(s):
    return {name: MessageToDict(getattr(s, name), preserving_proto_field_name=True)
            for name in ('session','trial','configuration','acquisition_devices','visual_stimulus_display','reservation')} | {
                name: [MessageToDict(v, preserving_proto_field_name=True) for v in getattr(s, name)]
                for name in ('errors','warnings','prompts','metadata','recoveries')}

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    if endpoint is None:
        raise RuntimeError('No endpoint')
    result['controller_generation'] = endpoint.controller_generation
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client('cli')
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                s = client.snapshot
                keep('before', view(s))
                original = pb.ExperimentConfiguration.FromString(s.configuration_values.current.SerializeToString())
                (OUT / (args.mode + '-before.pb')).write_bytes(s.SerializeToString())
                if args.mode == 'shutdown':
                    keep('shutdown', dataclasses.asdict(await client.execute('ShutdownApplication')))
                    return
                if args.mode == 'recover':
                    prior = pb.Snapshot.FromString((OUT / 'protocol-before.pb').read_bytes())
                    failed = json.loads((OUT / 'protocol.json').read_text())['checks']['setup_state']['session']['context']['session_id']
                    prompt = next(p for p in s.prompts if p.setup.session_id == failed and p.setup.controller_generation == prior.controller_generation)
                    keep('recovery', dataclasses.asdict(await client.execute('RespondToPrompt', rpc.PromptResponse(command=client.operator_command(), prompt_id=prompt.prompt_id, setup=prompt.setup, setup_operation=prompt.operation, choice='continue'))))
                    keep('after', view(client.snapshot))
                    return
                if s.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    raise RuntimeError('Configuration required; existing work preserved')
                if args.mode == 'restore':
                    baseline = pb.Snapshot.FromString((OUT / 'cameras-before.pb').read_bytes()).configuration_values.current
                    keep('restore', dataclasses.asdict(await client.execute('UpdateConfiguration', rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=baseline))))
                    keep('configuration_restored', client.snapshot.configuration_values.current == baseline)
                    return
                if args.mode == 'calibration':
                    root = Path(original.asset_root)
                    arena = root / 'calibration/rig_geometry_grid.glb'
                    try:
                        intent = capture_display_calibration_intent(s, arena_path=str(arena))
                        request = open_display_calibration_request(client, **intent)
                        opened = await asyncio.wait_for(client.execute('OpenDisplayCalibration', request), 90)
                        keep('normal_open', dataclasses.asdict(opened))
                        if opened.succeeded:
                            keep('normal_active', view(client.snapshot))
                            await asyncio.sleep(3)
                            keep('normal_close', dataclasses.asdict(await client.execute('CloseDisplayCalibration', close_display_calibration_request(client, expected_revision=client.snapshot.configuration.revision, diagnostic_id=request.diagnostic_id))))
                            return
                    except Exception as exc:
                        keep('normal_error', f'{type(exc).__name__}: {exc}')
                    # Independent current accepted profile; do not rewrite the normal bundle.
                    profile = json.loads(next(b.visual_stimulus.display.profile_json for b in original.backends if b.backend_name == 'visual_stimulus'))
                    profile['calibration_view'] = 'frame_grid'
                    path = root / 'calibration/workflow_audit_profile_20261013.json'
                    raw = json.dumps(profile, indent=2).encode()
                    if path.exists() and path.read_bytes() != raw:
                        raise RuntimeError('Audit profile collision')
                    path.write_bytes(raw)
                    (OUT / 'audit-profile.json').write_bytes(raw)
                    request = rpc.OpenDisplayCalibrationRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, diagnostic_id=str(uuid4()), profile_asset_reference=path.relative_to(root).as_posix(), arena_asset_reference=arena.relative_to(root).as_posix(), expected_profile_sha256=hashlib.sha256(raw).hexdigest(), expected_arena_sha256=hashlib.sha256(arena.read_bytes()).hexdigest())
                    try:
                        opened = await asyncio.wait_for(client.execute('OpenDisplayCalibration', request), 90)
                        keep('accepted_profile_open', dataclasses.asdict(opened))
                        if opened.succeeded:
                            keep('accepted_profile_active', view(client.snapshot))
                            for sequence, coords in ((1,[.05,.05,.95,.05,.05,.95,.95,.95]),(2,[0,0,1,0,0,1,1,1])):
                                values = tuple(DisplayCalibrationAdjustment(mapping_id=m['mapping_id'], destination_xy=coords).SerializeToString() for m in profile['mappings'])
                                update = update_display_calibration_request(client, expected_revision=client.snapshot.configuration.revision, diagnostic_id=request.diagnostic_id, adjustment_sequence=sequence, adjustments=values)
                                keep(f'update_{sequence}', dataclasses.asdict(await client.execute('UpdateDisplayCalibration',update)))
                                await asyncio.sleep(2)
                    finally:
                        s = client.snapshot
                        if s.visual_stimulus_display.HasField('calibration') and s.visual_stimulus_display.calibration.diagnostic_id == request.diagnostic_id:
                            keep('close', dataclasses.asdict(await client.execute('CloseDisplayCalibration', close_display_calibration_request(client, expected_revision=s.configuration.revision, diagnostic_id=request.diagnostic_id))))
                    keep('after', view(client.snapshot))
                    keep('configuration_unchanged', client.snapshot.configuration_values.current == original)
                    return
                if args.mode == 'cameras':
                    acquisition = next(b.acquisition for b in original.backends if b.backend_name == 'acquisition')
                    cameras = [(role, getattr(acquisition, field).device.device_id) for role, field in ((1,'behavioral'),(2,'tracking'),(3,'eye_tracking')) if getattr(acquisition, field).enabled]
                    keep('enabled_cameras', cameras)
                    keep('identity', await dispatch_device_action(client,'test_cameras',{'cameras':cameras},principal))
                    for role, serial in cameras:
                        try:
                            keep(serial+'_start', await dispatch_device_action(client,'camera',{'role':role,'kind':rpc.CAMERA_COMMAND_KIND_START_PREVIEW,'show_preview':True},principal))
                            await asyncio.sleep(3)
                            keep(serial+'_running', view(client.snapshot))
                        except Exception as exc:
                            keep(serial+'_error', f'{type(exc).__name__}: {exc}')
                        finally:
                            state = client.snapshot
                            device = getattr(state.acquisition_devices, {1:'behavioral',2:'tracking',3:'eye_tracking'}[role])
                            if device.preview_run_id or device.device_open or device.cleanup_pending:
                                try:
                                    keep(serial+'_stop', await dispatch_device_action(client,'camera',{'role':role,'kind':rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW},principal))
                                except Exception as exc:
                                    keep(serial+'_cleanup_error', f'{type(exc).__name__}: {exc}')
                                    break
                    keep('after', view(client.snapshot))
                    keep('configuration_unchanged', client.snapshot.configuration_values.current == original)
                    return
                candidate = pb.ExperimentConfiguration.FromString(original.SerializeToString())
                candidate.subject = 'DUMMY'
                candidate.experiment = 'workflow_audit_' + args.mode
                candidate.recording_root = str(OUT / 'recordings')
                Path(candidate.recording_root).mkdir(exist_ok=True)
                candidate.mode = pb.SESSION_MODE_OPEN_LOOP
                del candidate.trials[1:]
                del candidate.gaps[:]
                program = json.loads(candidate.trials[0].stimulus.program.program_json)
                for epoch, duration in zip(program['sequence'], ('5','20','35'), strict=True):
                    epoch['duration']['duration']['seconds'] = duration
                candidate.trials[0].stimulus.program.program_json = json.dumps(program)
                candidate.trials[0].stimulus.stimulus_seed_decimal = '20261013'
                for b in candidate.backends:
                    if b.backend_name in ('tracking','synchronization'):
                        b.enabled = False
                    if b.backend_name == 'acquisition' and args.mode == 'stimulus':
                        b.enabled = False
                    if b.backend_name == 'visual_stimulus':
                        b.enabled = True
                        b.visual_stimulus.save_visual_stimulus_data = True
                (OUT / (args.mode+'-candidate.pb')).write_bytes(candidate.SerializeToString())
                async def update(value):
                    return await client.execute('UpdateConfiguration',rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=value))
                try:
                    accepted = await update(candidate)
                    keep('configuration', dataclasses.asdict(accepted))
                    if not accepted.succeeded:
                        return
                    setup = await asyncio.wait_for(client.execute('Setup'), 100)
                    keep('setup', dataclasses.asdict(setup))
                    keep('setup_state', view(client.snapshot))
                    if not setup.succeeded:
                        return
                    start = await asyncio.wait_for(client.execute('StartSession'), 45)
                    keep('start', dataclasses.asdict(start))
                    if start.succeeded:
                        for _ in range(80):
                            await asyncio.sleep(1)
                            if client.snapshot.session.phase == pb.SESSION_PHASE_ENDED:
                                break
                        else:
                            keep('abort_timeout', dataclasses.asdict(await client.execute('AbortNow')))
                    keep('final', view(client.snapshot))
                    (OUT / (args.mode+'-final.pb')).write_bytes(client.snapshot.SerializeToString())
                finally:
                    phase = client.snapshot.session.phase
                    if phase == pb.SESSION_PHASE_SETTING_UP:
                        keep('cancel_setup',dataclasses.asdict(await client.execute('CancelSetup')))
                    elif phase in (pb.SESSION_PHASE_READY,pb.SESSION_PHASE_ENDED):
                        keep('new_session',dataclasses.asdict(await client.execute('NewSession')))
                    if client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION:
                        keep('restore',dataclasses.asdict(await update(original)))
                        keep('configuration_restored',client.snapshot.configuration_values.current == original)
    except Exception as exc:
        keep('error', f'{type(exc).__name__}: {exc}')
        raise
    finally:
        store.remove_client(principal)

asyncio.run(main())
