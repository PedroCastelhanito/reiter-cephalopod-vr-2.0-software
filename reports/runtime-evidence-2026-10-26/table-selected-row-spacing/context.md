# Selected row spacing — 2026-10-26

Source: current uncommitted workspace, no isolated revision attribution.
Method: offscreen PyQt6, standard app stylesheet, sample DashboardWindow at1920x980,
Amber appearance, Cameras tab,200ms settling then row0 selection and50ms settling.
[Camera table](cameras.png) visually inspected: first selected row retains header
gap and same card height as row1; both measured row heights66px.

Existing row-paint test now checks selected fill and all four top/bottom gap pixel
positions across Standard/Retro/Amber. Initial runs failed because clearing the
delegate state alone and then the item stylesheet still left Qt's row-level palette
highlight. Transparent selection-background-color resolves that remaining paint.
Final three-theme pixel cases pass.

Broader selection: table_row_bands, camera_batch_check_preserves_selection,
camera_selection_restores_pfs and projector_config_tabs_keep_column_width:
5 passed/1 fixture error (sandbox temp directory creation). The blocked camera
selection test passes with --basetemp pointing at this directory's pytest-temp.
Ruff/format tables.py/theme.py/test_dashboard.py and Win32 mypy tables.py/theme.py
pass; boundaries760 modules/zero violations. No live device or rig validation.
