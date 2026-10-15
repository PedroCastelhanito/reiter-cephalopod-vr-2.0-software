"""Collect only a normally finished trial, with exact session diagnostics."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("run", type=Path)
parser.add_argument("--timeout", type=int, default=300)
parser.add_argument("--parallel-videos", action="store_true")
args = parser.parse_args()
events = json.loads((args.run / "run.json").read_text())["events"]
final = next(row["value"] for row in events if row["label"] == "final")
assert final["session"]["cleanup_confirmed"]
assert final["trial"]["outcome"] == "TRIAL_OUTCOME_COMPLETED"
folder = Path(final["session"]["directory"])
metrics = []
for path in OUT.glob("renderer-metrics-*.jsonl"):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        row = json.loads(line)
        if row.get("event") == "recording_metrics" and Path(row["evidence_path"]).is_relative_to(folder):
            metrics.append(row)
assert len(metrics) == 1, f"Expected one exact completed recorder, got {len(metrics)}"
diagnostics = args.run / "owned-renderer-metrics.jsonl"
diagnostics.write_text("".join(json.dumps(row) + "\n" for row in metrics))
entry = [str(OUT / "collect_parallel.py")] if args.parallel_videos else ["tools/encoding_probe.py", "collect"]
command = [sys.executable, *entry, "--directory", str(folder),
           "--diagnostics", str(diagnostics), "--timeout", str(args.timeout),
           "--output", str(args.run / "collection.json")]
(args.run / "collection-command.json").write_text(json.dumps(command, indent=2))
with (args.run / "collection-output.txt").open("w") as stream:
    subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
subprocess.run([sys.executable, str(OUT / "assess.py"), str(args.run)], check=True)
assessment = json.loads((args.run / "assessment.json").read_text())
stimulus = next(value for key, value in assessment["sources"].items() if "stimulus" in key)
(args.run / "completion-summary.json").write_text(json.dumps(stimulus["final_records"], indent=2))
print(json.dumps(dict(session=final["session"], errors=assessment["errors"],
                      stimulus=stimulus["final_records"], metrics=metrics), indent=2))
