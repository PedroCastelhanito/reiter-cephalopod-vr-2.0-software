# Camera-native clock provenance

[A07/A09/A10](../../docs/architecture/acquisition.md) and
[SYS-004](../../architecture.md#sys-004) govern optional camera timestamps.
This contract declares preparation, transfer and storage; actual camera units and
SDK compatibility remain hardware evidence, not assigned defaults.

## Prepared descriptor

The camera adapter builds one CameraClockDescriptor while capture is stopped, after
settings/PFS application and native metadata selection. NativeMetadataSupport returns
it; CameraResolvedState carries it through controller adoption. Acquisition forwards
the same validated descriptor in CameraWorkerSetupPayload, bound by its existing
device/process/configuration context; the recording thread uses that descriptor. No
independent SDK query, model table, clock service or per-frame descriptor is added.

| Field | Required interpretation |
| --- | --- |
| device_id | Exact confirmed stable physical device identity used by recording metadata. |
| timestamp_source | Exact selected SDK source, e.g. a documented chunk node or grab-result member; `unavailable` if none can be established. Never silently switch sources mid-run. |
| conversion_available | Explicit boolean: source and rational units are known well enough to convert. Missing is invalid protocol data; false is an allowed optional capability. |
| tick_period_ns_numerator / denominator | Positive uint64 integers in reduced form when available; nanoseconds per native tick. Both absent when unavailable, never default 1 ns/tick. |
| timestamp_semantics | Documented event measured by this source, or `unknown`; do not infer exposure start from a generic timestamp name. |
| reset_semantics / wrap_semantics | Concise documented device behavior, or `unknown`; never claim continuous origin across resets/reconnections from a descriptor match alone. |
| unavailable_reason | Concise reason when conversion unavailable; empty when available. |
| counter_source / counter_semantics | Exact SDK frame-counter source (or `unavailable`) and whether it counts delivered frames or received triggers (`frames`, `triggers`, `unknown`). Needed to tell missed triggers from dropped frames against SpikeGLX pulses. |
| counter_width_bits / counter_wrap_semantics / counter_unavailable_reason | Documented bit width (0 = unknown), wrap/reset behavior or `unknown`, and a reason when unavailable. Stored in the A07 frame-log header; never guessed. |

Use exact SDK unit/readback evidence. A frequency f ticks/s yields the reduced ratio
1,000,000,000/f ns/tick; a documented already-nanosecond source yields 1/1. These are
conversion examples, not defaults for any model. Strings have a 1,024-byte UTF-8 bound,
no NULs and no silent truncation of provenance. Source and device identity must fit
without loss. Source-specific validity/sentinel rules remain adapter-owned; zero
can be a valid native timestamp and cannot globally mean unavailable.

Validate known source/units against the connected configuration during preparation.
An explicitly unavailable descriptor still permits Ready and valid images under A07.
A malformed/mismatched descriptor is a contract error, distinct from unknown optional
hardware facts. Conversion availability must agree with native_timestamp_available;
per-frame absence still uses existing validity flags. Unknown event/reset/wrap meaning
can remain `unknown` without inventing calibration or rejecting useful raw-clock times.

## Runtime interpretation and changes

Convert each available nonnegative native tick value t using integer arithmetic:
`ns = (t * numerator + denominator // 2) // denominator`, rounding nearest with ties
up. Use wide/arbitrary-precision intermediate arithmetic; require the resulting value
to fit the existing signed int64 camera_timestamp_ns field. Invalid/missing samples
or unrepresentable conversion become unavailable optional timestamps and the existing
warning path; do not discard otherwise valid pixels. Host receipt remains mandatory.

Preserve the native origin. Do not subtract the first timestamp, unwrap to a synthetic
continuous epoch, apply a host offset or save duplicate raw ticks. Documented resets/
wraps therefore need not produce increasing camera timestamps; they do not invoke
A05's host-clock regression failure. Do not infer event timing or continuity beyond
known semantics. Hardware pulses remain scientific alignment authority.

Before each trial, the camera owner confirms the selected source/unit interpretation
still agrees with retained Setup wherever readable; this is a device capability check,
not an output-file scan. Do not reconfigure/reset the camera clock merely to check it.
If the optional source/units become uncertain or differ, do not apply the old ratio
to new data: mark those optional timestamps unavailable and warn until fresh Setup.
The recording thread retains the original descriptor as provenance for values
actually converted under it. A confirmed device failure still follows E06. A detected
change never silently rewrites an in-use descriptor or an existing frame-log header.

## Frame-log header binding

At trial-file creation, write the descriptor once into the frame-log header's `clocks`,
using the fields in [frame_log_schema.toml](frame_log_schema.toml). `camera_clock` is
the domain label `cephvr.camera.native.v1`; it does not identify a shared epoch across
cameras or trials. The identity's `device_id` identifies the device. `timestamp_source`
maps to `camera_clock_source`; ratio numerator/denominator map to
`camera_clock_tick_ns_*`. The other descriptor fields use the matching
`camera_clock_`-prefixed names. Ratios are JSON integers and availability a JSON
boolean. When unavailable, the ratio fields are `null` and readers use the reason. No
zero denominator is ever evaluated. Frame-line fields and their null-when-unavailable
rule stay unchanged.

`timestamp_unit=ns` describes converted stored numbers, not physical timing accuracy
or synchronization with host/GPU/another camera. Required `host_clock` remains the
separate shared host-clock label. Missing/invalid provenance is never replaced with
guessed model defaults. This adds no periodic provenance logging or runtime
file-content validation.

Reference: [Basler timestamp documentation](https://docs.baslerweb.com/timestamp).
