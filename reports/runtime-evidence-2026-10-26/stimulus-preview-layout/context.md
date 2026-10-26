# Stimulus preview layout — 2026-10-26

Source: dirty working tree based on f82be21f28d3c1141adeabe2558c29808062727a.
Concurrent preview edits were preserved. G01 revision319 owns the requested layout.

## Method and outcomes

All Python commands use `.venv/Scripts/python.exe`.

- `-m pytest tests/gui/test_dashboard.py -q -k 'stimulus_preview or category_preview or drift_pairs or preview_slot or multiple_review_previews or preview_frame_metrics or stimulus_preview_belongs or preview_inline_controls' --basetemp .test-tmp-stimulus-layout-20261026`:46 passed,849 deselected,23.19s.
- Final same46-case selection with `--basetemp .test-tmp-stimulus-final-wide-20261026`:46 passed,849 deselected,21.82s, exit0 after the fixture correction.
- `-m pytest tests/gui/test_preview_timeline.py tests/visual_stimulus/test_rendering.py -q -m 'not windows and not rig' --basetemp .test-tmp-stimulus-plots-20261026`:204 passed,6 deselected,2.51s.
- After retaining existing Per-projector/navigation proportions and clarifying group-rate footers, the same13 layout/category assertions passed but combined runs exited1 without summary. Isolated12 layout cases exited0. Removing the category test's unused full-Dashboard fixture eliminated the combined teardown exit:13 passed,882 deselected,4.20s, exit0. This identifies a fixture interaction, not a proven production defect. Earlier same13 cases passed in5.13s.
- Ruff check and format check: all seven affected source/test files pass.
- Win32 mypy: preview_frame.py, preview_placement.py, preview_motion_dial.py, stimulus_preview_area.py and rendering/preview.py pass.
- Backend boundaries:758 modules, zero violations; existing size advisories remain.
- `render.py`: nine offscreen captures, three styles, Combined at1600×900/900×700 and Per-projector at1600×900. Inspected Amber Combined, narrow Retro Combined and Standard Per-projector. Frames are readiness placeholders, with planned motion and unavailable FPS; no native viewer or runtime/device connection is created.

The initial expanded layout-test attempt used the wrong theme helper signature:
12 fixture failures,1 pass. Corrected to the repository's per-widget palette/QSS
pattern. Invalid exploratory Windows wildcard/nonexistent-file searches were
corrected. One documentation patch failed its context check without changing files;
re-read and applied against the current concurrent G01 revision318.

## Scope and limits

GUI footprint and placement calculations now explicitly distinguish borderless
stimulus windows from decorated camera windows. A rendering unit test verifies
hidden/borderless creation with the shared context; existing tests cover owner
binding before Show, manual-placement preservation, closure and release failure.
The native stimulus toggle is the Show/Hide control. No rendering clock, GPU
placement, scientific pixels, recording or resource authority changed. These
checks do not prove Windows/DPI/full-load or physical-output acceptance. No app
restart was performed. The existing rig checklist remains authoritative.

Final source SHA256 (repository-relative paths):

| File | SHA256 |
| --- | --- |
| src/cephvr/gui/stimulus_preview_area.py | 188E8CC5451EF3F8EA20626510A0FB975388F58D310566D38F728855BA38B9CB |
| src/cephvr/gui/preview_frame.py | C52C352C95F3840454A97EC8B7CED035F9BA9208882FE4D774CFE1F5578EB4F9 |
| src/cephvr/gui/preview_motion_dial.py | E4A568A748B9676A89344FE4690CD2FC6C8E49C5516050AC553410ADC7F867BD |
| src/cephvr/gui/preview_placement.py | 6468D4A88F8D356CC086BB20218B41436FA3168D3FA7952752CC707EE9E72772 |
| src/cephvr/visual_stimulus/rendering/preview.py | 2F60DC6C839F4CE7983431F0A301DF52659C7A702F5D0208E6EF33A1BC3166C1 |
