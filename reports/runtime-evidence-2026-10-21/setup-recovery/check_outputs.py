"""Independent complete video decoding/counts for the successful bounded rig runs."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from cephvr.platform.windows.paths import extended_path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
probe = shutil.which("ffprobe")
assert probe
results = []
for label in ("abort", "normal"):
    state = json.loads((OUT / (label + "-terminal.json")).read_text(encoding="utf-8"))
    session = state.get("last_finalization", {}).get("session") if label == "abort" else state["session"]
    directory = Path(session["directory"]) / "protocol-data"
    logs = [p for p in directory.glob("*_LOG.json") if not p.name.endswith("_stimulus_LOG.json")]
    assert len(logs) == 1
    log = json.loads(logs[0].read_text(encoding="utf-8"))
    assert log["complete"]
    assert log["outcome"] == ("interrupted" if label == "abort" else "completed")
    item = {"label": label, "outcome": log["outcome"], "outputs": []}
    for output in log["outputs"]:
        assert output["closure"] == "OUTPUT_CLOSURE_CLOSED" and output["artifact_present"]
        path = Path(output["path"])
        assert path.is_file()
        result = {"tag": output["output_tag"], "counts": output.get("counts"), "bytes": path.stat().st_size}
        if path.suffix == ".mp4":
            command = [probe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", extended_path(path)]
            decoded = subprocess.run(command, capture_output=True, text=True, timeout=120)
            assert decoded.returncode == 0 and not decoded.stderr, decoded.stderr
            result["decode"] = json.loads(decoded.stdout)["streams"][0]
            assert int(result["decode"]["nb_read_frames"]) == output["counts"]["frames"]
        item["outputs"].append(result)
    results.append(item)
    (OUT / "output-verification.json").write_text(json.dumps({"ffprobe": probe, "runs": results}, indent=2), encoding="utf-8")
    print(label, "all outputs Closed/present; complete video decode counts match", flush=True)

sources = ["src/cephvr/acquisition/coordinator/session.py", "src/cephvr/acquisition/coordinator/session_preparation.py", "src/cephvr/controller/state.py", "src/cephvr/controller/lifecycle/preparation_context.py", "src/cephvr/controller/lifecycle_completion.py", "src/cephvr/visual_stimulus/coordinator/commands.py", "src/cephvr/visual_stimulus/coordinator/reports.py", "src/cephvr/visual_stimulus/worker/runtime.py", "src/cephvr/visual_stimulus/worker/lifecycle.py"]
(OUT / "source-provenance.json").write_text(json.dumps({"date": "2026-10-21", "base_revision": "c740c5c2881e11b4cf7f3d835ffa7708de6fdbfb", "dirty_tree": True, "sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}}, indent=2), encoding="utf-8")
