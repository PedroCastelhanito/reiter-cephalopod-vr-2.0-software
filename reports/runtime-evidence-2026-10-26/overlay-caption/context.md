# Camera overlay header — 2026-10-26

Base revision f82be21f28d3c1141adeabe2558c29808062727a plus concurrent dirty workspace.
User screenshots show nonclient hover resize and obsolete bottom frame space.
G01rev332 replaces native hover chrome with a private-image overlay; A10 source,
producer and viewport ownership unchanged. ARCH-002 uses existing helper/rendering.

Validation using .venv/Scripts/python.exe:
- pytest tests/platform/test_window_coordinates.py tests/acquisition/test_manual_preview.py -q --basetemp .test-tmp-overlay-caption-close2:171 passed,6 pre-existing SWIG warnings,1.77s.
- QT_QPA_PLATFORM=offscreen pytest tests/gui/test_dashboard.py -q -k 'preview_workspace or preview_video or video_previews_toggle or preview_placement or preview_frame' --basetemp .test-tmp-overlay-gui2:16 passed,921 deselected,15.32s.
- Ruff check/format six changed owners/test files pass.
- mypy --platform win32 preview_caption.py, highgui.py, preview_placement.py:pass.
- check_backend_boundaries.py:760 modules,zero violations; existing size warnings.

Native test creates isolated HighGUI viewers with actual shared rings, checks square
client/outer bounds and exact unchanged child bounds across hover, dispatches an
image-overlay X click, checks wheel/pan/reset and surviving producers/other viewer.
Pure checks verify unchanged pixels below overlay and native move-message routing.
This is not a live trial pointer-drag/Snap, alternate-DPI or throughput acceptance.
Current session was not restarted. Initial stale mocks and placement keyword fixture
failed and were updated; unprivileged test attempt was interrupted after a stall.
