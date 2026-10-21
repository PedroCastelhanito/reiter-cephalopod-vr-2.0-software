"""Summarize full timing logs without modifying source data."""

import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\cephvr-data\protocol-data\20261020_ephys-pilot\SP0003-123824\protocol-data")
OUT = Path(__file__).parent


def intervals(values, scale=1e-6):
    d = np.diff(np.asarray(values, dtype=np.int64)) * scale
    return {"percentiles": np.percentile(d, [0, 1, 50, 99, 100]).tolist(), "nonpositive": int((d <= 0).sum())}


result = {}
arrays = {}
for f in ROOT.glob("*frames.jsonl"):
    counts = Counter()
    hosts, native, counters, ids, markers, levels, epochs = [], [], [], [], [], [], []
    completions = []
    errors = Counter()
    for line in f.open():
        record = json.loads(line)
        r = record.get("payload", record)
        kind = r.get("type", r.get("kind"))
        counts[kind] += 1
        if kind == "header":
            header = r
        elif kind == "frame":
            hosts.append(r["host_receipt_ns"])
            native.append(r["camera_timestamp_ns"])
            counters.append(r["camera_frame_counter"])
            ids.append(r["frame_id"])
            errors[str(r["video_disposition"])] += 1
        elif kind == "render_group":
            hosts.append(r["state"]["evaluation_host_ns"])
            ids.append(r["group_id"])
            epochs.append(r["state"]["epoch_occurrence"])
            for s in r["submissions"]:
                errors[s["phase"]] += 1
                if s["marker_index"] is not None:
                    markers.append(s["marker_index"])
                    levels.append(s["marker_high"])
            for im in r["state"]["images"]:
                errors["image_" + im["disposition"]] += 1
        elif kind in ("completion", "encoder_outcome"):
            completions.append(r)
    assert len(hosts) == len(ids) and ids == list(range(len(ids)))
    summary = {"record_counts": dict(counts), "host_interval_ms": intervals(hosts), "outcomes": dict(errors), "completions": completions}
    if native:
        assert all(x is not None for x in native + counters)
        summary["camera_interval_ms"] = intervals(native)
        summary["counter_steps"] = dict(Counter(np.diff(counters).tolist()))
        for k, a in [("native", native), ("host", hosts), ("counter", counters)]:
            arrays[f.stem + "_" + k] = np.asarray(a, dtype=np.int64)
    else:
        assert markers == list(range(len(markers)))
        assert all(h == (i % 60 < 3 or (i % 60 >= 6 and i % 2 == 0)) for i, h in zip(markers, levels))
        summary["marker_count"] = len(markers)
        summary["epoch_counts"] = dict(Counter(epochs))
        summary["marker_transitions"] = int(np.count_nonzero(np.diff(levels)))
        for k, a in [("host", hosts), ("epoch", epochs), ("marker", markers), ("level", levels)]:
            arrays[f.stem + "_" + k] = np.asarray(a)
    start = header.get("trial_start_host_ns", header.get("clocks", {}).get("trial_start_monotonic_ns"))
    summary["first_last_relative_s"] = [(hosts[0] - start) / 1e9, (hosts[-1] - start) / 1e9]
    result[f.name] = summary
np.savez_compressed(OUT / "log_arrays.npz", **arrays)
(OUT / "log_inspection.json").write_text(json.dumps(result, indent=2))
print(json.dumps({k: {a: b for a, b in v.items() if a != "epoch_counts"} for k, v in result.items()}, indent=2))
