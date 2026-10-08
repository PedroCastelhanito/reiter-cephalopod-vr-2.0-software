# Camera settings and capability contract

Governing decisions: [A01/A10](../../docs/architecture/acquisition.md),
[E07](../../docs/architecture/experiment.md#e07),
[E14/E15](../../docs/architecture/system-contracts.md#e14).
Wire definitions: [camera.proto](../cephvr/acquisition/v1/camera.proto).
These are declarations; no loader, SDK adapter or rig compatibility is implemented.

## Values and validation

| Value | Representation and validation |
| --- | --- |
| Device | Explicit configured identifier; Setup obtains stable physical identity and checks distinct enabled roles. Never choose discovery's first camera. |
| Frame timing | External trigger or free running; required after default resolution. No unspecified fallback. |
| Exposure | Finite positive microseconds; writable setpoint and its SDK readback. Effective exposure is separate optional diagnostic evidence. |
| Gain | Integer or finite decimal matching the selected SDK node; explicit unit and applicable selector. Preserve raw/native units; never infer dB or convert with a guessed formula. |
| Free-running rate | Finite positive Hz when present. Does not control external pulse cadence; a retained value can remain unused in external mode. |
| ROI | Optional width/height/offsets while editing; positive dimensions and nonnegative offsets. Integers only; validate current SDK bounds/increments and combined extent. Zero offsets remain explicit. |
| Pixel format | Exact SDK symbol plus a supported common native-layout/consumer mapping. SDK advertisement alone cannot establish pipeline support. |
| Trigger controls | Typed selector/source/activation/exposure-mode fields. Source/input stays explicit for external triggering; do not infer wiring. |
| PFS baseline | Optional SDK-produced persistence text retained with current configuration. Apply baseline before subsequent explicit standard-field edits. No external-file reread during Setup. |
| Transport | Unique exact SDK names and original scalar types from owning TOML; only supported mappings in the correct node map/interface. |

Reject NaN/infinity, boolean-as-number, numeric-string coercion, out-of-width values,
unknown fields and malformed enum tokens. Missing values remain missing until owning
TOML/default/device resolution; protobuf zero/empty values are not implicit defaults.
Partial ROI entries resolve individually from the device, then validate the full ROI.
Device-resolvable omissions can be pending offline; required unresolved fields block
Ready. A requested read-only field may succeed if actual readback already matches;
otherwise it cannot be applied. Unavailable fields are not silently skipped.

Capabilities describe the currently applied settings and connected camera. Include
access and SDK ranges/increments/choices; absent bounds are unknown, not zero.
Unavailable features have no invented range. Floating increments may be absent;
never manufacture a rounding step. Refresh after dependent changes, including ROI,
pixel format, exposure mode and selectors. An SDK failure is not optional absence.

Trigger selector/activation/exposure-mode options use the existing readable canonical
names (`frame_start`, `rising_edge`, `timed`). The adapter supplies an explicit mapping
to SDK symbols for exposed choices; ambiguous/unmapped choices fail. Source/input,
pixel format and gain-selector values preserve SDK spelling. This is a mapping of
known typed controls, not permission for arbitrary node commands/register writes.

Only reliable limits applicable to external triggering populate `maximum_hz`.
When unavailable, leave it absent and explain why. Setup compares any known bound
with the **applied** MCU rate. Unknown warns and continues under A10; confirmed
incompatibility/device errors fail. No software frame rate or exposure-only estimate
is promoted to a verified maximum. No new runtime frame-rate threshold is introduced.

Independently check the final payload bytes per frame times the applied pulse rate
against any enabled, applicable device-link byte/s limit. Use confirmed node units
and payload semantics; exceeding the limit is a known incompatibility under A10,
not an unknown-maximum warning. Passing this necessary budget check does not prove
sufficient overhead/headroom, sensor timing or host/USB throughput. Re-evaluate after
ROI, pixel format, chunk or transport changes; never use recording-filter dimensions
to budget camera transport. Report the camera, payload, rate and limiting readback.

For Basler, inspect the applicable `BslResultingAcquisitionFrameRate`,
`ResultingFrameRate` or legacy `ResultingFrameRateAbs` with the final settings.
Use it as a trigger limit only where the model/mode semantics establish that use;
retain it as an SDK estimate, not measured FPS. `AcquisitionFrameRate` and its node
maximum are not interchangeable with this result. See Basler's
[resulting-rate documentation](https://docs.baslerweb.com/resulting-acquisition-frame-rate).

## Applying and adopting settings

1. Validate source authority, device assignment, configuration revision and lifecycle.
   Serialize SDK access; coordinate existing preview stop/apply/restart rules.
2. Open only the assigned camera. For a retained baseline, use SDK PFS loading with
   validation; explicit PFS Import instead establishes the imported common values.
   Pending typed edits then apply according to the accepted workflow.
3. Apply dependent controls while capture is stopped. Resolve advanced baseline
   features before standard controls that depend on them. Disable supported auto
   exposure/gain and verify manual operation. Read-only/manual-by-design devices do
   not require writing a nonexistent auto-control node.
4. Re-query bounds as needed, apply the final combination, and read back settings,
   capabilities, transport, optional native metadata availability and image layout.
   Do not reapply unconditionally when an unchanged value already matches.
5. Return `CameraResolvedState` for the request revision. The controller alone adopts
   actual values and the refreshed SDK-produced snapshot; stale results cannot replace a
   newer configuration. Required consumers validate that resolved layout/settings.
6. Allocate/attach buffers only after the final controller-confirmed revision under
   A03. Session locking remains authoritative. A failed/partial application leaves
   capture/pulses stopped and reports diagnostic readback, never successful resolution.

The device result is not Ready or permission to start capture. Native metadata may
be absent with a warning; required host receipt timing and image layout cannot be.
Subsequent trial preparation rechecks A10's capture-critical settings without repair
or adoption of drift in a locked session.

## Basler mapping and evidence

Resolve only applicable, readable/writable nodes; prefer the modern node when present,
otherwise use the documented legacy equivalent. Multiple unrelated nodes are not
interchangeable aliases. Record the selected mapping in capability/diagnostic context.

| Typed control | SDK mapping / handling |
| --- | --- |
| `exposure_us` | `ExposureTime`, or applicable legacy `ExposureTimeAbs`, in microseconds. `BslEffectiveExposureTime` is separate read-only evidence; never write it back as the requested setpoint. |
| `gain` | `Gain` or applicable `GainRaw`; use the actual node type/unit and `GainSelector` if supported. Native raw gain is not automatically dB. |
| `frame_rate_hz` | `AcquisitionFrameRate` or applicable legacy `AcquisitionFrameRateAbs`; handle `AcquisitionFrameRateEnable` when required for an explicit free-running rate. Never use this to set MCU cadence. |
| ROI | `Width`, `Height`, `OffsetX`, `OffsetY`; query dependent constraints. If centering owns offsets, resolve that dependency before applying explicit offsets; report actual adjustments. |
| Pixel format | `PixelFormat`; require the selected native layout/conversion registry entry. |
| Trigger | `TriggerSelector`, `TriggerSource`, `TriggerActivation`, `ExposureMode`; manage `TriggerMode` consistently with frame timing. Preserve validated PFS features unless they conflict with mandatory capture policies. |
| Manual exposure/gain | `ExposureAuto=Off`, `GainAuto=Off` when supported; verify the resulting manual mode. |
| PFS | SDK feature persistence load/save with validation; snapshot current persistable features, not all physical device state. |

ROI coordinates follow the camera's current image coordinate system, including
binning/decimation; do not label them unconditionally as physical sensor pixels.
ROI is distinct from auto-function ROI. Dependency-aware writes may use temporary
valid ROI values with capture stopped; only the final readback is adopted. Do not
hard-code model limits or silently restore a failed application.

Source references (documentation, not rig verification):
[Exposure](https://docs.baslerweb.com/exposure-time),
[Gain](https://docs.baslerweb.com/gain),
[Image ROI](https://docs.baslerweb.com/image-roi),
[Frame rate](https://docs.baslerweb.com/acquisition-frame-rate),
[Triggering](https://docs.baslerweb.com/triggered-image-acquisition),
[PFS persistence](https://docs.baslerweb.com/pylonapi/cpp/class_pylon_1_1_c_feature_persistence).
Specific node availability, native metadata semantics and format mappings must still
be verified for supported models/SDKs; this table is not blanket device support.

## Retained PFS application binding

The adapter's `apply_pfs_snapshot(snapshot)` applies the already retained SDK text
through pylon FeaturePersistence.LoadFromString(snapshot.text, camera.GetNodeMap(),
True), with SDK validation explicitly enabled. Require the assigned camera open and
capture/pulses stopped; keep serialized access in the existing camera owner. Apply
the baseline before explicit typed edits under the resolution order above. After
successful application return actual SettingsReadback, then refresh the retained
snapshot only after all authorized edits/readback succeed. Do not reread the original
PFS path, write a temporary PFS, parse/reimplement GenApi feature persistence or use
a separate worker. SDK LoadFromString binding availability is a compatibility check;
absence fails this requested operation explicitly rather than silently skipping it.

A load can partially apply before raising. Keep capture stopped, preserve the error
and any available diagnostic readback; no automatic rollback or adoption as successful
Setup. The owner performs normal failed-operation cleanup. This binds the existing
retained-baseline policy and adds no new PFS import/export workflow or operator choice.

## Serialization boundaries

Camera settings/PFS baseline are configuration data, not frame data. Snapshot text
travels only through authorized configuration/readback and reusable-history paths;
session/trial JSON excludes it and records only external preset filenames alongside
ordinary active-camera settings. No new session PFS file, hash or per-frame metadata.

SDK-produced baseline, applied readback and capabilities are backend-owned fields.
An operator edit may carry unchanged baseline data from the current configuration
but may not replace it to bypass the connected-camera Import contract. Controller
adoption binds backend results to the outstanding command/revision. GUI and headless
clients receive the same state; exact GUI controls remain a later design decision.

See the [single acquisition worklist](README.md#remaining-decisions-and-implementation-work)
for contract gaps, hardware inputs, later implementation and explicit rig deferrals.
The declarations above are not runtime or rig validation.
