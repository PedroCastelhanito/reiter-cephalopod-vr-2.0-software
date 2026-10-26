# Compact preview fix and native verification — 2026-10-26

Source: dirty tree based on f82be21f28d3c1141adeabe2558c29808062727a;
concurrent unrelated edits preserved. G01/G02 own adaptive image/plot pairs and
complete FPS footers; E15 separates these bounded checks from full rig acceptance.

## Implementation and local checks

StimulusPreviewArea chooses columns and image/plot orientation by available width
and height, including the frame's measured heading/footer minimum and plot space.
Borderless stimulus frames allow160px-wide columns (native image minimum128 retained).
The responsive outer layout does not impose the previous arrangement's minimum on
the next resize. Plot visibility changes trigger another fit. No dependency, RPC,
recording, camera-window or native rendering changes.

ARCH-002 review: focused existing layout owner, reuses Qt layouts and the existing
InstrumentGrid scaling approach; no new abstraction/state or size-boundary exception.
Extended the owning test_dashboard behavior module. Tests assert the requested
size is retained and images/cards/complete FPS labels remain within the area, with
plots at least100px in each dimension. Four sizes (700x350,700x430,1100x430,700x650)
in three themes plus existing category/static-Bottom checks:25passed.
Command: QT_QPA_PLATFORM=offscreen python -m pytest tests/gui/test_dashboard.py -q
-k 'per_projector_compact_layout or stimulus_preview_reclaims_camera_space or category_preview_modes'.
Ruff check/format on changed source/test and Win32 mypy on stimulus_preview_area.py
pass. Boundaries:759 modules,0violations, existing unrelated size advisories.
Initial new-test fixture lacked Front content (corrected); explicit size assertion
then exposed Qt silently enlarging isolated test windows (corrected). Intermediate
native48-second run still clipped FPS despite visible plots; final implementation
was reloaded before the passing run below.

## Final native run

Normal managed launcher and GUI Setup/Start with original saved50-minute protocol;
only recording root redirected under this evidence directory. Behavior recording
remained enabled. Final trial10:55:55.378–10:58:12.498 JST (137seconds), stopped via
GUI Stop now. Controller generation2f28ba04-0939-4f46-a178-1d8372e33698,
session3dd04fd3-ca65-45b2-8509-19fff66967ca,
trialc85e6f22-e059-41c4-83b1-2d77bdbdbee4.

@oai/sky drove the native GUI, screenshots saved here. At1442x972 with splitter
moved from572 to655 (wider Video), four live projector images, all plots and both
Source/Preview FPS lines remain visible. Retro and Amber pass. Plots off/on,
Left off/on,1920x1032 maximize and1442x972 restore preserve visible content after
settling. Evidence: compact-retro-live.png, compact-amber-live.png and
compact-restored-live.png. Read-only authenticated snapshots: final-running.json
and final-stopped.json, collected by snapshot.py.

Final stop returns Configuration and cleanup_confirmed=true; camera closed and
preview stopped. Both trial SESSION_LOG files record output_closure_confirmed=true.
ffprobe metadata: intermediate1435frames/47.833333s/168833768bytes;
final4109frames/136.966667s/481685074bytes, H264 at30fps. Metadata only, no full decode.

Normal authenticated ShutdownApplication succeeded (command
1b4384dd-e9d9-49bd-88cb-ba37c5c40cdf). Final process inventory found no python/cephvr
processes. Original Retro style and both config files restored byte-for-byte after
comparison confirmed only test recording-root changes. Outputs retained.

## Separate unresolved findings and limits

On GUI reconnect after intermediate Stop now, retained supervisor warning
ffmpeg:d0bf1f7a-c060-40ec-ad52-ec40e82699cc released without worker closure evidence;
outputs unconfirmed. It persists in final-stopped.json (warningea21b977-e2d6-4a07-978b-96d901ffe456).
See intermediate-closure-warning.png. This conflicts with session-level closure
claims; no recording-integrity acceptance, warning attribution/root cause unverified.

Stimulus preview readback later showed27.7–36.5fps despite G01's20Hz cap;
source sampled44–60fps during UI changes. This is observed telemetry, not proof of
actual presentation rate; investigate rate accounting/cap separately. Camera
preview sampled8–13fps at30fps source. No throughput or physical timing acceptance.

Not a50-minute completion or all-saving-off dummy test. Alternate DPI, extreme
window sizes below tested range, full-load performance and optical checks remain
under the existing rig checklist. Native control had stale screenshot identifiers
on two actions; refreshed observations before retrying. No forced termination.
