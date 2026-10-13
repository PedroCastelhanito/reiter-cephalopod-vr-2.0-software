"""Bounded microbenchmark using one actual recorded render-group envelope."""
import json
from pathlib import Path
import time
from cephvr.visual_stimulus.config.models.evidence_model import EvidenceRecord
from cephvr.visual_stimulus.recording.evidence import EvidenceWriter
OUT=Path(__file__).parent
r=json.loads((OUT/'run.json').read_text())['checks']
path=next((Path(r['final']['session']['directory'])/'protocol-data').glob('*stimulus_frames.jsonl'))
line=next(line for line in path.read_text().splitlines() if json.loads(line)['payload']['kind']=='render_group')
record=EvidenceRecord.model_validate_json(line)
old=EvidenceWriter._encode(record)
new=record.model_dump_json().encode('utf-8')+b'\n'
assert json.loads(old)==json.loads(new)
values={}
for name,fn in (('two_pass',lambda:EvidenceWriter._encode(record)),('native_json',lambda:record.model_dump_json().encode('utf-8')+b'\n')):
    started=time.perf_counter_ns()
    for _ in range(3000): fn()
    values[name]=(time.perf_counter_ns()-started)/3000/1e6
print(json.dumps({'mean_ms':values,'line_bytes':len(line.encode()),'semantic_match':True},indent=2))
(OUT/'serialize-benchmark.json').write_text(json.dumps(values,indent=2))
