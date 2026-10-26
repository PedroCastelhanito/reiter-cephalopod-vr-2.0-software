# Native preview check — 2026-10-26

Source: dirty working tree based on f82be21f28d3c1141adeabe2558c29808062727a;
includes G01 revision326 Video card and pending-toggle fix. Existing concurrent
changes preserved. Windows native GUI driven through @oai/sky screenshots/actions;
authenticated read-only snapshots collected by snapshot.py.

Managed runtime launched with `.venv/Scripts/python.exe scripts/start_runtime_gui.py`.
Saved 50-minute protocol retained (Rotation10s/Static20s,100 repeats); bounded run
10:40:22–10:43:14 JST, then GUI Stop now. Behavior video saving enabled; this is
NOT all-saving-off dummy acceptance or a full protocol completion.
Only recording root changed to this directory's output folder. Initial Setup
correctly rejected the not-yet-created folder; creating it allowed Setup to pass.

## Observations

- Two Video master off/on + Behavior reselect cycles, initial open, splitter drag,
  Combined/Per-projector/Combined and Left projector off/on completed. No recurring
  toolbar/heading jitter observed after settling; Video/Stimulus card edges aligned
  at1920x1032. Native viewer placement eventually followed resized frames.
- At1442x972 after enlarging Video with the splitter, four-face Per-projector with
  Plots enabled showed no plots and clipped Preview FPS footer lines. Maximizing
  restored plots and both footer lines. See per-projector-missing-plots.png and
  per-projector-maximized.png. Observed defect; root cause not established here.
- Camera source30fps, preview approximately8.5–12.9fps; stimulus source approximately
  60fps, preview19–20fps. These are sampled UI readings, not throughput acceptance.
- Initial camera opening briefly showed a small misplaced window before placement
  settled. Some automation focus/actions restored the maximized parent; attribution
  to application versus automation is unresolved. No claim of app regression.

## Cleanup and output

Session3907dd29-08c8-4431-88a7-b8a3ec810d2f; trialdf3019d3-b56a-41dd-8f02-3a187277e7d3.
SESSION_LOG.jsonl records interrupted trial with output_closure_confirmed=true.
after-stop.json confirms Configuration, cleanup_confirmed=true, cameras closed and
preview_running=false. Cached pulse readback is not a fresh physical-off measurement.
ffprobe metadata: H264,2456x2568,30/1fps,5152frames,171.733333s,605375351bytes.
Metadata readable; no full decode or frame-continuity audit performed. Outputs retained.

Restored Retro console through Style menu, closed GUI normally, then authenticated
CLI `--controller-generation d3709bab-650a-45b1-ad3d-5d326e3c7866 --json shutdown`
returned complete=true/succeeded=true (commandc86ea4f7-ddc9-4946-819c-6cb2eab9aa8a).
Post-shutdown Win32_Process inventory found no python/cephvr processes.
Launcher stderr was empty during run; closure added controller/supervisor channel
EOF messages. Config comparison found only the two recording-root changes; restored
runtime_gui.json and last_configuration.json byte-for-byte from before copies.

No production code changed in this test increment. Alternate DPI, Snap, physical
calibration, full-load performance,50-minute completion and no-output dummy acceptance
remain open under the existing rig checklist. G01/G02 and E15 govern this scope.
