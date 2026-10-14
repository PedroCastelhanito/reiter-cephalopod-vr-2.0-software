import json
import math
import tomllib
from pathlib import Path

from cephvr.acquisition.config.file_policies import load_file_policies
from cephvr.acquisition.configuration import load_defaults
from cephvr.controller.configuration import _load_saved_configuration, load_controller_configuration
from cephvr.controller.metadata.documents import message_dict
from cephvr.controller.metadata.files import atomic_json
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.visual_stimulus.resources.session import review_capture_cpu_bytes

root = Path.cwd()
out = Path(__file__).parent / 'owner-parameter-review'
out.mkdir(exist_ok=True)
config = root / 'config/backends/acquisition_config.toml'
history = root / 'config/last_configuration.json'

# Exclude a running or newly starting application while updating reusable settings.
with SingleInstanceGuard('application'):
    original = config.read_bytes()
    original_history = history.read_bytes()
    for name, data in [('acquisition_config.toml.before', original), ('last_configuration.json.before', original_history)]:
        target = out / name
        if not target.exists():
            target.write_bytes(data)
    saved = _load_saved_configuration(history, max_message_bytes=16777216)
    before = saved.SerializeToString()
    acquisition = next(b.acquisition for b in saved.backends if b.backend_name == 'acquisition')
    acquisition.recording_queue_frames = 20
    for role in ('behavioral', 'tracking', 'eye_tracking'):
        getattr(acquisition, role).sdk_buffer_count = 15
    revised = original.replace(b'recording_queue_frames = 17', b'recording_queue_frames = 20')
    revised = revised.replace(b'sdk_buffer_count = 10', b'sdk_buffer_count = 15')
    revised = revised.replace(b'post_cutoff_drain_margin_ms = 125', b'post_cutoff_drain_margin_ms = 150')
    parsed = tomllib.loads(revised.decode('utf-8'))
    assert parsed['buffers']['recording_queue_frames'] == 20
    for role in ('behavioral', 'tracking', 'eye_tracking'):
        assert parsed['cameras'][role]['sdk_buffer_count'] == 15
        assert parsed['cameras'][role]['post_cutoff_drain_margin_ms'] == 150
    document = {'format_version': 1, 'configuration': message_dict(saved)}
    try:
        config.write_bytes(revised)
        defaults = load_defaults(root)
        file_policies = load_file_policies(root)
        assert defaults.recording_queue_frames == 20
        assert all(getattr(defaults, role).sdk_buffer_count == 15 for role in ('behavioral', 'tracking', 'eye_tracking'))
        assert all(c.post_cutoff_drain_margin_ns == 150000000 for c in file_policies.cameras)
        atomic_json(history, json.dumps(document, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode(), replace=True)
        effective = load_controller_configuration(root)
        assert effective.history_warning is None
        loaded = next(b.acquisition for b in effective.configuration.backends if b.backend_name == 'acquisition')
        assert loaded.recording_queue_frames == 20
        assert all(getattr(loaded, role).sdk_buffer_count == 15 for role in ('behavioral', 'tracking', 'eye_tracking'))
        check = _load_saved_configuration(history, max_message_bytes=16777216)
        restore = next(b.acquisition for b in check.backends if b.backend_name == 'acquisition')
        old = type(saved).FromString(before)
        old_acquisition = next(b.acquisition for b in old.backends if b.backend_name == 'acquisition')
        restore.recording_queue_frames = old_acquisition.recording_queue_frames
        for role in ('behavioral', 'tracking', 'eye_tracking'):
            getattr(restore, role).sdk_buffer_count = getattr(old_acquisition, role).sdk_buffer_count
        assert check == old, 'Unrelated saved settings changed'
    except BaseException:
        config.write_bytes(original)
        atomic_json(history, original_history, replace=True)
        raise

width, height = 2560, 2000
frame_bytes = width * height * 4
cpu_bytes = review_capture_cpu_bytes(width, height, 3)
gpu_trial_total = 703694176
gpu_at_3 = gpu_trial_total - (21 - 3) * frame_bytes
result = {
    'user_selected': {'recording_queue_frames': 20, 'sdk_buffer_count_per_camera': 15, 'post_cutoff_drain_margin_ms': 150},
    'default_and_saved_history_verified': True,
    'all_other_saved_fields_preserved': True,
    'native_application_started': False,
    'native_retest': 'not performed; projector-dependent tests remain owner-deferred',
    'pending_records_recommendation': {'value': 10000, 'reason': 'Metadata-only backlog; normal-run peak14 does not bound a stalled writer. Keep until fault-backlog demand is measured.'},
    'visual_recommendation': {
        'capture_slots': 3,
        'recording_bytes_total': 268435456,
        'max_asset_gpu_bytes': 536870912,
        'capture_cpu_accounted_bytes': cpu_bytes,
        'capture_cpu_times_1_2_bytes': math.ceil(cpu_bytes * 1.2),
        'gpu_accounted_bytes_at_3_slots': gpu_at_3,
        'gpu_times_1_2_bytes': math.ceil(gpu_at_3 * 1.2),
        'method': 'CPU owning allocation helper; GPU inferred from same-assets21-slot total by subtracting18 RGBA8 slots. Accounting estimates, not new native measurements or whole-system RAM/VRAM.',
        'limit': '21 slots saturated in60s. No finite slot recommendation establishes steady throughput; keep3 until pipeline is repaired and measured again.'
    }
}
(out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
