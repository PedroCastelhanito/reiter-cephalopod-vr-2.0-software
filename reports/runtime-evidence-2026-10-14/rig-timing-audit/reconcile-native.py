import json
from pathlib import Path

root = Path(__file__).parent
p = root / 'lifecycle-findings.json'
d = json.loads(p.read_text())
d['failed_setup']['evidence'] += ['fault-recheck4/run.json', 'fault-recheck5/run.json', 'fault-recheck6/lifecycle.jsonl']
d['failed_setup']['fix_status'] = 'CPU preparation rejection and coordinator duplicate-fatal promotion repaired; acquisition CancelSetup now invokes aggregate cleanup. Fault6 retains accepted cleanup reports from both backends with all resources released and explicit output absence, but scope/revision warning rejection causes authority loss and aggregate failure. Warning race under repair; no end-to-end CancelSetup pass.'
d['three_camera_normal_confirmation']['external_decode_status'] = 'four full external decodes and frame counts pass'
d['final_three_camera_confirmation'] = {'evidence': 'final-sequence/verification.json', 'outcome': 'COMPLETED', 'cleanup_confirmed': True, 'configuration_restored': True, 'decoded_videos': 4, 'camera_queue_overflows': 0, 'review_capacity_drops': 3078, 'review_cfr_duplicates': 3098}
d['save_on_to_off'] = {'evidence': 'save-off/verification.json', 'same_generation': True, 'outcome': 'COMPLETED', 'cleanup_confirmed': True, 'configuration_restored': True, 'decoded_camera_videos': 2, 'stimulus_output_created': False}
d['abort'] = {'evidence': 'abort/run.json', 'partial_verification': 'abort/partial-verification.json', 'interruption_after_start_s': 5.3356403, 'cleanup_confirmed': False, 'decoded_videos': 3, 'configuration_restore_blocked': True}
d['native_gui']['offscreen_final'] = '494 passed; focused native layout9/hover2 passed; full native exception-hook stall unresolved'
d['configuration'] = {'recording_queue_frames': 17, 'camera_capacity_status': 'covers measured 20% burst heuristics; typed persistence pending', 'visual_status': 'original TOML restored byte-exact; 21-slot growth rejected because saturated', 'original_runtime_restore': 'pending next exact startup recovery'}
p.write_text(json.dumps(d, indent=2) + '\n')

todo = Path('TODO.md')
b = todo.read_bytes()
lines = b.splitlines(keepends=True)
lines = [line for line in lines if b'`stimulus-save-switch-cleanup`' not in line]
todo.write_bytes(b''.join(lines))
rig = Path('reports/rig-verification.md')
b = rig.read_bytes()
start = b.index(b'- [ ] Repair/retest the observed pre-change Save On')
end = b.index(b'\n\n', start) if b'\n\n' in b[start:] else -1
if end == -1:
    end = b.index(b'\r\n\r\n', start)
b = b[:start] + b'Oct14 dedicated Save On to Save Off native60s trial completes in the same generation, confirms cleanup and restores settings. Both camera videos independently count/full-decode; no stimulus output is created. This closes the normal switch check; failed-Setup and Abort cleanup remain separate open checks. [Evidence](runtime-evidence-2026-10-14/rig-timing-audit/save-off/verification.json).' + b[end:]
rig.write_bytes(b)
with Path('LOG.md').open('ab') as out:
    out.write(b'\n\n## 2026-10-14 - Exact cleanup tracing and final GUI verification\n\n- `stimulus-save-switch-cleanup` [visual_stimulus]: completed dedicated native Save On to Save Off trial in same generation, confirmed cleanup/settings restore, two camera full decodes/counts, no stimulus artifact. Remove completed TODO; interruption/fault recovery remains separate.\n- `rig-timing-buffer-audit` [gui] [controller] [supervisor] [acquisition] [visual_stimulus] [shared]: GUI final offscreen494pass. Ruffpasses; Win32mypy786filespasses; boundaries690zero. Format catches one test indentation, corrected. Real Abort at5.3356403s interrupts but cleanup unconfirmed; three partial videos count/decode, exact owned absence. No original configuration restoration claim after failure.\n- `renderer-failed-setup-cleanup-link` [controller] [supervisor] [acquisition] [visual_stimulus]: fix duplicate Setup fatal promotion76tests; fix acquisition CancelSetup missing existing aggregate cleanup71tests. Fault6 bounded macrotrace records both backend admissions/cleanupreports accepted with resources released/outputabsence. A warning scope/revision rejection still loses authority, so aggregate fails despite closure facts. Native end-to-end acceptance remains open.\n')
