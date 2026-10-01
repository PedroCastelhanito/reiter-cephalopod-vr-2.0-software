# Shared host-clock binding

Authority: [E08](../docs/architecture/system-contracts.md#e08), with trial timing
[E05](../docs/architecture/experiment.md#e05) and acquisition receipt evidence
[A05](../docs/architecture/system-contracts.md#a05). API declarations are in
[host_clock.pyi](host_clock.pyi); these files are implementation contracts, not a
working runtime helper or measured timing evidence.

## API and domain

Implement `host_time_ns() -> int` as a direct call to `time.perf_counter_ns()` in one
small common Python module imported by controller, supervisor, backends and workers.
Use its integer value unchanged. No floating-point seconds round trip, process-start
subtraction, adjustable offset, global lock, RPC clock server or drift calibration.
The fixed domain identifier is `cephvr.host.perf_counter_ns.v1`. Policy declarations
live once in `experiment_policy.toml [host_clock]`; they are validated constants, not
supported alternative APIs. Changing a declaration cannot change the implementation.

Every host timestamp uses this domain, including fields named `*_monotonic_ns`,
camera `acquisition_time_ns`, controller ingress, schedules/cutoffs, rendering and
feedback observations, health/progress and deadline anchors. Durations/intervals are
integer differences, not timestamps. Camera workers stamp receipt immediately after
SDK retrieval returns and before copying/processing under A05. Receiver ingress is
stamped locally before application queueing; sender timestamps never extend budgets.

Python integers are unbounded locally; validate signed int64 range at each wire/file
boundary and fail on overflow rather than wrap or truncate. Equal sequential readings
are permitted; resolution does not require strictly increasing nanoseconds. Existing
ordered-stream regression checks remain in force. Never repair a regression by
clamping timestamps or using wall time. A helper adds no shared mutable last-value
state that would serialize unrelated threads or invent ordering between them.

## Compatibility and registration

Each Python process validates `get_clock_info("perf_counter")` before operational
work: monotonic true, adjustable false, finite positive resolution. Require a supported
CPython implementation with system-wide perf_counter semantics; Windows support
requires Python 3.10 or later and the QPC-backed implementation. The selected runtime
must still satisfy the separately versioned SDK/Windows adapter compatibility rules.
A non-Windows development run does not establish Windows rig compatibility.

`describe_host_clock()` returns the fixed clock ID and the implementation, monotonic,
adjustable and resolution fields from that API. Do not report the clock-info result
for `monotonic` instead. Supervisor validates its own clock before launching children;
Python endpoint-stage `ConfirmLaunchRequest.host_clock` supplies the child descriptor.
Supervisor compares the domain and underlying implementation with its own validated
binding and retains the result in `LaunchState.host_clock`. Require all descriptor
fields, finite positive resolution and compatible implementation; resolution is
reported evidence, not a requirement that floating-point values match bit-for-bit.
Unsupported/missing/mismatched evidence prevents operational registration. Native
codec helpers do not fabricate Python clock descriptors or timestamp CephVR events.
Their registered Python owner stamps host observations using this helper.

Before Setup readiness, verify exact required Python generations still have matched
clock evidence, including consumers attached to acquisition rings. Reconnection to
the same generation preserves the evidence; replacement processes require fresh
registration. Independent clients that issue timestamped control messages must use
the shared binding; a remote SSH client runs the actual control client on the rig
host. Receiver ingress remains authoritative. No numerical timestamp comparison
establishes compatibility, and no sample exchange estimates offsets.

Descriptors stay in internal process registration/diagnostics, not every message,
heartbeat or frame. Existing local-only launch identity and generation checks scope
comparison to one host/run; never compare bare counters across machines, reboots or
unrelated archived sessions. No new synchronization service or public inventory.

## Scheduling and other clocks

Absolute trial times and deadline arithmetic stay in host integer nanoseconds.
When a waiting library requires a relative timeout, compute remaining time from the
original host deadline and the current helper reading. Convert only that bounded
relative interval to its required units. Never pass a host absolute counter directly
to `asyncio.call_at`, a device timer or another API with a different clock origin.
An event-loop adapter may schedule a relative wake-up, but must recheck the original
host deadline on wake and apply E05's inclusive cutoff rules. Early wakes do not
authorize early work; retries and late wakes do not renew budgets or move T.
This specifies the time domain, not a busy-spin loop or a wake-up precision guarantee.

Wall time remains for readable dates, filenames and E04's retained wall/host anchor;
wall-clock corrections do not retime execution. Do not use `time.time_ns()`,
`time.monotonic_ns()`, CPU process/thread clocks, GLFW time or a process-local elapsed
timer as replacements for host fields, even on versions where some happen to share
an implementation. Camera-native ticks/ns, GPU timestamps, video PTS and SpikeGLX
hardware evidence keep their own explicitly named domains. Native callbacks should
hand observation to the Python owner unless an exact compatible conversion is
separately bound; raw QPC ticks are not already host nanoseconds.

## Stored evidence and failure

The acquisition frame-log header's `clocks.host_clock` field is exactly the fixed domain
ID; `timestamp_unit` is `ns`. The validated shared helper supplies these constants,
so they need no duplicate per-camera clock-selection field. Camera-native provenance
remains separate. Visual Stimulus host timestamps use the same binding in its eventual schema.
Old files without this identity are not silently relabeled; readers require an
explicit known legacy mapping before interpreting them as this domain.

A failed clock validation blocks preparation/registration through E06/E08; discovered
incompatibility during active required work is a timing failure, never a silent
fallback. Finite resolution information alone cannot prove observed timing accuracy,
physical onset, scheduler jitter or A08's encoding accuracy. The 1 microsecond MP4
quantization grid remains distinct. SYS-004 hardware-pulse authority and the existing
encoder/timing rig deferrals are unchanged.

Sources: [Python time API](https://docs.python.org/3.12/library/time.html#time.perf_counter_ns)
and [Windows QPC guidance](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps).
The integer API and system-wide scope justify this binding; runtime integration,
scheduler/platform behavior and rig accuracy still require their own verification.
