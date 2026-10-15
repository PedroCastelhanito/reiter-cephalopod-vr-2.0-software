"""Independent SDK/NVENC/production-shader capacity; no managed acceptance claim."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time

import cv2
from google.protobuf.json_format import ParseDict
import moderngl
import numpy as np
from pypylon import pylon

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.rendering.shaders import _LAYER_FRAGMENT, _QUAD_VERTEX

parser = argparse.ArgumentParser()
parser.add_argument("--cq", type=int, required=True)
parser.add_argument("--seconds", type=int, default=30)
parser.add_argument("--label", required=True)
parser.add_argument("--pattern", choices=("gaussian", "grating"), default="gaussian")
parser.add_argument("--native-behavior", action="store_true")
parser.add_argument("--monitor", action="store_true")
args = parser.parse_args()
root = Path.cwd()
out = Path(__file__).parent / args.label
out.mkdir(exist_ok=False)
media = root / ".tmp" / args.label
media.mkdir(parents=True, exist_ok=False)
monitor = None
if args.monitor:
    monitor = subprocess.Popen(
        [str(root / ".venv/Scripts/python.exe"), str(root / "reports/runtime-evidence-2026-10-15/open-loop-soak/resume-1/monitor.py"), "--output", str(out / "monitor.jsonl"), "--stop", str(out / "monitor.stop")],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    limit = time.monotonic() + 10
    while not (out / "monitor.jsonl").exists():
        if monitor.poll() is not None or time.monotonic() >= limit:
            raise RuntimeError("monitor did not start")
        time.sleep(0.05)
config = ParseDict(json.loads((Path(__file__).parent / "original-settings/last_configuration.json").read_text())["configuration"], pb.ExperimentConfiguration())
acquisition = next(b.acquisition for b in config.backends if b.backend_name == "acquisition")
gpu = subprocess.run(["nvidia-smi", "--query-gpu=index,name,uuid", "--format=csv,noheader"], capture_output=True, text=True, check=True).stdout
encoding = [row for row in gpu.splitlines() if "RTX 2080 Ti" in row]
assert len(encoding) == 1
gpu_index = encoding[0].split(",")[0].strip()
record = {"scope": "Independent explicitly unaligned SDK streams plus four offscreen production layer shaders and three FFmpeg streams; no managed protocol, calibrated projection, optical timing or Tracking processing acceptance", "cq": args.cq, "seconds": args.seconds, "pattern": args.pattern, "native_behavior": args.native_behavior, "gpu_inventory": gpu, "media_root": str(media), "sources": {}}
deadline = [0.0]
barrier = threading.Barrier(3, action=lambda: deadline.__setitem__(0, time.monotonic() + args.seconds), timeout=20)
owned_encoders = []


def stop_owned_encoders():
    record["watchdog_expired"] = True
    for process in owned_encoders:
        if process.poll() is None:
            process.terminate()


watchdog = threading.Timer(args.seconds + 45, stop_owned_encoders)
watchdog.daemon = True
watchdog.start()


def encoder(name, width, height, rate, fmt, values):
    path = media / f"{name}.mp4"
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-f", "rawvideo", "-pixel_format", fmt, "-video_size", f"{width}x{height}", "-framerate", str(rate), "-i", "pipe:0", "-an", *values, "-gpu", gpu_index, "-bf", "0", str(path)]
    log = (out / f"{name}-ffmpeg.log").open("w", encoding="utf-8")
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    owned_encoders.append(process)
    return process, log, path, command


def camera_source(name):
    setting = getattr(acquisition, name)
    factory = pylon.TlFactory.GetInstance()
    info = next(d for d in factory.EnumerateDevices() if d.GetSerialNumber() == setting.device.device_id)
    camera = pylon.InstantCamera(factory.CreateDevice(info))
    process = log = None
    baseline = None
    result = {"serial": info.GetSerialNumber(), "frames": 0, "failed_grabs": 0, "frame_ids": [], "host_ns": [], "write_ns": []}
    try:
        camera.Open()
        baseline = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap())
        (out / f"{name}-before.pfs").write_text(baseline, encoding="utf-8")
        requested_pfs = setting.device.pfs_baseline.text
        if name == "behavioral" and args.native_behavior:
            requested_pfs = (Path(__file__).parent / f"camera-{setting.device.device_id}-baseline.pfs").read_text()
        pylon.FeaturePersistence.LoadFromString(requested_pfs, camera.GetNodeMap(), True)
        camera.TriggerSelector.Value = "FrameStart"
        camera.TriggerMode.Value = "Off"
        camera.AcquisitionFrameRateEnable.Value = True
        rate = setting.device.settings.frame_rate_hz
        camera.AcquisitionFrameRate.Value = rate
        width, height = int(camera.Width.Value), int(camera.Height.Value)
        result.update(width=width, height=height, requested_hz=rate, actual_hz=float(camera.AcquisitionFrameRate.Value), pixel_format=str(camera.PixelFormat.Value))
        result["exposure_us"] = float(camera.ExposureTime.Value)
        (out / f"{name}-effective.pfs").write_text(pylon.FeaturePersistence.SaveToString(camera.GetNodeMap()), encoding="utf-8")
        converter = pylon.ImageFormatConverter()
        converter.OutputPixelFormat = pylon.PixelType_RGB8packed if name == "behavioral" else pylon.PixelType_Mono8
        converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
        values = list(setting.ffmpeg_args.values)
        values[values.index("-cq") + 1] = str(args.cq)
        process, log, path, command = encoder(name, width, height, rate, "rgb24" if name == "behavioral" else "gray", values)
        result["command"] = command
        camera.MaxNumBuffer = 15
        camera.StartGrabbing(pylon.GrabStrategy_OneByOne, pylon.GrabLoop_ProvidedByUser)
        barrier.wait()
        while time.monotonic() < deadline[0]:
            grab = camera.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
            try:
                now = time.perf_counter_ns()
                if not grab.GrabSucceeded():
                    result["failed_grabs"] += 1
                    continue
                converted = converter.Convert(grab)
                pixels = converted.GetArray()
                begin = time.perf_counter_ns()
                process.stdin.write(pixels.tobytes())
                converted.Release()
                result["write_ns"].append(time.perf_counter_ns() - begin)
                result["host_ns"].append(now)
                result["frame_ids"].append(int(grab.GetBlockID()))
                result["frames"] += 1
            finally:
                grab.Release()
        camera.StopGrabbing()
        process.stdin.close()
        result["encoder_exit"] = process.wait(timeout=20)
        result["bytes"] = path.stat().st_size
        assert result["encoder_exit"] == 0
    finally:
        if camera.IsGrabbing():
            camera.StopGrabbing()
        if camera.IsOpen():
            try:
                if baseline is not None:
                    pylon.FeaturePersistence.LoadFromString(baseline, camera.GetNodeMap(), True)
                    restored = pylon.FeaturePersistence.SaveToString(camera.GetNodeMap())
                    (out / f"{name}-restored.pfs").write_text(restored, encoding="utf-8")
                    result["pfs_exact_restored"] = restored == baseline
            except Exception as error:
                result["restoration_error"] = str(error)
            finally:
                camera.Close()
        result["camera_closed"] = not camera.IsOpen()
        if process is not None and process.poll() is None:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            result["encoder_exit"] = process.wait(timeout=20)
        if log is not None:
            log.close()
        (out / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def render_source():
    ctx = moderngl.create_standalone_context(require=430)
    assert "5060 Ti" in ctx.info["GL_RENDERER"], ctx.info["GL_RENDERER"]
    program = ctx.program(vertex_shader=_QUAD_VERTEX, fragment_shader=_LAYER_FRAGMENT)
    quad = ctx.buffer(np.array([-1,-1,0,0, 1,-1,1,0, -1,1,0,1, 1,1,1,1], dtype="f4").tobytes())
    vao = ctx.vertex_array(program, [(quad, "2f 2f", "in_position", "in_uv")])
    rng = np.random.default_rng(17015)
    noise = np.clip(rng.normal(0.5, 0.17, (256,256)), 0, 1)
    texture = ctx.texture((256,256),4,np.stack((noise,noise,noise,np.ones_like(noise)),axis=-1).astype("f4").tobytes(),dtype="f4")
    texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
    texture.use(0)
    uniforms = {"image_tex":0,"mode":4 if args.pattern == "gaussian" else 1,"mean_rgb":(0.5,0.5,0.5),"modulation_rgb":(0.5,0.5,0.5),"contrast":1.0,"opacity":1.0,"frequency":(8,8),"phase":(0,0),"period":(4,4)}
    for name,value in uniforms.items():
        if name in program:
            program[name].value = value
    flags = ctx.buffer(reserve=16)
    flags.bind_to_storage_buffer(3)
    targets = [ctx.simple_framebuffer(size,components=4) for size in ((1280,720),(1280,720),(1280,720),(720,1280))]
    values = ["-c:v","h264_nvenc","-preset","p4","-rc","vbr","-cq",str(args.cq),"-b:v","0","-pix_fmt","yuv420p"]
    process,log,path,command = encoder("stimulus",1280,720,60,"rgb24",values)
    result = {"renderer":ctx.info["GL_RENDERER"],"frames":0,"command":command,"submission_ns":[],"render_ns":[],"source":"production _LAYER_FRAGMENT Gaussian tile; four native-sized offscreen outputs; resized review mosaic"}
    try:
        barrier.wait()
        next_frame = time.monotonic()
        while time.monotonic() < deadline[0]:
            begin = time.perf_counter_ns()
            program["phase"].value = (0.0, -0.2 * result["frames"] / 60)
            views = []
            for target in targets:
                target.use()
                ctx.viewport = (0,0,*target.size)
                vao.render(moderngl.TRIANGLE_STRIP)
                pixels = np.frombuffer(target.read(components=3,alignment=1),dtype=np.uint8).reshape(target.size[1],target.size[0],3)
                views.append(cv2.resize(pixels,(640,360),interpolation=cv2.INTER_AREA))
            frame = np.concatenate((np.concatenate(views[:2],axis=1),np.concatenate(views[2:],axis=1)),axis=0)
            process.stdin.write(frame.tobytes())
            result["render_ns"].append(time.perf_counter_ns()-begin)
            result["submission_ns"].append(begin)
            result["frames"] += 1
            next_frame += 1/60
            time.sleep(max(0,next_frame-time.monotonic()))
        process.stdin.close()
        result["encoder_exit"] = process.wait(timeout=20)
        result["bytes"] = path.stat().st_size
        assert result["encoder_exit"] == 0
    finally:
        if process.poll() is None:
            process.stdin.close()
            result["encoder_exit"] = process.wait(timeout=20)
        log.close()
        ctx.release()
        (out / "stimulus.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


with ThreadPoolExecutor(max_workers=2) as pool:
    cameras = {name: pool.submit(camera_source,name) for name in ("behavioral","tracking")}
    try:
        record["sources"]["stimulus"] = render_source()
        for name,future in cameras.items():
            record["sources"][name] = future.result()
    except BaseException:
        barrier.abort()
        raise
    finally:
        watchdog.cancel()
        if monitor is not None:
            (out / "monitor.stop").write_text("complete\n", encoding="utf-8")
            record["monitor_exit"] = monitor.wait(timeout=15)
        (out / "summary.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
print(json.dumps({name:{key:value for key,value in result.items() if key not in {"host_ns","frame_ids","write_ns","submission_ns","render_ns"}} for name,result in record["sources"].items()},indent=2))
