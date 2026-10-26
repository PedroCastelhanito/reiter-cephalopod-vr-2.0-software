# Amber tab chevron alignment — 2026-10-26

Base revision: f82be21f28d3c1141adeabe2558c29808062727a plus dirty concurrent GUI
changes. Owner screenshot shows leading markers overlapping projector tab icons.

Real offscreen Qt probe at1920×1032: Geometry tab text rectangle starts at41px,
icon starts at17px, but leading marker rectangle was36.5–48.5px. The existing
code centered the text, then incorrectly used that center to place the icon too.
Qt anchors the icon at the text rectangle's left edge. The marker now uses that
edge minus icon width and Qt's4px icon gap. Shared horizontal padding increases
16→18px to contain the12px marker and6px gap fully inside the tab. Trailing marker
continues to follow centered text. No new state/dependency or architecture choice.

Repository Python3.11 commands:

```text
python -m pytest tests/gui/test_dashboard.py -q -k phosphor_navigation_uses_chevron --basetemp=.pytest_tmp_tab_chevron_before --timeout=30
python -m pytest tests/gui/test_dashboard.py -q -k "phosphor_navigation_uses_chevron or phosphor_tab_bars_elide or configuration_scroll_keeps_projector_status_fixed" --basetemp=.pytest_tmp_tab_chevron_after --timeout=30
```

Before: both1400/1920px cases failed the new icon-separation assertion.
After:4 passed,867 deselected in6.01s. Existing paint/hover/sidebar/trailing-marker
checks remain; all projector leading markers must be inside their tab and at least
6px before its icon. Narrow overflow and screenshot-size full-label fit pass.
Ruff check/format3 files and Win32 mypy2 sources pass. Boundaries758/zero with
existing unrelated cohesion advisories. Whitespace check passes.

[Inspected tab-strip render](tabs.png) uses the real sample Dashboard, Amber,
1920×1032 offscreen window, Devices/Projectors selected, event-loop/layout settled,
then setup_tabs.grab(); strip620×40. This is isolated widget rendering; its grab
background is not evidence of native window compositing. Native application was
not restarted; alternate-DPI and hardware/rig acceptance remain unverified.
