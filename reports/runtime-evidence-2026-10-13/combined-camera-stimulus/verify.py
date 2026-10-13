"""External cadence/accounting, CPU decoding and live physical-GPU evidence."""
import collections
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

OUT = Path(__file__).parent.resolve()
label = sys.argv[1] if len(sys.argv)>1 else 'run'
checks = json.loads((OUT / (label+'.json')).read_text())['checks']
output = OUT/(label+'-verification.json' if label!='run' else 'verification.json')
final = checks['final']
folder = Path(final['session']['directory']) / 'protocol-data'
duration = (int(final['trial']['actual_end_monotonic_ns']) - int(final['trial']['start_monotonic_ns'])) / 1e9
result = dict(session=final['session'], trial=final['trial'], reservation=final['reservation'], errors=final['errors'], configuration_restored=checks.get('configuration_restored'), tools={}, videos={})
for tool in ('ffprobe','ffmpeg'):
    path = shutil.which(tool)
    result['tools'][tool] = dict(path=path, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
def stats(values):
    if not values:
        return {}
    return dict(min_ms=min(values), median_ms=statistics.median(values), mean_ms=statistics.mean(values), p99_ms=sorted(values)[int((len(values)-1)*.99)], max_ms=max(values))
for video in folder.glob('*.mp4'):
    probe_command = [result['tools']['ffprobe']['path'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)]
    probe = subprocess.run(probe_command,capture_output=True,text=True,timeout=90)
    decode_command = [result['tools']['ffmpeg']['path'],'-v','error','-hwaccel','none','-i',str(video),'-map','0:v:0','-f','null','-']
    decode = subprocess.run(decode_command,capture_output=True,text=True,timeout=120)
    rows = [json.loads(line) for line in video.with_name(video.stem+'_frames.jsonl').read_text().splitlines()]
    details = dict(ffprobe_command=probe_command, ffprobe_exit=probe.returncode, ffprobe=json.loads(probe.stdout) if probe.returncode==0 else {'error':probe.stderr}, decode_command=decode_command, decode_exit=decode.returncode, decode_stderr=decode.stderr, trial_duration_s=duration)
    if 'stimulus' in video.stem:
        payloads = [row['payload'] for row in rows]
        groups = [row for row in payloads if row['kind']=='render_group']
        times = [row['state']['evaluation_host_ns'] for row in groups]
        details.update(render_groups=len(groups), real_groups_per_s=len(groups)/duration,
            group_intervals=stats([(b-a)/1e6 for a,b in zip(times,times[1:])]),
            capture_dispositions=dict(collections.Counter(capture['disposition'] for group in groups for capture in group['captures'])),
            completion_records=[row for row in payloads if row['kind'] in ('encoder_outcome','completion')],
            recipe_digest_matches=hashlib.sha256(video.with_name(video.stem+'_LOG.json').read_bytes()).hexdigest()==payloads[0]['recipe']['sha256'])
    else:
        frames = [row for row in rows if row['type']=='frame']
        times = [row['host_receipt_ns'] for row in frames]
        details.update(header=rows[0],received_frames=len(frames),received_frames_per_s=len(frames)/duration,
            receipt_intervals=stats([(b-a)/1e6 for a,b in zip(times,times[1:])]),
            dropped_frames=sum(row['dropped'] for row in frames), invalid_frames=sum(row.get('invalid_code') is not None for row in frames),
            video_dispositions=dict(collections.Counter(row['disposition'] for row in rows if row['type']=='video_frame')),
            completion_records=[row for row in rows if row['type'] not in ('header','frame','video_frame')])
    result['videos'][video.name] = details
    output.write_text(json.dumps(result,indent=2))
    print(video.name, json.dumps({key:value for key,value in details.items() if key in ('ffprobe_exit','decode_exit','real_groups_per_s','received_frames','received_frames_per_s','dropped_frames','invalid_frames','capture_dispositions','video_dispositions')}),flush=True)
process_file = OUT/(label.replace('-combined','')+'-processes.json' if label!='run' else 'live-processes.json')
processes = json.loads(process_file.read_text())
renderer = next(row for row in processes if 'cephvr.visual_stimulus.worker.main' in row['CommandLine'])
encoders = [row for row in processes if 'ffmpeg.exe' in row['CommandLine']]
gpu0='GPU-77642118-1623-48dd-3686-1014aa86b818'
gpu1='GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc'
gpu_evidence = dict(renderer=renderer, encoders=encoders, rendering_gpu_uuid=gpu0,encoding_gpu_uuid=gpu1,samples=[])
for sample in checks['gpu_samples']:
    apps = next(value['stdout'] for key,value in sample['queries'].items() if '--query-compute-apps=' in key)
    sessions = next(value['stdout'] for key,value in sample['queries'].items() if 'encodersessions' in key)
    gpu_evidence['samples'].append(dict(host_ns=sample['host_monotonic_ns'],
        renderer_on_gpu0=any(line.startswith(str(renderer['ProcessId'])+', '+gpu0+',') for line in apps.splitlines()),
        encoders_on_gpu1={str(row['ProcessId']): any(line.startswith(str(row['ProcessId'])+', '+gpu1+',') for line in apps.splitlines()) for row in encoders},
        live_nvenc_gpu1_pids=sorted({int(line.split()[2]) for line in sessions.splitlines() if line.strip() and line.split()[0]=='1'})))
result['gpu_evidence']=gpu_evidence
result['metadata_tail']=[json.loads(line) for line in (folder/'SESSION_LOG.jsonl').read_text().splitlines()[-8:]]
result['provenance']=dict(date='2026-10-13',scope='single sixty-second open-loop real Behavior/Tracking camera plus four-output stimulus recording; Eye/locomotion tracking/SpikeGLX disabled; no optical or electrical timing claim',head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),working_tree='shared dirty tree;125ms all margins; current rendering/reset/boundary repairs; source hashes in context.json')
output.write_text(json.dumps(result,indent=2))
print('GPU evidence',json.dumps(gpu_evidence['samples']),flush=True)
