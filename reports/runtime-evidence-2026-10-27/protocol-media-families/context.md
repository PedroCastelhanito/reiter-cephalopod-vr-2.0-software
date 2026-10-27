# Protocol Media families — 2026-10-27

Base revision: `c7881b1f87a5d294383d310ebcb92630cd825099`; shared uncommitted tree.
Source files/hashes: [source-files.json](source-files.json). Concurrent authoring,
physical-field, Grating compatibility and monitoring changes were present throughout.

## Authorized outcome

Two protocol categories; six independent projector/layer epoch choices. Owner
follow-ups forwarded from the clarification chat explicitly authorize inline Sparse
noise and Grating, shared pattern/phase only for linked Gratings, and architecture
updates. Owner selected Bottom-based unfolding preserving spacing with possible
wall/wall seams. G01rev369, V02rev18, V04rev34 and V07rev6 govern the implementation.
No external scientific default or new dependency/process was selected.

## Local verification

- `.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k
  'media_family or inline_grating_pattern or sparse_noise_layer or protocol_category
  or category_first_visit or presentation_rows or protocol_type_switch or
  category_preview_modes or grating' --basetemp=.pytest-media-gui-final`
  with `QT_QPA_PLATFORM=offscreen`: **28 passed, 1027 deselected**, 20.73 s.
- Same GUI module, `-k inline_sparse_noise_discards`, offscreen and isolated basetemp:
  **4 passed, 1055 deselected**, 5.21 s. Authority/root/geometry/screen changes
  discard late preparation; unapplied parameters remain pending.
- `.venv/Scripts/python.exe -m pytest tests/visual_stimulus/test_configuration.py
  tests/visual_stimulus/test_resources.py tests/visual_stimulus/test_compilation.py
  tests/visual_stimulus/test_rendering.py -q -m 'not windows and not rig'
  -k 'not demo_image_recipes' --basetemp=.pytest-media-backend-final-2`:
  **299 passed, 50 deselected, 3 subtests passed**, 3.44 s. Includes actual eager/deferred
  image preparation, one-epoch sparse resource schedules, canonical motion/category
  validation, period/angle variations, shared edge phase, unlinked independence and
  exact boundary phase retention. Three demo asset cases require output outside the
  repository; they are explicitly excluded here, not reported as passes.
- `.venv/Scripts/python.exe -m pytest tests/visual_stimulus/test_rendering.py -q
  -k native_inline_grating --basetemp=.pytest-media-native-2`:
  **3 passed, 186 deselected**, 0.59 s, synthetic offscreen OpenGL only. Centered
  sinusoidal/intermediate/square waveforms agree with the CPU formula within 3e-6.
- Scoped Ruff check/format: 49 files pass. Win32 mypy: 44 sources pass.
  Published schema generator: 14 schemas, 0 drift after regenerating source/prepared
  schemas from their canonical definitions. Boundary checker: 785 modules,
  zero violations, with existing cohesion advisories. A local documentation check
  verifies 261 file/anchor targets, governing register revisions and the two edited
  JSON schemas; git diff --check passes (line-ending advisories only).

## Repairs and failed/partial attempts

The marked-Grating assignment regression failed before repair: a 37-degree occurrence
assignment initialized to zero in renderer state. The repair is guarded to marked
Grating only, within the authorized orientation behavior; preview uses that same
owner. The briefly broader repair was narrowed before completion. The observed general
non-Grating assignment gap remains `runtime-general-epoch-assignments`, explicitly
deferred by the owner's monitoring instruction. No general assignment rollout is
claimed.

Initial checks exposed stale three-category/no-motion assertions and asset-backed
Grating fixture assumptions; these were reconciled while preserving the old asset
compatibility scenarios. One queued GUI alignment callback assumed every row had an
Asset cell and raised StopIteration for new asset-free rows; the owning layout now
uses a safe stimulus anchor. Interim mypy issues and a local indentation edit were
corrected before the final checks.

An initial backend run used in-repository basetemp: three demo fixture setup errors
correctly rejected sample generation there. A redirected broad run produced no
usable result and was interrupted. Later xdist broad GUI/backend attempts were
interrupted to avoid competing with the monitoring chat's serial integration run;
GUI workers reported 'Not properly terminated' and restarted. Those attempts are
not full-suite passes. The monitor owns combined final-suite evidence and commit/sync.

## Scope limits

No managed-app restart, physical projection, optical seam/timing/frame-lock,
alternate-DPI or full scientific workload acceptance. The existing rig checklist
remains open. Legacy files containing distinct Media and Drift category schedules
reject atomically rather than merging or discarding experiment order.

ARCH-002 review extracts inline sparse/grating controls and common field geometry
into focused owners; reuses generators, state, protected images, residency, clocks
and shader evidence. Remaining size advisories concern cohesive canonical-model,
form assembly and renderer lifecycle owners; this change adds no runtime back-reference,
process or dependency. Tests extend the existing owning behavior modules.
