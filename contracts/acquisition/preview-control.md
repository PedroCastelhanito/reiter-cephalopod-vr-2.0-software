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
the newest valid in-trial frame into it at most at that rate. Capture remains active
from Setup through session cleanup, but nothing is published between trials.
Session preview never gates capture,
pulses, recording, tracking, Ready or trial start, and a viewer is never required.
The slot is released at session cleanup, not when a viewer closes.

An update-only SHOW placement may carry optional `camera_display_suppressed` for
the exact existing preview run and authenticated GUI owner identity, including its
native window. Hidden owning pages suppress the native viewer without changing
logical Show, capture or manual placement. Returning to a visible owning page
restores that viewer; an absent or X-closed viewer is never allocated by this hint.
Geometry updates retain pending suppression unless explicitly replaced.

The coordinator allocates a fresh manual-preview run UUID for each actual capture
start or configuration restart, not for viewer attachment. Equivalent already-running
Start returns existing state. Stop retires that run; a delayed command cannot revive
it. The slot descriptor has no fixed consumer; its transfer ledger binds each authorized
viewer to an exact process generation. At most one viewer may be attached at a time.
Controller owner cleanup marks its internal Stop Preview commands as retiring the
owner. Acquisition turns OFF only that camera's external trigger and does not resume
other preview roles; it retains the MCU claim until the remaining external previews
have also been stopped. The controller continues through all camera roles under the
original cleanup deadline and retains a failure if any role remains unconfirmed.

## Start capture

Manual camera actions may publish best-effort `LifecycleReport.operation` progress
with command `CameraAction`, the admitted backend child operation ID, exact backend
generation and work scope, and at most 2048 UTF-8 bytes of action text. The operation
is incomplete with neither `succeeded` nor `failure` set. Controller projects it only
for the live, unexpired camera operation before its terminal device status. Progress
never proves SDK/readback, frame reception, completion or release, changes no deadline,
and does not replace the required terminal evidence. A single background sender and
one replaceable pending action bound telemetry without awaiting controller delivery
on the camera execution/safety path. Telemetry and WatchState may coalesce steps;
the GUI displays observed changes under [G02](../../docs/architecture/gui.md#g02).

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

## Backend-owned camera windows

`ExecuteCameraCommand(SHOW_PREVIEW/HIDE_PREVIEW)` carries the assigned role,
current configuration revision and exact active manual `preview_run_id`; no path or
external consumer. Show attaches a private capacity-one reader in the acquisition
coordinator and creates an OpenCV window on its owning Win32 thread. Capture and
pulses are unchanged; Show completes after the first converted image reaches
the visible window (or is ready for its existing window while its GUI owner is
minimized), and is idempotent for that live window. Hide or native X
closes only the window/reader. Closing or failing a window never recreates it
implicitly; explicit Show is required. Only one display consumer owns a slot.

Show alone may carry `PreviewWindowPlacement`: signed physical-desktop `x`/`y`
coordinates of the visible frame's top-left corner (absolute value at most
1,000,000) and square image `side` of 128–2048
pixels. Controller forwards this display-only hint; acquisition validates it before
reserving an operation. Hide/other camera commands reject it. Without a hint use
a 640-pixel square at native default placement. An already visible Show preserves reader/capture ownership and may coalesce a
new placement on its display thread. Apply it only while native geometry remains
at the last automatic size and owner-relative position; an operator move or resize
opts out until close/reopen or an explicit `snap_to_grid` hint restores the grid
position/size and automatic following. Coalescing retains an unconsumed explicit
snap through subsequent automatic hints. The verified GUI process lifetime cannot
change in place. A layout hint may retarget the native display owner to another
live top-level window within that same process (Dashboard workspace or main
Cameras page); validate the handle before rebinding.
`update_existing_only` marks automatic layout refreshes: if the exact-run viewer
is absent or closed, succeed without allocating/reopening it. Check native X before
applying hints or drawing. Unowned legacy viewers retain their existing placement.
Optional `camera_caption_rgb` and `camera_caption_text_rgb` are display-only
packed `0xRRGGBB` values bounded to `0xFFFFFF` at both command boundaries.
Apply them to native Windows caption background/text before reveal and on layout
updates; absent fields restore system colors. Unsupported native color attributes
retain system chrome. Keep native move/resize/close and reserve its footprint (G01).

GUI measures the requested source's named bracketed footprint in the Preview grid
in the Dashboard workspace or below Cameras/Tracking HUD/log, including native chrome and DPI, and centers its fitting frame
there; without a visible slot it falls back beside the GUI within the work
area. Acquisition positions only its own native window, accounting for invisible
resize borders. The window's title text is blank: the GUI card names the source, and
the title bar remains for move and native X. Win32 resolves its handle from the title
once at creation, blanks the caption, then places by handle; Review does likewise.

The optional `gui_window_handle`, `gui_process_id` and
`gui_process_creation_time_100ns` owner identity must be supplied together or all
absent. The display thread verifies a live top-level window, matching PID and
process creation time, then retains a query/synchronize process handle. The native
owner link keeps the separate OpenCV window above its GUI without global topmost
status. Follow GUI translation while retaining an operator-adjusted offset;
host hiding and minimize/restore follow the GUI without closing/recreating the viewer or changing
capture/pulses. While minimized, retain latest private pixels and defer drawing;
restore redraws them even without a fresh frame. This state remains logically open.
A stale/exited owner fails only the display, closes its reader/link and requires
explicit Show; it grants no process, camera or controller authority. Cleanup
reports handle-release failure rather than claiming confirmation. With no owner
identity retain legacy detached behavior.

Fit preserves source aspect ratio with black padding inside the square image area.
Windows wheel deltas, including fractional steps, zoom by 1.2 per notch about the
pointer from fit to 16×. Clamp image translation to avoid empty space on enlarged
axes; keep padding centered on smaller axes. While zoomed, left-button drag pans
the image using the same translation bounds; at fit it has no effect. Release or
pointer motion without the left button ends panning. Zoom, reset and resize cancel
the active gesture. Double-click restores fit. Render
the current private image directly into the bounded square rather than allocating
a full enlarged source; idle interaction redraws cached pixels without reading a
new shared frame. Native caption/borders remain outside the square image area.

All acquisition Win32 windows share one HighGUI/native owner thread outside the
coordinator event loop. Each viewer waits independently on its frame event; no
frame wait blocks another viewer's message pump. New windows stay hidden through
initial image sizing, physical placement, caption clearing and exact owner binding,
then reveal without activation under G01. A bounded native
event wait also allows message pumping with no new frames; idle timeouts do not
poll frame counters. On attachment or frame wakeup select the newest valid image,
convert private pixels with the common Basler converter, and adapt RGB to OpenCV's
BGR display order. Native/tracking/recording pixels are unchanged. The current
window path supports 8 bits per channel; another depth fails explicitly.

Register the local reader under the coordinator generation and a fresh transfer ID
in the native ledger before attaching. Confirm release only after window and
mapping/event closure; unconfirmed release blocks buffer closure. Stop capture,
configuration restart and owner cleanup close local readers before owner buffer
release. Cleanup still attempts camera/pulse stopping if viewer release fails.

Camera device views carry `preview_visible`, `preview_visibility_revision` and
`preview_failure`. Native closure/failure uses an observation-only
`AcquisitionDeviceStatusReport.preview_visibility` with role, exact run, monotone
revision, visibility, host observation time and bounded failure text. Operation,
result, work and exported path are absent; source is the registered acquisition
backend. Controller adopts only a current run and newer consistent visibility;
observations cannot complete a camera command or alter capture/pulse state. Older
command snapshots cannot resurrect newer visibility from the same run. GUI Show/
Hide completion still requires the exact terminal command and backend visibility.

## External viewer attachment

Use the existing ExecuteCameraCommand path with ATTACH_PREVIEW_VIEWER, current manual or
session preview_run_id and exact registered preview_consumer. This is a separate
operator command, never a camera Start/Stop or settings change. Controller validates current
run, control authority and client-to-viewer identity. No arbitrary PID or
second SDK owner is permitted. Refuse a different viewer while prior attachment or
release is unresolved; a fresh attach, including to the same consumer, waits for
confirmed prior release. Queries and exact command retries remain idempotent.

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

Each viewer's existing reader thread copies and prepares its private newest image,
including SDK conversion, channel order and viewport resampling. Native window,
input and placement operations remain on the shared HighGUI owner (A10). Only one
preparation is in flight per reader; native steps pass private viewport snapshots
and await no image work on the shared owner. Before display, recheck stop/retirement,
session run, native closure/minimization and the current viewport transform. Discard
invalidated work; a newer view redraws from that reader's cached private pixels.
Reader failures return through the native owner's normal cleanup path. Do not signal
release while private work, native closure or mapping release remains unconfirmed.

G01 caps new viewer images at 20 Hz, or the source rate when slower. Pending new
frames may wait through the existing bounded event-service interval until due;
keep native close/placement handling responsive. Read the newest available
frame with A03's copy-then-recheck rule before conversion/rendering; a torn read is
skipped. Coalesce GUI dispatch to at most one pending update indication, carrying no image
backlog. While rendering is busy, newer frames replace the waiting slot; after that
work completes, select the newest frame rather than displaying queued older images.
Check for a newer frame before sleeping again. Never queue one GUI callback per camera
frame or spin on an unchanged slot. Rendering and monitor refresh can still
limit what is actually displayed; preview delivery is not lossless screen presentation.

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

Connecting an additional camera leaves existing captures, run/buffer/viewer identities
and unchanged MCU pulse phase intact under A10/A11. Resolve/prepare only the new
camera and enable only its pulse output after Ready. A rejected addition does not
stop existing independent previews; shared faults still follow E06.

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
to controller and supervisor; the authenticated current controller relays the exact
terminal proof to coordinator and supervisor under [E08](../../docs/architecture/system-contracts.md#e08).
The supervisor accepts either authenticated delivery route with the same registered
consumer and exact identity checks. ATTACHED goes through controller to coordinator
only and is rejected at supervisor. Supervisor has cleanup authority, not viewer-start authority. Its acknowledgement retains the exact
consumer-attested failure/release in bounded supervisor state, available in the existing
recovery snapshot. A later release keeps the earlier failure evidence; duplicates are
idempotent and changed same-result payloads reject. Only already released subjects may
be evicted at the existing entry/byte bounds; exhaustion of unreleased evidence follows
E06. These reports alone do not certify producer/aggregate resource closure. Missing acknowledgements retain
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
