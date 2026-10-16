"""One full decode/count/pixel comparison for the matched HEVC experiment."""
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time

import numpy as np

out=Path(__file__).parent
label="capacity-hevc-lossless-r1"
experiment=json.loads((out/label/"results.json").read_text(encoding="utf-8"))
media=out.resolve().parents[2]/".tmp"/"encoding-audit-20261016"/label
rng=np.random.default_rng(20261016)
result={"scope":"Full decoded-frame count and prepared-sample equality; same8frame deterministic pool as H264 comparison", "streams":{}}
for name,width,height,channels in (("behavior",1760,1716,3),("tracking",1588,1344,1),("stimulus",1280,1000,4)):
    frames=rng.integers(0,256,(8,height,width,channels),dtype=np.uint8)
    if channels==4:frames[...,3]=255
    hashes=[hashlib.sha256(frame.tobytes()).hexdigest() for frame in frames]
    assert hashes==experiment["fixture_sha256"][name]
    path=media/(name+".mp4")
    probe=subprocess.run(["ffprobe","-v","error","-show_streams","-of","json",str(path)],capture_output=True,timeout=15)
    row=result["streams"][name]={"probe_exit":probe.returncode,"probe":json.loads(probe.stdout),"frame_count":0}
    fmt="yuv420p" if name=="tracking" else "rgb24" if name=="behavior" else "rgba"
    frame_bytes=width*height*(3//1 if name=="behavior" else 4 if name=="stimulus" else 1)
    if name=="tracking":frame_bytes=width*height*3//2
    command=["ffmpeg","-hide_banner","-v","error","-threads","4","-filter_threads","1","-i",str(path),"-pix_fmt",fmt,"-f","rawvideo","pipe:1"]
    row["decode_command"]=command
    stderr_path=out/(name+"-hevc-decode.stderr")
    with stderr_path.open("wb") as stderr:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=stderr)
        timer=threading.Timer(180,lambda:process.terminate() if process.poll() is None else None)
        timer.start();started=time.perf_counter_ns()
        actual_hash,expected_hash=hashlib.sha256(),hashlib.sha256()
        exact=True;maximum=0
        try:
            expected_count=experiment["streams"][name]["expected_frames"]
            for index in range(expected_count):
                content=process.stdout.read(frame_bytes)
                assert len(content)==frame_bytes,(name,index,len(content),frame_bytes)
                actual=np.frombuffer(content,dtype=np.uint8)
                if name=="tracking":actual=actual[:width*height]
                expected=frames[index%8].reshape(-1)
                if name!="stimulus":
                    delta=np.abs(actual.astype(np.int16)-expected.astype(np.int16))
                    maximum=max(maximum,int(delta.max()));exact &= np.array_equal(actual,expected)
                    actual_hash.update(actual.tobytes());expected_hash.update(expected.tobytes())
                row["frame_count"]+=1
            assert not process.stdout.read(1),"unexpected extra decoded frames"
            row["exit"]=process.wait(timeout=5)
        finally:
            timer.cancel()
            if process.poll() is None:process.terminate();process.wait(timeout=5)
            row["process_absent"]=process.poll() is not None
        row["decode_elapsed_ns"]=time.perf_counter_ns()-started
        row["count_matches"]=row["frame_count"]==expected_count
        if name!="stimulus":row["prepared_pixel_reference"]={"byte_exact":bool(exact),"maximum_sample_error":maximum,"source_sha256":expected_hash.hexdigest(),"decoded_sha256":actual_hash.hexdigest(),"scope":"RGBsamples" if name=="behavior" else "grayversusstoredluma"}
    (out/"capacity-hevc-decode.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(name,row["frame_count"],row.get("prepared_pixel_reference"),flush=True)
assert all(r["exit"]==0 and r["count_matches"] and r.get("prepared_pixel_reference",{}).get("byte_exact",True) for r in result["streams"].values())
