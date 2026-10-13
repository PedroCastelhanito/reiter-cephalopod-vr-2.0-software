"""External decoder and measured submission/cadence evidence for the rig audit."""
import collections
import hashlib
import json
import shutil
import statistics
import subprocess
from pathlib import Path

OUT = Path(__file__).parent.resolve()
run = json.loads((OUT / 'stimulus.json').read_text())['checks']
final = run['final']
folder = Path(final['session']['directory']) / 'protocol-data'
result = {'session': final['session'], 'trial': final['trial'],
          'reservation': final['reservation'], 'metadata': final['metadata'],
          'tools': {}, 'videos': {}}
for name in ('ffmpeg','ffprobe'):
    path = shutil.which(name)
    result['tools'][name] = {'path':path,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
for video in folder.glob('*.mp4'):
    probe_command = [shutil.which('ffprobe'),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)]
    probe = subprocess.run(probe_command,capture_output=True,text=True,timeout=60)
    decode_command = [shutil.which('ffmpeg'),'-v','error','-hwaccel','none','-i',str(video),'-map','0:v:0','-f','null','-']
    decode = subprocess.run(decode_command,capture_output=True,text=True,timeout=120)
    (OUT / (video.stem+'-decode.log')).write_text(decode.stderr,encoding='utf-8')
    data = json.loads(probe.stdout) if probe.returncode == 0 else {'error':probe.stderr}
    rows = [json.loads(x)['payload'] for x in video.with_name(video.stem+'_frames.jsonl').read_text().splitlines()]
    groups = [r for r in rows if r['kind']=='render_group']
    times = [r['state']['evaluation_host_ns'] for r in groups]
    intervals = [(b-a)/1e6 for a,b in zip(times,times[1:])]
    durations = collections.defaultdict(list)
    summed = []
    for g in groups:
        values = []
        for s in g['submissions']:
            if s['return_host_ns'] is not None:
                ms = (s['return_host_ns']-s['entry_host_ns'])/1e6
                durations[s['output_id']].append(ms)
                values.append(ms)
        summed.append(sum(values))
    elapsed = (int(final['trial']['actual_end_monotonic_ns'])-int(final['trial']['start_monotonic_ns']))/1e9
    def stats(values):
        return {'median_ms':statistics.median(values),'max_ms':max(values),'mean_ms':statistics.mean(values)} if values else {}
    details = {'ffprobe_command':probe_command,'ffprobe_exit':probe.returncode,'ffprobe':data,
               'decode_command':decode_command,'decode_exit':decode.returncode,'decode_stderr':decode.stderr,
               'trial_duration_s':elapsed,'render_groups':len(groups),'render_groups_per_s':len(groups)/elapsed,
               'group_intervals':stats(intervals),'swap_durations':{k:stats(v) for k,v in durations.items()},
               'summed_swap_durations':stats(summed),
               'capture_dispositions':dict(collections.Counter(c['disposition'] for g in groups for c in g['captures'])),
               'completion_records':[r for r in rows if r['kind'] in ('completion','encoder_outcome')],
               'recipe_digest_matches':hashlib.sha256(video.with_name(video.stem+'_LOG.json').read_bytes()).hexdigest()==rows[0]['recipe']['sha256']}
    result['videos'][video.name] = details
    print(video.name,'probe',probe.returncode,'decode',decode.returncode,'groups/s',details['render_groups_per_s'],flush=True)
(OUT / 'output-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
