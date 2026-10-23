# GPU Combined rig preview — 2026-10-23

Source: dirty working tree based on `59a973ac3ffc6fb331bbee1d93c6b283d6b90474`,
with concurrent unrelated changes preserved. Decisions:
[G01](../../../docs/architecture/gui.md#g01),
[V01/E13](../../../docs/architecture/visual_stimulus.md).

## Implementation and review

Combined's existing optional GLFW window maps the existing GPU composite texture
onto prepared screen planes. Per-projector windows retain their flat crop shader
and placement. No output textures, stimulus state/observer, recording layout,
CPU pixel transport, contract schema or device command is changed. Geometry updates
from each prepared trial. The runtime geometry does not include tank dimensions;
the view displays calibrated screen planes and borders, without invented tank walls.
This is output-raster visualization following the protocol rig's placement convention,
not an inverse reconstruction of arbitrary imported warp meshes or a new observer render.

ARCH-002 review keeps window lifetime, pacing, rates and native ownership in the
existing base viewer/group. The new focused module owns only rig projection,
mouse-camera state and GPU drawing. A prepare hook selects either flat or rig
resources (three resources each); no unused flat quad is allocated for the rig.
The oversized native assembly receives only the geometry constructor/update wiring;
its projection, presentation, recording and deadline paths are unchanged.
No dependency was added. All tests extend existing owning behavior modules.

## Validation

Repository Python3.11 on Windows. Commands use explicit unique repository-local
pytest basetemp paths. GUI checks set `QT_QPA_PLATFORM=offscreen`.

- `python -m pytest tests/visual_stimulus/test_rendering.py -q`:117 passed, exit0.
  [Raw final output](rendering-tests.log). Four native standalone-GL cases use
  asymmetric gradients through the real crop compositor and rig shader. All four
  face quadrants match expected physical placement, rotation changes the preview,
  and source/composite texture bytes remain identical. Hidden/minimized draws skip.
  Existing uncropped recording/Bottom rotation/readback tests also pass.
- A hidden native GLFW4.3 shared-window test prepares the real viewer, verifies all
  three mouse/focus callbacks and exactly three GPU resources, then confirms window,
  context and resource release. No visible test window or projector is opened.
- Unit coverage exercises left-drag sensitivity, yaw wrap,±80° pitch clamp, release,
  focus-loss cancellation and double-click reset while proving immutable prepared
  geometry is unchanged. Group coverage verifies one Combined draw versus individual
  draws, geometry/layout refresh, mode switching, X-close polling behavior and
  synchronization of previously hidden readers.
- `python -m pytest tests/gui/test_dashboard.py -q -s -k 'preview_workspace or
  category_preview_modes or drift_pairs or trial_preview_maps'`:26 passed,
  831 deselected, exit0. [Raw final output](gui-tests.log). An earlier narrower
  mode/layout selection passed5 cases. Combined has one rig footprint; individual
  frame/instrument ownership remains stable through repeated switches.
- Ruff check and format-check pass7 files: `preview.py`, `preview_rig.py`,
  `preview_group.py`, `native.py`, `stimulus_preview_area.py`, and the two owning
  tests. Win32 mypy passes the five source files. Backend boundaries:758 modules,
  zero violations; existing cohesive source-size advisories reviewed.

All implementation test runs passed; final runs follow removal of unnecessary
flat-view GPU resources from Combined. No runtime failures were observed in these
bounded checks. These results do not establish optical correctness or rig throughput.

## Rendered inspection

[Home view](home.png) and [rotated view](rotated.png) are900×700 standalone-GL
framebuffer captures from the actual rig shader. Fixture geometry uses
`screen_corners(RigDimensions(120,166,110,(60,93,53)), ...)`: Front distance91mm,
other distances51mm, wall sizes100×80mm and Bottom126×94mm. Existing preview
composition receives four192px synthetic checkerboards (Left cyan, Front gold,
Right purple, Bottom green). Camera pitch25°, yaw25°/100°. Pixel readback is used
only by this QA capture; the product path has none. Both images were inspected for
plane placement, gaps, aspect, fitting and rotation. No current experiment pixels
or hardware measurements are represented.

The application was not restarted and saved experiment/calibration files were not
changed. Physical orientation, real mouse interaction/DPI/owner follow under the
managed application, fault/recovery and full-load performance remain on the
[single rig checklist](../../rig-verification.md#protocol-category-previews).
