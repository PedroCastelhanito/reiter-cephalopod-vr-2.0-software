import json
import subprocess
from pathlib import Path

out = Path(__file__).parent
run = json.loads((out / 'run.json').read_text())['checks']['final']
folder = Path(run['session']['directory']) / 'protocol-data'
tools = Path('C:/Dev/software/ffmpeg-4.3.2-2021/bin')
results = {'scope': 'partial interrupted trial, closure remains unconfirmed', 'videos': {}}
for video in folder.glob('*.mp4'):
    probe = subprocess.run([str(tools / 'ffprobe.exe'), '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(video)], capture_output=True, text=True, timeout=90)
    decode = subprocess.run([str(tools / 'ffmpeg.exe'), '-v', 'error', '-hwaccel', 'none', '-i', str(video), '-map', '0:v:0', '-f', 'null', '-'], capture_output=True, text=True, timeout=120)
    results['videos'][video.name] = {'ffprobe_exit': probe.returncode, 'ffprobe': json.loads(probe.stdout) if probe.returncode == 0 else probe.stderr, 'decode_exit': decode.returncode, 'decode_stderr': decode.stderr}
    (out / 'partial-verification.json').write_text(json.dumps(results, indent=2))
    print(video.name, probe.returncode, decode.returncode, flush=True)
