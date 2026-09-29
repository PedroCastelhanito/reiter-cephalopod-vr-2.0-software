# Session logging example

[E04](../architecture/supervisor.md#e04) is the authoritative file/event schema and
persistence policy. [E05/E11](../architecture/experiment.md) owns lifecycle/recording
boundaries; backend contracts own their scientific outputs. This page illustrates
those rules, not a second decision history or complete configuration schema.

All files illustrated below are under the session root's `protocol-data/` child.
The sibling `spikeglx-data/` is reserved for later transfer of the native ephys run
folders; see E04/E12. This example illustrates local lifecycle events, not the still
unfinished remote SpikeGLX start/stop integration.

## Session event example

Illustrative completed session with two 60-second trials. Each line is one complete
newline-terminated JSON object. Times and source labels are examples; the fixed
Setup anchor/timezone in SESSION_CONFIG.json supplies wall-time mapping. Session
identity/schema live there, not on every event. Trial numbers refer to its fixed order.

```jsonl
{"monotonic_ns":1000000000000,"wall_time":"2026-09-22T14:30:00+09:00","event_type":"session_started","source":"controller"}
{"monotonic_ns":1001000000000,"wall_time":"2026-09-22T14:30:01+09:00","event_type":"trial_started","source":"controller","trial_number":1}
{"monotonic_ns":1062000000000,"wall_time":"2026-09-22T14:31:02+09:00","event_type":"trial_finished","source":"controller","trial_number":1,"outcome":"completed"}
{"monotonic_ns":1063000000000,"wall_time":"2026-09-22T14:31:03+09:00","event_type":"trial_started","source":"controller","trial_number":2}
{"monotonic_ns":1124000000000,"wall_time":"2026-09-22T14:32:04+09:00","event_type":"trial_finished","source":"controller","trial_number":2,"outcome":"completed"}
{"monotonic_ns":1125000000000,"wall_time":"2026-09-22T14:32:05+09:00","event_type":"session_ended","source":"controller","outcome":"completed"}
```

Trial 1 records `[14:30:01, 14:31:01)` and trial 2 `[14:31:03, 14:32:03)` on
this illustrative mapping. Completion events occur after closure; their timestamps
do not extend those intervals. These timings prescribe neither a gap nor storage
latency. The first trial's completion metadata must be synchronized before trial 2.

## Configuration and trial references

For this example, trial logs are `SP001_143001_LOG.json` and
`SP001_143103_LOG.json`. Each contains schema/session/trial identity, one-based trial
number, SESSION_CONFIG.json reference and its resolved planned protocol. Use the
canonical UUID and metadata rules in E04; no abbreviated fake IDs or unfinished
stimulus schemas are supplied as executable configuration here.

SESSION_CONFIG.json contains active participants' resolved setup, the fixed order,
clock anchor/timezone, supervisor/active-backend software versions and asset filenames.
For an open-loop session with camera recording and Save VR data off, retain acquisition
and VR setup; omit inactive tracking. Asset hashes/paths, PFS snapshot contents,
scientific histories and unrelated environment inventories are excluded under E04.

## Interrupted or uncertain recordings

Keep planned configuration unchanged. The session log records accepted Abort/error
and interrupted outcomes using E04's event catalog. [E11](../architecture/experiment.md#e11)
separates request issuance from actual producer recording cutoffs; backend timing owns
those cutoffs. A camera's video and frame log use the same camera cutoff even when other
producers stop later. Do not reinterpret a trial_finished timestamp as that cutoff.

Missing completion evidence remains unknown; neither an end event nor a process exit
proves scientific file closure. E04 owns durable metadata/recovery rules and E06 owns
cleanup blockers. No logging failure waits on successful error persistence before
stopping work. Runtime durability and recovery still require E15 verification.
