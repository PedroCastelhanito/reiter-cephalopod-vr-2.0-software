"""Read-only reanalysis of archived rig metrics; no new rig execution."""
from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.recording.encoding import _layout_at_scale
from cephvr.visual_stimulus.resources.session import review_capture_cpu_bytes

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "reports/runtime-evidence-2026-10-15/open-loop-soak/resume-1/combined900-final-r1"
paths = {
    "metrics": BASE / "owned-renderer-metrics.jsonl",
    "completion": BASE / "completion-summary.json",
    "candidate": BASE / "effective-candidate.json",
    "tested_defaults": BASE / "operator-config.test.toml",
    "current_defaults": ROOT / "config/backends/visual_stimulus_config.toml",
}
metrics = json.loads(paths["metrics"].read_text().strip())
completion = json.loads(paths["completion"].read_text())
candidate = json.loads(paths["candidate"].read_text())
settings = next(item["visual_stimulus"] for item in candidate["backends"] if item["backend_name"] == "visual_stimulus")
tested = tomllib.loads(paths["tested_defaults"].read_text())
current = tomllib.loads(paths["current_defaults"].read_text())
profile = parse_display_json(settings["display"]["profile_json"], max_bytes=tested["resources"]["max_document_bytes"])
scale = tested["recording_runtime"]["review_scale_factor"]
width, height, _ = _layout_at_scale(profile, scale)
frame_bytes = width * height * 4
frames = completion["encoder_outcome"]["input_submitted_count"]
assert metrics["submitted_bytes"] == frames * frame_bytes
budget = tested["resources"]["recording_bytes_total"]
result = {
    "date": "2026-10-16",
    "method": "Archived rig aggregate interpretation and current pure allocation formula; no new performance measurement.",
    "rig_source_revision": "Not recorded in the selected raw metrics/config/completion files; source provenance remains with their original execution context.",
    "inputs_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths.values()},
    "geometry": {"width": width, "height": height, "scale": scale, "rgba_frame_bytes": frame_bytes, "confirmed_by_total_submitted_bytes": True},
    "accounted_capture_memory": {},
    "historical_stages": {name: {**data, "mean_ns": data["total"] / data["count"] if data["count"] else None} for name, data in metrics["stages_ns"].items()},
    "historical_capacity_drops": completion["encoder_outcome"]["capacity_drop_count"],
    "historical_peak_slots": metrics["peak_capture_slots"],
    "interpretation": [
        "Queue wait is ready-to-dequeue; slot hold spans reservation-to-release. The maxima need not belong to one capture.",
        "Pipe-call durations exclude time between zero-progress writes and do not bound complete-frame stdin latency.",
        "The old aggregates cannot correlate the single startup drop with a particular GL/encoder/OS scheduling event or recover percentiles.",
        "The new bounded worst-stage examples and full-frame input spans require a future rig run before native attribution.",
    ],
    "default_disposition": "Keep the restored capture_slots=3 default. The tested 15-slot override fits accounted budgets but still filled all slots and dropped one capture; retain its evidence and leave a default increase pending native correlation.",
    "limits": "CPU capture reservation is checked against recording_bytes_total; GPU reservation joins the shared asset budget. Evidence queue bytes are separate. These formulas exclude unmeasured Python/driver/FFmpeg/OS memory and are not total-process/VRAM or zero-loss guarantees.",
}
for slots in (3, 15):
    cpu = review_capture_cpu_bytes(width, height, slots)
    gpu = width * height * 16 + frame_bytes * slots
    result["accounted_capture_memory"][str(slots)] = {
        "cpu_bytes": cpu, "gpu_bytes": gpu,
        "cpu_mib": cpu / 2**20, "gpu_mib": gpu / 2**20,
        "recording_cpu_budget_bytes": budget, "fits_capture_cpu_budget": cpu <= budget,
        "separate_evidence_queue_limit_bytes": tested["resources"]["evidence_pending_bytes"],
    }
assert current["resources"]["capture_slots"] == 3
assert tested["resources"]["capture_slots"] == 15
output = Path(__file__).with_suffix(".json")
output.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"geometry": result["geometry"], "capture_memory": result["accounted_capture_memory"], "default": current["resources"]["capture_slots"]}, indent=2))
