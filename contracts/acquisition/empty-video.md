# Empty camera-video output results

[A07](../../docs/architecture/acquisition.md#a07) already permits complete acquisition
metadata plus a warning when every recording frame is dropped. [E05](../../docs/architecture/experiment.md#e05)
retains independent lifecycle, content and closure evidence. This contract binds that
allowed outcome without an empty-video encoder implementation or runtime validation claim.

## Independent evidence

OutputResult always identifies the enabled symbolic output and reserved path, even
when no artifact was created. `artifact_present` is an optional boolean: true means
a known artifact exists at that path, false means absence is positively established,
and omitted means unknown. A reserved filename alone is not a downloadable file.
For camera MP4 only, `camera_video_content` carries online evidence:

| Value | Meaning |
| --- | --- |
| UNKNOWN | Final content disposition is not established; this is not an empty result. |
| NO_FRAMES | Final producer/count/cutoff and recording-thread accounting are reconciled; zero frames were submitted to video and every received-frame disposition is resolved. |
| FRAMES_SUBMITTED | At least one complete frame was submitted through the prepared encoder input path. This does not certify how many encoded samples survive in MP4. |

UNSPECIFIED is for non-camera-video outputs or an incomplete declaration, not an
accepted final camera-video result. Content evidence never overwrites OutputClosure.
Partial/failed input submission cannot justify NO_FRAMES merely because an incremental
completed-write counter stayed zero. A known error retains FAILED; unavailable final
accounting/closure retains UNKNOWN/UNCONFIRMED as applicable.

## Completion predicate

For a normally successful recorded camera, require all existing activity/stop/health and
producer-cutoff evidence, drained queues, reconciled final accounting, completed encoder
finalization/exit and confirmed release of its writers/handles. The frame-log output
must have artifact_present=true and closure=CLOSED. Then the video obligation is
satisfied only by one of these combinations:

| Video content | Artifact presence | Closure | Additional condition |
| --- | --- | --- | --- |
| FRAMES_SUBMITTED | true | CLOSED | Ordinary successful finalization/accounting; no required write/error remains. |
| NO_FRAMES | true | CLOSED | Empty artifact was actually finalized, synchronized and closed without an encoder/storage error. Do not label it playable. |
| NO_FRAMES | false | NOT_STARTED | Recording-thread/encoder ownership evidence confirms this video artifact was never created; encoder/input cleanup completed successfully and the reserved path is confirmed absent. |

The final row is the narrow A07 exception, not a general NOT_STARTED success rule.
Late exact evidence may establish that same never-created case from UNCONFIRMED;
preserve the original timeout/error and Interrupted outcome under E05/E06.
An enabled output cannot be removed from the obligation list. If an artifact was
created then disappeared, do not use this exception or relabel it never-created.
Unknown presence, failed closure or an unexplained encoder exit fails normal completion.
A read-only exact-path existence/ownership check may establish absence after writers
have stopped; it is not a file-content scan and never replaces ownership history.
If never-created status cannot be established, remain unconfirmed.

NO_FRAMES triggers the existing grouped NO_VIDEO_FRAMES warning. Preserve all received
frame lines and the completion line's timing fields and diagnostics. No placeholder
image, duplicated frame, fabricated playable MP4, silent empty-file delete or encoder
restart. Attempt normal encoder/input finalization; an empty-input error is still an
error, not a code that may be ignored to force successful completion. Whether the
raw-input/muxer path can complete this case remains rig work.

An already Interrupted session stays Interrupted even when this predicate confirms
all output/cleanup obligations. A zero-received-frame trial cannot use the empty-video
exception to bypass Started or valid-frame health deadlines. Optional evidence never
turns an unstarted trial into real trial activity. Frame dropping does not waive other
required backend failure policies.

## Integration and limits

The camera worker fills these fields in WorkerFinishedEvidence.outputs; coordinator
forwards them unchanged in FinishedReport and retained ParticipantState. Controller
validates against the registered MP4/frame-log obligation set for that exact
camera/trial, applying this predicate rather than a blanket `every output CLOSED` test.
Missing fields fail confirmation; retries join retained results and never close or
recreate files twice.

Other outputs retain their owning predicates. Visual Stimulus's separately accepted result is
bound in [Visual Stimulus completion](../visual_stimulus/video-completion.md); this camera contract grants no
tracking exception. Preview and saving Off do not create
camera recording obligations. Existing result, metadata and cleanup deadlines remain.
CLOSED/FRAMES_SUBMITTED do not claim a reread, decoded-frame count or integrity check.
Normal completed-file validation stays external post hoc under E05.
