"""Bounded managed image-only source checks; no exposure/lighting/algorithm edits."""
import asyncio
import dataclasses
import hashlib
import json
import time
from pathlib import Path

import grpc
import numpy as np
from google.protobuf.json_format import MessageToDict
from cephvr.acquisition.v1 import camera_pb2
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.tracking.v1 import services_pb2 as trpc, services_pb2_grpc as transport

OUT = Path(__file__).resolve().parent
results = []
commands = []

async def execute(client, name, request=None):
    result = await asyncio.wait_for(client.execute(name, request), 90)
    commands.append({'command': name, **dataclasses.asdict(result)})
    (OUT / 'image-diagnostic-commands.json').write_text(json.dumps(commands, indent=2))
    print(commands[-1], flush=True)
    assert result.succeeded, result

async def main():
    root = default_runtime_root()
    store = CredentialStore(root, _existing_endpoint(root).controller_generation)
    principal = store.provision_client('gui')
    saved_path = Path('config/last_configuration.json')
    saved_bytes = (OUT / 'before-last_configuration.json').read_bytes()
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                assert client.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                original = pb.ExperimentConfiguration.FromString(client.snapshot.configuration_values.current.SerializeToString())
                (OUT / 'image-diagnostic-original.json').write_text(json.dumps(MessageToDict(original, preserving_proto_field_name=True), indent=2))
                async def update(config):
                    await execute(client, 'UpdateConfiguration', rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=client.snapshot.configuration.revision, proposed=config))
                try:
                    for role in ('tracking', 'eye_tracking'):
                        candidate = pb.ExperimentConfiguration.FromString(original.SerializeToString())
                        acquisition = next(b.acquisition for b in candidate.backends if b.backend_name == 'acquisition')
                        if role == 'eye_tracking':
                            prior_tracking = acquisition.tracking.SerializeToString()
                            acquisition.tracking.CopyFrom(acquisition.eye_tracking)
                            acquisition.eye_tracking.ParseFromString(prior_tracking)
                            prior_pulse = acquisition.pulses.tracking.SerializeToString()
                            acquisition.pulses.tracking.CopyFrom(acquisition.pulses.eye_tracking)
                            acquisition.pulses.eye_tracking.ParseFromString(prior_pulse)
                        tracking = next(b for b in candidate.backends if b.backend_name == 'tracking')
                        tracking.enabled = False
                        tracking.tracking.input_camera_role = camera_pb2.CAMERA_ROLE_TRACKING
                        tracking.tracking.preprocessing.scale_percent = 100
                        tracking.tracking.preprocessing.crop_enabled = False
                        await update(candidate)
                        await execute(client, 'ExecuteCameraCommand', rpc.CameraCommandRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, camera=camera_pb2.CAMERA_ROLE_TRACKING, kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW))
                        run_id = client.snapshot.acquisition_devices.tracking.preview_run_id
                        assert run_id
                        try:
                            if role == 'tracking':
                                malformed = pb.TrackingSettings.FromString(tracking.tracking.SerializeToString())
                                malformed.preprocessing.ClearField('crop_enabled')
                                started = time.monotonic()
                                rejected = ''
                                try:
                                    await execute(client, 'BeginTrackingDiagnostic', rpc.BeginTrackingDiagnosticRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, preview_run_id=run_id, selected_stages=[], diagnostic_settings=malformed))
                                except Exception as exc:
                                    rejected = str(exc)
                                assert 'explicit crop and scale' in rejected, rejected
                                await asyncio.wait_for(client._wait(lambda state: state.tracking_diagnostic.closed and not state.tracking_diagnostic.active), 5)
                                (OUT / 'invalid-diagnostic-reuse.json').write_text(json.dumps({'error':rejected,'elapsed_s':time.monotonic()-started,'state':MessageToDict(client.snapshot.tracking_diagnostic,preserving_proto_field_name=True),'operation':MessageToDict(client.snapshot.operations[-1],preserving_proto_field_name=True)},indent=2))
                            await execute(client, 'BeginTrackingDiagnostic', rpc.BeginTrackingDiagnosticRequest(command=client.operator_command(), expected_configuration_revision=client.snapshot.configuration.revision, preview_run_id=run_id, selected_stages=[], diagnostic_settings=tracking.tracking))
                            diagnostic = client.snapshot.tracking_diagnostic
                            query = trpc.TrackingDiagnosticQuery(client_id=principal.generation, viewer=pb.ProcessIdentity(role='gui', generation=principal.generation), controller_generation=client.snapshot.controller_generation, configuration_revision=client.snapshot.configuration.revision, diagnostic_id=diagnostic.diagnostic_id, preview_run_id=run_id)
                            async with grpc.aio.insecure_channel(diagnostic.tracking_endpoint, options=(('grpc.max_receive_message_length',16_777_216),)) as peer:
                                stub = transport.TrackingDiagnosticServiceStub(peer)
                                for index in range(5):
                                    await asyncio.sleep(.5)
                                    frame = await stub.GetLatestDiagnosticFrame(query, metadata=principal.metadata(), timeout=5)
                                    assert frame.available and frame.image_bytes
                                    assert frame.image.pixel_format in ('Mono8', 'BayerRG8')
                                    pixels = np.frombuffer(frame.image_bytes,dtype=np.uint8).reshape(frame.image.height,frame.image.row_stride_bytes)[:,:frame.image.width]
                                    histogram = np.bincount(pixels.ravel(),minlength=256)
                                    path = OUT / f'{role}-native-{index}.bin'
                                    path.write_bytes(frame.image_bytes)
                                    results.append({'role':role,'sample':index,'source_frame_id':frame.source_frame_id,'source_host_receipt_ns':frame.source_host_receipt_ns,'layout':MessageToDict(frame.image,preserving_proto_field_name=True),'minimum':int(pixels.min()),'maximum':int(pixels.max()),'mean':float(pixels.mean()),'stddev':float(pixels.std()),'zero_fraction':float(histogram[0]/pixels.size),'histogram':histogram.tolist(),'sha256':hashlib.sha256(frame.image_bytes).hexdigest(),'bytes_file':str(path),'camera_settings':MessageToDict(acquisition.tracking.device,preserving_proto_field_name=True)})
                                    (OUT / 'native-image-assessment.json').write_text(json.dumps(results,indent=2))
                                    print(role,index,results[-1]['minimum'],results[-1]['maximum'],results[-1]['mean'],flush=True)
                        finally:
                            if client.snapshot.tracking_diagnostic.diagnostic_id and (client.snapshot.tracking_diagnostic.active or not client.snapshot.tracking_diagnostic.closed):
                                current = client.snapshot.tracking_diagnostic
                                await execute(client,'CloseTrackingDiagnostic',rpc.CloseTrackingDiagnosticRequest(command=client.operator_command(),expected_configuration_revision=client.snapshot.configuration.revision,diagnostic_id=current.diagnostic_id,preview_run_id=run_id))
                            await execute(client,'ExecuteCameraCommand',rpc.CameraCommandRequest(command=client.operator_command(),expected_configuration_revision=client.snapshot.configuration.revision,camera=camera_pb2.CAMERA_ROLE_TRACKING,kind=rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW,preview_run_id=run_id))
                finally:
                    await update(original)
                    assert client.snapshot.configuration_values.current == original
                    if json.loads(saved_path.read_bytes()).get('configuration') == json.loads(saved_bytes).get('configuration'):
                        saved_path.write_bytes(saved_bytes)
                    (OUT / 'image-diagnostic-restoration.json').write_text(json.dumps({'runtime_configuration_equal':True,'saved_file_byte_equal':saved_path.read_bytes()==saved_bytes,'session':MessageToDict(client.snapshot.session,preserving_proto_field_name=True)},indent=2))
    finally:
        store.remove_client(principal)

asyncio.run(main())
