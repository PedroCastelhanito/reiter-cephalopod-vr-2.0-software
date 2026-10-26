# Screen dimension row cards — 2026-10-26

Base f82be21f28d3c1141adeabe2558c29808062727a, concurrent dirty workspace retained.
G01rev330/G02rev151; isolated Qt, no runtime/device commands.

```text
python -m pytest tests/gui/test_dashboard.py -q -k 'screen_dimension_cards or calibration_and_screen_dimensions or amber_table_headers or projector_reference_measurements or projector_config_tabs or old_projector_snapshot or projector_configuration_json or projector_configuration_invalid' --basetemp=.pytest_tmp_dimension_cards_final --timeout=30 --tb=short
13 passed, 920 deselected in 14.48s
```

Final identity-label refinement: three screen_dimension_cards cases pass in1.02s
using .pytest_tmp_dimension_cards_label. These cover620/420px in Standard, Retro
and Amber; actual header/field edges, wrapped header containment, row focus and
painted fills, read-only distance, retained partial draft and disabled-state lock.
Other cases cover calibration draft separation, measurements, tabs and snapshots.

Ruff check/format and Win32 mypy on projector_geometry.py pass; tests lint/format
pass. Boundary checker759 modules/zero violations with unrelated size advisories.
Whitespace checked separately. Early checks corrected header/row first-column
spacing, narrow heading height, and an inherited Card.header name collision; the
final header uses its own name and preserves QLabel height-for-width policy.

[render_screen_dimensions.py](render_screen_dimensions.py) uses the bundled font,
Amber, representative display-only values and Left width focus. Inspected
[620px](screen-dimensions-620.png) and [420px](screen-dimensions-420.png) captures.
Both show distinct compact row surfaces and aligned columns with the active card
highlight. This is offscreen presentation evidence, not native/DPI/rig acceptance.
