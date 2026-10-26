# Recorder closure and preview FPS verification — 2026-10-26

Source: working tree based on f82be21f28d3c1141adeabe2558c29808062727a;
concurrent GUI edits retained. Root causes: regular recording encoder launch ID
was absent from worker resource cleanup; staggered per-window timers each caused
a draw of the whole projector group. Fixes preserve A08/E08 exact release/output
separation and V01/G01 pacing, with no new dependencies or lifecycle states.

## Local checks

- 201 passed /6 Windows cases deselected: acquisition/test_recording_cleanup.py,
  visual_stimulus/test_rendering.py, supervisor/test_recovery.py; pytest -q
  -m "not windows and not rig" --basetemp .test-tmp-recorder-fps-nativechecks.
- Acquisition owner:817 passed /2 deselected, same marker filter, basetemp
  .test-tmp-recorder-owner-20261026.
- Final minimized/reopen guards:113 rendering tests passed /6 deselected,
  basetemp .test-tmp-fps-final. Tests cover delayed individual reopen, common
  deadline, hidden/minimized skip and immediate complete-group reopen.
- Resource regression covers terminal/uncompleted session, released/unreleased
  encoder, no encoder, and unconfirmed output independent of confirmed release.
  Existing supervisor exact-worker/work/helper proof rejection cases pass.
- Ruff check/format pass for six changed Python files. Win32 mypy acquisition +
  visual_stimulus passes352 files; final group rechecked. Boundary tool checks759
  modules, zero violations. RecordingSession cohesion advisory reviewed: release
  evidence stays with its owned encoder; no separate responsibility extracted.
- Initial default-Temp sandbox attempt failed permissions; repository basetemp
  attempt stalled at restricted process/socket tests; both interrupted. Approved
  local-permission rerun passes. No test assertions weakened.

## First native run

Generation27939898-b9db-4e67-9efb-90cb3bc9923e; saved50-minute dummy protocol,
behavior video On, physical camera/projector/MCU active. Bounded run stopped
normally using Stop now after81.866667 seconds of recorded video, not full50min
or an all-saving-Off dummy test. Session SP0004-110716, trial110737.
Combined/Per-projector mode and Left/Front hide/reopen exercised. At1442x972,
Video card, four plot tiles and FPS labels remain visible. Settled stimulus
readouts19.7–20.0fps; one sampling window20.6fps is finite-window phase/count
quantization (shared fixed50ms cadence), not the prior27.7–36.5fps behavior.
Camera source30fps with observed preview10–12.5fps; cap is not a throughput promise.
Native viewer repositioning settles after asynchronous placement updates.

running.json/stopped.json/reconnected.json and screenshots are direct runtime/UI
captures. Cleanup confirmed, no retained errors/warnings after Stop and GUI
reconnect. SESSION_LOG reports output_closure_confirmed=true. decode-1.json:
ffprobe -count_frames fully reads2456/2456 frames, exit0/no decoder stderr.
Behavior frame-log completion recorded_frame_count2456, duplicate0, accounting
complete; failed_buffers0/missed_frames0. shutdown-1.json confirms success.
Raw outputs retained. GUI restarted normally to load final minimized/reopen guard;
shared cadence and recording fix unchanged between runs.

## Final native run — complete

Owner explicitly approved authenticated takeover after the initial automatic
review rejection. Final Setup/Start and six SetStimulusPreview operations succeed:
Combined, all four projectors, hide Left, reopen Left, hide group, reopen group.
Native renderer snapshots in final-preview-samples.json show source59.94–59.99fps
and preview19.66–19.99fps; first interval after complete reopen20.90fps reflects
initial-frame/count-window quantization, below the former27.7–36.5fps anomaly.
These are renderer swap telemetry, not optical measurements. Minimized skipping
is covered locally; final GUI automation remained unavailable, so no second-run
GUI layout claim beyond the first run's actual compact captures.

Final generation8f1692c3-7016-4b3b-9ebf-9d09fa5fcfc0; session SP0004-111509,
trial111520:44.466667 seconds of behavior video. Normal AbortNow (GUI Stop now)
completes successfully, stopped and settled snapshots confirm cleanup and no
retained errors. decode-final.json fully decodes1334/1334 frames, matching frame
log recorded_frame_count, exit0 and empty decoder stderr. shutdown-final.json
confirms normal shutdown success. final-processes.json records zero CephVR
processes. restoration.json confirms original runtime_gui.json and
last_configuration.json restored byte-for-byte after validating only recording
roots had changed. Raw recordings and evidence retained. Both tracked defects
are complete; no remaining takeover/config-restoration blocker.

Limits: bounded software/UI/recording evidence only; no physical presentation
rate, optical timing, alternate DPI or full-workload acceptance.
