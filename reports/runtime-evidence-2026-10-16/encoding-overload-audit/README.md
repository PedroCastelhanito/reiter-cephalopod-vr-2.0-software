# Encoding and overload audit — 2026-10-16

**Prepared-pixel lossless capability is verified, but real-time lossless camera
retention is not achieved.** The completed p4 run receives 1798 Behavior frames,
retains 1416 and records 382 explicit recording-capacity omissions from 16.392 to
43.026 s. Tracking retains 3588/3588. Its 5.82 GB Behavior video is not evidence of
complete acquisition retention. Synthetic RGB/gray references, rather than live
camera pixel hashes, prove the prepared-pixel fidelity of the selected recipe.

One final p1-camera diagnostic also adds bounded instrumentation and interrupts
around 53 s. Behavior video sync totals 25.20 s in 44 calls, maximum 3.01 s, with
15 calls above 100 ms. Preparation averages 5.50 ms; pipe writes average 1.34 ms.
Its sampled queue reaches 20/20. Synchronous video-file flush is the dominant
measured stage in this run, not proof of deficient disk hardware or a GPU limit.
The two-factor change does not isolate preset causality. Do not enlarge queues to
hide sustained loss or weaken A08 persistence: retain the 1 s configured cadence
and mandatory final sync. Follow-up storage-path profiling and concurrent-sync
ownership design require focused evidence and review.

The diagnostic lacks exact Behavior frame-log closure; cleanup is not accepted.
Its exact exit receipt proves owned process absence, not successful cleanup.
`profile-stage-assessment.json` preserves process-lifetime aggregates; consumer
total nests stages and queue maxima are sampled, not continuous. The temporary
profiling hook is removed with source SHA256
5346fc095bededd9b74d1e847ba7c2eea877731498d9502000c6254dc5b2303f restored.
`final-restoration-r3.json` verifies all three baseline camera PFS/readbacks, closed
cameras and ten byte-identical operator files after final generation 34d92ca2.
Earlier successful normal shutdowns remain separate valid evidence.

## Changes and validation

The shared Windows adapter polls once immediately after submitting a write,
removing mandatory deferral while preserving exact pending buffer/deadline
ownership. Native stimulus input time decreases from about 14 ms to about 2 ms
under the measured fixture; whole-system CPU comparisons are confounded by
unattributed work. Acquisition uses its separate synchronous pipe path.

Cleanup now joins frozen pathless Setup identities to authoritative scheduled
output paths, retaining strict identity/closure checks. The 8-bit GBR native
buffer/H264 profile aliases retain installed-build, exact-device, profile and
lossless-feature intersections. No 10-bit or policy/filter expansion was made.
Native wait ACK is published before waking the private event; a deterministic
production-wrapper regression proves ordering. The observed failed Setup is
consistent with this race, not conclusively attributed without predicate traces.
GUI fixes preserve owned widget lifetime and correct narrow recording/tab layout.
Inherited cancellation, timestamp fallback and preview changes are separately
captured by `baseline.json`, `inherited.patch` and `inherited-baseline.zip`.

Final backend: **2188 passed, 5 Windows symlink-privilege skips**, one excluded rig
NVOF case separately passed. Native/owning wait checks: 75 passed. Full GUI:
**586 passed offscreen**, 28 selected native cases passed. Seven original native
selection roundtrips remain unvalidated: the first blocks in event processing
after accept, six were unattempted; all seven pass offscreen. This is a bounded
automation limitation, not proven operator picker failure. Static checks/build,
exact commands and scope are in the corresponding logs and GUI inventory.
No live device-cancellation or mixed-DPI acceptance is implied.

## Encoding and overload results

Current A08/A09 and E13/V12 writers retain each usable source once, with explicit
capacity omissions and no CFR padding/duplication. Scientific timestamps remain
in JSONL; video duration is not scientific time. External decoded counts are
compared to retained mapping records, separately from received-frame counts.

Three-slot repaired stimulus: 3592/3600 groups retained, eight startup omissions
(groups 5–12). Temporary 16-slot/half-resolution fixture: 3599/3599, peak eight
slots. Full-review-resolution/eight-slot fixture, four times the RGBA bytes:
3592/3597, five startup omissions at groups 10–14 (0.176–0.242 s), none later
observed. This is bounded higher demand, not proof of sustained saturation or a
universal guarantee. Saved defaults remain unchanged.

Matched standalone tests use eight deterministic high-spatial-entropy frames
repeated per stream, with generation outside timing. H264 p4 lossless input
throughput is 52.82/93.56/121.46 fps for Behavior/Tracking/stimulus. HEVC gives
20.37/35.65/53.34 fps, missing all three 30/60/60 targets, while camera files are
about 14.6% smaller. Every decoded HEVC RGB/gray frame matches the independent
reference exactly (150/300 frames); stimulus count is 300. These short seeded
pool comparisons do not predict live storage size or universal codec ranking.
Standalone GBR preserves prepared RGB bytes; lossless YUV444 alone does not
preserve RGB conversion codes. No raw Bayer/sensor or 10-bit lossless claim.

GPU rendering and NVENC already run on their SYS-002 devices. Existing GPU row
flip/PBO reuse remains. Tested CUDA filter paths do not negotiate the required
RGB conversion; no extra GPU policy is enabled. Normalization is negligible;
measured file sync, rather than GPU conversion, limits the final camera run.
`machine-*`, `inventory.json`, `resource-assessment.json` and exact argv/results
record fresh hardware, paths and device-wide sampled metrics. Process I/O includes
pipes and does not independently measure disk throughput.

## Lifecycle and remaining limits

The initial path-mismatch trials record completed output but their sessions remain
Interrupted. Failed Setup correctly rejects an unused-arena fixture budget; a
later report against its retired attempt triggers a separate lifecycle finding.
Save Off retains science with no videos and normal cleanup/NewSession. Save On
then early Abort writes interrupted camera completions but rejects exact Finished
closure, leaving cleanup unconfirmed. The final diagnostic has another missing
frame-log closure; no guard/outcome was weakened. Original emergency files remain.

The MCU protocol was not freshly established; tests explicitly use unaligned
free-running cameras with MCU trial/flip outputs disabled. Firmware is unchanged.
Tracking camera recording is distinct from disabled Tracking processing. Optical
scene/exposure, external-trigger timing and live sensor-pixel fidelity remain
unaccepted. A full application restart loads the inherited timestamp fallback;
optical confirmation is still outstanding.

Raw media stays locally under the recorded .tmp output paths. Deterministic .raw
buffers are ignored only in this audit directory and retained locally. The final
manifest identifies Git-excluded material; scientific JSON/JSONL is preserved in
scientific-records.zip with byte hashes. Unique raw failures, PFS and protobuf
snapshots are retained. Cleanup is limited to verified regenerable caches.

Final media verification: all 27 managed and 18 standalone primary videos (45 total) fully decode and match retained mapping counts. Interrupted outputs remain unconfirmed cleanup/artifact evidence despite successful decoding. Exact scientific JSON/JSONL from ten managed attempts is preserved in scientific-records.zip (84 files, 6,423,841 compressed bytes).
