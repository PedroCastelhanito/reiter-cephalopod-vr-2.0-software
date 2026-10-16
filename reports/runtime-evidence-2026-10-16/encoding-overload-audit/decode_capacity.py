"""Decode/count all capacity media and independently verify lossless source pixels."""
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

out = Path(__file__).parent
root = out.resolve().parents[2]
media = root / ".tmp" / "encoding-audit-20261016"
rng = np.random.default_rng(20261016)
pools = {}
for name, width, height, channels in (("behavior",1760,1716,3),("tracking",1588,1344,1),("stimulus",1280,1000,4)):
    frames = rng.integers(0,256,(8,height,width,channels),dtype=np.uint8)
    if channels == 4:
        frames[...,3] = 255
    pools[name] = frames
results = {}
for folder in sorted(out.glob("capacity-*")):
    if not folder.is_dir():
        continue
    experiment = json.loads((folder/"results.json").read_text())
    cases = results[folder.name] = {}
    for name, source in experiment["streams"].items():
        path = media/folder.name/(name+".mp4")
        command = ["ffprobe","-v","error","-count_frames","-show_streams","-of","json",str(path)]
        probe = subprocess.run(command,capture_output=True,timeout=30)
        row = cases[name] = {"probe_exit":probe.returncode,"probe":json.loads(probe.stdout),"command":command}
        decode = subprocess.run(["ffmpeg","-hide_banner","-v","error","-threads","2","-i",str(path),"-f","null","-"],capture_output=True,timeout=60)
        row.update(decode_exit=decode.returncode,decode_stderr=decode.stderr.decode(errors="replace"))
        row["count_matches"] = int(row["probe"]["streams"][0]["nb_read_frames"]) == source["expected_frames"]
        if experiment["arguments"]["lossless_camera"] and name in {"behavior","tracking"}:
            # Tracking compares the stored luma directly; generic gray extraction can rescale.
            fmt = "rgb24" if name == "behavior" else "yuv420p"
            command = ["ffmpeg","-hide_banner","-v","error","-threads","2","-filter_threads","1","-i",str(path),"-pix_fmt",fmt,"-f","rawvideo","pipe:1"]
            process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            width,height=source["dimensions"]
            frame_bytes=width*height*(3 if name=="behavior" else 3)/ (1 if name=="behavior" else 2)
            frame_bytes=int(frame_bytes)
            exact=True
            decoded_hash,source_hash=hashlib.sha256(),hashlib.sha256()
            maximum=0
            for index in range(source["expected_frames"]):
                content=process.stdout.read(frame_bytes)
                assert len(content)==frame_bytes
                actual=np.frombuffer(content,dtype=np.uint8)
                if name=="tracking":
                    actual=actual[:width*height]
                expected=pools[name][index%8].reshape(-1)
                maximum=max(maximum,int(np.abs(actual.astype(np.int16)-expected.astype(np.int16)).max()))
                exact=exact and np.array_equal(actual,expected)
                decoded_hash.update(actual.tobytes()); source_hash.update(expected.tobytes())
            assert not process.stdout.read(1)
            stderr=process.stderr.read()
            row["pixel_reference"]={"byte_exact":exact,"maximum_sample_error":maximum,"source_sha256":source_hash.hexdigest(),"decoded_sha256":decoded_hash.hexdigest(),"exit":process.wait(timeout=10),"stderr":stderr.decode(errors="replace"),"scope":"Prepared RGB samples" if name=="behavior" else "Prepared gray samples versus stored luma plane"}
    (out/"capacity-decode.json").write_text(json.dumps(results,indent=2)+"\n")
print(json.dumps({case:{name:{k:v for k,v in row.items() if k not in {"probe","command"}} for name,row in cases.items()} for case,cases in results.items()},indent=2))
assert all(row["decode_exit"]==0 and row["count_matches"] and row.get("pixel_reference",{}).get("byte_exact",True) for cases in results.values() for row in cases.values())
