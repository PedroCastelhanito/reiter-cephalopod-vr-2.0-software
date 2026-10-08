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
