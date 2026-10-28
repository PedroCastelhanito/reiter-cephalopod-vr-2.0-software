# Stale asset declarations after epoch replacement — 2026-10-28

Owner screenshot: Setup fails opening import-1cy0sy41/CephVR_Fold_Test_Bottom_Below.png.
Read C:/Users/ReiterU_PC/Desktop/Alsu/protocols/sparse-noise_20mins_protocol.json.
Active source has four sparse-noise layers in one300ms epoch, with21 unused asset
entries from prior image/texture edits. The inactive category template is separate.
This is an orphaned declaration defect, distinct from the earlier pending-assets UI
error. Source revision e4dd8f2694aa075380fe6711a884fe5894763c6f plus working changes.

Reused drop_unused_assets after subgroup repetition rules and drafts are finalized,
so active settings, other epochs, conditions and variation drafts retain references.
No change to backend preparation or required-asset errors. G01/V04 already specify
asset-free generated noise/gratings; ARCH-002 favors the existing focused helper.

The original protocol is retained byte-for-byte in
[sparse-noise_20mins_protocol.original.json](sparse-noise_20mins_protocol.original.json).
SHA256:84a5e490d623c75de39ce17829f705b2b6ab273d53d86e0dc549e50533c3d767.
[Repaired copy](sparse-noise_20mins_protocol.repaired.json) changes only active-trial
assets from21 entries to zero; structural comparison confirms all other data,
including timing, repetition, settings and category templates, is unchanged.
validate_protocol passes on the repaired document. Desktop original untouched.

Commands use .venv/Scripts/python.exe, QT_QPA_PLATFORM=offscreen:
- pytest tests/gui/test_stimulus_authoring.py -q -k type_change_prunes
  --basetemp=.tmp-stale-assets-red: both new cases fail before repair, reproducing
  the last image declaration surviving Image→Sparse noise and Image→Grating.
- pytest tests/gui/test_stimulus_authoring.py tests/gui/test_dashboard.py -q
  -k 'type_change_prunes or unified_subgroup or subgroup_rules_persist'
  --basetemp=<external>/stale-assets-tests:8 pass,1076 deselected. Covers preservation
  while another epoch uses the asset, removal after its last use, subgroup variations,
  shared sources, atomic edits and persistence.
- Ruff check/format on subgroup_editor.py and test_stimulus_authoring.py: pass.
- mypy --platform win32 src/cephvr/gui/subgroup_editor.py: pass.
- tools/check_backend_boundaries.py:791 modules,zero violations; no changed module
  exceeds the advisory. git diff --check:pass.

External root:C:/Users/ReiterU_PC/.codex/visualizations/2026/10/28/
01a17ff3-fd67-7e30-89d0-9b4ae49a6e0e.

No live state edits, managed-app restart, Setup/Start, device operation or cleanup
acceptance. The screenshot's unconfirmed cleanup is not a successful release proof.
Reload the repaired copy after normal restart; native execution remains unverified.
