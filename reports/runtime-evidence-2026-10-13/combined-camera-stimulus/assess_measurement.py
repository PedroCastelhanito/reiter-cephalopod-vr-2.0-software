"""External assessment of host-domain SDK receipt and MCU command evidence."""
import json
from pathlib import Path
import statistics
import subprocess
import hashlib
OUT = Path(__file__).parent
events = [json.loads(line) for path in OUT.glob('events-*.jsonl') for line in path.read_text().splitlines()]
events.sort(key=lambda row: row['host_ns'])
valid_pids = {row['pid'] for row in events if row['kind']=='instrumentation' and 'cephvr.acquisition.main' in row['argv']}
# The corrected coordinator generation is selected by its successful measurement command record.
coordinators = {pid for pid in valid_pids if any(row['pid']==pid and row['kind']=='off_end' for row in events)}
ons = [row for row in events if row['pid'] in coordinators and row['kind']=='on_end']
samples = {'40065509':[], '40747103':[]}
for on in ons:
    coordinator = on['pid']
    serial = {1:'40065509',2:'40747103'}[on['roles'][0]]
    off = next((row for row in events if row['pid']==coordinator and row['kind']=='off_end' and row['roles']==on['roles'] and row['host_ns']>on['host_ns']),None)
    if off is None:
        continue
    dispatch = int(on['evidence']['dispatched_monotonic_ns'])
    observed = next((row for row in events if row['kind']=='observation_begin' and row['serial']==serial and row['host_ns']>off['host_ns']),None)
    if observed is None:
        continue
    end = next((row for row in events if row['pid']==observed['pid'] and row['kind']=='observation_end' and row['host_ns']>observed['host_ns']),None)
    if end is None or not any(row['pid']==observed['pid'] and row['kind']=='observation_tail_end' for row in events):
        continue
    frames = [row for row in events if row['pid']==observed['pid'] and row['kind']=='frame' and dispatch<row['host_ns']<end['host_ns']]
    after_off = [row for row in frames if row['host_ns']>int(off['evidence']['acknowledged_monotonic_ns'])]
    tail = next(row for row in events if row['pid']==observed['pid'] and row['kind']=='observation_tail_end' and row['host_ns']>observed['host_ns'])
    readback = [row['value'] for row in events if row['pid']==observed['pid'] and row['kind']=='settings']
    samples[serial].append(dict(first_receipt_from_on_dispatch_ms=(frames[0]['host_ns']-dispatch)/1e6,
        post_off_receipts=len(after_off),last_receipt_after_off_ms=max([0]+[(row['host_ns']-int(off['evidence']['acknowledged_monotonic_ns']))/1e6 for row in after_off]),
        observation_duration_ms=(tail['host_ns']-observed['host_ns'])/1e6,frames=len(frames),readback=readback,
        applied_trigger_hz=on['evidence']['resulting_state'][{1:'behavioral',2:'tracking'}[on['roles'][0]]]['applied_frequency_hz']))
def stats(values):
    return dict(count=len(values),min=min(values),median=statistics.median(values),max=max(values)) if values else {}
result = dict(method='Sessionless managed previews; successful two-second observations only, exclude initial failed wrapper. ON-dispatch to first SDK receipt is a conservative combined latency including serial/trigger phase, exposure and delivery; direct SDK retrieval/release for 2s after confirmed OFF and AcquisitionStop. Per-frame diagnostic file append adds overhead. No recording, stimulus or concurrent-camera load; empirical observations, not guaranteed worst-case bounds. Diagnostic tail frames are raw observations, outside production accounting.',
    coordinator_pids=sorted(coordinators),samples=samples,summary={serial:dict(cycles=len(rows),first_receipt_ms=stats([r['first_receipt_from_on_dispatch_ms'] for r in rows]),last_post_off_receipt_ms=stats([r['last_receipt_after_off_ms'] for r in rows]),late_frames=sum(r['post_off_receipts'] for r in rows)) for serial,rows in samples.items()})
result['proposed_allowances'] = {}
for serial, proposal in (('40065509',125),('40747103',50)):
    rows = samples[serial]
    exposure = rows[0]['readback'][-1]['exposure_us']/1000
    period = 1000/rows[0]['applied_trigger_hz']
    first_max = max(row['first_receipt_from_on_dispatch_ms'] for row in rows)
    result['proposed_allowances'][serial] = dict(exposure_ms=exposure,frame_period_ms=period,
        conservative_empirical_delivery_component_ms=max(0,first_max-exposure),
        empirical_total_plus_one_period_ms=first_max+period,proposed_margin_ms=proposal,
        status='PROPOSED; owner approval required; file values remain unset; empirical measurements do not establish guaranteed maximum or full-load acceptance')
root = OUT.parents[2]
result['provenance'] = dict(date='2026-10-13', head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(), working_tree='concurrently dirty; no production source modified by timing measurement',
    methods_sha256={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('measure.py','assess_measurement.py','drain-instrumentation/sitecustomize.py')},
    failed_attempts='Initial wrapper sent excluded preview frame to sealed ring; corrected to raw SDK release. Early repeat client raced credential directory creation; corrected to wait for controller listener. Repeated MCU preview start returned unavailable/pending and later bounded command record byte budget exhaustion; further 12-cycle plan curtailed, three successful two-second observations per camera collected across two generations. Exact stopped-generation receipts/native inventory verified before launcher-remnant cleanup. Automatic review initially rejected broad cleanup; approved after exact absence proof and abort guards.')
(OUT/'drain-assessment.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result['summary'],indent=2))
