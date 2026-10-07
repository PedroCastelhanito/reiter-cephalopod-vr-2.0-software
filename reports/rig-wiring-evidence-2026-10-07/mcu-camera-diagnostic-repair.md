# Camera MCU diagnostic configuration repair

Date: 2026-10-07 (Asia/Tokyo). Base revision `08d146d` plus uncommitted
counted-diagnostic and concurrent camera-viewer work. The owner's
[exact console and observation](owner-camera-mcu-console.txt) report no D10 pulses
at requested 30 Hz, repeated incomplete-evidence failures, D9 HIGH/LOW completion
and 120 D2 input edges. Generation, loaded source, timestamps, duration and
receiving-channel mapping were not supplied. This is a failed camera output test,
not a generated-count result. A read-only attempt against the previously known
controller generation failed with `UNAUTHENTICATED: operator credential missing`
([response](mcu-camera-failure-snapshot.json)); it provides no current device state.
No takeover, hardware command, reset, upload or runtime restart was performed.

Source review finds that camera `DIAG_START` requires a configured/enabled output
with the same pin and requested rate. Manual Test previously skipped CONFIGURE;
D9 and D2 have no equivalent prerequisite. The source/test-adapter reproduction
establishes that defect, but the missing live failure detail prevents claiming
that this conclusively identifies the owner's exact firmware rejection.

Under [A11](../../docs/architecture/acquisition.md#a11) and
[ARCH-002](../../architecture.md#arch-002), the existing manual-pulse owner now
configures only the selected camera role through its existing serial owner before
starting the diagnostic, within the original deadline. Failure stops the sequence
before DIAG_START. Controller completion preserves backend rejection text instead
of replacing it with incomplete-evidence wording. A retained hardcoded protocol-2
Connect check also now follows the existing parser's protocol-3 constant. Correction
to the [previous counted implementation assessment](mcu-counted-diagnostics.md):
its passing suite missed that controller version mismatch; the new explicit
version-2/version-3 regression reproduces it and verifies the repair.

The implementation adds no process, RPC, dependency, authoritative state copy or
policy choice. It reuses focused configuration/result owners and existing behavior
test modules; unrelated concurrent camera-window edits are preserved.
[Four captured repair input hashes](mcu-camera-repair-sha256.json) identify this
working-tree snapshot; concurrent edits can change shared files afterward.

| Method | Result and scope |
| --- | --- |
| Existing owning tests, targeted selection before repair | [Six failed, one passed](mcu-camera-before.xml), 36 deselected, 0.43 s. Reproduces camera configuration omission, hidden backend rejection and protocol-version completion mismatch. |
| Same selection after repair | [Seven passed](mcu-camera-after.xml), 36 deselected, 0.33 s. D9 unchanged, D10/D11 configure first, configuration rejection prevents start, backend reason preserved, only protocol 3 Connect succeeds. |
| Native local acquisition/controller/client suite | [526 passed, two symlink-privilege skips](mcu-camera-integration.xml), 7.28 s; [console](mcu-camera-integration.log). Includes concurrent viewer scenarios; isolated tests do not operate the board. |
| Ruff/check and format for the four affected files | Pass. |
| Windows-target mypy, acquisition/controller | 267 sources pass. |
| Backend boundaries / whitespace | 601 modules, zero violations; `git diff --check` passes. Existing composition/source-size advisories do not concern the focused owners extended here. |

Matching manual protocol-3 installation and runtime restart remain pending owner
authorization to interrupt current runtime/COM8 ownership. The compiled firmware
is unchanged by this repair. Verify camera-generated counts increasing during the
bounded test, retained final count after Stop, reset on the next test, D9 count one,
and LOW cleanup; retain board results in the
[single rig checklist](../rig-verification.md#managed-device-gui). Generated counts
do not measure electrical reception or camera frames.

Follow-up cleanup removes 48 verified untracked source/test bytecode cache
directories, 553 files and 10,545,258 bytes. [Inventory](mcu-camera-cleanup.json)
retains the exact targets. Shared tool caches, installed dependencies, evidence,
operator data and the running runtime remain intact; concurrent work can recreate
bytecode caches after this inventory.
