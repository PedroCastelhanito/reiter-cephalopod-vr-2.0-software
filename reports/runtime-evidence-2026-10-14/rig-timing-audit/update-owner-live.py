import asyncio
import dataclasses
import json
import math
from pathlib import Path

from cephvr.acquisition.config.file_policies import load_file_policies
from cephvr.acquisition.configuration import load_defaults
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.controller.configuration import _load_saved_configuration
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.visual_stimulus.resources.session import review_capture_cpu_bytes

async def main():
    out = Path(__file__).parent / 'owner-parameter-review'
    out.mkdir(exist_ok=True)
    root = Path.cwd()
    config = root / 'config/backends/acquisition_config.toml'
    history = root / 'config/last_configuration.json'
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client('cli')
    original_config = config.read_bytes()
    try:
        async with loopback_channel(50051, 16777216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                state = await client.get_snapshot()
                assert state.session.phase == pb.SESSION_PHASE_CONFIGURATION and not state.prompts
                assert not state.microcontroller.cleanup_pending
                for role in ('behavioral', 'tracking', 'eye_tracking'):
                    device = getattr(state.acquisition_devices, role)
                    assert not device.device_open and not device.preview_run_id and not device.cleanup_pending
                original = pb.ExperimentConfiguration.FromString(state.configuration_values.current.SerializeToString())
                (out / 'live-configuration.before.pb').write_bytes(original.SerializeToString())
                (out / 'acquisition_config.toml.before').write_bytes(original_config)
                (out / 'last_configuration.json.before').write_bytes(history.read_bytes())
                proposed = pb.ExperimentConfiguration.FromString(original.SerializeToString())
                acquisition = next(b.acquisition for b in proposed.backends if b.backend_name == 'acquisition')
                acquisition.recording_queue_frames = 20
                for role in ('behavioral', 'tracking', 'eye_tracking'):
                    getattr(acquisition, role).sdk_buffer_count = 15
                changed = original_config.replace(b'recording_queue_frames = 17', b'recording_queue_frames = 20')
                changed = changed.replace(b'sdk_buffer_count = 10', b'sdk_buffer_count = 15')
                changed = changed.replace(b'post_cutoff_drain_margin_ms = 125', b'post_cutoff_drain_margin_ms = 150')
                config.write_bytes(changed)
                try:
                    defaults = load_defaults(root)
                    file_policies = load_file_policies(root)
                    assert defaults.recording_queue_frames == 20
                    assert all(getattr(defaults, role).sdk_buffer_count == 15 for role in ('behavioral', 'tracking', 'eye_tracking'))
                    assert all(c.post_cutoff_drain_margin_ns == 150000000 for c in file_policies.cameras)
                    result = await client.execute('UpdateConfiguration', rpc.UpdateConfigurationRequest(command=client.operator_command(), expected_revision=state.configuration.revision, proposed=proposed))
                    assert result.succeeded and client.snapshot.configuration_values.current == proposed
                except BaseException:
                    config.write_bytes(original_config)
                    raise
                saved = await client.execute('SaveConfigurationHistory')
                assert saved.succeeded
                assert _load_saved_configuration(history, max_message_bytes=16777216) == proposed
                (out / 'accepted-configuration.pb').write_bytes(proposed.SerializeToString())
                result_record = {
                    'controller_generation': endpoint.controller_generation,
                    'updated': dataclasses.asdict(result),
                    'saved_history': dataclasses.asdict(saved),
                    'settings': {'recording_queue_frames': 20, 'sdk_buffer_count_per_camera': 15, 'post_cutoff_drain_margin_ms': 150},
                    'current_equals_proposed': True,
                    'saved_equals_proposed': True,
                    'scope': 'Configuration settings only; no Setup, recording or projector tests dispatched. SDK15/drain150/queue20 not remeasured on rig.'
                }
                (out / 'result.json').write_text(json.dumps(result_record, indent=2) + '\n')
                print(json.dumps(result_record, indent=2), flush=True)
    finally:
        store.remove_client(principal)
    width, height = 2560, 2000
    cpu_bytes = review_capture_cpu_bytes(width, height, 3)
    gpu_bytes = 703694176 - 18 * width * height * 4
    recommendation = {
        'pending_records_capacity': 10000,
        'capture_slots': 3,
        'recording_bytes_total': 268435456,
        'max_asset_gpu_bytes': 536870912,
        'cpu_accounted_bytes': cpu_bytes,
        'cpu_accounted_times_1_2': math.ceil(cpu_bytes * 1.2),
        'gpu_inferred_accounted_bytes_at3': gpu_bytes,
        'gpu_inferred_times_1_2': math.ceil(gpu_bytes * 1.2),
        'scope': 'CPU owning helper; GPU estimate uses same-assets21-slot budget accounting subtracting18 RGBA8 slots. Not a new measurement or whole-process/GPU memory estimate.',
        'throughput': '21 slots saturated;3 slots is a provisional retained bound, not validated zero-loss capacity.'
    }
    (out / 'recommendations.json').write_text(json.dumps(recommendation, indent=2) + '\n')

asyncio.run(main())
