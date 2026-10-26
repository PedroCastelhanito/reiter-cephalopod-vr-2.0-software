# Video and Stimulus selection — 2026-10-26

Base revision f82be21f28d3c1141adeabe2558c29808062727a plus concurrent GUI edits.
Owner asks why Video is absent and requires Stimulus to toggle the projection
previews in Per-projector mode. G01rev318 formalizes the result. Concurrent
G01rev317's hide-empty-Video rule is preserved: active cameras still require video
recording selection, and existing open/pending viewers retain closure controls.

Dashboard supplies a preparation-layout flag in Configuration/Setting up/Ready.
The workspace and native-window footprint owner use it to reserve eligible camera
frames without claiming viewer visibility. Running hidden cameras still free space.
Stimulus selection now controls visibility of every projection frame in the chosen
Combined/Per-projector mode, including pre-Setup waiting selections. Dials remain
independently selected. Existing native Show/Hide and surface-tile placement remain.
ARCH-002 review reuses focused layout/request owners; no dependency, new transport
or renderer state. Existing larger-module cohesion advisories remain.

Repository Python3.11 validation:

```text
python -m pytest tests/gui/test_dashboard.py -q -k "preview and not trial_preview" --basetemp=.pytest_tmp_video_stimulus_final --timeout=30 --maxfail=3
python -m pytest tests/gui/test_dashboard.py -q -k "stimulus_preview_belongs_to_advanced or preview_inline_controls_follow_camera_recording_choices or preview_workspace_pending_visible" --basetemp=.pytest_tmp_video_stimulus_final_focus --timeout=30
```

Broad run with permitted local loopback:124 passed,1 failed,762 deselected in108.60s.
The failure was an old camera-footprint fixture using Stimulus despite its newer
Advanced ownership. Fixture now uses an actual camera; no production gate changed.
Final focused run:10 passed,877 deselected in8.29s. Covers both modes, native-ready
and pre-Setup selections, all projection frames on/off, instruments independent,
Video independence, camera recording/phase gates and placement during pending
updates. Two existing completion communication cases independently pass in0.43s.

Initial broad sandbox run stalled at communication and was interrupted. Focused
run initially had stale tooltip/master assertions; changing the fixture source to
a camera restores its intended responsibility. Initial configuration test used the
legacy helper that forces Running; changed to select Monitor without phase change.
Pre-Setup stimulus fixture now explicitly selects its projection views. The broad
run is not claimed as a complete pass; its sole failure passes in focused rerun.

Ruff check/format6 files, Win32 mypy5 sources and boundaries758/zero pass, retaining
existing size advisories. Concurrent test import order was corrected by Ruff.
Whitespace passes. No native app restart, physical frames/DPI or rig acceptance.

[Render script](render.py) creates the real sample window with one eligible camera,
four authored gratings and unavailable native sources, never connects to devices.
[Projection on](projection-on.png) and [off](projection-off.png) were inspected:
camera placeholder remains, projection frames toggle, motion dials remain. Earlier
render used the review program's empty first epoch and was replaced with gratings
to inspect instrument independence. These are offscreen presentation fixtures.
