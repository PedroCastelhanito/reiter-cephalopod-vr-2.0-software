"""Assess retained overlapping native SpikeGLX samples, without interpolation."""
import json
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parent
raw = np.load(OUT / 'onebox0-channel0.npz')
meta = json.loads((OUT / 'sampler.json').read_text(encoding='utf-8'))
assert 'error' not in meta, meta
heads = raw['heads'].astype(np.int64); rows = raw['values']
assert len(heads) > 2
parts = []; cursor = int(heads[0]); gaps = []; conflicts = 0
for head, row in zip(heads, rows):
    head = int(head)
    if head > cursor:
        gaps.append([cursor,head])
    start = max(0,cursor-head)
    if start < len(row):
        parts.append(row[start:]); cursor = head + len(row)
values = np.concatenate(parts)
assert not gaps, gaps
volts = values * meta['volts_per_int16']
high = volts > 2.5
edges = np.flatnonzero(high[1:] != high[:-1]) + 1
bounds = np.r_[0,edges,len(values)]
segments = []
for a,b in zip(bounds[:-1],bounds[1:]):
    v=volts[a:b]
    segments.append({'high':bool(high[a]),'first_sample':int(heads[0]+a),'samples':int(b-a),'duration_s':float((b-a)/meta['sample_rate']),'min_V':float(v.min()),'max_V':float(v.max()),'median_V':float(np.median(v))})
assessment = {'method':'Official SDK fetchLatest OneBox0 channel0, int16-to-volts factor from same stream. Overlapping chunks merged by native sample index, no interpolation. HIGH threshold 2.5 V. Host snapshots identify trial phase; host time is not electrical timing authority.', 'sample_rate_Hz':meta['sample_rate'],'unique_samples':len(values),'capture_seconds':len(values)/meta['sample_rate'],'missing_sample_intervals':gaps,'segments':segments,'limits':'One normal trial and one early Abort; does not establish full-load, intertrial-gap, preview or watchdog acceptance.'}
assert len(segments) == 5 and [s['high'] for s in segments] == [False, True, False, True, False]
assert abs(segments[1]['duration_s'] - 60) < .02
settled = {}
for name, edge in zip(('normal_start','normal_stop','abort_start','abort_stop'),edges):
    v = volts[int(edge+.1*meta['sample_rate']):int(edge+meta['sample_rate'])]
    settled[name] = {'window': '100ms to1s after recorded edge', 'min_V':float(v.min()), 'max_V':float(v.max()), 'median_V':float(np.median(v))}
assert all(settled[k]['max_V'] < .1 for k in ('normal_stop','abort_stop'))
assert all(settled[k]['min_V'] > 4.5 for k in ('normal_start','abort_start'))
assessment['settled_windows'] = settled
assessment['checks_passed'] = True
(OUT / 'signal-assessment.json').write_text(json.dumps(assessment,indent=2),encoding='utf-8')
print(json.dumps(assessment,indent=2))
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(11,3.8))
    # Preserve extrema within 10 ms bins for a compact plot.
    block=max(1,int(meta['sample_rate']*.01)); count=len(volts)//block
    trimmed=volts[:count*block].reshape(count,block)
    t=np.arange(count)*block/meta['sample_rate']
    ax.fill_between(t,trimmed.min(axis=1),trimmed.max(axis=1),color='#176b91',alpha=.8)
    ax.plot(t,np.median(trimmed,axis=1),color='#176b91',linewidth=.7)
    ax.set(xlabel='Seconds from capture start',ylabel='OneBox0 channel0 (V)',title='D12 trial signal recorded by SpikeGLX',ylim=(-.2,5.3))
    ax.grid(alpha=.2);fig.tight_layout();fig.savefig(OUT/'trial-signal.png',dpi=170);plt.close(fig)
except ImportError:
    print('Matplotlib unavailable; retained native data and numerical assessment.')
