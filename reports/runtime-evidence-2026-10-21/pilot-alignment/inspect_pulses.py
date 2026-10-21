"""Read-only pilot pulse inspection; derived evidence stays beside this script."""

import json
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\cephvr-data\protocol-data\20261020_ephys-pilot\SP0003-123824")
OUT = Path(__file__).parent


def metadata(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def edges(values, previous):
    change = np.diff(np.r_[previous, values].astype(np.int8))
    return np.flatnonzero(change == 1), np.flatnonzero(change == -1)


assert tuple(map(list, edges(np.array([False, True, True, False]), False))) == ([1], [3])
result = {"source": str(ROOT), "method": "full OneBox sample scan; three 5-second probe SY windows", "streams": {}}
meta = next(ROOT.rglob("*.obx.meta"))
m = metadata(meta)
n = int(m["nSavedChans"])
binary = meta.with_suffix(".bin")
assert binary.stat().st_size == int(m["fileSizeBytes"])
assert binary.stat().st_size % (2 * n) == 0
data = np.memmap(binary, dtype="<i2", mode="r").reshape(-1, n)
rate = float(m["obSampRate"])
signals = {f"XD{b}": (12, b) for b in range(12)}
signals["SY6"] = (13, 6)
previous = {k: False for k in signals}
found = {k + suffix: [] for k in signals for suffix in ("_rise", "_fall")}
samples = []
for start in range(0, len(data), 1_000_000):
    block = data[start : start + 1_000_000]
    samples.append(block[::100, :12].copy())
    for key, (ch, bit) in signals.items():
        value = (block[:, ch] & (1 << bit)) != 0
        rise, fall = edges(value, previous[key])
        if start == 0 and value[0]:
            rise = rise[rise != 0]  # Initial high is not an observed rising edge.
        found[key + "_rise"].extend((rise + start).tolist())
        found[key + "_fall"].extend((fall + start).tolist())
        previous[key] = bool(value[-1])
sample = np.concatenate(samples).astype(float) * float(m["obAiRangeMax"]) / int(m["obMaxInt"])
summary = {"metadata": m, "samples": len(data), "analog_voltage_percentiles_0_1_50_99_100": np.percentile(sample, [0, 1, 50, 99, 100], axis=0).T.tolist(), "edges": {}}
for key, v in found.items():
    a = np.array(v, dtype=np.int64)
    summary["edges"][key] = {"count": len(a), "first_s": (a[:6] / rate).tolist(), "last_s": (a[-6:] / rate).tolist(), "interval_percentiles_s": np.percentile(np.diff(a) / rate, [0, 1, 50, 99, 100]).tolist() if len(a) > 1 else []}
result["streams"]["onebox"] = summary
np.savez_compressed(OUT / "onebox_edges.npz", **{k: np.array(v, dtype=np.int64) for k, v in found.items()})
apmeta = next(ROOT.rglob("*.ap.meta"))
am = metadata(apmeta)
apbin = apmeta.with_suffix(".bin")
assert apbin.stat().st_size == int(am["fileSizeBytes"])
ap = np.memmap(apbin, dtype="<i2", mode="r").reshape(-1, int(am["nSavedChans"]))
ar = float(am["imSampRate"])
windows = []
for seconds in [0, 1900, 3898]:
    start = int(seconds * ar)
    words = ap[start : start + int(5 * ar), -1].copy()
    high = (words & 64) != 0
    rising = np.flatnonzero(np.diff(high.astype(np.int8)) == 1) + start + 1
    windows.append({"start_s": seconds, "unique_SY": np.unique(words).tolist(), "rising_samples": rising.tolist(), "rising_seconds": (rising / ar).tolist()})
result["streams"]["probe"] = {"metadata": {k: v for k, v in am.items() if not k.startswith("~")}, "samples": len(ap), "windows": windows}
(OUT / "pulse_inspection.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
