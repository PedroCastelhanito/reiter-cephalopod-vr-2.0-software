"""Preserve exact scientific JSON/JSONL bytes alongside dated assessment."""
import hashlib
import json
from pathlib import Path
import zipfile

out=Path(__file__).parent
assessment={k:{"directory":str(Path(v["session"]["directory"])/"protocol-data")} for k,v in json.loads((out/"counts.json").read_text(encoding="utf-8")).items()}
destination=out/"scientific-records.zip"
assert not destination.exists()
manifest={}
with zipfile.ZipFile(destination,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for label,result in assessment.items():
        for source in sorted(Path(result["directory"]).iterdir()):
            if source.suffix not in {".json",".jsonl"}:continue
            content=source.read_bytes();name=label+"/"+source.name
            archive.writestr(name,content)
            manifest[name]={"source_path":str(source),"bytes":len(content),"sha256":hashlib.sha256(content).hexdigest()}
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    for name,expected in manifest.items():assert hashlib.sha256(archive.read(name)).hexdigest()==expected["sha256"]
(out/"scientific-records-manifest.json").write_text(json.dumps({"scope":"Exact scientific/config JSON/JSONL bytes; videos retained locally and separately hashed, no output/closure reinterpretation","archive_sha256":hashlib.sha256(destination.read_bytes()).hexdigest(),"entries":manifest},indent=2)+"\n",encoding="utf-8")
print(len(manifest),"scientific files preserved",destination.stat().st_size,"archive bytes")
