from pathlib import Path
import json,heapq
root=Path("cephvr-data/r22/20261022_full22fixed/SPRIGCHECK-114917/protocol-data")
out=[]
for path in sorted(root.glob("*_stimulus_frames.jsonl")):
 groups=[]
 with path.open(encoding="utf-8") as stream:
  for line in stream:
   d=json.loads(line)["payload"]
   if d["kind"]!="render_group":continue
   subs=d["submissions"];state=d["state"]
   groups.append({"id":d["group_id"],"eval":state["evaluation_host_ns"],"epoch":state["epoch_occurrence"],"images":[x["asset_id"] for x in state["images"]],"submissions":subs})
 gaps=[]
 for prev,current in zip(groups,groups[1:]):
  interval=current["eval"]-prev["eval"]
  if interval>35_000_000 or any(s["return_host_ns"] is not None and s["entry_host_ns"] is not None and s["return_host_ns"]-s["entry_host_ns"]>35_000_000 for s in current["submissions"]):
   first=min((s["entry_host_ns"] for s in current["submissions"] if s["entry_host_ns"] is not None),default=None)
   prevlast=max((s["return_host_ns"] for s in prev["submissions"] if s["return_host_ns"] is not None),default=None)
   gaps.append({"group_id":current["id"],"eval_interval_ns":interval,"previous_return_to_eval_ns":current["eval"]-prevlast if prevlast is not None else None,"eval_to_first_entry_ns":first-current["eval"] if first is not None else None,"nearby":groups[max(0,current["id"]-2):current["id"]+2]})
 out.append({"path":str(path),"groups":len(groups),"gaps_over35ms":len(gaps),"worst":heapq.nlargest(12,gaps,key=lambda g:g["eval_interval_ns"])})
Path(__file__).with_name("gap-correlation.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
for trial in out:
 print(trial["path"],trial["groups"],"gaps",trial["gaps_over35ms"])
 for g in trial["worst"][:4]:
  print({k:v for k,v in g.items() if k!="nearby"})
  for n in g["nearby"]:print(" group",n["id"],"epoch",n["epoch"],"eval",n["eval"],"sub_ms",[(x["output_id"],round((x["return_host_ns"]-x["entry_host_ns"])/1e6,3)) for x in n["submissions"] if x["return_host_ns"] is not None and x["entry_host_ns"] is not None])
