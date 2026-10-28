# renderer-sha-provider repair — 2026-10-28

- Change: `src/cephvr/platform/windows/python_entry.py` reloads `hashlib` after base DLL
  registration and refuses to run managed modules if `sha256` is not from `_hashlib`.
- Method: `hash_probe_after.py` is the owner's exact-bootstrap probe
  (`../image-pipeline-native/hash_probe.py`) with only its output name changed. Run as
  `.venv\Scripts\cephvr-renderer.exe -m cephvr.platform.windows.python_entry hash_probe_after`
  with this folder on `PYTHONPATH`.
- Outcome ([hash-probe-after.json](hash-probe-after.json)): managed default provider is
  `_hashlib`; 41,297,200-byte hashes take at most 15.8 ms and observer pauses at most 1.79 ms,
  with digests identical to explicit OpenSSL. The pre-fix result is 75–77 ms and 78.691 ms.
- Regression check: the native managed-entry test, which asserts `_hashlib`, fails with the
  previous `python_entry.py` and passes with the fix.
- Scope: an isolated two-thread probe on the rig computer. No native playback rerun; gap
  reduction is not yet shown.
