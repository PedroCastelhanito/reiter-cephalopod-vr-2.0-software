"""Derive a fresh bounded harness after reviewing current RPC and sequential rules."""

import hashlib
import json
from pathlib import Path

out = Path(__file__).parent
origin = out.parents[1]/"runtime-evidence-2026-10-15/comprehensive-audit/trial.py"
source = origin.read_text(encoding="utf-8")
replacements = {
    '"threecam60", "abort60"': '"threecam60", "p160", "lossless60", "abort60"',
    'print(name, json.dumps(value), flush=True)': 'print(name, json.dumps(value)[:1500], flush=True)',
    '"audit-managed-recordings"': '"encoding-audit-20261016"',
    '"abort60", "abort120", "threecam60"}': '"abort60", "abort120", "threecam60", "p160", "lossless60"}',
    'visual.save_visual_stimulus_data = args.case != "off60"': '''visual.save_visual_stimulus_data = args.case != "off60"
    if args.case == "p160":
        for name in ("behavioral", "tracking"):
            values = getattr(acquisition, name).ffmpeg_args.values
            values[list(values).index("-preset")+1] = "p1"
        values = visual.review_ffmpeg_args
        values[list(values).index("-preset")+1] = "p1"
    if args.case == "lossless60":
        for name in ("behavioral", "tracking"):
            camera = getattr(acquisition, name)
            values = list(camera.ffmpeg_args.values)
            for key in ("-rc", "-cq", "-b:v"):
                index = values.index(key)
                del values[index:index+2]
            values += ["-rc", "constqp", "-qp", "0", "-tune", "lossless"]
            del camera.ffmpeg_args.values[:]
            camera.ffmpeg_args.values.extend(values)
        # E13 review video remains lossy; camera probes do not change that policy.''',
}
for old, new in replacements.items():
    assert source.count(old) == 1, old
    source = source.replace(old, new)
target = out/"managed_trial.py"
assert not target.exists()
target.write_text(source, encoding="utf-8")
(out/"managed-harness-provenance.json").write_text(json.dumps({"origin": str(origin), "origin_sha256": hashlib.sha256(origin.read_bytes()).hexdigest(), "adapted_sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "review": "Current RPCs reviewed; fresh settings source/output namespace; sequential accounting assessed separately, never old CFR assessment; compact console only; p1/lossless camera variants, E13 stimulus remains lossy"}, indent=2)+"\n")
