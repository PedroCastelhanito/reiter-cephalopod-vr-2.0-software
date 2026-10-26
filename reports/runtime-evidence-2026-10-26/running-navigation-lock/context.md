# Running navigation lock — 2026-10-26

Dirty workspace based on f82be21f28d3c1141adeabe2558c29808062727a; concurrent changes
preserved. G01 revision333. Repository Python3.11, offscreen Qt only.

```text
python -m pytest tests/gui/test_dashboard.py -q -k 'running_navigation or main_dashboard_click or dashboard_close_waits or dashboard_view_tabs or devices_side_rail or responsive_navigation or navigation_repaints or video_previews_toggle or video_hide_defers or preview_workspace_pending_visible or managed_preview_hides or preview_selection_waits' --basetemp=.pytest_tmp_running_nav_checked --timeout=60 --tb=short
30 passed, 919 deselected in17.81s

python -m pytest tests/gui/test_dashboard.py -q -k 'preview_slot_tracks_relevant_tabs or preview_log_four_lines or preview_inline_controls_follow_camera_recording_choices' --basetemp=.pytest_tmp_nav_placement_checked --timeout=60 --tb=short
7 passed, 942 deselected in12.94s
```

Assertions cover all four active phases, main button and direct-selector/signal
bypasses, forced Dashboard entry, disabled side routes, normal navigation after
Ended, Dashboard-only preview closure in Configure/Running, retained recording
choices and no session command, child Monitor selection without closing, deferred
opening cancellation and closure after a pending operation. Inactive visible
sources also close. Existing Video hide and serialized native-command tests remain.

Eight initial focused cases pass in12.81s; the expanded23-case selection passes
in20.00s. Three cross-page fixtures were updated to exercise their placement/log/
recording behavior outside the new runtime lock. The first integration run had one
stale decorated-frame assertion; corrected to the accepted frameless overlay
footprint under G01rev332, retaining full containment checks. Final37 cases pass.

Ruff check/format: window.py, previews.py and test_dashboard.py pass. Win32 mypy:
both sources pass. Backend boundaries:760 modules, zero violations with existing
unrelated size advisories. No new module/dependency or second close-intent state;
the existing workspace closure set now also covers explicit Dashboard exit.

A read-only test source audit initially used a slow AST source extractor; the
equivalent line-slice audit completed promptly. The first extractor subsequently
completed normally. An optional CIM process-inspection query lacked permission;
no escalation or process termination was used. No native app/device commands,
protocol stop/restart or live viewer acceptance; results are local GUI evidence.
