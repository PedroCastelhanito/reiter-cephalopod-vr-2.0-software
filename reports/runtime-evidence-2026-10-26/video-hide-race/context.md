# Video-off close race — 2026-10-26

Source base f82be21f28d3c1141adeabe2558c29808062727a plus concurrent dirty workspace.
Evidence: user screenshot with Video unchecked and camera image over Stimulus;
source trace PreviewWorkspace.request pending guard and shared queue_camera admission.
Fix retains pending section hides and serializes ManagedPreviewViewers hides before
relayout. Existing G01 semantics and acquisition ownership unchanged.

Validation using .venv/Scripts/python.exe, QT_QPA_PLATFORM=offscreen:
pytest tests/gui/test_dashboard.py -q -k 'video_hide_defers or video_previews_toggle or preview_selection_waits or preview_workspace or managed_preview or camera_connect_opens_only' --basetemp .test-tmp-video-hide-final
29 passed,913 deselected,13.52s (loopback-enabled elevated invocation).
Ruff check/format previews.py,managed_preview_viewers.py,test_dashboard.py pass.
Win32 mypy previews.py,managed_preview_viewers.py pass.
Backend boundaries760 modules,zero violations; existing size warnings reviewed.
Initial serial-queue test expected empty console rather than unchanged console;
fixed fixture baseline. Unprivileged expanded test invocation stalled and was
interrupted; not counted as a pass. Earlier24 workspace/selection checks passed.
No current-trial stop/restart or native toggle acceptance claimed. Existing TODO
retains live verification alongside overlay-caption drag and saved-divider ratio.
