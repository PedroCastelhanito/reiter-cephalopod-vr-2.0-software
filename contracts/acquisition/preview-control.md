# Preview capture and viewer attachment

Derived from [A02/A03/A09/A10](../../docs/architecture/acquisition.md),
[E03](../../docs/architecture/gui.md) and [E06/E08](../../docs/architecture/system-contracts.md).
[Configuration control](configuration-control.md) owns operator authorization;
[frame buffers](frame-buffers.md) owns native layout and handle/release rules.
These are interface declarations, not a running preview implementation.

## Manual configuration handoff

Manual camera and MCU commands carry the complete controller-accepted acquisition
settings with their exact configuration revision. The coordinator installs newer
drafts before dispatch, rejecting stale/missing payloads and changes while camera
or diagnostic ownership is active. This does not apply settings to hardware or
replace SDK/MCU readback and controller adoption. Release/attachment of existing
session work does not install a new draft. PFS imports carry the assigned requested
device into the worker, so the first import can open that device before SDK import.
The GUI completes its import editing operation with Finish Editing.

## Connection-only diagnostic

`ExecuteCameraCommand(TEST_CONNECTION)` is a Configuration/control-holder command
with the current configuration revision and assigned camera role, and no path,
preview run or consumer. Acquisition forwards one retained `WorkerEditCamera`
`TEST_CONNECTION` child under the original deadline. The worker checks the exact
serial and closes only a device it opened. No settings/PFS or capture operation is
performed. Active preview is rejected; the GUI skips that camera without stopping it.
A successful matched completion requires confirmed device ownership/cleanup state;
failure retains cleanup as unknown until Finish Editing or owner cleanup confirms it.
No frame, trigger or recording readiness is inferred.

## Capture owns the slot

Prepare one capacity-1 PREVIEW slot for each explicitly started manual preview in
Configuration, regardless of GUI presence. It retains the latest valid frame and
creates no files. An absent viewer does not stop that preview's capture or pulses;
preparing the slot alone does not start acquisition.

Session Setup first stops/releases manual preview; a manual preview allocation is
never converted into a session allocation. When `[preview] session_preview_max_hz`
is positive (default 10; 0 = off), Setup allocates one session-scoped PREVIEW slot per
enabled camera and reports a session preview_run_id for it. The capture thread copies
the newest valid in-trial frame into it at most at that rate; capture runs only during
trials, so nothing is published between trials. Session preview never gates capture,
pulses, recording, tracking, Ready or trial start, and a viewer is never required.
The slot is released at session cleanup, not when a viewer closes.

The coordinator allocates a fresh manual-preview run UUID for each actual capture
start or configuration restart, not for viewer attachment. Equivalent already-running
Start returns existing state. Stop retires that run; a delayed command cannot revive
it. The slot descriptor has no fixed consumer; its transfer ledger binds each authorized
viewer to an exact process generation. At most one viewer may be attached at a time.

## Start capture

1. Controller authorizes Start Preview without a viewer identity. Coordinator resolves
   camera/pulse settings and obtains controller adoption under the existing workflow.
2. Allocate the slot after confirmed native layout. WorkerPreparePreview supplies the
   full camera payload and slot attachment, even headlessly; no session/trial work or
   recording accounting. Camera attaches/prepares and returns matching Ready.
3. Publish preview_prepared and run identity. When camera/control/device gates pass,
   send WorkerStartPreview for that preparation. Do not wait for GUI attachment.
   Worker starts free-running capture or confirms external arming; coordinator then
   sends MCU ON. Never wait for an externally triggered frame before enabling pulses.
4. Report preview_running only after usable-frame and applicable pulse-state evidence.
   Existing capture-health/preparation deadlines apply without stage-based renewal.

Worker reports bind the originating operation to the retained run. Manual preview
has no trial number, trial T, trial files or trial marker. The producer overwrites the
slot under A03's seqlock and never waits for a viewer. GUI rendering speed does not
change capture rate.

## Attach or close a viewer

Use the existing ExecuteCameraCommand path with ATTACH_PREVIEW_VIEWER, current manual or
session preview_run_id and exact registered preview_consumer. This is a separate
operator command, never a camera Start/Stop or settings change. Controller validates current
run, control authority and client-to-viewer identity. No arbitrary PID or
second SDK owner is permitted. Refuse a different viewer while prior attachment or
release is unresolved; attaching the same live viewer is idempotent.

Coordinator publishes the memory and event names only for the requested attachment,
registers the transfer obligation and sends ReportPreviewAttachment to the controller's
private cache. Viewer obtains that existing transfer through GetPreviewAttachment,
validates/attaches memory and event, allocates private image storage, and
reports ATTACHED. That completes the attach command, not a capture-start gate.
Queries/retries never create another transfer; public snapshots contain no names.

Viewer waits (with a timeout) on the slot's A03 named event, outside the
GUI event/render thread. Check `published_count` against the last handled frame; a
notification alone is not a frame. On attachment, inspect the current slot
before waiting so an already-published image is not missed. Publication and stop/detach
wake the reader; waits always recheck new-frame and cancellation predicates.

There is no viewer-side FPS cap or periodic frame polling. Read the newest available
frame with A03's copy-then-recheck rule before conversion/rendering; a torn read is
skipped. Coalesce GUI dispatch to at most one pending update indication, carrying no image
backlog. While rendering is busy, newer frames replace the waiting slot; after that
work completes, select the newest frame rather than displaying queued older images.
Check for a newer frame before sleeping again. Never queue one GUI callback per camera
frame or spin on an unchanged slot. Rendering and monitor refresh can still
limit what is actually displayed; uncapped delivery is not lossless screen presentation.

Closing the image view stops
local reads, finishes its private copy, closes its mapping/event and reports
RELEASED. The coordinator retains the slot and producer; capture continues. A later
explicit Attach may transfer to the same or another registered viewer.
A released transfer is never reconstructed or closed twice. No per-frame RPC, extra
server, process or frame queue is introduced.

Closing the view is different from Stop Preview and from closing/disconnecting the
controlling client. E03/A10 promptly stops preview and releases its resources on
control loss, without a grace timer; an active experiment remains headless-capable.
Viewer attachment does not grant or renew control ownership.

## Image conversion for display

[Pixel processing](pixel-processing.md) defines the shared methods and branch boundaries.
Use Basler's image converter through the common native-image conversion module
inside the preview consumer, after copying/releasing the shared slot. Keep the
converter consumer-owned and serialize its use. It processes the private image
copy only; do not open a camera, change device settings or move conversion into
the acquisition grab loop. Display color and Bayer images as ordinary RGB;
Bayer reconstruction uses the confirmed format's pattern. Monochrome remains grayscale.
Native frames, recording conversion arguments and tracking inputs are unchanged.

Use configurable `preview.output_bit_depth` from acquisition settings, default 8 bits
per channel. Validate a positive integer and support in the common converter and
viewer image path before use; unsupported requests report the requested depth and
reason through existing preview failure handling, without silent fallback.

Map the native format's full valid intensity range linearly to the configured output
range, using the same mapping for every frame. For unsigned N-bit source and M-bit
preview samples, map 0 to 0 and (2^N - 1) to (2^M - 1) with nearest-integer rounding.
For example, 12-bit 0..4095 maps to 0..255 when M=8. A wider storage container does
not change effective output depth; upscaling cannot add source precision. The GUI
must interpret the declared range/alignment through the
[shared alignment/scaling binding](pixel-processing.md#prepared-alignment-and-preview-scaling).
For example, prepared MSB 12-bit 32768 in uint16 represents source value 2048,
which maps to 128 for an 8-bit preview. Fuse interpretation/scaling where practical;
no mandatory intermediate LSB image or additional process is required. This image setting does not
guarantee the physical monitor displays that many bits. Supported end-to-end depths
remain to be verified. Use effective sample bit depth after unpacking, not a 16-bit
storage container or the current image's observed min/max. Scale color channels consistently; no
per-frame histogram normalization, automatic contrast or added display gamma.
Unpack/channel-order/Bayer mappings must be defined for the selected native format;
unsupported conversion follows existing preparation/failure rules rather than guessing.

The Python binding, supported-format/edge handling and exact scaling integration
remain to be implemented/verified; SDK availability alone is not proof of compatibility. These display choices do not assert physical color
calibration or change camera exposure, gain or white-balance settings.

## Stop, edits and failures

Stop Preview stops capture/pulses and fences the run. Complete outstanding copies,
release camera/viewer attachments and close the camera before reporting cleanup.
Coordinator closes its owner mapping after all users release or exit. Editing camera
settings retains stop/apply/restart under A10: release the old slot, confirm readback,
then prepare a fresh run/layout. WorkerStopPreview.release_device=false retains SDK
ownership during that editing pause only; explicit stop/cleanup uses true. A viewer
change alone never enters this path. Failed readback leaves capture/pulses stopped.

Shared pulse edits pause dependent external previews before CONFIGURE adoption;
[microcontroller.md](microcontroller.md) owns ordering. Independent free-running
previews need not pause for an unrelated MCU change.

PreviewConsumerReport binds client/controller/consumer generations and run/allocation/
transfer. Duplicate reports are idempotent; ATTACHED cannot regress RELEASED or revive
retired work. FAILED is not release evidence; later verified RELEASED may discharge
that obligation while preserving the error. Send release/failure evidence independently
to controller and supervisor; controller normally relays it to coordinator. Supervisor
has cleanup authority, not viewer-start authority. Missing acknowledgements retain
existing reconciliation/deadlines, not another retry budget.

A cancelled attach may leave handles already transferred. Keep its cache/ledger entry
until reconciled and expose cleanup_pending with its run ID. GetPreviewAttachment may
return a retired known transfer with release_only=true: its exact target closes those
handles once without reopening memory or reading pixels. Late attachment reports may
populate this cleanup cache only. Unknown/unavailable data never proves release.

A viewer never writes shared memory, so its failure cannot corrupt the slot; exact-
process exit proves its handles are gone. Producer failure retires the slot under A03.
Required capture/session failures retain E06.

Remaining implementation includes registration, Windows transfer/cancellation, GUI
consumption and device integration. These declarations establish no measured latency.
