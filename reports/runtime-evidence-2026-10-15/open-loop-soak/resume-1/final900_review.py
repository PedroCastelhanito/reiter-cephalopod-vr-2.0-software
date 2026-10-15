"""Retain bounded post-closure drop and nonaliasing visual evidence."""
import json
from pathlib import Path
import shutil
import subprocess

run = Path(__file__).parent / "combined900-final-r1"
collection = json.loads((run / "collection.json").read_text())
assert collection["collection_complete"] and not collection["errors"]
directory = Path(collection["directory"])
source = next(directory.rglob("*_stimulus_frames.jsonl"))
groups, drops = {}, []
for line in source.open():
    row = json.loads(line)["payload"]
    if row["kind"] == "render_group":
        groups[row["group_id"]] = row["state"]["evaluation_host_ns"]
    if row["kind"] in ("render_group", "group_update"):
        captures = [capture for capture in row["captures"] if capture["disposition"] == "capacity_drop"]
        if captures:
            drops.append(dict(group_id=row["group_id"], captures=captures))
result = {"method": "Post-closure source records and nonaliasing video seeks; software review is not optical alignment evidence", "drop_updates": drops}
for row in drops:
    row["evaluation_elapsed_s"] = (groups[row["group_id"]] - 58890835301100) / 1e9
video = next(directory.rglob("*_stimulus.mp4"))
commands = []
for second in (15, 17, 315, 322, 615, 622):
    output = run / f"stimulus-{second}s.png"
    command = [shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-ss", str(second), "-i", str(video), "-frames:v", "1", "-y", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    commands.append(dict(command=command, exit=completed.returncode, stderr=completed.stderr))
    assert completed.returncode == 0 and not completed.stderr
result["snapshot_commands"] = commands
(run / "post-closure-review.json").write_text(json.dumps(result, indent=2))
print(json.dumps({"drops": drops, "snapshots": len(commands)}))
