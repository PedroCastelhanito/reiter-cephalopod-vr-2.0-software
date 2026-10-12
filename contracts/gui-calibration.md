# GUI rig calibration JSON

Owner: [G01](../docs/architecture/gui.md#g01). One portable projector configuration
combines the GUI rig/calibration values, synchronization settings, screen participation
and runtime screen-profile references. Load validates the entire file before replacing
the draft; Save as writes atomically. Physical device identities, current display
inventory/refresh properties and display-to-projector assignments
are excluded. Reference measurements retain their native pixel dimensions as measurement
provenance; they do not assign an output.
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
- `version`: integer `7`.
- `values`: all numeric/boolean calibration keys below.
- `settings`: `enabled_screens` (face → boolean), `photodiode_enabled` (boolean),
  `pulse_screen` (Front/Left/Right/Bottom or null), `vsync_mode` (Selected display
  VSync / All displays VSync), `frame_rect` (output-space X/Y/Width/Height),
  `pulse_rect` (X/Y/Width/Height inside the Frame), and `blackout_zones` (ordered objects with
  face/X/Y/Width/Height, encoded as `face`, `x`, `y`, `width`, `height`). Pixels
  are integers or null in unfinished drafts, with bottom-left origins. Complete
  Pulse geometry must fit the Frame; Setup validates output bounds. Version 6
  migrates its old `pulse_rect` into Frame and `pulse_square.Size` into equal Pulse
  Width/Height. Full versions 3/4/5 retain their original standalone marker rectangle
  and omit Pulse/zone drafts. Version 7 retains numeric calibration version 4.
  Frame and Pulse use the same four table columns: Origin X, Origin Y, Width, Height;
  Pulse origins are relative to the bottom-left Frame origin.
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

Numeric-only versions 1/2/3/4 remain loadable and leave synchronization, participation
and screen-profile references untouched. Legacy runtime display profiles use the
same Load… action: adopt their reusable profile/settings, retaining current
numeric GUI values and physical assignments. Legacy full version 3 and numeric
versions 1/2 acquire unset reference fields. Full version 4/numeric version 3 migrate
their retained native dimensions into the original quarter-output pixel spans.
Save writes merged version 7; numeric snapshots use version 4. Legacy inventories
reject unknown new fields.

Keys in `values` are dot-separated field identifiers:

| Prefix | Fields |
| --- | --- |
| `rig.` | `width`, `depth`, `height`, `subject_x`, `subject_y`, `subject_z` |
| `projection.` | `near_mm`, `far_mm`, `positional_tolerance_mm`, `orthogonality_tolerance` |
| `screens.<face>.` | `width`, `height`, `distance`, `throw`, `subject_distance`, `scale_u`, `scale_v`, `offset_x`, `offset_y`, `flip_x`, `flip_y`, `reference_width_px`, `reference_height_px`, `reference_x_px`, `reference_y_px`, `reference_x_mm`, `reference_y_mm` |

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

Config-only `reference_x_px` / `reference_y_px` set the actual horizontal/vertical
bar lengths in whole native-output pixels, for example
`"screens.Front.reference_x_px": 200` and `"screens.Front.reference_y_px": 100`.
Require positive integer-valued numbers within the corresponding output dimension;
null retains the rounded 3/8-to-5/8 default span. The submitted output carries the
resolved pair in `reference_bars: {x_length_px, y_length_px}`; shared-output faces
must agree on that pair. Draw configured orange/green bars centered on integer
pixel boundaries in the native device framebuffer, independently of output correction. Measure
their full spans in mm. X/Y mm/px are measured length divided by their corresponding
pixel span; full projected image dimensions multiply those scales by output dimensions.
The measurement table accepts only paired X/Y mm inputs under one header and shows
read-only mm/px estimates, independent of throw ratio. Read-only `distance` additionally
requires positive config-only effective `throw` and is projected image width × `throw`, with Bottom using
the folded total path. Subject-to-screen distances remain independent. Old unmeasured
distances remain historical display values; no scale is inferred from them.

Both measured axes and matching native output dimensions are required when applying
measurements. The exporter multiplies existing scale_u/v by physical screen width/height
divided by full projected image width/height, preserving offsets/inversions. Submission
creates content-addressed 2×2 assets for GUI affine profiles and preserves source assets;
imported nonlinear/masked/weighted profiles require their existing calibration workflow.
This local affine approximation requires optical verification, especially distortion/depth.

Lengths are millimetres except pixel offsets/reference dimensions; scale, throw ratio and orthogonality
tolerance are dimensionless. Dimensions, distances, scales, throw ratio and projection
limits must be positive when set. Subject coordinates and pixel offsets retain
signed numeric values; backend geometry validation remains authoritative at preparation.

A file is limited to 1 MiB. Invalid format/version, duplicate members, field inventory, types or numeric
values leave existing fields untouched and report an error in the activity log.
Nulls preserve unfinished work; a successful import does not establish valid geometry
or hardware readiness. Calibration actions obey GUI editing authority, and a file
picker closes when that authority is lost. Native Save as provides overwrite consent;
QSaveFile atomically replaces the selected destination only after successful writing.

## Two-stage calibration presentation

Measure reference bars exports `calibration_view: "reference_bars"` in the protected
native display profile. Render only configured raw-pixel bars on black, ignoring
saved measurements and manual scale/offset/inversion. Close and confirm release
before launching Adjust frame and grid. That action exports
`calibration_view: "frame_grid"` (also the default for older profiles), requires
complete X/Y measurements from each assigned native mode, and applies measured
physical screen/image ratios plus manual scale/offset/inversion. Render the frame/grid
without reference bars. Both actions prepare before sending and retain V01's existing
identity, authority, deadline, Active/Closed evidence and cleanup behavior.
Neither uses projector distance or requires throw ratio for launch or mapping.
`screens.<face>.throw` remains saved in the Projectors config and supplies only the
ideal distance/optics estimate. Its value is not editable in the GUI.

## Live frame/grid adjustments

While frame/grid presentation is confirmed Active, Scale X/Y and Offset X/Y edits
update the projection without Close/Open. Other projector controls, including
measurement, geometry, inverse-axis, file and output changes, remain locked.
GUI edits debounce for 150 ms and coalesce behind one in-flight update. A partial,
nonfinite, nonpositive scale or outside-output draft sends nothing and retains the
last valid projection. Reconnect/control loss or changed diagnostic discards queued
intents; the saved draft remains available for later explicit launch.

UpdateDisplayCalibration carries the existing operator lease, configuration revision,
diagnostic ID, a strictly increasing adjustment_sequence and one to four mapping
records. Each record contains mapping_id and exactly eight destination_xy values
(four row-major normalized X/Y pairs). Coordinates form a nondegenerate rectangle
inside [0,1], retaining the original inversion. Only protected GUI diagnostic 2×2
mappings are eligible. The GL owner validates all records before writing retained
vertex buffers; UVs, viewports, assets, masks, windows and cleanup owners are unchanged.
DisplayCalibrationEvidence reports calibration_view and the applied adjustment_sequence
only after every output presents successfully. Admission is not presentation proof. A pre-write rejection keeps Active at the
previous applied sequence with CALIBRATION_ADJUSTMENT_REJECTED; it is a failed
update, not failed display ownership. Valid updates clear this rejection evidence.
Unknown/failure and Close retain V01's existing deadlines, ownership and cleanup.
Up/Down keys step scale by 0.01 and pixel offsets by 0.1, displaying two and one
decimal places respectively after a step. Stepping emits the existing user-edit
intent, including while the frame/grid is active. Invalid partial input is retained;
loading does not round saved precision.

The draft scale/offset values continue to save through the existing Projectors file.
