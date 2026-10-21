"""Plot raw detector and 1 ms averages for diagnostic windows, not event extraction."""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).parent
ROOT = Path(r"D:\cephvr-data\protocol-data\20261020_ephys-pilot\SP0003-123824")
path = next(ROOT.rglob("*.obx.bin"))
data = np.memmap(path, dtype="<i2", mode="r").reshape(-1, 14)
rate = 30303
canvas = Image.new("RGB", (1500, 1000), "white")
draw = ImageDraw.Draw(canvas)
summary = []
for panel, (start, duration) in enumerate([(0, 5), (2, 1.2), (2.0, .1), (902, 2)]):
    a, b = int(start * rate), int((start + duration) * rate)
    v = data[a:b, 1].astype(float) * 5 / 32768
    x0, x1, y0, y1 = 75, 1475, 35 + panel * 245, 215 + panel * 245
    draw.text((x0, y0 - 20), f"XA1 photodiode: {start:g} to {start + duration:g} s, OneBox file time. Gray=raw; red=0.99 ms mean", fill="black")
    for volts in range(6):
        y = y1 - volts / 5 * (y1 - y0)
        draw.line([(x0, y), (x1, y)], fill="#dddddd")
        draw.text((35, y - 5), f"{volts} V", fill="black")
    for tick in range(6):
        x = x0 + tick / 5 * (x1 - x0)
        draw.text((x - 12, y1 + 7), f"{start + duration * tick / 5:.3f}", fill="black")
    # Min/max per horizontal pixel retains brief raw excursions.
    for pixel, indices in enumerate(np.array_split(np.arange(len(v)), x1 - x0)):
        if len(indices):
            lo, hi = v[indices].min(), v[indices].max()
            draw.line([(x0 + pixel, y1 - hi / 5 * (y1 - y0)), (x0 + pixel, y1 - lo / 5 * (y1 - y0))], fill="#aaaaaa")
    count = len(v) // 30
    mean = v[:count * 30].reshape(-1, 30).mean(axis=1)
    draw.line([(x0 + (i * 30 + 14.5) / len(v) * (x1 - x0), y1 - value / 5 * (y1 - y0)) for i, value in enumerate(mean)], fill="#c02020", width=2)
    summary.append({"start_s": start, "duration_s": duration, "raw_voltage_percentiles": np.percentile(v, [0, 1, 50, 99, 100]).tolist(), "mean_voltage_percentiles": np.percentile(mean, [0, 1, 50, 99, 100]).tolist(), "positive_rail_fraction": float(np.mean(v >= 32767 * 5 / 32768))})
canvas.save(OUT / "photodiode_windows.png")
(OUT / "photodiode_windows.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary))
