"""Current camera argv plus live NVENC session identity; generated frames only."""
import os
from pathlib import Path
_dll_handles = [os.add_dll_directory(str(Path('C:/Users/ReiterU_PC/miniforge3/envs/CephVR') / suffix)) for suffix in ('', 'DLLs', 'Library/bin')]
import dataclasses
import json
import shutil
import subprocess
import time
from uuid import uuid4
import numpy as np
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.shared.encoder_probe import ProbeResult
from cephvr.shared.ffmpeg_capabilities import probe_nvenc_capabilities
from cephvr.shared.ffmpeg_validation import validate_arguments
from cephvr.acquisition.recording.encoding import build_command
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.v1 import camera_pb2 as camera

out = Path(__file__).parent
ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
assert ffmpeg and ffprobe
class Probe:
    def run(self, exe, args, *, deadline_ns):
        result = subprocess.run([exe,*args],capture_output=True,text=True,timeout=max(.001,(deadline_ns-time.perf_counter_ns())/1e9))
        return ProbeResult(result.returncode,result.stdout,result.stderr)
caps = probe_nvenc_capabilities(ffmpeg,codec='h264_nvenc',nvenc_owner=NvencProbeOwner(),probe=Probe(),deadline_ns=time.perf_counter_ns()+30_000_000_000)
assert caps.encoder_gpu_ordinal == 1 and caps.device_uuid == 'GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc'
config=json.loads(Path('config/last_configuration.json').read_text(encoding='utf-8'))['configuration']
settings=next(b['acquisition'] for b in config['backends'] if 'acquisition' in b)
records=[]
attempt=str(time.time_ns())
for role in ('behavioral','tracking','eye_tracking'):
    selected=settings[role]
    device=selected['device']['settings']
    roi=device['roi']
    raw_format='gray' if device['pixel_format']=='Mono8' else 'rgb24'
    args=selected['ffmpeg_args']['values']
    effective=validate_arguments(args,capabilities=caps,input_pixel_format=raw_format,recording_bit_depth=8,input_width=roi['width'],input_height=roi['height'],owner=role)
    clock=camera.CameraClockDescriptor(device_id='synthetic-only',conversion_available=False,timestamp_source='unavailable',timestamp_semantics='none',reset_semantics='none',wrap_semantics='none',unavailable_reason='generated frames; no camera',counter_source='unavailable',counter_semantics='none',counter_width_bits=0,counter_wrap_semantics='none',counter_unavailable_reason='generated frames; no camera')
    identity=RecordingIdentity(str(uuid4()),str(uuid4()),1,role,'synthetic-only','synthetic-only.json',clock)
    video=out/f'synthetic-gpu-check-{attempt}-{role}.mp4'
    command=build_command(executable=ffmpeg,user_args=args,effective=effective,width=roi['width'],height=roi['height'],nominal_rate_hz=device['frame_rate_hz'],fragment_target_ns=1_000_000_000,video_path=str(video),identity=identity)
    command[1:1]=['-loglevel','verbose']
    assert command[command.index('-gpu')+1]=='1'
    channels=1 if raw_format=='gray' else 3
    payload=np.zeros((roi['height'],roi['width'],channels),dtype=np.uint8).tobytes()
    with (out/f'{attempt}-{role}-encoder.stderr.log').open('wb') as err, (out/f'{attempt}-{role}-encoder.stdout.log').open('wb') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=err)
        try:
            process.stdin.write(payload)
            process.stdin.flush()
            deadline=time.monotonic()+8
            session_text=''
            while time.monotonic()<deadline:
                try:
                    query=subprocess.run(['nvidia-smi','encodersessions','-i',caps.device_uuid],capture_output=True,text=True,timeout=2)
                    session_text=query.stdout+query.stderr
                except subprocess.TimeoutExpired as sample:
                    def sample_text(value):
                        return value if isinstance(value,str) else (value or b'').decode(errors='replace')
                    session_text=sample_text(sample.stdout)+sample_text(sample.stderr)
                if str(process.pid) in session_text:
                    break
                if process.poll() is not None:
                    raise RuntimeError(f'{role} encoder exited before session query')
                time.sleep(.2)
            (out/f'{role}-nvenc-session.txt').write_text(session_text,encoding='utf-8')
            assert str(process.pid) in session_text, session_text
            process.stdin.write(payload*3)
            process.stdin.close()
            assert process.wait(timeout=20)==0,(out/f'{attempt}-{role}-encoder.stderr.log').read_text(errors='replace')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    probe=subprocess.run([ffprobe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)],capture_output=True,text=True,timeout=10)
    assert probe.returncode==0
    details=json.loads(probe.stdout)
    assert int(details['streams'][0]['nb_read_frames'])==4
    records.append({'role':role,'source_kind':'generated frames; no camera opened','source_format':device['pixel_format'],'input_format':raw_format,'command':command,'resolved':dataclasses.asdict(effective),'pid':process.pid,'nvenc_session_gpu_uuid':caps.device_uuid,'frames':4,'ffprobe':details})
    (out/'encoder_check.json').write_text(json.dumps({'scope':'production camera command builders, actual NVENC sessions, generated frames only','ffmpeg':ffmpeg,'gpu_uuid':caps.device_uuid,'gpu_ordinal':caps.encoder_gpu_ordinal,'records':records},indent=2)+'\n',encoding='utf-8')
    print('PASS',role,'actual NVENC session on RTX2080Ti/index1, four frames',flush=True)
