"""Consolidate current acceptance limits without treating padded video as cadence."""
import hashlib
import json
from pathlib import Path
import subprocess
from dataclasses import asdict
from cephvr.shared.credentials import default_runtime_root
from cephvr.shared.recovery import RecoveryStore

OUT=Path(__file__).parent
run=json.loads((OUT/'profile-combined.json').read_text())['checks']
folder=Path(run['final']['session']['directory'])/'protocol-data'
videos={}
for path in folder.glob('*_frames.jsonl'):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if 'stimulus' in path.name:
        payloads=[row['payload'] for row in rows]
        groups=[row for row in payloads if row['kind']=='render_group']
        videos[path.name]=dict(real_groups=len(groups),real_groups_per_s=len(groups)/60,completion=[row for row in payloads if row['kind'] in ('completion','encoder_outcome')])
    else:
        videos[path.name]=dict(received_frames=sum(row['type']=='frame' for row in rows),completion=[row for row in rows if row['type']=='completion'])
store=RecoveryStore(default_runtime_root())
context=dict(date='2026-10-13',head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    authorization='Owner: use125ms for all; prior real camera plus stimulus recording/GPU placement/cadence test request retained',
    decisions=['SYS-002','ARCH-002','E14','A10','A07','V12','V20'],
    accepted_file_margin_ms={role:125 for role in ('behavioral','tracking','eye_tracking')},
    implementation='Only operator TOML values and existing configuration regression changed; no runtime performance/failure-policy implementation change or new dependency',
    baseline_verification='baseline-combined-verification.json; full external frame count and CPU decode all three videos, live physical-GPU/PID mapping, recipe match, output closure and unlocked reservation',
    baseline_cadence_pass=False,baseline_real_groups_per_s=2368/60,
    profile_videos=videos,
    profile_method='Existing temporary renderer stage timers, nested inclusive durations, native live5s process CPU/thread and GPU utilization sample; instrumentation overhead possible',
    profile_gpu_sample='GPU0 RTX5060Ti9% GPU,2722MHz; GPU1 RTX2080Ti57% GPU/60% encoder,1935MHz. Point sample is not an upper/lower capacity guarantee.',
    unresolved=['Combined normal rendering39.47fps/profile38.25fps versus prior stimulus-only60fps; critical path slower across readback handoff, drawing/context work and diagnostic polling; no single proven root cause or performance repair.', 'Both completed sessions later shut down during reset/restore with COORDINATOR_HEALTH_LOST: worker report rejected: EVIDENCE: warning producer/scope/revision differs. Exact owned absence independently confirmed; stale warning cause not yet diagnosed.'],
    exit_receipts={generation:asdict(store.read_exit_receipt(generation)) for generation in ('7ed9d374-aa03-492f-b9d8-80d51e3b788c','94986966-747e-472b-9a50-2e18d4f83e4e')},
    restored_normal_generation='6b8d9b8e-bb7d-42de-84ee-423bc81e1b3e',restored_configuration_equal=True,
    checks='Owning configuration17passed; Ruff check/format pass; boundaries667/zero violations with existing cohesive size advisories; TOML loader125000000ns for each camera; no unrelated implementation suite',
    limits='Eye disabled/unmeasured, locomotion Tracking and SpikeGLX disabled; no optical/electrical or full scientific workload acceptance.125ms adopted engineering allowance, not mathematical worst-case guarantee.',
    source_provenance='Shared dirty tree; post-run current hashes below. Raw completed media and failed/repeat diagnostics retained in this dated directory.',
    sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path('config/backends/acquisition_config.toml'),Path('tests/acquisition/test_configuration.py'),Path('src/cephvr/visual_stimulus/rendering/capture.py'),OUT/'run.py',OUT/'verify.py')})
(OUT/'context.json').write_text(json.dumps(context,indent=2))
print(json.dumps({'normal_real_fps':context['baseline_real_groups_per_s'],'profile':{name:row.get('real_groups_per_s',row.get('received_frames')) for name,row in videos.items()},'restored_generation':context['restored_normal_generation']},indent=2))
