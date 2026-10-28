# Visual Stimulus prepared asset lifetime

Governing rule: [V04](../../docs/architecture/visual_stimulus.md#v04). Apply to every external
image, video, arena dependency and projection/calibration resource consumed by a
prepared plan, with saving On or Off. [V13 replay](replay.md) separately owns the
manifest and preservation of external originals. This declares source protection;
no Windows adapter, decoder integration or tested storage profile is delivered.

## Stable source to prepared resource

Resolve logical references under E07's configured asset root. Open a protected source
before hashing, importing or decoding its bytes. Identify and protect transitive
external dependencies before they are consumed; embedded resources inherit their
container's protection and a stable subresource reference. Do not permit an importer
or decoder to bypass this resolver and open an unprotected path or network URL.

Choose the existing applicable resource path, not another operator authoring mode:

- Small assets: read one complete protected snapshot, derive any required SHA-256
  from those exact bytes and prepare owned immutable memory/GPU resources. Release
  the source handle only once no later operation needs source-file reads. Keep a
  prepared representation sufficient for planned reuse; an unexpected need to reload
  an unprotected file invalidates preparation rather than silently using new content.
- Streamed assets: retain protected read handles while any prepared consumer may
  need more bytes, including later trials, paused instances, returns and loops.
  Hash and decode the same protected file object. Preserve V11's bounded decoded
  queues; protection does not require whole-video loading or a disk-frame cache.

Count source snapshots, importer/decoder working memory, retained handles, prepared
CPU data and GPU resources in their respective preparation budgets. Share immutable
resources where compatible; never share mutable decoder position across independent
instances. No fixed small-file threshold or numeric resource budget is selected here.
Do not silently switch to whole-video preload when locking fails.

Manifest digests describe bytes consumed, not a later path reread. A digest may come
from V13's [local digest cache](replay.md#trial-recipe-and-evidence-ownership) (keyed by
path, size and modification time) instead of re-hashing; protection is still acquired
before any read or hash, and the manifest always records the digest. Persist digests
in V13's replay manifest in `_stimulus_LOG.json`, which is retained even with saving
Off; saving Off adds no detailed evidence history.
Source protection does not prove source suitability or sustained decode throughput.

V04's bounded still-image residency separates successful Setup validation from
decoded-pixel retention. Validate each unique source/interpretation with bounded
scratch memory; keep its manifest facts after releasing temporary pixels. When
later scheduled reads are needed, use the streamed protected-source lifetime above
even for a small individual image. Evicting decoded pixels or GPU textures never
releases protection needed by later consumers. Compatible immutable content can be
shared across trials; active consumer ownership prevents premature eviction.
Initial residency and subsequent prefetch include transient decode/conversion/upload
memory in admission. Resolved next-use order drives advance loading through one CPU worker and the existing
GL owner. Retain first-use anchors for every image-backed instance across prepared
trials, so selecting any prepared trial or skipping early render ticks cannot expose an
uninitialized texture. Bound the anchors, retained instance selections, next epoch and
one decode/conversion workspace before Ready; a budget too small for these sets fails
Setup. Per-trial scene targets, videos and arenas retain their existing separate bounds.

Share compatible image content/interpretation/recipe geometry and dependency identities.
Read and decode protected sources; eviction never reopens a logical path. Keep at most
one decoded upload handoff. GL uploads submit at most4 chunks of1 MiB (or one wider scanline per chunk) per
owner service turn, starting no further chunk after2ms, then use zero-wait completion polling. Uniform prepared Fold layouts reuse Setup-allocated texture slots and two fenced staging buffers per output; no slot is overwritten before its retirement fence completes. Pool storage remains budgeted until final cleanup. Pin the active/previous image
and pending GPU work; keep reservations until confirmed release. Driver allocation and
submission latency are not a real-time guarantee and require rig measurements.

If a requested texture is late, retain the instance's last selected texture while the
current authored motion, period, size, opacity and epoch clock continue. First use has
its preloaded anchor. Select the requested image as soon as complete; do not replay
expired epochs. Read/decode/graphics failures remain failures. Save-On evidence records
requested and actual identities/indices on every group; Save Off preserves only bounded
diagnostic counters. Cleanup joins the loader before closing protected sources and
retains unconfirmed GPU releases for retry.

## Disposable Fold samples

V04's `fold-samples-rgba32f-v1` preparation evaluates the original full-source Fold
shader at the original surface framebuffer grid, including Bottom's fractional
mapping. Store the covered rectangle as bottom-up RGBA32F and fetch by integer
framebuffer position at playback. No second interpolation, colour conversion or
calibration is applied to these stored samples. Other image fits retain their
original source-loading path. Validate full source coverage before preparation.
The prepared trial records asset identity, packed byte count/digest, per-output
rectangle/offset, original target grid, clip corners and Fold map. Its existing
manifest retains source fingerprints, interpretation and renderer provenance.

Deduplicate by source content and effective interpretation across aliases, trials
and repeated epochs. Compatible output mappings share the prepared samples; keep
per-asset provenance even when pixels are shared. Batches contain at most16 unique
images, with one decoded source at a time and reused GPU scratch. Pack each batch
in one file; its index records each image offset and its own byte count/digest.
Read exactly that range and verify the digest before upload. Report completed
unique images, batch position and shared repeated references through Setup progress.

Keep one persistent bundle per unique image in a visible `cephvr-bundles` folder
inside the asset root, never as loose files in the asset folder itself, with
disk-capacity and bounded scratch admission. Its key binds the protected source
SHA-256, interpretation, each used projector's geometric calibration and display
geometry, image fit/placement, algorithm/shader version and baking GPU name/driver.
Acquire source protection and hash before computing the key. Reuse a matching bundle
after verifying its manifest digest against the recomputed key and the prepared
trial; every load still verifies its byte range digest. A mismatch, missing or
unreadable entry means validate-and-rebake, never partial reuse. Publish atomically
with the manifest last, mark files read-only and leave no valid-looking entry after a
failed or cancelled bake. For a stale bundle, ask the operator once per stale bundle
(with apply-to-all-remaining) whether to keep or delete it while the replacement
bakes; delete only after the replacement is confirmed complete, only on that answer,
and after closing its readers. Unanswered means keep; the question is dismissed at
Start. Stop, failed Setup and shutdown never delete bundles. A read-only or full
asset folder fails Setup clearly. Originals and retained scientific evidence are
outside bundle management. Bundle files do not replace source protection or the
manifest's source digests. A `.cephvr-image-validation.json` index in the asset root retains successful validation facts keyed by current protected content digest, interpretation and validator/software identity. Invalid/stale entries are misses; writes are atomic and index I/O failure never substitutes for validation.

## Legacy texture recipe preparation

The image-producing profile `cephvr1_texture_json_v1` retains the original UTF-8 JSON
as its protected, fingerprinted source. Both `.json` and `.texture.json` filenames
are supported; content selects the recipe. Optional tags must be consistent with a
texture design. Normalize the legacy `params`/`pattern_params` spelling and supported
pattern aliases. Ignore preview filenames as rendering inputs: missing/stale previews
do not replace or invalidate an otherwise valid recipe.

Prepare static RGB8 pixels before Ready with provider compatibility
`cephvr1-texture-raster-v1`. Preserve legacy pattern formulas, explicit/default seeds,
frequency units and runtime resolution defaults. Supported pattern families are flat,
grating, polar grating, checker, vertical/horizontal bars, calibration grid, filtered
noise/substrate, binary/gray noise, regular/random dots and referenced images. Polar
patterns consume the prepared display's actual four-surface geometry; no old nominal
rig dimensions are assumed. Image recipes resolve and protect their transitive image
under the same asset root and retain its separate fingerprint/dependency relationship.

Generated values have the legacy normalized linear RGB interpretation by default;
supported explicit transfer overrides are retained. Budget source snapshots,
generation/decode scratch, retained pixels and GPU upload through existing resource
limits; reject over-budget work before allocating it. Missing blur dependencies or
unsupported source features fail preparation explicitly. Recipe generation never
runs during rendering and does not add an image-residency scheduler or archive copy.
GUI import applies explicit physical tile dimensions when supplied; absent dimensions
preserve the authored tile size. JSON recipe motion fields are not playback authority:
program epoch motion and V02 links own drift and rotation.

## Grating recipe interpretation

`cephvr_grating_json_v1` accepts a Grating texture-design JSON and retains its
original protected bytes/fingerprint. Raw images and other recipe families reject
this profile because they do not declare the required intrinsic grating parameters.
Interpret the saved orientation as zero in memory; the epoch owns final orientation.
Preserve recipe colour/contrast/sharpness and physical spatial period. Legacy designs
are sampled as one unrotated repeat period, with no fit-to-tile frequency rounding;
extent-independent physical-field designs keep that representation and zero their
intrinsic angle. GUI import uses the interpreted period for physical tile dimensions.

Planning preview, eager preparation and deferred protected reload use the same
interpreter. The profile distinguishes content/residency keys from ordinary Texture
using the same file, and existing source protection, cancellation, budgeting and
resource release remain authoritative. Repetition Asset choices retain their periods
under the source contract. No source file is rewritten or sampled during rendering.

## Windows handle binding

For a local source use `CreateFileW` with `GENERIC_READ`, `FILE_SHARE_READ`,
`OPEN_EXISTING` and noninheritable handles. Omit FILE_SHARE_WRITE/FILE_SHARE_DELETE:
conflicting existing access makes acquisition fail rather than accepting weaker
protection. Retain the handle for the required lifetime; advisory locks, attributes,
filenames, sizes and modification times are not equivalent protection.

Give a decoder a read/seek adapter over the protected source. If it needs an
independent cursor, open another equally protected read handle while the original
remains live and verify the same file identity. Duplicated Windows handles share
file position; do not assume duplication creates an independent stream. A library
that insists on reopening by path is unsupported until its adapter preserves the
same protected file identity and exclusion. No pathname-only reopen on each loop.

Keep native handles local to the owning runtime resource/decoder subsystem. If a
later worker binding requires transfer, use the existing Windows ownership/verified
transfer rules; do not serialize a process-local handle integer as a portable asset
reference. Coordinator/controller carry descriptors and preparation results, not
media bytes or a second copy of the decoder's ownership state.

Only admit storage/provider combinations whose protection semantics are supported
by the implementation. A successful generic file open, a network-mounted drive or
a writable mapping is not sufficient evidence of immutable reads. Failure to
establish compatible protection blocks Setup with the logical asset and cause;
do not automatically copy, retry indefinitely or downgrade to change detection.
This contract does not promise protection from arbitrary privileged/kernel changes.

## Lifetime, failure and release

Within one Setup, streamed assets may reuse a fingerprint from a still-live
`ProtectedWindowsSource` after acquiring another protected handle and verifying the
same volume/file identity. Keep per-consumer registration and handle ownership;
cache entries own no handles and cannot substitute pathname, size or modification
time checks for live protection. Rehash after the backing handle closes. Scope the
bounded fingerprint metadata to preparation; do not persist it across Setup runs.
Compatible image decode-validation results remain independently keyed by content,
interpretation, dependencies and display requirements. Setup reports reuse counts
and separate source, successful image-validation and compilation timings; these
are CPU preparation measurements, not presentation or rig throughput evidence.

Tag resources/results with their prepared configuration generation. Keep protection
across Ready and intertrial gaps until no prepared consumer can use the source;
finishing one trial alone is not permission to release a session resource. Late
preparation/decode completions from an abandoned generation cannot replace current
resources. Reference counting or the existing owner registry is sufficient; no asset
service, watcher process or periodic hash task is introduced.

On preparation failure, Cancel Setup, invalidation or session cleanup, stop scheduling
new work, retire/drain consumers within existing lifecycle bounds, close decoder/
importer objects, then release their sources and prepared resources. Preserve V19's
separately required Idle resources and GPU-thread ownership. Partial Setup failure
unwinds acquired resources; no automatic file deletion or asset modification.
Do not close a handle underneath a still-running read to pretend cleanup succeeded.
A stuck owner follows E06/E08 containment and truthful cleanup reporting.

A runtime read/protection/resource failure follows existing required-backend failure
handling. Transient decoded-frame lateness still uses V10's logged hold policy;
it is not permission to continue after a confirmed source failure. No rehash at
trial boundaries or render updates, no reread of completed output files, and no
attempt to repair a changed source during an active session.

Offline replay reacquires protection on relocated external sources, checks recorded
content identities, then uses those protected sources/prepared snapshots. Releasing
live-session handles does not preserve files for future replay; the operator must
retain the original content. No managed asset archive is created.

## Evidence still required

Implementation must demonstrate same-source hashing/decoding, incompatible existing
writers, replacement attempts, independent cursors, imported dependencies, cancellation,
partial-failure release and missing/changed replay assets on supported storage.
[Native source adapters and full resource descriptors](runtime-bindings.md) are declared; their runtime providers remain implementation work; hardware throughput and full-rig verification remain deferred under E15.

Platform references: [CreateFileW access and sharing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
and [DuplicateHandle file-position behavior](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-duplicatehandle).
