import json, runpy, time, tracemalloc
from pathlib import Path
import numpy as np
from cephvr.visual_stimulus.resources.media import ImagePixels
from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes
root = Path(__file__).parent
before = runpy.run_path(str(root / "upload_before.py"))["linear_rgba_bytes"]
rng = np.random.default_rng(0)
rows = []
for dtype, channels, alpha, transfer in [("uint8",3,"none","srgb"),("uint8",4,"straight","srgb"),("uint16",3,"none","srgb"),("uint16",3,"none","bt709"),("uint8",3,"none","linear"),("uint16",4,"associated","srgb")]:
    pixels = rng.integers(0, np.iinfo(dtype).max+1, (2160,3840,channels), dtype=dtype)
    image = ImagePixels(3840,2160,dtype,channels,(),pixels,transfer,alpha)
    expected = before(image)
    actual = linear_rgba_bytes(image)
    assert np.array_equal(np.frombuffer(expected,np.uint32),np.frombuffer(actual,np.uint32))
    del expected,actual
    row = dict(dtype=dtype,channels=channels,alpha=alpha,transfer=transfer)
    for name, operation in [("before",before),("after",linear_rgba_bytes)]:
        times=[]
        for _ in range(3):
            start=time.perf_counter(); result=operation(image); times.append((time.perf_counter()-start)*1000); del result
        tracemalloc.start(); result=operation(image); _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop(); del result
        row[name] = dict(median_ms=float(np.median(times)),peak_bytes=peak,bytes_per_pixel=peak/(3840*2160))
    rows.append(row)
(root / "benchmark.json").write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
