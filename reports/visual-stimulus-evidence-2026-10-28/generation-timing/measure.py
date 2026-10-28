"""Bounded CPU generation benchmark; no renderer, device or configuration mutation."""

import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.resources import sparse_noise
from cephvr.visual_stimulus.resources.sparse_noise_stream import trial_layers

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
source = next((HERE.parent / "rig-tests/sparse-fixed-run").rglob("*_stimulus_LOG.json"))
layers = trial_layers(PreparedTrial.model_validate_json(source.read_text()))
expected = {"front": (47, 42), "left": (64, 41), "right": (64, 42), "bottom": (64, 45)}
assert len(layers) == 4
for layer in layers:
    assert (layer.grid.columns, layer.grid.rows) == expected[layer.grid.surface_id]
    assert layer.shown == 200 and layer.recipe.square_size_mm == 2

observed = {}
frames = next(source.parent.glob("*_stimulus_frames.jsonl"))
for line in frames.open(encoding="utf-8"):
    payload = json.loads(line)["payload"]
    if payload["kind"] == "render_group":
        for item in payload["state"]["images"]:
            if item.get("pattern_sha256"):
                observed[item["instance_id"], item["image_index"]] = item["pattern_sha256"]
assert len(observed) == 800

# Warm imports/interpreter and allocator; these calls are not timing samples.
for index in range(10):
    for layer in layers:
        sparse_noise.pattern_rgba(layer.recipe, layer.grid, index)

samples = []
started = datetime.now(timezone(timedelta(hours=9))).isoformat()
for repeat in range(5):
    for index in range(200):
        for layer in layers:
            start = time.perf_counter_ns()
            pixels = sparse_noise.pattern_rgba(layer.recipe, layer.grid, index)
            elapsed = time.perf_counter_ns() - start
            digest = hashlib.sha256(pixels).hexdigest()
            assert digest == observed[layer.instance_id, index]
            samples.append({"repeat": repeat, "index": index,
                            "screen": layer.grid.surface_id, "generation_ns": elapsed})

summary = {}
for layer in layers:
    values = sorted(s["generation_ns"] / 1e6 for s in samples
                    if s["screen"] == layer.grid.surface_id)
    assert len(values) == 1000 and min(values) > 0
    summary[layer.grid.surface_id] = {
        "grid": asdict(layer.grid), "recipe": layer.recipe.model_dump(mode="json"),
        "samples": len(values), "mean_ms": statistics.mean(values),
        "median_ms": statistics.median(values), "p95_ms": values[949],
        "min_ms": min(values), "max_ms": max(values),
    }
result = {
    "started_jst": started, "python": sys.version, "platform": platform.platform(),
    "processor": platform.processor(), "executable": sys.executable,
    "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "source_plan": str(source.relative_to(ROOT)),
    "source_plan_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "generator_sha256": hashlib.sha256(Path(sparse_noise.__file__).read_bytes()).hexdigest(),
    "method": "perf_counter_ns around pattern_rgba only; 10 warmups/screen; 5 passes of indices 0..199, interleaved screens; GC/default process priority unchanged; p95 nearest rank",
    "limits": "Standalone CPU timing on rig under ambient load; excludes startup, IPC, hashing, row flip, GPU upload, rendering and optical latency. No combined-load acceptance.",
    "hash_checks_passed": len(samples), "summary": summary, "samples": samples,
}
(HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
