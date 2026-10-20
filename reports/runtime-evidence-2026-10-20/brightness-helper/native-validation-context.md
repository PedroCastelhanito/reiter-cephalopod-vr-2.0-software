# Brightness helper validation context — 2026-10-20

Initial source revision: `226a506c6e3f7a2adb710009d9d47929cbd6b5c8`, plus shared
in-progress brightness implementation and architecture changes. This validation
agent does not edit production source/tests/contracts or control devices.

## Existing native baseline

Command (repository Python 3.11 environment):

```powershell
.venv\Scripts\python.exe -m pytest tests/platform/test_windows_native_on_rig.py::test_managed_python_entry_preserves_identity_prefix_and_bootstrap tests/platform/test_windows_native_on_rig.py::test_creation_time_containment_and_outer_job_shutdown tests/platform/test_windows_native_on_rig.py::test_exit_code_259_is_not_mistaken_for_running -vv --basetemp=.tmp/brightness-native-20261020
```

Result: **3 passed in 3.10s**, exit 0. Raw output:
`native-baseline-sandbox.log`. No elevated permission was needed.

These tests create real Windows child processes, private Jobs, inherited pipes and
temporary files. They verify creation-time containment, exact process identity,
bootstrap/runtime provenance and exit handling. They do not touch running CephVR
processes, existing application Jobs, USB devices or projector settings. They are
a mechanism baseline, not a pass for the new brightness adapter.

## Production adapter over actual native processes

Command: `.venv/Scripts/python.exe reports/runtime-evidence-2026-10-20/brightness-helper/native_adapter_probe.py`.
Final frozen-source raw log: `native-adapter-strict-final.log`; results:
`native-adapter-final-results.json`. **All three cases pass**: success, cancellation,
and timeout. Measured elapsed times and original budgets are recorded per case.
The timeout probe allows the production adapter's existing two-second cleanup
reserve; it does not extend the original three-second operation budget.

The probe replaces only `brightness_command` with a benign Python child and uses
the production `WindowsProjectorBrightness`, `SupervisedEncoderLauncher`, native
Jobs, suspended creation, pipes, reader threads and cleanup. The in-process
supervisor receipts are simulated, not authenticated RPC or a production supervisor
pass. That simulated peer independently uses real Windows handles to inspect exact
child creation identity and empty Job/process absence before its release receipt.
SDK JSON and interface identities are explicitly fake; no TI SDK or USB call runs.

The final probe asserts the brightness launch forwards `no_window=True`, then each
real child prints `GetConsoleWindow()==0`. All cases confirm released registration,
empty exact Job, absent exact child, completed local cleanup and completion before
the original deadline. Successful structured RGB evidence is parsed through the
actual production parser. Cancellation/timeout retain null results and their
explicit failure messages.

Historical pre-final-flag native results remain separately in
`native-adapter-initial-results.json` and `native-adapter-permitted.log`; they are
not the final no-console proof. An intermediate source manifest was captured in
`probe-source-initial.json`, not at the initial probe's start. Final source/probe
SHA256 hashes are in `probe-source-final.json` (HEAD plus shared dirty changes).

After the implementer froze strict JSON integer typing and authority cleanup
truthfulness, the three native and five metadata cases were rerun once, all
passing. Native launch mechanics were unchanged. Earlier no-console passes remain
in `native-adapter-pre-strict-results.json` and `native-adapter-final-pass.log`;
their source hashes are `probe-source-pre-strict.json`. The current final manifest
also includes the controller runtime authority guard.

Failed attempts remain as evidence:

- `native-adapter-sandbox.log` initially hid a prelaunch failure behind an assertion;
  `native-adapter-sandbox-detail.log` identifies private named-pipe client opening
  denied with `CreateFileW WinError 5`. Permission-enabled execution passed.
- `native-adapter-final-permitted.log` and `native-adapter-final-detail.log` show
  the benign child could not import ctypes because its Conda libffi DLL directory
  was absent from child-local lookup. The probe now adds the existing
  `sys.base_prefix/Library/bin` directory using `os.add_dll_directory` before its
  console query. No global PATH, dependency, production interpreter or SDK change
  was made. Final execution then passed. This was a Python probe setup issue;
  production brightness runs the existing PowerShell helper.

## Actual serialized Start metadata

Command: `.venv/Scripts/python.exe reports/runtime-evidence-2026-10-20/brightness-helper/metadata_output_probe.py`.
Final frozen-source raw log: `metadata-output-strict-final.log`; results and the twenty
retained output-file hashes: `metadata-output-results.json`.
**Five cases pass**: unknown/no attempt, succeeded, latest failed attempt after a
prior success, requested1500/readback1023 clamped, and two-interface partial
confirmation. These are fake device observations, not physical clamp/readback proof.

The fixture runs actual controller brightness admission and result bookkeeping,
`StartActivation.run_start`, `MetadataCoordinator`, `MetadataWriter`, Windows durable
publication, and `TrialLogs.start_trial_log`. Authority, supervisor registration,
SDK and backend identities are simulated; trial execution is suppressed. Actual
installed Tracking writer definitions build SCHEMA through `build_schema`; Start
adds its production brightness descriptor. The generated configuration names its
subject `FAKE_IDENTITY_NO_HARDWARE` and experiment `NON_SCIENTIFIC_METADATA_FIXTURE`.

For each case the fixture parses disk `SESSION_CONFIG.json`, `SCHEMA.json`, trial
LOG and SESSION_LOG. It checks current controller generation, latest admitted
command, retained failed attempt, per-interface readback/error, correct unknown
state, and the production SCHEMA descriptor. A rejected configuration revision
does not replace the admitted attempt. Nested live evidence is changed after Start
captures its document but before persistence, proving deep-copy independence;
later memory replacement cannot rewrite saved bytes. Each trial LOG references the
same saved SESSION_CONFIG and session identity.

Fixture output directories may contain `20261019` because they use the actual UTC
date while this Oct20 evidence directory uses Japan local time. All identities and
date paths are fixture provenance, not a real experiment date or session.

The first metadata attempt (`metadata-output-permitted.log`) failed a probe
expectation that omitted the newly added controller metadata descriptor. The second
(`metadata-output-final.log`) wrote valid files but its plain Python read exceeded
Windows path limits in the long fixture directory name. The final probe uses a
short unique output-root name and passes. Historical partial fixture directories
are retained; only paths enumerated by `metadata-output-results.json` are the five
successful representative cases.

The preceding five-case pass remains in `metadata-output-pre-strict-results.json`
and `metadata-output-final-short-path.log`, with its original output files retained.
`metadata-output-results.json` now enumerates only the latest frozen-source run;
`metadata-hash-check.log` verifies all twenty current file hashes against disk.

These checks do not establish physical brightness, USB release, live production
supervisor transport, application fault recovery, or full-workload acceptance.
