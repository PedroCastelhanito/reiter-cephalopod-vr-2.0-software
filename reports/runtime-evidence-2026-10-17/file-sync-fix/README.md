# File synchronization repair — 2026-10-17

The primary frame-retention criterion passes in a 120 s concurrent workload:
Behavior **3598 received / 3598 retained**, Tracking **7188/7188**, stimulus
**7200 groups / 7200 retained**. Capacity omissions, duplicate mappings/counters,
invalid frames and native counter gaps are zero in this fixture. The session
completes, all exact outputs close, Cleanup and NewSession confirm, and normal
Shutdown returns an exact all-owned-processes-absent receipt. All nine videos from the three runs fully decode and match their retained mapping
counts (managed-assessment.json). The primary three independently confirm
3598/7188/7200 decoded frames; successful decoding does not erase experimental
source omissions.

## Configuration and scope

Camera quality uses unchanged saved p4/CQ23 FFmpeg arguments; stimulus uses its
unchanged saved p4/CQ18 arguments. This is not a quality downgrade to force success.
The explicit engineering fixture temporarily uses **16 stimulus capture slots**,
not the saved three. Scale remains two; review composition is 1280×1000 RGBA8.
This passes ordinary unchanged CPU/GPU resource budgets. Behavior ROI is 1760×1716,
Tracking 1588×1344; source pixel formats and actual exposure/rate readbacks are in
inventory.json and Ready/candidate evidence. Eye and Tracking processing are off;
Behavior/Tracking camera capture, four projectors, rendering and three encoders
run concurrently. The Gaussian-only fixture explicitly prunes unused arena
resources rather than increasing budgets. Cameras are explicitly unaligned free
running, MCU trial/flip outputs disabled, firmware unchanged. No optical timing,
external-trigger or live Tracking-processing acceptance is implied.

The validated recipe consists of the saved camera/stimulus argument arrays plus
capture_slots=16 and recording_downsample_factor=2. validated-recipe.json records
these exact candidate arrays. **Saved defaults are restored**, including three
slots; this does not certify the saved three-slot startup path or universal
loss-free behavior. Optical scene/high-entropy live image suitability remains
unverified; prior synthetic high-entropy encoding evidence is separate.

## Implementation and integrity

A focused standard-library PeriodicVideoSync owner wraps the unchanged native
exact-file handle. At most one live helper flushes that file; completed helpers
are replaced only for due requests. An overdue request stays pending without an
unbounded queue or resetting its due timestamp. Encoder feeding no longer waits
on a periodic FlushFileBuffers call. Frame-log sync ownership is unchanged.

At encoder closure, fence periodic admission, join the exact pending operation,
then issue a distinct mandatory post-encoder-exit flush. Absolute lifecycle bounds
remain unchanged. Timeout retains the helper/handle and blocks close/reuse;
late reconciliation cannot become timely success. A completed flush failure can
release exact resources while video durability stays unconfirmed. Native errors
latch, including thread-start failure. No cadence, final-sync, deadline, resource
identity or closure guard was weakened. Existing A08/windows-resources already
require independent single-pending sync; this repairs implementation, not policy.

After the exact handle is adopted, the recording hot path no longer reopens and
stats its path every frame. Initial creation/sharing validation and explicit final
identity/stat checks remain. Replaced/deleted paths still cannot certify closure.
Remaining metadata contention was a source-supported hypothesis, not independently
isolated by native timing. The final accepted workload changes both ownership and
this redundant work; no isolated per-change throughput attribution is claimed.

## Experiments and limits

| Run | Behavior retained/received | Tracking | Stimulus | Outcome |
|---|---:|---:|---:|---|
| Independent flush, experimental lossless, 60 s |1710/1798 (88 omissions)|3588/3588|3599/3599|Completed, cleanup confirmed|
| Same lossless with aggregate profile, 60 s |1512/1798 (286 omissions)|3588/3588|3600/3600|Completed, cleanup confirmed|
| Final source, saved quality, 120 s |3598/3598|7188/7188|7200/7200|Completed, cleanup confirmed|

The first experimental run's omissions occur 51.898–59.331 s. In the profiled run,
Behavior video flush totals 18.507s/54 calls, maximum3.991s, **concurrently** with
feeding. Preparation totals 9.196 s/1512 calls; pipe writes 2.190 s. Consumer total
29.087 s includes uninstrumented work and must not be added to concurrent flush
time. Both experiments precede the final hot-path guard. **Final source's
pixel-exact real-time capacity is unvalidated**, neither proven failing nor fixed.
The owner prioritizes every usable source retained exactly once, with no duplicate
or padding. Prepared-pixel equality is secondary, not authorization for arbitrary
quality reduction. Source gaps remain separate from retained-video count equality.

The recording volume is C: NTFS on CT2000P3PSSD8 NVMe (storage-mapping.json).
No alternate writable data volume was found. This is mapping, not a diagnosis of
hardware deficiency; no cache, driver, filesystem or system setting changed.
Prior sync measurements establish a blocking stage, not a universal disk limit.

## Validation, provenance and restoration

60 owning cleanup cases and 629 acquisition tests cover actual session feeding
while flush is blocked, source-once mapping, distinct final flush, timeout ownership,
late retry, start/storage failures, safe failed resource closure and original run
bound. Full final backend: 2209 passed, 5 Windows symlink-privilege skips, one rig
case separately passed (NVOF). Ruff/format, Win32 mypy 815 files and backend-boundary
checks pass. GUI code is unchanged; its Oct16 586 offscreen/28 selected native
passes and seven unvalidated native picker roundtrips remain historical scope.
Native Abort exact-Finished and older failed-Setup/Shutdown findings stay open;
they are not retested or silently closed by this normal workload.

Initial clean revision 6f3afad was captured before changes. User commit f447b4f
occurred during the task and contains only initial evidence/settings, not production
fixes; it is preserved unchanged. source-provenance.json records final production
hashes and the missing launch-hash limitation. No production source changed between
owning tests, accepted native run and final suite. The temporary aggregate hook is
removed; session.py's subsequent reviewed hot-path guard is intentional.

All three fresh PFS/readbacks and ten operator files restore exactly; cameras are
closed (final-restoration.json). final-shutdown.json and final-exit.json distinguish
normal command completion and exact process absence. No new emergency report was
created by these three completed runs. Unique JSONL/protobuf/PFS, failed attempts,
logs and media are preserved. Scientific records are archived with hashes; .tmp
video paths remain local, with exact counts/hashes in the media manifest. Only
verified regenerable caches are eligible for cleanup. Evidence manifest records
which byte artifacts are committed versus ignored/local-only.

Final preservation: scientific-records.zip contains all 24 scientific JSON/JSONL files (3,217,832 compressed bytes), verified after archive extraction. media-manifest.json hashes all nine local videos. cache-cleanup.json records 70 verified regenerable directories / 52,714,154 bytes removed. No experiment outputs or operator data were deleted.
