# Preview markers and Combined surface styling — 2026-10-26

Base f82be21f28d3c1141adeabe2558c29808062727a plus concurrent dirty GUI/native work.
Owner requests consistent vector widths, rotation arrowheads, GUI-matching surround,
theme-compatible marker colors and matching projector outlines. Owner clarified
that matching outlines means projector surfaces inside Combined, not GUI brackets.
Initial GUI bracket/caption coloring was removed; GUI chrome keeps normal styling.
G01rev323 records final scope, with existing V01/E08 native-preview ownership.

Translation/rotation pens are cosmetic2px, arrowheads7px when enlarged, allowing
compact shrink. Outer axes use1.5px. Rotation arrowheads use the signed tangent at
the arc endpoint. No indicators appear before trial time. Colors come from the
current theme's coral/projection/mirror/accent tokens for Left/Front/Right/Bottom.
Resolve paint colors from the current widget theme so early construction/style
switches cannot freeze an old palette. Combined table rows use the same identities.

Additive optional background RGB and bounded face/RGB map fields travel in existing
authenticated placement hints. Both stimulus boundaries use shared validation;
camera hints reject these fields. GUI supplies card color and the same identity
palette; native GL clears the surround and colors screen LINE_LOOP outlines only.
Textures, source buffers, physical output and recording pixels are untouched.
Bindings regenerated from19 owning proto sources; generated files not hand-edited.
ARCH-002 reuses painter/theme/placement/group owners without dependencies, new
processes or authoritative state. Existing size advisories remain cohesive.

Repository Python3.11 checks:

```text
python -m pytest tests/gui/test_preview_timeline.py -q --basetemp=.pytest_tmp_marker_style_done --timeout=30
python -m pytest tests/visual_stimulus/test_rendering.py -q --basetemp=.pytest_tmp_marker_rendering_done --timeout=30
python -m pytest tests/gui/test_dashboard.py -q -k "advanced_content_and_projector_filters or preview_frame_metrics" --basetemp=.pytest_tmp_marker_gui_corrected --timeout=30
python -m pytest tests/acquisition/test_manual_preview.py -q -k placement_admission --basetemp=.pytest_tmp_marker_admission --timeout=30
python -m pytest tests/visual_stimulus/test_controller_communication.py -q --basetemp=.pytest_tmp_marker_transport_all --timeout=30
```

112 instrument,119 rendering,3 Dashboard,10 camera-admission and8 authenticated
loopback cases pass (252 selected cases). Transport run used loopback permission;
initial preview-name filter selected none and was replaced with the owning module.
Tests cover both signed rotation arrowheads, constant pen width/head size at1×/2×,
all three theme palettes, GUI-to-native hint colors, invalid RGB/name rejection and
camera separation. Four native standalone-GL cases verify exact GUI background and
outline RGB plus unchanged source/composite pixels and crop/orientation behavior.
Ruff check/format11 final source/test files, Win32 mypy9 sources, boundaries758/zero
and whitespace pass. Initial patch context, typing and formatting errors corrected.

[Render script](render.py), [Combined](running.png), [Per-projector](per-projector.png)
and [Ready](ready.png) are isolated offscreen fixtures, with no device connection.
Inspection found early single-dial palette capture; paint-time resolution corrects
it. One script attempt exited-1073741819 without text; final explicit Qt teardown
and faulthandler run exits0. This is presentation evidence, not running-app or rig
acceptance. GUI frames in final images retain their ordinary theme colors.
Running GUI/backend processes were not restarted; reload the full application for
both sides of the new hints. Native multiwindow/DPI/full-workload remains unverified.
