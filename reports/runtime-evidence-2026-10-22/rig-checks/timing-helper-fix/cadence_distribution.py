"""Post-run software cadence distribution; no device or optical timing claim."""
import collections,json,math,sys
from pathlib import Path
out=Path(sys.argv[1]);terminal=json.loads((out/'terminal.json').read_text(encoding='utf-8'));root=Path(terminal['session']['directory'])/'protocol-data'
def summary(values):
 values.sort();n=len(values)
 return {'count':n,'minimum_ns':values[0] if n else None,'p50_ns':values[math.ceil(n*.5)-1] if n else None,'p95_ns':values[math.ceil(n*.95)-1] if n else None,'p99_ns':values[math.ceil(n*.99)-1] if n else None,'p999_ns':values[math.ceil(n*.999)-1] if n else None,'maximum_ns':values[-1] if n else None,'gaps_over_ms':{str(ms):sum(v>ms*1_000_000 for v in values) for ms in (20,25,35,50,100)}}
results=[]
for path in sorted(root.glob('*_stimulus_frames.jsonl')):
 intervals=[];outputs=collections.defaultdict(list);last=None;lastout={};slow=[];groups=0
 with path.open(encoding='utf-8') as stream:
  for line in stream:
   d=json.loads(line)['payload']
   if d['kind']!='render_group':continue
   groups+=1;now=d['state']['evaluation_host_ns']
   if last is not None:
    gap=now-last;intervals.append(gap)
    if gap>35_000_000:slow.append({'group':d['group_id'],'epoch':d['state']['epoch_occurrence'],'interval_ns':gap})
   last=now
   for s in d['submissions']:
    if s['phase']!='returned':continue
    key=s['output_id'];entry=s['entry_host_ns']
    if key in lastout:outputs[key].append(entry-lastout[key])
    lastout[key]=entry
 result={'path':str(path),'groups':groups,'state':summary(intervals),'outputs':{key:summary(v) for key,v in outputs.items()},'slow_state_gaps':slow};results.append(result);print(path.name,'state',result['state'],flush=True)
(out/'cadence-distribution.json').write_text(json.dumps({'scope':'host software evaluation and submission entry intervals, no optical onset/strict60Hz guarantee','trials':results},indent=2),encoding='utf-8')
