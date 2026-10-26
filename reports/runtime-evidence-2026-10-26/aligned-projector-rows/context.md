# Aligned compact projector rows — 2026-10-26

Working tree based on f82be21f28d3c1141adeabe2558c29808062727a, with concurrent
changes preserved. G01 revision327 implements the approved compact grid and the
owner's Asset-edge correction. No runtime/device commands.

Owning validation:

```text
.venv/Scripts/python.exe -m pytest tests/gui/test_dashboard.py -q -k 'projector_cards or mixed_projector_cards or reference_motion_source or presentation_rows_keep or texture_reference_link or unified_subgroup or large_random_group or arena_xyz_orientation or protocol_arena_limits or fade' --basetemp=C:/Users/ReiterU_PC/.codex/visualizations/2026/10/26/01a17586-62df-7660-b6ca-af466c7051c3/.pytest_aligned_rows --timeout=30 --tb=short
24 passed, 900 deselected in 18.81s
```

Four source-switching cases pass again in3.96s after asserting the Advanced card's
right edge. Tests cover shared column guides/control baselines, Asset-edge endings,
three styles,1400/780/520px reflow, source choice visibility/width, actual relocated
field edits, validation, fades, layers and family-specific authoring.
The first stricter geometry run exposed a6px Layer baseline offset; moving that
rail into the main grid fixed it. An initial broader run used a repository-local
temp root that the demo generator rejects; a Windows Temp retry lacked write
permission. Final run uses the authorized visualization root outside the repo.

Ruff check/format pass for projector_reference.py, stimulus_parameters.py and
test_dashboard.py; Win32 mypy passes both source files. Backend checker:759 modules,
zero boundary violations with existing size advisories; whitespace check passes.

[render.py](render.py) builds an isolated EpochComposer with the bundled font and
Amber style, three linked textures and one Self texture with Advanced expanded.
Paths are display-only fixture values; it sends no commits or device commands.
Inspected [desktop](amber.png) and [520px reflow](narrow.png). The first render
attempt included the empty rig-wide row in projector iteration; corrected to use
configured screens. Source geometry tests exercise valid models independently.
These offscreen renders are not native/DPI or experiment acceptance.
