# Microcontroller protocol and applied timing

Derived from [A10/A11](../../docs/architecture/acquisition.md) and
[E06/E08](../../docs/architecture/system-contracts.md). Typed host evidence is in
[microcontroller.proto](../cephvr/acquisition/v1/microcontroller.proto).
This specifies protocol version 2. The matching source is under `firmware/uno`;
COM8 reported the expected protocol after the owner-authorized 2026-10-05 upload.
Managed diagnostic transport and pin settings are implemented but have not passed
a full GUI-to-rig test. Arduino CLI identified COM8 as Uno; timer behavior and
electrical behavior remain unverified.

## Line grammar

ASCII, one command/reply per LF-terminated line, at most 512 bytes including LF.
Accept CRLF as a terminator within that same bound. Tokens are separated by one or
more ASCII spaces; fields are unique `key=value` pairs. No quoting, escaping, tabs,
empty values or debug output. Keys are case-sensitive. Parse a complete bounded line
before execution; reject unknown/duplicate/missing fields and invalid numeric syntax.
On overrun discard through LF; never execute a truncated prefix.

Every request includes `id=<connection_uuid>-<counter>`. Host uses a fresh UUIDv4 on
opening the port and monotonically increasing uint64 counters, starting at 1 without
wrap/reuse. Firmware echoes the token unchanged. Only one request is outstanding;
reply IDs must match exactly. Unmatched/malformed replies are diagnostic evidence,
not successful completion or fresh health. Keep the original deadline.

Booleans are `0`/`1`; integers are nonnegative base-10 digits within the stated width;
frequency requests and CAPS request bounds are positive decimal Hz on the 0.1-Hz grid,
serialized with exactly one fractional digit. Parse/check that grid using decimal
arithmetic, not binary floating-point remainder tests. IDs, pins, timer IDs and firmware
labels use printable ASCII tokens without whitespace, `=` or `,`. CAPS uses a comma-
separated pin list; preserve every pin token exactly, including numeric-looking ones.
There are no per-token length limits beyond the complete-line bound.

| Request | Fields in addition to `id` |
| --- | --- |
| CAPS | None. |
| STATUS | None. |
| PING | None. |
| CONFIGURE | `watchdog_ms`; both `<role>_enabled`; for each enabled role: `<role>_pin`, `<role>_hz`. Disabled roles omit pin/Hz. |
| ON / OFF | Both `behavioral_selected` and `tracking_selected`; at least one is 1. |
| DIAG_START | `kind=trial_state|projector_flip|behavioral|tracking`, `pin=<CAPS pin>`, `duration_ms=2000`; camera kinds also require `hz=<0.1-Hz-grid rate>`. |
| DIAG_STATUS / DIAG_STOP | No additional fields. Operate on the one active diagnostic. |

`role` is exactly `behavioral` or `tracking`. CONFIGURE is one complete application,
not a proposal followed by approval. Group masks select active external session
outputs at trial boundaries or requested previews in Configuration. Never infer masks
from disabled roles' retained host settings. Firmware validates every field, pin,
watchdog and combined timing before touching outputs. Successful configuration clears
inactive assignments and leaves their previous pins LOW.

## Replies and precision

Replies begin `OK id=...` or `ERR id=... code=...`. Successful payloads are:

| Request | Required OK payload |
| --- | --- |
| CAPS | `protocol`, `firmware`, `pins`, `input_pins`, `min_hz`, `max_hz`, `watchdog_min_ms`, `watchdog_max_ms`. `input_pins` is a unique subset of `pins` capable of interrupt-driven rising-edge capture. |
| STATUS / CONFIGURE | `valid`, `watchdog_stopped`, `watchdog_ms`, both `<role>_enabled` and `<role>_running`; for each configured enabled output: `<role>_pin`, `<role>_applied_hz`. |
| PING / ON / OFF | Both `<role>_running` and `watchdog_stopped`. |
| DIAG_START / DIAG_STATUS / DIAG_STOP | `active=0|1`, `kind`, `pin`, `edges=<uint32>`. Input `edges` counts rising edges seen during the bounded test; outputs report zero. `DIAG_STOP` and elapsed duration return `active=0`. |

Only one diagnostic may run, and only when normal outputs are stopped. Firmware
rejects a conflicting request without touching pins. A Trial state test holds its
assigned output HIGH until Stop or the two-second deadline; camera tests use the
requested rate only when it equals that role's configured applied rate, with 50% duty
through the same hardware timer owner. A Projector flip test accepts only a CAPS
`input_pins` pin, configures it as INPUT and counts interrupt-captured rising edges
without driving it. All
diagnostic output pins return LOW on Stop, timeout, connection loss, reset or fault;
the host reports an unconfirmed stop if the acknowledgement is missing. Successful
serial replies prove firmware state and edge count only, not physical voltage,
camera frames or SpikeGLX recording. The GUI requires Configuration and control,
rejects duplicate active assignments, and uses acquisition as the sole serial owner.

`protocol` is uint32 and must equal 2; watchdog values are uint32. Applied Hz is
positive and finite decimal text (ordinary or exponent notation), parsed into the
host's binary64 `applied_frequency_hz`. It is not restricted to the 0.1-Hz request grid.
Firmware emits sufficient significant digits to preserve its computed rate on a
readback round trip; never format applied Hz with the GUI's one-decimal request format.
STATUS and CONFIGURE use the same stored rate and serialization. Reject missing,
nonfinite, zero or negative applied rates for an enabled output. Disabled outputs omit
pin/frequency and report running=0.

Boot state is invalid, stopped, with both outputs disabled; `watchdog_ms=0` means no
applied watchdog only in that invalid state. After watchdog stop, last settings may
remain visible but cannot pass Ready. ON requires successful fresh CONFIGURE first.

Firmware calculates and reports the applied nominal frequency. Timer registers,
clock sources, dividers and counts remain private firmware details; CephVR does not
reconstruct a frequency or select board timer profiles. The host compares retained
reported frequency, pin, enablement and watchdog configuration on preparation;
display rounding is not equality and running flags follow the expected lifecycle.
Stable readback does not prove physical frequency or oscillator accuracy. Hardware
pulses recorded by SpikeGLX remain the scientific alignment authority.

CAPS reports supported pins and broad request bounds, not every valid joint pin/rate
combination. CONFIGURE validates the full combination and selects nearest feasible
timing under A11. No particular timer representation is required on the wire.

Build the complete bounded reply before applying CONFIGURE. If the resolved reply
cannot fit, reject with REPLY_TOO_LONG without changing outputs. CAPS likewise returns
one complete bounded reply or an error; no truncation/pagination. This requirement
constrains firmware support, not the existing host's line-size limit.

## Failure and command semantics

Minimum symbolic error inventory:

| Code | Meaning |
| --- | --- |
| BAD_COMMAND / BAD_ID | Unknown verb or unusable request identity. |
| MISSING_FIELD / DUPLICATE_FIELD / UNKNOWN_FIELD / BAD_VALUE | Malformed or invalid request; reject before application. |
| LINE_TOO_LONG / REPLY_TOO_LONG | Input exceeds bound, or a complete success reply cannot fit. |
| INVALID_PIN / UNSUPPORTED_FREQUENCY / TIMER_CONFLICT | Full requested output combination cannot be supported. |
| INVALID_WATCHDOG / NOT_CONFIGURED | Unsupported timeout, or ON lacks usable configuration. |
| APPLY_FAILED / INTERNAL_ERROR | Application/runtime fault; cancel affected pulse generation and leave outputs off. |

ERR may add `role=behavioral|tracking`, `field=<key>` and `reason=<symbolic_token>`.
Host renders human-readable explanations. If malformed input has no safely recovered
complete ID, firmware may emit `ERR code=...` without ID; host cannot count it as the
outstanding request's acknowledgement. Unknown future error codes still mean failure;
unknown success fields are incompatible with this exact protocol version.

Valid complete commands may refresh firmware's communication watchdog; malformed or
rejected commands do not keep outputs alive. Reads never clear a latched watchdog stop.
Boot/reset loses usable configuration. OFF is repeat-safe; repeated ON preserves phase.
ON starts a stopped configured output's first HIGH on application. OFF/watchdog/fault
cancels scheduling and forces LOW immediately, including mid-pulse. Prevent callbacks
from reasserting HIGH after stop. ON/OFF validate the entire mask before applying;
OFF on an already disabled selected role is harmless, while ON is rejected.

CONFIGURE on running preview outputs stops, applies and restores only previously
running outputs still enabled, unless Stop/fault intervenes. Validation rejection
leaves the pre-command state unchanged; application failure leaves outputs off.
For CephVR edits requiring controller adoption, the coordinator first pauses affected
capture and turns off dependent external previews, so CONFIGURE cannot prematurely
restart them. After matching confirmation and re-preparation, restore only those
previously requested runs still authorized. Free-running independent previews need
not pause for an unrelated MCU update. This is internal coordination, not another
operator confirmation or firmware proposal phase.

No automatic retransmission of CONFIGURE/ON/OFF after timeout. Completion remains
unconfirmed and E06 cleanup/interruption applies. Startup alone uses bounded read-only
CAPS/STATUS probes within the original deadline. A successful reply confirms firmware
state, never received camera frames, physical pulse timing or SpikeGLX acquisition.
Scheduled serial admission and watchdog defaults remain the existing A11/config rules.

## Controller binding and lifecycle

PulseSettingsApplication carries complete requested host settings, active-role mask
and file-resolved watchdog. ApplyPulseConfiguration is an internal pulse-only operation.
For an edit also affecting cameras, use AcquisitionCameraSettingsCommand.pulses and
one combined resolution batch, not competing revisions from independent camera/MCU
adoptions. Setup uses the same coordinator-owned dependency ordering.

AcquisitionResolutionReport.pulses retains request revision/settings/mask and matched
applied observation. Controller validates dependent camera limits and stores requested
values separately from actual timing; its confirmation echoes the exact pulse result.
Do not rewrite requested Hz with off-grid applied Hz. Warn on differences without an
operator prompt and log active-camera setup through existing metadata paths.

The observation binds port, connection/request IDs, monotonic reception time and
capabilities' separate observation time. Snapshot device views show this evidence.
PING can update existing operational health/running evidence but cannot refresh full
configuration or CAPS timestamps. New connection/reset invalidates old capabilities
and configuration confirmation. Setup refreshes CAPS; between trials use retained
capabilities plus required current-state verification. Locked-session drift fails,
without applying/adopting a new timing configuration or resuming Interrupted work.

Firmware installation remains manual; automatic flashing stays deferred. Board-specific
resolution, parser/serial implementation and hardware verification remain outstanding.

## Scheduled serial boundaries (A11)

The serial owner knows each scheduled ON/OFF boundary B. Admit routine PING/STATUS/
CAPS only when `now + ack_timeout < B` (and within any earlier operation deadline).
Defer queued routine work otherwise. Reserve the channel until the boundary command
has completed; check deadlines on actual dispatch, not only when enqueueing. If an
already-outstanding request cannot drain within a newly registered boundary/cutoff,
report the conflict and block timely release/start under the existing failure rules;
do not shift the target to accommodate it. Service
keepalive early when needed; preparation validates that these reservations fit the
configured watchdog budget. Do not extend deadlines, disable the watchdog or overlap
requests to resolve a conflict. Missed drain/command deadlines use existing failure
handling, not a late successful start. Clear unsent execution commands on interruption.

Scheduled reservations do not preempt a request already sent when Abort arrives.
Stop local admission promptly, prioritize OFF at the next available serial slot,
retain its original deadline and report unconfirmed stopping if evidence is late.
No second serial channel or immediate hardware-stop guarantee is introduced.

## Stop-budget validation

`microcontroller.ack_timeout_ms` defaults to 100; the owning experiment
`stop_report_timeout_ms` remains 250. `microcontroller.stop_completion_margin_ms`
defaults to 50 and reserves camera stopping/drain plus end-to-end report delivery;
it is not an extra timeout or sleep. Before Ready require
`2 * ack_timeout_ms + stop_completion_margin_ms <= stop_report_timeout_ms`.
One full outstanding serial request may precede OFF on unexpected Abort. Include
command transport/dispatch and reporting queues in the completion reserve. Verify
camera-stop/drain work on the critical path plus a positive report-delivery allowance
fits that reserve, using resolved per-camera drain margins; parallel camera work uses
its longest path, not an assumed free serial interval. Normal scheduled reservations
can reduce actual waiting but do not justify ignoring the Abort case. Missing required
bounds or incompatible settings fail preparation. Static budget compatibility does not
prove rig latency; SDK stop/drain and delivery bounds still need rig verification.
Original operation deadlines always win, including when fewer than two full command
budgets remain after delayed delivery. No retry or recovery receives a fresh allowance.

## Host boundary and evidence binding

For a released trial, B_on=T and B_off=T+resolved_duration on the common host clock.
These are serial dispatch targets. The coordinator retains both with the exact
scheduled trial and active external-camera mask, reserves the channel under the
preceding rules and dispatches grouped ON/OFF when the corresponding boundary arrives.
No command may start an output early to compensate for serial latency. ON requires
valid release and an unfenced trial; cancellation/interruption cancels unsent ON.
If no external camera is active, send no empty-mask boundary command and create no
pulse obligation; free-running cameras retain their own local schedule.

Do not put future timestamps on the wire, synchronize a firmware clock, add a lead
compensation setting or shift T/end after dispatch. The current ASCII ON/OFF grammar
is unchanged. Start pulses on firmware application under A11, with actual physical
latency still unknown until rig verification. Camera workers independently admit
receipts at T and seal at the E11 cutoff; late pulse/frame delivery cannot extend
that interval. OFF completion and camera admission-stop are separate evidence.

Once the normal boundary is due, use the next scheduler opportunity with the channel
already reserved. Ordinary OS scheduling delay is not itself permission to change
the boundary. Do not issue ON once required start evidence can no longer meet E05's
T+250 ms bound or after interruption/end. Failure to drain/reserve the channel uses
the existing release/start failure path; no overlapping request or speculative retry.
Always retain best-effort OFF cleanup if stopping is late; late success can reconcile
safety evidence but cannot restore a timely Stopped outcome or re-enable failed execution.

For each dispatched command, its reply deadline is the earliest of dispatch plus
the existing acknowledgement timeout and the applicable lifecycle/operation deadline.
Complete Started/Stopped report delivery still must fit E05's original bounds; an
ACK at the last instant grants no extra delivery allowance. Command acceptance or
ON OK alone never proves camera activity. Acquisition Started also needs its actual
camera/worker evidence; Stopped needs camera activity ended and the selected MCU
outputs confirmed off. Bounded buffered-result drain/accounting is separately governed
by recording-lifecycle.md; it cannot postpone Stopped or turn admission sealing into
proof of device stop. Missing OFF evidence stays unconfirmed even if camera rings
are sealed; missing camera cutoff remains unconfirmed even if OFF was acknowledged.

On Abort/interruption, camera-local admission stops promptly under E11 while the
serial owner cancels unsent ON and prioritizes OFF at the next available slot. A
transmitted request is not preempted. OFF retains the original stop issuance and
earlier deadline; do not reinterpret its eventual dispatch as a new stop boundary.
A timed-out ON cannot be retried as execution; a fresh OFF cleanup request has its
own request ID and preserves the original failed/uncertain ON evidence.

### Typed host evidence

PulseCommandEvidence in microcontroller.proto holds the existing connection/request
IDs, ON/OFF verb and exact selected role mask. Normal commands carry scheduled boundary
T/end; interruption OFF instead carries original stop_issued_monotonic_ns and omits
a scheduled boundary. Capture dispatched_monotonic_ns immediately before attempting
the serial write, not when queueing it; this is a host write-attempt timestamp, not
completion at the device. A partial write/error retains its uncertainty and error.

Set acknowledged_monotonic_ns only on receipt of a complete valid matching reply.
Set applied=true only for matching OK plus validated resulting selected-output state;
applied=false represents matching ERR, with error_code. Missing/malformed/unmatched
replies cannot populate success or refresh a deadline. Carry returned state verbatim
when valid. No firmware-application timestamp or physical pulse time is invented.

The existing acquisition device-status path retains current/latest completed
TrialPulseEvidence with exact WorkContext, never a history of PING traffic. StartedReport
carries the successful grouped ON observation; StoppedReport carries grouped OFF.
Scope them through the enclosing ReportContext; stale generations/requests cannot
satisfy newer work. Retain failure/late evidence through existing operation/recovery
views without replacing original issuance/deadlines or declaring another success.
The coordinator sends each terminal grouped ON/OFF observation to every affected
camera worker (`RecordPulseEvidence`). Camera workers use OFF's
outcome to anchor bounded excluded-frame drain; this call never sends a serial command
or changes the cutoff. Use the same registered context/idempotency/deadline checks.
Terminal outcomes include APPLIED, REJECTED, TIMED_OUT, TRANSPORT_FAILED and
NOT_DISPATCHED. Emit a failed/not-dispatched outcome even when no serial write occurred;
never invent dispatch/ACK times, request IDs or firmware state for an unsent command.
The recording thread requires applicable terminal ON/OFF outcomes before the completion
line, storing outcome and available host times in its `pulses` object
([frame_log_schema.toml](frame_log_schema.toml)). A failed outcome completes the evidence
obligation but not successful stop confirmation. Missing outcome at the original closure
deadline stays invalid and makes finalization incomplete under E06. Late evidence stays
in existing retained failure views; never rewrite a closed file or reset deadlines.
No new process, serial channel or scientific file. Physical edge/exposure matching
remains synchronization/rig work.
