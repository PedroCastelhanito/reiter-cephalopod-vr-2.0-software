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
for label in ("on-first", "off-abort", "on-reuse"):
    state = json.loads((OUT / (label + "-terminal.json")).read_text(encoding="utf-8"))
    session = state.get("last_finalization", {}).get("session") if label == "off-abort" else state["session"]
    directory = Path(session["directory"]) / "protocol-data"
    logs = [p for p in directory.glob("*_LOG.json") if not p.name.endswith("_stimulus_LOG.json")]
    assert len(logs) == 1
    log = json.loads(logs[0].read_text(encoding="utf-8"))
    assert log["complete"]
    assert log["outcome"] == ("interrupted" if label == "off-abort" else "completed")
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
    if label == "off-abort":
        assert not list(directory.parent.rglob("*.mp4")), "video Off unexpectedly created video"
        assert not any(o["tag"].startswith(("behavioral_cam", "tracking_cam", "eye_tracking_cam")) for o in item["outputs"])
        assert any(o["tag"] == "stimulus_frames" for o in item["outputs"])
    item["max_path_length"] = max((len(o["path"]) for o in log["outputs"]), default=0)
    results.append(item)
    (OUT / "output-verification.json").write_text(json.dumps({"ffprobe": probe, "runs": results}, indent=2), encoding="utf-8")
    print(label, "all outputs Closed/present; complete video decode counts match", flush=True)
