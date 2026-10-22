# Timing and helper-proof validation — 2026-10-22

Sol6.1 executes; Astra independently reviews. Working tree includes earlier accepted fixes; `provenance.json` records HEAD, current scoped hashes and absence of temporary driver hooks; `final-source.patch` is the exact incremental helper/ABI/test diff. Ordinary evidence follows GOV-001; unresolved incidents remain protected.

## Confirmed corrections

- E08 helper retirement: use copied, already accepted exact-worker session cleanup only for a same-session helper's explicitly released `ffmpeg:command` resource. Native job-empty/exact-process release still required; output results remain independent. Old false-warning reproduction, eight proof/identity/live-job cases and168 supervisor tests retained in helper logs/XML.
- V01/V12/V21/V28 timing: `_file_identity` previously declared a13-DWORD ctypes structure and POINTER on every protected image read. ctypes permanently caches each pointer type. Changing-image60s census retains313 structure types/4069 fields, versus fixed-image control's small graph. Hoisting the unchanged ABI type prevents accumulation; no GC policy, deadline or identity relaxation. Old regression observes256 distinct pointer types; corrected regression uses one while checking changing identity/WinError6. Native ownership test includes32 independent reads, file exclusion and closure.483 Visual Stimulus tests pass.

## Diagnostic sequence and limits

`gap-correlation.json`: earlier105.882ms state interval follows97.275ms before first swap; individual swaps are short. Disposable `runtime_probe.py` captures gen2 GC76–142ms overlapping GL/recording work. Probe is bounded but perturbs execution and is not cadence acceptance.

`heap-growth.json`:72000 representative evidence encodes have constant graph. `engine_heap_growth.json`: actual prepared2×600s engine/4000epoch transitions with fake render port have constant graph/gen2<0.1ms; excludes native image/GL behavior. Census v1 fails only in diagnostic metadata because a NumPy ctypes type has `__module__=None`; local reproduction and corrected type naming retained. Corrected fixed-image60s census (`census-trial-v2`) completes, postcollect1253 tracked objects. Original-changing200epoch/60s census (`census-changing`) retains13471, identifying the cached ABI graph. All diagnostic sessions complete/cleanup and exact baseline restoration; no optical or strict60Hz inference.

## Final production validation

`final-full-fresh` runs unchanged protocol SHA256fb0f9b552342221bc4704031c62b7f0ec7074d95a1f17d937b1230c63bd78aee in fresh generatione985c1a2-bff6-4c7b-abbc-6bbd3a1bd130/sessionf8ee72c7-205e-4c62-b3c5-076023aa7a75. Two natural600s trials complete; controller confirms cleanup; exact original runtime/history SHA2567c12d49cc9fc46e4f8b14d547882514c49fb50b7c78ba39b27cf2f34c2d8b93c restored. No errors, warnings or prompts at final Configuration. `cadence-distribution.json` contains all state/output intervals and thresholds. State max31.9408/26.8303ms, p9921.9190/22.5099ms, zero state gaps>35ms. Worst output entry interval38.6401ms; this is not strict60Hz/optical certification. Final `output-verification.json` passes all six complete video decodes/counts and all4000 image/blank occurrences/143544 exact image bindings, zero holds/mismatches/failed submissions. Stimulus36000/36001 admitted=transfer=input=encoded=decoded. `camera-accounting.json` validates17985 Behavioral/35972 Tracking pertrial, exact identities, zero drops/invalid/native gaps/regressions, no diagnostics and two post-cutoff exclusions per role/trial. Maximum first-group software onset21.8091ms (trial2 20.389ms). Astra independently accepts all raw proof. `idle-snapshot.json`/`idle-processes.json` confirm restored idle Configuration/no session/acquisition generation, no ffmpeg/ffprobe/pytest/audit job; healthy GUI/runtime retained.

`final-full` retains genuine first Setup PING failure at200.495ms/199.987ms budget (no Start, successful Cancel and restoration). `final-full-retry` retains admission rejection from that same owner failure; no new physical attempt. Root/Astra approve one fresh restart/retry, which is final-full-fresh. No deadline changed. Separate idle shutdown JOB_INSPECTION_FAILED/MCU Close/unregistered-resource incidents and exact process absence retained; do not reinterpret a launcher exit0 as cleanup proof.

## Commands

All native/socket/pytest commands run elevated because sandbox denies required Windows/loopback/temp-file operations. No firmware flash, scientific Tracking or deferred continuous-capture implementation.

```powershell
.venv/Scripts/python.exe -m pytest tests/supervisor -q
.venv/Scripts/python.exe -m pytest tests/visual_stimulus/test_windows_resources.py -q -k reuses --junitxml=reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/identity-before.xml
.venv/Scripts/python.exe -m pytest tests/visual_stimulus -q --junitxml=reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/visual-final.xml
.venv/Scripts/python.exe -m ruff check src/cephvr/platform/windows/protected_source.py src/cephvr/supervisor tests/supervisor tests/visual_stimulus/test_windows_resources.py
.venv/Scripts/python.exe -m ruff format --check src/cephvr/platform/windows/protected_source.py src/cephvr/supervisor tests/supervisor tests/visual_stimulus/test_windows_resources.py
.venv/Scripts/python.exe -m mypy --platform win32 src/cephvr/platform/windows/protected_source.py src/cephvr/supervisor
.venv/Scripts/python.exe tools/check_backend_boundaries.py
git diff --check
.venv/Scripts/python.exe -u scripts/start_runtime_gui.py
.venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh/baseline.py
.venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final_full_fresh.py
.venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/cadence_distribution.py reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh
.venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/verify_outputs.py reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh
```

Additional final audit:

```powershell
.venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/verify_camera_counts.py reports/runtime-evidence-2026-10-22/rig-checks/timing-helper-fix/final-full-fresh
```

Ruff/format35, Win32 mypy25 and boundaries749/zero pass; existing size advisories remain cohesive owner responsibilities. No new dependencies or generic coordination state. Affected behavior tests extended in existing modules; no broad GUI rerun, prior899-node evidence remains separate.
