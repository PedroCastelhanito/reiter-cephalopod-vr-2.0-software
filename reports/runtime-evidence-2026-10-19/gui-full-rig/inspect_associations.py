"""Read-only exact mapping, resource and planned-file checks after recording."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ended = json.loads((OUT / 'endurance-ended.json').read_text())
root = Path(ended['session']['directory']) / 'protocol-data'
config = json.loads((root / 'SESSION_CONFIG.json').read_text())
trial_path = next(p for p in root.glob('*_LOG.json') if not p.name.endswith('stimulus_LOG.json'))
trial = json.loads(trial_path.read_text())
planned = {(o['output_key'], o['output_tag'], o['extension']) for o in config['outputs']}
actual = {(o['output_key'], o['output_tag'], o['extension']) for o in trial['outputs']}
assert planned == actual and len(actual) == len(config['outputs']) == 9
assert all(o['closure'] == 'OUTPUT_CLOSURE_CLOSED' and o['artifact_present'] for o in trial['outputs'])
expected = {Path(o['path']).name for o in trial['outputs']} | {trial_path.name, 'SESSION_CONFIG.json', 'SESSION_LOG.jsonl', 'SCHEMA.json'}
assert expected == {p.name for p in root.iterdir() if p.is_file()}
camera_checks = {}
for path in root.glob('*cam_frames.jsonl'):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    frames = [r for r in rows if r['type'] == 'frame']
    mappings = [r for r in rows if r['type'] == 'video_frame']
    assert [m['encoded_frame_index'] for m in mappings] == list(range(len(mappings)))
    by_id = {f['frame_id']: f for f in frames}
    assert len(by_id) == len(frames)
    seen = set()
    for mapping in mappings:
        frame = by_id[mapping['source_frame_id']]
        assert mapping['source_host_receipt_ns'] == frame['host_receipt_ns']
        assert frame['video_frame'] == mapping['encoded_frame_index']
        assert mapping['disposition'] == frame['video_disposition'] == 'real'
        assert frame['frame_id'] not in seen
        seen.add(frame['frame_id'])
    assert len(seen) == len(frames)
    gaps = [(b['camera_frame_counter'] - a['camera_frame_counter']) for a, b in zip(frames, frames[1:]) if a['camera_frame_counter'] is not None and b['camera_frame_counter'] is not None]
    host_steps = [b['host_receipt_ns'] - a['host_receipt_ns'] for a, b in zip(frames, frames[1:])]
    assert all(step >= 0 for step in host_steps)
    assert all(step == 1 for step in gaps)
    camera_checks[rows[0]['identity']['camera_role']] = {
        'source_frames': len(frames), 'video_mappings': len(mappings),
        'native_counter_steps_checked': len(gaps), 'nonunit_native_steps': sum(step != 1 for step in gaps),
        'mapping_source_id_time_disposition_and_index_equal': True,
        'first_receipt_offset_s': (frames[0]['host_receipt_ns'] - rows[0]['clocks']['trial_start_monotonic_ns']) / 1e9,
        'last_receipt_offset_s': (frames[-1]['host_receipt_ns'] - rows[0]['clocks']['trial_start_monotonic_ns']) / 1e9,
        'observed_host_receipt_fps': (len(frames)-1) * 1e9 / (frames[-1]['host_receipt_ns'] - frames[0]['host_receipt_ns']),
    }
stimulus = json.loads(next(root.glob('*stimulus_LOG.json')).read_text())
source = config['trials'][0]['definition']['stimulus']['program']['program_json']
assert hashlib.sha256(source.encode()).hexdigest() == stimulus['source_sha256']
assert json.loads(source) == stimulus['source']
resources = []
asset_root = Path(config['configuration']['asset_root']).resolve()
for resource in stimulus['manifest']['resources']:
    fingerprint = resource['fingerprint']
    path = (asset_root / fingerprint['logical_path']).resolve()
    path.relative_to(asset_root)
    assert path.stat().st_size == fingerprint['bytes']
    assert hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() == fingerprint['sha256']
    resources.append(fingerprint)
manifest_ids = {r['resource_id'] for r in resources}
assert {a['asset_id'] for a in stimulus['source']['assets']} <= manifest_ids
result = {'exact_reserved_keys_tags_extensions': True, 'all_nine_outputs_closed': True,
          'exact_protocol_directory_file_set': sorted(expected), 'cameras': camera_checks,
          'source_program_exact_and_hash_equal': True, 'manifest_resources_digest_size_and_containment_equal': resources,
          'limits': 'Native counters/host receipt prove logged stream continuity; not exposure accuracy, pulse/optical alignment, animal scene representativeness or reconstructability of external SpikeGLX contents.'}
(OUT / 'association-assessment.json').write_text(json.dumps(result, indent=2))
print(json.dumps(camera_checks, indent=2))
