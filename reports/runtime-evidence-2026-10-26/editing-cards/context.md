# Editing cards — 2026-10-26

Base f82be21f28d3c1141adeabe2558c29808062727a; dirty concurrent workspace.
Actual Qt widgets rendered offscreen by render.py at600px, Amber with bundled font.
Camera, Tracking, Calibration and Variation captures visually inspected. Explicit
widget cleanup; capture exits0. No connected device or running app access.

Final validation (repository Python3.11):
```
python -m pytest tests/gui/test_dashboard.py -q -s -k "variation or tracking_methods_preserve or tracking_preview_stages or tracking_draft_roundtrip or camera_selection_restores or camera_pin or calibration_adjustment_steps or live_calibration_coalesces or active_calibration_measurements or mixed_projector_cards or projector_cards_label" --basetemp=.test-tmp-card-reuse7
```
42 passed,866 deselected,67.66s. Ruff check/format10 files, Win32 mypy9 sources,
boundaries759 modules/zero violations and whitespace pass. Existing size advisories
reviewed: extraction owns shared appearance; no new mixed backend responsibilities.

Earlier attempts: focus fixture initially omitted selected epoch (3 failures,
corrected and passed); broad39 passed/3 failed revealed empty-rule Remove disabled
by card parent (two cases, fixed) and existing linked-Speed50ms notice race. Bounded
condition polling keeps its assertions and passes. Follow-up9 passed/one timing
failure preceded the final all42 pass. Concurrent test formatting changes were
normalized without changing their behavior. No full-suite/native/rig claim.

Source SHA256 at completion:
- `editing_card.py`: `f8ac2fc8e56171f97e9217d410c279d1b2d0e826892db5a76ce8eb12c2054ae6`
- `variation_cards.py`: `c944f22631dafbe6a84b28b788a8add358924ca1e26859e6b3896d6d81778495`
- `batch_variation.py`: `8972ffbd983fb8e9d3164edd7e76db349bfa2c850b518a70a6c0431ad4bc0579`
- `batch_create.py`: `aabe1bf414b0408014c9ff8e7fdbe8da79d43eb1a76e3d2180460e7969e2b3a9`
- `projector_reference.py`: `f6a69a449f8ae709efad259b840dcc11293d2afa09d1822b577926953c755a63`
- `projector_calibration.py`: `3d8cb8a047d23e08ca9f571fe69e7ed1539eac6eeeaa1defdb9b3667b8c56f1f`
- `projectors.py`: `3a81e9d78f519c583d9f4b0b78ddc8b8a05c9b8dda2766dca5d5534c0b005047`
- `tracking_stages.py`: `1b2d8e66230156bccc76690ec0f923ea5bfa49c6fc3a8a10474b6ae40a376d8b`
- `cameras.py`: `bf5572ad6e6783ea22f8b4c29e1cdcf9e3969ea981addaa79deb2a6836d1df6e`
