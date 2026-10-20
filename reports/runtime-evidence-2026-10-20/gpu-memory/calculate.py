import json,time,hashlib
from pathlib import Path
from uuid import uuid4
from google.protobuf.json_format import ParseDict
from cephvr.visual_stimulus.v1 import messages_pb2 as wire
from cephvr.visual_stimulus.configuration import load_file_policies
from cephvr.visual_stimulus.resources.session import NativePreparation
from cephvr.visual_stimulus.resources.budget import review_capture_gpu_bytes
from cephvr.visual_stimulus.config.review_layout import recording_layout
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
root=Path.cwd()
snapshot=json.loads((root/'reports/runtime-evidence-2026-10-20/setup-watchdog/snapshot.json').read_text())
config=snapshot['configuration_values']['current']
protocol=json.loads(Path(r'C:\Users\ReiterU_PC\Desktop\Pedro\primate_cuttlebase_20min.json').read_text())
r=wire.WorkerSetup(); ParseDict(config,r.session.configuration)
r.session.configuration_revision=1
r.session.context.session_id=str(uuid4());r.session.context.controller_generation=str(uuid4())
for i,t in enumerate(r.session.configuration.trials):
 t.stimulus.program.program_json=json.dumps(protocol['trials'][i]['program'])
 trial=r.session.trials.add();trial.context.session.CopyFrom(r.session.context);trial.context.trial_id=str(uuid4());trial.context.trial_number=i+1;trial.definition.CopyFrom(t)
for backend in r.session.configuration.backends:
 if backend.backend_name=='visual_stimulus':r.settings.CopyFrom(backend.visual_stimulus)
r.settings.save_visual_stimulus_data=False
r.policies.CopyFrom(load_file_policies(root))
class Source:
 def __init__(self,path):self.path=path
 def independent_reader(self):return self.path.open('rb')
 def close_after_consumers(self):pass
prep=NativePreparation(object(),renderer_generation=str(uuid4()),source_factory=Source)
started=time.perf_counter()
try:
 artifacts=prep.prepare_trials(r,lambda *_:None,time.perf_counter_ns()+300_000_000_000,announce_batch=lambda _:None)
 cache=prep.image_residency;s=cache.schedule
 fixed={k:v.gpu_bytes for k,v in prep._budget._usage.items() if v.gpu_bytes}
 initial=sum(s.sources[k].gpu_bytes for k in s.anchors)
 rows=[]
 for trial,epochs in s.epochs.items():
  maxima={};largest=0
  for epoch in epochs:
   keys={s.aliases[(trial,a)] for _,a in epoch}
   largest=max(largest,sum(s.sources[k].gpu_bytes for k in keys if k not in s.anchors))
   for instance,a in epoch:
    k=s.aliases[(trial,a)];maxima[instance]=max(maxima.get(instance,0),0 if k in s.anchors else s.sources[k].gpu_bytes)
  rows.append({'initial':initial,'held':sum(maxima.values()),'next':largest,'minimum_images':initial+sum(maxima.values())+largest})
 layout=recording_layout(artifacts[0].display,r.policies.review_scale_factor)
 review=review_capture_gpu_bytes(layout.composite_width,layout.composite_height,r.policies.limits.capture_slots,'rgba8_top_down')
 result={'basis':'saved Pedro20min protocol and retained calibrated display snapshot; CPU preparation only; no native GPU allocation','seconds':time.perf_counter()-started,'fixed_gpu_bytes':fixed,'fixed_total':sum(fixed.values()),'minimum_working_set':rows,'review_capture_gpu_bytes':review,'review_dimensions':[layout.composite_width,layout.composite_height],'minimum_with_review':sum(fixed.values())+len(artifacts)*review+max(x['minimum_images'] for x in rows),'old_minimum_with_review':sum(fixed.values())+len(artifacts)*review+4*max(x['minimum_images'] for x in rows),'trial_count':len(artifacts),'all_image_gpu_bytes':sum(x.gpu_bytes for x in s.sources.values()),'image_count':len(s.sources),'used_output_counts':sorted(set(len(x.output_ids) if x.output_ids is not None else 4 for x in s.sources.values())),'display_sha256':hashlib.sha256(r.settings.display.profile_json.encode()).hexdigest()}
 (root/'reports/runtime-evidence-2026-10-20/gpu-memory/calculation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
 prep.cleanup(time.perf_counter_ns()+10_000_000_000)
