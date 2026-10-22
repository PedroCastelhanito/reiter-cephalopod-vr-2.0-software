# October22 Windows and rig verification

Current result after resumed authorization: corrected clipping reservations pass
fresh Setup/Cancel, bounded60s and unchanged2x600s playback/recording with fullsixvideo
and required-evidence audits. See [final raw evidence](cleanup-fix/queue-fix/README.md)
and [current assessment](../../runtime.md#rig-checks-oct22). Earlier pending/blocking
statements below are retained chronological evidence, superseded by this result.
Timing/optical limits and two pre-Start helperwarnings remain explicit.


Sol6.1 managed tests; Astra independently reviewed decisions/results. Initial
revision/clean status are in revision.txt/working-tree.txt. Final repaired source
hashes and tracked diff are in final-source-sha256.json/final-source.patch (untracked
raw evidence is retained separately). Python3.11.15, native Windows/Qt6.11.2.
Current assessment: [runtime](../../runtime.md#rig-checks-oct22).

## Current outcomes

- Backend regression:2629pass/6skip/1rig deselected in33.24s, including40Windows-
  marked passes/1symlink skip. Five skips need symlink privilege/Developer Mode;
  one needs native C++ for actual-sketch fixture. No firmware installed/flashed.
- Separate rig-marked NVOF generated same-image lease/readback/close:1pass0.33s.
  No scientific Tracking, camera or workload acceptance is inferred.
- Final owning GUI checks:79 timeline +14 Dashboard/style/layout =93unique cases.
  The81-case dial suite includes the same two compact-reference cases as the14
  selection; do not add those duplicates. Uncaught Qt-slot exceptions fail teardown.
- Native style and layout: two real GUI lifetime defects reproduced and fixed;
  disposable native QAction repeat cleanly exits with Amber asserted; root's actual
  managed Configure/Monitor and Amber/Retro menu observations pass. Original Retro
  restored. Actual viewer follow/reflow, all dialogs and alternate DPI stay open.
- Final lint/format984/mypy857/boundaries749zero and30schemas pass;90contract tests
  pass. Final Windows wheel and sdist build pass. Existing cohesion advisories and
  missing assets/calibration/*.md manifest warning are retained.
- Full unchanged texture Setup:Ready84.7078s/noPING failure with configured200ms ACK.
  CancelSetup fails10.0275s: renderer cleanup identity/release proof rejected,
  renderer exits and application automatically shuts down. No Start issued;
  Started250ms/Stopped450ms trial and full20min acceptance remain blocked.
- Exact old-process absence verified; supported preserving startup recovery retains
  failed-session unknown closure. Original live configuration/history match exactly
  (history SHA256 d3e1b9c0ff202b72b358f18e0508ec37bfa44b5809083d375b50c5c44a8275e8).

## Commands and retained failures

Run from repository root with `.venv/Scripts/python.exe` as `python`:

1. `tools/test_on_rig.ps1 -OutputDirectory <this directory>`: prerequisites,
   syntax/static/contracts run. Exposes launcher trailing whitespace and stale
   prepared-trial schema. Formatter/generator repair only those existing artifacts.
   Sandbox pytest stalls after72 cases and is interrupted; no suite pass inferred.
2. Elevated `python -m pytest -q -m "not rig" tests --ignore=tests/gui --timeout=60
   -o faulthandler_timeout=30 --junitxml <pytest-nongui.xml>`:2629pass; raw log/JUnit.
3. Elevated `python -m pytest -q -m rig tests/tracking/test_windows_native.py
   --timeout=30 --junitxml <pytest-rig.xml>`:1pass; generated capability only.
4. Full GUI serial pre-fix imports abort after409completed/noJUnit, four stale/event
   failures. Windows QtCore0xc0000409 event retained. Isolated exception-hook trace
   establishes deleted MotionDial from overwritten same-face parent. Initial native
   style-hook trace separately establishes deleted QLabel. Hook-logged exceptions
   are failures even when disposable process initially exits0.
5. `python -u -X faulthandler <gui_verify.py> -q tests/gui/test_preview_timeline.py
   tests/gui/test_dashboard.py::test_compact_reference_rows_share_headers_and_commit_relocated_fields
   --timeout=120 --tb=short --junitxml <pytest-dial-fix-final.xml>`:81pass.
   Final14case owning Dashboard selection is in pytest-final-owning.log/XML.
6. Final serial225case batch is intentionally stopped after51passes to prioritize
   actual rig checks; noJUnit/full-suite pass claimed. Final bounded full899case
   `python -u -X faulthandler -m pytest -n2 -q -p slot_exception_checks tests/gui
   --timeout=120 -o faulthandler_timeout=60 --tb=short --junitxml
   <pytest-gui-final-parallel.xml>` is stopped after roughly 10 minutes: 432 passing
   reports, 0 failure/error reports, no JUnit/full 899-case pass. Offscreen Qt and the evidence
   directory in PYTHONPATH load the exception-failure plugin in both workers.
   Quiet partial output lacks per-node identities; no unique broad count is added
   to owning coverage. Exact test-process absence and final restored idle state
   are retained in gui-final-test-absence.json/live-setup/final-idle-verification.json.
7. Final-static-summary.json records exact commands/exit codes; corresponding logs
   retain full output. `python -m build --no-isolation --outdir <packages>` succeeds
   elevated after an initial sandbox temporary-directory permission failure.
8. `live-setup/baseline.py` is read-only; `controlled_setup.py` authenticates guarded
   UpdateConfiguration→Setup→CancelSetup only. Events/snapshots retain complete
   command identities/results; observer exit0 is not a cleanup pass. Recording root
   `<repo>/cephvr-data/r22` keeps the retained failed test session. The bounded-trial script
   is prepared but NOT executed; the full-workload procedure remains gated. No deadline/identity guards were relaxed.
9. Automatic-shutdown-absence.json proves exact core PIDs and all managed owners
   absent. Preserving relaunch uses normal scripts/start_runtime_gui.py;
   recovery_restore.py selects only exact old session recover and verifies baseline.
   No session deletion, output closure upgrade or saved-history overwrite occurred.

The disposable fixture's intermediate post-loop0xc0000005 is preserved separately;
proper DeferredDelete cleanup yields clean repeat. A raw managed-executable launch
without its DLL bootstrap fails import and is not an application-test result.
File-policy-load.json is explicitly a fresh file-loader check, not runtime readback.
No GUI regression ran concurrently with the actual Setup/cancel probe. Physical
pulse/optical, source content, fault/storage, viewer DPI and scientific/full-load
acceptance remain separate under E15. Evidence for unresolved cleanup stays retained.

## Final handoff after owner requests imminent-use wrap-up

Full unchanged two-trial attempt in `cleanup-fix/full-texture/` fails after completed
trial1/600s and trial2/185.0268s on required evidence_pending_bytes overflow.
Emergency655095435292400 and partial recordings are retained; no full-run pass or
confirmed failed-session closure. No proven minimal queue fix; no budget/deadline
change or dropped evidence. Source review/drain hypothesis is not runtime proof.
`cleanup-fix/full-recovery/` retains supported preserving recovery command/source,
stdout and snapshots. `recovery-verification.json` confirms exact original runtime
and history bytes, failed-session preservation and no upgrade of unknown closure.
Application is idle Configuration; no test workload remains. Earlier in-progress
statements in chronological raw notes are historical. Current assessment is
`reports/runtime.md#rig-checks-oct22`.

Recovery commands (elevated native/loopback access):
`.venv/Scripts/python.exe -u scripts/start_runtime_gui.py`
then `.venv/Scripts/python.exe -u reports/runtime-evidence-2026-10-22/rig-checks/cleanup-fix/full-recovery/recovery_restore.py`.
Both stdout logs retained; recovery exits0. Launcher remains the user's idle managed
application and is intentionally not terminated.
