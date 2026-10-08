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
Save uses an atomic replacement, preserving the destination on failure. Protocol,
Microcontroller, SpikeGLX and full GUI files are bounded to 32 MiB on read and write.
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
retain draft text; E07 submission checks their experiment meaning. Reload resets
edit histories and transient epoch selection while retaining trial selection/order.
An empty schedule remains empty rather than inserting an executable trial. The
toolbar also accepts canonical single-program documents into the selected trial,
retaining the loaded path; existing per-trial source APIs remain available.

## Microcontroller

Root: `format: "cephvr-microcontroller-config"`, integer `version: 1`, `port`,
`firmware_path` (text), `trial_state` and `projector_flip` (objects with text `pin`
and boolean `enabled`), and `camera_pins` (current camera key → text pin).
The complete camera-key inventory must match; camera participation/rates belong
to Cameras. Restore blocks port/toggle command signals and never uploads firmware.
Loaded pins enter the normal GUI configuration proposal. Apply pin settings also
offers the existing explicit controller pin-save action during Configuration.

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
apply. Save pulse mapping validates numeric channels/source IDs and publishes
through the existing E12 controller-owned file operation.

## Tracking and Projectors

Tracking uses the existing `cephvr-tracking-ui-draft` version 4 inventory and v1–3
migrations, including both pipeline drafts, method choices, preprocessing,
diagnostic switches, distance calibration, source-pixel annotations, image dimensions
and acquired-source lineage. Source mismatch invalidates spatial calibration as
required by T20/G01. Inactive loaded drafts survive local submission until Tracking
is enabled, when ordinary strict encoding/validation applies.

Projector-only Load JSON/Save as keeps portable full version 4/numeric version 3,
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
Accepted SDK preset baselines follow their serial when roles change; a different
or unimported PFS path requires the existing camera SDK import before submission.
Saved `pfs_imported` text cannot establish that provenance. MCU pins and camera
settings join the same normal proposal as protocol, projection and enabled Tracking.
Force-reloading controller configuration explicitly discards pending local drafts;
stale revisions never silently rebase them. External policy, startup transport,
credentials, live statuses, device handles and process/session authority are excluded.
