# GUI configuration snapshot files

Owner: [G01](../docs/architecture/gui.md#g01). These UTF-8 JSON files restore local
operator drafts for reusable experiments/experimenters. They are separate from
[E07 controller history](../docs/architecture/experiment.md#e07). Loading neither
submits configuration nor starts a device; normal submission/Setup retains backend
validation and revision checks. Paths reference external assets, presets, models and
firmware; files do not embed those assets or annotation image pixels.

Every format uses an exact field inventory and typed values. Unknown versions,
duplicate JSON members, nonfinite constants, incompatible identities and malformed
sections reject loading before any widget changes. Empty text/unset values remain
unset; draft structural validity does not prove runnable scientific configuration.
Save uses an atomic replacement, preserving the destination on failure. Cameras,
Protocol, Microcontroller, SpikeGLX and full GUI files are bounded to 32 MiB on read and write.
Tracking retains its 1,000,000-byte bound and owning draft migrations; Projectors
retains its existing [calibration format](gui-calibration.md) and 1 MiB limit.
File choosers are nonmodal, follow editing authority and close when authority or
the applicable diagnostic lock is lost. Full GUI loading also requires stopped
camera capture, no pending camera/MCU operation and closed projector presentation.

## Protocol

Root: `format: "cephvr-protocol-config"`, integer `version: 1`, `mode`
(`Not set`, `Open-loop`, `Closed-loop`), `asset_root` (text), `selected_trial`
(zero-based integer, or -1 for an empty schedule), and ordered `trials`.

Each trial has exactly `name`, `path` (logical source reference), `program`
(canonical nested program object), `stimulus_seed_decimal`, `gap_after_seconds`
and `arena_boundaries_json` (text; nonempty boundaries must parse). Seeds/gaps
retain draft text; E07 submission checks their experiment meaning.
Seed is config-only: set a trial's `stimulus_seed_decimal` to a canonical nonnegative
decimal integer string, for example `"42"`; `""` leaves seed selection to Setup.
The GUI exposes no Seed or Gap editor. Existing `gap_after_seconds` remains in the
file for lossless compatibility with saved schedules and retains E01/E07 validation.
Reload resets edit histories and transient epoch selection while retaining trial
selection/order. Canonical subgroup authoring metadata retains applied variation
controls and compact random seeds (including legacy cached samples) across protocol/full-GUI save/load.
An empty schedule remains empty rather than inserting an executable trial. The
toolbar also accepts canonical single-program documents into the selected trial,
retaining the loaded path; existing per-trial source APIs remain available.

## Cameras

Root: `format: "cephvr-cameras-config"`, integer `version: 1`, and ordered `cameras`.
Each camera has exactly nonempty text `serial`, known `role`, boolean `enabled` and
text-valued `values`, with the same inventory/role validation as full GUI files.
The serial set must match the current inventory; assigned roles are unique.
Load/Save requires editing authority, no pending camera operation and stopped,
disconnected cameras. Loading restores drafts without submitting settings or
opening cameras; imported PFS provenance still requires A10's SDK import.

## Microcontroller

Root: `format: "cephvr-microcontroller-config"`, integer `version: 3`, `port`,
`firmware_path` (text), `trial_state` and `projector_flip` (objects with text `pin`
and boolean `enabled`), and `camera_pins` keyed by exactly `behavioral`, `tracking`
and `eye_tracking`. Pins are wiring for logical roles, independent of camera
inventory and participation. No camera Use flags are stored or restored here;
Cameras/full GUI files own participation. Unset pins and port remain valid local drafts.

The recognized `review_inputs` and `review_outputs` extensions are shared by runtime
and Review; their historical names remain for file compatibility. Inputs is a list
of `{name: text, pin: text, enabled: boolean}` drafts. Outputs has exactly `selected`
(unique supported signal identities) and `templates` (unassigned pin text). Retain
unfinished definitions; legacy files without these fields restore empty drafts.
Input authoring does not enable A11's deferred physical input capture/diagnostics.

Version 1/2 files migrate camera-keyed pins through the current known camera-role
mapping, or the saved camera roles when embedded in a full GUI file; reject unknown
or ambiguous assignments without changing current drafts.
Validate legacy version 2 `camera_enabled` values but do not restore them. Loading
requires stopped/disconnected cameras and no pending camera operation. Restore blocks
port/toggle command signals and never uploads firmware.
Loaded pins enter the normal GUI configuration proposal; no Apply pin settings
action remains. Camera output removal clears that role's pin without changing camera
participation or timing source. Fixed signal enable flags retain their own meaning.
No arbitrary I/O definitions or new firmware behavior are encoded.

## SpikeGLX

Root: `format: "cephvr-spikeglx-config"`, integer `version: 1`, `host_reference`
and ordered `rows`. Host reference contains boolean `pairing` and text `address`
and `command_port`; it is retained context, never a startup-TOML override. A
differing reference is reported while the current endpoint remains authoritative.

Every row contains text `key`, `signal`, `stream` (`OneBox`, `NI`, `imec`), `index`,
`channel`, `bit`, `source_id`; boolean `enabled` and `custom`; and `role` (known
non-unspecified PulseRole integer or null for a derived unmapped source). Keys are
unique; noncustom pulse roles are unique; custom rows have the Custom role and a
`custom:` key. Empty numeric text remains editable. Loading replaces prior custom
rows, restores dormant values and leaves the current controller file digest/required
role inventory unchanged. Current source participation/required-role rules still
apply. Only Channel index is visible/editable alongside Use and Signal; stream family,
stream index and digital bit remain saved metadata. GUI Save/Load persists these drafts; it does not publish controller inventory
changes. There is no separate Save pulse mapping button. The E12 controller-owned
file operation retains validation of numeric channels/source IDs.

## Tracking and Projectors

Tracking uses the existing `cephvr-tracking-ui-draft` version 4 inventory and v1–3
migrations, including both pipeline drafts, method choices, preprocessing,
diagnostic switches, distance calibration, source-pixel annotations, image dimensions
and acquired-source lineage. Source mismatch invalidates spatial calibration as
required by T20/G01. Inactive loaded drafts survive local submission until Tracking
is enabled, when ordinary strict encoding/validation applies.

Projector-only Load…/Save as… keeps portable full version 11/numeric version 8,
older format migrations and calibration/profile references under
[its contract](gui-calibration.md). It does not replace physical display assignments.

## Full GUI

Root: `format: "cephvr-gui-config"`, integer `version: 1`, and exactly `experiment`,
`protocol`, `microcontroller`, `projectors`, `spikeglx`, `tracking`.
Each tab section embeds the format above; `projectors` instead wraps
`configuration` (portable projector document), `assignments` (stable display identity
→ logical face/Unassigned), and boolean `participation` for each assignment identity.
Assignments must have unique assigned faces and every assigned display must be
available in the current inventory; this rig-specific wrapper does not change
the portable projector format.

`experiment` contains:

- `dashboard`: text `subject_id`, `species`, `age`, `subject_size`, `experiment`,
  `condition`, `output_root`, and a known `sex` choice.
- `cameras`: ordered objects with nonempty unique text `serial`, known unique
  assigned `role` (or Unassigned), boolean `enabled` and text-valued `values`.
  The serial set must match the current inventory. Connection/capture state is excluded.
- `recordings`: boolean `stimulus`, `velocities`, and `cameras` (serial → boolean).

All sections are validated before restoring any of them. Camera roles/settings
remain pending local drafts; polling continues to report actual capture ownership.
Full v2 MCU camera enable flags must agree with the experiment camera flags; mismatches
reject the entire load before mutation. Accepted SDK preset baselines follow their
serial when roles change; a different
or unimported PFS path requires the existing camera SDK import before submission.
Saved `pfs_imported` text cannot establish that provenance. MCU pins and camera
settings join the same normal proposal as protocol, projection and enabled Tracking.
Force-reloading controller configuration explicitly discards pending local drafts;
stale revisions never silently rebase them. External policy, startup transport,
credentials, live statuses, device handles and process/session authority are excluded.
