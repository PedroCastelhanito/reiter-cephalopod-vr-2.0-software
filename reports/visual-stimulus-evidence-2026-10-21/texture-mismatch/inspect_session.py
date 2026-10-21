import collections
import hashlib
import json
from pathlib import Path

root = Path(r'C:\Data\projects\reiter-cephalopod-vr\cephvr-data\20261020_ephys-pilot\SP0003-145623\protocol-data')
protocol_path = Path(r'C:\Users\ReiterU_PC\Desktop\Pedro\primate_cuttlebase_20min.json')
protocol = json.loads(protocol_path.read_text())
config = json.loads((root / 'SESSION_CONFIG.json').read_text())
summary = {'inspection_date': '2026-10-21', 'session': str(root.parent), 'inspection_head': 'c740c5c2881e11b4cf7f3d835ffa7708de6fdbfb', 'provenance_limit': 'Inspection tree dirty; run records version 2.0.0.dev0 without exact source revision. Renderer selections are not optical measurements.', 'protocol_sha256': hashlib.sha256(protocol_path.read_bytes()).hexdigest(), 'trials': []}
for index, path in enumerate(sorted(root.glob('*stimulus_frames.jsonl'))):
    recipe = json.loads(path.with_name(path.name.replace('_frames.jsonl', '_LOG.json')).read_text())
    counts = collections.Counter()
    affected = set()
    per_epoch = collections.defaultdict(collections.Counter)
    examples = []
    for line in path.open():
        row = json.loads(line)['payload']
        if row['kind'] == 'header':
            start = row['trial_start_host_ns']
        if row['kind'] != 'render_group':
            continue
        counts['render_groups'] += 1
        state = row['state']
        images = state['images']
        if not images:
            continue
        counts['texture_groups'] += 1
        epoch = state['epoch_occurrence']
        per_epoch[epoch]['total'] += 1
        assert len({x['requested_asset_id'].rsplit('_', 1)[0] for x in images}) == 1
        held = any(x['asset_id'] != x['requested_asset_id'] for x in images)
        mixed = len({x['asset_id'].rsplit('_', 1)[0] for x in images}) > 1
        counts['held_groups'] += held
        counts['mixed_groups'] += mixed
        if mixed:
            affected.add(epoch)
            per_epoch[epoch]['mixed'] += 1
            if len(examples) < 1:
                examples.append({'group_id': row['group_id'], 'epoch': epoch, 'seconds': (state['evaluation_host_ns'] - start) / 1e9, 'images': images})
    planned = [e for e in recipe['epochs'] if e['settings']]
    assert all(len({s['asset_id'].rsplit('_', 1)[0] for s in e['settings']}) == 1 for e in planned)
    saved = json.loads(config['configuration']['trials'][index]['stimulus']['program']['program_json'])
    result = {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'counts': dict(counts), 'planned_texture_presentations': len(planned), 'mixed_presentations': len(affected), 'mixed_for_all_observed_groups': sum(c['mixed'] == c['total'] for c in per_epoch.values()), 'mixed_epoch_indices': sorted(affected), 'example': examples, 'saved_program_matches_desktop': saved == protocol['trials'][index]['program']}
    summary['trials'].append(result)
    print({k:v for k,v in result.items() if k not in ('mixed_epoch_indices','example')})
Path(__file__).with_name('summary.json').write_text(json.dumps(summary, indent=2) + '\n')
