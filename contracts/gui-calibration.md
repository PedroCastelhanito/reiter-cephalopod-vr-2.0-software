# GUI rig calibration JSON

Owner: [G01](../docs/architecture/gui.md#g01). This is a portable local GUI draft,
not a Visual Stimulus display profile, mesh calibration or Setup-ready artifact.
Load replaces every calibration field together; Save as writes an atomic snapshot.
Discovered display/projector lists, device/output assignments, output participation,
photodiode settings and VSync mode are outside this calibration document; loading
leaves them unchanged. Screen names identify physical calibration surfaces, not
discovered devices. Subject distances retain the same JSON keys when their GUI
editors move between cards.

The root has exactly three keys:

- `format`: `"cephvr-rig-calibration"`.
- `version`: integer `2`.
- `values`: an object with all keys below, no missing or additional keys.

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
version 1 values load into version 2; saving always writes version 2. Reversal fields are JSON
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

A file is limited to 1 MiB. Invalid format/version, field inventory, types or numeric
values leave existing fields untouched and report an error in the activity log.
Nulls preserve unfinished work; a successful import does not establish valid geometry
or hardware readiness. Calibration actions obey GUI editing authority, and a file
picker closes when that authority is lost. Native Save as provides overwrite consent;
QSaveFile atomically replaces the selected destination only after successful writing.
