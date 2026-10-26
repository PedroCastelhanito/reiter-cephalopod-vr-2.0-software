# Motion source retained after locked binding — 2026-10-26

Dirty workspace based on f82be21f28d3c1141adeabe2558c29808062727a; concurrent work
preserved. Existing G01 requirement; no architecture-policy change.

Root cause: reference_fields used linked_to.isEnabled() to infer linking support.
That includes disabled ancestors from a session lock. The resulting row omitted
Motion source entirely and did not reconstruct it on unlock. isEnabledTo(editor)
keeps the local support decision while ignoring the external lock for field
composition. The field itself still inherits normal enabled/disabled state.
ARCH-002: one condition changed in the existing focused owner, no dependency,
capability flag or duplicated model eligibility predicate.

Before repair: expanded test_reference_motion_source_switches_controls_and_requires_target
with bind_locked False/True at1400/720px, Standard/Amber. Four locked cases failed
because motion_source was None; four ordinary cases passed in10.22s. After repair,
eight initial cases pass in2.06s. Then added saved Linked rebind while disabled.

Final selection:

```text
python -m pytest tests/gui/test_dashboard.py -q -k 'reference_motion_source_switches or mixed_projector_cards or texture_reference_link or presentation_rows_keep or projector_cards_label' --basetemp=.pytest_tmp_motion_source_diagnostics --timeout=30 --tb=short
17 passed, 936 deselected in7.59s
```

Executed through pytest.main with an exception diagnostic that prints uncaught Qt
exceptions and makes the result nonzero if any occur. Count: zero uncaught Qt
errors; command exits0. A preceding direct broader invocation reached100% but
exited1 without a summary and is not counted as a pass. Existing assertions retain
source246px geometry, Asset-edge alignment, source validation, popup visibility,
copy/paste/family ownership and media-mode exclusions. Locked cases additionally
assert the field is present and disabled, then enabled on unlock, retaining a
saved link target and fades through another locked rebind.

Ruff check/format on reference_fields.py/test_dashboard.py pass. Win32 mypy on
reference_fields.py passes. Backend checker:760 modules, zero boundary violations
with existing unrelated size advisories. Whitespace checked separately.

[Restored row](restored-row.png): actual isolated EpochComposer, Amber with bundled
font, two default Texture layers. Bind while composer disabled, assert source
exists/disabled, enable, show at1400px and focus the Left Motion source selector.
Three event passes then row.grab(); capture exits0 and was inspected. Default
texture.png is fixture data; no saved configuration changed or device commands.
No running app restart or native/DPI/rig acceptance.
