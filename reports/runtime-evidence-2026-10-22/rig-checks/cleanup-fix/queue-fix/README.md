# Clipping reservation correction — 2026-10-22

Fresh read-only elevated Win32 process inventory found zero Python/FFmpeg processes;
no active user experiment. Parent user explicitly resumes fix/tests after prior wrap-up.
Sol6.1 owns execution; Astra independently reviews source/evidence. Existing unrelated
changes preserved. `source-provenance.json` hashes corrected runtime source/settings.

Only fixed-schema clipping reservation changes256KiB→2048bytes; total evidence budget
16MiB and complex rendergroup reservation256KiB remain unchanged. Serialization stays
offGL, actual encoded-size guard and required-evidence overflow failure remain.
Observed historical clipping lines147–155bytes, four/group. Historical drain stall
cause is not established; corrected accounting addresses independently reproduced
avoidable queue exhaustion, not a claimed historical exact cause.

Existing test_recording additions cover three worst-case128-character ID/scalar
variants and blocked-consumer32groups/128clips exact preservation. `../queue-before`
log/XML proves old code exact BufferError; corrected owner482 cases pass.
Initial sandboxtemp prerequisite error and newfixture missingoutputs failure were
corrected before final owning pass. Ruff/format15, Win32mypy14, boundaries749zero and
whitespace pass. No unrelated GUI rerun (899 unique nodes already covered).

Native commands (elevated loopback/device access):
- `.venv/Scripts/python.exe -u scripts/start_runtime_gui.py` (launch.log)
- `.venv/Scripts/python.exe -u .../queue-fix/setup/baseline.py`
- `.venv/Scripts/python.exe -u .../queue-fix/setup/controlled_setup.py`

Fresh generation ed0cf088-7f99-419f-8308-60f7396161e5; all planned stages completed.
Every stage captures fresh baseline/history, one attempt marker and guarded exact
restoration; no unexplained history edits or failed-closure upgrade.

## Final results

- SetupReady75.9819s/Cancel253.1699ms; cleanup/exact baseline confirmed.
- Bounded60s trial77138ccb: completed/intentionalSessionStopped/cleanuptrue; full3video
  and required-evidence audit succeeds. Source/encoded/decoded1797B/3596T/3601stim.
- Full session2e34ee88: natural2x600s SessionCompleted/cleanuptrue, all14outputsClosed.
  `full-texture/output-verification.json` audits both2000-epoch schedules,71904+71980
  correct imagebindings,0mismatch/hold/submissionfailure, exact admission/transfer/
  input/encoder/decode counts. Six videos fully decode: eachtrial17985B/35971T,
  stimulus36000/35995. `camera-accounting.json`: source/video/native identities match,
  zero observed drop/invalid/nativegaps/regressions/failedbuffers/missedframes;
  post-cutoff2B/3T frames pertrial accounted. No physical trigger/exposure inference.
- Maxstate105.882ms/output107.899ms/firstonset47.1322ms are measured limitations;
  no uninterrupted60Hz/precision optical onset guarantee.
- Two helper-retirement warnings alreadypresentReady persist; actual helperrole/work
  unresolved. Bothcurrenttrials'14outputs nevertheless have exactclosed/decodeproof.
- `restoration-verification.json` proves exactfreshbaseline/history7c12…d8b93c;
  `idle-after-run.json` confirms idleConfiguration/cleanup/noactiveacquisitionprojection.
  Originalpriorfailedrecordings/unknownclosure remain separate/protected.

Audit commands (elevated only for native loopback/process/temp access):
`.venv/Scripts/python.exe -u .../cleanup-fix/verify_outputs.py .../queue-fix/bounded-trial --stopped-after-trial`
then camera verifier for boundedOUT; repeat full verifier withoutflag and camera
verifier for fullOUT. All fouraudit commands exit0; stdout retained audit.log and
camera-audit.log. Allowning482 cases pass; finalrecording77pass0.60s afterfixtureheader
fourfaces tidy, Win32mypy163/Ruff/format15/boundaries749zero/whitespacepass.
Prior899GUIcoverage remains accepted, no unrelatedrerun.

Astra independently reviews source, Setup/bounded/fullrawproof, bothauditJSONs and
restoration: noactionableissue, functional playback/recording acceptance only.
Currentbackendreport is `reports/runtime.md#rig-checks-oct22`; TODO keeps physical
cadence/optical and generichelperwarning followups. No further workload requested.
