import json
from pathlib import Path

root = Path(__file__).parent
paragraphs = {
    'reports/acquisition.md': 'Oct14 rig audit verifies a sixty-second combined Behavior/Tracking/Eye trial: confirmed cleanup, restored settings, four independently counted/full-decoded videos and zero camera queue overflows. Queue capacity17 is now saved in the operator TOML and typed configuration; it covers measured burst demand with20% margin at30/60/60Hz, with sustained headroom unproven. Camera nominal-slot omissions remain separately accounted. Dedicated Save On to Save Off completes in one generation with two decoded camera videos and no stimulus artifact. Four preview start/stop cycles per camera (12 total) complete with unchanged settings and all devices released. E05/E06/E08/A10 repairs cover completed-session health, stale serial failure, aggregate CancelSetup, exact cleanup receipt retention and interrupted-trial pulse evidence. The last two require renewed native session checks: projectors are now owner-deferred and E10 correctly rejects disabling required Visual Stimulus. Physical electrical/photodiode, paired mappings and Tracking processing remain deferred. [Configuration assessment](runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json), [Current findings](runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json).',
    'reports/visual_stimulus.md': 'Oct14 combined sixty-second three-camera trial completes with nine closed outputs, restored settings and four counted/full-decoded videos. Stimulus slots21 saturate with3078 capacity drops/3098 CFR duplicates; finite buffer growth is rejected and original visual TOML restored byte-exact. V12 throughput remains open. Nested video-sync cadence is corrected: measured successful intervals stay below1.2s (maximum1040.5247ms), errors0. Native Save On to Save Off completes/cleans/restores with two decoded camera videos and no stimulus output. E05/E06/E08 cleanup repairs preserve strict output absence, exact resource receipts and confirmed delivery. Fault6 records accepted cleanup from both backends, but warning authority loss prevents overall cancellation; its scope repair is locally verified under E03 revision35. With projectors off, fault9 exposes lost prior calibration release receipts; catalogue retirement/reopen handling is repaired and full Visual suite311 passes, native retest deferred. No renderer-exit cause is inferred from generic CHILD_EXITED. [Current evidence](runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json).',
    'reports/runtime.md': 'Oct14 rig audit saves only acquisition queue10 to17, covering measured burst demand with20% margin; all other original experiment settings and original visual TOML are preserved. Combined three-camera and dedicated Save Off trials complete/clean/restore and independently decode. Four preview cycles per camera pass; normal ShutdownApplication succeeds with exact all-owned absence. Current regression selections1540 backend passes/five skips and494 GUI passes; Ruff, format906, Win32 mypy786 and boundaries690/zero violations pass. An earlier authenticated timeout passes isolated and final selection; cause unproven. Native layout9/hover2 pass, but full native GUI exception-hook stall/manual DPI acceptance remain open. E05/E06/E08 fixes cover aggregate cleanup, stopped-trial pulse proof and bounded warning scope (E03 revision35); native full cancellation/Abort/idle-reuse checks await projectors. Tracking processing, photodiode and physical paired mappings remain owner-deferred. [Assessment](runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json).',
}
for name, paragraph in paragraphs.items():
    p = Path(name)
    b = p.read_bytes()
    start = b.index(b'Oct14 `rig-timing-buffer-audit`')
    end = b.index(b'\r\n\r\n' if b'\r\n' in b else b'\n\n', start)
    p.write_bytes(b[:start] + paragraph.encode() + b[end:])

with Path('LOG.md').open('ab') as out:
    out.write(b'\n\n## 2026-10-14 - Rig audit available-scope completion\n\n- `manual-camera-repeat-admission` [controller] [acquisition] [gui] [shared]: four real preview start/stop cycles each Eye/Behavior/Tracking in one generation (12 total), all completed, configuration unchanged and final devices closed/no preview/no pending cleanup. Remove completed TODO. Physical edge/LOW and GUI selector/DPI acceptance remain separate.\n- `rig-timing-buffer-audit` [controller] [supervisor] [acquisition] [visual_stimulus] [shared] [spikeglx] [gui]: accept and persist only camera queue10->17 via typed UpdateConfiguration plus owning TOML; baseline comparison proves other original fields unchanged. Reject Visual21 growth, restore exact original TOML. Normal ShutdownApplication succeeded; exact generation b51cab36-51b9-4a41-bcc1-458fed93fb28 all-owned absence receipt retained.\n- Native fault6 both backend cleanup proofs accepted but warning authority loss prevents aggregate pass. Generalize existing one-previous-warning-scope slot with exact session/config revision; E03 revision35/register updated, producer/camera/occurrence validation retained. Interrupted worker accepts only exact retained stopped-trial pulse evidence after readiness is fenced; source152focused pass, native Abort retest pending. Fault9 starts with absent projector and separately rejects budget; prior calibration receipts regress in cleanup, repaired with explicit catalogue retirement and same-key reopen invalidation. FullVisual311pass; no native post-fix projector pass.\n- Owner confirms projectors off and defers projector tests. Camera-only trial was rejected before Setup by accepted E10 required Visual participant; original configuration restored. Defer remaining full-session cancellation/Abort/idle300s reuse, timing receipts and visual throughput. Photodiode, physical SpikeGLX mappings/paired acceptance, Tracking processing and manual firmware deferrals remain.\n- Exact quarantined fault6 marker/lock preserved/restored within verified workspace paths; recreate only removed empty protocol/spikeglx directories for normal explicit StartupRecovery. Recovery completes administrative marker/report without certifying unknown files/remote stopping. No manual pointer clearing or forced process termination occurred.\n- Final source selections: nonVisual1229pass/5skip, Visual311pass, GUI494pass; earlier backend authenticated timeout rechecks2pass and final selection passes, cause unproven. Ruff/format906/mypyWin32786/boundaries690zero pass. Full native GUI exception-hook stall remains unresolved.\n')

p = Path('TODO.md')
b = p.read_bytes()
lines = b.splitlines(keepends=True)
removed = {'rig-timing-buffer-audit', 'renderer-failed-setup-cleanup-link', 'manual-camera-repeat-admission'}
lines = [line for line in lines if not any(('`' + task + '`').encode() in line for task in removed)]
b = b''.join(lines)
at = b.index(b'## Deferred')
end = b.index(b'\n', at) + 1
deferred = b'\n- [ ] `rig-timing-buffer-audit` [controller] [supervisor] [acquisition] [visual_stimulus] [spikeglx] [shared] [gui] Owner-deferred after projectors powered off Oct14: resume required full-session Abort/idle300s reuse, lifecycle receipt margins and sustained stimulus throughput. Camera17 saved with measured20% burst margin, full combined/SaveOff/preview checks pass; preserve Tracking/photodiode/paired mapping deferrals. - [Assessment](reports/runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json)\n- [ ] `renderer-failed-setup-cleanup-link` [visual_stimulus] [controller] [supervisor] [acquisition] Projector-dependent native retest deferred by owner: verify complete failed Setup cancellation and fresh reuse after strict cleanup, bounded warning scope and release-receipt repairs. Fault6 backend proofs accepted but aggregate failed; latest local311 Visual/1229 other backend tests pass, native complete cancellation unproven. - [Findings](reports/runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json)\n'
b = b[:end] + deferred + b[end:]
replacements = {
    'combined-recording-loss': '- [ ] `combined-recording-loss` [acquisition] [visual_stimulus] Resolve sustained review throughput when projector tests resume: Oct14 camera queues17 have zero overflows but nominal-slot omissions remain; review21 saturates3078capacity drops/3098CFRduplicates. Original precision/quality/rates preserved and visual defaults restored. - [Assessment](reports/visual_stimulus.md)',
    'eye-camera-and-connect-recovery': '- [ ] `eye-camera-and-connect-recovery` [gui] [controller] [supervisor] [acquisition] [shared] [visual_stimulus] Triggered Eye60Hz video/drain and four preview cycles now verified Oct14; complete full-session interrupted reuse after source repairs when projectors return, plus separate physical/GUI acceptance. Firmware upload manual; Tracking processing/photodiode/paired mappings deferred. - [Assessment](reports/acquisition.md)',
    'mcu-managed-connection-and-io': '- [ ] `mcu-managed-connection-and-io` [gui] [controller] [acquisition] Installed COM8 protocol4/cephvr2_uno_4 readback and all3 configured triggers verified in combined run and12 preview cycles; no flashing. Complete electrical edge/LOW, watchdog-load/lease-expiry and interrupted-upload acceptance with instruments; preserve deferred physical mappings. Historical ON rejection cause remains unproven. - [Findings](reports/runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json)',
}
lines = b.splitlines(keepends=True)
for i, line in enumerate(lines):
    for task, replacement in replacements.items():
        if ('`' + task + '`').encode() in line:
            lines[i] = replacement.encode() + b'\n'
p.write_bytes(b''.join(lines))

p = root / 'lifecycle-findings.json'
d = json.loads(p.read_text())
d['status'] = 'available_scope_completed_remaining_native_tests_owner_deferred'
d['owner_deferrals'].append('projector-dependent tests while projectors off')
d['preview'] = {'evidence': 'final-preview/measurement-cycles.json', 'cycles_per_role': 4, 'roles': ['eye_tracking', 'behavioral', 'tracking'], 'all_start_stop_completed': True, 'configuration_unchanged': True, 'all_devices_released': True, 'limit': 'commands/SDK capture and closure; electrical edges and GUI visibility not certified'}
d['configuration']['camera_capacity_status'] = '17 accepted/saved in TOML and typed settings; measured20% burst heuristic, sustained bound unproven'
d['configuration']['original_runtime_restore'] = 'all original fields preserved except accepted queue17'
d['failed_setup']['evidence'] += ['fault-recheck9/lifecycle.jsonl']
d['failed_setup']['fix_status'] = 'Local fixes complete; both backend closure proofs accepted in fault6, aggregate cancellation not proven. Warning scope repaired; fault9 exposes stale calibration release proof, repaired with catalogue retirement/reopen tests. Native complete cancellation/reuse deferred while projectors off.'
d['abort']['repair'] = 'Exact stopped-trial pulse evidence admission after interruption locally verified; native retest blocked by projector deferral and E10 required Visual participant.'
d['validation'] = {'backend_passed': 1540, 'backend_skipped': 5, 'gui_offscreen_passed': 494, 'ruff': 'passed', 'format_files': 906, 'mypy_win32_files': 786, 'backend_modules': 690, 'boundary_violations': 0, 'native_gui_full_suite': 'unresolved exception-hook stall'}
d['final_shutdown'] = {'succeeded': True, 'all_owned_processes_absent': True, 'evidence': 'final-exit-receipt.json'}
p.write_text(json.dumps(d, indent=2) + '\n')

p = Path('reports/rig-verification.md')
b = p.read_bytes()
start = b.index(b'- [ ] Repeat real preview start/stop cycles in one generation')
end = b.index(b'- [ ] Reduce combined review/camera', start)
b = b[:start] + b'Oct14 four preview start/stop cycles per camera (12 total) complete in one generation, settings unchanged and all devices released. Electrical/GUI acceptance remains separate. [Evidence](runtime-evidence-2026-10-14/rig-timing-audit/final-preview/measurement-cycles.json).\n\n' + b[end:]
intro = b'\nOct14 owner powers projectors off and defers projector-dependent checks. Final combined three-camera and SaveOff recordings count/full-decode; queue17 saved with measured20% burst margin. Review throughput, full CancelSetup/Abort/idle300s reuse and lifecycle receipt margins remain open. Source/local repairs are not native acceptance. [Current assessment](runtime-evidence-2026-10-14/rig-timing-audit/configuration-assessment.json).\n'
at = b.index(b'\n') + 1
p.write_bytes(b[:at] + intro + b[at:])
