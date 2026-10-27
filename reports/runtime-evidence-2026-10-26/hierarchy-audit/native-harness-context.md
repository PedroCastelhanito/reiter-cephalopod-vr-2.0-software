# Prepared native and encoder harnesses

These are isolated verification harnesses. Their default invocations only parse
and validate current saved configuration and print plans. Root executed the native
trial below after review; root owns live GUI actions, TODO/LOG and backend reports.

## Native recording

[native_recorded.py](native_recorded.py) copies the live authenticated snapshot,
uses one 60-second blank stimulus trial, and enables recording for its
existing enabled cameras and Visual Stimulus. It preserves camera IDs, complete
PFS/settings, trigger lines/rates, ROI, source depths, codec/filter/quality lists,
display geometry/calibration and fixed policy. Tracking processing and other
backends remain disabled. A fresh output path inside this repository is required.

Current saved settings at preparation select Behavioral 2456x2568 BayerRG8 at
30 Hz and Tracking 1588x1344 Mono8 at 60 Hz; Eye is disabled without a selected ID.
Behavioral quality is CQ23/yuv444p, Tracking CQ23/yuv420p; saved stimulus quality
is CQ18/yuv444p, differing from the backend TOML defaults. The actual live snapshot
remains authoritative. Installed controller/backend validators, including the V20
file-policy overlay, check an offline saved candidate before control acquisition
and the actual live candidate before UpdateConfiguration. The fresh recording
root is created before Setup. Hardware/device acceptance remains Setup's work.

Execution requires an explicit controller generation. Every command checks that
generation and this client's exact control lease. Preflight requires Configuration,
no retained session, no pending operator/manual operations, no cleanup blockers,
prompts or active diagnostics, and no preview/prepared/run identity/cleanup on any
camera role. Enabled cameras may be disconnected: ordinary Setup owns their exact
native validation/opening and aggregate Ready. An already connected camera still
requires matching configured/physical identity and applied settings. The final
trial began from fresh disconnected devices; no manual Connect or pulse mapping
action was made. This avoids the separately unresolved manual lease-loss path.

Normal flow is exact UpdateConfiguration, Setup/Ready, StartSession/Running,
StopAfterTrial, exact completed trial interval and confirmed session cleanup,
NewSession and exact original runtime configuration restoration. Required Ready
participant health and exact session/trial IDs are checked. All commands, outcomes,
failure snapshots, authoritative checkpoints and final recording directory are
retained. No prompt is silently accepted and no uncertain command is retried.

The same-lease `finally` path cancels SettingUp/Ready or aborts Starting/Running,
then requires confirmed cleanup before configuration restoration. Changed lease,
generation, session, configuration revision or installed configuration stops
mutation and records the retained state for root review. Unknown closure never
becomes a success. No blind settings-file restore or process kill occurs.
The harness leaves controller/application running. Acquisition devices finish disconnected,
which matches their pre-audit state according to root; configuration alone is
restored by this harness. Root restores pre-audit GUI navigation/theme file bytes
after normal shutdown; this harness never overwrites those files while GUI is live.
Root subsequently confirmed normal ShutdownApplication, exact generation exit
with all owned processes absent, and exact restoration of the three pre-audit
GUI/configuration files.

Every current backend TOML and the three configuration/GUI JSON files are copied
into the isolated run directory and hashed before work. Final byte equality is
reported individually. Native collection/decode is a subsequent read-only step:
`tools/encoding_probe.py collect --directory <recording_directory> --output <fresh_summary_path>`.
The completed run's collection and assessment below perform those read-only checks.

## Failed preparation attempts and separate runtime finding

- `native-recorded-30s-1`: UpdateConfiguration explicitly rejected the E05 minimum
  duration violation; Setup did not run. The first harness used Pydantic
  `model_copy`, so its shallow offline plan missed model-wide validation. Root's
  initial/rejection snapshot comparison shows exact equality of controller
  generation, configuration, configuration values, session and trial. All eleven
  settings-file checks were unchanged. The old harness's
  `runtime_restoration_unconfirmed` line is overly conservative for this explicit
  rejection; it is not evidence of a configuration mutation. The corrected
  harness only allows 60 seconds, runs authoritative validation before control,
  and separately labels an explicit rejected/unchanged Update.
- `native-recorded-60s-1`: UpdateConfiguration succeeded, then Setup admission
  explicitly rejected the nonexistent recording root. Device Setup did not run.
  Original runtime configuration was restored exactly; all eleven files remained
  unchanged and control release reported no failure. Root corrected the harness
  to create its isolated `recordings` directory before Setup; this is harness
  preparation, not a backend behavior change.

After the rejected 30-second attempt released its CLI control lease while two
manual previews were active, the existing runtime failed during manual cleanup.
Stderr records `PREVIEW_STOP_FAILED: Microcontroller operation is unavailable or
pending`, followed by the Behavioral worker's `INVALID_EVIDENCE: manual preview
cleanup does not prove its exact ring release` and supervisor shutdown. This
failure is distinct from the harmless rejected Update. The emergency report
[emergency report](../../emergency-1081805269636400-75871685-c23f-4725-a030-1e1df97108a8.json)
retains that cause; the exact failed
generation's [exit receipt](failed-generation-exit.json) confirms all owned
processes absent. No source/hardware fix is claimed.

Source-review candidate, not an executed reproduction: controller
`MicrocontrollerLifecycle.owner_lost` sets `releasing=True`, so acquisition's
`manual_preview._stop` can apply OFF and release the first camera/rings but then
its ON of remaining roles correctly fails the MCU release gate. That leaves a
stopping preview retained. A subsequent owner-cleanup retry can request a new
worker Cleanup after the ring already closed; `WorkerLifecycleReports` then asks
`ManualPreviewEvidence.confirm_cleanup` for the old ring and rejects its absence.
This chain fits the retained timing but requires focused end-to-end reproduction
through accepted StopPreview cleanup, real owner retirement and new Cleanup.
Exact old report replay after resource removal is a separate unverified concern.
Keep ON authority and exact release proof strict; no new owner-loss semantics,
schema fields, production fixes or diagnostic injection are implemented here.

## Completed native result — 2026-10-27

[Native run](native-recorded-60s-2/) uses controller generation
`e498a719-f0da-4783-93fc-6c9991d94766`, session
`55f10639-ac99-4cd0-a4ae-e534bfece2ca` and trial
`603a1eea-c920-4cd5-b64d-1db4fc421398`. The exact scheduled/actual interval is
60 seconds; normal trial completion, StopAfterTrial, confirmed cleanup, NewSession
and exact runtime configuration restoration pass. All eleven run-baseline file
comparisons remain unchanged; control release has no retained failure.

Read-only command: `.venv/Scripts/python.exe tools/encoding_probe.py collect --directory reports/runtime-evidence-2026-10-26/hierarchy-audit/native-recorded-60s-2/recordings/20261027_hierarchy_audit/RIGCHECK-090710 --output reports/runtime-evidence-2026-10-26/hierarchy-audit/native-recorded-60s-2/collection.json --timeout 90`.
The collector exits zero with no errors after full software decode and ffprobe
counting of all three videos. [Assessment source](native-recorded-60s-2/assessment.py)
checks raw source/mapping/capture evidence and writes
[assessment.json](native-recorded-60s-2/assessment.json).

- Trial LOG declares all seven outputs Closed/artifact-present; session cleanup is
  confirmed. [Final generation receipt](final-generation-exit.json) separately
  confirms all owned processes absent after root's normal shutdown.
- Behavioral: 1,797 received/real/mapped/decoded images at 2456x2568; Tracking camera:
  3,596 at 1588x1344. Every source and encoded index is contiguous and its receipt
  mapping exact; native counters are contiguous from zero. No invalid image,
  capacity drop, duplicate or diagnostic gap is recorded. First host receipts are
  T+73.0615 ms and T+33.0283 ms. Counts below nominal 1,800/3,600 are not proof of
  missing exposures/pulses; source membership is the actual host-receipt interval.
- Stimulus: 3,554 actual groups/admissions/transfers/encoder inputs/decoded frames;
  all 14,216 per-output submission observations returned. Zero capacity drops,
  omissions, duplicates or unresolved attempts; encoder exit zero, EOF and drain
  confirmed. Video is 1280x720 with unchanged saved CQ18/yuv444p encoding.
- Software evaluation gaps: median 16.655 ms, maximum 276.4823 ms; seven exceed
  25 ms, six exceed 50 ms, all within the first 0.932 seconds. No later gap exceeds
  25 ms. Maximum individual submission duration is 13.943 ms. Successful capture
  of every rendered group does not establish absence of presentation gaps.

Sequential video playback durations (59.900/59.933/59.233 seconds) reflect source
counts, not padding or an extended/shortened experiment interval. Blank stimulus
and mostly dark Tracking imagery do not validate representative scene throughput,
science, physical timing, Tracking processing or full-load headroom. Slot/readback/
queue maxima remain unavailable from the fresh run, as detailed below.

## Synthetic encoder isolation

[encoding_current.py](encoding_current.py) reuses `encoding_probe.command` and
`probe_video`, but retains saved/live-candidate quality arguments exactly; the
existing `encoding_probe bench` always substitutes CQ16/23 and reads TOML lists,
so would misrepresent current saved stimulus CQ18/yuv444p.

Default planning uses saved configuration; pass the native run's `candidate.json`
to use its actual frozen choices. Camera 8-bit source mappings and full ROI are
explicit; unsupported source formats reject. Stimulus input/layout uses the owning
`ffmpeg_input_format` and `recording_layout` helpers with current review scale.
Expected current composite is 1280x720 RGBA at 60 Hz. Check it against actual
native prepared/recorded evidence before executing a throughput case.

Execution adopts the unique RTX 2080 Ti using `discover_encoder_device` and rejects
unless its physical UUID matches an explicit reviewed `--expected-gpu-uuid`. Its
current CUDA ordinal is passed to each FFmpeg job; no ordinal is guessed. Each
case has 5 or 10 seconds' frame count, one to four concurrent streams, 45-second
per-encoder bounds, then full count/decode checks after timed encoders finish.
Failed/partial outputs yield no throughput success claim. `--rate-multiple 2` or
`4` increases only synthetic source rate/frame demand; quality/defaults/policy do
not change. Inputs are unpaced synthetic lavfi sources, so results bound that
source/filter/encoder path, not camera/pipe/readback performance or science fidelity.
The reused probe applies `-bf 0`, one-second forced keyframes and its synthetic
fragmented-MP4 mux flags; these are recorded command controls, not a claim that
camera output durability/mux metadata matches production. Saved user quality,
codec, pixel format and filter arguments remain exact.
Do not overlap these probes with the native recording workload.

Root completed three isolated finite cases after the native run and full decode,
using the exact frozen [candidate](native-recorded-60s-2/candidate.json). Adopted
GPU is the RTX 2080 Ti, CUDA ordinal 1, UUID
`GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc`. All nine encoders/probes/full decodes
exit zero, all nine decoded counts match requested counts (5,250 total frames),
and each dimensions/quality/filter list matches the frozen candidate. See
[assessment](encoding-assessment.json) and raw [baseline](encode-baseline/),
[double-rate](encode-double-rate/), [quadruple-rate](encode-quadruple-rate/) evidence.

| Finite case | Behavioral measured / requested fps | Tracking camera measured / requested fps | Stimulus measured / requested fps |
| --- | --- | --- | --- |
| Baseline | 66.1 / 30 | 131.4 / 60 | 165.1 / 60 |
| Double rate | 71.9 / 60 | 141.3 / 120 | 184.9 / 120 |
| Quadruple rate | 75.6 / 120 | 147.6 / 240 | 193.7 / 240 |

Baseline and doubled finite demands finish faster than their five-second media
interval. Quadrupled demand completes without corrupt/lost encoded frames, but
every source misses its requested real-time rate; the slowest job takes 8.13
seconds. Finite completion is not a fourfold capacity pass. Measurements include
startup; jobs are unpaced, share CPU/filter/encoder work and finish at different
times, so these are neither steady-state simultaneous capacity nor isolated NVENC
hardware ceilings. No quality/policy/default optimization is integrated.

Preparation checks: both default plans pass; source compile and Ruff checks using
the root configuration on stdin pass. Ruff intentionally excludes reports paths,
so ordinary directory checks do not cover these evidence scripts. Actual native
execution/collection is recorded above; synthetic execution and its physical GPU
identity/results are owned by root's separate retained evidence.

## Code to review / implement: retain existing recording metrics

Observed source gap: `src/cephvr/visual_stimulus/recording/metrics.py` defines
`RecordingMetrics.snapshot` with per-stage count/total/max, worst bounded samples,
peak/active capture slots, queued captures and incomplete input. The capture path
populates these aggregates; `RecordingSession.metrics` references the same owner
in `recording/session.py`. Current source has no consumer that serializes the
snapshot. `tools/encoding_probe.py::collect` can read legacy diagnostic records
with `event=recording_metrics`, but current runtime emits no such record. Therefore
queue/readback/slot maxima cannot be claimed from a fresh uninstrumented trial.
This is a missing diagnostic export, not observed capture loss or an ownership
defect. Historical raw metric records retain their original revision/scope.

Small candidate: emit one existing bounded snapshot after an actual recording
thread exits through its existing diagnostic owner/sink, and verify that sink
retains it. Keep it separate from authoritative scientific/file-closure evidence;
retain original failure/deadline behavior and do not log per frame or inject a
runtime hook for this verification. `tests/visual_stimulus/test_recording.py`
already owns these paths and asserts that cancellation before a recording header
does not emit recording metrics; preserve that distinction. Add focused active
recording completion/failure coverage there if this export is later authorized.
No implementation or diagnostic injection is made in this audit.

For current native evidence use raw `_frames.jsonl` evaluation timestamps,
capture/encoder dispositions, completion/accounting records and full MP4
count/decode. Current camera schema 5 and stimulus recording are sequential:
their duplicate counts should be zero; historical CFR substitution behavior
must not be assumed for this revision. Evaluation/submission gaps are software
timing evidence, not optical cadence or attribution of readback/queue stalls.
