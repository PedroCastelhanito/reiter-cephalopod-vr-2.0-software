# Preview rotation and Combined windows — 2026-10-23

Source: dirty working tree based on `59a973ac3ffc6fb331bbee1d93c6b283d6b90474`;
concurrent unrelated edits retained. Decisions: [G01](../../../docs/architecture/gui.md#g01),
[V01/E13](../../../docs/architecture/visual_stimulus.md).

The owner's report confirms coherent physical rig rotation, reversed Bottom planning
rotation and different Front/Bottom versus side-screen Monitor directions. This is
owner observation, not a new measured optical acceptance result. The final clarified
request uses existing separate windows for Combined in the unfolded rig layout.

## Methods and results

Repository Python3.11; GUI checks use `QT_QPA_PLATFORM=offscreen` and unique
repository-local pytest basetemp paths.

- `python -m pytest tests/gui/test_dashboard.py tests/gui/test_preview_timeline.py -q -s
  -k 'trial_preview or bottom_portrait_mapping or category_preview_modes_keep_camera_space
  or drift_pairs_keep_face_directions or preview_workspace_frames_shown_streams_and_timeline
  or preview_frame_metrics or linked_subject_directions_align'`:39 passed,903 deselected,
  exit0. [Raw final output](gui-tests.log). Coverage includes asymmetric X/Y pixels
  through portrait/crop/flip placement, existing Bottom pitch/direction rules,
  Combined cross-layout centers, shared metrics and repeated mode/widget ownership.
- `python -m pytest tests/visual_stimulus/test_rendering.py -q`:111 passed, exit0.
  Includes `test_native_review_layouts_crop_only_preview_and_rotate_full_recording`,
  using a standalone ModernGL4.3 context with asymmetric quadrant source pixels,
  preview crops/mirrors, unchanged full recording raster/Bottom rotation and readback.
  This bounded native GPU pixel check is not projector or full-load validation.
- Ruff check/format: `stimulus_preview_area.py`, `preview_frame.py`,
  `trial_preview_rig.py`, `rendering/capture.py` and the two owning test modules pass.
  Win32 mypy on the four source modules passes. Backend boundaries:757 modules,
  zero violations; existing size advisories. These edits stay in focused owners.

Initial GUI expectations attributed the folded reflection to physical Y; four pixel
cases failed and established that output-Y reflection becomes physical X after the
portrait turn. Corrected the expectations; final coverage passes. Two earlier quiet
GUI runs printed all passing dots but exited1 without a summary; final captured
`-s` runs finish with summaries/exit0. No unsupported cause is assigned.

## Visual inspection and limits

[Combined layout](combined-layout.png) is a1200×610 offscreen grab of the real
StimulusPreviewArea/StimulusTimeline, with `review_program`, elapsed1s, Advanced on
and a deliberately noncanonical Front/Left/Right/Bottom input order. Bundled IBM
Plex Mono and Amber stylesheet are loaded. The four preview placeholders are arranged
Left–Front–Right, Bottom centered beneath Front. Native viewer pixels are absent;
the sample epoch has no active motion instruments. Initial capture attempts used
unsupported theme arguments/imports or missing font registration; this inspected
capture replaces those unusable attempts.

No running application restart, device commands, saved experiment/calibration edit,
physical direction comparison or throughput benchmark. Four GPU windows still sample
the existing preview composite; no claim of reduced GPU cost. Outstanding acceptance:
[single rig checklist](../../rig-verification.md#protocol-category-previews).
