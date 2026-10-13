"""Eight generated frames per encoding case; no camera or scientific footage."""
import dataclasses
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4
import numpy as np
from cephvr.acquisition.recording.encoding import build_command
from cephvr.acquisition.recording.identity import RecordingIdentity
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.shared.ffmpeg_types import ResolvedEncoding
from cephvr.visual_stimulus.config.models.artifact_models import ReviewEncoding
from cephvr.visual_stimulus.recording.encoding import build_review_argv

ROOT=Path.cwd(); OUT=Path(__file__).parent
BIN=ROOT/'.tmp/ffmpeg-toolchain/extracted/ffmpeg-9.0.2-essentials_build/bin'
audit=json.loads((OUT/'audit.json').read_text()); records=[]
for role,candidate in audit['camera_candidates'].items():
    for label,entry in candidate['entries'].items():
        effective=ResolvedEncoding(**entry['resolved'])
        path=OUT/f'synthetic-v2-{role}-{label}.mp4'
        clock=camera.CameraClockDescriptor(device_id='synthetic-only',conversion_available=False,timestamp_source='unavailable',timestamp_semantics='none',reset_semantics='none',wrap_semantics='none',unavailable_reason='generated frames; no camera',counter_source='unavailable',counter_semantics='none',counter_width_bits=0,counter_wrap_semantics='none',counter_unavailable_reason='generated frames; no camera')
        identity=RecordingIdentity(str(uuid4()),str(uuid4()),1,role,'synthetic-only','synthetic-only.json',clock)
        command=build_command(executable=str(BIN/'ffmpeg.exe'),user_args=entry['args'],effective=effective,width=effective.output_width,height=effective.output_height,nominal_rate_hz=candidate['rate'],fragment_target_ns=1_000_000_000,video_path=str(path),identity=identity)
        records.append((role+'-'+label,path,command,effective.input_pixel_format,effective.output_width,effective.output_height,effective.output_pixel_format))
review=ReviewEncoding.model_validate_json(json.dumps(audit['stimulus_current']['review']))
path=OUT/'synthetic-v2-stimulus-current.mp4'
command=build_review_argv(BIN/'ffmpeg.exe',review,output=path,fragment_target_ns=1_000_000_000)
records.append(('stimulus-current',path,command,review.input_pixel_format,review.composite_width,review.composite_height,review.encoder_pixel_format))
results=[]
for label,path,command,fmt,width,height,output_fmt in records:
    channels={'rgb24':3,'gray':1,'rgba':4}[fmt]
    plane=((np.arange(width,dtype=np.uint16)[None,:]+np.arange(height,dtype=np.uint16)[:,None])%256).astype(np.uint8)
    if channels>1:
        image=np.stack([(plane+idx*43).astype(np.uint8) for idx in range(channels)],axis=2)
        if channels==4:image[:,:,3]=255
    else:image=plane
    payload=image.tobytes()*8
    start=time.perf_counter()
    completed=subprocess.run(command,input=payload,capture_output=True,timeout=30)
    (OUT/(label+'.stderr.log')).write_bytes(completed.stderr)
    assert completed.returncode==0,completed.stderr.decode(errors='replace')
    probe=subprocess.run([str(BIN/'ffprobe.exe'),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=10)
    assert probe.returncode==0
    data=json.loads(probe.stdout); stream=data['streams'][0]
    assert int(stream['nb_read_frames'])==8 and stream['width']==width and stream['height']==height
    assert stream['color_range']=='pc'
    decoded_fmt=stream['pix_fmt'].replace('yuvj','yuv',1)
    assert decoded_fmt==output_fmt and stream['codec_name']=='h264'
    if label!='stimulus-current':assert data['format']['tags']['cephvr_device_id']=='synthetic-only'
    results.append({'label':label,'method':'eight generated pattern frames; sequential; not capture/throughput/quality acceptance','command':command,'elapsed_s':time.perf_counter()-start,'ffprobe':data})
    print('PASS',label,stream['profile'],stream['pix_fmt'],stream['nb_read_frames'],flush=True)
    (OUT/'smoke.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
