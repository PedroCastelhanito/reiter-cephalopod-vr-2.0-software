# GUI rig calibration JSON

Owner: [G01](../docs/architecture/gui.md#g01). One portable projector configuration
combines the GUI rig/calibration values, synchronization settings, screen participation
and runtime screen-profile references. Load validates the entire file before replacing
the draft; Save as writes atomically. Physical display inventory, device identities,
resolution/refresh properties and display-to-projector assignments are excluded.
Loading preserves the current assignments and applies participation/pulse selection by
logical rig face, so changing the machine does not restore obsolete monitor bindings.
This is a local draft, not backend preparation or optical calibration evidence.

Machine-specific display assignments are retained separately in the existing frontend
preferences (`projectors/assignments`), as a JSON object with exactly `version: 1`
and `assignments` (stable display identity → Front/Left/Right/Bottom/Unassigned).
The value is bounded to 1 MiB; duplicate identities/assigned roles and invalid types
or versions reject the entire saved value without overwriting it. Explicit assignment
changes sync immediately; inventory/loading is read-only. Restoration follows G01's
local-draft/controller synchronization rule and does not alter this portable format.

The root has exactly five keys:

- `format`: `"cephvr-rig-calibration"` (retained for existing files).
- `version`: integer `3`.
- `values`: all numeric/boolean calibration keys below.
- `settings`: `enabled_screens` (face → boolean), `photodiode_enabled` (boolean),
  `pulse_screen` (Front/Left/Right/Bottom or null), `vsync_mode` (Selected display
  VSync / All displays VSync), and `pulse_rect` (X/Y/Width/Height, integer pixels or null).
  Rectangle origins are nonnegative; non-null dimensions are positive. Pulse-off
  preserves the other settings and permits a disabled target face. An unassigned
  physical pulse target must receive a logical projector role before saving.
- `screen_profile`: null for an unfinished draft, or the retained runtime profile
  without its physical `outputs` / `photodiode_output_id`. Surface mappings retain
  calibration references and logical `projector_role` coverage; `output_settings`
  retains requested RGB precision and color-calibration references by logical face,
  excluding identity, output ID, resolution, refresh and participation. At submission,
  bind these to the current explicit display choices/properties. Preserve shared-output
  coverage; absent required roles fail rather than guessing a display. Pacing remains
  owned by backend configuration, without a GUI editor.

Numeric-only versions 1/2 remain loadable and leave synchronization, participation
and screen-profile references untouched. Legacy runtime display profiles use the
same Load JSON action: adopt their reusable profile/settings, retaining current
numeric GUI values and physical assignments. Save always writes the merged version 3.

Keys in `values` are dot-separated field identifiers:

| Prefix | Fields |
| --- | --- |
| `rig.` | `width`, `depth`, `height`, `subject_x`, `subject_y`, `subject_z` |
| `projection.` | `near_mm`, `far_mm`, `positional_tolerance_mm`, `orthogonality_tolerance` |
| `screens.<face>.` | `width`, `height`, `distance`, `throw`, `subject_distance`, `scale_u`, `scale_v`, `offset_x`, `offset_y`, `flip_x`, `flip_y` |

Faces are exactly `Front`, `Left`, `Right`, `Bottom`. The exception to the field
list is `screens.Right.subject_distance`: it is omitted and derived as tank width +
left-screen distance − 2 × subject-to-left-wall distance, enforcing equal side-screen
offsets from the tank walls. Side and Bottom screen front edges start at the Front
screen plane, using their own in-plane lengths toward the tank back. This placement
is derived during GUI geometry conversion; it adds no stored calibration field.
Invalid/missing inputs leave derived geometry invalid.
Version 1 imports may include that field: a non-null value must agree with the
formula (1e-9 absolute/relative numeric tolerance), with all three inputs supplied.
Otherwise reject the whole document without changing current values. Compatible
version 1 values load into the current draft. Reversal fields are JSON
booleans. Other fields are finite JSON numbers or `null` for an unset draft value.
For Bottom, `distance` denotes the total optical path through the 45° mirror:
projector-to-mirror plus mirror-to-screen. The operator diagram derives the fold
beneath the retained Right projector placement; this is not a measured mirror-size
or runtime optical-correction field. Impossible diagram paths retain the draft
but show no Bottom optics when the central path is impossible. Outer-ray clearance
failure retains the valid central path and marks the ideal footprint as incomplete.

Lengths are millimetres except pixel offsets; scale, throw ratio and orthogonality
tolerance are dimensionless. Dimensions, distances, scales, throw ratio and projection
limits must be positive when set. Subject coordinates and pixel offsets retain
signed numeric values; backend geometry validation remains authoritative at preparation.

A file is limited to 1 MiB. Invalid format/version, duplicate members, field inventory, types or numeric
values leave existing fields untouched and report an error in the activity log.
Nulls preserve unfinished work; a successful import does not establish valid geometry
or hardware readiness. Calibration actions obey GUI editing authority, and a file
picker closes when that authority is lost. Native Save as provides overwrite consent;
QSaveFile atomically replaces the selected destination only after successful writing.
