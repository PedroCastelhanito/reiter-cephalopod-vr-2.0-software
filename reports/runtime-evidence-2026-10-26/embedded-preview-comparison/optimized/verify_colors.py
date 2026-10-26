"""Post-timing RGB fidelity and reused-QImage freshness check."""
import json
import time
from pathlib import Path

import numpy as np
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication

from tools.preview_benchmark_widgets import RasterCanvas, TextureCanvas, rectangles

fmt = QSurfaceFormat()
fmt.setSwapInterval(0)
QSurfaceFormat.setDefaultFormat(fmt)
app = QApplication([])
results = []
for kind in ("raster", "texture"):
    evidence = {}
    canvas = (RasterCanvas(3, 128, 3, []) if kind == "raster"
              else TextureCanvas(3, 128, 3, [], evidence))
    canvas.resize(600, 200)
    canvas.show()
    app.processEvents()
    addresses = [a.ctypes.data for a in canvas.frames.arrays]
    for sequence in range(2):
        frames = [np.zeros((128, 128, 3), np.uint8) for _ in range(3)]
        for i, frame in enumerate(frames):
            frame[:, :, (i + sequence) % 3] = 255
        canvas.submit(frames, sequence, time.perf_counter())
        for frame in frames:
            frame.fill(0)
        app.processEvents()
        pixels = canvas.grab().toImage() if kind == "raster" else canvas.grabFramebuffer()
        for i, rect in enumerate(rectangles(canvas.width(), canvas.height(), 3)):
            color = pixels.pixelColor(int(rect.center().x()), int(rect.center().y()))
            expected = [0, 0, 0]
            expected[(i + sequence) % 3] = 255
            assert [color.red(), color.green(), color.blue()] == expected
        assert addresses == [a.ctypes.data for a in canvas.frames.arrays]
    if kind == "texture":
        assert canvas.uploads == 6
        canvas.grabFramebuffer()
        assert canvas.uploads == 6
        canvas.release()
    canvas.close()
    results.append({"kind": kind, "passed": True, **evidence})
Path(__file__).with_suffix('.json').write_text(json.dumps(results, indent=2)+'\n')
print(json.dumps(results))
