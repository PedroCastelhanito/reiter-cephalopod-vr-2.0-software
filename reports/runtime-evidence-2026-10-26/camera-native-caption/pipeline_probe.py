"""Generated pixels at retained camera layouts; no hardware or shared capture state."""
import json
import statistics
import time
import numpy as np
import cv2
from cephvr.acquisition.camera.native_formats import pylon_pixel_format
from cephvr.acquisition.preview.highgui import display_array
from cephvr.acquisition.preview.viewport import SquareViewport
from cephvr.shared.pixels import preparer as module
from cephvr.shared.pixels.types import PixelLayout

from pathlib import Path
import runpy
Baseline = runpy.run_path(str(Path(__file__).with_name("baseline_preparer.py")))["PixelPreparer"]
results = []
for name, width, height, symbol in (("behavior",2456,2568,"BayerRG8"),("tracking",1588,1344,"Mono8")):
    layout = PixelLayout(width,height,pylon_pixel_format(symbol),width,width*height)
    pixels = bytearray(np.arange(width*height,dtype=np.uint8))
    preparer = Baseline(layout)
    viewport = SquareViewport(width,height,360)
    reference = bytes(preparer.prepare_preview(pixels).data)
    for variant, constructor in (("baseline",Baseline),("identity-copy",module.PixelPreparer)):
        preparer = constructor(layout)
        samples = {"prepare":[],"channel_order":[],"viewport":[]}
        for _ in range(25):
            a=time.perf_counter_ns()
            frame=preparer.prepare_preview(pixels)
            b=time.perf_counter_ns()
            image=display_array(frame,np)
            c=time.perf_counter_ns()
            viewport.render(image,cv2,np)
            d=time.perf_counter_ns()
            for key,value in zip(samples,((b-a)/1e6,(c-b)/1e6,(d-c)/1e6)):
                samples[key].append(value)
        assert bytes(frame.data)==reference
        results.append({"camera":name,"variant":variant,"median_ms":{k:statistics.median(v) for k,v in samples.items()}})
Path(__file__).with_name("pipeline-result.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
print(json.dumps(results,indent=2))
