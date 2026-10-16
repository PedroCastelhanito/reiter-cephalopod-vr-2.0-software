"""Twenty-frame production Bayer preparation timing, no camera or encoder opened."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from pypylon import pylon

from cephvr.shared.pixels.preparer import PixelPreparer
from cephvr.shared.pixels.types import NativePixelFormat, PixelLayout

out=Path(__file__).parent
width,height=1760,1716
layout=PixelLayout(width,height,NativePixelFormat("BayerRG8",int(pylon.PixelType_BayerRG8),8,"bayer_rg","unpacked","byte","lsb"),width,width*height)
rng=np.random.default_rng(20261016)
buffers=[bytearray(rng.integers(0,256,(height,width),dtype=np.uint8).tobytes()) for _ in range(8)]
preparer=PixelPreparer(layout)
target=bytearray(width*height*3)
conversion=[];total=[]
original=preparer._convert
def timed_convert(pixels):
    start=time.perf_counter_ns()
    try:return original(pixels)
    finally:conversion.append(time.perf_counter_ns()-start)
preparer._convert=timed_convert
try:
    threads=str(preparer._converter.MaxNumThreads) if hasattr(preparer._converter,"MaxNumThreads") else None
    for index in range(20):
        start=time.perf_counter_ns()
        prepared=preparer.prepare_recording_into(buffers[index%8],target,target_bits=8)
        total.append(time.perf_counter_ns()-start)
        assert len(prepared.data)==len(target)
finally:preparer.close()
result={"scope":"Offline exact production PixelPreparer, synthetic8-bitBayer pool,20calls; includes attachment/conversion/outputcopy, no camera/FFmpeg/storage/queue load","dimensions":[width,height],"seed":20261016,"converter_max_threads":threads,"source_sha256":[hashlib.sha256(b).hexdigest() for b in buffers],"output_bytes":len(target),"samples_ns":{"prepare_total":total,"attach_and_convert":conversion,"remaining_validation_copy_release":[a-b for a,b in zip(total,conversion)]}}
result["summary_ns"]={name:{"mean":float(np.mean(samples)),"p50":float(np.percentile(samples,50)),"p95":float(np.percentile(samples,95)),"max":max(samples)} for name,samples in result["samples_ns"].items()}
(out/"pixel-preparation-profile.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result["summary_ns"],indent=2),flush=True)
