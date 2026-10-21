"""Exploratory matching checks; these do not certify physical timing accuracy."""

import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent
ROOT = Path(r"D:\cephvr-data\protocol-data\20261020_ephys-pilot\SP0003-123824")
edges = np.load(OUT / "onebox_edges.npz")
logs = np.load(OUT / "log_arrays.npz")
rate = 30303
blocks = np.split(edges["XD2_rise"], np.flatnonzero(np.diff(edges["XD2_rise"]) > rate / 2) + 1)
assert len(blocks) == 2
camera = []
for i, (pulse, stem) in enumerate(zip(blocks, ["0003_123845", "0003_125346"])):
    native = logs[stem + "_behavioral_cam_frames_native"]
    cam = (native - native[0]) / 1e9
    time = (pulse[:len(cam)] - pulse[0]) / rate
    slope, offset = np.polyfit(cam, time, 1)
    residual = (time - (slope * cam + offset)) * 1e6
    assert len(pulse) - len(cam) == i + 1
    camera.append({"trial": i + 1, "pulse_count": len(pulse), "saved_frames": len(cam), "post_cutoff_pulses": len(pulse) - len(cam), "first_pulse_vs_gate_us": int(pulse[0] - edges["XD0_rise"][i]) * 1e6 / rate, "camera_to_obx_slope": slope, "residual_us_percentiles": np.percentile(residual, [0, 1, 50, 99, 100]).tolist(), "residual_rms_us": float(np.sqrt(np.mean(residual ** 2)))})
(OUT / "camera_matching.json").write_text(json.dumps(camera, indent=2))
data = np.memmap(next(ROOT.rglob("*.obx.bin")), dtype="<i2", mode="r").reshape(-1, 14)
means = []
# Thirty-sample bins have exactly known centers and approximately 1 ms width.
for start in range(0, len(data), 900_000):
    values = data[start:start + 900_000, 1].astype(float) * 5 / 32768
    means.append(values[:len(values) // 30 * 30].reshape(-1, 30).mean(axis=1))
mean = np.concatenate(means)
np.save(OUT / "photodiode_mean_30samples.npy", mean.astype(np.float32))
checks = []
for threshold in [1., 1.5, 2., 2.5]:
    high = mean > threshold
    changes = np.flatnonzero(np.diff(high.astype(np.int8))) + 1
    run_bounds = np.r_[0, changes, len(mean)]
    lengths = np.diff(run_bounds) * 30 / rate
    counts = []
    for i in range(2):
        # Include 100 ms around gates for optical lag; exact matching is still needed.
        lo, hi = edges["XD0_rise"][i] / 30 - 100, edges["XD0_fall"][i] / 30 + 100
        selected = changes[(changes >= lo) & (changes <= hi)]
        counts.append({"trial": i + 1, "transitions": len(selected)})
    checks.append({"threshold_v": threshold, "total_transitions": len(changes), "runs_below_3ms": int((lengths < .003).sum()), "per_trial": counts})
result = {"method": "exploratory 30-sample bin means with fixed thresholds; not calibrated event timestamps", "checks": checks}
high = mean > 1.5
changes = np.flatnonzero(np.diff(high.astype(np.int8))) + 1
matches = []
for i, stem in enumerate(["0003_123845", "0003_125346"]):
    lo, hi = edges["XD0_rise"][i] / 30 - 100, edges["XD0_fall"][i] / 30 + 100
    observed = changes[(changes >= lo) & (changes <= hi)]
    levels = logs[stem + "_stimulus_frames_level"]
    host = logs[stem + "_stimulus_frames_host"]
    expected = np.r_[0, np.flatnonzero(np.diff(levels.astype(np.int8))) + 1]
    # A final high-to-Idle transition has no corresponding render-group timestamp.
    assert len(observed) == len(expected) + int(levels[-1])
    observed = observed[:len(expected)]
    assert np.array_equal(high[observed], levels[expected])
    x = (host[expected] - host[expected[0]]) / 1e9
    y = (observed * 30 + 14.5) / rate
    slope, offset = np.polyfit(x, y, 1)
    residual = (y - (slope * x + offset)) * 1e3
    matches.append({"trial": i + 1, "paired_transitions": len(expected), "host_to_obx_slope": slope, "residual_ms_percentiles": np.percentile(residual, [0, 1, 50, 99, 100]).tolist(), "residual_rms_ms": float(np.sqrt(np.mean(residual ** 2))), "scope": "ordered candidate matching to render evaluation, not calibrated submission-to-photon latency"})
result["candidate_sequence_matches"] = matches
(OUT / "photodiode_threshold_checks.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
