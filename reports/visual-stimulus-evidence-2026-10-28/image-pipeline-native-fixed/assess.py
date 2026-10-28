import ast,hashlib,json,re,statistics
from pathlib import Path
out=Path(__file__).parent
before=out.with_name("image-pipeline-native")
events=[json.loads(l) for l in (out/"events.jsonl").read_text().splitlines()]
log=(out/"launch.err").read_text(encoding="utf-8")
line=next(l for l in log.splitlines() if l.startswith("Texture residency"))
a=line.split("stages=",1)[1];st,g=a.split(" gpu=",1);gpu,loader=g.split(" loader=",1)
presentation=[]
for line in log.splitlines():
    if line.startswith("Presentation timing"):
        values=dict(re.findall(r"(\w+)=([^ ]+)",line))
        values["mean_submissions_per_second"]=(int(values["returned"])-1)*1e9/(int(values["last_ns"])-int(values["first_ns"]))
        presentation.append(values)
original=json.loads((out/"before.json").read_text())["configuration_values"]["current"]
restored=json.loads((out/"restored.json").read_text())
assert restored["configuration_values"]["current"]==original
assert restored["session"]["cleanup_confirmed"]
def stimulus_config(folder):
    c=json.loads((folder/"applied.json").read_text())["configuration_values"]["current"]
    return next(b for b in c["backends"] if b["backend_name"]=="visual_stimulus"),c["trials"]
assert stimulus_config(out)==stimulus_config(before)
provenance=json.loads((out/"source-provenance.json").read_text())
changed=[f for f,d in provenance["sha256"].items() if hashlib.sha256(Path(f).read_bytes()).hexdigest()!=d]
summary={"date":"2026-10-28","setup":[e["value"] for e in events if e["kind"]=="setup"],"duration":next(e["value"] for e in events if e["kind"]=="duration"),"stages":{"render":ast.literal_eval(st),"gpu":ast.literal_eval(gpu),"loader":ast.literal_eval(loader)},"presentation":presentation,"cleanup_confirmed":True,"configuration_restored":True,"stimulus_and_trials_match_prior_test":True,"changed_source_during_run":changed,"remaining_crop_directories":[str(p) for p in Path(original["asset_root"]).parent.glob(".cephvr-crops-*")],"hash_probe":json.loads((out/"hash-probe.json").read_text()),"limits":"Two Setups and90-second projector-only playback. No camera/recording/preview load,20-minute/full-hour endurance or optical simultaneity acceptance."}
(out/"assessment.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in summary.items() if k not in ("stages","hash_probe")},indent=2))
