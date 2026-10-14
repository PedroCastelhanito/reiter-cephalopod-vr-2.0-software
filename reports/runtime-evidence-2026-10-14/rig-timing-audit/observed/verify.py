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

output.write_text(json.dumps(result,indent=2))
