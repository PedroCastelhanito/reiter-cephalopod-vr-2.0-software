"""Read-only sparse/hash and submission assessment for a closed native test."""
import collections
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.resources.sparse_noise_stream import trial_layers
from cephvr.visual_stimulus.resources.sparse_noise import pattern_rgba
root=Path(sys.argv[1])
frames=next(root.rglob('*_stimulus_frames.jsonl'))
plan=PreparedTrial.model_validate_json(next(root.rglob('*_stimulus_LOG.json')).read_text())
layers={(l.epoch_index,l.instance_id):l for l in trial_layers(plan)}
counts=collections.Counter(); dispositions=collections.Counter(); seen=collections.defaultdict(set)
hash_errors=[]; hash_count=0; evaluation=[]; returns=collections.defaultdict(list); ends=[]; final=[]
for line in frames.open():
 r=json.loads(line)['payload']; counts[r['kind']]+=1
 if r['kind']=='render_group':
  state=r['state']; evaluation.append(state['evaluation_host_ns'])
  for im in state['images']:
   dispositions[im['disposition']]+=1; seen[im['instance_id']].add(im['image_index'])
   if im['pattern_sha256']:
    layer=layers[state['epoch_occurrence'],im['instance_id']]
    actual=hashlib.sha256(pattern_rgba(layer.recipe,layer.grid,im['image_index'])).hexdigest()
    hash_count+=1
    if actual!=im['pattern_sha256']: hash_errors.append([im['instance_id'],im['image_index']])
  for sub in r['submissions']:
   if sub['phase']=='returned': returns[sub['output_id']].append(sub['return_host_ns'])
 if r['kind'] in ('completion','encoder_outcome'): final.append(r)
def gaps(values):
 a=np.diff(values)/1e6
 return {'count':len(values),'median_ms':float(np.median(a)),'p95_ms':float(np.percentile(a,95)), 'max_ms':float(max(a)), 'mean_hz':float(1000/np.mean(a))} if len(a) else {'count':len(values)}
summary={'record_counts':dict(counts),'image_dispositions':dict(dispositions),'patterns':{k:{'count':len(v),'first':min(v),'last':max(v)} for k,v in seen.items()},'hashes_checked':hash_count,'hash_mismatches':hash_errors,'evaluation':gaps(evaluation),'returns':{k:gaps(v) for k,v in returns.items()},'final_records':final,'provenance':plan.manifest.model_dump(mode='json')['provenance']}
(root/'assessment.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k not in ('final_records','provenance')},indent=2))
