# Renderer cleanup repair and resumed rig verification — 2026-10-22

Working directory is the repository root. Python is `.venv/Scripts/python.exe` (3.11.15).
Native/socket/CIM/build commands ran elevated after sandbox restrictions; no firmware,
policy timeout, scientific protocol or service-role credential was changed.
`fixed-source-provenance.json` identifies the final runtime source and original policy hashes.

- `gui-full.log/xml`: complete899-case two-worker run,894pass/5fail/923.07s.
- `gui-final-replays.log/xml`: final seven scoped serial cases,7pass/12.79s/clean exit0.
  `gui-coverage.json` accounts899 unique nodes with passing evidence. Other replay files
  retain initial selector whitespace, stale/window-focus failures and failed-assertion QtGC aborts.
- `backend-final.log/xml`:2633pass/one20ms thread-entry scheduling failure/6skip/1deselected.
  `backend-serial-replay.log/xml`: that unchanged case passes serially (0.37s).
- `visual-final.xml`:478pass; `fence-before.xml` retains initial missing-deadline regression;
  `fence-final.xml` includes pending/error/expiry and actual GL_WAIT_FAILED cases.
- `build-final.log`: wheel/sdist success; existing calibration Markdown manifest warning.
- `diagnostic-setup/`: pre-fix clean replay79.848s/Cancel260.898ms, not historical cause proof.
- `verified-setup/`: fresh final-source Ready76.6843s/Cancel264.0674ms, explicit verification,
  exact runtime/history restoration. Temporary controller instrumentation is removed;
  retained diagnostic source is provenance only and is not final product code.
- `bounded-trial/`: initial preflight key failure before any configuration mutation.
- `bounded-trial-final/`: recorded60s completed trial, expected SessionStopped after
  StopAfterTrial, cleanupconfirmed and exact restoration. Original executed harness's
  wrong SessionCompleted assertion/exit1 retained; explicit outcome audit exits0.
- `full-texture/`: unchanged2x600s workload, currently in progress; no pass until terminal
  state, exact restoration and independent output audit are verified.

Commands (PowerShell; log paths abbreviated to this directory):

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONPATH=(Resolve-Path reports/runtime-evidence-2026-10-22/rig-checks).Path
& .venv/Scripts/python.exe -u -X faulthandler -m pytest -p slot_exception_checks tests/gui -n 2 -vv --timeout=60 -o faulthandler_timeout=30 --junitxml=reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/gui-full.xml
& .venv/Scripts/python.exe -u -X faulthandler -m pytest -p slot_exception_checks -q tests/gui/test_dashboard.py::test_timeline_epoch_shortcuts_and_keyboard_history tests/gui/test_dashboard.py::test_review_devices_capture_aligned_fields_and_wrapped_headers tests/gui/test_dashboard.py::test_linked_texture_motion_variation_reports_reference_and_recovers --timeout=60 --junitxml=reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/gui-final-replays.xml
& .venv/Scripts/python.exe -m pytest -q -m 'not rig' tests --ignore=tests/gui --timeout=60 -o faulthandler_timeout=30 --junitxml=reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/backend-final.xml
& .venv/Scripts/python.exe -u scripts/start_runtime_gui.py
& .venv/Scripts/python.exe reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/verified-setup/baseline.py
& .venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/verified-setup/controlled_setup.py
& .venv/Scripts/python.exe reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/bounded-trial-final/baseline.py
& .venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/bounded_trial.py
& .venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/verify_outputs.py reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/bounded-trial-final --stopped-after-trial
& .venv/Scripts/python.exe reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/full-texture/baseline.py
& .venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/full_texture.py
```

Each physical harness is single-attempt and refuses changed generation/config/history.
Full programs/seeds/gaps remain unchanged; the bounded program is explicitly reduced.
Public operator snapshots omit raw backend Started/Stopped/CleanupReport payloads.
Successful controller enforcement is evidence of accepted configured bounds, not numeric
receipt margin; command elapsed time is not lifecycle ingress latency. The original
rejected cleanup term remains unknown. Camera counts/cadence are measured, not exact-rate
or optical acceptance. Eye camera and Tracking/Sync backends remain disabled as recorded; two-camera
open-loop runtime validation does not lift deferred scientific or fault/physical scope.
