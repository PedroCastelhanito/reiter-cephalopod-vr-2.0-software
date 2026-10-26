# Motion source popup and width — 2026-10-26

Base: `f82be21f28d3c1141adeabe2558c29808062727a`, dirty tree including concurrent
Amber styling and trial layout edits. Owner supplied screenshots and requested
both choices visible without scrolling and a stable wide-row width.

Real offscreen EpochComposer probe with linked textures and complete Amber QSS:
two model entries, two 21px rows, but only a 26px viewport; Self at y=-21 and
Linked at y=0. Replacing the list view alone did not solve it. The existing view
now receives a minimum height from styled row hints plus frame. Wide rows reserve
246 logical pixels without stretch; narrow rows retain reflow.

Final command, repository Python 3.11:

```text
python -m pytest tests/gui/test_dashboard.py -q -k "reference_motion_source or compact_reference_rows" --timeout=30 --basetemp=.pytest_tmp_motion_source_final
```

[Raw result](pytest.txt): six passed. Existing owning tests cover Standard/Amber,
1400/720px layouts, both choices' vertical visibility for either selection, actual
mouse selection of Self, fixed wide-row width, required target validation,
persisted links/removal and neighboring compact-row commits/headers.

Ruff check/format (two source files and owning tests), Win32 mypy (two sources)
pass. Boundaries: 758 modules, zero violations, existing unrelated size advisories.
Initial attempts exposed list-view clipping, a transient pre-layout width assertion
and sandbox default-temp errors; final run waits for layout and uses workspace
temp. Initial static check required narrowing the optional view type.

ARCH-002 reuses focused widget/layout owners without dependencies or new state.
G01rev310 records the requested presentation rule. No native application restart,
alternate-DPI or rig acceptance is claimed.
