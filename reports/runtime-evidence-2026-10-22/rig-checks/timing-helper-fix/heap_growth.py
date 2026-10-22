"""Offline representative evidence allocation census; not rig acceptance."""
import collections,gc,json,time
from pathlib import Path
from cephvr.visual_stimulus.config.models.evidence_model import EvidenceRecord,RenderGroup,Clipping,GroupUpdate,Capture
from cephvr.visual_stimulus.recording.evidence import EvidenceWriter
root=Path("cephvr-data/r22/20261022_full22fixed/SPRIGCHECK-114917/protocol-data")
for line in (root/"RIGCHECK_115036_stimulus_frames.jsonl").open(encoding="utf-8"):
 payload=json.loads(line)["payload"]
 if payload["kind"]=="render_group":break
raw=RenderGroup.model_validate_json(json.dumps(payload)).model_dump(mode="python")
count=72000
results=[]
def census():
 return collections.Counter(type(x).__module__+"."+type(x).__qualname__ for x in gc.get_objects())
gc.collect();gc.freeze();start=census();clock=time.perf_counter()
try:
 for group in range(count):
  raw["group_id"]=group
  record=RenderGroup.model_validate(raw)
  EvidenceWriter._encode(EvidenceRecord(payload=record))
  for face in ("front","left","right","bottom"):
   clip=Clipping(kind="clipping",group_id=group,output_id=face,occurrence_index=0,observation_host_ns=1,stages=())
   EvidenceWriter._encode(EvidenceRecord(payload=clip))
  for disposition in ("transfer_complete","input_submitted"):
   update=GroupUpdate(kind="group_update",group_id=group,submissions=(),captures=(Capture(disposition=disposition,video_frame_index=group if disposition=="input_submitted" else None,source_pixel_format="rgba8_top_down",encoder_pixel_format="yuv444p",failure_code=None),))
   EvidenceWriter._encode(EvidenceRecord(payload=update))
  if (group+1)%12000==0:
   before=time.perf_counter_ns();collected=gc.collect(2);elapsed=time.perf_counter_ns()-before
   delta=census()-start
   item={"groups":group+1,"gen2_ns":elapsed,"collected":collected,"growth":delta.most_common(12)};results.append(item);print(item,flush=True)
finally:gc.unfreeze()
Path(__file__).with_name("heap-growth.json").write_text(json.dumps({"scope":"offline representative model encode, no GL/recording thread", "elapsed_s":time.perf_counter()-clock,"samples":results},indent=2),encoding="utf-8")
