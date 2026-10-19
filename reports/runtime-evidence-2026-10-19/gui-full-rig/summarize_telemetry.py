"""Summarize valid sampled utilization inside the actual controller trial interval."""
import collections
import csv
import datetime as dt
import json
import math
import os
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent
end = json.loads((OUT / 'endurance-ended.json').read_text())
directory = Path(end['session']['directory']) / 'protocol-data'
events = [json.loads(line) for line in (directory / 'SESSION_LOG.jsonl').read_text().splitlines()]
start = next(e for e in events if e['event_type'] == 'trial_started')
finish = next(e for e in events if e['event_type'] == 'trial_finished')
timestamp = lambda value: dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
low, high = timestamp(start['wall_time']), timestamp(finish['wall_time'])
rows = [json.loads(line) for line in (OUT / 'telemetry.jsonl').read_text(encoding='utf-8-sig').splitlines()]
rows.sort(key=lambda row: timestamp(row['utc']))
active = [r for r in rows if low <= timestamp(r['utc']) <= high]
assert active, 'No utilization samples inside the trial'
metrics = collections.defaultdict(list)
invalid = collections.Counter()
adapter_names = {int(a['AdapterLuid']): a['Description'] for a in json.loads((OUT / 'adapter-map.json').read_text(encoding='utf-8-sig'))}
for row in active:
    metrics['CPU host percent'].extend(row['cpu_percent'])
    for line in row['nvidia_csv']:
        fields = next(csv.reader([line], skipinitialspace=True))
        name = fields[2]
        for index, key in ((5, 'GPU percent'), (6, 'encoder percent'), (7, 'decoder percent'), (8, 'memory MiB'), (9, 'power W'), (10, 'temperature C')):
            try:
                metrics[name + ' ' + key].append(float(fields[index]))
            except ValueError:
                invalid[name + ' ' + key] += 1
    engines = collections.defaultdict(float)
    for engine in row['engines']:
        match = re.search(r'luid_0x([0-9a-f]+)_0x([0-9a-f]+)_(phys_\d+_eng_\d+_engtype_.+)', engine['instance'])
        if not match:
            continue
        name = adapter_names.get((int(match[1], 16) << 32) | int(match[2], 16), 'Unknown adapter')
        if engine['status'] not in (0, 1):
            invalid[name + ' engine status ' + str(engine['status'])] += 1
            continue
        engines[(name, match[3])] += max(0.0, engine['percent'])
    busiest = collections.defaultdict(float)
    for (name, engine), value in engines.items():
        metrics[name + ' Windows ' + engine + ' percent'].append(value)
        busiest[name] = max(busiest[name], value)
    for name, value in busiest.items():
        metrics[name + ' Windows busiest engine percent'].append(value)

for previous, current in zip(active, active[1:]):
    seconds = timestamp(current['utc']) - timestamp(previous['utc'])
    if not 0 < seconds < 10:
        continue
    prior = {p['pid']: p for p in previous['processes']}
    totals = collections.defaultdict(float)
    for process in current['processes']:
        if process['pid'] in prior and process['cpu_seconds'] is not None:
            delta = process['cpu_seconds'] - (prior[process['pid']]['cpu_seconds'] or 0)
            if delta >= 0:
                totals[process['name']] += delta / seconds / os.cpu_count() * 100
    for name, value in totals.items():
        metrics[name + ' CPU host-capacity percent (adjacent surviving PIDs)'].append(value)

def describe(values):
    ordered = sorted(values)
    return {'n': len(values), 'mean': sum(values) / len(values), 'p95': ordered[math.ceil(.95 * len(values)) - 1], 'max': max(values)}

times = [timestamp(r['utc']) for r in active]
summary = {
    'trial_start': start, 'trial_end': finish, 'trial_duration_s': high - low,
    'sample_count': len(active), 'first_sample_offset_s': times[0] - low,
    'last_sample_before_end_s': high - times[-1],
    'max_sample_gap_s': max(b - a for a, b in zip(times, times[1:])),
    'gaps_over_5s': [{'from_offset_s': a - low, 'to_offset_s': b - low, 'gap_s': b - a} for a, b in zip(times, times[1:]) if b-a > 5],
    'logical_cpu_count': os.cpu_count(),
    'method': 'Arithmetic sampled mean/p95/max; host CPU is Windows total. Process CPU normalizes cumulative CPU delta by elapsed time and logical CPUs; only adjacent surviving PIDs counted. Windows engines sum process instances sharing one physical engine, then select busiest engine per adapter; independent engines are never summed into a GPU percent. NVIDIA utilization/encoder are separate driver metrics. Sampling is not frame timing or optical evidence.',
    'limits': 'Monitor stopped on startup invalid-instance error; resumed explicitly. Missing interval is not interpolated. Invalid engine statuses excluded and counted. Background OS/Codex work remains in host/GPU figures. Tracking processing disabled in original open-loop configuration.',
    'invalid_samples': dict(invalid), 'metrics': {k: describe(v) for k, v in metrics.items()},
}
(OUT / 'telemetry-summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps({k: v for k, v in summary.items() if k != 'metrics'}, indent=2))
print(json.dumps({k: v for k, v in summary['metrics'].items() if 'Windows phys' not in k}, indent=2))
