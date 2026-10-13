"""Current assessment of the two final real recordings and exact source provenance."""
import hashlib
import json
from pathlib import Path
import subprocess
from cephvr.control.v1 import types_pb2 as pb

OUT=Path(__file__).parent
labels=('scope-fixed-first-combined','scope-fixed-repeat-combined')
runs=[]
for label in labels:
    evidence=json.loads((OUT/(label+'-verification.json')).read_text())
    run=json.loads((OUT/(label+'.json')).read_text())['checks']
    videos={}
    for name,video in evidence['videos'].items():
        assert video['ffprobe_exit']==video['decode_exit']==0
        videos[name]={key:video[key] for key in ('real_groups_per_s','render_groups','group_intervals','received_frames','received_frames_per_s','dropped_frames','invalid_frames','capture_dispositions','video_dispositions','completion_records') if key in video}
        videos[name]['external_frame_count']=int(video['ffprobe']['streams'][0]['nb_read_frames'])
    assert run['new_session']['succeeded'] and run['configuration_restored']
    assert evidence['session']['cleanup_confirmed'] and not evidence['errors']
    assert all(s['renderer_on_gpu0'] and all(s['encoders_on_gpu1'].values()) and set(map(int,s['encoders_on_gpu1']))<=set(s['live_nvenc_gpu1_pids']) for s in evidence['gpu_evidence']['samples'])
    runs.append(dict(label=label,session=evidence['session'],videos=videos,reset_and_restore=True,gpu_pid_evidence=evidence['gpu_evidence'],verification=label+'-verification.json'))
baseline=pb.Snapshot.FromString((OUT/'before.pb').read_bytes()).configuration_values.current
restored=pb.Snapshot.FromString((OUT/'measurement-restored.pb').read_bytes())
assert restored.configuration_values.current==baseline and not restored.prompts
assert restored.session.phase==pb.SESSION_PHASE_CONFIGURATION
sources=[
 'src/cephvr/shared/deadlines.py','src/cephvr/controller/lifecycle/trials.py',
 'src/cephvr/acquisition/coordinator/trial_pulses.py','src/cephvr/acquisition/coordinator/trial_termination.py',
 'src/cephvr/acquisition/worker/execution.py','src/cephvr/acquisition/worker/reports.py',
 'src/cephvr/acquisition/worker/health_snapshot.py','src/cephvr/acquisition/worker/pulse_evidence.py',
 'src/cephvr/platform/windows/byte_stream.py','src/cephvr/visual_stimulus/recording/capture.py',
 'src/cephvr/visual_stimulus/rendering/capture.py','src/cephvr/visual_stimulus/rendering/native.py',
 'src/cephvr/visual_stimulus/rendering/native_display.py','src/cephvr/visual_stimulus/resources/session.py',
 'tests/shared/test_invariants.py','tests/platform/test_byte_stream.py',
 'tests/acquisition/test_worker_admission.py','tests/acquisition/test_pulse_evidence.py',
 'tests/visual_stimulus/test_recording.py','tests/visual_stimulus/test_rendering.py',
 'tests/visual_stimulus/test_resources.py','tests/visual_stimulus/test_lifecycle.py',
 'config/backends/acquisition_config.toml','architecture.md','docs/architecture/acquisition.md',
 'contracts/acquisition/diagnostics.md',str(OUT/'run.py'),str(OUT/'verify.py'),str(OUT/'assess_final.py')]
context=dict(date='2026-10-13',head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 source_provenance='Shared dirty tree; exact final source hashes below. The final normal generation loaded these repairs; no diagnostic injection. Source patch includes earlier shared-file edits and is not a task-only diff.',
 authorization='Owner explicitly requests rendering slowdown and reset shutdown fixes;125ms drain for all cameras remains accepted.',
 decisions=['SYS-002','ARCH-002','A07 revision61','A08','A10','V12','V20','E05','E08','E11','E13','E14','E15'],
 baseline=dict(real_render_groups_per_s=2368/60,verification='baseline-combined-verification.json',reset_failed=True),
 implementation=['Native bounded row conversion, completed PBO mapping with private copy, actual-context no-op checks, normalization outside admission lock, private native pipe copy releasing GIL.',
 'Warning acknowledgement precedes Finished; terminal pulse retry equality excludes forwarding command identity; canceled trial health retains its scope until cleanup.',
 'Absolute host-boundary recheck after early async wakes for acquisition ON/OFF/normal end and controller onset/end/gap.',
 'Preparation release receipts reset only when all local source/consumer ownership has closed; repeated cleanup remains idempotent until new preparation.',
 'CPU preparation budget includes admitted slots, retained padding, readback and pipe copies and half-frame row scratch. No new dependency/process or scientific tuning.'],
 diagnosis=dict(warning='rejected-warning.jsonl',early_off='rejected-lifecycle.jsonl: internal Stop issued3.38ms before scheduled end, channel correctly rejects not-yet-due boundary',canceled_scope='rejected-heartbeat.jsonl',resource_reuse='NativePreparation returned cumulative retired-trial resource receipts; owning regression and real On-to-On reuse repaired'),
 runs=runs,nominal_combined_cadence_pass=True,uniform_frame_time_guarantee=False,
 checks=dict(pytest='1123 passed,3 skipped,6 deselected; final-suite.xml; acquisition/visual_stimulus/controller/shared invariants/native pipe owning tests; authenticated loopback/native publication permitted',native_pipe='14 passed including native Windows endpoint transfer/release',ruff='check/format affected owners passed;364 acquisition/visual/shared/platform files and138 controller/shared/platform files in scoped format commands',mypy='--platform win32:427 source files pass',boundaries='667 modules,0 violations; existing cohesive size advisories reviewed',whitespace='git diff --check passed'),
 restored=dict(generation=restored.controller_generation,original_configuration_equal=True,phase='Configuration',prompts=0,cameras_released={name:not getattr(restored.acquisition_devices,name).device_open and not getattr(restored.acquisition_devices,name).preview_run_id and not getattr(restored.acquisition_devices,name).cleanup_pending for name in ('behavioral','tracking')}),
 driver_setting='Managed cephvr-python.exe: OpenGL RTX5060Ti; original Threaded optimization Use global(Auto) restored/read back after ineffective Off experiment.',
 limitations=['Nominal60fps host render-group cadence, not uniform16.67ms or optical presentation proof. Final repeat median16.79ms/p9927.56ms/max37.88ms.',
 'Review video has substantial explicit capture drops/duplicate padding. Final repeat1176 real captures,2367 capacity drops,58 same-slot omissions,2424 duplicates in3600-frame video.',
 'Camera queues still drop frames: first9/28 and repeat6/19 Behavior/Tracking; full accounting and identified duplicates remain. No zero-loss claim.',
 'Eye disabled/unmeasured; locomotion Tracking and SpikeGLX disabled. Paired/optical/electrical/full scientific acceptance remains separate.',
 'On-to-On cleanup/reuse passes twice in same generation; native Save On-to-Off path still needs its dedicated verification.',
 '125ms remains an adopted engineering allowance, not a proven worst-case bound.'],
 experiments='Raw attempts retained. Switch quantum, uninitialized staging and optional compiled accelerator experiments removed; pyproject dependency set restored. Initial fixture/sandbox/startup-race failures and exact failed-generation administrative recovery are recorded in LOG.md.',
 sha256={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources})
(OUT/'context.json').write_text(json.dumps(context,indent=2)+'\n')
(OUT/'final-source.patch').write_bytes(subprocess.check_output(['git','diff','--',*sources[:26]]))
print(json.dumps(dict(real_fps=[next(v['real_groups_per_s'] for v in r['videos'].values() if 'real_groups_per_s' in v) for r in runs],reset_pass=True,restored=context['restored']),indent=2))
