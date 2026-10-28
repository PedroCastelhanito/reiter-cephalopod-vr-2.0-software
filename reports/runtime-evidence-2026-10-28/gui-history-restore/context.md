# GUI history restore repair — 2026-10-28

Source: owner screenshot and local `config/runtime_gui.json`; source revision
`e4dd8f2694aa075380fe6711a884fe5894763c6f` with pre-existing uncommitted changes.

Method: repository `.venv/Scripts/python.exe`, inline Python calling
`validate_protocol(read_snapshot('config/runtime_gui.json')['protocol'])`.
Reproduced four forbidden `sparse_noise: null` fields on image settings, followed
by dependent empty-sequence validation errors. No non-null sparse configuration
was present. G01 correctly prevents overwriting a failed restore.

Repair: backed up original bytes to [runtime_gui.original.json](runtime_gui.original.json),
then removed exactly those four null fields using QSaveFile atomic replacement.
Compared parsed objects and bytes; no other bytes changed. No source, policy,
dependency, device or running-process changes. ARCH-002 review selected the bounded
saved-file correction instead of broadening the canonical stimulus schema.

Validation: offscreen DashboardWindow with isolated QSettings and sample camera
inventory serials aligned to the saved file. Full GuiSnapshot.validate, restore,
and capture/validate passed before writing. The first fixture attempt rejected
sample serials that did not match; this was a test-fixture mismatch, not a second
observed live defect. This does not establish actual connected inventory or native
restart/Setup acceptance. The live process retains its failed-restore flag until
restart; no application closure or loss of current unsaved edits was authorized.

Original SHA256: `bc7567464fa1922c9d5540c8850e7759d62c331585b3f7794c5663bb98c3ded6`.
Repaired SHA256: `bc41765bfc5d5fe514a76b789df4ba1c05c2672ef5fd13c06c3ddfe47279b386`.
