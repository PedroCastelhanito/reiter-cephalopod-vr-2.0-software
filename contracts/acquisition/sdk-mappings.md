# Basler format, transport and error mappings

Derived from [A01/A09/A10](../../docs/architecture/acquisition.md) and
[pixel processing](pixel-processing.md). These are implementation bindings, not
verified camera support. Exact devices, SDK/runtime versions and rig evidence remain
pending. No additional camera process or alternate conversion provider is introduced.

## Native format registry

Match the exact pylon `EPixelType` value reported by the grab result, using an
explicit registry. Device `PixelFormat` node symbols and pylon enum names are separate
identifiers; compare through the SDK mapping, never by case folding or suffix guesses.
The following notation expands into concrete entries for each listed depth/pattern.
Only symbols present in the chosen pypylon build can be enabled.

| pylon names (all prefixed `PixelType_`) | Native interpretation | Consumer preparation |
| --- | --- | --- |
| `Mono8` | One unsigned byte/pixel, 8 effective bits | `Mono8` or direct suitable private view |
| `Mono10`, `Mono12`, `Mono16` | One unsigned little-endian 16-bit container/pixel; effective depth 10/12/16 | `Mono16`, retain source depth with prepared MSB alignment |
| `Mono10packed`, `Mono12packed` | Exact legacy SDK packing; not PFNC `p` packing | SDK unpack to `Mono16` |
| `Mono10p`, `Mono12p` | Exact PFNC packing; 10/12 effective bits | SDK unpack to `Mono16` |
| `Bayer{GR,RG,GB,BG}{8,10,12,16}` | Mosaic phase from exact enum; 8-bit byte or unsigned little-endian 16-bit container | SDK reconstruct `RGB8packed` for 8 bits, `RGB16packed` otherwise |
| `Bayer{GR,RG,GB,BG}12Packed` | Exact legacy packed Bayer; capital `Packed` in these enum names | SDK reconstruct `RGB16packed` |
| `Bayer{GR,RG,GB,BG}{10p,12p}` | Exact PFNC packed Bayer with explicit phase/depth | SDK reconstruct `RGB16packed` |
| `{RGB,BGR}8packed` | Interleaved byte channels in the named order | `RGB8packed`, avoiding conversion when already suitable |
| `{RGB,BGR}{10,12,16}packed` | Interleaved little-endian 16-bit channel containers, 10/12/16 effective bits; `packed` here does not mean mono bit packing | `RGB16packed`, only where SDK advertises that exact source and conversion |

No suffix-based catch-all. Other pixel types need an explicit entry before Setup can
accept them. Do not infer support for alpha, YUV, compressed, multipart, depth/range,
signed or planar inputs from this table. The registry covers the accepted broad mono,
color, Bayer and packed-depth scope without pretending to support every SDK type.

`NativePixelFormat` holds SDK enum name/value, effective bits, channel/Bayer layout,
packing identifier, byte order and sample alignment. Prepared `PixelLayout` holds
width, height, row stride and image bytes. Compute packed minimum row/image sizes
using pylon's pixel-type helpers, then validate against actual result stride/padding
and payload bounds. Never derive legacy packing as `ceil(width * effective_bits/8)`.
Require a single top-down image plane. Exclude metadata chunks and trailing payload
material; copying native row padding does not permit reading past the SDK image.
Bind the complete layout at Setup and reject runtime layout drift before publication.
Native alignment is resolved from the exact SDK format mapping, not copied from
consumer output settings or inferred from pixel values. Retaining source-format depth does not assert additional sensor/ADC precision;
hardware-specific facts remain unknown until supplied. Preparation requires a known
format interpretation/range, not guessed sensor precision.

## Private conversion binding

Wrap each consumer's private native memory in a pylon image carrying the exact pixel
type, dimensions, padding and top-down orientation, using the supported pypylon
`PylonImage` buffer attachment binding. Retain its Python buffer owner through conversion;
release the wrapper before reusing that memory. Convert into a reusable private
`PylonImage` via `ImageFormatConverter.Convert(destination, source)`. No grab result,
camera object or mutable converter is passed across processes. Verify binding/ABI
support when choosing the runtime; absence is an explicit compatibility failure.

For source-depth preparation set output to Mono8/RGB8packed or Mono16/RGB16packed,
with explicit MSB alignment for wider containers, zero extra output padding and
top-down output. Descriptor retains the original effective depth, so a 12-bit
sample in 16-bit storage is not reported as a 16-bit measurement. Set MonoConversionMethod=Truncate, Gamma=1 and AdditionalLeftShift=0; never route high-depth preparation through 8 bits.
For Bayer edge reconstruction use the SDK's `Extend` mode, preserving geometry by
extrapolating neighboring image data. Reject dimensions the SDK cannot convert;
never silently clip the image or insert a zero border. This remains reconstruction,
not a bit-identical raw image. This fixed implementation rule adds no operator knob.

Preview's fixed full-source-range mapping is a separate final step under A10; tracking
retains the same precision and declares RGB/grayscale need under T01. A no-conversion
private view is permitted only when channel order, packing, byte order, stride,
dimensions, effective depth, numeric range and alignment all match the prepared
consumer descriptor. For example, an LSB-aligned 12-bit native Mono16 container
cannot be passed directly as prepared MSB Mono16 merely because both use uint16.
The [alignment binding](pixel-processing.md#prepared-alignment-and-preview-scaling)
owns interpretation and preview arithmetic. FFmpeg mappings for prepared
8-bit mono/RGB are `gray`/`rgb24`; 16-bit containers use `gray16le`/`rgb48le` (or an
explicit lossless layout rearrangement if the packaging API needs planar RGB).
Validate significant-bit alignment end to end. Container width does not waive output
effective-depth checks. No format choice proves NVENC compatibility.

## Transport and metadata bindings

Apply explicit transport settings with capture stopped, before final layout/readback.
For GigE, packet size precedes inter-packet/frame transmission delay; for USB, transfer
size precedes queued transfers. Requery dependent limits after each write, adopt
actual readback under A10 and fail unsupported explicit settings. Omitted settings
remain SDK defaults. No arbitrary node search or device-register API.

| Exact key | Node map / interface | Type and units |
| --- | --- | --- |
| `DeviceLinkThroughputLimitMode` | Camera / USB3 or GigE when exposed | Exact enum symbol `On` or `Off`; require advertised availability |
| `DeviceLinkThroughputLimit` | Camera / USB3 or GigE when exposed | Integer bytes/s; require confirmed SDK units/semantics and current range/increment |
| `MaxTransferSize` | Stream grabber / USB3 | Integer bytes |
| `NumMaxQueuedUrbs` | Stream grabber / USB3 | Integer transfer count |
| `GevSCPSPacketSize` | Camera / GigE | Integer bytes |
| `GevSCPD` | Camera / GigE | Integer device timestamp ticks, using that device's documented clock |
| `GevSCFTD` | Camera / GigE | Integer device timestamp ticks |
| `PacketTimeout` | Stream grabber / GigE | Integer milliseconds |
| `FrameRetention` | Stream grabber / GigE | Integer milliseconds |
| `EnableResend` | Stream grabber / GigE | Boolean |

Require each mapped node's actual availability/access/type/range/increment. No assigned
rig values or global override defaults. SDK buffer count remains its separate typed
camera setting; reject it in the transport table.

Resolve device-link mode/limit dependencies with capture stopped and re-query access
after a mode change. Apply only explicitly configured overrides; omitted values keep
the applicable device/PFS baseline. Read back both effective mode and limit after
all settings, even without overrides, for the
[camera transport budget check](camera-settings.md#values-and-validation). Disabling
the limiter or raising its value is never an automatic response to an insufficient
budget. Node availability alone does not validate sustained bandwidth.

Map summary fields respectively to stream-grabber `Statistic_Buffer_Underrun_Count`,
`Statistic_Failed_Buffer_Count`, `Statistic_Missed_Frame_Count`,
`Statistic_Resend_Request_Count`, `Statistic_Resend_Packet_Count`, and
`Statistic_Resynchronization_Count`. Only read supported nodes with matching semantics;
USB/GigE/model differences may leave fields unavailable. Take baseline after grab
initialization (which may reset counters), final before deinitialization, serialized
with SDK access. If reset continuity cannot be established, report unavailable.
The summary binding below owns aggregation and delivery; these counters never replace
source IDs.

Prefer documented image-associated timestamp/frame-counter chunk values; use native
grab metadata only when its meaning/units are established. Request supported chunks
at Setup without replacing already useful native metadata. Chunk selector names,
clock frequency and counter sentinel/reset behavior come from the connected model's
SDK. Convert timestamp ticks by exact rational arithmetic, nearest integer ns;
unknown clock units leave the optional timestamp invalid. Do not use a host clock
substitute or assume every GigE/USB model shares clock/counter semantics. Bind the
source node/unit/counter epoch in adapter state, avoiding duplicate per-frame metadata.
Transfer timestamp provenance through the prepared [camera-clock descriptor](camera-clock.md);
recording never rediscovers it independently or assumes a host-aligned clock.

## Transport summary binding

A07's compact summary (code `TRANSPORT_SUMMARY`, no frame reference) is written to the
completion line's `transport_summary` object. Read a baseline around capture start and a
final snapshot after stopping capture but before sealing the end marker; bind
both to the exact camera/capture run. Read outside the per-frame path under existing
operation deadlines. The adapter must account for SDK counter-reset semantics;
only subtract comparable observations from the same counter epoch. Unknown/reset/
wrapped values are unavailable, never assumed zero or repaired by guessed wrap math.
This is a capture-run diagnostic interval, not exact exposure/trial membership proof.

Use these fields: `buffer_underruns`, `failed_buffers`, `missed_frames`,
`resend_requests`, `resend_packets`, `resynchronizations`. Values are nonnegative
integer changes or `null` when unavailable. Map only supported SDK counters with
matching meanings; none is a substitute for CephVR received IDs or recording-drop frame
lines, and overlapping counters must not be summed into a total lost-frame count. Zero
is valid only after successful comparison. The summary's observation time is the host
time when it is formed.

Read failures/unsupported counters may yield a partial or wholly unavailable summary
without blocking recording or extending stop/closure deadlines. If the camera worker
fails before producing it, absence means unknown, not zero. The capture thread hands
any available summary to the recording thread before the end marker; the recording
thread writes it in the completion line. No polling history, extra file or
counter is needed. Optional SDK evidence does not waive required storage or
device-error handling. With saving off, create no diagnostic file.

The camera worker reuses the same resolved summary values in `WorkerFinishedEvidence`;
the coordinator validates camera/trial identity and forwards them in the acquisition
`FinishedReport`. Expose that completed report through the existing participant
status/GetState/GetSnapshot/WatchState path. No new polling endpoint, scientific
history or duplicated status field is needed. GUI rendering/which controls it exposes
remain later design work; both GUI and headless clients can access the typed summary.

Keep at most one latest completed summary per camera, with the Finished report's
original trial/process context. Retain it across subsequent preparation/running until
replaced by a newer completed report; never label it current-trial/live data or use it
as fresh readiness evidence. Clear at fresh Setup/process generation change. If the
new report lacks a summary, show unavailable for that trial rather than carrying an
older value forward. A report present with absent counter fields means those counters
are unknown; numeric zero is a measured zero. No extra SDK reads or fabricated summary
are required when recording is off or evidence is unavailable. Closure/output evidence
remains separate: a diagnostic summary never proves the file saved successfully.

## Capture call scheduling

Use Basler OneByOne with the worker-owned retrieve loop. StartGrabbing arms external
capture with pulses off; free-running starts only at T. StopGrabbing and release/drain
stale SDK results before fresh arming, retaining the camera connection. Never purge
already admitted trial frames. Set MaxNumBuffer before grabbing from resolved camera
settings, then verify readback. No SDK-owned callback grabbing loop.

Use the [capture-wait contract](capture-wait.md): jointly wait for the SDK grab-result
object, command event and nearest deadline, then retrieve nonblocking and recheck
commands between results. There is no fixed 1 ms polling cap. Check admission cutoff
again immediately after stamping receipt; late results never enter a sealed trial.
The selected binding must support the combined wait and GIL release. A stuck native
call retains E06's failure path; API support alone does not prove timely wakeup.

Stable diagnostic codes and warning aggregation are bound in
[diagnostics](diagnostics.md); SDK error details never replace the CephVR category.

## Adapter result and exception handling

| SDK outcome | Adapter result / stable error |
| --- | --- |
| Bounded `RetrieveResult` timeout with return-on-timeout | `None`; worker applies frame-health/lifecycle policy. |
| Result exists but `GrabSucceeded()` is false or payload invalid | Invalid `GrabResult`, original SDK code/detail; worker still assigns receipt ID/time and accounts a dropped frame line. Release once. |
| Exact device absent/removed/not open | `DEVICE_UNAVAILABLE`; no substitution/reconnect during trial. |
| Missing mapped feature or invalid setting/type/range | `UNSUPPORTED_FEATURE` / `INVALID_SETTING`, field path and SDK cause. |
| GenApi access/logical failure | `SDK_ACCESS` / `SDK_STATE`; failed operation with available diagnostic readback. |
| Other SDK timeout or transport/runtime failure | `SDK_TIMEOUT` / `SDK_FAILURE`; no generic retry. |
| Allocation failure or inconsistent required layout | `RESOURCE_EXHAUSTED` / `INVALID_LAYOUT`; fail preparation or interrupt active use. |

Classify using exception type/error code and operation context, never message-string
matching. Unknown exceptions become SDK_FAILURE rather than success/invalid-image
continuation. Optional metadata/counter read unavailability is a warning only when
no device failure is established. Host deadlines, user prompts, logging and lifecycle
remain outside the adapter. Release SDK buffers exactly once on every path.

Primary references: [pylon pixel types](https://docs.baslerweb.com/pylonapi/cpp/group___pylon___image_handling_support),
[converter](https://docs.baslerweb.com/pylonapi/cpp/class_pylon_1_1_c_image_format_converter),
[converter controls](https://docs.baslerweb.com/pylonapi/cpp/namespace_basler___image_format_converter_params),
[pypylon binding](https://github.com/basler/pypylon/blob/master/src/pylon/ImageFormatConverter.i),
[stream parameters](https://docs.baslerweb.com/stream-grabber-parameters),
[GigE network parameters](https://docs.baslerweb.com/network-related-parameters).
