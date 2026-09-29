# VR review-video completion

Authority: [V12](../../docs/architecture/vr.md#v12) and
[E05](../../docs/architecture/experiment.md#e05). This binds accepted empty-review
completion; it does not establish an implemented or verified encoder path.
Reuse shared output-result/cleanup mechanisms, with VR-owned accounting instead of
camera producer/frame-log evidence. [V28](../../docs/architecture/vr.md#v28) still governs crashed outputs.

## Final evidence

With saving On, the trial's one tiled review video retains its registered output key
and reserved path in OutputResult. Reservation does not establish that a file exists.
`artifact_present` is true for confirmed presence, false for confirmed absence and
omitted for unknown. `vr_review_video_content` supplies independent online evidence:

| Value | Meaning |
| --- | --- |
| UNKNOWN | Final sample dispositions are unavailable or unresolved. |
| NO_FRAMES | Final cutoff and renderer/recording-thread accounting reconcile; all eligible image dispositions are resolved and zero complete frames were submitted to the encoder input. |
| FRAMES_SUBMITTED | At least one complete frame was submitted through the prepared input path; this does not certify persisted MP4 samples. |

UNSPECIFIED is for other output kinds or incomplete reports, never a successful VR
review result. The camera field stays UNSPECIFIED for VR. Reject conflicting fields,
unknown enum values and output-kind/context mismatches. Required detailed-record
outputs have neither video field set. Counts and identities stay in the existing
detailed stream and bounded final summaries, not per-frame lifecycle RPCs.

At cutoff, reconcile eligible render groups, capacity omissions, admissions and terminal
input dispositions of the composite stream. Drain admitted work, resolve pending capture
slots and confirm writers/children/handles released. A partial or failed input write
cannot become NO_FRAMES merely because the completed-frame counter is zero. Any
known encode/write/sync failure remains failure, regardless of the content count.
Missing final accounting stays unknown. Required state/presentation evidence remains
complete even when every review image was omitted; rendering misses and recording
omissions stay distinct under V10/V12.

## Successful obligation predicate

Require normal activity/Started, stop/cutoff, health and cleanup evidence under E05–E08.
Every required detailed-record output must be present and CLOSED under V28, including
its closing Completion line and successful sync/close. For the review video, only
these combinations satisfy its normal completion obligation:

| Content | Artifact | Closure | Required evidence |
| --- | --- | --- | --- |
| FRAMES_SUBMITTED | present | CLOSED | Successful input accounting, encoder finalization/exit, file sync/close and cleanup. |
| NO_FRAMES | present | CLOSED | Empty artifact finalized, synced and closed without error; do not claim it is playable. |
| NO_FRAMES | absent | NOT_STARTED | Exact recording-thread/FFmpeg ownership history proves the artifact was never created, input/encoder cleanup succeeded and the reserved path is absent after all possible writers stopped. |

Only the last row permits NOT_STARTED for an enabled VR review video. An exact-path
existence check is allowed after writers stop; it is not a content scan and cannot
replace creation/ownership history. Created-then-missing files do not qualify. Never
ignore empty-input exit errors, delete a file to manufacture absence, restart an
encoder to hide failure or supply dummy/duplicated frames. Attempt the selected
path's normal finalization. Its ability to finish with empty input is still to be
verified; this contract does not choose or prove MP4 input packaging.

For a NO_FRAMES review video, emit one warning and retain its exact loss/accounting
summary, using existing bounded diagnostics/admin status.
Keep the video in the registered obligation/result set, including its reserved path
and honest presence state; UI must not advertise an absent artifact as downloadable.
Saving Off creates no recording obligation.

Renderer recording results pass unchanged through coordinator FinishedReport and retained
ParticipantState for the exact process generations/session/trial/operation. The
controller checks the registered obligation set with this predicate rather than a
blanket every-output-CLOSED check. Missing evidence prevents successful Finished;
failure/current-state reporting remains available. Retries use retained results,
without a second close or recreated output.

After a deadline or interruption, exact late evidence may resolve UNCONFIRMED to
NOT_STARTED only for the proven never-created row above; otherwise retain ordinary
E05/E06 closure transitions. Never erase the original failure, change Interrupted
to Completed, resume trial work or promote an unknown crashed video to CLOSED.
No MP4 index scan, frame decode or file-content validation runs in normal runtime.
External post hoc verification remains separate from these online obligations.
