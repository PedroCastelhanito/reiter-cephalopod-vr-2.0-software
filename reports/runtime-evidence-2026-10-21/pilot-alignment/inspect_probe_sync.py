"""Check every recorded probe SY word; no neural preprocessing."""

import json
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\cephvr-data\protocol-data\20261020_ephys-pilot\SP0003-123824")
OUT = Path(__file__).parent
path = next(ROOT.rglob("*.ap.bin"))
data = np.memmap(path, dtype="<i2", mode="r").reshape(-1, 385)
counts = {}
transitions = 0
previous = None
for start in range(0, len(data), 1_000_000):
    a = data[start : start + 1_000_000, -1].copy()
    values, n = np.unique(a, return_counts=True)
    for v, count in zip(values, n):
        counts[int(v)] = counts.get(int(v), 0) + int(count)
    bit = (a & 64) != 0
    transitions += int(np.count_nonzero(np.diff(bit)))
    if previous is not None:
        transitions += int(previous != bit[0])
    previous = bit[-1]
assert sum(counts.values()) == len(data)
result = {"method": "every probe SY word scanned", "samples": len(data), "word_counts": counts, "bit6_transitions": transitions}
(OUT / "probe_sync_full.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
