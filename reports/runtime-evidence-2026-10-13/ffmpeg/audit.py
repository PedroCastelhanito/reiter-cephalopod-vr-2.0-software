"""Bounded build/device and argument audit; no camera access or encode."""
import dataclasses
import hashlib
import json
import subprocess
import time
from pathlib import Path
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.shared.encoder_probe import ProbeResult
from cephvr.shared.ffmpeg_capabilities import probe_nvenc_capabilities
from cephvr.shared.ffmpeg_validation import validate_arguments
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.recording.encoding import prepare_review_encoding, ffmpeg_input_format

ROOT=Path.cwd()
OUT=Path(__file__).parent
BIN=ROOT/'.tmp/ffmpeg-toolchain/extracted/ffmpeg-9.0.2-essentials_build/bin'

class Probe:
    def run(self,exe,args,*,deadline_ns):
        result=subprocess.run([exe,*args],capture_output=True,text=True,timeout=max(.001,(deadline_ns-time.perf_counter_ns())/1e9))
        label='_'.join(args).replace(':','_').replace('-','')
        (OUT/(label+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        return ProbeResult(result.returncode,result.stdout,result.stderr)

def serial(value):
    if dataclasses.is_dataclass(value):return serial(dataclasses.asdict(value))
    if isinstance(value,dict):return {str(k):serial(v) for k,v in value.items()}
    if isinstance(value,(set,frozenset,tuple,list)):return [serial(v) for v in value]
    return value

record={'method':'actual build help and native RTX2080Ti capability query; no encoder stream or camera','tools':{}}
for name in ('ffmpeg','ffprobe'):
    exe=BIN/(name+'.exe'); result=subprocess.run([str(exe),'-version'],capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    record['tools'][name]={'path':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'version':result.stdout.splitlines()[0]}
    (OUT/(name+'-version.log')).write_text(result.stdout,encoding='utf-8')
caps=probe_nvenc_capabilities(str(BIN/'ffmpeg.exe'),codec='h264_nvenc',nvenc_owner=NvencProbeOwner(),probe=Probe(),deadline_ns=time.perf_counter_ns()+30_000_000_000)
record['capabilities']=serial(caps)
config=json.loads((ROOT/'config/last_configuration.json').read_text())['configuration']
acq=next(b['acquisition'] for b in config['backends'] if 'acquisition' in b)
record['camera_candidates']={}
for role,fmt,outfmt,profile in (('behavioral','rgb24','yuv444p','high444p'),('tracking','gray','yuv420p','main')):
    camera=acq[role]; settings=camera['device']['settings']; roi=settings['roi']
    current=camera['ffmpeg_args']['values']
    reference=['-c:v','h264_nvenc','-pix_fmt','+'+outfmt,'-vf',f'scale=w=iw:h=ih:in_range=full:out_range=full:out_color_matrix=bt709,format=pix_fmts={outfmt}','-color_range','pc','-colorspace','bt709','-profile:v',profile,'-preset','p3','-rc','vbr','-cq','33','-b:v','0','-maxrate','150M','-bufsize','240M','-rc-lookahead','4','-surfaces','16']
    entries={}
    for label,args in (('current',current),('reference_adapted_not_applied',reference)):
        resolved=validate_arguments(args,capabilities=caps,input_pixel_format=fmt,recording_bit_depth=8,input_width=roi['width'],input_height=roi['height'],owner=role)
        entries[label]={'args':args,'resolved':serial(resolved)}
    record['camera_candidates'][role]={'source_format':settings['pixel_format'],'rate':settings['frame_rate_hz'],'entries':entries}
visual=next(b['visual_stimulus'] for b in config['backends'] if 'visual_stimulus' in b)
display=DisplayProfile.model_validate_json(visual['display']['profile_json'])
review,resolved=prepare_review_encoding(display,ffmpeg_args=visual['review_ffmpeg_args'],capabilities=caps,input_pixel_format=ffmpeg_input_format(display),capability_evidence_id='ffmpeg-20261013-readonly-audit')
record['stimulus_current']={'review':serial(review.model_dump()),'resolved':serial(resolved)}
(OUT/'audit.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print('PASS',record['tools']['ffmpeg']['version'],caps.device_uuid,caps.encoder_gpu_ordinal)
print('Camera current/reference argument validation PASS; stimulus',review.composite_width,review.composite_height)
