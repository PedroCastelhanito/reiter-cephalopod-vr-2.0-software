# Protocol cards - 2026-10-26

Source base: f82be21f28d3c1141adeabe2558c29808062727a, dirty concurrent workspace.
G01rev320/G02rev147. Offscreen Qt only; no running app or hardware access.

`render.py` creates the real EpochComposer with mixed family presets, applies Amber,
loads the bundled font and captures1400/780/520 widths with Left focused. Initial
fontless captures showed missing glyphs; replaced after font loading. Explicit Qt
widget deletion resolves teardown exit1 after otherwise completed captures. Final
render exits0. Wide and520px captures visually inspected; no field clipping remains.

Final test command (repository Python):
```
python -m pytest tests/gui/test_dashboard.py -q -s -k "mixed_projector_cards or projector_cards_label or reference_motion_source or reference_advanced_controls or reference_type_change or presentation_rows_keep_layers or blank_layer_then_family or batch_reference_projector or layer_actions_offer" --basetemp=.test-tmp-protocol-cards6
```
18 passed,885 deselected,16.01s. Earlier broader reference selection45 passed/one
50ms linked-variation warning timing failure; linked-variation and card cases then
passed13/13 in16.29s. Initial captured8-case process ended1 without summary; not a
complete pass. Ruff check/format4 files and Win32 mypy3 source files pass;
boundary checker758 modules/zero violations, existing size advisories retained.

Source SHA256 at completion:
- `src/cephvr/gui/projector_reference.py`: `1c767cd307c46ea874f137a38ce8dfd9d5def3a758d073cbe598358d83c7a7a7`
- `src/cephvr/gui/epoch_composer.py`: `3be7e74d4a2ed0796b67f80847b67bd83abb6651e6796f17ca80590fe82455cf`
- `src/cephvr/gui/theme.py`: `68e85032eb2d72b3d0432415ba1b535ff921d539cd914a91ad722d9f8699b4f7`
- `tests/gui/test_dashboard.py`: `431883fefa5ba20109f6779076f7cc948be8613e0cb2ae8fe04b799a9fcc34b7`
