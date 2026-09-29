# Acquisition, tracking and VR preparation handoff

Authority: [E08](../docs/architecture/system-contracts.md#e08),
[A03](../docs/architecture/acquisition.md#a03), [T08](../docs/architecture/tracking.md#t08)
and E05/E07/E10. This binds control metadata under the accepted process layout; it is
not another process, data relay or executable implementation. Pixel/flow/result payloads
remain on their direct data paths.

## Acyclic Setup order

The controller owns this dependency progression within the original collective Setup
budget. Independent work can proceed concurrently. A dependency's prepared descriptor
is available before its final Ready report; no step waits for mutually dependent Ready.

| Step | Sender → receiver / existing endpoint | Required content and completion |
| --- | --- | --- |
| Confirm camera configuration | Controller → acquisition, BackendService.SetupSession; acquisition → controller, ControllerService.ReportAcquisitionResolution; controller → acquisition, AcquisitionConfigurationService.ConfirmConfiguration | Acquisition applies/readbacks the requested camera settings. Controller adopts actual readback atomically and confirms the final configuration revision before dependent allocation or tracking Setup. This remains inside the original collective Setup deadline. |
| Admit dependent preparation | Controller → tracking, BackendService.SetupSession | Use the confirmed final acquisition revision and dependent settings. Both backends register their resources/obligations under E08. Tracking reports its new preparation generation immediately after admission. Only work independent of acquisition readback overlaps the first step. |
| Make camera input available | Acquisition → controller, ReportDataPreparation | After confirmed camera layout and allocation, tracking_input carries the exact FrameBufferAttachment targeted at the registered tracking process. Acquisition does not wait for tracking attachment or final Ready to send it. |
| Bind camera input | Controller → tracking, TrackingPreparationService.BindData | Exact descriptor, current tracking preparation generation and configuration revision. Admission means accepted work, not attachment completion. |
| Confirm camera input | Tracking → controller, ReportDataPreparation; controller → acquisition, AcquisitionConfigurationService.ConfirmTrackingInput | The tracking state has data_attached=true and exact allocation/resource_id plus transfer_id in attached_input. Controller forwards that validated report unchanged; acquisition checks it against its registered consumer obligation. |
| Make feedback endpoint available, closed loop only | Tracking → controller, ReportDataPreparation | FeedbackAttachment after listener, catalogue and bounded transport resources are prepared. It can be reported with input completion or later; do not wait for a VR connection before publishing the descriptor. |
| Bind feedback endpoint, closed loop only | Controller → VR, BackendService.SetupSession | feedback_attachment is required on this request. The coordinator forwards it unchanged in renderer WorkerSetup; renderer and tracking complete the existing peer/nonce/credit handshake. |
| Complete preparation | Each backend → controller, ordinary ReadyReport | Verify all of that backend's obligations. Acquisition includes confirmed tracking attachment; tracking/VR include the actual feedback handshake in closed loop. Controller still requires all participant/resource/output gates. |

Open-loop VR Setup does not wait for tracking's feedback endpoint and must not receive
one. Open-loop tracking still attaches its selected camera and computes/records under its
save setting; it has no unconsumed result queue. Disabled tracking adds no ring/confirmation.
Saving Off removes only the corresponding writer/output obligations, never a required
tracking input or closed-loop connection. Existing display/Idle initialization is independent
of this session handoff. Delay VR's closed-loop Setup dispatch until its descriptor exists;
do not mutate an already accepted Setup request or introduce a second feedback-binding RPC.

## Report identity, retention and secrecy

[DataPreparationReport](cephvr/control/v1/services.proto) uses source ReportContext with
exact backend generation, session and that backend's initiating Setup command. The
controller validates it against the registered attempt and confirmed configuration revision.
Only acquisition may send tracking_input; only tracking may send tracking. The descriptor
must match the selected camera/consumer and the same session/allocation; the nested tracking
revision must equal the envelope. Missing required payloads are errors.

report_revision starts at one and increases for changed state within that source Setup
operation. Identical duplicates are idempotent; changed contents under the same revision
fail. Lower revisions cannot regress retained state. Each tracking report is the complete
currently available TrackingPreparationState, with preparation identity always present;
methods and feedback can be absent while still preparing. data_attached is true iff a
successful matching attached_input is present. Descriptor/preparation identity cannot
silently change within an attempt. Further progress only fills/checks the prepared state;
replacement requires the existing cancellation/fresh-Setup boundary.

Retain only the latest report plus ordinary bounded operation/idempotency state. Push
reports during normal preparation. On lost delivery or reconnection, the controller's
existing GetRetainedResult for the original Setup command retrieves data_preparation;
tracking GetPreparation exposes the same underlying state. Reconciliation is bounded by
the original Setup/recovery deadline, not a polling loop or another allocation attempt.
Required report failure blocks/fails Setup through E06; absent readiness is never success.
ConfirmTrackingInput validates original tracking evidence against the exact registered
allocation, transfer and consumer and records fulfillment of that obligation. It cannot
acknowledge another participant or grant execution. Identical retries are idempotent.

ReportReceipt acknowledges receipt only; neither it nor command admission proves Ready,
resource release or a peer handshake. Use registered authenticated control connections.
Memory/event/pipe names, startup nonces and descriptors stay in protected backend/controller
memory and authorized retained-result responses. Exclude them from WatchState/public
snapshots, session/trial logs, configuration history and scientific headers. This report
is not an E04 metadata payload or a GUI-visible configuration choice.

## Cancellation and cleanup

Before accepting a completion, recheck that the Setup attempt is live. Cancellation or
failure retires it immediately, prevents forwarding new descriptors/starting dependent
preparation, and invokes existing cancellation/cleanup on participants already involved.
A late successful attachment is evidence of an existing cleanup obligation, not permission
to restore Ready. Acquisition keeps allocation ownership until matching consumer release
or confirmed process exit under the native-resource contract; it never frees a mapping
merely because Setup was cancelled. Controller/supervisor resource obligations and E06
blocked-cleanup behavior remain authoritative. No lifecycle budget is renewed by a handoff.
