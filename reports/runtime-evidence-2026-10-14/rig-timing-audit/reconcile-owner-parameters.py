import json
from pathlib import Path

root = Path(__file__).parent
p = Path('docs/architecture/acquisition.md')
b = p.read_bytes()
start = b.index(b'### A03 ')
end = b.index(b'### A04 ', start)
part = b[start:end]
part = part.replace(b'**Revision:** 32', b'**Revision:** 33', 1)
old = b'- The tracking ring and the in-process recording queue each default to **10 frames**\r\n  (`[buffers] tracking_ring_frames`, `recording_queue_frames`), configurable before\r\n  Setup.'
if old not in part:
    old = old.replace(b'\r\n', b'\n')
assert old in part
newline = b'\r\n' if b'\r\n' in part else b'\n'
new = b'- Configure tracking-ring and recording-queue capacities before Setup; the owning' + newline + b'  operator TOML holds their defaults and explicit saved values take precedence.'
part = part.replace(old, new, 1)
p.write_bytes(b[:start] + part + b[end:])
p = Path('architecture.md')
b = p.read_bytes()
old = b'[A03](docs/architecture/acquisition.md#a03) | Frame transfer between processes | Accepted | 32 |'
assert old in b
p.write_bytes(b.replace(old, old.replace(b'32 |', b'33 |'), 1))

p = Path('reports/acquisition.md')
b = p.read_bytes()
old = b'Queue capacity17 is now saved in the operator TOML and typed configuration; it covers measured burst demand with20% margin at30/60/60Hz, with sustained headroom unproven.'
new = b'The measured queue17 covered burst demand with20% margin at30/60/60Hz. Owner now selects queue20, SDK15 per camera and150ms drain allowance; TOML/live configuration/history loading are verified, but these new values have not been remeasured. Sustained headroom remains unproven.'
assert old in b
p.write_bytes(b.replace(old, new, 1))
p = Path('reports/runtime.md')
b = p.read_bytes()
old = b'Oct14 rig audit saves only acquisition queue10 to17, covering measured burst demand with20% margin; all other original experiment settings and original visual TOML are preserved.'
new = b'Oct14 rig audit measured queue17 with20% burst margin. Owner subsequently selects queue20, SDK15 per camera and150ms drain allowance; apply through idle Controller UpdateConfiguration/SaveConfigurationHistory and owning TOML. Current/live/saved values match, other current fields are preserved and the open application remains running. New values are not native retested. Original visual TOML remains unchanged.'
assert old in b
p.write_bytes(b.replace(old, new, 1))
p = Path('reports/visual_stimulus.md')
b = p.read_bytes()
needle = b'V12 throughput remains open.'
add = b'V12 throughput remains open. Retain3 slots with256MiB recording CPU/512MiB asset GPU budgets for the tested2560x2000 composite/assets: CPU accounting133120000bytes requires159744000with20%; GPU same-assets estimate335054176bytes requires402065012with20%. These are allocation accounting estimates, not new native measurements or whole-process/GPU memory guarantees. Twenty-one slots saturated, so no finite slot recommendation establishes steady throughput.'
assert needle in b
p.write_bytes(b.replace(needle, add, 1))

p = root / 'configuration-assessment.json'
d = json.loads(p.read_text())
d['accepted_change']['after'] = 20
d['accepted_change']['measured_confirmation_capacity'] = 17
d['accepted_change']['saved_typed_settings'] = 'owner-parameter-review/result.json'
d['accepted_change']['owner_revision'] = 'Queue20 explicitly selected after measured queue17 confirmation; no new native run.'
d['retained_settings']['sdk_buffers']['value'] = 15
d['retained_settings']['sdk_buffers']['result'] = 'Owner selects15; defaults/live/history confirmed, native remeasurement pending.'
d['retained_settings']['post_cutoff_drain_margin_ms']['value'] = 150
d['retained_settings']['post_cutoff_drain_margin_ms']['owner_revision'] = 'Owner selects150ms; file-policy loading confirmed, measured tails were collected at125ms.'
d['retained_settings']['pending_records_capacity']['recommendation'] = 'Keep10000 metadata records; normal peak14 is not stalled-writer demand.'
d['visual_recommendation'] = json.loads((root / 'owner-parameter-review/recommendations.json').read_text())
p.write_text(json.dumps(d, indent=2) + '\n')
p = root / 'lifecycle-findings.json'
d = json.loads(p.read_text())
d['configuration']['recording_queue_frames'] = 20
d['configuration']['sdk_buffers_per_camera'] = 15
d['configuration']['post_cutoff_drain_margin_ms'] = 150
d['configuration']['camera_capacity_status'] = 'Owner-selected20/15/150; TOML and Controller current/history verified. Prior native measurements were17/10/125; no new native validation.'
d['owner_parameter_review'] = {'evidence': 'owner-parameter-review/result.json', 'application_left_running': True, 'setup_or_recording_dispatched': False}
p.write_text(json.dumps(d, indent=2) + '\n')

p = Path('TODO.md')
b = p.read_bytes()
b = b.replace(b'Camera17 saved with measured20% burst margin', b'Owner queue20/SDK15/drain150 saved; prior queue17 measured with20% burst margin')
p.write_bytes(b)

with Path('LOG.md').open('ab') as out:
    out.write(b'\n\n## 2026-10-14 - Owner parameter selections and stimulus budget review\n\n- `rig-timing-buffer-audit` [controller] [acquisition] [visual_stimulus]: owner requests queue20, SDK15 per camera and150ms post-cutoff drain. Initial closed-app update refuses held application guard before any settings mutation; read-only snapshot shows existing application idle Configuration. Authenticated UpdateConfiguration and SaveConfigurationHistory both succeed; owning TOML/default/file-policy loading and saved/current equality verified, all other current fields preserved. No Setup/recording/projector test or restart/shutdown dispatched; application remains open. New20/15/150 values are not native remeasured. A03 revision33/register remove obsolete duplicated numeric defaults, leaving operator TOML authoritative; fixed policy values/version unchanged.\n- Recommend retaining10000 metadata-only pending records: normal peak14 does not bound fault backlog. Retain Visual3 slots/256MiB recording CPU/512MiB asset GPU budget; same tested composite CPU accounting133120000bytes,20%159744000; same-assets inferred GPU335054176bytes,20%402065012. Allocation accounting is not a new measurement or whole-process/GPU budget. Slots21 saturated and finite growth cannot establish sustained throughput. Recommendations preserved in owner-parameter-review/recommendations.json; reports/current assessment updated without rewriting measured raw evidence.\n')
