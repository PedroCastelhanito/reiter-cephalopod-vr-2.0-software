# Plot typography and pretrial indicators — 2026-10-26

Base f82be21f28d3c1141adeabe2558c29808062727a plus concurrent dirty GUI work.
Owner requests plot typography matching preview info and no arrows before trial
start. G01rev321 refines the earlier initial-planned-values presentation rule.

The shared instrument painter explicitly inherits the widget font family/weight
and caps text at the shared preview-info12px size. Point size and absolute tracking
compensate for enlarged drawing transforms; compact instruments can still shrink.
No font asset, dependency or runtime-policy change. Timeline keeps configured
instruments/axes visible when elapsed time is absent, but clears velocity vectors,
angular indication, current orientation and map pose/history. Existing unavailable
or live-input reasons remain; otherwise show Waiting for trial. Current-value
display resumes at actual elapsed0. The window ignores elapsed fields during
Configuration/Ready/Starting rather than letting stale time display motion.

ARCH-002 review reuses focused painter/sample/window owners and owning test modules;
no new authoritative state or dependency. Existing timeline size warning remains a
cohesive plan/refresh owner. No renderer, actual motion or timing policy changes.

Repository Python3.11 final commands:

```text
python -m pytest tests/gui/test_preview_timeline.py -q --basetemp=.pytest_tmp_plot_font_integrated --timeout=30
python -m pytest tests/gui/test_dashboard.py -q -k "preview_ignores_elapsed or category_preview_modes_keep_camera_space or preview_window_supplies_current_profile" --basetemp=.pytest_tmp_plot_font_final --timeout=30
```

100 timeline checks pass in1.93s; five Dashboard cases pass in4.50s. New painter
checks compare effective font size/family/weight/tracking against actual PreviewFrame
info across Standard/Retro/Amber at0.75×/1×/2×. Existing shared-dial and arena tests
now assert empty pretrial vectors, turns and pose/history, then normal values after
elapsed0 and after reset to waiting. Window cases reject stale12s in three pretrial
phases and admit elapsed0 at Running. Ruff check/format5 files, Win32 mypy3 sources,
boundaries758/zero and whitespace pass; existing size advisories retained.

Integration limits: a wider20-case Dashboard selection had8 failures during
concurrent available-projector/layout work (two Per-projector cases unexpectedly
had Front only; six830px cases had195px frames in186px cells). Those failures were
not closed by font checks; retained under the existing advanced-preview task.
A later timeline run initially lost all samples in12 all-projector fixture cases
because the new available-face filter needed explicit configuration; adding the
fixture's intended four faces restores all100 timeline checks. Initial import and
format errors were fixed; one no-op patch/search attempt changed no code.

[Render script](render.py) and [Ready](ready.png)/[Running](running.png) are isolated
offscreen presentation fixtures with four authored gratings, no backend connections.
Ready inspected: same font sizing as info footer, blank arrows/rotation indicators,
configured table retained. Script asserts vectors appear only after playback0.
No application restart, native/DPI/hardware or measured-output acceptance.
