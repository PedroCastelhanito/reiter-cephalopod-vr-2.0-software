# Advanced content and projector selection

2026-10-26 Asia/Tokyo. Dirty working tree based on
f82be21f28d3c1141adeabe2558c29808062727a; concurrent GUI/layout/font work preserved.
Repository Python3.11. GUI uses offscreen Qt; renderer pixel tests use standalone
ModernGL4.3, not native live projector acceptance.

Commands/results:
- `python -u -m pytest tests/gui/test_dashboard.py tests/gui/test_preview_timeline.py -q -x -k 'advanced_content_and_projector or preview_toolbar_wraps or stimulus_preview_belongs or advanced_projector_toggles or category_preview_modes or stimulus_preview_reclaims or preview_timeline_visibility or preview_selection_waits or preview_controls_hide' --basetemp=.pytest-advanced-verified`:36 passed,967 deselected,6.32s.
- `python -u -m pytest tests/visual_stimulus/test_rendering.py tests/acquisition/test_manual_preview.py -q -x -k 'projector_preview_group or native_gpu_rig_crops or preview_placement_admission_bounds' --basetemp=.pytest-advanced-wire`:15 passed,254 deselected,1.13s.
- `python -u -m pytest tests/gui/test_preview_timeline.py -q --basetemp=.pytest-advanced-timeline`:100 passed,1.78s.
- `python -u -m pytest tests/gui/test_dashboard.py -q -x -k advanced_content_and_projector --basetemp=.pytest-advanced-final-state`:2 passed,901 deselected,0.66s.
- Ruff check/format10 edited handwritten source/test files and Win32 mypy7 sources pass.
  Backend boundaries758/zero, existing cohesion warnings plus PreviewWorkspace
  reviewed as one presentation/request owner. `python tools/generate_contracts.py`
  generated19 schemas; generated bindings stay under existing ignore rules.

Earlier attempts: temporary Front-only fixture caused1 failure/5 passes; removed
that stale setup. Placement helper test needed a real parent host (1 failure/8 passes),
then11 cases passed. Broader run exposed redundant instrument-layout invalidation
(1 failure/19 passes); removed it, all12 geometry cases pass. Subsequent36-case run
covers these fixes. Fixed import order/strict zip lint findings.

Visual method: isolated themed QWidget/PreviewWorkspace, registered terminal font,
configured four-projector grating program, playback0.5, local visible PreviewView,
Combined/Per-projector at1600/650 widths; process events then QWidget.grab. Inspected
controls-Per-projector-650.png: compact ON/OFF toolbar and image/plot pairs.
This isolated capture exited1 at teardown with no diagnostic after image creation;
images are visual evidence only. Initial Dashboard sample captures were not a
representative native lifecycle and are not runtime passes. No app restart or live
native multiwindow/DPI/device/full-load claim.

Source hashes at assessment:
- `src/cephvr/gui/previews.py`: `b61d9c0b78906bd2262a49a5e41f118be8b2c008b3f7da001832fbbb5367c1db`
- `src/cephvr/gui/stimulus_preview_area.py`: `918fcfc43b3180a9bb5aed3172163a832ff5e6e1dcc81fb3f6f594b131569aff`
- `src/cephvr/gui/preview_timeline.py`: `c316a5fab9d73024e8e66807f537c73afad698cfc78b1fdc12cd0fa69a849908`
- `src/cephvr/shared/preview_placement.py`: `cb93a124c470e876ce884b6361ba1841d267b3300cd806e9c55bd81043c56a01`
- `src/cephvr/visual_stimulus/rendering/preview_group.py`: `ad52ce95fe68db8261ed3b827812675405cc007650a6bb5fd1677f95f8e79a1e`
- `src/cephvr/visual_stimulus/rendering/preview_rig.py`: `21c23f72c89552cc3fd1f2c8c45ff44b6eb62ad36bb0c4fdc8f535004e3a3d4a`
- `contracts/cephvr/control/v1/services.proto`: `0b9a87ec6fc0b822ccf030e37d15b40d3f2a47c03c85fdc13546f0a9d8ef25f6`
