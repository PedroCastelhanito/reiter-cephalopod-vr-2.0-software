# Visual Stimulus status

## Missing startup assets — 2026-10-29

Owner-observed startup shutdown after moving Assets: the saved root no longer
exists. CPU display preparation retained FileNotFoundError, but only unavailable
output errors entered the existing verified rejection path; other errors escalated
to renderer/supervisor failure. [V19](../docs/architecture/visual_stimulus.md#v19)
now explicitly includes inaccessible Assets/calibration paths. Preparation converts
FileNotFoundError, NotADirectoryError, IsADirectoryError and PermissionError to a
typed display-asset rejection. Existing exact cleanup/deadline/cancellation/report
guarantees remain required; Setup validation still applies. No directory creation,
saved-path rewrite, dependency or extra state. ARCH-002 review retained the existing
focused preparation/cleanup operations and owning lifecycle test module.

Local validation: lifecycle, coordinator and authenticated controller communication
suites pass (183 tests, one excluded by E15 markers). Ruff and Win32 mypy pass;
802-module boundary check has zero violations (existing size warnings; no touched
module exceeds 500 lines). Sandbox suites stalled and were interrupted; loopback
suites passed outside sandbox. Initial integration run found a coordinator code
mismatch, corrected before the passing run. Formatting corrected after its check.
Commands/provenance: [evidence](visual-stimulus-evidence-2026-10-29/startup-missing-assets/context.md).
Native restart with moved assets remains in the [rig checklist](rig-verification.md);
no GUI restart, live device operation or saved-configuration rewrite was performed.

## Bottom output mirror correction — 2026-10-29

The owner reports physically reversed Bottom left/right while linked-motion preview
is correct. [G01rev389](../docs/architecture/gui.md#g01), within
[V15](../docs/architecture/visual_stimulus.md#v15), adds a fixed native output-X
reflection after Bottom's portrait rotation. Saved X/Y inversions compose with it;
offsets, pixel pitch, valid bounds and output-local markers/masks retain their owners.
Both normal GUI-generated profiles and full-grid diagnostics use the correction.
Planning and native rig previews undo that fixed reflection when placing the output
on the physical plane, preserving linked-motion preview direction. Imported mappings
retain their own definition; fresh GUI preparation regenerates owned mappings.

Local coordinate coverage checks all four directions and saved-flip combinations;
crop/pitch/export/preview checks pass. Four offscreen native OpenGL tests confirm
cropped preview quadrants on all faces and no source/composite writes. ARCH-002 keeps
the correction in existing helpers with no dependency or ownership change. Monitor
full-duration behavior and complete validation/known baseline failures are in the
[runtime assessment](runtime.md#bottom-output-and-monitor-duration--2026-10-29) and
[dated evidence](runtime-evidence-2026-10-29/bottom-output-monitor/context.md).
Physical optical agreement after restart/fresh Setup remains in the
[single rig checklist](rig-verification.md); no experiment was launched.

**Rebake attribution (Oct29, read-only):** owner reports no saved configuration
change despite stale-bundle prompts. A retained old/new pair for
`import-dfeziwys/0007_1_metamer7.png` has identical source identity, GPU/driver,
bake algorithm and Front/Left/Right crops. Only geometry digest and Bottom Fold
sampling differ: the Bottom horizontal coefficient reverses sign, with the origin
shifted by the same span. This matches the generated mapping correction above;
the software change can invalidate a Fold bundle without a saved-settings edit.
Both stored keys recompute correctly from their manifests. The pasted 0242 old
bundle is no longer present, so it was not directly compared. No false miss with
identical complete inputs was established, and another unchanged Setup has not
been run. Retained metadata and comparison:
[evidence](visual-stimulus-evidence-2026-10-29/bundle-rebake-attribution/assessment.json).
Read-only controller snapshot established the current Assets folder; no control
lease, device command or bundle deletion was issued. Temporary client removed.

## Setup inactivity timeout — 2026-10-28

[E06](../docs/architecture/system-contracts.md#e06)/
[E08](../docs/architecture/system-contracts.md#e08) inactivity renewal now spans
CPU validation, graphics uploads, serialization and prepared-artifact publication.
Resource checks read the live cutoff; confirmed meaningful progress carries an
increasing sequence through the coordinator to the controller. Publication has
the current inactivity allowance rather than the remaining total Setup budget.
Controller/renderer Ready, identity, health and cleanup checks remain authoritative.
[Implementation, local tests and limitations](runtime.md#setup-inactivity-timeout--2026-10-28)
include 1772 passing tests / 5 subtests. The historical 32 MB publication failure
is addressed in code; native projector-only full-set publication/Ready now pass in312.52s, followed by
confirmed cleanup. Stall isolation and combined acceptance remain in the
[single rig checklist](rig-verification.md#setup-inactivity).

## Image pipeline audit — 2026-10-28

**Hash-provider repair verified on the native rig:** after confirmed shutdown/relaunch,
repeated the same600-image stimulus configuration/trials, four projectors and90-second
preview/recording/camera-off test. Cold Setup183.473s (previous214.223s;14.4% lower),
warm139.932s (previous192.553s;27.3% lower). First cancel and final Abort/cleanup pass;
original configuration restored exactly, no crop folders remain. Normal validation-index
reader reports600/600 hits with fresh source hashes and matching current/tested validator.
Tracked image/bootstrap source hashes stayed unchanged during this run. Individual runs
establish observed improvements, not a statistical performance guarantee.
[Assessment and stage data](visual-stimulus-evidence-2026-10-28/image-pipeline-native-fixed/assessment.json),
[source provenance](visual-stimulus-evidence-2026-10-28/image-pipeline-native-fixed/source-provenance.json).

90.937s playback:5,458 returned submissions/output, approximately60.01Hz,21,832 image
selections and zero holds. **Zero gaps above50ms on all four outputs**, versus224–225
before the fix. One gap above25ms/output remains, maximum30.998ms (before105.169ms).
Native bundle hashing averages15.656ms, maximum17.345ms, versus77.037/95.505ms before.
Maximum swap time falls from99.549ms to15.044ms; upload remains3.118ms, draw10.562ms,
release0.032ms. Front finish has a27.562ms maximum; no per-frame correlation was retained
to attribute the isolated31ms gap. This confirms removal of the recurring hash/GIL stalls
within this workload, not elimination of every timing miss or proof of optical frame lock.

**Persistent Fold bundles (stages 1-2 implemented, locally tested; not rig-run):** under
[V04](../docs/architecture/visual_stimulus.md#v04) rev51 and the
[asset-lifetime contract](../contracts/visual_stimulus/asset-lifetime.md#disposable-fold-samples),
Setup now keeps one bundle per unique image in `<asset folder>/cephvr-bundles/<stem>.<key prefix>/`
(`fold-samples.rgba32f`, then `bundle.json`; published by folder rename, files read-only).
The key binds the image content key (protected source SHA-256 and interpretation), display
geometry plus each used projector's geometric calibration, the fold crops, the bake shader
digest and the GL vendor/renderer/version (driver). Matching manifests are reused without
decode or bake (byte count and crops checked; every load still verifies the digest). A miss
bakes and records older bundles naming the same relative file, or unreadable ones in that
image's folder name, as replaced stale entries. Stop, failure and cleanup only close readers.
Code: `resources/image_bundle_store.py`, `resources/image_bundle.py`, `rendering/image_bake.py`;
tests in `tests/visual_stimulus/test_resources.py` cover bake/reuse/damage, stale after
calibration and GPU changes, unanswered keep, failed bake, unreadable entries, unwritable
folders and the identity helper. Policy35: `fold_storage`/`bundle_cleanup`.

Stage 2 keep/delete question: each replaced entry (never one reused, i.e. open, in this
Setup) rides the renderer's Setup progress as `OperationState.stale_image_bundles` (at most
64 per report; extra entries wait for the next emitted report). The coordinator bounds the
entries and remembers their IDs for this Setup. The controller (`lifecycle/stale_bundles.py`)
publishes one non-blocking prompt per entry (`keep`, `delete`, `keep_all`, `delete_all`) in
the existing prompt table and GUI dialog. Delete choices send the coordinator's local
`DeleteStaleImageBundles` command, accepted only for recorded IDs before the first trial and
read back from the retained result; failures become a Visual Stimulus warning. Apply-to-all
also answers later entries in that attempt. Start, or retiring the attempt, closes unanswered
questions and keeps those bundles. Tests: renderer progress batching and in-use exclusion
(`test_resources.py`), bounds, deletion and retained outcome (`test_coordinator.py`), prompt
choices, delete-all, dismissal and failure warning (`tests/controller/test_setup.py`).
GUI labels were checked offscreen only; the GUI test package was not run (it hangs on an
unrelated editor dialog). Limits: entries left unsent when Setup ends are never asked about,
so those bundles are kept; a bundle reused for a renamed image still lists its old file name
and may be offered for that name later (a wrong delete only causes a rebake); crash-left
hidden `.partial-` folders are ignored, not removed; no native Setup/bake, prompt-to-delete
run or cache-hit timing yet.

The exact managed bootstrap now selects `_hashlib` by default: twelve41.3MB hashes take
14.69–15.16ms with observer maximum1.670ms, versus prior75–77ms/78.691ms. Explicit
OpenSSL and managed-default digests remain identical. [Benchmark](visual-stimulus-evidence-2026-10-28/image-pipeline-native-fixed/hash-probe.json).
`renderer-sha-provider` is complete;20-minute/full-hour combined-load and optical
acceptance remain in the [rig checklist](rig-verification.md#cropped-image-presentation).
No runtime or policy edits were made in this verification task.

**Pre-fix evidence retained for comparison:**

**Native Setup and gap attribution:** owner-authorized600-image projector-only tests
complete: first Setup214.223s, second192.553s, first CancelSetup and final Abort/cleanup
successful; original protobuf configuration restored exactly and no temporary crop
directories remain. Relative to historical312.52s Setup, cold preparation is31.5%
faster; warm is10.1% faster than this cold run. These are individual observations,
not a controlled distribution. Preview and recording were off; cameras/Tracking/
synchronization were disabled temporarily and restored. The old index validator
mismatched before cold completion; the tested validator generated600 entries and the
second Setup reused that version. Fresh source hashing and key/fact lookup verify
600/600 matches for the tested renderer identity. Concurrent implementation-review
follow-ups changed source files during the test: current on-disk identity now differs
and correctly invalidates those facts. No current-tree cache hit is claimed from the
initial failed post-run lookup. [Native assessment/provenance](visual-stimulus-evidence-2026-10-28/image-pipeline-native/assessment.json).

90.888s playback produced5,032 submissions/output and zero holds across20,128 image
selections, but224–225 gaps above50ms/output, maximum105.169ms. The stage maxima are
bundle read14.199ms, hash95.505ms, upload3.063ms, context activation0.441ms,
staging write0.349ms, texture write2.293ms, completion fence0.843ms, ready poll0.483ms,
draw12.316ms and result release0.053ms. Swap calls measure86–100ms peaks;
finish peaks2.936–29.376ms. Thus small/paced uploads and buffer release do not account
for the recurring long pause; expensive hashing occurs on every image load.

**Reproduced mechanism:** the exact managed renderer executable/bootstrap selects
`hashlib.sha256` from `_sha256`, while the ordinary venv selects `_hashlib`.
A two-thread probe of the same41,297,200-byte payload reproduces75–77ms hashes and
78.691ms observer stalls with the managed default. Explicit available OpenSSL hashing
produces the identical digest in14.7–15.6ms and observer pauses at most1.823ms.
The fallback holds the GIL across hashing, blocking the render thread's return to
Python; swap timestamps can therefore include that wait rather than GPU/vblank work.
225 bundle hashes and224–225 long gaps strongly corroborate this mechanism in playback.
`python_entry.py` imports `python_runtime.py` (which imports hashlib) before registering
base DLL directories; OpenSSL is importable afterward, but hashlib retains its early
fallback. [Exact-bootstrap reproducer/results](visual-stimulus-evidence-2026-10-28/image-pipeline-native/hash-probe.json).

**Provider repair (implemented, locally verified):**
[`python_entry.py`](../src/cephvr/platform/windows/python_entry.py) now reloads `hashlib`
after base DLL registration and refuses to start a managed module unless `sha256` comes
from `_hashlib`. Every digest check is unchanged; V20 pacing is not amended. Through
`cephvr-renderer.exe` the exact-bootstrap probe now reports `_hashlib`, 15.8ms maximum
hashes and 1.79ms maximum observer pauses (was 75–77ms and 78.691ms). The native
managed-entry test asserts the provider; it fails before the fix and passes after.
[Evidence](visual-stimulus-evidence-2026-10-28/renderer-sha-provider/context.md).
A patched native playback comparison is required before calling the gap fixed; residual VSync/optical
skew remains separate. Phase C representation/fence changes are not established as
necessary by these timings. Full20-minute/combined-load/optical acceptance remains open.

**Integrity-check review (source review plus one local probe; no runtime change):**
- *Provider repair path.* Blocking `_hashlib` import, then `importlib.reload(hashlib)`
  after DLL registration, restores `_hashlib.openssl_sha256` in the repo venv (41.3MB in
  20.9ms). [`python_entry.py`](../src/cephvr/platform/windows/python_entry.py) imports only
  `python_runtime` (attribute-style `hashlib.sha256`) before `runpy`, so a reload before
  `runpy` covers every renderer module. Implemented with a startup rejection of the
  `_sha256` fallback (see provider repair above).
- *Setup also pays the fallback.* Every cold image is hashed on protection, re-hashed
  by full-file inspection (`_read_protected(..., verify_hash=True)`) and its baked
  payload is hashed for the manifest on the GL owner. At the measured 76 versus 15ms per
  41.3MB, the 600 bake digests alone are about 37s of the cold Setup; this is an
  arithmetic estimate.
- *Redundant inspection re-hash.* The protected handle is non-shareable (`FILE_SHARE_READ`
  only; no write/delete) and is held from fingerprinting through validation. The
  [asset-lifetime contract](../contracts/visual_stimulus/asset-lifetime.md) requires a rehash only
  after the backing handle closes, so the inspection re-hash can be skipped while the
  same live handle protects the source. Keep the protection-time digest and manifest.
- *Keep the per-load bundle digest.* The same contract requires verifying each range
  digest before upload. With OpenSSL it runs off-GIL on the loader. Folding hashing
  into the `readinto` loop is a minor optional gain. Cheaper non-cryptographic checksums
  are not recommended without a contract change.
- *Validator identity churn.* `validator_identity()` hashes whole module sources, so
  unrelated edits to `image_source.py`, `media.py`, `upload.py` or
  `image_interpretation.py` invalidate all facts. That happened to the 600 native facts
  after the review follow-ups. An explicit validator version would avoid this but risks
  stale facts if it is not bumped; this is owner-choice dev-time churn, not a runtime
  cost.
- *No action.* Header/chunk walks, interpretation equality, per-MiB cancellation checks,
  index parsing and completion polling (ready ≤0.483ms, activation ≤0.441ms measured)
  are not significant.


**Implemented from the owner-approved merged plan (Phases A/B):** exact cached
float32 transfer tables now write a bottom-up upload buffer without the final bytes
copy. Associated alpha retains the original formula. Ordinary validation no longer
converts pixels solely to check output length. Native Setup inspects PNG/TIFF/JPEG
metadata before compilation, then full decode/interpretation validation and conversion
feed the Fold bake in one pass; every unconsumed deferred source is validated before
initial residency/Ready. Cache facts publish only after successful full validation.
Palette/transparency PNG inspection conservatively uses the decoder; those uncommon
inputs can still decode twice. Recipes retain their existing generation path.
No entire-image-set pixel retention or additional process is introduced.

One admitted bundle buffer is reused through `readinto`; its reservation remains until
bundle cleanup and the single loader's upload handoff controls reuse. Bundle loads
therefore reserve no second per-load CPU payload; residency closes the loader before
bundle cleanup. Digest checks remain mandatory. Small changes remove ordinary unchanged-settings copies and unused
PNG payload copies, cache package versions and schedule totals, and separate ordinary
image-validation keys from display geometry/output count. Recipe geometry remains keyed.
Per-trial bounded summaries report bundle read/hash, ordinary-fit source
decode/convert, result release, activation,
staging/texture write, upload, completion fencing/polling, draw and per-output
swap/finish totals/maxima/counts. Loader-thread records and render-thread
reset/summary share one lock. Timing adds no wait or per-frame output file.

[Local benchmark and exactness evidence](visual-stimulus-evidence-2026-10-28/image-pipeline-implementation/benchmark.json):
4K RGB8 sRGB conversion median332→70ms, RGBA8 straight sRGB393→152ms,
RGB16 sRGB330→69ms and BT.709329→69ms. Conversion peak tracked allocation drops
from60 to20.01B/pixel for these cases. Associated RGBA16 remains about67B/pixel;
its formula and performance are retained. Ordinary image admission is128B/pixel
plus encoded buffers, leaving margin above measured conversion plus decoded samples;
recipe admission remains192B/pixel. Tracemalloc is not a total-process or native-codec
memory guarantee. The supplied original benchmark was also copied and rerun; its
new-buffer versus candidate-bytes comparison has zero pixel differences.

Validation: **836 passed / 5 subtests / 80 deselected** in the requested non-Windows,
non-rig suite with authenticated loopback access; two isolated Windows temporary-bundle
tests also pass (buffer identity reuse, corruption rejection, owned cleanup).
72 exhaustive conversion cases compare uint32 views for every uint8/uint16 code,
three transfers, six channel/alpha layouts and opaque override. Deferred-validation
checks cover successful one-decode consumption and decoder failure without cache
publication. Ruff check/format and Win32 mypy191 sources pass; boundaries799 modules,
zero violations. Existing recipe/source, preparation and session size advisories were
reviewed: they retain source lifetime and preparation orchestration; timing aggregation
is a focused helper with no runtime back-reference. No new dependency.
[Commands, provenance and limits](visual-stimulus-evidence-2026-10-28/image-pipeline-implementation/context.json).

Two sandboxed suite attempts stalled at communication and were interrupted; loopback
execution completed. Intermediate timing-fixture/missing-field/type errors were fixed;
a script-induced UTF-8 mojibake in session progress/TODO was repaired and the full suite
rerun. The stale reader-count expectation is corrected to six actual reads.
Phase C remains measurement-gated: no R32F, GPU conversion, fence amortization or V20
pacing change. Native600-image Setup/index reuse and stage profiling remain under the
[rig checklist](rig-verification.md#cropped-image-presentation); no resolution of the
111ms gaps or optical mismatch is claimed.

**Original audit snapshot (before implementation):**

Scope: current dirty-tree image Media path, including Fold and ordinary image fits;
source tracing and focused local behavior checks only. Governing rules are
[V04](../docs/architecture/visual_stimulus.md#v04),
[V10](../docs/architecture/visual_stimulus.md#v10),
[V20](../docs/architecture/visual_stimulus.md#v20),
[E07](../docs/architecture/experiment.md#e07) and
[ARCH-002](../architecture.md#arch-002). No runtime/policy/configuration changes.
Source hashes, commands and validation limits are in
[audit provenance](visual-stimulus-evidence-2026-10-28/image-pipeline-audit/context.json).

Current path: protect/hash sources → unique validation/cache lookup → compile and
resolve output footprints → decode/convert and GPU-bake Fold samples → temporary
bundle → bounded CPU loader → paced GPU uploads/fences → image selection → render,
per-output swaps and optional preview. Fold playback does not decode PNG/TIFF/JPEG;
other fits reload/decode/convert on the existing background loader after eviction.
The [existing native evidence](#high-resolution-presentation-options--2026-10-28)
records 41,297,200 bytes per prepared four-output image and unresolved >50ms gaps.
Those historical results are not fresh measurements of this audit's source snapshot.

Prioritized opportunities (recommendations, not accepted new policy):

1. **Combine validation, conversion and Fold preparation on cache misses.**
   `resources/image_source.py:validate_image_source` decodes and converts the whole
   image, then discards both arrays and RGBA bytes. Later
   `resources/image_bundle.py:ImageBundle.prepare` calls `source.load`, repeating
   read/decode/conversion before baking. A valid persistent index avoids the first
   decode for ordinary images; a cold/missing/invalid index still duplicates it,
   and recipe sources bypass that index. Prefer a bounded per-image preparation
   operation that validates and consumes those same pixels for baking, admitting
   metadata/coverage before Ready and publishing cache facts only after successful
   validation. Do not retain every full image or introduce an unbounded handoff.
   Compiler/footprint ordering makes this a focused preparation-interface change,
   not simply deleting validation. Benefit is Setup latency/CPU, not a direct cure
   for pauses during prepared Fold playback.

2. **Reuse CPU payload storage and keep its reclamation off the GL path.**
   The bundle loader performs `file.read(count)` plus SHA-256 for each load;
   `ImageWorker` retains one result until all uploads are submitted.
   `ImageResidency.service` clears that result and its local reference on the GL
   owner, so the final large bytes release can occur there. At the recorded size,
   each load allocates about 39.38 MiB; a 400ms stream carries about 98.46 MiB/s of
   payload before hashing/staging/driver traffic. These are arithmetic estimates,
   not measured memory bandwidth or pause attribution. Prefer bounded reusable
   `bytearray`/`readinto` storage with explicit handoff/reuse after the final CPU
   upload read; retain per-range digest checks and cancellation/cleanup guarantees.
   A second slot should be added only if measured overlap warrants its extra
   reservation. GPU slots are already pooled; they do not remove CPU allocation.

3. **Measure the complete GL service/presentation cost before changing pacing.**
   `ImageGpu.upload` limits four chunks and checks 2ms between calls, but context
   activation/driver calls are non-preemptible. Completion/retirement fencing and
   replanning sit outside that upload timer. `ImagePool.write` fences and flushes
   every chunk; `ImageGpu.fence` adds full-image completion fences across allocating
   contexts. `ModernGLPort.present` swaps outputs sequentially and calls
   `context.finish()` on paced outputs. That drains outstanding work in that
   context, potentially coupling background uploads to presentation. These are
   profiling targets, not proof of the reported 111ms stalls. Measure read/hash,
   result release, context activation, staging/write, fences, draw, swap and finish
   separately with asset/epoch/output identity. Evaluate fence/flush amortization
   only after tracing proves safe completion/retirement. Preserve V20's truthful
   submission evidence; changing pacing or ownership needs its governing amendment.
   Zero residency holds establishes neither smooth cadence nor simultaneous scanout.

4. **Consider exact single-channel float32 samples for verified opaque grayscale.**
   Four RGBA32F components dominate bundle, read/hash, staging and upload costs.
   R32F with shader replication and alpha=1 would reduce that payload by 75%,
   approximately 41.30 to 10.32 MB/image, while retaining float32 composition.
   All required images and baked coverage/alpha must qualify, including transparent
   edges; the prior 24-source sample does not establish all-600 eligibility.
   Keep RGBA32F for general RGB/alpha assets. This is a new representation requiring
   V04/contracts/policy/evidence integration and byte-equivalence checks, not an
   authorized implementation choice. R8/half-float cannot be assumed equivalent to
   already interpolated float32 Fold samples, particularly Bottom's fractional map.

5. **Remove small repeated CPU work after the larger costs.**
   `ImageResidency.select` copies Pydantic image settings every frame even when
   requested==actual. Reuse unchanged settings and copy only for a hold; keep actual
   image evidence/counting intact. Replanning also recomputes source-byte totals;
   immutable schedule totals can be prepared once. Neither is established as the
   dominant cost. `media._png_transfer` copies every chunk payload, including unused
   IDAT data; slice only recognized metadata (or use views) while preserving complete
   structural rejection. For plain images, `image_validation_key` includes display
   geometry/output count although decoding validity is independent of them, causing
   avoidable cache misses after display edits. Separate decode-validation identity
   from geometry-dependent recipe/crop identity without weakening source hashes or
   software-version invalidation. Memoizing package-version lookup within one
   process is a minor Setup improvement, not a new caching subsystem.

Optional preview composition is already gated to V01's 20Hz cadence and hidden
viewers skip it. A later authorized native comparison with preview visible/hidden
can isolate its cost; do not build another preview pipeline or drop required
scientific evidence. Increasing queues, lookahead or VRAM alone is not recommended:
the stopped pooled run already had zero holds and failed cadence. Persistent pixel
bundles across Setup are outside the accepted disposable-bundle rule.

Validation: focused resource/rendering selection finishes **61 passed, 1 failed,
390 deselected**, [raw result](visual-stimulus-evidence-2026-10-28/image-pipeline-audit/tests-external-temp.txt).
The failure at `test_resources.py:1015` expects five readers after six explicit reads
(validation, two source reads, two loads, one cached-info loader call); this is a
current test assertion inconsistency, not evidence that a validation-index hit itself
reads pixels. Keep a small follow-up to reconcile that expectation. Two earlier temp
fixture failures are retained in provenance; the final external writable temp path
resolves them. No test assertions or runtime source were edited. Native stage
profiling, index reuse, grayscale eligibility, optics, full endurance and combined
load remain open in the [single rig checklist](rig-verification.md#cropped-image-presentation).

## High-resolution presentation options — 2026-10-28

**Owner observation after the stopped pool test:** projector images did not change
at the same time and stimulus-sync pulses remained very inconsistent. The saved
four image rules have identical seeds, streams, offsets, strides and initial assets;
the source-selection path polls residency once before selecting all instances, but
this is not proof of physical output agreement. V20 uses separate per-output swaps;
transition skew versus sustained different images is not yet distinguished. No
additional rig run was started. Source audit also identifies a remaining per-image
41MB CPU allocation (`file.read`) and possible final-reference release on the GL
thread, plus per-output context switches/fences and preview composition. These are
profiling targets, not established causes. Both visible consistency and timing remain
failed acceptance criteria, independently of zero residency holds.

**Latest pool test:** owner requested Stop after approximately58s. Abort7420f0e8
and restore6d6ea362 succeeded; cleanup confirmed, no temporary crop folder remains.
Policy34 reused GPU slots and fenced/paced uploads, but recording-off playback still
reported143 submission gaps above50ms per output (maximum110.918ms), despite zero
holds across12,920 selections. This is an unresolved pacing failure; pooling alone
has not fixed sync pauses and the1200s acceptance was not completed. The source-folder
validation index contains600 entries; an initial channel-name mismatch in its reader
was fixed, with native reuse still requiring verification. Owner also requested a
whole-pipeline audit and combining decode/validation/crop generation; that combined
stage remains to implement. [Stopped assessment](visual-stimulus-evidence-2026-10-28/setup-optimization/pool-endurance/stopped-assessment.json).

**Current native finding:** the owner stopped the first20-minute attempt after
observing only Left and random stimulus-sync pauses. Abortf239cfbf confirmed cleanup;
restorea16f295d restored original settings.19,796 selections reported zero readiness
holds, which does not prove correct projector pixels. Earlier isolated equivalence
and happy-path four-output state checks therefore do not establish presentation
acceptance. The trial GPU-resource scoping dropped `:crops` metadata, leaving the
layer shader in full-source Fold mode for prepared cropped textures. A regression
fails before the focused handoff repair and passes afterward;261 rendering and
calibration cases pass (50 deselected). Native repaired retest is in progress with
stimulus data enabled temporarily to measure the reported random sync pauses.
[Failed run evidence](visual-stimulus-evidence-2026-10-28/setup-optimization/twenty-minute/after-abort.json),
[repaired retest](visual-stimulus-evidence-2026-10-28/setup-optimization/twenty-minute-repaired/test.log).


Owner selected temporary RGBA32F bundles for all four projectors with a small
fixed buffer under [V04](../docs/architecture/visual_stimulus.md#v04)/
[E14](../docs/architecture/system-contracts.md#e14), with batching introduced in
policy31. Setup uses original Fold-shader sampling at the unchanged surface framebuffer grid, followed by integer sample
fetch during playback. This resolves Bottom without rebasing its fractional
texture coordinates. Composition, opacity and downstream calibration remain live.
Source images must cover all consumed Fold areas; insufficient coverage fails Setup.

[Original-shader comparison](visual-stimulus-evidence-2026-10-28/setup-optimization/batched-reference-equivalence.json)
verifies all600 images and all four mappings byte-for-byte, including full RGBA32F
surface coverage: zero different components,143.5s on RTX5060Ti. The reference
fragment shader is extracted from HEAD, independent of the new branch. The saved
display-profile digest matches the native test. This is one isolated GPU context,
not optical acceptance. [Reproducer](visual-stimulus-evidence-2026-10-28/setup-optimization/verify_batched_reference.py).
Prior equivalent run took159.6s; this is a single-run comparison, not a throughput guarantee.
Prepared payload is41,297,200 bytes/image across all four outputs,23.08GiB for600.

The owner-requested preparation batches contain at most16 unique content identities,
one decoded source at a time. GPU source texture, shader, VAO and framebuffer are
reused; direct read-into avoids the intermediate crop-byte and final immutable-byte
copies. Each batch uses one indexed temporary file, with per-image range/digest
validation:600 unique images need38 data files plus the manifest. Repeated epochs,
asset aliases and trials share compatible content/interpretation identities.
Declaration reason text remains per-asset provenance but does not split validation.
Setup reports unique-image counts, batch position and shared repeated references.

Bundles are sibling directories of the asset root, protected by Windows delete-on-close
handles. Current plus two future epochs, required first-use/held anchors and pending
fences bound residency independently of spare VRAM. One loader reads/verifies ready
bytes; no playback PNG decode. Cleanup closes readers/files then removes the folder.
Supervisor startup/renderer-exit recovery removes only verified unlocked empty
folders; unrelated content blocks removal. Native tests cover active ownership,
normal closure, abrupt child exit and unrelated-file refusal; power-loss acceptance
remains outside this evidence.

Six native batch/source-protection cases pass, including17 unique images across a
batch boundary, repeated references across trials, offset reads, corruption and
same-content/different-reason validation reuse.95 configuration/lifecycle cases and
5 subtests pass; five-source Win32 mypy, scoped Ruff,14 schemas and backend boundaries
pass. The broader resources/rendering/compiler/configuration suite passes395 cases
and5 subtests, with49 platform/rig cases deselected.

Before batching, native Setup119e1f1c reached Ready, StartSessionf359ecb2 ran the
600-image saved protocol on four outputs for240s with fixed lookahead, Abortd03dee4d
confirmed cleanup and restore66b65418 restored original settings. Folder/registry
were absent;16 Running snapshots and no residency-hold warnings were retained.
[Assessment](visual-stimulus-evidence-2026-10-28/setup-optimization/crop-playback/assessment.json).
SaveOff dummy testing has no detailed frame history. Window capture hit Computer Use
app-approval timeout, so no visual/optical inspection is claimed. Earlier native GPU
catalogue reporting used the stale original Setup cutoff; the active command/live
cutoff repair is covered by80 lifecycle cases and the subsequent successful Setup.
Final policy31 batched Setupc7d1a481 reached Ready in312.52s, displayed batch/image
counts and35,400 shared uses, and created38 data files plus one manifest.
Startf7c347eb completed240s of native four-output playback; Abort87eddac5 confirmed
cleanup in2.39s, with folder/registry absent. Original configuration equality was
verified after restore643266bd. The initial restore was rejected because concurrent
Grating work changed the shared policy to32; a graceful restart resolved that
version mismatch. This is not a Grating acceptance result.
[Final native assessment](visual-stimulus-evidence-2026-10-28/setup-optimization/crop-batch/assessment.json).
Remaining acceptance: [full-hour, combined load and optics](rig-verification.md#cropped-image-presentation). Combined camera
Setup has a separate [deadline concern](acquisition.md#setup-confirmation-deadline--2026-10-28).

The earlier conversion optimization preserves every uint8/uint16 code, orientation
and immutable source input.325 resource/rendering checks passed, plus12 strengthened
code-value cases. Full600-image CPU preparation/compilation/serialization/parse
took110.54s: image validation92.45s, source protection4.08s, compile6.74s,
serialization1.72s, parse5.09s. Fresh native Setup0c335bf6 reached Ready under the
unchanged180s bound. Operator started playback;97.22% of42292 selections held the
previous texture. Authorized Abort084821d5 succeeded with cleanup confirmed.
Prior4-chunk/turn upload budget cannot sustain four full3840x2000 float-RGBA
copies every400ms.64-chunk candidate plus configuration/resource/render checks
passes341 cases/5 subtests, but has no native playback acceptance. No Start was
sent by this agent. GUI inspection found operator-started Running; no UI input
was issued. No control restoration was needed before that operator Start.

Benchmarks are in [options/results.json](visual-stimulus-evidence-2026-10-28/setup-optimization/options/results.json),
with reproducible [script](visual-stimulus-evidence-2026-10-28/setup-optimization/options_benchmark.py).
Actual retained calibration/Fold map yields source bounding rectangles with one
texel filtering halo: Front(1029,0)-(1791,691), Left(0,0)-(1031,682),
Right(1789,0)-(2816,697), Bottom(1043,694)-(1777,1754). These are source footprints,
not assumed output resolutions or rescaled images:2,723,543 pixels total.

RTX5060Ti, four independent invisible GL contexts, preallocated textures,
five warmups plus30 timed completed uploads (finish on every context), byte-equal
texture readbacks. No drawing/vsync/camera load or photodiode measurement.

| Representation | MiB/change, four outputs | Median upload ms | p95 ms |
| --- | ---: | ---: | ---: |
| Full RGBA32F |468.750|21.43|23.08|
| Cropped RGBA32F |41.558|2.36|2.69|
| Cropped R32F |10.389|1.23|1.26|
| Full R8 |29.297|2.19|2.87|
| Cropped R8 |2.597|0.63|0.99|
| Cropped R8 through PBO |2.597|1.52|2.07|

PBO trial includes staging copy and completion, without overlap; this does not
evaluate asynchronous ring overlap.24 evenly spaced source images were verified
uint8 and channel-identical. Warm read/decode median55.51ms/p9576.35ms; grayscale
crop packing1.80/2.07ms; reading a prepared2.60MiB crop bundle5.03/5.64ms.
Not a cold-storage or all600-file statistical test. Initial two wrapper launches
failed missing DLL initialization; process-local DLL directories fixed startup.
WGL emitted a teardown warning after results/readback checks; no projector windows
or application state were changed by the isolated benchmark.

Recommendation, pending owner choice: hash-bound, calibration-specific lossless
source crop bundles, small fixed schedule-driven CPU/GPU rings, reusable textures,
explicit completion fences and per-image timing/identity evidence. Start with
cropped RGBA32F for the smallest precision-preserving change, or cropped R32F for
verified grayscale (45.1x less transfer than current). Retain float32 interpolation
and calibration downstream; R8 remains a faster alternative requiring interpolation/
normalization equivalence measurement. CPU crop conversion must preserve normalization,
UV origin, pixel centres, border semantics and one-texel bilinear support; do not
downsample or apply calibration twice. Moving/rotating/repeating/dynamically warped
stimuli need a swept footprint or full source fallback, not a static crop guess.
Cache identity includes source hash, encoding, mapping/calibration, crop algorithm
and format version. Bounded lookahead is sized by measured tail latency, not spare
VRAM; all600 resources still require validated identity/preparation under V04.
Persistent cache reuse across Setup would need an explicit V04 amendment.

References: [Psychtoolbox MakeTexture](https://psychtoolbox.org/docs/Screen-MakeTexture)
supports monochrome and distinct integer/float precisions;
[PreloadTextures](https://psychtoolbox.org/docs/Screen-PreloadTextures) checks VRAM
residency; [PsychoPy timing](https://psychopy.org/general/timing/reducingFrameDrops.html)
moves expensive generation/texture changes away from critical presentation;
[PsychoPy rendering](https://psychopy.org/general/rendering.html) recommends reducing
uploaded pixel counts; [Bonsai image sequences](https://bonsai-rx.org/docs/api/Bonsai.Shaders.LoadImageSequence.html)
exposes texture formats and sequence loading;
[Bonsai playback](https://github.com/bonsai-rx/bonsai/blob/main/Bonsai.Shaders/PlayTextureSequence.cs)
separates texture sequences from timer-driven presentation;
[Khronos PBO](https://wikis.khronos.org/opengl/Pixel_Buffer_Object) documents transfer
staging. These tools were researched, not installed or benchmarked against CephVR.

Before accepting an implementation: all600 images, pixel-equivalence through actual
Fold/calibration and fractional sampling, paced four-projector playback with cameras,
tail frame timing/holds, cold-cache IO and cancellation/cleanup. No full-workload
or optical acceptance is inferred from isolated throughput.

<a id="full-image-setup-publication-deadline--2026-10-28"></a>
## Full-image Setup publication deadline — 2026-10-28

Owner screenshot/log for Setup `927c71fd-b869-4a5c-90eb-da15114dc57d`
shows600/600 image validations and8/8 initial uploads, followed by a
32,147,883-byte ReportWorkerOperation receipt failure:4250.584ms elapsed,
4241.152ms remaining budget. Worker preparation publishes the serialized prepared
trial after graphics preparation using the original Setup deadline; coordinator
receipt includes synchronous JSON parsing/model validation before acknowledgement.
This is evidence of final publication exceeding the remaining Setup bound, not a
PNG decode failure or demonstrated GPU exhaustion. Contribution of decoding,
serialization, transport and receiver validation needs profiling; no causal split
or repair is established. Renderer exit and refused interruption/cancel calls leave
cleanup unconfirmed. No new device commands or replay attempted. Preserve V04/E08
validation, original deadlines and truthful cleanup while investigating.

## Linear metadata in selected stimuli folders — 2026-10-28

`stimuli-png-linear-metadata`: owner narrowed Desktop/Alsu/media request to the two
`stimuli` subfolders only. Added explicit linear gAMA1.0 and Rec709/D65 cHRM PNG
metadata to1,200 generated images (600 ALDER,600 POPLAR). Source exemplars80,
root copies20 and six source/document files remain unchanged by hash. Both
generators match the previously reviewed source; all600 ALDER files also match
retained original hashes. Source directories have moved under media, so separate
sibling originals were not presumed still present. No existing colour declarations
conflicted. This artifact operation uses[V04](../docs/architecture/visual_stimulus.md#v04)'s
explicit-metadata precedence; it introduces no runtime policy or default.

[Evidence/manifest](visual-stimulus-evidence-2026-10-28/stimuli-png-metadata/context.md):
all1,200 after-hashes, PNG CRCs and linear metadata pass; every encoded IDAT chunk
is unchanged, and removing the60 inserted bytes reconstructs each original full-file
hash. Four decoded-array comparisons and actual protected-source/float-RGBA
validations with colour_override=None pass. Atomic per-file updates reject concurrent
edits; preflight/reversal manifest retained instead of duplicate12GB image copies.
Initial missing-old-path preflight failed before mutation, then corrected to current
source provenance. Whitespace passes. No runtime/source/dependency changes or broad
suite needed for metadata-only artifact edits. No GUI/runtime Setup/optical test;
existing imported copies outside these subfolders and protocol files were not edited.

## Untagged images default to linear — 2026-10-28

Owner instructed that images should be assumed linear. [V04rev44](../docs/architecture/visual_stimulus.md#v04)
and [E14rev217](../docs/architecture/system-contracts.md#e14) now declare policy25's
fixed linear/full-range Rec.709 D65 RGB fallback for untagged PNG/TIFF. Supported
PNG transfer metadata and explicit overrides retain precedence; unresolved PNG
chromaticity/ICC, unsupported gamma and TIFF declared transfer/primaries/ICC remain
errors instead of receiving a fallback. JPEG/video and glTF colour rules retain
their profiles. No operator option or global rewriting of asset declarations.
Resolved interpretation already retains effective transfer/range/primaries.

ARCH-002 review keeps this in the existing focused decoder, used by retained and
deferred preparation; no new helper/module/dependency/state. glTF passes its own
explicit texture override. Existing manifest/precision/upload owners remain.
Policy/config versions25, allowed key inventory and loader digest align; contracts
updated. No source-image/protocol file edits or live application changes here.

Validation: resource/configuration154 tests and5 subtests pass, then four focused
PNG metadata cases pass after adding chromaticity-only rejection coverage; controller
configuration integration24 pass. New coverage checks8/16-bit PNG/TIFF pixel and
linear-RGBA intensity preservation, PNG transfer/override precedence, unsupported
gamma/chromaticity and TIFF ICC rejection. Actual metamer without its override
decodes linear and produces the same float-RGBA SHA256 as its explicit-linear path.
Scoped Ruff/format, two-source Win32 mypy,792-module boundaries/zero violations and
whitespace pass. Initial run151 passed/three demo-fixture errors from repository-local
output; rerun in writable external output resolves all three without weakening tests.
One test patch context mismatch corrected after reread.
[Dated command/scope evidence](visual-stimulus-evidence-2026-10-28/untagged-linear/context.md).
Local implementation complete; full app restart required for policy25, with native
Setup, combined workload and physical luminance acceptance unverified.

## Image validation CPU capacity — 2026-10-28

**Current600-image revision:** new owner Setup57873edf reports a different import
ID/path and0/600 validation. The saved texture protocol was replaced with600
untagged ALDER assets, so the earlier ten-asset overrides do not cover this revision.
Verified all600 imported/original SHA256 matches and reused the accepted ALDER
linear interpretation under V04rev43. Atomically applied600 per-asset declarations
with backup/concurrent-edit guard; only those fields differ. All600 protected-source
hash/decode/linear conversion/output validations pass in130.6s, peak reservation
1,499,265,784bytes under2GiB, with reservations/handles released. PNG bytes unchanged.
[Full-set evidence](visual-stimulus-evidence-2026-10-28/image-cpu-capacity/full-alder/context.md).
No global default or new runtime/import behavior. Reload/Apply this saved600-image
protocol after full restart for accepted500ms MCU/1050ms Stopped timings. No new
native Setup, GPU allocation or playback acceptance for this600-image revision.

`image-validation-cpu-capacity`: owner Setup2aeec5d1 fails CPU admission at
1,494,464,310/1,073,741,824 bytes, GPU0/4,294,967,296. Supplied texture protocol
references ten3840×2000 PNGs. Existing source/decoder/float-conversion accounting
reserves192bytes/pixel plus protected encoded-read storage, sequentially per image;
it does not retain all ten decoded images for validation. Standalone source
validation reproduces the old rejection at1,494,407,186 bytes before the live
session's additional reservations. Read-only GlobalMemoryStatusEx reports
66,094,223,360 physical bytes total /42,027,282,432 available at inspection;
neither is a full-load guarantee. These initial measurements concerned the earlier
ten-image revision; the current saved protocol now imports600 ALDER images.

[V04rev43](../docs/architecture/visual_stimulus.md#v04)/E14 set the existing CPU
asset ceiling to2GiB, retaining GPU4GiB, all other limits,192bytes/pixel accounting,
source precision, sequential scratch ownership and fail-closed admission. Engineering
operator value only, no fixed policy change/version bump. ARCH-002 chooses the
existing setting rather than decoder changes or relaxed accounting/dependencies.
Owning loader checks both ceilings;15 configuration tests/5 subtests and whitespace
pass. No runtime source edits or unrelated runtime/static suite needed.

[Native source-validation evidence](visual-stimulus-evidence-2026-10-28/image-cpu-capacity/context.md)
now passes all ten through protected hashing, decode, linear float-RGBA conversion
and output validation under2GiB. Maximum source reservation1,494,414,146bytes;
reservations released and protected handles closed. Earlier missing-colour failures
remain in before-linear evidence. Generator/original hashes establish direct
normalized grayscale export; the owner explicitly selected linear interpretation.
V04 records the scoped choice, without a global untagged-media default or claim
of physical luminance calibration.

Initially updated only ten asset overrides in Desktop/Alsu/protocols/
texture-presentation-1hr_protocol.json: linear/full-range/RGB/Rec709 D65/no chroma,
with explicit owner/provenance reason. Backup and applied proposal retained in
evidence. GUI envelope validates; semantic comparison proves no other fields
changed. PNG bytes unchanged. Owner-requested native test now applies this exact
file at controller revision3, with device settings and recording selections retained.
GUI records loading the same protocol; all ten images validate, initial texture
uploads8/8 and prepared-memory finalization complete. Setupa23f5a27 reaches Resolving
outputs but fails on a new MCU PING206.031ms/199.983ms timeout, not image admission
or colour validation. CancelSetupada0a3fc succeeds and snapshot confirms Configuration
with cleanup_confirmed=true. GUI displays the corrected9,000-epoch texture protocol
and regains control. No trial started by this test, automatic retry, deadline change,
optical or combined-playback acceptance. [Native evidence](visual-stimulus-evidence-2026-10-28/image-cpu-capacity/native-setup/context.md).

## Streamed configuration validation — 2026-10-28

`mcu-setup-ping-latency`: actual supplied texture-protocol validation triggered
a454ms cyclic-GC pause while retaining all expanded settings in the controller
process. Semantic validation now obtains duration sources in a bounded ordered
pass, then validates settings as a stream. The existing compiler still materializes
its prepared plan; source ordering, random sampling, condition expansion, epoch
limits, duration resolution and range/writer checks retain their owners under
[V03/V08](../docs/architecture/visual_stimulus.md#v03)/[E07](../docs/architecture/experiment.md#e07).
ARCH-002 review reuses the existing iterator rather than adding a process or GC
policy; the cohesive compiler owner retains semantic validation despite its size
advisory. Local witness delay falls481→33ms and texture validation3.84→1.87s.
47 tests/5 subtests and scoped static checks pass; native serial attribution and
Setup/Cancel remain open. [Runtime assessment](runtime.md#setup-watchdog-and-secondary-renderer-failure--2026-10-28),
[dated evidence](runtime-evidence-2026-10-28/mcu-protocol/context.md).

## Linked Grating orientation investigation — 2026-10-28

**Current review request:** owner asks Grating linking to follow Texture drift,
with multi-direction previews before implementation. Rendered
[cardinal](visual-stimulus-evidence-2026-10-28/linked-grating-orientation/drift-link-cardinal-preview.gif)
and [diagonal](visual-stimulus-evidence-2026-10-28/linked-grating-orientation/drift-link-diagonal-preview.gif)
pages for all eight Bottom orientations,20mm/s and5mm period. They call existing
production linked_rates with unit reference translation and saved calibrated geometry,
then align each grating normal with mapped velocity. Actual planning tank raster and
aspect-preserved flat/local-arrow views are shown. Full coverage and common temporal
phase retained. This is a proposed motion mapping, not deployed local-copy policy33.
Owner review, runtime/contract revision and optical validation remain pending; no
Right-only flip or calibration change has been applied.

**Open Right-only rig mismatch:** owner supplied IMG_1435.MOV and reports coherent
Bottom/Left/Front with Right incoherent. Decoded273 frames/9.13s, inspected1s/6s
frames and reviewed saved profile meshes. Full coverage is visible; no new origin
defect identified. Left/Right local horizontal axes are opposite in the calibrated
geometry, while policy33 deliberately copies the same local wave. A Right-only
horizontal stimulus reflection is the proposed diagnostic, preserving vertical
component, shared phase clock and physical period. This is a hypothesis, not an
optically validated fix. The saved unflipped Right mesh is not proof of the exact
configuration used for the recording. Approximate manually rectified carrier
analysis has high Right residual/camera uncertainty; it does not establish a timing
or speed reversal. Confirm with cardinal/diagonal drift and asymmetric orientation
pattern before choosing a grating-only reflection versus global calibration Flip X.
No production/configuration/device changes belong to this investigation.

The owner approved the [flat four-panel candidate](visual-stimulus-evidence-2026-10-28/linked-grating-orientation/flat-four-projectors-candidate.gif)
and explicitly requested all linked projectors, all random orientations0..315 in
45-degree steps, no origin point and no stimulus-driven uncovered areas.
[V02rev26](../docs/architecture/visual_stimulus.md#v02) and
[G01rev388](../docs/architecture/gui.md#g01) now govern one infinite screen-local
physical wave: common local bar angle, physical period, signed phase drift and
centre phase. Reference/follower stimulus maps are compensated in physical units;
configured masks/valid areas/corrections remain independent. Physical corner
stitching and angular parallelism from arbitrary camera positions are not promised.

Implemented in the shared preview/RenderEngine resolver, with full usable-screen
coverage through the existing coverage extension. Removed the perspective divide,
horizon mask, projection origin, geometry cache and perspective-only shader/evidence
uniforms. Geometry is no longer passed into the shared field/retention operation.
Unlinked Gratings and Texture drift retain their rules. ARCH-002 favours the much
smaller pure affine helper and existing shader path, with no new dependency/state/
process. RenderEngine remains a large assembly owner; this increment only removes
geometry arguments from its existing snapshot/boundary calls. Existing behavior
modules were extended; obsolete projection-specific constraints/tests were removed.
Fixed policy33/digest and both TOMLs agree; saved bounds/seeds/draw ordering remain
unchanged. Full restart/fresh Setup is required before trying the new implementation.

Validation:492 configuration/compiler/resources/rendering/authoring tests and5
subtests pass (70 deselected). A100-epoch seeded random rule samples every requested
angle and checks identical local angle/phase and signed drift on all four screens.
Eight-angle/four-reference/identity-and-sheared-map cases check common physical
phase, translation, eye independence, long50-second periodicity and backward seek.
The existing coverage extension encloses every physical screen corner in all64
angle/reference/map cases.24 standalone native OpenGL cases (eight angles by three
sharpnesses) verify waveform and alpha coverage across the entire framebuffer.
16 evidence-contract cases pass with native permission. Scoped Ruff/13-file format,
ten-source Win32 mypy,796-module boundaries/zero violations and whitespace pass.
The first new diagonal GPU fixtures exceeded3e-6 from raster vertex snapping;
aligned fixture vertices to the pixel grid to isolate waveform evaluation without
loosening the assertion. No runtime-angle restriction was added.

[Implemented four-panel motion](visual-stimulus-evidence-2026-10-28/linked-grating-orientation/flat-four-projectors-implemented.gif)
uses actual PreviewPlan-resolved fields. Its static panel pixels match the approved
candidate exactly;25-frame GIF decoded, quarter-speed playback. The actual runtime
preview's nonconstant field, changed midpoint and exact one-period repeat checks
pass. Saved protocol/calibration and devices were not changed. The prior policy32
rig result was rejected for paired directions and partial coverage; those local
passes were not rig acceptance. Physical validation of policy33 remains in the
[single rig checklist](rig-verification.md#linked-grating-corner-phase).
[Detailed dated evidence](visual-stimulus-evidence-2026-10-28/linked-grating-orientation/context.md).

## Cleanup before Setup catalogue — 2026-10-28

`stimulus-unprepared-catalogue`: owner diagnostics and the retained
[emergency report](emergency-1173345912101600-52617fda-fcea-47bb-b697-b2a6042ae173.json)
show renderer departure after `INVALID_CATALOGUE: first catalogue must be
revision-zero empty`. Reproduction confirms cleanup before renderer Setup forwards
the previous session's catalogue revision into a newly registered session. Revision0
passes; retained revision12 reproduces the exact rejection. The reported serial
watchdog overrun is a plausible initiating failure, not proven causal ordering.

The existing cleanup owner now declares zero for an unprepared session without
retained obligations, and uses zero in its aggregate Cleanup. Retained obligations
reject explicitly. Native stopped/release proof, exact work/generation checks,
original deadline, supervisor validation and immutable replay remain; neither raw
worker evidence nor prior-session revision is rewritten. This implements existing
[E08](../docs/architecture/system-contracts.md#e08)/[E06](../docs/architecture/system-contracts.md#e06).
ARCH-002 review retains the cohesive lifecycle-validation/forwarding owner despite
its size advisory; this focused branch needs no new module, state or dependency.

[Evidence](visual-stimulus-evidence-2026-10-28/unprepared-catalogue/context.md):
173 coordinator/lifecycle/supervisor registration cases pass, one Windows case
excluded; scoped Ruff/format, Win32 mypy and792-module boundaries/zero violations
pass. Sandbox asyncio stalled at socketpair creation; approved loopback-capable
runs completed. No live app restart, native failed-Setup/retry or watchdog repair
claimed. Follow the [rig check](rig-verification.md#unprepared-stimulus-cleanup).

## Schedule and transport ceilings — 2026-10-28

Owner revised the requested schedule ceiling to 50 decimal MB. Current defaults:
`max_prepared_plan_bytes = 50_000_000`, shared RPC cap `67_108_864` bytes (64 MiB),
controller event/central metadata queues `268_435_456` bytes each (256 MiB), GPU
asset ceiling unchanged at4GiB. [V03rev15](../docs/architecture/visual_stimulus.md#v03)
and [E08rev185](../docs/architecture/system-contracts.md#e08) govern; numbers live
only in their owning operator TOMLs. Full application restart is required for the
shared transport cap. No active-process settings were changed. ARCH-002 reuses
existing limits and loader validation; no runtime code, dependency or policy changes.
Updated the owning saved-history test's default substitution to preserve its
1,024-byte rejection scenario, and made the existing read-only capacity probe read
the current transport ceiling rather than hard-code the historical default.

Validation on base revision `e4dd8f2694aa075380fe6711a884fe5894763c6f` plus current
working tree: both owning loaders assert all four limits; the existing20-minute
protocol compiles4,000 epochs/16,000 settings into15,158,567 bytes, with51,950,297
bytes of transport headroom. This uses the probe's fixture identity/seed17 and saved
display, not native Setup. Visual Stimulus configuration/compilation46 tests/5 subtests
pass (`--basetemp=.tmp-schedule-final`). Three focused controller configuration tests
(timing/budgets, Setup reload, bounded saved history) pass with21 deselected
(`--basetemp=.tmp-controller-capacity-final`). Broader combined controller run stalled
after12 progress dots and was interrupted without a summary; no full-suite pass.
Initial direct-loader probe used an unsupported keyword; corrected to
`include_configuration=False` and passes. Scoped test Ruff/format and whitespace pass.
These are serialized-byte ceilings, not memory preallocations or throughput promises;
large-message native publication, live Setup and full-load memory remain unverified
under the [existing rig checklist](rig-verification.md).

## Sparse prepared schedule capacity — 2026-10-28

Historical initial repair; current owner-selected ceilings are recorded above.

Owner's Setup screenshot rejects15,173,120 prepared JSON bytes against8,388,608;
this is serialized CPU schedule size, not sparse pattern pixels or VRAM. The saved
`sparse-noise_20mins_protocol.json` expands to4,000 epochs and16,000 complete layer
settings. Under [V03rev14](../docs/architecture/visual_stimulus.md#v03)/E14, raised
the explicit operator preparation ceiling to16,000,000 bytes, below E08's existing
16MiB transport cap. No runtime limit growth, truncation, stimulus change or policy
version change. ARCH-002 review chose the existing configurable bound over a new
serialization format; no source/dependency/state-owner changes.

[Read-only probe](visual-stimulus-evidence-2026-10-28/prepared-capacity/check.py),
run from repository root with `PYTHONPATH=.` and `.venv/Scripts/python.exe`, uses the
saved display and fixture identity/seed17, not the running Setup identity. Protocol
SHA256 `134a0ad5960be2b5497548073c46c6e444205e89906e7e9403ed629e52872246`:
old bound reproduces rejection at15,158,567 bytes; new bound passes with exact
1,200,000,000,000ns duration and1,618,649 bytes remaining under the transport cap.
This does not verify native publication, GPU allocation or presentation. Initial
probe invocation lacked the test-helper import path; the next expected-rejection
handler used the wrong exception type; both probe-only mistakes were corrected.
Configuration/compiler pytest command (`tests/visual_stimulus/test_configuration.py
tests/visual_stimulus/test_compilation.py -q -m "not windows and not rig"
--basetemp=.tmp-prepared-capacity`) passes46 tests and5 subtests; whitespace passes.
No managed-app/device action. Fresh Setup remains native acceptance under the
[existing rig checklist](rig-verification.md).

Live `nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv`
reports RTX5060Ti16,311MiB total/417MiB used and RTX2080Ti11,264MiB total/26MiB used.
These are a point-in-time reading, not full-load headroom. Owner subsequently selected
4GiB: `max_asset_gpu_bytes = 4_294_967_296` now sets the admission ceiling under
[V04rev40](../docs/architecture/visual_stimulus.md#v04)/E14. No preallocation,
total-process VRAM guarantee or prepared-JSON-limit change is implied. ARCH-002:
reuse the existing setting/loader, with no code, dependencies or policy changes.
Owning loader confirms both ceilings; configuration suite15 tests/5 subtests and
whitespace pass. Live allocation and combined-load acceptance remain unverified.

GUI preview now consumes only the first100 canonical occurrences under
[G01rev375](../docs/architecture/gui.md#g01). The shared expansion traversal is
incremental; backend full-plan bounds/count checks remain enforced. Compiler and
sparse seed checks pass; [current evidence and limitations](runtime.md#preview-first100-epochs--2026-10-28).

## Epoch-owned sparse timing — 2026-10-28

[V04rev38](../docs/architecture/visual_stimulus.md#v04) implements one new deterministic
pattern per repeated epoch for new GUI layers. Shared expansion resolves occurrence
seeds; one pattern remains resident for the whole resolved epoch. Preview and runtime
use the existing generator and request stream. Explicit legacy timed sequences retain
their behavior outside an epoch-editor commit. Canonical source/prepared schemas were
regenerated; no worker, transport, pacing or resource-ownership changes were needed.
Nested repetitions, seed wraparound, request timing, distinct cells, repeatability,
legacy sequence behavior and invalid hidden counts have local coverage:162 resource/
compiler cases and4 sparse lifecycle cases pass. Broad full-lifecycle execution was
interrupted without a summary and is not a pass.
[Commands/results and limits](runtime-evidence-2026-10-28/epoch-timing/context.md).
Prior native 200-pattern sequence measurements below do not verify the new epoch-based
schedule; native/optical/full-load checks remain [pending](rig-verification.md#sparse-noise-presentation).

## Native rig validation — 2026-10-28

Standalone rig CPU generation measurement (`sparse-noise-generation-timing`, V04):
the saved successful 60-second trial's exact recipes/grids were passed to the existing
`pattern_rgba`, with 10 warmups per screen and five interleaved passes of all 200
indices (1,000 timed calls per screen). All 4,000 hashes match recorded trial evidence.
Mean/median/p95/max milliseconds: Front (47×42) 0.812/0.800/0.845/1.610;
Left (64×41) 1.074/1.061/1.117/1.892; Right (64×42) 1.104/1.087/1.151/1.982;
Bottom (64×45) 1.179/1.162/1.230/2.080. Cells are 2 mm, spacing 4 mm,
activation probability 0.6 and seed 20261028. Mean generation summed across four
screens is 4.169 ms. These are Windows rig wall-clock CPU function timings under
ambient load, excluding helper startup, IPC, hashing, row flipping, GPU upload,
rendering and optical latency; they do not attribute the presentation gaps or close
combined-load/prefill acceptance. No production/configuration change. Raw samples,
source hashes, platform, revision and method: [results](visual-stimulus-evidence-2026-10-28/generation-timing/results.json);
reproduce with `.venv/Scripts/python.exe reports/visual-stimulus-evidence-2026-10-28/generation-timing/measure.py`.

Testing commit `e4dd8f2694aa075380fe6711a884fe5894763c6f` on Python 3.11.15,
Windows, NVIDIA 617.14; standalone GL identifies the RTX 5060 Ti.
Evidence: [dated rig tests](visual-stimulus-evidence-2026-10-28/rig-tests/).
Under [V04](../docs/architecture/visual_stimulus.md#v04), the four-output
2 mm/300 ms/200-pattern sparse test passes Setup but fails during PrepareTrial,
before Running: `raw frame writes require a contiguous writable pinned buffer`.
`SparseNoiseProcess.send` forwards immutable `encode_job` bytes to the native
`OverlappedPipe.write`, which rejects read-only buffers. CREDIT uses the same
path. This is an observed Windows integration defect, not a throughput result.
The incident window expired; automatic application shutdown followed. The launcher
receipt confirms all owned processes absent; all eleven saved settings files match
their pre-test bytes. API restoration could not run after controller departure.

Owner authorized repair: `SparseNoiseProcess.send` now supplies a writable memoryview
backed by a bytearray to the existing synchronous native writer, preserving its deadline
and pending-I/O ownership. ARCH-002 review: the focused 190-line helper needs no new
abstraction, dependency or policy change. An owning lifecycle test sends JOB and two
CREDIT messages through a real Windows pipe. Post-fix: 720 Visual Stimulus/native-pipe
tests and three subtests pass; Ruff/format, Win32 mypy (184 files) and boundaries pass.
The initial native-pipe regression attempt was sandbox-denied (WinError5); the native
access run passes.

The repaired 60-second four-output sparse trial completes with exact scheduled cutoff,
confirmed cleanup and exact runtime/saved-settings restoration. All 200 patterns on
each of four surfaces appear: 800 regenerated hashes match, 14,176 selections are
`current`, none are residency/background holds. All 3,544 recorded frames fully decode
and match encoder accounting, with zero capacity drops, duplicates or unresolved
submissions. Live helper/encoder identities are retained; encoding selects GPU1
(RTX2080Ti) and rendering uses RTX5060Ti. Start-command to scheduled T is1.407s
(includes preparation/encoder/scheduling, not isolated helper-prefill timing).
See [assessment](visual-stimulus-evidence-2026-10-28/rig-tests/sparse-fixed-run/assessment.json)
and [decode/accounting](visual-stimulus-evidence-2026-10-28/rig-tests/sparse-encoding.json).

The initial timing result remains unresolved: saved all-output VSync was preserved; evaluation median
16.666ms, mean59.052Hz, maximum298.802ms at0.734s, and maximum166.708ms after the
first second (37.665s). No optical flip or steady60Hz guarantee follows. The separate
initial grating probe incorrectly extended an angular review fixture to all four
planes: runtime rejected a ray behind the observer at5s; subsequent Stopped evidence
was rejected and shutdown followed. Retain that harness limitation and cleanup failure
as separate evidence, not a grating shader regression. Normal non-destructive startup
recovery succeeded, preserving all scientific files. The corrected physical-coordinate
comparison (5s blank, 20s four-screen10mm/37-degree grating drifting10mm/s, 35s blank)
completes and restores configuration: 3,602 fully decoded/count-matching frames,
zero recording drops/unresolved submissions, median16.651ms and maximum20.726ms
evaluation gaps. This single comparison does not establish causation for sparse gaps.

Focused gap investigation retained [stage traces and methods](visual-stimulus-evidence-2026-10-28/gap-diagnosis/context.md).
The old startup intervals mostly span swap/completion waits; the later event spends
152.93ms before its first swap. No generator starvation is recorded. A temporary
buffered stage/GL/GC trace did not reproduce either large event:60s/3599 frames,
800 matching hashes, no holds, max34.269ms, mean59.975Hz. Before Ready, helper prepare
takes916.718ms including744.964ms prefill; max upload0.660ms, selection1.767ms,
GC1.289ms, scene render9.803ms and swap23.521ms. These nested spans are not additive.
No causal timing repair is established; shader warm-up or OS/driver scheduling are
unverified hypotheses. Similar large startup gaps exist in historical blank scenes.

After removing instrumentation and restarting normally, the corrected180s fixture
completes with10,799 fully decoded/count-matching frames, all2,400 regenerated hashes
matching,43,196 current selections, no holds/drops/duplicates/unresolved submissions.
Evaluation median16.667ms, mean59.993Hz, maximum33.466ms; per-output return maximum
33.758ms. All11 saved files and runtime configuration restore exactly. A first extended
fixture accidentally retained a60s epoch; its exact-duration guard aborted and restored
cleanly before the corrected run. The diagnostic collector initially requested metrics
from an empty launcher stderr and reported missing metrics; recording-only collection
passes. Five focused native sparse lifecycle tests, scoped Ruff/format and791-module
boundaries pass. Temporary hooks are removed; the writable-buffer repair remains the
only production sparse change. The167–299ms events remain unreproduced/unattributed,
not fixed; optical and combined-load acceptance remain open.

Sparse Abort after5s completes in238.443ms, returns to Configuration with cleanup
confirmed, and leaves no helper/encoder process. Its303 frames fully decode and match
accounting; all68 first-display hashes match, no holds, max evaluation gap20.789ms.
The test harness incorrectly awaited an Ended snapshot after Abort had already reset
to Configuration; it exits1 on that bounded wait, then its finally block restores the
original runtime configuration exactly. The session journal, decoded evidence and
authenticated snapshot establish interruption/closure independently of that harness
exit. Final verification: Configuration, cleanup confirmed, no prompts, no helper or
encoder, all eleven saved settings files unchanged. The managed app remains open.
See [final verification](visual-stimulus-evidence-2026-10-28/rig-tests/final-verification.json).

Windows checks: 1,012 Visual Stimulus/generation/supervisor tests and three subtests
pass, including native GL; focused GUI checks: 32 pass and two fail on obsolete
`Texture` labels (`Texture drift` is current), reproducing the recorded failures.
42 contract tests, 14 schema checks and backend boundaries pass. The initial sandbox
attempt timed out in asyncio socketpair creation; the successful run used native
access. The later instrumented prefill measurement is bounded to this rig fixture;
optical and combined camera/Tracking load remain unverified.

## Rendering and presentation review — 2026-10-28

Source review of `rendering/engine.py`, `native.py`, `scene.py`, `upload.py` and the
GL-owner loop against [V10](../docs/architecture/visual_stimulus.md#v10),
[V20](../docs/architecture/visual_stimulus.md#v20) and V04's color pipeline. No runtime or
rig measurement backs any item.

- Applied (owner-approved, local checks only): `render_tick` resumes the epoch search at
  `TrialState.epoch_index` instead of scanning from zero; per-tick inline imports moved to
  module level; `ModernGLPort.present` calls `context.finish()` after each swap whose
  interval is above zero, so `swap_return_ns` follows the paced flip rather than driver
  queue depth. Immediate outputs are unchanged. The fence can lengthen the GL thread's
  per-frame blocking on VSync outputs; its timing effect needs the rig
  ([checklist](rig-verification.md)).
- Open, not implemented: evaluate frame state at the predicted flip time instead of loop
  CPU time (needs a V10/V13 evidence-meaning decision); merge the warp and LUT/marker
  passes and skip the screen copy when no capture/preview is due.
- Deferred by owner: video frames are converted uint8→float32 with a NumPy EOTF and
  uploaded as RGBA32F on the GL thread once per output (`scene.py` video loop); several
  VSync pulse outputs swap sequentially and may wait on unsynchronized vblanks; `bt709`
  decoding inverts the camera OETF rather than a display EOTF such as BT.1886.
- Validation: 647 Visual Stimulus tests pass, 3 fail at HEAD for the missing PyOpenGL
  module; ruff, format, Windows-target mypy, boundary check and `git diff --check` pass.

## Protocol Media families — 2026-10-27

`protocol-media-families` implements the owner's two protocol types and six per-epoch,
per-projector/layer choices under [G01](../docs/architecture/gui.md#g01),
[V02](../docs/architecture/visual_stimulus.md#v02),
[V04](../docs/architecture/visual_stimulus.md#v04) and
[V07](../docs/architecture/visual_stimulus.md#v07). Sparse noise and new Grating author
parameters directly without mandatory recipe files. Sparse preparation retains its
seeded definition/resources and the unchanged epoch clock; linked Gratings share one
reference-owned pattern/phase via the owner-selected Bottom unfolding. Unlinked
Gratings and Texture drift remain independent under their respective rules.

32 focused GUI cases, 299 backend cases plus 3 subtests, and 3 synthetic native
waveform cases pass. Scoped Ruff/format (49 files), Win32 mypy (44 sources), 14 schemas and
785-module boundaries/zero violations pass. Earlier broad xdist runs were interrupted
with worker crashes/no usable completion; the monitoring chat owns combined serial
suite results. [Evidence, commands, failures and limits](runtime-evidence-2026-10-27/protocol-media-families/context.md).
No managed-app restart or physical/full-load acceptance. Use the
[existing rig checks](rig-verification.md#protocol-category-previews).

The required marked-Grating occurrence assignment fix is bounded to the authorized
Grating interface. Source review also observed the broader non-Grating assignment
path missing from renderer state; `runtime-general-epoch-assignments` remains deferred
pending separate authorization. Legacy distinct Media/Drift schedules fail atomic
migration with an explicit separate-import message; they are never silently combined.

`grating-profile-policy-reconciliation` is complete (2026-10-28):
[V04](../docs/architecture/visual_stimulus.md#v04) revision39 and
[E14](../docs/architecture/system-contracts.md#e14) bind the already-supported
`cephvr_grating_json_v1` image profile in policy22, matching both TOML versions
and the loader digest. No rendering behavior or operator setting changed.
The owning configuration regression compares the policy inventory with the Asset
model and both published program/prepared-trial schemas, and loads the strict pair.
ARCH-002 review: reuse the existing loader/digest and owning test module; no new
abstraction, dependency or oversized production module extension.

Validation on the uncommitted tree atop e4dd8f2694aa075380fe6711a884fe5894763c6f:
configuration/compilation/shared-config tests pass55 plus5 subtests; grating resource
tests pass9; controller installed-policy edit/Setup integration passes1 with loopback
permission. Scoped Ruff/format, Win32 mypy,791-module boundaries (zero violations;
unrelated size advisories retained) and whitespace pass. Commands use the repository
Python: `-m pytest tests/visual_stimulus/test_configuration.py tests/visual_stimulus/test_compilation.py tests/shared/test_config.py -q -m "not windows and not rig"`,
`-m pytest tests/visual_stimulus/test_resources.py -q -k grating -m "not windows and not rig"`,
and `-m pytest tests/controller/test_configuration_transactions.py -q -k installed_visual_stimulus_policy --timeout=20`.
Initial resource attempts hit the external-assets fixture requirement and sandbox temp
allocation; a writable external visualization test directory passes. Initial controller
attempt was interrupted; bounded retry timed out in asyncio socketpair creation;
the permission-enabled retry passes. Initial formatting found CRLF introduced by editing;
repository formatting restored. No app restart or physical/optical acceptance performed.

## Combined-tree verification — 2026-10-27

After both chats finished, the complete local owner suite passes620 tests plus3
subtests,55 deselected; affected-owner lint/format/Win32 mypy and14 schemas pass.
The broader GUI run remains incomplete, separately recorded in the
[runtime report](runtime.md#combined-tree-verification--2026-10-27) and
[reconciliation evidence](runtime-evidence-2026-10-27/repo-reconciliation/context.md).

The monitoring chat corrected the display-replacement test's fake native boundary
to isolate `hide_output_shell_entry` beside the existing window mocks. The broad
texture-field run's cleanup failure came from this missing fixture operation;
runtime ownership and release assertions are unchanged. All31 tests in
`tests/visual_stimulus/test_display_calibration_rendering.py` pass with
`-q -m "not windows and not rig" --basetemp=.pytest-monitor-display --timeout=30`;
scoped Ruff/check/format pass. This is local fixture validation under
[ARCH-002](../architecture.md#arch-002), not native acceptance under
[E15](../docs/architecture/system-contracts.md#e15).

## Grating stimulus — 2026-10-27

Earlier asset-backed verification (before the current Media increment):8 Grating GUI and5 Grating compiler/resource cases pass;
Ruff/check/format33 files, Windows-target mypy30 sources,14 schemas and whitespace
pass. Boundary review reports780 modules and zero violations, with size advisories.

`grating-stimulus` implements [V04](../docs/architecture/visual_stimulus.md#v04)'s
specialized asset interpretation and [V08](../docs/architecture/visual_stimulus.md#v08)
Orientation/Asset sampling under [G01](../docs/architecture/gui.md#g01). The shared
interpreter ignores the design angle in memory, retains appearance/period and source
bytes, and handles legacy periodic rasters plus concurrent extent-independent fields.
Absolute rotation assignments and Cartesian drift keep bars normal to movement while
retaining compatible position/phase. Invalid asset-backed custom/linked/feedback/misaligned motion
and incompatible candidate profiles reject explicitly. Candidate periods stay paired
with the chosen assets, without extra source epochs.

156 compiler/configuration/resource cases plus3 subtests and69 GUI cases pass.
Protected eager/deferred and legacy/current recipe checks agree; stationary angle,
all four projector frames, numeric variation and save/reload are covered. Source and
prepared schemas come from their canonical models. ARCH-002 uses focused helpers
and existing source protection/residency/transition owners without new dependencies
or processes; model/form/preparation size advisories remain cohesive assembly owners.
[Raw evidence and exclusions](runtime-evidence-2026-10-27/grating-stimulus/context.md)
retain the obsolete concurrent category tests and repaired UTF-8 assertion damage.
No actual projector/native full-load acceptance; the [rig checklist](rig-verification.md#protocol-category-previews)
remains authoritative for that work.

## Photodiode mode selector — 2026-10-27

`photodiode-mode-selector` implements the owner-confirmed two modes under
[V22](../docs/architecture/visual_stimulus.md#v22) and
[G01](../docs/architecture/gui.md#g01). Devices/Projectors/Sync offers60-frame
landmarks (existing HHHLLL landmark plus alternation) and Every frame (plain bright/
dark alternation). Absent saved mode defaults to landmarks. Projector files,
runtime/prepared profiles, trial evidence's intended levels and both placement
paths retain the selection. Mode edits are locked during active placement; live
rectangle edits preserve its submission index. Policy version20 declares supported
modes; canonical schemas and loader digest are aligned under E14.

ARCH-002 review reuses the existing focused pattern/model/file owners with no
new dependency, counter, process or timing loop. Large projectors.py remains GUI
assembly: only three explicit field handoffs added; engine.py remains the trial
render-group owner with sequence evaluation delegated to the existing pattern
helper. No separable responsibility is added to either size-advisory file.

Final focused checks:33 pass,1233 deselected, covering saved/legacy/invalid modes,
runtime roundtrip and disabled placement retention, trial second-frame distinction,
60-frame vectors and two fake-GL placement lifetimes through65 submissions and
rectangle updates. Broader rendering/configuration checks:144 pass,44 deselected,
3 subtests pass. Ruff/check/format17 files, Windows-target mypy14 sources,
14 canonical schemas and780-module boundary checks pass (zero violations; existing
size advisories). Initial sandbox temp-directory errors recovered using workspace
basetemp. Initial type errors were corrected. Earlier broad failures in concurrent
media-category/image-schedule work no longer reproduce; final broad suite passes.
Schema drift from concurrent model changes was regenerated and rechecked.
[Commands, raw results and source provenance](runtime-evidence-2026-10-27/photodiode-mode/context.txt).

No managed-app restart, native UI visual inspection, physical detector measurement
or full-load acceptance was performed. Pending optical verification stays in the
[single rig checklist](rig-verification.md#photodiode-mode-selector).

## Bottom linked translation direction - 2026-10-27

`bottom-linked-translation-direction` is repaired per owner instruction under
[G01 revision365](../docs/architecture/gui.md#g01) and
[V02](../docs/architecture/visual_stimulus.md#v02). Planning PreviewRig and native
RigStimulusPreview now undo only the Bottom portrait quarter-turn, removing the
extra surface-X reflection that reversed front/back motion relative to linked
walls. Physical projector calibration, saved output flips and source/follower
motion rates are unchanged. ARCH-002 review uses the existing small placement
owners and owning tests; no new state, dependencies or abstractions are required.

Updated pixel-placement expectations reproduce two Bottom-X failures before the
fix and pass all16 cases afterward, including both axes and saved flips. Linked
preview state/replay coverage now includes direct layer translation alongside phase
drift and spin:19 focused GUI cases pass. Native offscreen GPU quadrant/crop/source
immutability checks pass4 cases;124 platform-independent rendering cases pass.
Scoped Ruff/check/format and Win32 mypy2 sources pass;777-module boundaries have
zero violations (existing unrelated size advisories). Local fix complete; normal
relaunch is needed for the running app. Live preview and physical projection were
not exercised. [Validation scope and commands](runtime-evidence-2026-10-27/bottom-preview-direction/validation.txt).

## Asset preview after Save - 2026-10-27

`asset-preview-after-save` repairs post-save design ownership under
[G01](../docs/architecture/gui.md#g01). save_design returns a normalized copy;
the visible property callbacks previously retained the old nested dictionaries.
Subsequent edits changed visible controls without updating the authoritative draft,
so preview generation and later saves could retain earlier values. This affects
textures and arena geometry; historical files are not automatically repaired.

After successful Save, the existing rebuild operation reconnects every property
control to the current document and schedules preview regeneration using the saved
path. Existing cancellation/stale-result rejection is preserved. ARCH-002 reuses
that operation and the existing owning behavior tests, adding no dependency, state
or helper. No policy change or further architecture revision is needed.

Before the fix both new regression cases fail: entering80 after a save leaves
texture period12 or arena width500 in the draft. After the fix82 authoring tests
pass/5 deselect, including real texture-pixel changes, subsequent saved JSON values,
history/current-document updates and continued editing after a second save.
Scoped Ruff/format and Windows-target mypy pass;773-module boundaries have zero
violations and existing unrelated size advisories. [Commands and evidence](runtime-evidence-2026-10-27/asset-preview-after-save/validation.txt).
Managed app not restarted; native interaction/physical/full-load checks remain
unverified. Recheck saved design values affected by edits made after earlier saves.

## Asset Save As - 2026-10-27

`asset-save-as` implements the owner's [G01 revision362](../docs/architecture/gui.md#g01)
request: every Generate assets Save action opens Save As, prefilled with the last
path or the existing new-design default. The shared action is labeled Save as;
Ctrl+S and texture export use the same handler. Cancellation preserves saved files,
path and draft; explicitly choosing the same destination retains Qt's standard
overwrite confirmation. Image dependency rebasing and atomic writing remain owned
by the existing save_design operation. ARCH-002 removes the path-dependent dialog
bypass, with no new state, dependency or helper; existing window/test owners suffice.

Scoped Ruff/format and Windows-target mypy pass;773-module boundaries report zero
violations and existing unrelated size advisories.
[Commands and evidence](runtime-evidence-2026-10-27/asset-save-as/validation.txt).
80 authoring tests pass,5 native/rig cases deselected, with texture/arena regression
coverage for first save, second destination, prior-file byte preservation and cancelled
third save. The initial regression draft used an invalid top-level seed and blocked
in the warning dialog; interrupted and corrected to valid editable fields with
unexpected warnings failing the test. Managed app not restarted; native file-dialog
interaction and physical/full-load acceptance remain unverified.

## Asset variation rules — 2026-10-27

`protocol-asset-variation` implements [V08](../docs/architecture/visual_stimulus.md#v08)
Asset rules through the existing expansion path, under [G01](../docs/architecture/gui.md#g01)
folder authoring. All candidate references/families are checked using the canonical
source validator; sampled settings retain normal validation. Numeric sampler golden
values and legacy untagged declarations remain compatible. Source/prepared schemas
were regenerated from the owning models;14-schema drift check passes.

38 compiler/configuration tests (plus3 subtests) pass, including choice reproducibility,
all-candidate family rejection, missing/duplicate identities and bounded expansion.
35 GUI checks and2 final geometry checks pass. Ruff/format13 files, Windows-target
mypy11 sources and773-module boundaries pass/zero violations. ARCH-002 reuses the
existing resolver/reference loop; program_model.py remains the cohesive canonical
reference owner despite its size advisory. No dependency or rendering-loop sampling.
[Commands/provenance/raw results](runtime-evidence-2026-10-27/protocol-asset-variation/context.md).
Tests establish source/editor/compiler behavior, not actual file decoding or physical
presentation; use the existing [rig checklist](rig-verification.md#protocol-category-previews).

## Missing Fold asset declarations - 2026-10-27

`pre-ready-camera-cleanup`: the owner's WinError3 refers to an absent imported PNG.
Read-only inspection of saved `config/last_configuration.json` finds five absent
asset declarations, all unused by the trial sequence. Its four active image layers
reference the existing root `CephVR_Fold_Test_Bottom_Below.png`. Setup still validates
all declared assets; no fallback or source substitution was introduced under V03/V11.
The original cause of the stale declarations/deleted import directories is unproven.

A [corrected protocol copy](runtime-evidence-2026-10-27/pre-ready-cleanup/fold-program-repaired.json)
removes only those five missing unused declarations; all remaining files exist,
program parsing passes, and every non-assets field is unchanged. This is an offline
artifact, not a repaired running configuration or a native Setup pass.
[Source and assessment](runtime-evidence-2026-10-27/pre-ready-cleanup/asset-assessment.json).
The separate camera cleanup admission defect and validation are recorded in
[Acquisition](acquisition.md#pre-ready-camera-cleanup---2026-10-27).

## Texture independent extent — 2026-10-27

`texture-independent-extent` is locally implemented under
[G01](../docs/architecture/gui.md#g01), [V04](../docs/architecture/visual_stimulus.md#v04)
and [V14/V15](../docs/architecture/visual_stimulus.md#v15). New procedural files are
version1 `texture_field` JSON recipes: physical appearance and unsigned64-bit seed,
with no raster resolution, saved extent, projector identity or repeat tile. The
[authoring contract](../contracts/visual_stimulus/stimulus-authoring.md) owns the
representation, deterministic field interpretation and compatibility limits.

The former100mm raster repeat caused diagonal grating boundaries. The shared
physical-field sampler now serves authoring and Protocol inspection; prepared GL
shaders evaluate the field directly in local millimetres through each projector's
independent calibrated X/Y surface mapping. Period, angle, dot diameter and bar
width are independent of window dimensions and native resolution. Seeded overlap
is stable; random-dot density and filtered-noise black fraction are statistical.
Physical extents and retained phase are captured per mapping in shader evidence,
avoiding one output overwriting another output's coordinate inputs.

Protected preparation fingerprints unchanged source bytes, retains a validated
recipe and bounded1-pixel residency sentinel, and compiles output-owned shaders
before playback. The sentinel is never the displayed pattern. Existing actual-asset
selection, motion, deadlines and partial-allocation/closure owners remain in use.
Unknown versions/parameters, invalid work bounds and unsupported placement/color
interpretations reject. Legacy designs loaded directly retain their existing raster
interpretation; opening/saving compatible designs in the editor emits the new field.
Existing image files remain finite images. Static arena export bakes each physical
surface once with clamped sampling and correct glTF Y orientation; geometry-cache
entries are preserved. The authoring viewport now follows the runtime's glTF origin.

ARCH-002 review keeps field mathematics and shader generation in focused modules,
with no dependency, service or second renderer. `scene_resources.py` and `prepare.py`
retain their cohesive resource-allocation/preparation orchestration despite size
advisories; field algorithms are outside those owners. Existing owning behavior
modules cover the changes; no per-fix test module was introduced.

Final checks:272 resource/render/configuration cases plus3 subtests,20 authenticated
communication cases,95 authoring cases,31 selected GUI cases and39 native offscreen
GL cases pass. Native coverage includes all four screen identities, unequal X/Y
pitch, protected/deferred loading, cropping, phase conversion, source-image
regressions and field sampling beyond100mm. CPU checks cover exact10mm grating
period/45° orientation, overlap identity, statistical noise/dots, seeds and saved
byte independence. Ruff/check/format26 files, Win32 mypy21 sources and785-module
boundaries pass with zero violations; global whitespace check passes. Commands,
raw results and source hashes are in the [dated evidence](runtime-evidence-2026-10-27/texture-field/context.md).

The earlier broad snapshot has602 backend passes and two failures: a Grating
asset-list expectation during concurrent media-family migration, and a display
cleanup receipt assertion. Its GUI selection has35 passes/eight failures in the
concurrent Grating control layout. Those failures remain visible in raw evidence;
they are not field-validation passes and are tracked by the existing media-family
and projector-shell tasks. A combined authoring/GUI run crashed in theme fixture
setup; separate final suites pass. Sandbox asyncio stalled creating its loopback
socket pair; permitted loopback reruns pass without changing assertions.

Local implementation is complete; the managed application was not restarted.
Actual projector measurements, optics, mixed-DPI presentation and full-load timing
remain in the [single rig checklist](rig-verification.md#stimulus-authoring).
[Earlier control-removal evidence](runtime-evidence-2026-10-27/no-cycle-fit/validation.json)
applies to the superseded finite-tile authoring path.

## Preview cleanup — 2026-10-27

`asset-preview-cleanup` implements [G01 revision 354](../docs/architecture/gui.md#g01):
removed the preview footer caption, Cancel generation action/button and routine
Generating/Preview ready messages. Errors and Save feedback remain visible;
automatic cancellation and stale-result rejection remain intact. Source review
confirmed texture arrays and arena mesh/compiled bytes already stay in memory;
no preview-file writing path required removal. Save remains the editor's file
publication action. Existing explicit headless/export APIs are unchanged.

ARCH-002 removes unused UI wiring/caption calculation in the focused layout and
window owners, reusing the worker and existing tests; no dependencies or state
owners added.76 authoring tests pass,2 native/rig cases deselected. New texture/arena
checks reject Python file writes during preview, verify the asset folder stays
empty and confirm Save creates a nonempty design file. Scoped Ruff/format, two-source
Windows-target mypy and772-module boundaries/zero violations pass. Existing size
advisories concern unchanged modules. Evidence: [validation](runtime-evidence-2026-10-27/preview-cleanup/validation.json).
No running-app restart/native or physical acceptance performed; existing
[authoring rig checks](rig-verification.md#stimulus-authoring) remain pending.
Concurrent extent/parameter work preserved.

## Fixed asset tile and phase — 2026-10-27

`asset-fixed-tile` implements [G01 revision 352](../docs/architecture/gui.md#g01):
all selectable texture patterns normalize to100 × 100 mm; grating phase normalizes
to zero. Both fields are hidden, including on imported designs. Open/preview/Save
share normalization; disk inputs change only on Save. Preserved the concurrent
Grating-only selector refinement: saved-only legacy bars retain width-derived tiles.
Sparse-noise sample extents and Protocol screen-grid resolution remain unchanged.

ARCH-002 keeps the shared size constant and normalization in the existing focused
texture authoring module, reuses the property form and owning tests, and removes
conditional Open normalization. No backend algorithm or dependency changes.
72 authoring tests pass,2 platform cases skip; coverage exercises every selectable
texture's Open/Save/preview, fixed fields, related derived scales, control absence,
and preserved legacy bar width. Ruff/format16 files, Windows-target mypy14 sources
and772-module boundaries/zero violations pass; existing size advisories unchanged.
Evidence: [validation](runtime-evidence-2026-10-27/fixed-tile/validation.json).
No app restart or physical projection; [authoring rig checks](rig-verification.md#stimulus-authoring)
remain pending. Finite raster resolution and existing tile repetition behavior
still apply; this does not certify optical scale or seamless arbitrary gratings.

## Bar authoring controls — 2026-10-27

`asset-bars-controls` implements [G01 revision 349](../docs/architecture/gui.md#g01):
horizontal/vertical bars expose shared bar width, blur and two colors; all asset
RGB(A) channels share one row. Authoring resolves a 512-pixel, one-period square tile
with equal color widths. Saved backend dimensions preserve exact period 2 × width;
there is no separate spacing, tile-size or resolution control. Opening legacy bars
in the editor adopts their line width for both colors; disk files change only on Save.
Direct runtime interpretation remains unchanged. See the [contract](../contracts/visual_stimulus/stimulus-authoring.md).

ARCH-002 review reused focused authoring normalization, existing backend rasterizer,
property-form layout and owning test modules; no dependency or backend algorithm
change. Existing source size advisories concern unchanged backend responsibilities.
[Validation evidence](runtime-evidence-2026-10-27/asset-bars/validation.json):
60 authoring tests pass,2 platform tests skip; tests verify equal pixel widths at
multiple physical sizes, blur, saved backend/preview equality, round trips, invalid
width rejection and RGB row/control editing. Ruff/format, Windows-target mypy14
sources and772-module boundaries/zero violations pass. No running GUI restart or
physical projection performed; existing [authoring rig checks](rig-verification.md#stimulus-authoring)
remain pending. Initial search used an unsupported Windows path glob and was retried
against the directory; no file changes resulted from that failed search.

## External texture/media selection — 2026-10-27

Compact texture picker correction (`texture-picker-empty-row`,2026-10-27): the
reported Gaussian selection error reproduces when the file control is empty while
its preset asset still has a placeholder path. The recipe picker called candidate
validation before replacing that old field. It now excludes only the asset being
replaced from old-field validation and commits the already resolved file through
existing epoch-local selection; other invalid edits still prevent the commit.
G01's external-selection and atomic-edit rules are unchanged. ARCH-002 review kept
the four-line change in the existing form commit responsibility; the large owning
widget retains its existing cohesive binding/commit role, with no new dependency.

Before fix:two checker/Gaussian regression cases reproduce Choose an asset. After:
16 focused GUI cases pass, including rejected invalid-motion preservation. All eight
actual Desktop/Pedro Gaussian recipe files select/apply through an offscreen compact
form, with imported copies matching and originals unchanged. Scoped Ruff/format,
Windows-target mypy1 source and773-module boundaries/zero violations pass.
[Validation](runtime-evidence-2026-10-27/texture-picker/validation.json) and
[actual-file evidence](runtime-evidence-2026-10-27/texture-picker/actual-gaussian-files.json)
retain commands/provenance. Running GUI not restarted; native file-dialog interaction
and physical presentation are not claimed by the offscreen checks.

`external-stimulus-selection` implements [G01 revision 348](../docs/architecture/gui.md#g01)
while retaining [E07](../docs/architecture/experiment.md#e07) root-relative saved
references. Browse, pasted replacements, batch edits and preset insertion share the
existing resolver. External supported files are copied into unique `import-*`
folders inside Assets; in-root files stay in place. Image recipes retain their
validated relative image dependency. Originals and existing assets are untouched;
failed copies remove their partial import. Successful imports remain library assets,
including after later draft cancellation. Selecting again creates a separate copy.
An existing writable Assets folder is still required. No runtime/schema change.

ARCH-002 review: keep import handling in the small owning resolver and reuse the
existing recipe dependency validator, standard-library copying and owning GUI test
module; no new dependency, worker or runtime back-reference. Existing backend size
advisories concern unchanged modules; 772-module boundary check has zero violations.
16 focused offscreen GUI checks and 3 recipe-preparation regressions pass, including
external texture selection, saved-program round trip and preview after removing the
original. Scoped Ruff/check/format, one-source Windows-target mypy and whitespace
checks pass. Early demo fixture placement inside the repository and sandbox Temp
permissions failed; final GUI run used the authorized external visualization folder.
[Evidence](runtime-evidence-2026-10-27/external-stimulus/validation.json) records scope.
Running GUI was not restarted; native picker/projector/full-load checks were not run.

## Sparse spacing and activation — 2026-10-27

`sparse-spacing-probability` implements [V04 revision 29](../docs/architecture/visual_stimulus.md#v04)
and the [v2 recipe contract](../contracts/visual_stimulus/sparse-noise.md). Asset
Generator, previews, CLI preparation and Protocol import share a new seeded eligible
layout per pattern, center-to-center minimum distance in mm, independent activation
probability and equal black/white polarity. Probability changes preserve layout;
actual active counts are retained per pattern. Old density recipes fail explicitly;
already generated image programs remain usable. Defaults are 10 mm distance and
0.5 activation for 5 mm cells. Spacing zero allows all cells; probability endpoints
produce blank/all-eligible patterns. Maximal greedy layouts may have spatial bias;
finite sequences do not guarantee coverage or distinct patterns.

ARCH-002 review retained the focused generator and existing property controls;
standard-library RNG/spatial buckets need no dependency, state owner or process.
All three preparation callers share the conservative 512-byte-per-cell scratch
admission estimate and cancellation callback. Existing oversized GUI/resource test
modules remain their owning behavior modules; no new test module was introduced.

Validation: 143 authoring/resource tests passed, 2 native/rig cases deselected;
5 focused Protocol GUI tests passed. Ruff, format, Windows-target mypy (19 sources),
14-schema drift checks and 772-module boundary checks (zero violations) passed.
Evidence: [validation](runtime-evidence-2026-10-27/sparse-spacing/validation.json).
Coverage includes separation/maximality, per-pattern variation, probability endpoints,
nested activation, polarity stability, deterministic replay, cancellation, asset
round trips and decimal editor controls. Early strict-JSON parsing and stale golden
failures were corrected before passing; formatting was reapplied after edits.
No running-app restart, physical projector or full-load timing acceptance occurred;
these remain in the [rig checklist](rig-verification.md#sparse-noise-presentation).

## Projector shell icons - 2026-10-27

Current correction (2026-10-28), `projector-window-visibility`: the owner reports
partial hiding, blank taskbar thumbnails and lingering entries, and authorizes
normal visible windows. [G01rev373](../docs/architecture/gui.md#g01) now keeps normal
named GLFW output entries. Removed the hide/style/show sequence and its unused
TOOLWINDOW option from the camera-caption helper. Output titles/icons are no longer
cleared; creation, recreation and native destruction remain with the renderer.
This removes the shell workaround; the screenshot alone does not establish whether
the lingering entries represent live windows or stale Explorer thumbnails.

ARCH-002 review: delete unused behavior, no new dependency/state/helper. Native.py
remains cohesive lifecycle ownership (904 lines); this increment removes two lines.
Existing tests cover visible recreation/cursor preservation, multi-output replacement,
partial creation, release failures and retries; camera caption behavior is preserved.
205 focused rendering/calibration/platform tests pass,48 Windows/rig cases deselected.
Scoped Ruff/format, three-source Win32 mypy,791-module boundaries/zero violations and
whitespace pass. No running-app restart or live Explorer/physical projector closure
check was performed. Follow-up remains in the [rig checklist](rig-verification.md#projector-window-visibility).

Historical evidence: Oct27's earlier helper added WS_EX_DLGMODALFRAME to fullscreen
outputs; incident `emergency-1104471759979700-28973466-a93b-47f4-b122-55fb4f33dec4.json`
reported calibration_front1274x714. Removing that border while retaining TOOLWINDOW
passed166 rendering/platform tests including the native1280x720 client/style case;
Ruff/format/Win32 mypy and772-module boundaries passed. The earlier146-case local run
and fixture-only31-case run did not verify Explorer appearance. Those results are
historical: the current repair removes the entire projector styling path and its
style-specific tests. The prior interruption IDENTITY warning remains a separate
unverified follow-up under `projector-shell-retry`.

## Image Resize/Source — 2026-10-27

Fold is now the third image mode (`image-fold`), implementing the owner's preview-net
layout and Front reference choice under [V04](../docs/architecture/visual_stimulus.md#v04),
[V14](../docs/architecture/visual_stimulus.md#v14) and [G01](../docs/architecture/gui.md#g01).
Runtime/preview share physical source-coordinate mapping, including Bottom rotation,
flips, valid-area cropping and transparent out-of-source coverage. Preparation rejects
missing/ambiguous Front calibration and incompatible mappings; Front must remain enabled
but need not display the layer. Net placement remains independent of selected screens.
Canonical settings, batch edits, schemas and per-mapping shader evidence include Fold.
The owner-corrected source layout is Bottom **below** Left/Front/Right (V04rev31).
The earlier Desktop rearrangement alone left runtime source coordinates above and
produced the reported Front/Bottom mixing. Shared mapping now puts the row at Y=0
and Bottom after the maximum row height; Front pitch, horizontal placement and
orientation are unchanged. Use CephVR_Fold_Test_Bottom_Below.png, not the fully
vertically flipped file. ARCH-002 review kept this as a position correction in the
existing focused helper, with no dependency or ownership change.

Correction validation:219 backend rendering/resource cases pass (18 deselected),
15 focused render cases pass including12 standalone native GL comparisons, and two
GUI four-region/flip tests pass. The actual Desktop PNG sampled with saved GUI
calibration yields the expected distinct face colours on all four outputs; this
is local preview evidence, not physical rig acceptance. Scoped Ruff/format3 files,
Windows-target mypy1 source and772-module boundaries/zero violations pass.
[Retained checks](runtime-evidence-2026-10-27/image-fold/bottom-layout-checks.json).
Running GUI not restarted; reload corrected code before testing the corrected file.


ARCH-002 review reused calibration/source textures without new dependencies or processes.
Separated preview image fitting from the canvas and fixed-screen preparation validation
from the provider orchestration. The remaining prepare.py size warning is its existing
asset/calibration preparation transaction with shared budget/source cleanup; program_model.py
remains the owning discriminated vocabulary (this change adds one enum value).

Validation: final backend rendering/resources/compilation/evidence selection:247 passed,
18 deselected and one sandbox os.link denial; that unchanged evidence-publication case
passed outside the sandbox (1 passed). Focused rendering selection:15 passed, including
12 native standalone-OpenGL image comparisons (six Fold Front/Bottom cases). Offscreen GUI
selection:11 passed. Scoped Ruff/check/format16 files, Windows-target mypy13 sources,
14-schema drift and772-module boundaries/zero violations pass. Early attempts used a
nonexistent compiler test filename (no tests), sandbox default temp (34 setup errors),
and a malformed new strict-model test fixture; these were corrected. Final formatting
also exposed a Windows text-decoding roundtrip in two edited files; original UTF-8 text
was restored and focused GUI/lint/format checks rerun successfully. No behavior assertion
was weakened. [Commands, outputs and source provenance](runtime-evidence-2026-10-27/image-fold/context.json)
are retained alongside raw results in that directory.

The running GUI was not restarted. Physical scale/optical equality and full-workload
acceptance remain in the [single rig checklist](rig-verification.md#image-resize-source).


`image-resize-source` implements the owner's two choices under
[V04](../docs/architecture/visual_stimulus.md#v04),
[V14](../docs/architecture/visual_stimulus.md#v14) and
[G01](../docs/architecture/gui.md#g01). Canonical Image settings, generated schemas,
batch edits, GUI defaults, planning preview, shader selection and actual uniform
evidence agree. The full valid-area frame is resolved through rectangular calibration,
including smaller valid rectangles, flips and Bottom quarter-turns. Source crops/pads
each axis independently using original asset dimensions; preview thumbnail size does
not change the crop. Source texels are selected without image resampling, before the
existing calibration/output pipeline. Full source texture memory is still required.

Legacy imported fits retain appearance and movement until explicitly changed. New
fixed-screen fits disable object movement/position controls; opacity still applies.
Looming/Video/Texture behavior is preserved. Consumed sheared/nonlinear profiles reject
at preparation rather than silently approximating native image size; unrelated profiles
do not block Setup. The running GUI was not restarted and physical projection is not
claimed. Remaining acceptance is in the [rig checklist](rig-verification.md#image-resize-source).

ARCH-002 review extracted the existing layer draw/upload/evidence responsibility from
scene.py into layer_draw.py with explicit frame/artifact/resource inputs and unchanged
GL ownership. Shared image geometry is pure; preview keeps bounded thumbnails plus
their original dimensions. The existing preparation orchestrator gains only a focused
consumed-profile validation gate. No dependency, new rendering process, extra texture
copy, new policy setting or alternate timing path was introduced. Existing source-size
advisories remain cohesive orchestration/model concerns; scene.py is now below500 lines.

Validation:555 local backend cases pass,20 native/rig deselected,3 subtests;13 focused
render cases include6 native standalone OpenGL comparisons through actual layer drawing
for both modes, crop/pad/mixed dimensions and exact target-uniform evidence.13 focused
GUI tests and118 preview tests pass offscreen. Ruff/format193 files, Windows-target
mypy176 sources,14-schema drift and770-module boundary checks pass with zero violations.
Initial nonexistent test-module invocation ran no checks; import/loop-index lint
findings were fixed. [Commands, outcomes and limits](runtime-evidence-2026-10-27/image-modes/validation.json)
and adjacent raw backend output/source provenance retain this local evidence. No optical,
full-load, DPI or running-application acceptance is implied.

## Repeated-asset Setup preparation — 2026-10-27

`stimulus-setup-asset-reuse` implements [V04](../docs/architecture/visual_stimulus.md#v04)
and [protected asset lifetime](../contracts/visual_stimulus/asset-lifetime.md).
The existing session-wide compatible-image validation cache is retained. A bounded,
Setup-local fingerprint cache now avoids rereading streamed files across repeated
trial references while both old and newly acquired Windows handles verify the same
protected identity. Every consumer retains its own registration/handle; closed
backing handles require rehashing, and unverified source providers never reuse hashes.
Recipe size limits, cancellation, source interpretations and original deadlines remain
authoritative. No persistent cache, extra worker pool or GPU ownership change.

Setup logs cumulative source acquisition/hash time, successful image-validation and
compilation time, plus hashed/reused and validated/reused counts; operator progress
summarizes unique/reused validations before initial residency. These are preparation
stage measurements, not total Setup or physical presentation timing. Sequential image
scratch memory remains bounded. ARCH-002 review keeps fingerprint ownership in assets
and counters in progress; the oversized prepare/session modules only thread focused
records through their existing preparation orchestration, with no runtime back-reference
or new dependency. Further parallel decoding is not justified by this small workload.

Native comparison: two seeded 3840x2160 RGB8 PNGs across six repeated trial preparations,
with baseline/optimized order reversed on the second pair. Hash reads fall from12 to2;
image validation remains2 with10 reuse hits. Source work falls from0.183–0.204s to
0.039–0.041s; total measured CPU preparation from1.005–1.092s to0.872–0.877s.
This warm/local sample excludes compilation, GPU upload, recording, tracking and
projectors; it does not establish performance for thousands of unique images.
[Raw measurements and source hashes](runtime-evidence-2026-10-27/asset-reuse/measurement.json)
and the adjacent reproducible measurement script retain provenance.

Validation:545 local Visual Stimulus cases pass,14 Windows/rig cases deselected,
3 subtests;8 separately executed native ownership/cache cases pass. Coverage includes
repeated references, changed color interpretation, immutable protection across partial
consumer release, changed content after release, recipe-limit rejection and cancellation.
Ruff/format185 files, Windows-target mypy169 sources and769-module boundary checks pass
with zero boundary violations (existing cohesion advisories above). The default sandbox
temp fixture initially failed, the sandboxed broad run stalled and was stopped, and a
repository-local demo fixture was correctly rejected; the final broad run used permitted
loopback and external temporary storage without weakening assertions. Remaining physical
timing/full-load acceptance stays on the existing [rig checklist](rig-verification.md).

## Offline stimulus authoring — 2026-10-27

`asset-preview-1080p` implements [G01](../docs/architecture/gui.md#g01) revision359:
texture previews preserve physical aspect within1920 × 1080; square previews are
1080 × 1080. Procedural source sampling matches the longest preview dimension,
using an ephemeral normalized document; resolution-free saved JSON stays unchanged.
ARCH-002 reuses existing backend generation, allocation limits and preview sampling
without dependencies or new persistent state.78 authoring tests pass,2 native cases
deselected, covering square,16:9, portrait, source sampling and document identity.
The old sparse-margin check assumed640px; its crop now uses the same physical fraction.
Scoped Ruff/check/format, Windows-target mypy and772-module boundaries pass (zero
violations; unrelated size advisories remain). No app restart/native/physical checks.

`asset-remove-resolution` applies [G01](../docs/architecture/gui.md#g01) revision358:
new authoring documents omit resolution; Open/Save strip resolution and legacy size
aliases. Raster sampling uses the existing internal default. Save emits JSON only;
no companion PNG is created. Direct runtime recipe parsing is unchanged. ARCH-002
reuses the normalizer and removes the redundant authoring constant/default field.
76 authoring tests pass,2 native cases deselected, including all catalogue patterns
saved/reopened without resolution/size fields, unchanged input documents, identical
generated pixels and no companion PNG. Scoped Ruff/check/format, Windows-target mypy and
772-module boundaries pass (zero violations; unrelated size advisories remain).
No running-app restart, native or physical checks performed.

`asset-parameter-order` applies [G01](../docs/architecture/gui.md#g01) revision355:
color controls follow all other parameters; Grating's spatial period/orientation
precede sharpness. Texture resolution is hidden; saved-field behavior is owned by
the current resolution assessment above. ARCH-002: stable color-last ordering and one hidden
field in the existing property form, without document mutation or dependencies.
76 authoring tests pass,2 native cases deselected;300/620px cases check row order,
RGB placement, editing and preservation of a hidden1024 resolution. Scoped Ruff,
format, Windows-target mypy and772-module boundaries pass (zero violations;
existing unrelated size advisories). Running GUI/native/physical checks not exercised.

`asset-parameter-columns` implements [G01](../docs/architecture/gui.md#g01) revision353:
simple property controls use equal-width two-column rows; colors, paths, seeds and
nested groups span both columns. RGB(A) channels retain one row. ARCH-002 review
uses one local grid-placement helper in the existing property owner, with no new
dependency or document state.74 authoring tests pass,2 native cases deselected,
including300/620px geometry and edit persistence. Initial narrow layout check found
unequal top alignment when a caption wrapped; explicit top alignment fixes it.
Scoped Ruff/check/format, Windows-target mypy and772-module boundaries pass with
zero violations and existing unrelated size advisories. Offscreen screenshot
geometry inspected; fallback font glyphs prevent typography acceptance there.
No running app restart, native themed display or physical checks performed.

`asset-grating-selector` removes horizontal/vertical bars from the pattern choices
under [G01](../docs/architecture/gui.md#g01) revision351; Grating retains orientation.
Saved bar recipes keep their existing values/controls, with a placeholder identifying
the loaded recipe rather than a selectable bar entry. ARCH-002 review reuses the
existing catalogue and Qt placeholder, with no conversion, dependency or backend changes.
All60 local authoring tests pass,2 native cases deselected; existing GUI tests cover
the reduced selector, orientation input and both saved bar patterns. Scoped Ruff,
format, Windows-target mypy and772-module boundaries pass (zero violations;
unrelated size advisories remain). Native restart and physical checks not exercised.

`asset-file-buttons` removes New, Export, Undo, Redo, Assets folder and Calibration
from the shared embedded/standalone Design files card under [G01](../docs/architecture/gui.md#g01)
revision350. Open and Save retain their existing handlers. ARCH-002 review: delete
six action entries, reuse the existing two-column layout, no dependency or state changes.
Validation:14 offscreen GUI tests pass,2 native cases deselected; a direct Qt check
confirms exactly Open/Save buttons and actions. Scoped Ruff/check/format and Windows-target
mypy pass;772-module boundary check has zero violations and existing unrelated size
advisories. Initial pytest failed to create sandbox Temp fixtures; rerun with an
explicit writable visualization basetemp passes. Running GUI restart/native display
and physical acceptance were not exercised.

`asset-first-open-window` (Oct27) fixes first-open native window recreation under
[G01](../docs/architecture/gui.md#g01). Native reproduction changed HWND6425952 to
6491488 when the lazy editor added the first QOpenGLWidget. This matches
[Qt's documented dynamic-GL-child behavior](https://doc.qt.io/qt-6/qopenglwidget.html#limitations-and-other-considerations).
The page now owns a permanently hidden QOpenGLWidget before top-level show, selecting
GL composition without creating its GL context. Editor/documents/workers remain lazy.
ARCH-002: five initialization lines plus the existing Qt import, no extra application
state, dependency, process or rendering algorithm. No architectural amendment needed.
Two isolated native cases (minimal host and actual Dashboard navigation) preserve
HWND and avoid Hide/Close/WinIdChange through first/repeat open and arena activation;
47 authoring regressions pass. Scoped Ruff/format, Win32 mypy and771-module boundary
checks pass. Existing size advisories remain outside the small page owner.
[Evidence](runtime-evidence-2026-10-27/generate-stimulus/first-open/context.json).
Running managed GUI untouched; native test success does not close rig acceptance.


`asset-projector-independent` (Oct27), G01 revision345 / V04 revision26:
new polar recipes use tile-local physical coordinates; saved assets have no screen
names, and both pixels/cache identity are independent of calibration. Static arena
materials accept these polar tiles while retaining legacy screen-dependent rejection.
Default tile preview hides the screen selector and needs no geometry; sparse noise
uses an illustrative100x100mm sample. Optional calibrated inspection and Protocol's
actual per-screen sparse streams retain their existing behavior. Legacy runtime
polar files remain unchanged; editing/saving them creates the independent variant.
ARCH-002 review reused polar formulas and extracted bounded grid sizing from the
existing sparse owner, without a new dependency or duplicated random algorithm.
No oversized owner was extended; existing boundary advisories remain unrelated.
Validation:240 authoring/resource/rendering cases pass (6 native/rig deselected),
including geometry-independent polar pixels/cache keys, calibration-free previews,
legacy polar behavior and arena texture import. Ruff/check/format21 files,
Windows-target mypy18 sources,14-schema drift,769-module boundaries and whitespace
checks pass. Optional native preview and physical projection remain untested;
existing rig acceptance stays open. One initial lint command used unsupported
PowerShell brace expansion; the explicit-path rerun passed.


`asset-appearance-only` (Oct27): G01 revision344 / V04 revision25 separate
sparse-noise appearance/seed from Protocol-owned screen assignment, pattern count
and duration. Save/Open normalizes legacy full recipes to appearance; Protocol
accepts both formats, uses its explicit timing, and persists those controls with
selection paths. Indexed preview pixels retain the existing generator. Ordinary
texture motion remains Protocol-owned. The full preparation recipe/API stays
strict and preserves E05 duration and resource checks.

ARCH-002 review: reuse the existing model fields through an appearance base model,
existing generators and file/dialog owners; no dependency or process added. Changed
modules remain focused; existing boundary size advisories are outside this change.
Validation:122 authoring/resource tests and5 sparse-noise GUI tests pass (offscreen),
scoped Ruff/format20 files, Win32 mypy17 sources,14-schema consistency and769-module
boundary checks pass. Initial GUI run found a stale summary field and three stale
worker fixtures; corrected and all five GUI cases rerun successfully. No native
relaunch or optical acceptance claimed; retain the existing rig checklist.

`generate-stimulus` implements the approved standalone module/GUI under
[G01](../docs/architecture/gui.md#g01), [V04](../docs/architecture/visual_stimulus.md#v04)
and [V18](../docs/architecture/visual_stimulus.md#v18). The
[authoring contract](../contracts/visual_stimulus/stimulus-authoring.md) documents
recipes, square physical tiles, calibration context, static geometry/relief/scatter,
explicit OPAQUE/MASK coverage and transactional GLB bundles. Runtime ownership and
protocol movement boundaries are unchanged. Under G01 revision344 the main GUI embeds
the shared editor in a lazy Generate assets tab; standalone use keeps its own window.
Drafts/undo survive navigation, shortcuts stay scoped to the editor and unsaved
designs can veto closure before managed configuration saving or Review shutdown.
The viewport requests its own OpenGL format in either host. ARCH-002 review keeps
the existing window as the shared editor, with a focused lazy page and no new dependency.
Presentation is extracted into layout.py under ARCH-002; the window retains document
transactions and job coordination. G02 revision169 applies the shared Card, field,
button, dropdown and ResponsiveColumns components to both hosts. Standalone reads
the saved frontend style; caption formatting is shared with the main GUI. Amber
navigation measures the full label, and preview pixels refit when columns resize.
No new dependency or backend-generation change is introduced.

Layout validation:42 authoring cases pass, followed by37 selected authoring/managed
cases; Ruff/format18 files, Win32 mypy16 sources and769-module boundaries pass.
Native embedded/standalone screenshots at100% and125% and720px narrow stacking
were inspected. The broader selection passed85 cases but failed two GUI focus/splash
cases. Isolated reruns fail their three style variants; both Standard failures also
reproduce with the HEAD appearance module substituted in memory. Root cause remains
unverified; these are not counted as passes. See layout-validation.json and
layout_probe.py in the linked authoring evidence directory.

Tab validation:48 focused authoring/GUI cases and2 managed-close cases pass;
scoped Ruff/format, Win32 mypy17 sources and769-module boundaries pass. A bounded
native1440x960 main-window probe rendered arena geometry with no viewport error;
embedded-arena.png and embedded-check.json retain local evidence. Actual managed
runtime restart, rig calibration and full-workload acceptance remain pending.

Owner-reported managed-launch regression: direct execution through the managed
`cephvr-python.exe` reproduced QtGui DLL import failure. The parent GUI's DLL-directory
registrations are process-local. The initial repair used the verified Python
resolver and existing `python_entry`/`module_arguments` bootstrap. The owner-requested
embedded tab now supersedes that detached launcher, avoiding a second Qt process. Eight GUI regression cases, scoped Ruff/format and Win32 mypy pass;
a fresh managed-interpreter bootstrap opened the actual editor and exited cleanly
through a bounded test event loop. Initial standalone preview tests did not cover
this managed-launch path. The running main GUI was not restarted.

ARCH-002 review reused NumPy/Pillow, existing texture and indexed sparse generators,
the production GLB parser, linear image upload and sampler configuration. No new
dependency or experiment process was introduced. Generation, file publication,
documents, properties, preview jobs and viewport remain focused modules; the window
owns UI transactions only. New owner tests are split into pure authoring and Qt GUI
responsibilities rather than per-fix modules. Per-surface CPU geometry and current
GPU mesh/texture caches avoid rebuilding unchanged resources.

Current validation: 254 authoring/backend cases pass (6 native/rig deselected),
47 existing GUI protocol/preview cases pass; the final39 authoring cases pass after
publication/cancellation and budget refinements. Scoped Ruff/format20 files, Win32
mypy17 sources,13-schema drift and boundaries769/zero violations pass. The sdist
and Windows wheel build successfully and include all13 authoring modules/launcher.
Native Windows editor/OpenGL rendering, textured MASK materials and cached material
updates passed at100%/125% scaling. Wide/narrow screenshots were inspected and the
initial property-panel clipping corrected. These are bounded local UI checks.
Initial tests encountered sandbox temporary-directory creation failure, then three
demo-asset fixtures rejected repository-local temp storage; the passing broad run
used the authorized external visualization workspace. An alpha-BLEND export attempt
was rejected by the production loader; the editor now exposes only its supported
OPAQUE/MASK modes. Those failures were not treated as runtime passes.

Native screenshots and validation context are retained in
[authoring evidence](runtime-evidence-2026-10-27/generate-stimulus/).
Optical dimensions, calibrated luminance and full-workload performance remain in
the [rig checklist](rig-verification.md#stimulus-authoring).

Current Oct27 immediate-start Abort investigation under E05/E06/E13 and V12:
normal finish now seals recording admissions while retaining the required late
recipe Header; explicit cancellation stays final. Submitted-frame closure follows
the accepted [completion predicate](../contracts/visual_stimulus/video-completion.md):
exact final identity, accounting, successful encoder exit, synchronization and
cleanup. Creator evidence remains required for never-created absence/deletion;
it is not inferred from a late file appearance. Final identity is independently
rechecked to reject replacement/disappearance. Deferred cleanup also retains its
own original deadline despite intervening recipe-publication commands.
Owning recording/lifecycle checks and final2907-test backend integration pass.
Native Abort confirms Interrupted metadata and seven Closed outputs, followed by
two60s trials crossing the retired end; six videos fully decode/count-match.
Historical failed recordings remain Unconfirmed and retained in the
[rate/scaling evidence](runtime-evidence-2026-10-27/rate-scaling/validation.json).

## Sparse-noise preparation — 2026-10-27

`sparse-noise-recipes` implements the owner-requested seeded backend preparation
module under [V04](../docs/architecture/visual_stimulus.md#v04).
The owner selected density-derived fixed counts without replacement and independent
reproducible per-screen streams. The [contract/schema/example](../contracts/visual_stimulus/sparse-noise.md)
defines recipe generation and the command-line/Python API. Preparation emits standard
image programs, compact RGBA grids and provenance; the legacy texture importer
remains unchanged. The GUI picker below now exposes preparation. Physical sizing uses supplied calibrated screen geometry,
with centered full cells and background residual margins. Existing image residency,
timing/holds, source protection and actual-image evidence retain their owners.

ARCH-002 review selected existing image resources/compiler/scheduler rather than a
new shader family, runtime RNG, process or dependency. The recipe model and focused
preparer are separate from existing large owners; existing size advisories remain
cohesion reviews, with no affected large source module extended. Tests extend the
owning resource behavior module and exercise normal preparation, compilation and
image scheduling. 211 affected resource/compiler/rendering tests pass, 6 native/rig
cases deselected. Win32 mypy passes168 Visual Stimulus sources; scoped Ruff/format,
12-schema drift check, boundaries764/zero violations and whitespace checks pass.
The CLI prepares the supplied600-pattern/four-screen example against test geometry;
this is no physical display measurement or runtime/rig presentation pass.

Initial sandbox temp creation failed; repository-local temp then conflicted with an
existing demo-fixture outside-repository requirement. Final tests use the separate
authorized visualization workspace. Two tiny-grid assertions incorrectly assumed
independent patterns could not coincide; corrected to reference pixels and sequence
comparison, preserving legitimate random repetitions. No production defect was
hidden by those corrections. Provenance, commands and scope are in
[evidence](runtime-evidence-2026-10-27/sparse-noise/context.json).
Native size/color/onset/combined-load acceptance remains in the
[single rig checklist](rig-verification.md#sparse-noise-presentation).

## Sparse-noise runtime generation — 2026-10-28

`sparse-noise-runtime-generator` implements the owner's choice of patterns generated
during playback in a separate contained process, 100 patterns ahead, under
[V04 revision 36](../docs/architecture/visual_stimulus.md#v04), V01 revision 37 and the
[sparse-noise contract](../contracts/visual_stimulus/sparse-noise.md). Uncommitted.

- **Authoring:** new `sparse_noise` layer kind (appearance, count, duration); no PNGs
  or Apply. The GUI edits it inline and previews by generating the pattern; legacy
  image-form rows load read-only and still play through the image path.
- **Compile:** width/height fixed to the grid resolved from the active display.
- **Helper:** `sparse_noise_helper` runs per trial through `SupervisedEncoderLauncher`
  (the renderer's FFmpeg launch path: supervisor plan, Job Object, OS/operational
  confirmation, stdin-EOF stop, exact exit and empty-job cleanup) as role
  `visual_stimulus_sparse_noise`, added to the supervisor's renderer-helper set.
  JOB/CREDIT lines on stdin, framed RGBA8 cells on stdout.
- **Renderer:** `SparseNoiseRing` prefills the first window at PrepareTrial before
  Ready, uploads grid-sized RGBA8 textures (16 B/cell float32 no longer applies),
  reuses retired textures and selects the newest due pattern; misses are
  `residency_hold` evidence and never stall the clock or the credit window.
- **Generator speedup (kept):** byte-identical stencil in `eligible_cells`; 320
  golden and 900 fuzzed patterns equal the previous implementation.

Local evidence (macOS, not the rig): the helper over real pipes starts and returns
its first frame in 0.2–0.3 s, stops in under 40 ms on stdin EOF, and its frames are
byte-identical to `pattern_rgba` (rows flipped for GL). Four-screen generation costs
14 ms per pattern at 120×68 cells but 343 ms at 600×340, which cannot sustain 300 ms
patterns in one process; the calibrated 2 mm rig grid (~10k cells over four screens)
is about 1 ms per screen. A design defect found by the ring tests (holding the
previously shown pattern could exhaust credit and deadlock a lagging helper) was
fixed by showing the newest due resident pattern.

Checks (macOS, Oct28): `tests/visual_stimulus` + `tests/supervisor` 828 passed, 3 failed
(known: PyOpenGL absent locally); `tests/generate_stimulus` (offscreen) 131 passed;
focused GUI `-k "sparse or noise or preset or layer or media_family"` 30 passed, 2
failed in `test_dashboard.py` (they select a removed "Texture" preset label from earlier
uncommitted preset work; not re-run at HEAD). Ruff, format, Win32 mypy (423 files),
boundaries (0 violations), 14 schemas and whitespace pass. Policy v21 digest updated.

Not verified: Windows launch/containment of a Python helper under the encoder
launcher, helper startup time against the PrepareTrial deadline, GPU upload cost,
optical timing. Inherited gap: the supervisor has no release path for renderer helper
launch records (also true for its FFmpeg children), so per-trial records accumulate
for the session. Rig steps: [rig checklist](rig-verification.md#sparse-noise-presentation).

Follow-up, same day (owner-approved): the legacy PNG sparse path is removed (image-form
`sparse_noise` sequences, bundle preparation, multi-projector import,
`tools/prepare_sparse_noise.py`, the Protocol import dialog, legacy rows/previews and their
tests; G01 revision 370). Old protocols with such rows no longer load. Evidence now records
`background_hold` with null `image_index` when a sparse layer drew only its background, and
`pattern_sha256`/`pattern_generator` on the first frame showing each pattern (helper-computed
SHA-256 of `pattern_rgba`; V04 revision 37, V13 revision 14). Re-run: 817 Visual
Stimulus/supervisor pass (3 known PyOpenGL failures), 131 authoring pass, focused GUI 54 pass
with the 2 known dashboard failures and 24 sparse/preview pass; static checks pass.

## Stimulus authoring review follow-up — 2026-10-27

Read-only review of commit bfe24b35 (correctness, simplification, GUI) followed by
owner-authorized fixes under [V04](../docs/architecture/visual_stimulus.md) and
[G01](../docs/architecture/gui.md#g01), uncommitted at this entry. Applied:
- Correctness: `physical_field._hash` casts through int64, so negative field cells match the
  GLSL `field_hash` (the macOS `test_seeded_field_statistics_and_full_seed_range` failure
  was this defect; Windows x86 results had masked it). Golden negative-index tests added.
- Backend (behavior-preserving): faster `dots_rand` (bit-identical; about 1.3-1.5x, noisy),
  per-trial `LayerCache` with one shared GL/evidence uniform computation (a missing
  width/height now defaults to 0.0 in the GL path, as the evidence path already did),
  fold-map/unfolder reuse, one validation of the merged sparse-noise program,
  one GL program per distinct field fragment source, `get_args(SurfaceId)` face lists.
- Generate window: cached `limits()` (9.6 to 0.5 ms), texture-bake cache (colour-edit
  recompile 140-190 to about 10 ms), smooth DPR-aware preview scaling (17.8 to 2.7 ms per
  resize), model-derived spin ranges, inline validation feedback, flush on save/close,
  Save/Discard/Cancel prompts with Cancel default, `.json` default suffix, themed Surfaces
  list, poll timer only while jobs run, late-export reporting.
- Epoch editor: grating row inputs 124 to 37 px with R/G/B prefixes and visual Tab order,
  tooltip preservation, `stimulus_layers`/`stimulus_binding`/`stimulus_asset_paths` splits
  (output byte-identical across 158 preset combinations), import dedupe and a byte-budget
  media cache, Trial Preview stale banner with Refresh, sparse-noise status/Cancel and
  cleanup of only the layer's own unapplied `sparse-noise/<32 hex>` directories, shared
  wording, epoch card value 145 to 115 (contrast at least 4.5:1 for every hue),
  stimulus-authoring tests moved to `tests/gui/test_stimulus_authoring.py`.

Validation (macOS, local): 743 Visual Stimulus/authoring tests pass, 3 fail
(`ModuleNotFoundError: OpenGL`, environmental); 294 focused GUI tests pass (selection by
keyword; the full GUI suite was not run). Ruff, format, Win32 mypy, boundaries and
14 schemas pass. Four GUI tests and two preview tests fail or abort identically at HEAD
(reported by the coder; not re-verified here). GL paths (`draw_layer` fold/field, shared
field programs, lazy viewport texture variants, `paintGL`, picking) are not locally
proven; they stay in the [rig checklist](rig-verification.md#stimulus-authoring).

Correctness fixes applied after owner approval (Oct28): mixed field/raster candidates now
get uniform layouts and Setup placement checks (V08); legacy `media_presentation` link load
errors name the epoch and instance (V02); the published program schema accepts legacy
`texture_drift`; marked inline Grating rejects `square_grating`; invalid field colours are
rejected; sparse-noise minimum distance tolerates the 7.000000000000001 case (one golden
case changed: the exact-distance layout) and accepts an optional `active_surfaces`; the
unused `photodiode_level` is removed; opening a legacy `texture_design` shows a conversion
notice and Save routes to Save as…; the arena scatter sampler uses a precomputed cdf
(bit-identical to `rng.choice`, 4.1 s to 2.7 ms on 200k triangles x 2000 instances). Local:
775 Visual Stimulus/authoring tests pass, 3 OpenGL environmental failures; GL draw is not
exercised. GUI wiring (Oct28): protocol/program loads log one notice for linked Media epochs
and report invalid-link errors readably; the sparse-noise import dialog and inline layer pass
the enabled-projector surfaces as `active_surfaces` on each preparation (97 focused GUI cases
pass; full suite not run).

Oct28 owner decisions implemented under [G01](../docs/architecture/gui.md#g01)
revision376: converted legacy bars retain mandatory new-file protection; Generate
keeps Open/Save as. Removed uncalled New, Undo/Redo/restore, Export, Cancel, root and
calibration handlers with their unused history/export state. Preserved headless arena
export, injected geometry, preview cancellation, stale-result filtering and unsaved
close/Open prompts; preview error text now accurately offers saving. ARCH-002 caller
review found no production callers; owning tests retain edit/save, selection/rebuild,
workspace isolation and stale-result checks instead of exercising unreachable actions.
No new dependencies. Existing legacy conversion test now covers both bar orientations,
including rejection of the original path, byte preservation and successful new-file save.

Validation: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/generate_stimulus -q -m "not windows and not rig" --basetemp=.pytest-tmp-authoring-actions --timeout=30`
gives131 passes,6 deselected and1 failure: `test_parameter_pairs_keep_full_width_rgb[300]`
measures188/200px instead of equal widths. Isolated selection `-k "parameter_pairs_keep_full_width_rgb or legacy_open"`
gives5 passes and the same failure; it constructs the unchanged property form without
AuthoringWindow. No baseline execution claimed; tracked under gui-suite-reconciliation,
not repaired in this action cleanup. Scoped Ruff/check/format, two-source Win32 mypy,
791-module boundaries/zero violations and whitespace pass. Source tree uncommitted
atop e4dd8f2694aa075380fe6711a884fe5894763c6f; no app restart/native/optical acceptance.
Remaining review findings: follower position on unlink (unverified), GL-only paths,
and GUI suite reconciliation.

## Current runtime verification

### Sparse-noise GUI integration — 2026-10-27

`sparse-noise-gui` implements [G01 revision340](../docs/architecture/gui.md#g01)
and [V04 revision22](../docs/architecture/visual_stimulus.md#v04): Protocol opens
one recipe picker per enabled screen, displays each seed/density/size/timing and
adds a separately prepared trial using the existing Assets root. Save/reload
retains the bundle path and restores selections. Preparation uses a bounded
backend composition helper with validated current Geometry, isolated per-screen
recipe snapshots and normal image program execution. It performs no device or
experiment commands. Cancellation/authority/root/screen/geometry fencing prevents
late completion from changing the protocol; generated files are retained.

ARCH-002 keeps widgets, file preparation and backend composition separate, with no
new dependencies or runtime references. Window geometry reading is shared with its
existing preview; the572-line Protocol page remains the GUI transaction owner,
while new recipe widgets/generation live in focused modules. Its size advisory was
reviewed: adding a second owner for trial/history mutation would duplicate state.

Validation:47 GUI protocol/preview/sparse-noise checks pass;215 backend resource,
compiler/rendering checks pass with6 native/rig exclusions. Scoped Ruff/format8,
Win32mypy6,12-schema drift and boundaries767/zero pass. The5 new GUI cases cover
independent recipes, preserved existing trials, save/reload, cancel, authority loss,
geometry change and invalid/out-of-root paths. Four added backend cases cover
per-screen seed/density binding and mismatched schedule/background rejection.
Offscreen picker layout is rendered and inspected; this does not establish native
DPI/file-picker/physical projection behavior. Initial mypy caught a QWidget.geometry
name collision, corrected before GUI execution. First isolated render lacked font
registration; final render uses the application's font setup. Native app untouched.
[Evidence](runtime-evidence-2026-10-27/sparse-noise-gui/context.json),
[picker](runtime-evidence-2026-10-27/sparse-noise-gui/picker.png).
Remaining acceptance stays in the [rig checklist](rig-verification.md#sparse-noise-presentation).

### Other runtime evidence

Oct26/27 hierarchical audit removes the renderer's unread duplicate resource field
and unreachable inner start-time guard. `_sessions` keeps resource ownership;
cutoff validation/order and cleanup semantics remain unchanged under V01/E06 and
ARCH-002.113 rendering tests pass (6 excluded); static/boundary checks pass.
Fresh60s recorded trial closes3554 stimulus frames, all fully decoded and matched.
Seven software-evaluation gaps exceed25ms (maximum276.4823ms), all in the first0.932s;
startup attribution and optical timing remain open. Synthetic2080Ti encoding passes
baseline/double demand but cannot sustain quadruple demand. [Audit](runtime.md#hierarchical-audit--2026-10-2627).

Oct27 approved V12rev20 terminal export is implemented and verified natively in two
unchanged60s runs: exactly one identity-bound metric row each; all six videos fully
decode/count-match. Initial stdin input spans144.462/145.4227ms with34/22 zero-progress
writes, peak11/9 of15 slots and no reported capacity drop. Max software-evaluation
gaps38.0735/32.3304ms do not reproduce or explain the historical276ms gap. The first
run's initial gap precedes its worst pipe interval. Input backpressure is established;
encoder computation, GL first-use and physical timing attribution remain open. Keep
buffers/threading/quality unchanged. [Current assessment](runtime.md#hierarchical-audit--2026-10-2627).

Oct26 lifecycle follow-up under [V01](../docs/architecture/visual_stimulus.md#v01)
and [E06/E08](../docs/architecture/system-contracts.md#e06) is verified for the bounded
cases. Confirmed-only catalogue/receipt retirement fixes repeated-Shutdown stale keys;
immutable completed evidence and exact session tombstones preserve old-session fencing.
Native regressions additionally repair lost arena release proof across calibration
Close/display restoration, retained finished trial state blocking post-session Open,
and stale previous-display ownership preventing Close. New allocations invalidate only
their own old release receipts; failed release, unacknowledged cleanup and active trial
state remain owned/fenced. No proof validator or original deadline is relaxed.
Final backend2676 tests and all static checks pass; owning lifecycle64, renderer29
and resources56 pass. Native GPU88/1 rejection confirms cleanup and fresh Setup/Cancel.
The final fresh application completes two60-second Visual Stimulus-only trials,
NewSession, calibration OpenACTIVE/CloseIDLE with resources_closed, then normal
Ended-session Shutdown. Renderer exits0; exact supervisor receipt confirms all owned
processes absent. Four saved settings files are restored byte-for-byte and no new
emergency is created. Prior failed probes are preserved, including the orderly-exit0
reproduction that led to the finished-trial fix. Missing remote ErrorReport details in
those failed probes remain an unverified delivery limitation; bounded local recovery
cause logging now survives channel teardown. No optical/full-load/encoder feasibility
or deferred backend acceptance is inferred.
Small exact session tombstones persist for generation lifetime; full report payloads
retain ledger budgets/pruning. Cohesive evidence, native lifetime and worker command
owners remain intact, with no whole-runtime back-reference or generic retry framework.
[Methods, source hashes and evidence](runtime-evidence-2026-10-26/lifecycle-followup/).

Oct26 `repo-cleanup-and-code-review`: Astra/Luna source/caller review found no
additional safe runtime deletion or optimization. Shared GLB/geometry/texture test
helpers moved unchanged to the existing support module under
[ARCH-002](../architecture.md#arch-002), preserving scenarios and avoiding imports
from test modules. Final local validation passes491 Visual Stimulus cases; all19
schemas regenerate and installed binding hashes match. No rendering throughput or
rig acceptance is inferred. [Review evidence](runtime-evidence-2026-10-26/repo-review/).

Oct26 `preview-rate-readback`: fixed under [V01](../docs/architecture/visual_stimulus.md#v01)
revision36. Each staggered per-projector timer previously triggered draws of all
visible windows. One shared50ms group timer now gates all optional composition;
individual toggles cannot multiply cadence. Hidden/minimized skip and immediate
whole-group reopen retained.113 final rendering checks pass; Ruff/format, Win32
mypy and boundaries pass. Native Combined/Per-projector and Left/Front toggles
at1442x972 show settled19.7–20.0fps with plots/FPS visible; one finite sampling
window reads20.6fps. No27.7–36.5fps recurrence. First81.87s run and normal shutdown
pass. Final44.47s native run uses user-approved authenticated takeover after UI
input timeouts: six Combined/projector/hide/reopen operations succeed, telemetry
19.66–19.99fps with first reopened count interval20.90fps. Final minimized skip
remains locally tested. Both recordings fully decode/count-match; cleanup and
shutdown succeed, no runtime processes remain, settings restored byte-for-byte.
No optical/DPI/full workload acceptance. [Evidence and limits](runtime-evidence-2026-10-26/recorder-fps-fix/context.md).

Oct26 `monitor-projector-toggle-stability`: V01's existing native viewer now checks
actual size before resizing and changes native visibility only on transitions,
avoiding redundant render-thread work during projector mask/placement updates.
Manual-placement, snap/reopen and owner binding retained.119 rendering tests,
Ruff/format, Win32 mypy and boundaries pass. Live FPS improvement remains unmeasured;
no renderer restart or rig acceptance. [GUI checks and limitations](runtime.md#monitor-projector-toggle-stability--2026-10-26).

Oct26 `preview-marker-style`: [G01](../docs/architecture/gui.md#g01) revision323
adds bounded display-only RGB hints through the existing authenticated preview
placement path. Combined inspection uses the GUI card surround and theme-derived
per-projector surface outlines matching plot markers; GUI preview brackets stay
normally themed after owner clarification. GL applies colors only to the inspection
clear/outline shader. Physical stimulus, source/composite textures, recordings,
resource ownership and timing remain unchanged under V01/E08.
119 rendering cases pass, including native standalone-GL exact surround/outline
colors and source/composite preservation;8 authenticated transport and10 camera
hint-admission cases also pass. Shared validation rejects malformed RGB/name maps
and stimulus styling on camera requests. Ruff, Win32 mypy and boundaries pass;
no running backend restart or native full-load/rig acceptance.
[Current methods and limits](runtime-evidence-2026-10-26/preview-marker-style/context.md).

Oct26 `advanced-preview-content-projectors`: [V01](../docs/architecture/visual_stimulus.md#v01)
revision35/[G01](../docs/architecture/gui.md#g01) revision322 apply bounded display-only
surface exclusions in Combined and Per-projector previews. All excluded means no
native viewer; source projection/recording textures are unchanged. Five focused
renderer cases pass, including actual standalone GPU draws proving suppressed
surfaces/outlines and unchanged source/composite pixels; ten camera placement
admission cases reject stimulus masks. Shared bindings regenerated, static checks
pass. Native live multiwindow/DPI/full-load acceptance remains pending.
[Current assessment and evidence](runtime.md#compact-preview-toolbar--2026-10-26).

Oct26 `stimulus-preview-layout`: [G01](../docs/architecture/gui.md#g01) revision319
uses borderless native stimulus viewers within themed GUI frames, FPS beneath each
image and larger centered Combined instruments. GLFW still owns shared contexts,
pixels and lifetime; existing visibility/owner/placement gates remain.46 Dashboard
and204 timeline/rendering checks pass locally, with13 final layout checks repeated;
static checks pass. Offscreen visual review covers placeholders/planned plots,
not live native GPU windows. No app restart, DPI or physical-output acceptance.
[Evidence and limitations](runtime.md#stimulus-preview-layout--2026-10-26).

Oct23 `preview-space-and-shared-polar`: [G01rev309](../docs/architecture/gui.md#g01)
enlarges Combined's GUI allocation while retaining the existing GPU rig. Compatible
projector vectors share a colored polar plot and projector-row parameter table;
Per-projector adapts placement and retains static Bottom. No renderer, calibration,
recording, physical output or camera-preview backend change.91 timeline and125 selected
Dashboard tests pass offscreen; native/full-load checks remain open.
[Current evidence and limits](runtime.md#combined-space-and-shared-polar-table--2026-10-23).

Oct23 `no-recording-dummy-session`: implements the owner-requested
[E04](../docs/architecture/supervisor.md#e04) all-recording-Off exception.
[Current validation and limits](runtime.md#no-recording-dummy-session--2026-10-23).

Oct23 `dummy-setup-empty-catalogue`: owner-observed Setup failure is reproduced by
the real [E08](../docs/architecture/system-contracts.md#e08) catalogue validator:
dummy recipe preparation sent revision1 without adding resources after revision0
empty. A two-line guard keeps the acknowledged empty catalogue until actual worker
resources arrive. Saving-enabled preparation and supervisor checks are unchanged;
this precedes renderer Setup and is independent of the GPU rig view.102 affected
coordinator/supervisor checks pass; Ruff/format, Win32 mypy and boundaries pass.
Failed native session/recovery remain unverified and untouched.
[Assessment/evidence](runtime.md#no-recording-dummy-session--2026-10-23),
[dated reproduction](runtime-evidence-2026-10-23/dummy-setup-catalogue/README.md).

Oct23 `preview-rotation-and-projector-windows`: owner confirms physical rotation
is coherent; reported preview direction mismatches remain distinct from rig output.
[E13](../docs/architecture/visual_stimulus.md#e13) revision31 updates operator
orientation, and [G01](../docs/architecture/gui.md#g01) revision305 compensates the
Bottom folded mirror in protocol planning. The subsequent owner-authorized
`gpu-combined-rig-preview` replaces Combined with one GPU screen-plane rig window
under [G01](../docs/architecture/gui.md#g01) revision308,
[V01](../docs/architecture/visual_stimulus.md#v01) revision34 and E13 revision32.
Left-drag rotates its inspection camera; double-click resets. It samples existing
calibrated composite tiles with protocol rig orientation; Per-projector is unchanged.
No projector/calibration/recording pixel change, stimulus-observer change or CPU
readback.117 rendering cases (including native GPU pixels and hidden GLFW lifetime)
and26 selected GUI cases pass; Ruff/format7 files, Win32 mypy5 sources and758-module
boundaries/zero pass. GPU geometry/camera behavior lives in a focused owner under
ARCH-002; native.py retains only assembly. Cost and native/physical acceptance remain
unmeasured. [GPU rig methods/images](runtime-evidence-2026-10-23/gpu-rig-preview/README.md).
[Current assessment](runtime.md#preview-rotation-and-combined-windows--2026-10-23),
[methods/evidence](runtime-evidence-2026-10-23/preview-rotation/README.md),
[rig checklist](rig-verification.md#protocol-category-previews).

Oct23 `protocol-category-templates`: owner revised [V02](../docs/architecture/visual_stimulus.md#v02)
to ignore saved texture-motion links in Media presentation. Canonical source retains
links, link validation is bypassed for this category and compiler settings remove them
before writer/geometry checks and rendering. Motion restrictions remain in force.
37 compilation/configuration tests plus3 subtests pass, including inactive-link source
retention/executable removal. GUI template restoration, checks and native limitations
are recorded in [Runtime](runtime.md#protocol-category-and-preview-design--2026-10-23).

Oct23 `protocol-category-preview-design`: implemented optional canonical categories
and cross-trial capability validation under [V02](../docs/architecture/visual_stimulus.md#v02)
and [V03](../docs/architecture/visual_stimulus.md#v03), with legacy content preserved.
[V01](../docs/architecture/visual_stimulus.md#v01) preview ownership now includes
Combined or up to four lazy per-surface windows sampling the existing calibrated
preview texture, with per-context reader fences, grouped visibility/cleanup and the
existing20Hz ceiling. No GUI pixel transport or change to recording composition.
ARCH-002 isolates the preview group and category validator; native.py retains assembly.
[Implementation and current checks](runtime.md#protocol-category-and-preview-design--2026-10-23);
[native/full-load acceptance](rig-verification.md#protocol-category-previews) remains open.

Oct23 `device-warning-clarity`: wrong-GPU remedy now uses plain language while
preserving RTX5060Ti, executable-specific settings and full-application restart
requirements under [V19](../docs/architecture/visual_stimulus.md#v19).
117 rendering/controller-communication checks pass; GUI warning review and validation
limits are recorded in [Runtime](runtime.md#device-warning-clarity--2026-10-23).

Oct26 `projector-warning-diagnostics` refines `projector-unavailable-message`:
unavailable-output feedback identifies the assigned face(s) with one recovery
instruction. The owner-requested shorter review leaves the saved Windows display/
output identity in Copy details and omits redundant failure progress. Ambiguous identity
diagnostics remain distinct. Under [V19](../docs/architecture/visual_stimulus.md#v19),
placement, exact identity matching, all-output preflight and cleanup are preserved.
ARCH-002 moves preflight into the existing native display helper, keeping lifecycle
assembly in native.py with no new dependency/state.112 rendering checks and8
authenticated communication checks pass;4 retained-review checks and static checks
also pass. Initial sandbox fixture/socket failures are not counted as passes.
[Current commands, evidence and limits](runtime.md#device-warning-clarity--2026-10-23).
The running app was not restarted; native warning/physical display checks remain open.


Oct22 current result: the image-read ctypes lifetime defect and helper retirement
proof mismatch are fixed. Final uninstrumented unchanged2×600s playback/recording
completes with confirmed cleanup, all14 outputs closed and six videos fully decoded.
All4000 image/blank occurrences agree; no image mismatch, residency hold or failed
submission. Worst state interval improves105.882→31.9408ms; worst output interval
107.899→38.6401ms and software onset47.1322→21.8091ms. Neither helper warning recurs.
This is software timing/content validation, not strict60Hz or optical/electrical
certification. Exact original configuration/history is restored; app is idle.
483 Visual Stimulus and168 supervisor tests pass; prior899 GUI-node coverage remains.
One pre-Start MCU PING timeout followed by a successful fresh retry and separate idle
shutdown findings remain explicit follow-ups. [Evidence and limits](runtime.md#rig-checks-oct22).

Oct21 `stimulus-rig-direction-authoring`: [G01](../docs/architecture/gui.md#g01)rev289 / G02rev106,
[V02](../docs/architecture/visual_stimulus.md#v02)rev15 and
[V08](../docs/architecture/visual_stimulus.md#v08)rev7 implemented for physical-screen
controls, batches/conditions and new numeric variations. Right0°/Front90°/Left180°/
Back−90° now govern authoring and moving dial labels/readouts; arrow alignment is
unchanged. Saved rig-angle version1 rules/drafts retain Back0°, new rules write
version2, and mixed versions are rejected. Existing mapped layer
translation keeps rig direction independent of texture rotation; linked references
accept that translation while followers retain calibrated phase binding. Untouched
legacy rates/functions and saved local random rules retain their semantics; imported
visual-angle controls remain explicitly angular. Shared incompatible screen frames
use per-projector editing. Existing linked drift/spin and centered spin-pivot limits
remain enforced.
Validation:216 preview/configuration/compilation/rendering tests and44 selected GUI
checks pass; current angle revision Ruff/format13, Win32 mypy214, schema-model equality and
boundaries748/zero pass. Existing size advisories: the parameter form remains the
assembly owner; new conversion logic is in focused helpers, with duplicate motion
parsing removed from the widget. No dependencies or renderer state added. Scoped
whitespace passes; full-tree check flags pre-existing launcher whitespace. Native
cardinal-direction/retained-state acceptance remains in the existing
[rig checklist](rig-verification.md); running GUI was not restarted.

Oct21 GUI subject-coordinate polar previews reuse V02 calibrated unfolding without
changing renderer motion. G01rev282/G02rev103 and validation/limitations are recorded
in [Runtime](runtime.md):78 preview/compilation checks pass; native label readability
and running-GUI acceptance remain pending.

Oct21 `preview-20hz`: [V01](../docs/architecture/visual_stimulus.md#v01) revision31
applies G01's20 Hz cadence before optional preview composition and GL synchronization.
Slower batches display at their source rate; hidden/minimized previews skip this
work. Projector swaps and scientific recording retain their existing path. Shared
pacing and native-owner visibility tests are included in373 passing local checks;
Ruff, Win32 mypy and boundary checks pass. Native live cadence remains unmeasured.
ARCH-002 review keeps pacing in the shared helper and one gate in the large native
GL owner; no separable responsibility or dependency is added there.

Oct21 current rig validation: video On60s → Off Abort5s → On60s retains required
stimulus scientific evidence in all modes, with no encoder in Off; all six combined
videos decode/count exactly, zero requested/actual image mismatches and zero capture
drops in the bounded dummy. Maximum state intervals are36.8833/33.3202/26.6106ms.
The unchanged full20min protocol did not start: long-path output reservation then
MCU PING/cleanup failures block acceptance. No full-texture or optical pass claimed.
See the [combined assessment](runtime.md#current-rig-validation--2026-10-21).


Oct21 `preview-frame-details`: [V01rev30](../docs/architecture/visual_stimulus.md#v01)
adds source/preview FPS to existing exact-session preview state. Completed render
batches and preview swaps feed the shared meter; optional roughly-one-second reports use
the existing bounded worker bridge. They do not block rendering or change scientific
timing/health authority. ARCH-002 cohesion review retains small native-owner and worker
lifecycle hooks in those existing large owners; measurement is separated in
shared/preview_rates.py. Focused rendering/lifecycle, projection and authenticated
transport checks pass (commands/results in LOG). Native appearance and rates need
application/backend restart and remain E15 acceptance work; no running experiment was
restarted for this change.

Oct21 `stimulus-preview-initial-placement`: [V01rev29](../docs/architecture/visual_stimulus.md#v01)
fixes a source-confirmed show-order defect: WindowsPreviewOwner construction can
show its child before placement, and the old GLFW show preceded native frame
correction. Size and visible-frame position now precede owner binding and Show;
Win32 no longer first applies GLFW client-origin coordinates. Manual-move opt-out,
explicit Snap and reopen reset remain covered. ARCH-002 reorders existing operations
in the focused preview owner without new dependencies or lifecycle state.
103 local rendering tests pass (one Windows-marked case excluded), including initial
placement order, manual movement, Snap, reopen, native-close and failed-release
ownership. Ruff lint/format2, Win32 mypy1 and boundaries742/zero pass. A bounded native
GLFW NO_API probe created a hidden300x300 window, positioned its visible frame at
(410,220), showed/polled it and read exactly(410,220), then destroyed it. This proves
first-show frame positioning on this desktop, not renderer/OpenGL, alternate-DPI or
live experiment acceptance. Existing [rig checks](rig-verification.md) remain open.
Application not restarted; no experiment operation sent.


Oct21 `setup-watchdog-cleanup`: [V01rev28](../docs/architecture/visual_stimulus.md#v01)
binds cleanup before Visual Stimulus Setup dispatch. The renderer verifies native
release before confirming an empty session catalogue; the coordinator registers
that catalogue with the supervisor, and the controller retains the dispatch fact.
Dispatched resources/outputs and every registered participant still require exact
cleanup. Native missing-camera failure/reuse, Ready cancellation, recorded10s Abort
and fresh60s normal playback pass; both stimulus videos fully decode with matching
600/3,600-frame counts. Final native GUI inspection confirms terminal log rows
and fresh-Setup gating. The original intermittent PING cause and full
texture-workload/optical acceptance remain open. See the
[combined assessment](runtime.md) and
[evidence](runtime-evidence-2026-10-21/setup-recovery/output-verification.json).

Oct21 `pilot-spikeglx-alignment-inspection`: full SP0003-123824 logs have contiguous
Right-only markers and current images; analog photodiode candidate transition
counts match both trials after short-window averaging. Digital threshold chatter,
analog clipping, candidate-fit outliers and unobserved same-level boundaries
require explicit optical QC; other projectors have no measured optical anchor.
Evaluation gaps reach355.121/94.983 ms despite zero video drops. See the
[current inspection and evidence](runtime.md#pilot-spikeglx-alignment-inspection--2026-10-21)
and [rig follow-up](rig-verification.md#pilot-synchronization-verification).

## Primate/cuttlebase texture mismatch — 2026-10-21

Oct21 `setup-texture-progress`: [V04rev20](../docs/architecture/visual_stimulus.md#v04)
and [E08rev178](../docs/architecture/system-contracts.md#e08) retain initial decode,
upload and GPU-fence completion before Ready, now with visible stages and counts.
CPU Setup validates all authored images (compatible repeated images reuse validation);
graphics Setup fills the bounded initial cache, including every first-use anchor.
Counts distinguish per-trial validation from initial GPU residency; they are not a
percentage of the whole protocol. Later images continue bounded prefetch during playback.
The worker sends at most one optional progress report in flight through existing
operation RPCs; repeated counts are throttled to one second, stage/completion changes
emit promptly. Controller generation/session/command/deadline checks publish the
existing participant progress field consumed by the GUI action log. Delivery failure
cannot fail Setup, and progress grants no Ready/completion or health evidence.
ARCH-002 review keeps formatting/throttling and controller admission in focused
helpers; existing resource/session orchestrators only call them. Resource prepare's
509-line warning reflects its cohesive file-to-manifest pipeline; no new dependency,
runtime state machine, configuration key or schema was added.

Validation: combined renderer/controller suite 1,195 passed, 4 skipped, 8 deselected;
10 offscreen GUI action-log checks pass. A final preservation of first-service
cancellation/deadline ordering passes 159 renderer/lifecycle checks. Ruff lint/format
323 files, Win32 mypy277 sources, boundaries742/zero and whitespace checks pass.
An earlier combined run hit the existing 20 ms reservation-thread scheduling test
(1,193 passed); it passed alone and on the final combined rerun. An initial callback
type-inference error was corrected before the passing static run.
[Raw test results](visual-stimulus-evidence-2026-10-21/texture-mismatch/setup-progress-tests.txt)
and [source/command context](visual-stimulus-evidence-2026-10-21/texture-mismatch/setup-progress-context.json)
retain scope. No app restart or native visible-progress/full-protocol run was made;
those remain in the [rig checklist](rig-verification.md).

Owner session `SP0003-145623` (20261020_ephys-pilot) confirms actual renderer
selection divergence, not merely preview labels. Read-only full JSONL inspection
of both trials found 16,381/18,016 and 16,410/18,001 texture render groups with
mixed image families across outputs. At least one mixed group occurs in 923/1,000
Primate and 933/1,000 Cuttlebase texture presentations; 887 and 878 respectively
are mixed in every observed group. Grey intervals are excluded. All prepared
texture epochs and all recorded requested selections agree across the four image
families. Desktop/saved programs differ only by presence of GUI sequence metadata
keys (batch/repetition/subgroup fields); no differing shared values were found.

Example: first trial at 18.6006314 s, occurrence62, requests image193 on all four
screens; Left retains image139 while Front/Right/Bottom select193. Records explicitly
label the stale selection `residency_hold`. Under [V04](../docs/architecture/visual_stimulus.md#v04),
`ImageResidency.select` selects independently per instance and holds its previous
texture when the requested resource is not resident, without delaying the clock.
This explains mixed screen content. The protocol alternates300 ms texture/300 ms
grey. Dedicated measurements below identify the upload throttle; recorded selections
alone do not isolate loading-stage costs. The recorded renderer source fingerprint
is retained in [asset verification](visual-stimulus-evidence-2026-10-21/texture-mismatch/asset-verification.json),
but no exact Git revision is recorded; the inspection tree is dirty. All664 tested
source images match the saved recipe hashes and sizes.

[Reproducible inspection and hashes](visual-stimulus-evidence-2026-10-21/texture-mismatch/summary.json)
and its adjacent `inspect_session.py` retain counts, affected zero-based epoch IDs,
examples and provenance. Method: repository Python3.11, full parse of both renderer
JSONLs and prepared recipes, consistency assertions, no runtime/device commands.
Renderer evidence is not optical measurement; historical MP4s were not decoded.
Planned epoch labels alone do not establish delivered stimulus identity for this session.

The confirmed upload bottleneck was one 1 MiB chunk per render update: the four
images expand to 41,297,200 bytes and required 45 upload turns, or 750 ms at 60 Hz
before decode, against a new set every 600 ms. Representative native decoding
cost about 113 ms per set; GPU transfer calls themselves took only milliseconds.
[Original uploads](visual-stimulus-evidence-2026-10-21/texture-mismatch/baseline-upload.json),
[corrected uploads](visual-stimulus-evidence-2026-10-21/texture-mismatch/final-upload.json)
and [one-chunk paced baseline](visual-stimulus-evidence-2026-10-21/texture-mismatch/baseline-cache.json)
retain measurements: the baseline has 1,025/1,480 mixed groups in the first 60 s of
each saved trial. Exact GPU pixel readback passes before and after the change.

[V04 revision 19](../docs/architecture/visual_stimulus.md#v04) / E14 policy 19 now
bound a turn to four 1 MiB chunks, reducing this set to 12 turns. Upload completion
skips trailing unused contexts; fences cover only contexts with actual allocations,
including partial uploads and retirement. Float32 RGBA, the single decoder, next-use
prefetch, first/held anchors, resource budgets, clocks and late-image evidence remain
unchanged. ARCH-002 retains the existing focused GPU owner and explicit texture-list
interface, with no new dependency or process.

A remaining pause was isolated to a 104.10 ms generation-2 garbage collection in
the loader thread, which blocks other Python execution under the GIL. The
[GC trace](visual-stimulus-evidence-2026-10-21/texture-mismatch/final-cache-gc.json)
retains attribution. A small stdlib PreparedHeap owner now collects Setup garbage
within the original deadline, freezes the existing prepared graph after graphics
preparation, and unfreezes on cleanup (including failed/cancelled Setup). New objects
remain collectible, prior GC enablement is preserved, and foreign frozen ownership
is rejected. The existing preparation orchestrator delegates this separate concern;
its large-file cohesion exception is unchanged. Tests cover deadline/foreign-owner/
reuse and real isolated-interpreter collection of new cycles and release of old cycles.

[Final native result](visual-stimulus-evidence-2026-10-21/texture-mismatch/final-prepared-heap.json):
200 presentations, 3,600 texture render groups, zero holds/mixes and every tested
onset current, including the second-trial transition. Each saved trial ran 60 s
at requested 60 Hz with four hidden RTX 5060 Ti contexts and protected real PNGs.
The 1 GiB budget reserved 551,476,536 bytes for scene/review obligations; peak total
reservation was 1,069,647,336 bytes. Cache-service p99 was 1.91/1.82 ms, maxima
8.66/8.72 ms. No GC callback exceeded the probe's 5 ms reporting threshold.
This is not full-rig acceptance: no projector swaps, cameras, compositing or review
recording were performed, and other processes were not controlled. Intermediate
holds and long calls remain in dated evidence. Restart/fresh Setup and the complete
20-minute combined workload remain in the [rig checklist](rig-verification.md).

Final checks: 336 tests pass, 1 skipped, 1 rig/platform case deselected, plus 82
contract subtests. Ruff lint/format 177 files, Win32 mypy 161 sources, boundary check
746 modules/zero violations and whitespace/local-link checks pass. Existing large
backend owners are unchanged except focused preparation delegation; no new oversized
module is introduced. [Commands, source hashes and limits](visual-stimulus-evidence-2026-10-21/texture-mismatch/fix-context.json)
retain provenance, regression failures and intermediate attempts. The application
was not restarted and no protocol/image/calibration values were changed.

For this workload, bounded ahead-of-time preparation is preferable to retaining
all used float32 RGBA images (9.19+9.23 GiB across both trials) under the1 GiB
configured asset budget. [PsychoPy timing guidance](https://psychopy.org/general/timing/reducingFrameDrops.html)
recommends preparation before onset and expensive updates during intervals;
[StaticPeriod](https://psychopy.org/api/core.html#psychopy.core.StaticPeriod) explicitly
accounts for loading time and reports overruns. [Psychtoolbox PreloadTextures](https://psychtoolbox.org/docs/Screen-PreloadTextures)
uploads textures before a trial and reports residency success subject to VRAM.
These approaches do not themselves guarantee optical synchronization of independent
projectors. V04's existing per-instance late-image evidence/fallback remains unchanged;
an atomic fallback or fail-on-miss experiment policy would require a separate choice.


Oct21 `quiet-recording-metrics`: owner requested no terminal recording_metrics JSON.
Removed the recording-thread summary emission and its dedicated renderer logger
setup. Internal capture metrics, V12/E13 evidence, output closure and error handling
remain unchanged. ARCH-002 removes now-unused logger plumbing without dependencies
or new policy. Existing recording tests retain cleanup/evidence assertions and check
that cancellation emits no metrics summary.73 recording tests pass with native file
access; scoped Ruff lint/format16, Win32 mypy15 and boundaries741/zero pass.
Initial local run exposed an accidentally removed live metrics alias (restored) and
sandbox extended-path publication failures; final checks pass. Runtime not restarted.

Oct20 playback follow-up: owner retained log since497633616783900 confirms Setup
8d62c7cb-805e-4ec2-a02d-276960852ba8 Ready and StartSession
63918951-4b22-407f-98e4-baf6adf44f6f activated, followed by cannot-add-resources-after-Ready,
Stopped-conditions-missing and unregistered-cleanup errors. Source identifies lazy
ImageResidency.service registering each GPU obligation on first allocation, including
future images first loaded during playback. V04rev18/E08 now predeclare all planned
GPU identities at attach during Setup (one batch through the existing preparation
callback). Lazy allocation/eviction and1GiB budget remain unchanged; GL owner retains
release proof for never-allocated entries and does not claim fenced/live allocations
released prematurely. CPU preparation does not own these GPU release facts.

202 rendering/lifecycle/resource tests pass,1 native deselected: a sealed registration
callback rejects any playback addition while the bounded-cache test loads future
images; both single/batch registration paths covered. Cleanup test verifies never-
allocated releases while failed fences retain allocated obligations. Initial lifecycle
assertion expected old individual announcements, updated to verify the batch instead.
Ruff/format, Win32 mypy2 pass; boundary checker740/zero. ARCH-002 reuses existing
residency/attachment/preparation callback without new state machine/dependency;
session.py remains the existing cohesive resource-lifetime owner above500 lines.
Memory admission and Setup/Start now have owner-provided native evidence, but full
playback, Stopped evidence and cleanup after reload remain unverified.

Oct20 `setup-watchdog-cleanup`, output-specific GPU allocation: owner screenshot
confirms minimum image residency budget rejection. Source review found each source
uploaded to all four contexts regardless of consuming surfaces. V04rev17 now scopes
ImageSchedule's immutable source records to the union of consuming outputs across
trials/epochs, accounts only those copies, and ImageGpu preserves output-indexed
bindings with empty unconsumed slots. Release skips empty slots, retaining existing
fence and failed-resource retry semantics. No format/precision, timing, cache-budget
or physical-screen behavior change. ARCH-002 uses existing schedule/upload owners;
no dependencies or new configuration. No modified module crosses500 lines.

[Calculation](runtime-evidence-2026-10-20/gpu-memory/calculation.json) and its
[reproduction script](runtime-evidence-2026-10-20/gpu-memory/calculate.py) use the saved
Pedro20min protocol and retained calibrated display snapshot. CPU preparation of1920
source assets completed in63.55s without native GPU operations. Fixed scene/preview/
calibration reservations426,138,936 bytes; two review capture allocations125,337,600;
minimum images165,188,800 (82,594,400 anchors +41,297,200 held +41,297,200 next).
Total minimum716,665,336 bytes =683.465MiB, versus1,212,231,736 =1156.074MiB before
output scoping; existing1GiB limit therefore admits the calculated working set.
Image texture copies fall75% for single-screen crops. Prefetch can grow toward the
budget; this is minimum accounted memory, not measured peak VRAM or driver overhead.
Review calculation includes both trials at1280x720, RGBA8,15 slots. Native Setup must
confirm effective display/calibration unchanged and actual rendering/cleanup.

201 rendering/resource/lifecycle tests pass,1 native test deselected; union sharing,
physical/angular surfaces, sparse indices and release covered. Ruff/check/format,
Win32 mypy4 and boundaries740/zero pass. First calculation reached completion but
failed formatting unused-source output metadata; rerun corrected evidence and uses
recording layout rather than preview layout for recording buffers. Source tests and
calculation do not establish a physical rig pass. Numerical capacity errors now
include fixed/image/total/limit bytes for future diagnostics.

Oct20 latest log check: [emergency496983556709800](emergency-496983556709800-d4fe31b4-f81c-47f5-8500-2fe8b9c0eca5.json)
(controller c401b963-bd3d-4422-a5bd-39047d86a851,14:35:46 JST) contains three
ReportWorkerLifecycle INCOMPLETE_CLEANUP errors and unconfirmed SpikeGLX stop.
No original Setup error or RPC timeout is present. Launcher recovery record for that
generation reports all_owned_processes_absent=true at14:36:37 JST; process absence
is not proof of resource/output cleanup. Config/runtime source edits predate launch,
but this report does not show the effective Setup policy. No newer emergency report
found in reports. Requested first GUI Setup-failed line to determine trigger; no
new code change or native success claim from this evidence.

Oct20 next attempt [emergency evidence](emergency-496811385853700-5cdaf1f0-6254-45e6-bcc7-ef40924a9cac.json)
records ReportWorkerOperation with its original peer deadline already expired.
This report does not reveal the retained executor failure; it establishes that
post-execution delivery triggered renderer loss. Runtime now skips an already-expired
result send after retaining the exact executor outcome, leaving the existing E06
query path available. It neither renews execution deadlines nor claims cleanup; actual
in-budget receipt loss still follows the existing failure path. Owner explicitly
approved Setup180s (E06rev78), replacing60s in experiment_config.toml; trial timing and
cleanup/recovery budgets unchanged.35 configuration/transport tests pass, including
expired delivery and existing receipt-loss behavior; Ruff/format, Win32 mypy1 and
boundaries740/zero pass. ARCH-002 keeps the existing ledger/query owner without new
state/dependencies; runtime module remains below the cohesion warning threshold.
Full texture Setup and native cleanup remain unverified after reload.

Oct20 next renderer attempt: [emergency report](emergency-496554628674800-c3caaf3a-1259-4e3f-b68d-907a27778209.json)
identifies ReportWorkerHeartbeat:389,959 bytes,6.934ms remaining deadline and11.613ms
elapsed. This establishes exhausted remaining Setup time at resource registration;
it does not measure the preceding preparation stages or prove memory exhaustion.
The prior asset release error is absent, but supervisor cleanup is still unconfirmed.
E08 permits multiple append-only obligations per revision: NativePreparation now
predeclares authored asset intents per trial, waits for one batch receipt, then uses
the unchanged protected-source opening/validation path. Transitive discovered assets
still register before creation. Lifecycle's single and batch paths share exact identity,
Ready sealing and original deadline checks. No timeout or memory-policy change.
ARCH-002 adds the callback through existing preparation ports; session/lifecycle remain
cohesive existing owners despite size warnings.172 resource/lifecycle/coordinator/
communication tests pass, including1,920-resource single-receipt/repeated-key identity
checks and native preparer batch wiring. Ruff/format, Win32 mypy4 and boundaries740/zero
pass after fixing callback typing/formatting. Full-workload Setup duration and native
cleanup still require rig evidence; this removes repeated catalogue transfer work,
not every possible preparation bottleneck.

Oct20 renderer-exit follow-up: [raw emergency report](emergency-496221647855400-f4487176-3678-4f2e-aa70-e21f515d48c0.json)
for controller faed0faf-a80c-42b7-9e73-6996bcd06d7e records RPC DEADLINE_EXCEEDED
and unconfirmed asset image_222_bottom. It does not identify the RPC or prove a
native crash, GPU exhaustion, or the reason for the timeout. Source review finds
NativePreparation recorded resource intent only after announcement returned; the
worker records it before awaiting receipt. A lost receipt therefore left an obligation
without local never-created release evidence. Resource owner now retains intent before
announcement; creation still waits for accepted registration, and failed live-source
closure remains unconfirmed (E08/V01). ReportBridge failures now identify RPC,
elapsed/budget milliseconds and message bytes while retaining the original exception
and deadline. ARCH-002 keeps ownership in existing modules; session.py's existing
cohesive resource lifetime owner remains above the size warning threshold, with only
statement ordering changed. Resource/lifecycle106 tests and coordinator/transport74
tests pass. Initial3 fixture errors were corrected by generating demo assets outside
the repository; Ruff/format and Win32 mypy pass. The originating timeout remains
unresolved; full Setup and failure cleanup require rig verification after reload.

Oct20 owner Setup log advances through camera preparation, then fails on the
supervisor's cleanup catalogue capacity. The shared 256-history-entry bound and
registration reply reservation are corrected in the existing supervisor owners;
see [runtime evidence](runtime.md) and E08 rev177. No asset obligations are omitted,
and the byte budget remains enforced. Local 2,049-resource registration/cleanup
passes; full texture-session Setup on the rig remains unverified.

Oct20 `setup-watchdog-cleanup`: profiling the actual two-trial texture protocol found
condition substitution repeatedly rebuilding unchanged frozen settings. Existing
expansion now reuses unchanged frozen models/tuples; changed paths still undergo strict
validation, preserving condition ordering and source immutability under V08/ARCH-002.
No cache, new dependency or process. Local four-batch controller validation improved
1.940s to1.415s; maximum observer-thread pause58.84ms to41.63ms. This demonstrates
avoidable load, not the cause or resolution of the serial timeout.80 affected compiler,
configuration and acquisition recovery cases pass; static checks pass. Native Setup
pending. [Probe evidence](runtime-evidence-2026-10-20/setup-watchdog/validation-load.json).

Oct20 `visual-stimulus-gpu-budget`: owner requested raising the GPU resource ceiling
after Setup reported551476536/536870912 bytes at scene-surfaces. Changed only
resources.max_asset_gpu_bytes in visual_stimulus_config.toml to1073741824 (1GiB),
an operator capacity under [E14](../docs/architecture/system-contracts.md#e14).
TOML parsing and the owning load_file_policies loader confirm the new value and
valid policy binding. Fresh Setup adopts it; no active allocation or prepared session
was modified. Capacity/performance and successful Setup remain unverified.
The supplied INCOMPLETE_CLEANUP, COMMAND_ADMISSION and IDENTITY warnings are retained
failure evidence, not resolved by a larger budget. Matching emergency report:
[emergency evidence](emergency-489843786873500-fd741bf6-3bde-4e72-940a-8a32f9e8e3be.json).
Recovery/cleanup must finish before retrying; no recovery action was executed here.

Oct20 `protocol-final-gap`: owner's Setup screenshot exposed an artifact defect:
generated protocols set final gap_after_seconds to the nonempty string "0".
G01's GUI apply_schedule rejects any final gap, including zero; structural file
validation did not cover this submission rule. Corrected only the final field to
empty in the dummy, Gaussian and Primate/Cuttlebase Desktop/Pedro files and the
two repository protocol copies; natural-texture reproduction now clears it too.
Original failure reproduced and actual ProtocolPage.apply_schedule passes with
real draft/program/Protobuf models for all three schedules (1,3,4 trials).
Lightweight UI-value stand-ins were used; this is local submission validation,
not live GUI load or rig Setup. Existing loaded drafts must be reloaded.
[Verification](runtime-evidence-2026-10-20/protocol-final-gap/verification.json).
This correction supersedes earlier artifact hashes and structural-only validation;
stimulus timing, motion, assets and calibration are unchanged.

Oct20 `bottom-preview-orientation`: owner confirms the dummy trial moves correctly
on the physical rig with the existing calibration (Bottom Y inversion off).
The preview's Bottom raster placement added a reflection along surface X.
[G01](../docs/architecture/gui.md#g01) rev257 removes that extra reflection by
undoing only the portrait quarter-turn, preserving calibrated output flips.
Only PreviewRig's corner order changes; renderer, projector profiles and protocol
motion are unchanged. ARCH-002 review finds the existing small placement method
cohesive; no new helper/state/dependency is needed. Existing oversized-module
boundary advisories are unrelated and no source module was enlarged.

Extended the existing owning pixel-placement test to both axes: before the fix,
only the two Bottom-X cases fail; after it,25 preview/motion tests pass. Ruff check/
format, Windows-target mypy and backend boundaries740/zero pass. Initial wider
pytest attempt had3 temp-directory fixture errors; rerun with a dedicated workspace
basetemp passes. The running GUI has not been restarted; native preview confirmation
after restart remains pending. Owner's physical confirmation is not an instrumented
optical measurement and does not close pitch/mask/tearing checks.
[Evidence](runtime-evidence-2026-10-20/bottom-preview-orientation/preview-fix-validation.json).

The owner-requested dummy direction trial (repository copy removed during the
2026-10-27 disposable-file cleanup; tracked history remains available)
was also saved as Desktop/Pedro/dummy_bottom_direction_95s.json under
[G01](../docs/architecture/gui.md#g01) and [V02](../docs/architecture/visual_stimulus.md#v02).
It uses scale15 Gaussian textures with Bottom-linked followers:5s initial static,
then each signed Bottom X/Y translation at30mm/s and signed rotation at10deg/s
for10s, each followed by5s static (13 epochs,95s). Epoch names state source signs,
not unverified physical directions. GUI validation, parsing, expansion, asset existence,
rate checks and byte-identical Desktop copy pass. Calibration files and other
protocols were not changed by the preview fix. Owner confirms rig motion; compare the
restarted preview under the same current calibration. [Validation/timeline](runtime-evidence-2026-10-20/bottom-preview-orientation/dummy-protocol-validation.json).
Existing [rig direction acceptance](rig-verification.md) and separate speed finding remain open.

Oct20 `natural-texture-screen-crops`: completed owner-requested separate session
under [G01](../docs/architecture/gui.md#g01) and [V02/V03](../docs/architecture/visual_stimulus.md#v02).
Desktop/Pedro/media/{primate,cuttlebase} each contains960 PNGs: all240 originals
cropped to Front760x690, Left1030x680, Right1025x695 and Bottom685x940.
Saved Pedro calibration matches runtime_gui; crop boxes form a centered contiguous
Left/Front/Right cross with Bottom centered below Front. Exact native grayscale
samples are retained without resampling; projector offsets stay in calibration.
The source/output hashes, boxes and reproducible ordering are in each manifest.

Desktop/Pedro/primate_cuttlebase_40min.json is a separate Open-loop session:
20min Primate then20min Cuttlebase, each2000 pairs of300ms image/300ms grey.
All four image assets in a pair come from one original. Each collection uses160
images eight times and80 images nine times, globally shuffled with saved seeds.
Untagged PNG samples explicitly use sRGB; grey is127/255 sRGB, encoded as the
corresponding linear background. Physical image extents follow measured pitches;
Bottom uses the calibrated90-degree surface-to-portrait coordinate mapping.

Each collection is split into two10min trials with zero authored gaps: the original
20min source/epoch/boundary serialization alone exceeded the existing8MiB prepared
artifact cap. Each final block's corresponding partial size is4.64MB; full resource
manifests and native Setup remain untested. No resource limit/runtime change was made.
Gaussian protocol bytes remain unchanged. All1920 saved crops pass source-pixel equality;
GUI validation, canonical parsing, full expansion (8000 epochs/2400s), per-image
frequencies and same-source four-screen grouping pass. Eight representative crops
also pass the actual backend image decoder. Initial preparation used two20min trials;
size inspection identified the limit and the final file uses four10min blocks.
No GUI load, full resource preparation or physical presentation pass is claimed;
existing [rig acceptance](rig-verification.md) remains separate.
[Verification](runtime-evidence-2026-10-20/natural-texture-screen-crops/verification.json),
[reproduction script](runtime-evidence-2026-10-20/natural-texture-screen-crops/prepare.py),
[initial inventory](runtime-evidence-2026-10-20/natural-texture-screen-crops/inventory.json).

Oct20 `gaussian-three-trial-protocol`: created the requested [loadable protocol](../protocols/gaussian_scale15_bottom_linked_3_trials.json) under
[G01](../docs/architecture/gui.md#g01) and [V02/V07](../docs/architecture/visual_stimulus.md#v02).
All four scale-15 Gaussian textures link motion to Bottom; baseline is900s,
then100 repetitions each of10s movement followed by20s static for translation
(30mm/s along Bottom X, both signs) and rotation (10deg/s, both signs).
Independent saved direction draws use seeds20261021/20261022; counts are54/46
and59/41, without enforced balance. Same instance/asset identities and reset=false
retain state at static boundaries. Total6900s, zero authored inter-trial gaps.
GUI file validation, canonical parsing and expansion verify1/200/200 epochs and
requested timing/motion; the external scale-15 recipe exists. No runtime code or
dependencies changed. Native load/Setup and physical motion remain untested;
existing [rig checks](rig-verification.md) and speed finding remain open.
[Validation evidence](runtime-evidence-2026-10-20/gaussian-three-trial-protocol/verification.json).

Oct19 `gui-full-rig-test`:600s Gaussian derivative uses20 repetitions of the
existing20s static/10s drift group, retaining accepted calibrated geometry/settings.
Four-output rendering and review encoding produce36001 groups/144004 submissions;
capture/capacity drops, omissions, duplicates and unresolved groups are zero. Full
1280×720 h264 yuvj444p review decode/count passes (600.016667s =36001/60).
Software evaluation-gap median16.659ms, p9919.732ms, max51.765ms; two gaps exceed25ms,
none100ms. Both worst gaps are mainly before first swap; no optical cause or perfect
frame-timing claim follows. All29 resource fingerprints and exact source recipe JSON
match. Current telemetry supports bounded rendering/encoding measurements, with the
first40s missing and scientific Tracking disabled. Original configuration restored.
No renderer/pacing change was justified. Physical speed/tearing/alignment acceptance
and representative full scientific load remain open.
[Assessment](runtime-evidence-2026-10-19/gui-full-rig/native-assessment.json),
[resource/association audit](runtime-evidence-2026-10-19/gui-full-rig/association-assessment.json),
[verification](runtime-evidence-2026-10-19/gui-full-rig/verification.json),
[outstanding rig work](rig-verification.md).

Oct19 `camera-finalization-stimulus-timing-check`: current native software cadence
checked with all3 camera videos and four projector outputs, under
[E13](../docs/architecture/visual_stimulus.md#e13), V10/V12/V28 and E15. Corrected
camera-runtime runs retain671/675/3602 render groups. Median/99th-percentile cadence
and individual worst gaps are in the [native assessment](runtime-evidence-2026-10-19/camera-timing-verification/fixed-run/native-assessment.json).
Max gaps are54.5658/25.8199/48.3826ms; p99 is19.2888/19.0619/18.915ms, with no gap
over100ms. The historical649.2921ms stall did not recur. Historical decomposition
places645.567ms before the first swap, within one static epoch; swap itself peaks
0.8991ms for that group. Its unique cause remains unknown; this is not evidence
that the old stall never recurs. No speculative renderer/pacing change was made.

First Abort run records one startup review-video capacity drop (15/15 slot peak):
670 encoded images for671 render states. All states remain saved. Next Abort and
normal60s encode675/3602 groups with zero capacity drops. All3 stimulus MP4s fully
decode and match submitted encoder counts. Capture loss, renderer cadence and
physical presentation are distinct; occasional25-55ms software gaps mean perfect
frame timing is not established. No instrumented optical/electrical measurements,
Tracking/SpikeGLX workload or full-duration scientific endurance was performed.
Owner confirms photometric calibration works; the old recipe label alone is not a
current calibration defect. Current configuration restored exactly.
[Checks and retained raw evidence](runtime-evidence-2026-10-19/camera-timing-verification/verification.json).


Oct19 `texture-rig-geometry-motion`: [V02](../docs/architecture/visual_stimulus.md#v02)
rev14 and the linked-motion contract now use the reference screen's geometric
center and signed perpendicular distances to target planes for angular flow.
Removed observer dependence from both rates and retained-pivot validation; physical
map translation determines the required texture-space pivot. Reused the existing
compiler/runtime helper and state ownership without new settings/dependencies
(ARCH-002). Drift remains physical mm/s with per-output calibration. Existing
programs with an explicitly subject-centered, off-screen-center spin pivot must
correct that center/reset before Setup; no silent migration. Added coverage for
observer invariance, moved rig planes/center, mapped pivots and runtime integration.
All436 non-Windows/non-rig Visual Stimulus tests pass (2 deselected); Ruff check/
format2, Windows-target mypy1 and boundaries735/zero pass. Existing oversized-owner
advisories are unchanged; this focused helper remains below the review threshold.
Initial sandboxed full-suite run stalled after33 tests and was interrupted; the
permitted rerun completed. Live runtime was not restarted and physical acceptance
remains pending. This angular-motion correction does not establish the cause of
the separately reported linear Front/Bottom speed discrepancy below.


Oct27 owner-deferred `stimulus-physical-speed-mismatch` (reported Oct19): owner observes Front downward motion
faster than Bottom backward motion on physical screens. Earlier synthetic checks
cannot close this finding. Read-only inspection of DUMMY_2_161013's actual logged
phase/period/clip uniforms over1.0005195s infers50 mm/s on both surfaces under its
saved calibration: Front0.122222 mm/pixel (409.091 pixels/s), Bottom0.1375 mm/pixel
(363.636 pixels/s). [Evidence](runtime-evidence-2026-10-19/stimulus-drift-speed/saved-motion.json)
identifies source and recipe hash. This older saved trial is not confirmed as the
current live configuration. Owner confirms current reference measurements are
Front Y22 mm/180 pixels and Bottom Y44 mm/320 pixels. Final recorded-pixel template
matching at three20.5-22.7s intervals gives Front50.0-50.2 and Bottom49.4-49.6 mm/s
within integer-pixel uncertainty (up to2 native pixels), using logged host intervals
and a zero-drop/duplicate/omission encoder outcome. Correlations exceed0.99;
[recorded-pixel evidence](runtime-evidence-2026-10-19/stimulus-drift-speed/recorded-pixel-motion.json).
This checks the recorded GPU result beyond the previous uniform arithmetic, not
optical motion. Need a same-measured-distance travel comparison on the physical
screens and current session binding. No cause established, corrective multiplier
applied or live output changed. V15 is not proof of optical speed. Owner deferred
the physical comparison on Oct27; resume only on explicit request.


Oct19 `pre-experiment-output-audit`: four retained Desktop dummy sessions contain
required recipe/state files and their planned review MP4s under
[E13](../docs/architecture/visual_stimulus.md#e13), V12/V13/V28. Recipe byte lengths/
SHA-256 match the evidence references; all29 resource fingerprints per recipe match
currently available external originals. Every review video fully decodes and its
frame count equals retained render groups (4830/2462/2059/1884). Recorded completion
has zero capture drops/unresolved attempts; group IDs are contiguous and all logged
presentation calls returned. These are software submission/recording facts, not
physical presentation or exact-pixel proof.

A timing concern requires bounded investigation before timing-sensitive experiments:
DUMMY_2-160507 has a649.2921ms maximum state-evaluation gap, four gaps over100ms,
and2059 rendered groups across35.621s. 155008 peaks129.844ms; latest160948 peaks
33.049ms. Zero capture drops does not mean uninterrupted rendering. Cause/physical
impact are unverified; continue existing rig timing acceptance rather than infer
encoder loss. All four historical recipes explicitly use photometric_mode=uncalibrated.
The owner confirms photometric calibration is working; that historical label alone
is not a current calibration defect or outstanding acceptance blocker. Preserve
external originals: fingerprints verify availability today, not archival retention.
[Read-only audit and exact evidence](runtime-evidence-2026-10-19/output-audit/assessment.json).
No projector commands, optical measurements, replay/export or full-duration run.



Oct19 `stimulus-calibrated-drift-speed`: [V15](../docs/architecture/visual_stimulus.md#v15)
rev22 makes the existing per-projector physical drift mapping explicit. Independent
and V02-linked texture rates stay in physical coordinates; measured X/Y pitch,
usable geometry and output mapping convert to pixels exactly once. No second
speed multiplier or runtime state was added (ARCH-002). The GUI speed tooltip
explains measured calibration and fresh Setup. Regression coverage follows linked
or independent diagonal drift through unequal anisotropic pitches, cropped/offset
affine maps and portrait Bottom rotation, checking 50 mm displacement in one second
while pixel displacements differ. Nine focused GUI/calibration tests and all20
compilation tests pass. Ruff check/format2, Win32 mypy1 and boundaries734/zero pass;
existing size advisories concern unchanged owners, with no responsibility added to
them. Initial new fixtures omitted required screen dimensions; corrected before
passing. These are mathematical mapping tests, not optical or live presentation
measurements; rig accuracy remains pending in [rig verification](rig-verification.md).

Oct19 `preview-image-flips`: E13rev30 applies horizontal mirrors to Left/Right
and a vertical mirror to Bottom in native preview composition only; Front,
projection and recording remain unchanged. Uses existing compositor uniforms and
layout kind/surface labels, no new schema/dependency/state owner (ARCH-002).
Standalone Windows GL test checks asymmetric quadrant pixels on all four preview
tiles and unchanged recording pixels/readback; passes.89 renderer unit tests pass;
Ruff/format2, Win32 mypy1 and boundaries734/zero pass. Existing cohesive-size
advisories unchanged. No live GUI restart or optical acceptance performed.

Oct19 `stimulus-composite-preview`: implements the owner's revised choice under
[E13](../docs/architecture/visual_stimulus.md#e13),
[V01](../docs/architecture/visual_stimulus.md#v01),
[V12](../docs/architecture/visual_stimulus.md#v12) and
[G01](../docs/architecture/gui.md#g01). Dashboard Visual stimulus uses a renderer-owned
native window after Setup: calibrated crops in Left–Front–Right / Bottom arrangement.
Recording uses uncropped full outputs in equal 2x2 cells, Bottom rotated 90 degrees
clockwise. Layout3 has no labels/header strips; matching post-rotation dimensions
fill adjoining cells exactly. Preview also omits labels and label-strip spacing. Separate targets share one compositor
implementation; projector pixels and video admission/accounting remain unchanged.
The recipe embeds both layouts, source/destination rectangles/rotation and protected
geometric/photometric values for later conversion. Policy pair18 and schema updated. Layout2 metadata remains readable.

Label-free follow-up:435 Visual Stimulus tests (2 deselected), one standalone GL
pixel test, scoped Ruff/format7, Win32 mypy160 and boundaries734/zero pass. The
rectangular fixture uses a portrait Bottom raster that matches the other landscape
rasters after rotation and asserts complete cell coverage. Native pixels allocate
no label textures. [Follow-up evidence](runtime-evidence-2026-10-19/stimulus-composite-preview/label-free-verification.json).
ARCH-002 keeps the geometry change in the existing pure helper; no new dependency.

Earlier integration baseline:571 scoped backend/client tests,82 preview GUI tests and2 explicit native pixel/cleanup
checks pass;12 policy checks pass after the final digest update. Ruff/format, Win32
mypy452 and boundaries734/zero pass. The GL check verifies preview-only cropping,
full recorded borders, Bottom rotation and captured row orientation. Metadata round-trip
checks need no source calibration files. Broader camera-test failures, sandbox retry
limits and exact commands/hashes are in the
[verification evidence](runtime-evidence-2026-10-19/stimulus-composite-preview/verification.json).
This is not a clean full-suite or full-workload rig pass.

ARCH-002: pure layout/metadata rules, native viewer ownership, controller authority
and GUI intents have focused owners with no runtime back-references or dependencies.
Existing large native/scene/worker/preparation modules retain only their established
GL/lifecycle orchestration; recording/native only uses the revised geometry provider.
No app restart, original-recording edit, physical projection or optical pass was made.
[Fresh-session preview/recording acceptance](rig-verification.md) remains pending;
the offline conversion script remains deferred.

Oct19 `texture-retain-static`: DUMMY-141422 recipe exactly matches the saved GUI
program and confirms separate static `stimulus_2/3/4/5` and drifting `Instance_1/2/3/4`
identities. At30s the compiled plan pauses drift and resumes the static instances
at their unchanged phase. Under [V07](../docs/architecture/visual_stimulus.md#v07),
Retain state applies per compatible instance; matching texture files alone do not
connect their state. Corrected only static instance IDs, their identical asset aliases
and scene references to reuse the drifting instances. Rates, timing, layer order,
texture recipes and all other settings remain unchanged. ARCH-002 favors this
protocol correction; no runtime changes or dependencies are needed.

Program parsing and exact semantic-diff assertions pass. Existing compiler and
runtime state/link handlers verify all199 internal boundaries across200 epochs:
all four states continue, every static interval holds its incoming phase, and every
drifting interval moves from that phase. GUI was closed; saved draft updated for
next launch with a byte-exact backup and an importable protocol. No native/optical
pass is claimed. [Evidence and corrected protocol](runtime-evidence-2026-10-19/texture-retain-static/)
and [physical acceptance](rig-verification.md).

Oct19 `bottom-direction-tearing`: owner confirms Bottom portrait top faces the head;
projector is below Right in the same physical orientation. Under
[G01 revision242](../docs/architecture/gui.md#g01)/[V15 revision21](../docs/architecture/visual_stimulus.md#v15),
GUI-generated Bottom mappings now rotate surface UVs before saved output flips.
Measured raw Y supplies physical depth and raw X the cross-span; current retained
values give129.25mm depth/91.333mm cross-span instead of the exchanged extents.
Preview places the corrected raster through the folded orientation. Trial/calibration
surface targets swap raster dimensions; live translations retain UV orientation and
pixel pitch. Raw reference bars/crops/offsets/masks/pulses and imported warps keep their
coordinate ownership. Linked source/follower motion is unchanged. No settings file
was edited; application restart and fresh Setup regenerate GUI profiles.

All432 local Visual Stimulus tests pass (1 deselected);99 affected GUI cases pass.
Scoped Ruff/format, Win32 mypy8 and boundaries724/zero pass. Focused direction tests check
four motion directions at the saved anisotropic pitch; native optical acceptance is
still pending. ARCH-002 reuses existing affine generation, resource builder and preview
helpers without dependencies or new state; scene_resources remains a cohesive GL
allocation owner. Detailed commands, source hashes and test receipts are in
[verification evidence](runtime-evidence-2026-10-19/bottom-direction-tearing/).

Original DUMMY-140646 evidence retains1932 groups with requested interval0 on
Front/Left/Bottom and1 on Right. Immediate swaps can tear under
[V20](../docs/architecture/visual_stimulus.md#v20); the existing all-output VSync option
is the comparison to run after cleanup/restart. Saved pulse-only mode is unchanged.
[Outstanding physical direction/pitch/tearing checks](rig-verification.md) remain open.

Oct19 `setup-scale15-recipe`: the newly pasted Setup failure identifies scale-15
`asset_6`; current saved GUI draft has eight scale-15 PNG references without a color
override, in addition to previously selected recipe assets. Applied the prior owner
recipe choice to these eight paths/profiles only; kept a byte-exact backup and
exported the corrected protocol for loading into the open GUI. Recipe, Asset and
all trial Program parsers pass; exact semantic diff confirms no other setting change.
This corrects the present draft and does not extend the earlier successful Setup
evidence to this larger protocol. Subsequently loaded corrected-protocol.json through
the native GUI Protocol Load dialog at owner request; Dashboard runtime log confirms
the path, and timeline shows 200 epochs/50 minutes. GUI remains Configuration;
Setup/Start were not clicked and controller history was not submitted. Under
[V13](../docs/architecture/visual_stimulus.md#v13), color validation still rejects
undeclared PNG encodings. Recipes can regenerate pixels differently from previews.
[Backup, corrected protocol and validation](runtime-evidence-2026-10-19/setup-scale15-recipe/verification.json).

Oct19 `preview-linked-fullscreen`: owner approved full-screen physical image-tile
textures in runtime and preview (V14 revision5); G01 revision240 binds preview links
through the runtime resolver with boundary/pivot validation. Whole-tile symmetric
extension covers calibrated surfaces under rotation/translation without stretching
periods or shifting phase; saved dimensions/configuration are not rewritten. GUI
brush Y anchoring now matches bottom-origin phase. Preview backward seeks replay
linked bindings; missing geometry rejects before playback.20 focused preview/coverage
cases and108 rendering/compilation cases pass. Saved actual protocol coverage passes
all four screens at six seeks with a white diagnostic tile; configuration byte equality
verified. Initial evidence script used strict Python validation on JSON lists; rerun
through model_validate_json succeeds. Ruff/format, Win32 mypy6 and boundaries724/zero
pass. ARCH-002 reuses the focused layer projection and canonical link helpers; no
new dependency or ownership. Existing scene orchestration remains cohesive.
Native inspection unavailable (Computer Use: foreground window did not report a
process id); GUI/runtime restart and physical output verification remain pending.
No live process restart, scientific config edits or staged promotion performed by
this change; concurrent work preserved. Evidence:
`runtime-evidence-2026-10-19/linked-fullscreen/verification.json`.


Oct19 shared GUI promotion implements per-output Frame/Pulse maps under
[V20](../docs/architecture/visual_stimulus.md#v20)/[V22](../docs/architecture/visual_stimulus.md#v22).
Every configured active output is bounds-checked and rendered with the group's
marker sequence; each submission keeps its own output/index/state/outcome evidence.
Explicit maps select every enabled pulse output for mixed VSync; blank/disabled
pulses request none. Legacy single-output profiles preserve their pacing behavior.
Portable rebinding and diagnostic updates retain all pulse screens; default files,
MCU ownership and physical input scope are unchanged. The complete local Visual
Stimulus suite passes427 tests (1 deselected); schema and contract checks pass.
[Evidence and scope](runtime-evidence-2026-10-19/shared-controls/context.json) remain
separate from [native/optical acceptance](rig-verification.md).

Oct19 Ponytail/Vulture maintenance removes two write-only cached display-limit
attributes. Preparation still uses request limits and its bounded budget; strict
asset-root resolution and protected resource retention remain unchanged under
[V15](../docs/architecture/visual_stimulus.md#v15)/[E14](../docs/architecture/system-contracts.md#e14).
Owning local tests pass; [caller review and validation scope](runtime.md#maintainability-review)
do not establish native/rig acceptance or performance.

Oct19 owner-selected GaussianNoise recipe replacement is complete:8 PNG asset
references now use the matching `.texture.json` and `cephvr1_texture_json_v1` profile.
Program/recipe parsing and exact candidate-diff assertions pass. Native Setup command
`be321de5-cf00-4a23-9276-fc1c4211ff0c` succeeds; session
`0813eb4e-fbbf-48e9-8642-ee975a7287fe` reaches Ready. Prior failed reservation required
administrative recovery preserving scientific files/unknown evidence. No trial was
started. Both saved configurations verify8 recipe references; corrected protocol was
also loaded into the open GUI, left on Ready. Other settings/staged scope are unchanged.
This supersedes the pending color-choice note below; recipe pixels need not match the
old PNG preview. [Raw evidence](runtime-evidence-2026-10-19/recipe-setup/verification.json).

Oct19 reported Setup failure is reproduced by an untagged PNG without color_override;
V13 rejects guessed color interpretation. Error now identifies asset/path and required
override. Saved GaussianNoise source has a sibling authoritative texture recipe naming
the PNG as preview; selecting the recipe is an alternative if intended, not a silent
pixel-equivalence substitution. Saved settings unchanged pending owner color intent.
Owning decoder regression passes. [Assessment](runtime.md).

Oct19 repair supplies missing GUI photodiode white/black RGB defaults, preserving
explicit values. Native texture-only 120-second preview trial completes with cleanup;
full saved-draft GUI Setup and optical timing remain unaccepted. Stimulus evidence
and recipe writers use extended paths; native >260-character filename tests pass,
but full long-root trial remains open. Subsequent240-second three-camera video-on
verification records14231 stimulus states/admissions, zero capture drops/same-slot
omissions/unresolved attempts at saved quality and15 slots. Tracking processing is
omitted; this does not certify optical timing or full-workload capacity. Saved defaults restore
exactly. See [assessment and evidence](runtime.md).

Oct17 owner selects `resources.capture_slots = 15` in the operator defaults for
a later rig test under V12/E14. Other settings and policy versions are unchanged.
This selection supersedes the restored three-slot baseline described in historical
evidence below; it does not change those results or certify zero-loss capacity.
Apply through fresh Setup; no rig run or running-session change was performed.

Current Oct17 concurrent acceptance run retains all 7200 real stimulus groups
exactly once over 120 s, alongside Behavior 3598/3598 and Tracking 7188/7188.
Rendering/projection and three encoders run concurrently; no capacity omissions,
duplicates or padding occur in this fixture. Its explicit temporary 16 capture
slots/half-resolution recording pass unchanged budgets. Saved three slots are
restored; their earlier startup limitation remains distinct and is not closed.
The saved lossy p4/CQ18 review recipe is unchanged under E13/V12/V28; GPU placement
remains SYS-002. Scientific JSONL is independent of optional review video.

The acquisition recording sync owner now independently services one flush per
exact file, with mandatory distinct final sync and strict timeout/closure proof.
Normal completed session, Cleanup/NewSession and Shutdown pass. All camera/settings
baselines restore exactly. Older acquisition Abort Finished, failed-Setup late
report and final Shutdown resource-registration triggers remain open. No optical,
external-trigger or Tracking-processing equivalence follows from software counts.
[Current assessment](runtime-evidence-2026-10-17/file-sync-fix/README.md),
[single outstanding checklist](rig-verification.md).

Historical Oct15 comprehensive recheck confirms fresh managed Idle initialization on
all four60Hz outputs with8-bit channels and swap interval1. This is software
submission evidence, not optical timing. The saved program's declared arena texture
requires715,827,840 GPU-budget bytes versus536,870,912 configured; Setup correctly
rejects it. Texture-only engineering variants remove unused declared arena
scene/instance/asset/boundary references; arena/combined variants require an explicit
smaller fixture rather than a silent budget increase. Failed-Setup long-path
cleanup/recovery is repaired in generated cancellation paths and lock-only startup
settlement with native before/after regressions; the original marker was immutably
backed up and explicitly removed only as this audit's unstarted artifact cleanup.
This is not general recovery acceptance. Fresh native60-second managed Gaussian
and mixed Gaussian/arena trials now complete on all four physical projector outputs
with both recording cameras; the arena uses an explicit512-pixel texture derivative,
retaining the original asset and budget. Save On→Off→On produces3→0→3 videos;
detailed frame/scientific logs remain enabled. Interrupted trials retain Interrupted
outcomes and complete output cleanup, with approximately40.12seconds metadata delay.
This establishes software submission/lifecycle evidence, not optical timing or
physical calibration accuracy. Post-session diagnostic reopening remains fenced.
Fresh native photodiode/blackout placement now pass invalid-bounds rejection then
valid live updates, move/remove and Close Idle/resourcesclosed with unchanged
asset/profile hashes. Safe worker prevalidation and typed owner/coordinator
propagation preserve proven Active state; generic/mismatched failures remain fatal.
Automated owner361 and managed-interpreter132 cases pass separately. The live
authenticated diagnostic run supplies native projector evidence; neither source
establishes GUI button-click or optical acceptance.
The final isolated60-second managed mixed-scene run completes with3600 decoded
review frames:3592 real/eight repeats, four capacity drops and two same-slot
omissions.3598 render groups have no unresolved submission attempts. The
[cross-owner benchmark](runtime.md) retains active-only CPU/GPU/RSS statistics,
per-stream saved codecs, three strict decode/count matches and exact restoration.
The later final Shutdown emits `cleanup returned an unregistered resource` despite
command success and exact process absence. This separate resource-report finding
remains open; it is not normal-shutdown acceptance. [Evidence](emergency-80538644376400-cf134742-126d-4fc6-aa22-c7ed8d33f493.json).
Independent capacity checks render four native-sized offscreen outputs through the
production layer shader and CPU-resize a review mosaic into a third NVENC stream;
they bypass calibrated projection/native presentation and the production recording
queue. Gaussian runs submit/decode3600 frames each at about60Hz; the separate20s
grating/native4096 case submits/decodes1199. All nine combined camera/stimulus
outputs fully decode. CQ23 GPU samples show5060Ti3–4%/339MiB and2080Ti encoder
45–52%/684MiB. CPU samples overlap another automated suite and do not establish
isolated workload cost/headroom; no CQ18 resource comparison is claimed.
Live-calibration explicit Update rejection is repaired without clearing the active
diagnostic block; owning cases cover three views and rejected/unknown outcomes.
[Fresh audit evidence](runtime-evidence-2026-10-15/comprehensive-audit/).

Oct16 `stimulus-sequential-recording` implements owner-approved
[E13 revision26](../docs/architecture/visual_stimulus.md#e13), with V12rev14,
V28rev7 and E14rev212/policy16. Retained usable composites now enter the MP4 once in
source-group order, including equal-time and repeated-content groups. Contiguous
zero-based indices are published only after a complete raw input frame is accepted.
Capacity drops and failed/cancelled readbacks consume no index; pending earlier
readbacks block later input ordering within the same fixed capture-slot bound.
There is no nominal-slot omission or leading/interior/trailing padding. Legacy
omission/duplicate counters stay zero, and closure requires full sequential count
reconciliation. A failed input or mapping publication cannot be retried as another
frame or promoted to successful closure.

Header6 and the MP4 writer schema3 distinguish the new correspondence; recipe schema2
is retained with `ffmpeg_rawvideo_sequential_v1`. The same `_stimulus_frames.jsonl`
provides `input_submitted.video_frame_index` → group → `state.evaluation_host_ns`
and exact per-output submission times, without a second timestamp file. Historical
Header3–5 remain readable under their original semantics. MP4 nominal playback rate
is unchanged but its duration is no longer scientific elapsed time. Video-off
scientific outputs, fragmented-MP4 closure, original deadlines and exact cutoff stay
in place. Crashed tail pixels/mappings remain unknown; no recovery/replay runtime is
added.

ARCH-002 removes the cadence/padding state and retained previous image, simplifying
the focused capture owner. No new
process, dependency or whole-runtime reference. The existing native recording and
resource session size advisories remain cohesive lifecycle/resource owner exceptions;
timing logic stays in the focused capture helper. The conservative memory ceiling
is unchanged. At that sequential-recording increment, geometry/input-argument helpers
matched HEAD by AST and compositor/readback source matched byte-for-byte; operator
TOML values matched except the required policy version. The subsequent capture
optimization below changes readback implementation while retaining tile sampling. The retained Oct15 profile still computes1280×1000 with factor2 and
unchanged tile rectangles when the encoder maximum needs no extra reduction; this
is not a live-rig configuration observation. Projector pacing and output rendering
were not edited.

Local validation:458 tests and79 contract subtests pass (one native/rig exclusion),
including authenticated transports, normal/interrupted on-disk mappings, same-time
real repeats, reverse readback completion, cancelled first capture, capacity gaps,
partial input/mapping failures, empty/off recording and original cleanup deadlines.
Ruff/format174, Win32 mypy158,11 generated schema checks and710 backend modules with
zero boundary violations pass. Initial Header version fixture/schema sequencing,
optional diagnostic typing and one formatting error were corrected. The first broad
run's11 localhost bind denials passed with socket permission. A preservation probe's
initial tuple serialization assumption was corrected; its actual equality/geometry
checks pass. [Raw results, exact commands, sample test outputs and source hashes](runtime-evidence-2026-10-16/stimulus-sequential-recording/validation.json)
retain the dirty-checkout/source scope. Native encoder input/count/fragment recovery
and full-load throughput remain in the [single rig checklist](rig-verification.md);
local fake-input tests do not prove NVENC output or device equivalence.
Local documentation checks resolve changed references/decision anchors but find two
pre-existing missing historical PNG targets (Oct15 bottom-grid/fix-verification/after/
bottom-offscreen.png and Oct14 tank-screen-plot/tank-screens.png). Oct26 recheck
finds both exact linked files present, decodable and consistent with their retained
historical context; no replacement image was generated. The old missing-path
result is historical. [Current path/hash evidence](runtime-evidence-2026-10-26/lifecycle-followup/historical-images.json)
records resolution; images remain local under the media-ignore policy.

Oct16 `stimulus-capture-optimization` now implements the owner-authorized PBO reuse
and GPU row orientation under [V12 revision15](../docs/architecture/visual_stimulus.md#v12).
The existing admission bound controls lazy pool growth; idle PBO storage is reused
without per-frame allocation/deletion. Each transfer has a fresh identity/fence.
Only signaled, successfully copied/unmapped buffers return to the pool; cancelled or
failed storage is discarded. Host bytearrays remain independent of later PBO writes.
Covered cleanup retries retain exact failed ownership and skip confirmed deletions, including
idle-buffer and partial-target allocation failures. Cleanup explicitly activates the
first output context before scene release, even when producer fences are already
retired. A local failure probe exposed this pre-existing context-selection gap; failed
activation retains scene/window ownership for retry. GL calls stay on their owner.

The compositor's shaders, quad, tile-render loop, dimensions and FFmpeg argv builder
are unchanged against the pre-increment snapshot; operator configuration is byte
identical. Rather than change bilinear tile sampling, a same-size nearest GPU blit
reverses the completed framebuffer into a second identical-format target. It preserves
black margins, restores scissor, rebinds the composite FBO and leaves no PBO bound. New capture strings
`rgba8_top_down` and `r10g10b10a2_le_top_down` make the actual row order explicit in
recipes/evidence. Historical bottom-up representations remain interpretable; live GL
capture accepts only top-down plans. The 8-bit recording path passes its owned buffer
through without a row copy; packed 10-bit retains X-bit normalization. This additional
GPU copy is a deliberate tradeoff to preserve sampled pixel codes; performance is
unmeasured. [OpenGL framebuffer blit semantics](https://wikis.khronos.org/opengl/GlBlitFramebuffer)
and [PBO synchronization](https://wikis.khronos.org/opengl/Pixel_Buffer_Object) support
the transfer design, not a hardware throughput claim.

ARCH-002 keeps ownership in the existing focused capture helper and moves recording
memory calculations to the existing resource-budget module. GPU preflight now counts
both targets (two RGBA8 or RGBA32F images) plus the bounded four-byte PBO pool; CPU
headroom/settings stay unchanged. No new process/dependency, independently editable
capacity or off-thread GL work. The existing large preparation/recording owner size
advisories remain reviewed cohesive exceptions; separable accounting was extracted.
E13 layout, resolution, image processing, nominal playback and projector pacing are
unchanged; sequential timestamp mapping and closure rules remain in place.

Final local owner/contract suite:430 tests and82 subtests pass, one native/rig exclusion,
including authenticated transports. The host GL model checks byte-equivalent transfer
against the prior CPU path for 8/10-bit, odd/even/single rows, bounded repeated reuse,
independent host buffers, reverse completion, unsignaled cancellation, stale handles,
blit/fence/map corruption, and failed-deletion/partial-allocation retries. It does not
execute native GL or prove actual GPU pixel equivalence. Ruff/format174, Win32 mypy158,
11 schemas and710 module boundary checks pass; three import-order issues were fixed
before final checks. The context probe initially lacked a GLFW teardown stub, which
was corrected without changing its ordering assertion; final normal/failing activation
cases pass. [Exact source snapshots/hashes and raw validation](runtime-evidence-2026-10-16/stimulus-capture-optimization/validation.json)
retain this dirty checkout's scope. The owner will perform native pixel, memory and
combined-load performance checks later under the [rig checklist](rig-verification.md).
GPU grayscale conversion, off-thread readback and layout/crop changes remain outside
this implementation; `stimulus-review-encoding-cost` retains the native follow-up.

Oct16 `stimulus-capture-cleanup-faults` repairs both locally reproduced cleanup
findings under [V12](../docs/architecture/visual_stimulus.md#v12) and
[E06](../docs/architecture/system-contracts.md#e06), without changing those decisions:

- Capture cancellation now attempts independent reservation/GL releases even when
  required evidence cannot be queued, then propagates the first error. Confirmed
  reservation cancellation is retained across GL retries, so failure counts are not
  repeated; a failed or incomplete GL deletion retains its exact pending handle.
  A stopped recorder still produces Failed output results after resource cleanup.
- Readback retirement/pooling now follows all fallible GL work, including the final
  buffer unbind. Restoration failures mark the handle failed and retain it for
  cancellation, even when the fence was already deleted. Failed storage is discarded,
  never recycled; later capture allocates fresh storage.

Ten new owning regressions fail before repair and pass after it. They cover full and
sealed evidence queues, multiple pending captures, false/raising GL cancellation
followed by retry, unchanged failure counters and deadlines, failed output results,
and ready/unsignaled unbind failures with deletion retries. Final owner/contract suite:
440 tests and82 subtests pass with one native/rig exclusion and localhost permission.
Ruff/format174 files, Win32 mypy158 sources and boundaries712 modules/zero violations
pass; two initial formatting findings were corrected. ARCH-002 keeps the existing
focused owners and owning test modules; unchanged large backend owners retain their
cohesion advisories. No new state machine, dependency or queue is added.

Static preservation checks confirm unchanged capture submission, GPU orientation,
shader bytes, composite geometry, encoding arguments and operator settings. Existing
host tests retain asymmetric 8/10-bit and odd/even/single-row image coverage. These
results do not establish native GL pixel equivalence, driver fault frequency or
throughput; those remain in the [rig checklist](rig-verification.md). The
[original review reproductions](runtime-evidence-2026-10-16/stimulus-capture-review/validation.json)
remain historical evidence of the defects; current red/green results, commands and
source fingerprints are in [fix validation](runtime-evidence-2026-10-16/stimulus-capture-cleanup-fixes/validation.json).

Oct16 E08/V12/ARCH-002 maintenance shares only unary peer mechanics, with Visual
Stimulus-owned stub selection retained. Recording metric comments clarify complete
input spans, zero-progress gaps and independent maxima without changing diagnostics
or scientific outputs. Authenticated peer26 and recording52 focused cases pass;
[current evidence](runtime.md#maintainability-review) retains final integration scope.
Native full-load acceptance remains open.

Oct16 `stimulus-replay-provenance` is repaired under
[V13 revision12](../docs/architecture/visual_stimulus.md#v13). The existing recipe
manifest now includes the installed renderer-source SHA-256, individual scene/arena/
warp/output shader hashes, Python/OS and relevant package/linked-decoder versions,
in-package color/importer identities, and actual per-output GL vendor/renderer/driver
observations. Missing required graphics facts reject Setup. Source/shader/environment
changes are distinguishable in saved canonical bytes; retain the matching software
release externally. The [earlier probe](runtime-evidence-2026-10-16/backend-output-alignment-review/validation.json)
reproduced the generic-label defect before this repair.

ARCH-002 extracts provenance from the resource preparer into a focused helper and
consolidates unchanged GLSL source ownership. Source collection runs once per Setup;
no per-frame hashing/readback or new dependency/process is introduced. The existing
CPU preparation worker now hands artifacts to the graphics owner and resumes after
context provenance enrichment, before recipe preparation, canonical hashing and
publication. Two bounded Futures preserve graphics-thread ownership, original Setup
deadlines and cleanup joins. Graphics failures retain the original lifecycle failure
path. Final serialized size remains bounded. Native/session/lifecycle size advisories
are reviewed as cohesive context/resource/lifecycle owners; new provenance mechanics
live in the helper and existing preparation job, without runtime back-references.

Owner-approved external preservation uses one backed-up, versioned asset library;
per-run manifests retain paths, sizes and hashes without copying an asset subset.
Preserve each image, mesh/material dependency and calibration version once, and keep
referenced versions. [Operator example](../docs/examples/session-logging.md#shared-asset-library).
Tracking remains deferred; reconstruction targets software-generated output.
Offline compatibility validation/replay/export and native GPU verification remain
separate from experiment-side retention; no pixel/light-onset equivalence is claimed.

Acquisition/stimulus and selected central-output tests pass997, with five platform
skips/three exclusions, including authenticated localhost transports. Five focused
final-publication cases additionally verify the on-disk recipe against the prepared
handle, graphics failure, cancellation, deadline and final-byte-limit rejection.
Source relocation/edit, shader mutation, driver changes/missing facts and shared
asset version reuse are covered. Exact GLSL preservation is checked against HEAD.
Ruff/format176, Win32 mypy159 and boundary checks pass. The initial run required
localhost access and correction of one new test fixture's snapshot budget; two initial
type annotations were corrected. [Commands, source fingerprints and raw results](runtime-evidence-2026-10-16/output-provenance-fixes/validation.json)
retain scope/limits. Native checks stay in the [single rig checklist](rig-verification.md#always-saved-scientific-evidence).

Oct15 live-pulse follow-up completes the owner-requested photodiode preview: the
existing GL-owner service loop repeatedly submits the current placement while Active.
Trial and diagnostic drawing share one pure V22 pattern helper, with separate
submission indices. Diagnostic Open starts at zero; successful all-output swaps
advance the index; live Frame/Pulse/target edits preserve it. Unknown and Close
stop repetition. Failed presentation marks Unknown and uses existing renderer
failure handling; no trial clock, marker log, recording or new resource owner is added.

Current pulse checks: affected backend/controller193 pass; the focused combined
GUI/rendering selection85 passes, including live edits to all Pulse fields, geometry
changes during a dark landmark, cycle wrap/reopen reset, failed swaps without index
advancement, Unknown cessation and Close/Idle. Ruff/format9, Win32 mypy50 and
boundaries699/zero violations pass. Two initial test-fixture errors (strict JSON
parsing and field-key names) were corrected before the final runs. RTX5060Ti
offscreen production drawing matches every pixel in66 frames across a live move/resize.
[Pulse evidence](runtime-evidence-2026-10-15/output-placement/pulse-native.json) and
[check context](runtime-evidence-2026-10-15/output-placement/pulse-validation.json)
retain method/source scope. No running GUI/projector or optical timing acceptance
was performed. Existing renderer-native and calibration-worker size advisories
remain cohesive owner exceptions: repetition stays with diagnostic lifecycle state;
the shared pattern is extracted rather than duplicating trial logic (ARCH-002).

Oct15 screenshot follow-up fixes `live-output-placement` launch incorrectly
requiring a pre-existing Frame/Pulse. Empty/incomplete initial definitions now
open black without inventing a rectangle or changing the draft. A complete
in-bounds live definition draws the pulse; later incomplete updates still retain
the confirmed image. The initial-only empty allowance stays with the existing
preparation validator; live-update validation remains strict. Existing GUI bundle,
initial draft and renderer-owner tests now cover empty-start-to-first-pulse and
unchanged cleanup. Follow-up GUI14/backend135, scoped Ruff/format7, Win32 mypy5,
schemas11 and boundaries698/zero violations pass. RTX5060Ti offscreen pixels are
exactly black initially, then show only the first valid white pulse. An initial
parameterized-test signature collection error was corrected before final execution.
[Follow-up native evidence](runtime-evidence-2026-10-15/output-placement/empty-start-native.json)
and [GUI transcript](runtime-evidence-2026-10-15/output-placement/empty-start-gui-tests-final.txt)
retain the scope; no running application/projector was operated.

`live-output-placement` is implemented under
[G01 revision208](../docs/architecture/gui.md#g01),
[V01 revision25](../docs/architecture/visual_stimulus.md#v01) and
[V22 revision7](../docs/architecture/visual_stimulus.md#v22). Synchronization adds
Launch photodiode placement (repeating bright/dark configured pulse on black) and Launch
blackout placement (black zones on neutral gray). Relevant pixel fields/target or
zone add/remove controls update the actual diagnostic via the existing debounced,
sequenced command path. Complete snapshots validate before replacing placement;
invalid/incomplete edits preserve the prior image. Unknown remains closable with
tuning disabled. Close restores Idle through existing exact resource ownership.
No trial clock or recording runs in these previews; V22 owns the diagnostic pulse sequence.

ARCH-002 keeps pixel drawing, strict placement records and GUI gating/conversion in
three focused helpers; existing lifecycle/GL/output owners remain authoritative.
One shared pattern allowlist covers all four views. Protobuf adds one placement JSON
field to the three existing update envelopes; regeneration preserves previous tags.
Only the display/profile-bearing derived schemas change. No dependency, process,
operator default or policy value is added. Cohesion advisories for the existing
Projectors composition, controller calibration dispatch and renderer owners remain
reviewed exceptions; no feature helper retains a whole runtime reference.

Final affected GUI52 and backend/controller362 pass (one Windows/rig case deselected),
including authenticated forwarding, stale/lease/sequence rejection, worker actual
presentation/Unknown, atomic invalid-rectangle rejection, resource closure and the
two new bundle/GUI paths. Contract42/79 subtests, schemas11, scoped Ruff/format342,
Win32 mypy336 and boundaries698/zero violations pass. Initial restricted communication
stalls, one legacy Close fixture, mixed-pacing fixture setup and screen-resource
ownership assertions were resolved or replaced by permitted final checks. Broad
repository-local temp runs reached GUI90/backend353 passes but failed the existing
external-demo-assets guard; final normal-temp executions pass without weakening it.
The offscreen Qt inspection required explicit test-only Segoe UI registration.

RTX5060Ti offscreen native pixels match complete expected images before/after pulse
movement and zone removal. This does not establish projector submission, physical
placement or optical timing acceptance. Restart the application to load all updated
clients/backends and use the new Synchronization actions. Existing local drafts hold
the edits for normal Apply; previews do not publish an experiment configuration.
[Native pixels, controls and final check transcripts](runtime-evidence-2026-10-15/output-placement/)
retain evidence; physical/fault checks stay in the
[single rig checklist](rig-verification.md).

Oct15 `bottom-calibration-grid-distortion` software fix completed under
[G01](../docs/architecture/gui.md#g01)/[V15](../docs/architecture/visual_stimulus.md#v15),
with no architecture/policy change. The existing diagnostic GLB builder now passes
native per-face raster sizes to its guide helper. Grey strokes cover at least two
source pixels on each axis; fixed10mm/world-phase line centers and measured
geometry/corrections remain unchanged. No new dependency, state owner or render
path was added under ARCH-002. Exports without a known raster retain their physical
stroke defaults. Source review found no separable responsibility requiring extraction.

An isolated RTX5060Ti render of production arena/warp shaders reproduces the latest
saved bundle's122px middle gap against ordinary41px gaps. The fixed generator
restores17 visible columns with40–41px gaps. Earlier inputs produced a163px gap;
their dated evidence remains separate. This corrects the initial CPU-only assessment:
uniform mesh centers do not establish visible raster coverage. All four generated
meshes retain exact10mm spacing on both axes. Existing owning GUI coverage is
extended for portrait/landscape/low-resolution strokes, mirrored world phase,
fractional sample coverage and bundle raster propagation. Focused GUI17 and
rendering74 pass; scoped Ruff/format4, Win32 mypy3 and boundaries695/zero violations
pass, with existing unrelated cohesion advisories. Broad restricted GUI selections
were interrupted after stalling; initial default/temp-root failures are not test passes.
The native probe initially supplied a full GUI configuration to the numeric-only
parser; corrected fixture construction uses the retained dimensions directly.

Physical cell-size equivalence remains open. Saved Bottom bars are44/24mm for
180/320px in portrait720×1280 mode:0.244444/0.075mm-per-pixel, yielding nominal
10mm cells of40.91×133.33px. Other screens use40/22mm for320/180px:
0.125/0.122222mm-per-pixel and80×81.82px cells. No extra Bottom grid spacing
factor exists. The owner is unsure whether Bottom measurements belong to the
current orientation; retain them pending remeasurement of the current orange X
and green Y bars. This establishes the different software scale assumptions,
not an optical diagnosis. Saved measurements and the running application were
not modified. Restart the GUI and relaunch projection calibration to regenerate
the fixed grid. Border cropping still creates partial edge cells by design.
[Native before/after, source hashes and input snapshots](runtime-evidence-2026-10-15/bottom-grid/fix-verification/summary.json),
[scale audit](runtime-evidence-2026-10-15/bottom-grid/fix-verification/scale-audit.json)
and [fixed render](runtime-evidence-2026-10-15/bottom-grid/fix-verification/after/bottom-offscreen.png)
retain the evidence. No projector presentation or optical acceptance is claimed.

Current Oct15 open-loop engineering gates pass linked Gaussian translation/spin,
visible rotating circular floor and combined60s reuse, with all four videos externally
counted/full-decoded and normal cleanup. Actual common-group state and four submitted
outputs support software motion linking; projection areas remain uncalibrated. The
original arena has only a textured circular floor, despite its directory name. A unique
unlit derivative preserves geometry/BIN/source; its explicit height0 test placement
corrects a failed black-frame trial at height53 without altering observer calibration.
Full resource preparation exposed invalid colon-containing generated arena IDs; bounded
deterministic valid IDs now agree across dependency manifests and GPU lookup, preserving
strict schemas. Embedded/external owning regressions and329 Visual Stimulus cases pass.

Controlled startup tuning changes capture slots3→15:25 capacity drops in the first0.739s
become zero in repeated60s and120s runs. Keep same-slot omissions/CFR duplicates distinct.
The source2048 texture requires a temporary GPU asset limit512MiB→1GiB; combined prepared
GPU usage is784,080,416bytes and CPU346,219,117bytes. Camera/codec settings and review
scale2 remain fixed. Both TOML overrides have exact originals retained for restoration.
The first900s interruption and reviewed shared-reader/fatal-error repairs are assessed
in [Acquisition](acquisition.md);120s passed afterward. The owner stopped the900s retry
at883.852s; outcome is Interrupted with recording cleanup unconfirmed. The owner has
resumed tests; those partial recordings remain retained. Original Visual Stimulus
TOML and last configuration were restored exactly
after all owned processes exited. Resumed trials use unique copies of the newer GUI
calibration (Bottom685x940; derived linked-spin pivot23,0). Current normal120s recording
passes four full decodes/counts, with7201 stimulus states/7168 real selected frames,
zero capacity drops,33 same-slot omissions and32 CFR duplicates. Fresh combined900-final-r1
now completes exactly 900 seconds with confirmed cleanup and four full video decodes.
Its 53,988 contiguous render groups retain four returned output submissions each;
there are no unresolved submissions/captures. Stimulus records 54,000 CFR frames:
53,389 real frames, 598 same-slot omissions, one capacity drop and 611 duplicates
(1.131%). The capacity drop is group 17 at T+0.2947451 seconds, with none thereafter.
Peak capture occupancy reaches 15/15 and maximum slot hold is 261.51 ms; burst headroom
and zero-loss capture are not established.
Oct16 read-only reanalysis bounds the historical ready-to-dequeue maximum at241.9643ms,
readback readiness at61.2051ms, normalization at10.0268ms and individual pipe calls
at9.3096ms. These maxima need not belong to one capture; pipe-call duration excludes
waiting between zero-progress calls. The old aggregates cannot attribute group17's
startup drop to GL, encoder or OS scheduling, and cannot recover percentiles.
Current local diagnostics retain one group/slot/timestamp example per fixed stage and
a full-frame input span with attempt/zero-progress counts, plus one unfinished span.
No rendering, pixels, capture selection, output count, deadline or GL ownership changes.
Owning tests pin old counts/timings, exact examples and snapshot isolation; new native
correlation remains in the [single rig plan](rig-verification.md#encoding-test-plan).
Final integrated backend/authenticated1860 passes/five skips/five exclusions, Ruff,
format679, Win32 mypy583 and boundaries702/zero violations pass. Validation is local;
no native throughput, total-memory or zero-loss acceptance is inferred.

The archived profile/scale resolves to1280x1000 RGBA (5,120,000bytes/frame), independently
matching276,480,000,000 submitted bytes/54,000 input frames. Accounted capture memory:

| Slots | CPU reservation | GPU reservation |
| --- | --- | --- |
| Restored default3 | 31.74MiB | 34.18MiB |
| Tested override15 | 90.33MiB | 92.77MiB |

Both CPU reservations fit256MiB `recording_bytes_total`; GPU reservations join the shared
asset budget. The evidence queue has a separate16MiB bound. These are current allocation
formulas, not measured full-process/driver/FFmpeg/OS memory. Keep restored default3;
15 fits these bounds but still filled and dropped in the900-second run, so no new default,
queue increase or headroom claim is justified here. Existing15-slot test settings remain
archived for controlled native comparison. [Reproducible analysis and limits](runtime-evidence-2026-10-16/remaining-dev-work/stimulus_capture_analysis.json).
 Active GPU means by translation/spin/arena
are 10.99/11.28/10.21% rendering and 42.36/42.76/42.56% encoding; memory stays constant.
Six nonaliasing snapshots at 15/17, 315/322 and 615/622 seconds show changing content
in all four tiles. Astra accepts software-linked motion/endurance, with physical
alignment still uncalibrated and stimulus review still lossy under E13.
[Final recording accounting](runtime-evidence-2026-10-15/open-loop-soak/resume-1/combined900-final-r1/completion-summary.json),
[active resource measurements](runtime-evidence-2026-10-15/open-loop-soak/resume-1/combined900-final-r1/monitor-analysis.json).
The separate 60-second camera-lossless workload also completes/counts/decodes, with
zero stimulus capacity drops, three same-slot omissions and two CFR repeats. Stimulus
review encoding is unchanged. Fresh resume-1 GUI/configuration/TOML baselines are now
restored, with the tested overrides retained only in the separate reusable packages.
All runtime processes are absent and camera handles are closed; Acquisition records
the camera PFS selector-cursor restoration limitation. Cleanup removes only 51 passed
regenerable synthetic MP4s (13.504 GiB), retaining their commands/counts/decode results,
all real/failed recordings and unique evidence.
[Cleanup manifest](runtime-evidence-2026-10-15/projector-free-rig/synthetic-media-cleanup.json).
Oct16 `arena-effective-pose-evidence` repairs that structured evidence gap under
[V13/V16](../docs/architecture/visual_stimulus.md#v16). The scene renderer retains one
pose for the active arena using the same frozen state as its existing model matrix:
explicit world frame, millimetre position and a unit xyzw quaternion matching the
existing yaw/pitch/roll composition. The authored asset transform remains separately
represented by the prepared asset and exact model-matrix words. Drawing/constraint
behavior and physical observer calibration are unchanged; no new movement semantics
or scientific acceptance is inferred. Existing arena helpers share finite pose-value
validation under ARCH-002, with no new dependency/state owner. Rendering/evidence/
feedback97 and Visual Stimulus347 pass (one native/rig deselected); scoped Ruff/format3,
Win32 mypy2 and boundaries698/zero violations pass. An initial test fixture omitted
the required arena kind and was corrected. Native pose/frame/matrix inspection remains
in the [rig checklist](rig-verification.md).
[Local source/check evidence](runtime-evidence-2026-10-16/remaining-dev-work/context.json).
[Raw attempts, fixes and native evidence](runtime-evidence-2026-10-15/open-loop-soak/)

Oct15 encoder matrix completes31/31 cases:10s all-source warm-up plus three
repetitions of five source combinations at CQ16/CQ23, each requesting60s of frames;
all external counts and full decodes pass. Enabled camera dimensions/rates are
Behavior1760x3000RGB24/30Hz and Tracking 1588x1344gray/60Hz; synthetic Stimulus is
1280x1000RGBA/60Hz. Actual FFmpeg GPU UUID is RTX2080Ti; matched FFmpeg/ffprobe9.0.2
is selected process-locally, leaving default PATH4.3.2 unchanged. A separately opened
application renderer appears on RTX5060Ti during r1-cameras-cq23 and thereafter;
later cases are not an otherwise idle-machine benchmark. Raw commands, versions,
formats, sizes and per-case timing are retained. Synthetic generation/conversion/NVENC
does not prove live capture, cross-GPU readback/stdin, sustained synchronized full-path
headroom, real-frame losses or animal-image quality. Eye remains disabled. CQ decisions
and saved argument lists are unchanged. Direct zero-byte raw-input probes for both
camera formats exit0 and finalize/synchronize small MP4s; these are not playable-video
or runtime NO_FRAMES ownership/accounting acceptance. Initial read-only-handle fsync
probe failure is retained; the corrected probe uses fresh paths.
[Results and actual workload](runtime-evidence-2026-10-15/projector-free-rig/context.json).

Oct15 projector-free verification finds stale derived prepared-trial JSON Schema
still embedding superseded seam_check and reference-bar guide Width/Height fields. Regenerating from
the retained canonical models under G01/V15 changes only that schema; all11 generated
schemas match afterward and42 contract cases pass. No policy or calibration behavior
changes. Native/source packages build; source archive contains both calibration GLBs.
[Dated commands, raw results and limits](runtime-evidence-2026-10-15/projector-free-rig/context.json). Projector rendering, readback, optical alignment and real-frame recording/drop
acceptance remain deferred while outputs are powered off; synthetic encoding is separate.

Oct15 Git-sync integration retains the owner-approved local pixel-size/offset calibration
under [G01](../docs/architecture/gui.md#g01)/[V15](../docs/architecture/visual_stimulus.md#v15),
while preserving independent required scientific evidence, optional reduced review video,
arena-file regions and recording metrics under E13/V12/V16/V28. E14 policy version15
binds the combined declarations; Protobuf projection remains field11 and review scaling
uses field12. Existing periodic sync is preserved when the video worker is absent.
Final owning suite327 passed/one deselected; full backend1,737 and offscreen GUI509 pass.
Static/document checks and initial failed attempts are assessed in the
[Runtime report](runtime.md) with [dated source provenance](runtime-evidence-2026-10-15/git-sync/context.json).
These local checks do not close [rig verification](rig-verification.md).


Oct14 `projection-calibration-window-controls` completes the owner's refinement under
[G01 revision204](../docs/architecture/gui.md#g01) and
[V15 revision20](../docs/architecture/visual_stimulus.md#v15). Screen names are smaller,
centered and use contiguous glyph cells. The table has no arrow buttons and adds
separate whole-pixel Offset X/Y columns (positive right/up, blank zero). Interactive
sizes cap at native resolution; offsets cap at remaining image margins and reclamp
when a size grows. Numeric8/full11/review6 persist pixel offsets while older removed
offsets remain discarded. Preview and published affine assets share translated bounds.
Diagnostic assets/views cover the full measured native raster, so expansion reveals
additional fixed-pitch, world-phase grid lines. Diagnostic plane isolation prevents
expanded grids occluding other faces; trial drawing disables that filter.

ARCH-002 reuses the pure extent owner, existing affine mapping, Qt entries, GLB
builder and arena shader/drawer; no dependency, wire field, process, deadline,
policy setting or whole-runtime reference is added. Projectors remains a cohesive
composition owner and delegates bounds/files/geometry. Owning GUI26 and persistence11
checks pass; renderer73 pass. Ruff/format157, Win32 mypy155 and boundaries686/zero
violations pass, with existing size advisories. The730px offscreen table was inspected;
no native restart/projector/optical/full-workload acceptance is claimed. Reopen the
application to load the code and launch projection calibration to regenerate its grid.
[Commands, XML, preview and provenance](runtime-evidence-2026-10-14/window-controls/context.json).
Broader GUI/calibration attempts stalled and were interrupted; no full-suite pass.
Stale version/extent assertions, numeric8 file routing and static findings were repaired.
A failed Windows encoding write emptied the GUI architecture page; its complete
pre-existing content was restored byte-exact from the Codex pre-edit snapshot before
these focused amendments. Remaining physical checks stay in
[rig verification](rig-verification.md).

Oct14 combined sixty-second three-camera trial completes with nine closed outputs, restored settings and four counted/full-decoded videos. Stimulus slots21 saturate with3078 capacity drops/3098 CFR duplicates; finite buffer growth is rejected and original visual TOML restored byte-exact. V12 throughput remains open. Source review identifies per-capture PBO allocation/deletion, fresh CPU readback followed by another ownership copy, row normalization, copied overlapped pipe backing and5ms recorder polling as optimization candidates. Stage timings are needed before attributing the bottleneck; preserve image quality/accounting/GPU ownership. [Performance review](runtime-evidence-2026-10-14/rig-timing-audit/recording-performance-review.json). Retain3 slots with256MiB recording CPU/512MiB asset GPU budgets for the tested2560x2000 composite/assets: CPU accounting133120000bytes requires159744000with20%; GPU same-assets estimate335054176bytes requires402065012with20%. These are allocation accounting estimates, not new native measurements or whole-process/GPU memory guarantees. Twenty-one slots saturated, so no finite slot recommendation establishes steady throughput. Nested video-sync cadence is corrected: measured successful intervals stay below1.2s (maximum1040.5247ms), errors0. Native Save On to Save Off completes/cleans/restores with two decoded camera videos and no stimulus output. E05/E06/E08 cleanup repairs preserve strict output absence, exact resource receipts and confirmed delivery. Fault6 records accepted cleanup from both backends, but warning authority loss prevents overall cancellation; its scope repair is locally verified under E03 revision35. With projectors off, fault9 exposes lost prior calibration release receipts; catalogue retirement/reopen handling is repaired and full Visual suite311 passes, native retest deferred. No renderer-exit cause is inferred from generic CHILD_EXITED. [Current evidence](runtime-evidence-2026-10-14/rig-timing-audit/lifecycle-findings.json).

ARCH-002 adds only a focused pure extent owner; reuse Qt and existing projection,
texture-coordinate and resource builders. No dependencies, wire/policy fields,
process/state machine, deadlines or ownership changes. Existing Projectors and
scene-resource size advisories are cohesive composition/allocation owners; physical
extent arithmetic stays in the helper. Current checks: owning GUI48 pass/445
excluded; rendering/config82 pass including real builder allocation with fake GL
contexts. Cross-projector proof uses different native resolutions and anisotropic
pitches: equal usable mm dimensions give equal physical corners/off-axis matrices,
and 20×10 mm texture spans retain physical size. Migration, arrow-click, integer
rejection, preview/export, fixed-pitch live sequence and imported asset preservation
checks pass. Ruff, format160, Win32 mypy158 and boundaries690/zero violations pass.
Projection numeric settings are unchanged: resulting extents are bounded by native
raster and measured pitch; current tests remain within near1/far250 and existing
tolerances. Hardware geometry changes still require V15's owner-approved limits review.

Initial unconfigured Qt runs fail without diagnostics; explicit offscreen mode fixes
local execution. A broader calibration selection stalls in restricted integration,
is interrupted, and is replaced by the focused owner checks. During implementation,
UTF-8 handling, an overly broad numeric restore conversion, obsolete version/offset
fixtures, strict JSON tuple validation and fake-resource cleanup field were corrected.
No native renderer restart, projector alignment, optical/scientific or full-workload
acceptance is claimed. Reopen the application to load changes; retain outstanding
[rig verification](rig-verification.md).
[Commands/scope](runtime-evidence-2026-10-14/integer-views/context.json) and XML evidence.
Previous pixel-crop evidence remains [here](runtime-evidence-2026-10-14/valid-area/context.json).

Oct14 `reference-calibration-output-frame` completed under
[G01 revision200](../docs/architecture/gui.md#g01) and
[V01 revision21](../docs/architecture/visual_stimulus.md#v01). Reference calibration
now shows a white native output-boundary frame and unchanged colored raw-pixel bars.
The initial frame needs only output resolution; it supports aiming/focus/rough
positioning and cannot claim a measured physical screen boundary. Align the raw
projection, measure bars, close it, then launch the measured physical frame/grid
for existing Scale/Offset refinement. No screen dimensions/measurements/corrections
or clipping values are changed by this step.

ARCH-002 reuses one focused four-rectangle helper in the native drawer and GLB
exporter; no dependencies, protocol fields, resources, policy or state additions.
Frame draws before colored bars, so intersections preserve exact configured bar
pixel spans; scissor restoration, native copy, protected lengths/digests, authority
and cleanup remain. Source GLB now contains four frame edges plus two bars per output.
Final rendering/resource71 and owning GUI15 pass/467 deselections. Ruff/format6,
Win32 mypy3 and boundaries689/zero violations pass with unchanged size advisories.
Initial70-pass/one-failure result exposes obsolete8-vertex asset assertion; update
it to24vertices and the bar slices, preserving length/cleanup assertions. Final71 pass.
No runtime/device/native/optical acceptance. A normal application restart loads the
renderer change, and reference launch regenerates its source. Physical alignment
remains in the [rig checklist](rig-verification.md).
[Commands, limits and test XML](runtime-evidence-2026-10-14/reference-frame/context.json).

Oct14 `updated-tank-screen-plot`: [3D/top/side plot](runtime-evidence-2026-10-14/tank-screen-plot/tank-screens.png)
uses current production corner construction, owner-confirmed126×94mm Bottom image
axes,5mm front/lower gaps and retained120×166×110mm tank / subject(60,93,53).
Retained51mm side distances give4mm lateral clearance;52mm would give5mm for the
centered94mm Bottom cross-span. Keep measured distances pending reconciliation;
the plot labels this source-input discrepancy without claiming optical verification.
[Inputs/corners](runtime-evidence-2026-10-14/tank-screen-plot/geometry.json) and
[generator](runtime-evidence-2026-10-14/tank-screen-plot/plot.py) retain provenance.
PNG inspected; front/lower gaps and Bottom axes asserted. No runtime/settings/device change.

Oct14 `clean-calibration-grid-bottom-fit` software correction completed under
[G01 revision199](../docs/architecture/gui.md#g01),
[V15 revision17](../docs/architecture/visual_stimulus.md#v15) and E14 revision210.
The grid remains solid neutral lines, a white border and one screen name. Owner
confirms 5 mm frame gaps at both front and lower junctions: Side/Bottom front edges
start behind Front; Front/side lower edges start above Bottom. Preserve perpendicular
subject distances and physical heights. Bottom image X/width126mm follows +rig Y;
Y/height94mm follows -rig X, preserving the 94×126mm tank footprint with corrected
image axes. The earlier on-disk Bottom width94/height126 caused image X to target
94mm instead of126mm. This resolves the source axis mismatch; actual optical
coverage is still pending, not inferred from arithmetic.

Numeric5/full8/review3 swap legacy Bottom width/height only, preserving raw native
bar measurements, extra scales/offsets/inversions and imported runtime profiles.
GUI fixed policy/config version6 declares the 5mm gap. All consumers reuse the shared
corner helper; ARCH-002 needs no dependency/state/process/module extraction. Final
owning GUI38 passes/444 deselections, plus2 focused passes after exact126/94 neutral
mapping and legacy-review migration assertions. Ruff/format7, Win32 mypy6 and
boundaries689/zero violations pass, with existing unrelated size advisories; TOML
syntax/version/binding and documentation references/whitespace pass. Initial legacy
affine/mirror-fixture failures and one static version comparison are corrected;
source geometry changes require the mirror tests' new clearances, retaining all
complete/partial/impossible-path scenarios.

Retain V15 clipping/tolerances after reviewing the orthonormal axes and 5mm gap;
no numeric change is needed for the supplied physical planes. Extra saved X/Y
multipliers remain operator adjustments. Reopen the GUI to migrate drafts and launch
projection calibration to regenerate the clean grid. No stored measurement edit,
runtime restart, device/output command or native/optical/full-workload acceptance.
Existing [rig checks](rig-verification.md) retain physical coverage verification.
[Correction evidence and commands](runtime-evidence-2026-10-14/frame-gaps/context.json).
The [earlier artifact assessment](runtime-evidence-2026-10-14/clean-grid/context.json)
records the old axis assumption and remains historical evidence, superseded by the
owner's126mm image-width/94mm image-height clarification.

Oct14 `calibration-close-button-and-distance-format` completed under
[G01 revision197](../docs/architecture/gui.md#g01). GUI derived distances display one
decimal millimetre; raw reference measurements/mm-per-pixel mapping retain precision.
The confirmed active step's own launch button becomes Close, with the other step
disabled and both disabled while pending. Existing diagnostic Close transport and
output-confirmation semantics remain unchanged. Owning GUI selection13 passes,
scoped static/boundary checks pass; no native output/restart or optical acceptance.
See the [runtime assessment](runtime.md) and
[local evidence](runtime-evidence-2026-10-14/calibration-controls/context.json).

Oct14 `bottom-attached-screen-elevation` completed under
[G01 revision196](../docs/architecture/gui.md#g01) and
[V15 revision16](../docs/architecture/visual_stimulus.md#v15). Replace tank-height
centering of Front/Left/Right with lower edges at subject Z minus Bottom-screen
distance. Preserve physical screen heights; shared corner construction now passes
Bottom distance through diagram, trial preview, saved calibration/GLB export and
prepared geometry. Missing/nonpositive/nonfinite Bottom distance invalidates all
planes rather than retaining detached wall geometry. Saved drafts gain no fields.

ARCH-002 reuses the focused geometry helper and existing owning behavior tests,
without new state, dependencies, runtime references or extraction needs. Final local
GUI selection25 passes/455 deselections; scoped Ruff/format5, Win32 mypy4 and
boundaries689/zero violations pass. Existing oversized-module advisories are unchanged;
all four edited source modules remain cohesive focused responsibilities. Initial
8-pass/2-failure run exposed test-fixture migration needs (full versus numeric
snapshot, missing Bottom distance); repair fixtures, intermediate20 and final25 pass.
Initial format finding corrected. Retain current V15 clipping/tolerances: no new
measured dimensions/scene depth justify a numeric adjustment, and planar attachment
does not change orthogonality. No runtime restart/device/native/optical acceptance;
reopen the GUI to load this fix. Existing [rig checks](rig-verification.md) remain.
[Local command/results and test XML](runtime-evidence-2026-10-14/screen-elevation/context.json).

Historical measured-base fit evidence used extra Scale multipliers; that rule is
superseded by G01's pixel valid-area crop. The original
[measured-base evidence](runtime-evidence-2026-10-14/measured-base-scale/context.json)
retains its dated measurements, tests and limits.

Oct14 `projector-cursor-stability` completed under
[G01 revision194](../docs/architecture/gui.md#g01), retaining V01/V04 native output ownership.
GLFW defaults to centering the cursor on each fullscreen creation; the shared native
window configuration now sets CENTER_CURSOR false after every hint reset. ARCH-002
uses the existing focused owner without cursor restoration, extra state or dependencies.
Owning rendering/calibration tests71 pass; scoped Ruff/format2, Win32 mypy1 and
boundaries689/zero violations pass. Native main-display checks verify launch at
(497,768), Close at (497,784), and recreated reference outputs at (497,425), each
exactly matching the clicked main-display location. Authenticated states confirm
Active/presented, Idle/resources_closed, then Active/presented. Leave reference bars
open for measurement; this verifies cursor placement, not optical/full-workload acceptance.
The accidental Escape interrupted the first native attempt; resume on owner request,
discover the closed Dashboard and reopen it in the running generation. The sandbox
status probe stalls; permitted loopback read succeeds. One initial cursor evidence
filename was overwritten by status evidence; record it separately on the next read.
[Commands, status and native evidence](runtime-evidence-2026-10-14/projector-cursor/context.json).

Oct14 `live-reference-measurements-and-tab` completed under
[G01 revision193](../docs/architecture/gui.md#g01). Measured X/Y mm fields now stay
editable with GUI editing authority during confirmed Active reference bars; retain
native pixel/mode provenance, rig/assignment/correction locks and protected inputs.
Edits update retained drafts/derived estimates without renderer updates or rewriting
active assets. Pending/unknown/closing and observer states remain locked; a pending
non-Active state now also locks the card. Frame/grid retains its original live
Scale/Offset controls. Shared DataTable's grid navigation trapped Tab on embedded
editors; disable that behavior to use Qt's normal widget traversal. Tab/Shift+Tab
moves between nested editors/combos/checkboxes and skips disabled fields; inventory
arrow selection remains native. Console, log-details and example text views release
Tab for navigation. Incomplete imported display profiles no longer raise a pre-existing
KeyError when adding file-owned projection limits; retain partial drafts while Setup
still validates complete geometry.

ARCH-002 reuses existing measurement drafts/refresh, shared Qt controls and owning
behavior tests; no global event filter, dependency, process or extra state. Existing
large Projectors code remains focused widget/view-lock composition; no separable new
responsibility is added. Focused7 tests pass; final calibration/keyboard/table/measurement
selection34 pass/441 deselections, after initial33-pass/incomplete-import failure.
Scoped Ruff/format5, Win32 mypy4, boundaries689/zero violations, documentation references
and whitespace pass. Final fixture run emits Windows COM0x8001010d diagnostic but
continues/exit0 with34 passes; cause unverified. Correct initial Ruff line/zip findings.

Reopen the already-closed GUI in the existing runtime using --reopen-gui. Native
Active reference presentation and screenshots verify FrontX→FrontY→LeftX and reverse
Tab movement with measurement fields focused; scientific values are unchanged.
This native Active-case check precedes the final pending-only guard refinement;
pending/observer behavior is verified by the local regressions. GUI remains open
with reference bars Active. A transient DWM ghost is observed without inferring backend
failure; read-only controller status confirms current presentation. Existing optical/
full-workload limits remain in the [rig checklist](rig-verification.md).
[Evidence and native focus captures](runtime-evidence-2026-10-14/live-reference-tab/context.json).

Oct14 `reference-bars-visible-output` repaired and verified under
[V01](../docs/architecture/visual_stimulus.md#v01)/[V15](../docs/architecture/visual_stimulus.md#v15).
Reference bars were drawn into the device framebuffer without copying to the native
screen; the branch continued before the copy used by frame/grid. Actual Front output
was black. Copy that framebuffer to the current screen before returning; native-pixel
lengths, correction independence, existing swaps, ownership and cleanup remain.
ARCH-002 reuses the established framebuffer copy, with no dependency, process, state,
module proliferation or architecture-policy change. Extend the owning behavior test
to require each output copy after bar drawing; both bars cases fail before the fix,
and both grid cases pass. After repair, rendering16 and calibration rendering/lifecycle/
authenticated transport22 cases pass (37 deselections); scoped Ruff/format2, Win32
mypy1, boundaries689/zero violations and whitespace pass. Default sandbox temp fixtures
initially cause six errors/ten passes; workspace basetemp and permitted integration pass.

Native GUI testing through Computer Use confirms four visible orange/green bar outputs,
normal Close with authenticated Idle/resource-closure evidence, and successful reopen
with Active/presented evidence. Graceful ShutdownApplication succeeds after the prior
GUI has closed and resources are confirmed closed; restart through the managed launcher
loads the repair and restores the draft/control. Final controller80dfe14b-7d23-45b0-a46f-eaf77c024b62
is left running with reference calibration open for measurements. An input-observation
race/stale-window binding and one geometry-unavailable click require refresh/reselection;
no unknown UI input is retried blindly. Initial exact-color screenshot analysis rejects
lossy JPEG values; corrected approximate-color analysis confirms both colors, without
claiming exact framebuffer pixels or optical accuracy. Optical/full-workload checks
remain in the [rig checklist](rig-verification.md). The repository asset directory
still contains only the two requested GLBs. [Evidence, native captures and commands](runtime-evidence-2026-10-14/reference-bars/context.json).

Oct14 `projection-config-only` completed locally under
[G01](../docs/architecture/gui.md#g01), [V15](../docs/architecture/visual_stimulus.md#v15)
and [E14](../docs/architecture/system-contracts.md#e14). Remove the four rig projection
editors and frontend draft persistence. `[projection]` in the owning Visual Stimulus
TOML supplies near 1 mm, far 250 mm, positional 0.000166 mm and orthogonality 0.000001.
Both calibration and experiment submission read that file; controller validation/startup
and worker Setup overlay its resolved snapshot before geometry validation. Missing or
invalid file values reject preparation. Imported numeric calibration/review drafts stay
loadable but cannot override these values; physical corners and other fields remain.
Regenerate the authoritative Protobuf bindings for the focused ProjectionLimits payload;
no policy value or policy_version changes. ARCH-002 removes the duplicate diagnostic
heuristic and reuses existing file/profile assembly, adding one focused pure validator,
no dependency/process/state. Existing large Projectors and worker lifecycle modules retain
composition and lifecycle ownership; no new independent responsibility is placed there.

GUI geometry/import/restoration/diagnostic 18 cases, configuration 9 cases, contracts 42
cases plus 79 subtests, worker lifecycle 34 cases and a controller startup overlay case pass.
Scoped Ruff/format and Win32 mypy 10 sources pass; boundaries 688 modules/zero violations
retain existing cohesion advisories; whitespace passes. Default sandbox temp fixtures fail;
repository-local basetemp works. Authenticated lifecycle tests stall under sandbox and are
interrupted; permitted loopback run passes. Initial fixtures lacked required projection
values and are updated, retaining rejection checks. Three transient admission failures
during concurrent two-step migration are corrected by the matching source/runtime
fixtures; the final55-case calibration selection passes and includes those scenarios. No running GUI restart, device command or
physical/optical acceptance performed. Existing rig checklist retains those boundaries.

Oct14 `projector-sync-modes` completed locally under
[G01 revision190](../docs/architecture/gui.md#g01),
[V20 revision9](../docs/architecture/visual_stimulus.md#v20) and E14 revision208.
Synchronization follows Screen calibration and Rig geometry. Remove its MCU summary,
editor and obsolete projector contextual-wiring path; Projector flip input/offsets
are now owner-deferred under A11 revision46. Offer Free run (no VSync), VSync on pulse
display, and VSync on all displays; migrate both old labels on portable/review draft
load. Existing file-owned pacing identity remains independent of pulse placement.
Free run requests zero swap interval on every output, including retained marker/pacer
outputs; it preserves V10 scheduling, V22 pulse controls and nominal recording-rate
validation. Canonical model, published schemas, codec and fixed policy agree;
Visual Stimulus policy/config/loader version12 and verified policy digest match.

ARCH-002 review removes redundant wiring and keeps mode mapping in ProjectorTiming,
presentation requests in DisplayProfile and existing GL owner binding. No new process,
dependency or runtime back-reference. Projectors remains composition of focused
helpers; native/configuration owners retain existing cohesive responsibilities.
Local GUI16, configuration/rendering61, lifecycle34 and contract42 cases pass
(79 contract subtests); scoped Ruff/format12 files, Win32 mypy10 sources,
boundaries687/zero violations and whitespace pass. Initial policy-version/digest and
new-test API mistakes were corrected; sandbox temp failures avoided with workspace
temp paths, stalled lifecycle transport run interrupted and permitted rerun passes.
No running GUI restart, physical output/device action or optical acceptance.
[Evidence and commands](runtime-evidence-2026-10-14/projector-sync/context.json).
Remaining V20 optical/driver/full-load checks stay in the [rig checklist](rig-verification.md).

Oct14 `two-step-calibration-assets` completed locally under
[G01](../docs/architecture/gui.md#g01), [V01](../docs/architecture/visual_stimulus.md#v01)
and [E07](../docs/architecture/experiment.md#e07). Exactly two files remain
in `assets/calibration/` (the extra README is removed): `reference_bars.glb` contains only two native-pixel bars per
output; `frame_grid.glb` contains the physical frame/grid for measured scale/offset
adjustment. Each launch refreshes only its selected file. Remove the five generated
repository JSONs and old shared grid filename. Generated profiles/mappings and exact
working copies live outside the repository in separate per-step user runtime roots.
GUI intent captures source/profile digests; controller rechecks the source, matching
profile view and staged copy before passing the runtime root to protected renderer
preparation. The reference file's pixel metadata must match the protected outputs;
reject wrong lengths/grid files, stale copies and wrong step references. Preserve
revision/authority/deadline/bounds, correction-independent bars, V15 frame/grid mapping,
exact source ownership and cleanup. No hardware command or live restart occurred.

ARCH-002 reuses the mesh packer, existing profiles and protected-source pipeline.
Extend the focused shared path helper; extract the controller's separable bounded
file reader into `device/calibration_inputs.py` before adding stage validation.
No dependency/process/runtime back-reference. Remaining controller calibration and
projector widget size advisories are cohesive command/state ownership and composition,
without new unrelated responsibilities. Extend owning test modules rather than adding
per-fix modules. Media outside calibration stays external; demo generator remains
external-only. Source distribution includes the two patterns; repository-less wheel
execution still rejects unavailable diagnostic sources.

Validation: focused `.venv/Scripts/python.exe -m pytest` controller admission, GUI and
calibration-rendering selection with `-m "not windows and not rig"`:55 pass/450
deselections. Covers independent exports, unchanged grid after reference export,
source/runtime byte identity, stale-copy rejection, exact reference quad pixel spans,
wrong-length/grid rejection and source cleanup. Scoped Ruff/format10 files, Win32
mypy7 sources, boundaries689/zero violations, actual two-file backend GLB parsing,
reference metadata/geometry consistency, source-manifest contents, local links/anchors
and whitespace pass. `python -m build --no-isolation` builds sdist/wheel. A transient
script insertion lookup fails before adding the new test; corrected and verified.
No application restart/native-output/optical/full-workload acceptance claimed; restart
before using the new path. [Current evidence](runtime-evidence-2026-10-14/calibration-assets/two-step-context.json),
[55-case results](runtime-evidence-2026-10-14/calibration-assets/two-step-tests.xml).

Oct14 `renderer-opengl-adapter-selection` repaired under
[SYS-002 revision3](../architecture.md#sys-002) and
[E08 revision171](../docs/architecture/system-contracts.md#e08): use separate Windows
executable identities with identical verified prepared Python bytes. Before creation,
apply/read back power-saving preference for cephvr-python.exe (GUI/CPU) and high
performance for cephvr-renderer.exe. Preserve unrelated per-application options;
global/other-application preferences are untouched. Verify the role image against
prepared provenance at resolution/bootstrap; stale/tampered images fail explicitly.
Actual renderer NVIDIA model/UUID checks remain authoritative. CUDA/OF and RTX2080Ti
encoding owners remain unchanged. ARCH-002 reuses prepared interpreter/launch/containment
mechanisms with one focused preference helper, no extra process/dependency/fallback.

Fresh hidden probes prove AMD GUI/CPU and RTX5060Ti renderer selection. After normal
GUI save/closure and approved full E08 replacement, controller
5a66b261-7079-49d6-bf9b-8bfcad0bb9ad reports four outputs resources-ready/applied
revision1/returned Idle submissions without initialization issues. Live renderer
PID23168 uses NVIDIA UUID GPU-77642118-1623-48dd-3686-1014aa86b818; native GUI
PID13128 restores its draft, holds control and shows no failure dialog. Leave runtime
session75315 open. The remedy now correctly distinguishes full renderer restart from
GUI-only reopen. Earlier AMD context failure remains in raw evidence; the exact
historical driver-selection cause is unproven, while fresh placement/Idle is verified.

Final485 affected renderer/supervisor/platform-adapter/launcher cases pass/one
deselection; native prepared-role-image tamper/refresh case passes. Focused89 cases
also pass. Scoped Ruff/format8 files, Win32 mypy5 sources, boundaries687/zero
violations and whitespace pass. Initial sandbox asyncio loopback stalls are interrupted;
permitted replacement passes without weakened assertions. These rig checks cover
fresh contexts/Idle only, not OF/recording/scientific/optical/full-load acceptance.
[Methods, hashes and live/test evidence](runtime-evidence-2026-10-14/gui-refresh/gpu-selection-context.json)
and the [rig checklist](rig-verification.md) retain scope and remaining checks.
## Arena-file movement regions

[V16](../docs/architecture/visual_stimulus.md#v16) revision5 and the
[schema binding](../contracts/visual_stimulus/stimulus-schema.md) now allow explicitly selected
arena-file regions. The protected GLB provider retains the declared legacy geometry; the
compiler converts each unique asset/transform once, checks cancellation/deadline budgets,
transforms it into the existing convex sliding input and rejects inconsistent instance
geometry/invalid starts/empty insets, and retains the resolved polygon and resource fingerprint.
Prepared artifacts reject unresolved source selectors. Existing explicit regions remain
independent of metadata. Rectangular/convex imports are implemented; circular/cross/T/torus
imports and wrapping are outside this owner-selected increment. GUI evidence lives in the
[Runtime report](runtime.md#protocol-group-headings-and-arena-advanced-settings).

ARCH-002 review uses focused geometry-declaration and region-resolution helpers, existing
Pydantic models/GLB preparation ownership and owning tests; no dependencies or runtime
back-references. Source/prepared boundary schemas regenerated. Local Visual Stimulus suite
passes318/one deselected with loopback permission; the initial sandbox run passed309 and
failed nine socket binds, and a15-case authenticated rerun passes before the full pass.
Final protected-source-adapter→GLB metadata→compiled artifact/closure regression passes;
native protection is mocked, not established. Ruff/format, Win32 mypy313 sources, boundary
check694/zero violations and schema/document checks pass. Initial type/fixture issues were
corrected. Native arena limits/sliding/four-view agreement remain in the single
[rig checklist](rig-verification.md), with existing physical/hardware deferrals preserved.


Oct14 encoding rig test plan: [commands, matrix and collection](rig-verification.md#encoding-test-plan)
cover CQ16/CQ23 isolated/concurrent synthetic probes and separate live-app runs.
`tools/encoding_probe.py` collects external decode/frame counts, sizes, source/drop/
padding counters and renderer timing JSON. Review repaired launch/probe/decode failure
retention, bounded version queries, malformed-log isolation and empty/missing diagnostic
reporting; decoder error output suppresses successful throughput even with exit0.
The plan uses one executable warm-up/three-repeat matrix and documents independent
synthetic completion versus sustained live contention. Fifteen offline tool tests plus lint/format/
Win32 mypy pass; no FFmpeg/NVENC, PowerShell or hardware execution on this machine.
Eye inputs/readiness remain required; missing timing/completion evidence is not a pass.

Oct14 `stimulus-local-recording-improvements` completed locally under
[V12](../docs/architecture/visual_stimulus.md#v12) revision12 and
[E13](../docs/architecture/visual_stimulus.md#e13) revision24. Fresh native readback
bytearrays transfer exclusive ownership to the recording worker; borrowed inputs
still copy. Rejecting stale completion/cancellation now preserves a live reservation
instead of removing it before validation. The GL owner, bounded admission, evidence
priority, frame identity/order, padding and original I/O/closure deadlines remain.

File-owned `recording_runtime.review_scale_factor=2` multiplies the encoder-fit tile
divisor before GPU readback: the prior 2560x2000 example becomes1280x1000 (5.12MB
instead of20.48MB RGBA/frame). Exact scaled rectangles/dimensions remain in the
prepared recipe; empty or incompatible layouts fail Setup. Full-resolution rendering
and reconstruction inputs are unchanged; V13 offline implementation stays deferred.
Policy version13/fingerprint and additive file-policy Protobuf binding are synchronized.
Older absent scale fields mean1; deployed files must be reloaded through fresh Setup.

`recording.metrics` stores fixed count/total/max nanosecond aggregates for ready and
pending readback polls, admission-to-ready, ready-to-dequeue, row normalization,
pipe-write calls and admitted-slot lifetime; it retains timestamps only for admitted
captures. Peak/current slot occupancy, queued captures, zero-progress writes, bytes
submitted and cancellations accompany the aggregates. `recording_metrics` emits one
JSON summary through a dedicated INFO session logger on thread exit (including
failure/cancel), with event=recording_metrics and the evidence path. Worker startup
installs one stderr handler without changing root logging; rig tools must capture
renderer stderr. Oct14 review fixed the previously unconfigured INFO logger, which
normal root WARNING settings silently suppressed, and removed the non-JSON prefix.
Invalid encoder write counts now fail before updating submitted-byte diagnostics. A live diagnostic reader can call `metrics.snapshot()`.
Ready-poll time includes native mapping/copy/unmapping/cleanup, not isolated GPU time;
pipe-call time excludes asynchronous OS wait (use zero-progress counts and slot hold).
These are diagnostics, not scientific timestamps, encode acknowledgements or durability.

Validation: `python -m pytest tests/visual_stimulus -q -m "not windows and not rig"`
passes313/one deselected after review with loopback permission. Initial sandbox run passed300 but
blocked nine socket binds; those15 owning transport tests then passed with permission.
Final Ruff/format and Win32 mypy (151 sources) pass; boundaries689/zero violations.
Protobuf generation succeeds for19 sources. Existing owning tests cover exclusive vs
borrowed buffers, partial/blocked writes, delayed/out-of-order captures, cancellation,
stale reservations, bounded counters/timing, diagnostic exit logging and scaled tile
layout without display changes. Review adds root-WARNING/idempotent-handler JSON
emission and invalid-write-count regressions. No other actionable ownership/scaling
defect found in this source review; native stderr collection and encoding remain
rig checks. ARCH-002: diagnostics are a focused module; existing
oversized native owner only binds the scale/clock to existing lifecycle operations,
with no added process/dependency or whole-runtime reference. No native GPU/FFmpeg
encode or measured frame-drop reduction was claimed by that increment. PBO pooling
and GPU row orientation are subsequently implemented above; off-thread readback and
RGB/mono capture-layout changes remain deferred. Current mono encoding still takes
RGBA input at the reduced review dimensions; [native measurements](rig-verification.md)
remain pending.

Oct14 `encoding-quality-defaults`: owner selects CQ16 as the standard, p4, unchanged
camera dimensions (review composite now reduced as above), Behavior color 4:4:4 and Tracking mono; Eye and Stimulus mono
use explicit CQ23 test overrides pending owner evaluation. Mono chains explicitly
convert to gray then NVENC-compatible 8-bit YUV 4:2:0 with neutral chroma; future
color Stimulus uses 4:4:4. Camera source-depth protections remain; saved settings
retain E07 precedence. No automatic bit-depth reduction or camera/PFS edits.
[A08](../docs/architecture/acquisition.md#a08) and
[E13](../docs/architecture/visual_stimulus.md#e13) govern these lists.
Local validation: 34 configuration/filter-expression tests pass; all four token/filter
chains preserve dimensions, TOML/policy bindings load, Ruff/format and Win32 mypy
for the policy-binding module pass. Boundary check: 688 modules, zero violations;
existing size warnings concern unchanged owners, with no new responsibility added.
Installed GPU/FFmpeg conversion, visual
quality, size and combined throughput remain [rig checks](rig-verification.md).

Oct14 `always-save-scientific-evidence`: Required stimulus recipe and JSONL are now planned and recorded with review video off. The existing bounded writer persists actual state, submissions, diagnostics, feedback and completion without a capture worker, GPU readback or FFmpeg child. Evidence schema5 declares video_enabled; disabled captures are empty and encoder outcomes absent. The saved legacy switch retains its value and controls video only; the GUI explains always-saved scientific evidence.
Policy/config bindings updated together (acquisition21, Visual Stimulus14). Wiring,
trigger timing, assumed first-trigger anchor and trial boundaries are unchanged.
[Local evidence](runtime-evidence-2026-10-14/always-save-scientific-evidence/context.json):
affected acquisition/Visual Stimulus/controller suites pass1200 tests
(five skips, three deselections); offscreen recording-control check passes (478
unrelated GUI cases deselected). Ruff/format and Win32 mypy338 source files pass;
contract generation, TOML/schema consistency and whitespace checks pass. Boundary
review:690 modules, zero violations. Native acceptance remains in the
[rig checklist](rig-verification.md#always-saved-scientific-evidence).
ARCH-002: keep existing lifecycle owners and bounded queues; camera metadata terminal
assembly is a separate focused module. The larger camera session and stimulus native
owner remain cohesive schedule/ownership adapters, without whole-runtime back-references
or extra processes. Tests cover video-off sources/invalid images/bounds/cutoffs,
pre-onset cancellation and write failure, plus stimulus scientific records and feedback
interval closure without native capture/encoder ports. Existing video-on tests pass.

Oct14 projector power-on recovery under
[V19](../docs/architecture/visual_stimulus.md#v19) and
[E08](../docs/architecture/system-contracts.md#e08): all four saved DLP identities
enumerate at60Hz. The approved fresh runtime reports four resources-ready outputs,
applied configuration revision1 and returned Idle submissions with no initialization
issues. Saved GUI settings restore as a local draft; no Setup/Start or scientific
settings change. This closes the unavailable-display startup blocker only;
optical/calibration/full-workload acceptance remains in the
[rig checklist](rig-verification.md).
[Authenticated status and method](runtime-evidence-2026-10-14/gui-refresh/projectors-on-context.json).

Oct14 repository media cleanup keeps the demo manifest/texture descriptors in source
control and generates their nine sample PNGs locally through
`tools/generate_demo_assets.py`. Existing texture decoding tests now use temporary
samples; three owning decode cases and three GUI authoring/repetition cases pass.
[Cleanup inventory and validation](runtime-evidence-2026-10-14/repo-cleanup/context.json)
index the local-only screenshots/run datasets and generated binaries. V02/V04/V12
runtime ownership, actual saved media/evidence and scientific acceptance limits are
unchanged. The native sources/builders remain tracked; no active runtime is altered.

Device workflow refinement under [G01](../docs/architecture/gui.md#g01) keeps
projector assignment/participation separate from MCU input wiring. Projectors opens
a contextual editor for the canonical MCU draft, shows calibration prerequisites,
and keeps VSync editable independently of the photodiode pulse. Existing runtime
validation and ownership remain unchanged. The [runtime assessment](runtime.md)
owns local GUI evidence; native synchronization/optical acceptance remains in the
[rig checklist](rig-verification.md).

Oct13 texture implementation under [V02](../docs/architecture/visual_stimulus.md#v02)
and [V04](../docs/architecture/visual_stimulus.md#v04): the previous importer required a
tagged `.texture.json` plus preview PNG. CephVR1 instead treats JSON as a procedural
recipe. The new image-producing recipe profile retains/hashes the original JSON and
protected image dependencies, prepares deterministic RGB8 pixels under existing
source/workspace/CPU/GPU/deadline limits, and uses configured geometry for polar
patterns. Preview PNGs are not authoritative. Plain JSON and legacy parameter aliases
are accepted by content; GUI and headless programs use the same prepared resource
path. Explicit tile dimensions update authored periods; missing dimensions preserve
the existing authored size. Source-derived fixtures substitute for the owner's files,
which are unavailable here. Source-derived pixel/provider checks pass; no actual-user-file or native acceptance
claim is made.

Independent image-tile appearances now support direct reference motion links.
Bottom-centered unfolding preserves linear speed across perpendicular screens and
opposite local axes. Angular flow follows V02's subject-distance convention. Each
follower retains its own asset, periods, phase and reset choice. Standard state fields
bind at epoch boundaries using retained orientations; no frame-time coordination or
second phase state is added. Custom/Tracking motion, chains/cycles, competing motion
writers, combined drift plus spin, nonuniform/reflected stimulus maps and skew-plane
spin are explicitly rejected. Output calibration reflections are separate. Spin
requires a known subject-centered reference pivot; Setup reports the necessary
coordinates and runtime rechecks the retained center. GUI linking disables follower
movement controls, including controls reparented into the reference table.

Astra review found a coordinate discrepancy: stimulus-schema declared a bottom-left
physical origin, while rendering/layer_projection.py's physical_corners emits
`2*local/extent`, making zero the screen center. Oct14 owner decision
([V14 revision 4](../docs/architecture/visual_stimulus.md#v14)): the surface-local
origin is the surface center, so the contract now matches the renderer and spin guard
and no placement changes. Surface maps authored against a different origin must be
regenerated (the owner is redoing calibration and surface mapping). A rendering
regression pins the convention. Normal drift is independent of the pivot limitation.
[Rig acceptance](rig-verification.md) remains deferred.

Final local texture validation:277 Visual Stimulus tests pass (one rig/platform
case deselected),42 contract tests/79 subtests pass,11 schemas are current, and14
focused GUI cases pass. The earlier broad GUI run had450 passes/seven failures while
another chat changed epoch editing; the final14-case run includes every previously
failing case, after the layout, demo recipe expectations and concurrent epoch changes.
This is not a fresh full-GUI-suite pass. Demo JSONs now explicitly declare their
existing PNG as an image input; three exact pixel comparisons preserve their original
checker/noise/sine appearance. Procedural recipes require no preview PNG.

Scoped Ruff/format checks pass23 feature files; Windows-target mypy passes19 sources,
boundaries pass676 modules/zero violations, and dependency consistency passes. Initial
sandbox transport retries failed on prohibited loopback binding; the permitted rerun
passes without weakening assertions. Packaging reaches the existing AMD64-Windows
native-DLL guard on this macOS host; no package/native acceptance is claimed. Luna
writing, Sol6.1 integration and Astra main review are complete. Dated commands,
source provenance and limitations are in the [texture evidence](runtime-evidence-2026-10-13/texture-recipes-motion/context.json).

Oct13 local recovery repair under [V01](../docs/architecture/visual_stimulus.md#v01)
and [E06/E08](../docs/architecture/system-contracts.md#e08): worker-local failure
recovery previously bypassed command registration and forwarded its cleanup under a
UUID the coordinator never issued. It now registers a command-local retained
admission/outcome before dispatch, keeps cleanup on the worker query route, preserves
exact context/deadline/replay and prunes local routing with the ledger. Coordinator
unknown-ID validation and supervisor-issued cleanup proof remain strict. Teardown
attempts owner/report/listener/channel closure with the original deadline even after
report-drain failure, then propagates the first failure.

The threaded RenderOwner/ReportBridge regression covers cleanup emitted while local
shutdown executes, prior finalized session scope, replay and pruning. Failure injection
verifies listener/channel attempts after drain rejection. Final authenticated transport
passes9; the [cross-owner validation](runtime.md#unresolved-findings-and-limitations)
records1316 passes/five platform skips/four deselections plus static checks and Luna/
Sol6.1/Astra review. [Raw provenance](runtime-evidence-2026-10-13/dev-machine-repairs/context.json)
retains the final-helper rerun boundary. This repairs a concrete local recovery defect,
not a reproduction of the complete historical failed-Setup/prior-calibration workflow.
Native failed-Setup/reuse and Save On-to-Off remain [rig-deferred](rig-verification.md).

Oct13 owner-authorized combined rendering/reset repair verifies two consecutive
normal60s Behavior/Tracking recordings at3602/3601 actual render groups
(60.0333/60.0167 groups/s), improving the combined baseline39.47/s. Renderer GPU0
and both camera/review NVENC GPU1 are confirmed by exact live PIDs/UUIDs in four
samples per trial. All six videos externally count/fully decode; both sessions close,
reset and restore original settings in the same live generation.

Under [V12](../docs/architecture/visual_stimulus.md#v12)/
[E13](../docs/architecture/visual_stimulus.md#e13), native row conversion, completed
PBO mapping/private copy, actual-context no-op checks, normalization outside admission
lock and private native pipe copying remove recording contention. Original ownership,
slot bounds, precision and encoder settings remain. Preparation release receipts are
retained for cleanup retry until all source/consumer ownership closes, then retired at
new preparation; this fixes the reproduced On-to-On unknown-resource shutdown.
That historical CPU budget included padding, readback/pipe copies and half-frame
scratch; the current sequential path retains the conservative ceiling without padding.
ARCH-002 keeps the existing cohesive native/preparation owners with small helpers,
no new dependency/process or whole-runtime reference.1123 regressions pass/3 skip/
6 deselect, native pipe14 pass, Ruff/static mypy427/boundaries667 pass.

Nominal60fps is not uniform frame timing or optical proof: repeat p9927.56ms,
max37.88ms. Review fidelity remains limited:1176 real samples/2367 capacity drops/
58 same-slot omissions and2424 explicit duplicates in3600 encoded frames. Dedicated
Save On-to-Off native verification, Eye/locomotion Tracking and paired/optical
acceptance remain open. Original GUI/settings are restored. Historical stimulus-only
measurements below remain distinct from this combined result.
[Dated raw evidence, verification and limits](runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)

Oct13 `stimulus-throughput-repair` implements the measured review-capture fix under
[V12](../docs/architecture/visual_stimulus.md#v12)/
[V20](../docs/architecture/visual_stimulus.md#v20)/
[E13](../docs/architecture/visual_stimulus.md#e13). Matched native60s trials on four
RGB8/all-output-VSync outputs show Save On30.13 real groups/s versus Save Off60.03/s.
Save Off's trial completes but session cleanup fails on an unregistered resource
after the preceding Save On session; this pre-change transition defect stays open.
Mean float-composite glReadPixels12.98ms and capture polling6.54ms dominate the
recording cost. Use an RGBA8 compositor for the already selected8-bit review path,
retaining float32 for packed10-bit, and fill a fresh host bytearray directly instead
of allocating a NumPy result then copying to bytes. The recording owner still copies
that buffer into its own bounded slot; deadlines, source/output rendering precision,
all-output VSync, trial timing and admitted-sample accounting are unchanged.

The first framebuffer-only run completes at50.42 real groups/s. The final instrumented
recorded run completes3600 real groups/60s (60.0/s),3422 real captures,178 padding
duplicates,166 same-slot omissions and12 capacity drops; all stimulus outputs close,
metadata syncs, reservation unlocks and external decode/recipe verification pass.
Mean readback submission falls to0.736ms and capture polling to3.40ms. These are
inclusive diagnostic timings, not optical measurements. A native768-pixel comparison
of the same compositor shader observes at most one8-bit code difference from the
former float-to-byte rounding; review video is not bit-exact, while physical
rendering and V13 input precision are unchanged. Final uninstrumented confirmation
also completes3600 real groups/60s (60.0/s):3423 real captures,177 duplicates,
169 same-slot omissions and eight capacity drops. All outputs close, metadata syncs
and original configuration restores; external count/full decode/recipe verification
passes for both final runs. The normal
uninstrumented GUI/runtime is left open in Configuration. Sustained simultaneous
camera/Tracking work and optical timing remain unverified.

ARCH-002 review keeps the implementation in the focused existing capture owner,
with no dependency/process or policy change. Native/scene modules receive only
transfer-type annotations; their existing cohesive size advisories remain reviewed.
Extend the owning rendering behavior module for8/10-bit retention, representation
locking, zero-wait fence polling and exact caller-owned host writes. Owning suite
passes244; Ruff check/format152 files, Win32 mypy136 sources and boundaries667/
zero violations pass. Retain failed diagnostic bootstrap/interrupted attempts,
concurrent GPU-placement context and complete native runs separately in the
[throughput methods/results](runtime-evidence-2026-10-13/throughput/context.json).

Oct13 owner-authorized GPU placement repair is now natively verified under
[SYS-002](../architecture.md#sys-002)/V19. Through NVIDIA Control Panel, add the
exact managed .venv/Scripts/cephvr-python.exe program and set OpenGL rendering GPU
explicitly to RTX5060Ti, then Apply. The previous generic Windows GpuPreference=2
entry and inherited NVIDIA global choice were insufficient proof of the actual
context. Leave CUDA GPUs at All and other driver/encoding settings unchanged.
The managed-image native renderer now verifies all four contexts against
GPU-77642118-1623-48dd-3686-1014aa86b818 (CUDA ordinal0), initializes actual assigned
RGB8 output modes/Idle and releases every native obligation. The owner's exact
Miniforge-base start_runtime_gui.py launch subsequently confirms all four outputs
ready without display issues in generationc3532451-334e-4874-beaa-3e181be7bc2d.
Leave that runtime/GUI open; no existing session is interrupted by this task.
These checks establish placement/startup, not optical correctness or sustained
presentation/encoding throughput. A separate concurrent throughput task remains open.
[Methods/raw GPU evidence](runtime-evidence-2026-10-13/gpu-placement/context.json).

Oct13 renewed owner screenshot/live read-only snapshot confirms a current AMD
adapter rejection, not only an old popup: controller generation10dc50d5-98da-463f-9bb9-02516f041026,
InitializeDisplay commande9933d53-eec0-4ec9-afa2-e04f8a1e3532 reports AMD Radeon
instead of RTX5060Ti, with all listed display resources released. The screenshot
shows the VS Code start_runtime_gui.py route and a visible Behavior preview;
read-only process paths confirm managed cephvr-python.exe children. Its exact
HKCU UserGpuPreferences entry already contains GpuPreference=2. That registry value
does not establish the requested actual context, and repeating the generic remedy
is not a verified repair. That earlier read-only investigation prompted the explicit
program-setting change and successful native checks above, which now close adapter
selection. Its prior matched RTX startup runs remain historical evidence.
[Controller assessment](runtime.md).

Oct13 fresh workflow audit: normal calibration assets fail pacing validation; a
separate profile using current accepted all-output VSync passes native grid Open,
two adjustments and confirmed Idle/closure. Regenerate the ordinary diagnostic
bundle before retesting its GUI path (V01/V19/V20). Independent open-loop60s
stimulus recording completes and externally decodes:3600 encoded frames/60s,
1820 real render groups (30.33/s),1805 captured groups,1795 duplicates and15 drops.
Median group interval32.18ms; median summed four-output swap durations2.42ms.
This run does not support the older sequential-swap bottleneck hypothesis as its
dominant explanation; capture/draw/context/transfer costs still need stage timing
and a matched Save-Off comparison. Padded60fps video is not60Hz optical evidence.
Combined camera recording cannot start with unset drain policy, and its failed-Setup
cleanup crashes the renderer on an unknown cleanup command link. Preserve that
separate E06/E08 failure for repair; normal stimulus-only closure and final exact
application shutdown pass. [Failure/remedy inventory](runtime.md),
[raw and external verification](rig-evidence-2026-10-13/workflow-tests/).

Oct13 Windows rig: V19 startup confirms four 60 Hz RGB8 outputs with requested
interval-1 swaps. A V01 native grid diagnostic using retained dummy geometry and a
separate all-output-VSync profile passes Open, live adjustments at sequences 1/2,
and Close with confirmed Idle/resource closure; accepted configuration is unchanged.
No optical accuracy, physical timing, mixed-DPI, reference-bar measurement or sustained
presentation-rate claim follows. The earlier native chooser crash is repaired under
G01; native GUI now completes with two separate hover-test failures, while the earlier
offscreen stage retains three projector-layout failures. The cross-owner assessment
below records exact stages and remaining limits.
The initial FFmpeg/ffprobe 4.3.2 incompatibility is resolved by the later matched 9.0.2
upgrade and synthetic composite closure check on RTX 2080 Ti (see runtime.md).
Recording/full-load acceptance remains open. [Current cross-owner assessment](runtime.md),
[raw evidence](rig-evidence-2026-10-13/) and [remaining rig checks](rig-verification.md).

Oct12 subgroup variations implement [V03 revision12](../docs/architecture/visual_stimulus.md#v03)
and [V08 revision5](../docs/architecture/visual_stimulus.md#v08): compact seeded rules
replace eager new repetition tables. Setup resolves by immediate-group repetition
index after condition substitution and validates concrete settings; it checks the
configured expanded-plan limit before sampling. Legacy tables remain supported.
No renderer RNG or device ownership changes. GUI authoring is compact at 10,000 and
1,000,000 repetitions; concrete Setup plans still scale with expanded epochs and
remain bounded (currently 100,000). The [current GUI/compiler assessment](runtime.md#current-scope-and-review)
records source/schema changes, 233 passing Visual Stimulus tests/one deselection,
layout evidence and native/rig limits.

The Oct12 model-hierarchy audit deeply traced live-calibration identities, sequence,
deadline, validation versus uncertain GPU failure, presentation/closure and blackout
ordering, with sampled compiler/media/recording/feedback paths. RT-001 identifies a
controller admission omission during application shutdown; the
[current cross-owner assessment](runtime.md#current-scope-and-review) owns its disposition
and verification. No renderer change or measured performance improvement is justified
by this pass. Native optical/GPU/full-load acceptance remains in the
[rig checklist](rig-verification.md).

Oct12 live frame/grid adjustment follows [V01 revision 18](../docs/architecture/visual_stimulus.md#v01)
and [G01 revision 148](../docs/architecture/gui.md#g01). A leased UpdateDisplayCalibration
carries bounded affine rectangles for the exact active diagnostic/revision and an
increasing sequence. Validate the whole request before writing existing GL-owner
warp buffers; render and present all outputs without asset replacement/window reopening.
The protected base profile/arena and inversion remain fixed. Evidence confirms the
sequence only after all outputs present; pre-write rejection retains the healthy
prior projection/sequence and reports failed update, while GPU/presentation uncertainty
remains Unknown with exact closure available. Fenced sessions never resume through
an adjustment. GUI partial/invalid edits send nothing; coalesce behind one update.

ARCH-002 keeps admission/validation/presentation in focused helpers and existing
renderer resource ownership. Buffer references alias existing tracked resources;
there is no additional GPU allocation or dependency. Affected backend suites
pass 659 tests/one deselection before the final mesh-precision guard, including authenticated controller-port/coordinator/
renderer transport with hardware injected. The final guard run passes 658 and
times out in one CLI-help case; the unchanged case passes an isolated rerun. Sixty GUI cases and seven final correction
cases pass (overlapping); source/static/contract checks and wide/narrow active-control
inspection pass. [Current dated evidence](runtime-evidence-2026-10-12/live-grid-context.json)
retains scope, failures and staged source context, without claiming full exact-final
coverage of concurrent Protocol/photodiode edits. Older workflow evidence below
remains distinct. Native GPU/Windows/DPI, optical correctness/latency and repeated
live-edit/closure acceptance remain in the [rig checklist](rig-verification.md).

Oct12 [V15](../docs/architecture/visual_stimulus.md#v15),
[V19](../docs/architecture/visual_stimulus.md#v19) and
[V22](../docs/architecture/visual_stimulus.md#v22) implement owner-requested
CephVR1.0-style output masks and photodiode placement. Optional output rectangles
clear mapped scene pixels to linear black before existing color correction; an
optional black marker area contains a separately positioned rectangular Pulse drawn above the
zones. Static zones persist in Idle and frame/grid diagnostics, including GUI bundle
export; raw measurement bars remain unobscured. The marker Frame/Pulse remains
trial-only, with the existing alternation and landmarks. Legacy patch rectangles
remain valid; positive integer rectangles must fit, with no clipping or resizing.
Planning preview illustrates placement with a white pulse. G01 revision150/V22
revision5 use a Frame/Pulse table with independent width/height and relative Pulse
origins. Full Projectors files are version 7; version-6 Size migrates into equal
dimensions and older standalone rectangles remain valid. Numeric calibration remains
version 4. Fifty affected cases, nine final presentation/file/render/parity cases
and 42 contract cases/79 subtests pass;
[current table evidence](runtime-evidence-2026-10-12/pulse-definition-table/context.json)
records the source stages, both-width captures and passing Ruff/format (289 files),
Win32 mypy (271 sources), 11 schemas/zero drift and boundaries (649 modules/zero violations).
Existing shared DataTable and rectangle/file owners replace the form/single Size
controls without new dependencies, rendering resources or runtime state.

ARCH-002 isolates zone editing and scissor-preserving clearing, keeps rendering and
calibration ownership intact, and moves photodiode draft/import operations out of
the large Projectors panel. Remove duplicate output lookup and fixed-page-height
plumbing. Native/scene size advisories retain cohesive rendering/resource ownership;
no shader, dependency, process or persistent GPU resource is added. The earlier local
GUI/Visual Stimulus/contract integration stage passes 665 tests, one Windows/rig deselection
and 79 contract subtests. Its 21-case final affected selection covers the initial
layout/export changes; these cover file migration, submission mapping, output bounds,
marker-over-zone order, grid/raw-bars behavior, scissor restoration, preview pixels,
growing tables and 1280/720 Runtime/Review parity. Ruff/format (289 files), Win32 mypy
(271 sources), schemas (11, zero drift), boundaries (649 modules, zero violations)
and whitespace pass. [Current source-stage context and raw evidence](runtime-evidence-2026-10-12/output-overlays/context.json)
retain corrected fixtures, observed layout defects and loopback-permission retry.
Both-width offscreen captures are inspected. Native Windows/WGL/DPI, optical black
levels/placement/timing, recorded GPU pixels and throughput remain unverified in this
increment; the existing [rig checklist](rig-verification.md) owns those checks.

Oct12 cleanup removes three constructor fields with no readers: the decoder's unused
ID counter, the scene renderer's unused clipping set, and the native port's unused
Idle color cache. Active state and evidence remain with their existing V01/V11/V19/V21
owners. Under ARCH-002 these cohesive modules shrink without new dependencies or
responsibilities. Final cross-owner selection passes 795 tests; affected Win32 mypy,
repository lint/format and boundaries pass. Raw cleanup logs and hash manifests were
removed at the owner's request on Oct12; these results remain historical summaries.
This establishes no new optical, native GPU,
throughput or rig acceptance.

Oct11 startup repair follows existing [V19](../docs/architecture/visual_stimulus.md#v19)
and E06/E08. Missing or ambiguous saved monitor identities produce a typed
configuration rejection only after exact sessionless resource release and confirmed
display evidence delivery within the original deadline. Controller/GUI operation
status exposes the corrective issue; Configuration remains available and a fresh
Setup can reuse the worker. Every identity is resolved before any window opens.
GPU/context errors, cancellation, expired deadlines, uncertain cleanup and failed
evidence delivery retain the existing failure path. The
[startup contract](../contracts/visual_stimulus/startup.md) records the evidence order.

ARCH-002 extracts coordinator display-report handling and the existing sessionless
cleanup helper. Native renderer and lifecycle files remain cohesive ownership
orchestrators; no new dependency, process or policy choice is introduced. Owning
renderer/lifecycle/coordinator/authenticated-controller cases cover missing/ambiguous
identities, complete versus stale/unreleased proof, cleanup/GPU/deadline/cancellation
failure and fresh Setup. The full portable suite passes 1,861 tests with six skips
and eight Windows/rig deselections; [current results](runtime.md) retain source and
validation scope. Native disconnected/reconnected startup acceptance remains in the
[rig checklist](rig-verification.md); this is not optical/throughput evidence.

Oct9 [V20/V15](../docs/architecture/visual_stimulus.md#v20) permits all-projector VSync
without a designated pacer. [E13](../docs/architecture/visual_stimulus.md#e13) derives
recording cadence from the common exact nominal enabled-output rate and records
null pacing identity; differing rates reject. Mixed mode still requires its selected
pacer. Policy/config version 9 and the prepared schema bind this behavior. Oct11
local regression/contracts/declarations cover it. The Oct9 Windows full-suite timeout
and passing focused rerun remain [historical evidence](review-evidence-2026-10-09/mcu-configurable-context.json);
its native cause is not proven fixed by the Mac pass. Native MCU Apply and a new
rendering/recording run remain pending.

Earlier Windows checkout `94285ac` passes the complete non-rig suite, all 42 stimulus
contract cases and 11 schema matches after regenerating stale local bindings.
[Current cross-owner results and limits](runtime.md) retain exact evidence; presentation,
encoding throughput and optical acceptance remain separate rig checks.

Oct9 authorized baseline repair restores the 500 ms preparation lead and unsets the
diagnostic pacing-output identity; camera drain margins are also unset. All 36 owning
configuration cases pass. Visual Stimulus contract discovery passes 42 tests and all
11 generated schemas match. [Current integration evidence](review-evidence-2026-10-09/implementation-context.json)
records full local validation; native presentation/encoding throughput, scientific
timing and owner-deferred encoder acceptance remain in the [rig checklist](rig-verification.md).

Measured-reference baseline (Oct12, `two-stage-projector-calibration`)
follows [G01 revision 146](../docs/architecture/gui.md#g01),
[V01 revision 17](../docs/architecture/visual_stimulus.md#v01),
[V15](../docs/architecture/visual_stimulus.md#v15) and
[V24](../docs/architecture/visual_stimulus.md#v24). The owner explicitly selects
config-controlled actual projected lengths. Per-screen `reference_x_px` /
`reference_y_px` resolve into output `reference_bars`, shared by native calibration,
measurement conversion and planning preview. Positive whole-pixel lengths must fit
the output; faces sharing an output must agree. Unset values retain the original
rounded quarter-output spans. Measure reference bars selects the protected `reference_bars` view: bars only on
black in exact native pixels, independent of prior measurements or corrections.
Adjust frame and grid selects `frame_grid`: complete mode-matched measurements
produce physical screen/image ratios combined with manual scale/offset/inversion.
Neither action requires throw ratio or projector distance. Both retain the same
V01 protected-input, GL ownership, Active/Closed evidence and deadline/cleanup paths;
Close must confirm release before switching views. The frame/grid uses V15 and does
not draw measurement bars; normal trial rendering ignores diagnostic selection.

Runtime and Review share the Pixel-to-mm calibration card with three equally
stretched columns and no explanatory text or pixel columns: Screen, paired Measured X / Y (mm), and read-only X / Y (mm/px).
Measured pairs derive scale independently of throw ratio; ideal read-only projector
distance additionally uses a positive config-only effective throw ratio. Physical screen
and subject distances remain independent. Full Projectors JSON version 7 / numeric
version 4 preserve lengths and measurements. Legacy full versions 3/4/5/6 and numeric
versions 1/2/3 migrate without changing prior spans or unmeasured historical distance.
Invalid lengths reject before draft mutation. Output-mode mismatch invalidates scale
without replacing measurement provenance. Export/submission preserves original
assets and creates content-addressed GUI affine corrections; imported nonlinear,
masked or weighted corrections still reject automatic replacement.

ARCH-002 retains focused measurement/file/profile helpers and existing native
render ownership, adding no dependency, process or persistent GPU resource. The
existing projector panel remains orchestration; boundary cohesion advisories retain
their established owners. Final affected GUI/config/render/preview selection passes
74 tests; separate contract discovery passes 42 tests with 79 subtests. Ruff/format,
Win32 mypy (265 sources), 11-schema drift and boundaries (642 modules/zero violations)
pass. Wide/narrow two-action card captures are visually inspected offscreen.
[Current workflow methods, hashes, failures and raw results](runtime-evidence-2026-10-12/calibration-workflow-context.json)
preserve local scope; [earlier measured-bar evidence](runtime-evidence-2026-10-12/projected-bars-context.json)
remains historical. No native Windows/GPU, optical, full GUI regression or rig
acceptance is claimed. Current zoom/keystone/fold, bar spans and physical mapping
remain in the [rig checklist](rig-verification.md).

Oct8 unpaired dummy execution uses all four saved active projector identities,
isolated **uncalibrated** geometry/color profiles and a 60-second procedural grating.
Temporary Front 60 Hz pacing satisfies [V20](../docs/architecture/visual_stimulus.md#v20).
Real startup observes required Idle submissions/framebuffer sizes/RGB precision
after strict SYS-002 RTX 5060 Ti verification. This is native initialization evidence,
not optical accuracy, timing or full-load acceptance. Runs40–42 complete real Setup,
Start, the immutable 60 s trial, output closure and session cleanup. Later run43
[output evidence](rig-wiring-evidence-2026-10-08/dummy-experiment/unpaired-run-43-output-verification.json)
records 1,182 admitted/submitted frames, four capacity drops, zero unresolved attempts
and confirmed EOF/drain/zero encoder exit. External count/full CPU decode and recipe
digest checks pass. Its 2560×2000 H.264 MP4 is 19.7 s at nominal 60 fps for a 60 s
trial; median render interval is 49.29 ms. This supersedes run42's 1,419-frame/23.65 s
measurement for the latest retained workload, without establishing a regression or
cause across differently loaded runs. Throughput and unpadded elapsed-time compression
remain separate issues; padding cannot restore missing physical presentations.
See current [E13](../docs/architecture/visual_stimulus.md#e13) sequential recording above and the
[rig checklist](rig-verification.md); this is not a scientific timing pass.

Recording uses one bounded full-frame pending encoder write instead of polling every
256 KiB, preserving native ownership/partial-progress/deadline rules. Bottom-up rows
are normalized exactly once even when the first write is pending. At cutoff, finish
already-admitted GPU transfers before sealing evidence; unresolved original-deadline
transfers still fail. Calibration CPU closure receipts survive retries and are revoked
on reopening a logical source. These fixes use existing owners under ARCH-002, V01/V12
and E08; owning recording cases pass 28. Oct9 restores defaults and records current
regressions above; all native attempts retain their dated raw evidence.

Under V01/V04/E08, disable GLFW's automatic fullscreen iconification so the four
windows survive focus changes. Load each current GLFW context with ModernGL's
loader-only initialization; GLFW retains sole WGL lifetime ownership. Detected
glcontext wrappers otherwise destroy an already GLFW-owned context at release,
observed as invalid WGL handles during cleanup. Move video selector/reset binding
from CPU preparation to the existing graphics handoff. Register the exact empty
revision-zero session cleanup catalogue before recipe/renderer resources, under the
existing catalogue lock. Retain private operation results locally and route only
Setup completion to the controller; display readiness still requires actual Idle
evidence. Native tests exposed these failures; no identity, precision, resource
proof or deadline check is bypassed.

Shared probe parsing now accepts FFmpeg's four-column pixel-format table; the
existing RGBA8 and packed RGB10 capture ABIs have explicit layout/matrix validation.
Capability evidence names conform to the existing prepared-record identifier schema.
System PATH FFmpeg 4.3.2 lacks the saved p4 preset; an isolated process PATH uses the
already installed static FFmpeg 7.1, preserving encoding arguments and global PATH.
The cached FFmpeg 8.0.1 package could not execute with available DLL paths and is
not adopted. Current ffprobe remains the installed 4.3.2 executable; actual output
inspection is recorded for run43 above. [Current integration assessment](runtime.md#current-scope-and-review),
[raw attempts and focused checks](rig-wiring-evidence-2026-10-08/dummy-experiment/).
The complete Visual Stimulus suite passed 170 before the latest context/format
repairs; latest focused context/registry checks pass 44, CPU handoff one, probe 28,
and strict review format eight. A later complete validation will supersede these.
Current source checks pass lint/format and 149-source Win32 mypy. Existing rendering
and session files remain cohesive owners; the small native attachment helper lives
in native_display under ARCH-002.

Library ownership references: [GLFW fullscreen hints](https://www.glfw.org/docs/latest/window_guide.html),
[ModernGL context creation](https://moderngl.readthedocs.io/en/latest/topics/context.html),
[ModernGL loader lifetime](https://github.com/moderngl/moderngl/blob/5.12.0/_moderngl.py).

Historical Oct9 timing validation used nominal-slot selection/padding, now superseded
by the Oct16 sequential implementation above under [E13](../docs/architecture/visual_stimulus.md#e13).
Its retained checks below establish only the source and policy tested at that date.
Pre-T cancellation, immutable cleanup cutoff, omission accounting and proved camera
tail boundaries are corrected. Successful encoder input is retained before maintenance;
a missing required mapping poisons normal retry. Sol accepts the corrections after 53
focused checks and the reproduced cancellation/omission paths. Astra independently
accepts these corrections and the exact camera terminal proof, with no remaining
padding finding. [Astra evidence](review-evidence-2026-10-09/nongui-astra-review.txt).
Repository-wide lint/format, Windows-target mypy, boundary and contract/schema checks
pass; the final portable suite passes and Sol/Astra accept the integrated source.
[Exact full-suite result and provenance](review-evidence-2026-10-09/nongui-context.json)
retain counts, source hashes and limits. Local checks
do not establish native encoder behavior or throughput.
[Current handoff](review-evidence-2026-10-09/nongui-luna-padding.txt),
[Sol review](review-evidence-2026-10-09/nongui-sol-padding.txt).
Original deadlines and rig deferrals remain.
The stimulus and acquisition wrappers now share the protected native launch handshake;
backend registration/retirement and exact native ownership remain with their owners.
[Shared launch review](review-evidence-2026-10-09/nongui-sol-launch.txt) passes locally;
Windows equivalence remains a rig check.

Oct9 local analysis of run43 finds 1,186 real groups in 60 s (19.77 groups/s), with
99.66% capture admission and all admitted inputs submitted at closure. Four capacity
drops do not explain the render-rate gap; this does not rule out recording-related
CPU/GPU contention. [Retained arithmetic and limits](review-evidence-2026-10-09/nongui-throughput-assessment.json)
require controlled per-stage rig measurements. Padding preserves review duration;
physical presentations and encoder/toolchain acceptance remain separate.

Oct11 source trace strengthens the multi-output pacing hypothesis. Decoding the
retained run43 Setup, pre-final and final snapshots gives the same controller/session,
`all_outputs_vsync`, four 60 Hz 8-bit outputs, and four retained requested swap intervals
of 1. The earlier Front-pacer description must not be read as interval 0 on the other
outputs: all-output mode requests VSync on each regardless of the selected pacer.
The current native presenter swaps all windows sequentially on one GL thread. The
49.29 ms median is near three refresh periods; accumulated swap waits are a leading
hypothesis, not measured causality. Retained display intervals are startup evidence,
not per-trial swap durations. [GLFW semantics](https://www.glfw.org/docs/latest/window_guide.html#buffer_swap)
allow driver overrides, so requested settings alone cannot establish actual waits.

Recording remains a second candidate: shared-context ordering, RGBA32F composition,
per-frame PBO allocation, readback and the completed CPU copy run on the GL thread.
Each 2560×2000 capture carries 20.48 MB; 60 fresh captures/s means 1.2288 GB/s of
payload before extra copies/encoding. This is arithmetic, not a measured bandwidth
limit. Recording normalization also holds the lock shared with capture admission.
The packed-10-bit Python mask loop is irrelevant to this 8-bit run. The trial loop
has no intentional 50 ms pacing delay, and later nominal-slot padding cannot cause
the historical run. Preserve accepted pacing; inspect raw submission entry/return
records first, then measure draw/capture/readback and recording on/off on the rig.
[Snapshot hashes, extracted settings and limits](runtime-evidence-2026-10-11/throughput-source-trace.json)
retain this investigation without claiming a backend fix or native benchmark.

Projector configuration JSON (2026-10-08) under [G01](../docs/architecture/gui.md#g01)
now combines all Projectors GUI experiment settings with reusable runtime profile
references. Physical inventory/mappings remain current; participation and pulse target
restore by logical face. Submission preserves geometry/color references and shared-output
coverage while rebinding current native properties. Numeric-only and legacy runtime
files remain supported through one Load JSON / Save as row. Full backend preparation
validation remains authoritative; no physical output is driven by loading a file.
ARCH-002 review extracts portable profile/native rebinding and file settings into focused
helpers; the Projectors panel remains the shared UI composition/selection owner. No new
dependency, backend process or policy choice is added. Validation results follow in the
[current runtime assessment](runtime.md#current-scope-and-review); Windows/optical
acceptance stays on the existing rig checklist.

Calibration authoring update (2026-10-08) under
[G01](../docs/architecture/gui.md#g01)/[V01](../docs/architecture/visual_stimulus.md#v01):
Launch always exports the grid using saved rig planes and display corrections.
CephVR1.0 `914ecbc` supplies world-phase colored solid/dashed grid, full-face center
cross, physical face dimensions and 50 mm ruler strategy. Guide geometry is built
once in a focused helper; narrow faces omit a ruler that would not fit, and labels
stay inside the face with dark backgrounds. Local tests verify world phase through
reversed U axes, midpoint spans, physical reference length and backend GLB parsing;
the sample asset is 316,004 bytes. Two focused cases pass after final guide formatting.
[Current local suite](runtime.md#current-scope-and-review) passes; actual corrected
output and optical measurements remain in the existing rig checklist. No projector
was driven in this local increment.

Latest Windows execution (2026-10-08, `7ba43b1` plus controller/native repairs):
managed coordinator/renderer startup, bounded idle and exact application cleanup pass.
Final full suite passes 1463 with eight existing GUI clipping failures/five privilege
skips; Visual Stimulus contracts/schema drift pass. The authenticated calibration
Shutdown test now waits for the asynchronous coordinator settlement inside its
existing bound; no runtime policy changed. Inventory finds only the operator display,
with no active projector outputs or saved profile/assignments. Actual corrected
Launch/Close and optical timing remain untested. [Dated methods/results](rig-wiring-evidence-2026-10-08/README.md)
retain scope; the [single rig checklist](rig-verification.md) owns remaining acceptance.

Earlier Windows check (2026-10-07, `08d146d`): managed coordinator/renderer startup
and long idle process liveness pass; normal authenticated application shutdown
confirms exact process absence. Inventory finds four projector outputs at 60 Hz.
The saved experiment profile, output-to-surface assignments and asset root remain
unset, and no exported diagnostic profile/arena was supplied. Untimed Launch/Close,
first-use restoration, physical corrections and optical timing therefore remain
pending. Native automated tests run in the full suite; GUI failures and native
teardown crash prevent blanket rig acceptance. See the
[current runtime assessment](runtime.md#current-scope-and-review) and
[dated raw evidence](rig-wiring-evidence-2026-10-07/README.md). E15 and the existing
encoder/scientific deferrals are unchanged.

Updated: 2026-10-08. The complete Visual Stimulus implementation is selected under
[ARCH-001](../architecture.md#arch-001). This report describes the uncommitted working
tree, preserving the existing controller, supervisor and acquisition work.
[V01–V28/E13](../docs/architecture/visual_stimulus.md) and [E05–E08/E14–E15](../docs/architecture/system-contracts.md)
remain authoritative; implementation does not mean experiment or rig acceptance.

Current managed-wiring increment: V20 file-only pacing propagation includes canonical
startup profile adoption, nominal-60 handling of 60000/1001 timebases, and resolution
of file-only output identity before pulse-disabled profile validation. Sol reproduced
three initial defects; the worker repairs passed re-review with 43 focused tests.
Installed validation and startup resolve pacing before strict profile validation.
Sol then reproduced lost policy-aware dispatch in the actual controller wrapper:
Setup rereads TOML instead of using its held policy. The focused wrapper repair and policy-drift regression now pass through actual
application assembly. Independent permitted-loopback controller/lifecycle tests pass
34 cases (1.16 s). Sol accepted the wrapper with no actionable findings and 43
controller/Visual Stimulus configuration checks passing separately. Earlier raw-provider passes did not
establish exact policy retention. Managed projector configuration and
renderer-owned V01 calibration/cleanup are active. Additive contracts are generated.
Sol accepted the repaired native leaf and final controller/coordinator/worker wiring.
Calibration uses the V15 correction/material pipeline, exact output contexts and
retryable partial resource closure. Focused helpers preserve one display and source
owner. The pre-Setup catalogue retains exact resources locally until Setup accepts
session context; no fake session evidence is published. Actual authenticated tests
cover first-use/repeated calibration, uncertain-close recovery, active Shutdown,
owner loss, late preparation cleanup and Close while preparation remains blocked.
The latter waits for exact worker Close application before releasing preparation and
asserts no late presentation. Cancellation before dispatch clears only the local
reservation; uncertain dispatched ownership remains retained. Setup rechecks all
diagnostic ownership after asynchronous validation. Sol and Astra have no remaining
source findings; final combined checks pass and evidence is tracked in the
[current wiring assessment](runtime.md#current-scope-and-review).
Hardware GL and optical presentation remain rig checks.

[V04](../docs/architecture/visual_stimulus.md#v04) image fitting is implemented in
the source model, renderer shader and planning preview: centered Contain, Cover
and Stretch within authored bounds, before geometry/calibration. Source/prepared
schemas carry the fit choice; omitted legacy values retain Stretch. The shader
uses the existing mode/period inputs and source texture dimensions; no render
process, frame transport or scheduling change. Local rendering/compilation/contract
checks report 68 passes and 79 passing subtests, with schema consistency and scoped
static checks passing. GPU shader compilation and physical Windows output remain
unverified. GUI details are in the [current runtime report](runtime.md#dashboard-frontend-implementation).

The 2026-10-05 managed rig launcher reached the renderer after correcting consumed
bootstrap-handle closure and confirming the coordinator's existing supervisor launch
record before planning its worker. The renderer then missed an original
`ReportWorkerHeartbeat` peer deadline and triggered safety shutdown; its cleanup
reported an unknown command and an async admission conflict. The deadline was not
relaxed. The exact delay between worker heartbeat construction, coordinator receipt
and supervisor forwarding remains open in `visual-renderer-startup-deadline` (TODO).
The emergency error is retained under `reports/emergency-*.json`; no projection or
camera command was issued. The Visual Stimulus/supervisor behavioral run passed 242
cases with one previously known pacing-key loader failure. See the
[runtime report](runtime.md#dashboard-frontend-implementation) for startup details.

Historical recording attempts 22–28 repaired retained trial failure admission,
camera clock validation, gray raw input naming, cleanup result format, pre-Ready
encoder obligations, Schedule/Release ordering, GPU fence arguments, compositor
resource order and trial-parent forwarding. Their interrupted reservations and exact
exit evidence remain in the [dated bundle](rig-wiring-evidence-2026-10-08/dummy-experiment/).
Run43 completion/decode results above supersede the early incomplete-run assessment.
Oct9 restores source defaults; measured timing and full-workload acceptance remain open.
ARCH-002 keeps focused owners and existing behavior test modules.

## Calibration arena asset

[V18 revision 4](../docs/architecture/visual_stimulus.md#v18) permits a dedicated
offline exporter for a static calibration GLB. It reads the G01 version 2 saved
rig JSON and reuses the GUI's four screen-corner calculation. The resulting unlit
mesh has a 10 mm grid, a center cross and a Front/Left/Right/Bottom name on each
screen, plus a thin tank outline. The owner's 2026-10-04 Desktop JSON defines a
120 × 166 × 110 mm tank and four screen planes; the generated local asset is under
ignored `cephvr-data/calibration`. The earlier timed trial program was removed when
the owner selected manual open/close. The
Visual Stimulus GLB reader parsed the 55,688-byte asset (806 triangles). This is
source/format evidence, not a managed launch or optical check. The saved JSON has
unset near/far/tolerance and correction values. The GUI's Launch action prepares
calibration files automatically, computing bounded diagnostic projection limits and explicit uncalibrated
geometric meshes from the current four face assignments and native monitor identities;
it exports the V15 display profile with the GLB into Protocol Assets.
The managed GUI now sends typed untimed Launch/Close requests with captured revision
and asset fingerprints before Setup. Active requires renderer presentation evidence;
Close requires Idle and confirmed release, restoring the prior display or known
uninitialized state. Its local review entry point has no controller transport.
Optical/native verification remains in `projector-calibration-launch` in TODO.

Oct14 projector-calibration rework (owner-approved; local validation only) follows
[G01 revision 183](../docs/architecture/gui.md#g01) and
[V01 revision 19](../docs/architecture/visual_stimulus.md#v01). A source review found
affine-only scale/offset correction, a 25 % centre-bar measurement, widget-only state,
Qt-logical vs GLFW-physical output binding, an unrecoverable late-completing Open and
silent live-update failures. The owner chose independent edge margins. Implemented:
(1) the valid area is the output minus four independent pixel margins per face
(blank = automatic, centered from a complete measurement, else the projector border;
undershoot rejects with its remedy), with calibration file version 5/full 8 and
conversion of older scale/offset files; (2) the reference view adds an output frame,
100 px ticks and a screen-aspect guide outline beside the bars, and any face may be
dark (Use ticks) so one projector is positioned at a time, using the existing output
subsets; (3) a `seam_check` view draws bold eye-level, corner, meridian and floor
lines through the same live mesh; (4) displays bind by native interface, with the
Windows adapter name matching Qt screens; (5) a late-completing Open is closed without
touching the renderer and a repeated Close repeats confirmed evidence; (6) live
edits show working/applied/rejected status and invalid fields are outlined; diagnostic
files are written atomically; the measurement table no longer pins bar lengths before a
measurement or blanks the distance on partial input; (7) the renderer-side calibration owner builds
its evidence through one `_build_evidence`/`_mark` pair instead of ten hand-built updates.
Local evidence (macOS offscreen): 2089 passed/6 skipped across tests, Ruff/format, Win32
mypy (782 sources), 11 schemas without drift, boundaries (687 modules, no violations;
`worker/display_calibration.py` 590 lines and `gui/projectors.py` 904 lines keep their
single owners, with launch helpers extracted to `gui/projector_launch.py`) and whitespace
pass. Rendered reference view and calibration card were inspected as offscreen images.
Not done and still open: native Windows/GPU/optical alignment; the 59.94 Hz refresh rate
GLFW reports as an integer; the `projector-calibration-retention` cause (not
reproduced; a launch/adjust/close regression and old-file loading are tested); and
old content-addressed `reference_*.json` assets remain intact. The unused standalone
pruning command and its dedicated test were removed in the Oct21 repository cleanup;
this does not change calibration publication, imported-profile protection or the
unresolved retention investigation;
Keystone is now corrected (below); lens distortion and depth remain uncorrected.

Oct14 keystone warp (owner-approved; local validation only): each face's valid area is
now a convex quadrilateral. Signed Keystone H / V pixel fields narrow the top or bottom
edge and shorten the right or left edge of the margin rectangle, and the screen maps onto
the quadrilateral by the projective transform of its four corners, tessellated into a
17×17 grid shared by the GUI profile builder, the submit path and the renderer's live
update (`projective_mesh`; the same four-corner wire message, now any convex
quadrilateral). Piecewise-affine error against the exact map is 0.13/0.29/0.69/2.1 px for
5/10/20/40 % top-edge narrowing on a 2560 px output (measured locally). Calibration file
version 6/full 9 adds `keystone_h/keystone_v`; older files load with none. Tests (macOS
offscreen): 2099 passed/6 skipped, Ruff/format, Win32 mypy783, schemas, boundaries688. They
cover mesh corners/straightness/perspective spacing, convexity rejection, the renderer's
17×17 live write (no allocation, inversion/area rejections), sign conventions, profile
validity, version 5 loading, signed entries, live keystone payload and preview. Not
established: that real keystone is removed on the rig, or that the sign convention suits
the Bottom mirror fold (check optically; the convention is output-space top/right).
The four exported geometric profiles now carry per-face scale, pixel offsets and
axis inversion when entered; unset fields produce identity mappings. A focused test
checks adjustment, mirroring and rejection of corrections beyond the output.

## Arena movement gains

[V24 revision 7](../docs/architecture/visual_stimulus.md#v24) now supports independent
longitudinal/lateral gains, explicitly selected by the owner to match CephVR1.0.
The canonical planar mapping adds optional `sideways_gain`; omission/null retains
legacy shared-gain behavior. Both gains use existing unit/function validation and
application-time evaluation before the unchanged midpoint-heading transform and
boundary slide. Zero disables an axis; yaw retains its existing independent mapping.
Program/prepared-trial schemas and the pure reference were updated. No input stream,
tracking estimator, resource ownership or timing semantics changed.

Local GUI/feedback/compiler/contract validation passes 194 tests and 79 subtests;
two additional focused authoring/reference tests pass. Ten runtime mapping cases
exercise unequal/zero/reversed/fallback gains at two headings; contracts check units
and source round trips. Static/schema/boundary checks and native GUI evidence are
in [frontend evidence](runtime.md#dashboard-frontend-implementation). Native Windows,
managed binding and physical closed-loop acceptance remain pending under
[the rig worklist](rig-verification.md). These are local implementation results.

## Authoring labels

[V03 revision 9](../docs/architecture/visual_stimulus.md#v03) adds optional epoch
batch labels for [G01 targeting](../docs/architecture/gui.md#g01). The bounded field
is retained in source/prepared-source JSON; compiler expansion settings and durations
are unchanged. Program and prepared-trial schemas were regenerated from the canonical
model; all 11 schema drift checks pass. Current GUI/compiler/contract results and
native authoring evidence are recorded in [runtime frontend evidence](runtime.md#dashboard-frontend-implementation).
A broader configuration test reproduces the existing loader rejection of
`presentation.pacing_refresh_hz`, whose managed adoption remains listed in TODO.
No renderer, pacing implementation or physical acceptance changed in this increment.

The 2026-10-05 GUI advanced update follows [G01 revision 93](../docs/architecture/gui.md#g01)
and V07: new authoring instances default to reset false, while imported resets and
assignments remain explicit. Advanced settings now use one card; the opacity editor
is removed, and fixed-duration fades encode ordinary V05 opacity keyframes without
a new renderer mechanism. Imported custom curves remain preserved. + Control is
a separate dialog launched below Advanced settings (action hidden during its draft), restricted to closed-loop Texture/Looming
with the three Tracking channels; imported mappings and arena axis controls remain. Body-relative input mapping to 2D screens awaits the local-axis versus
rig/heading choice; no conversion is silently introduced. Explicit ranges still
await the clamp-versus-extrapolation answer, with no change to V24 gain/offset behavior. [V02 revision 12](../docs/architecture/visual_stimulus.md#v02)
records the confirmed clockwise Bottom direction (Right front→back, Left back→front)
and subject-to-screen lever arms. Linked movement still awaits source/target feedback
ownership; no motion-link schema,
compiler or rendering behavior is claimed. GUI document guards now reuse the existing
16 MiB engineering default; Setup limits and policy values are unchanged. Large
200-epoch multi-layer round-trips and cached trial switching are locally verified.
A separate planning preview now reuses canonical expansion/V07 state for enabled
screens from either side in a rotatable 3D rig view using Devices geometry, with cached per-face
compositions, on-demand assets and bounded approximate arena rendering. Unset
tank/plane geometry prompts configuration rather than guessing dimensions. It applies
the GUI screen scale/offset/inversion calibration using the same mapping as export,
with assigned-resolution pixel normalization. Blank corrections share export defaults;
invalid corrections report errors. It applies no live Tracking, arbitrary runtime
warp/photometric profiles or physical output; actual video codec
playback remains unverified locally. Variation captions match stimulus columns and
ordered values materialize independent epochs, including video end modes and arena
gains, without runtime schema changes. Authoring Random samples a bounded numeric
range at a positive precision step, using batch Repetitions for the count; mixed
fixed lists repeat in order with a fresh draw per resulting epoch. Cached choices
remain stable until range/precision/count changes.
Concrete epoch values are saved; no runtime random rule or Setup-seed change.
Final commit cleanup retains the owning GUI tests, removes temporary review harnesses
and duplicate results, and verifies 183 GUI/client-state/compiler checks. The existing
pacing-default loader rejection remains open; no Windows/physical-output acceptance
is claimed. Current GUI/compiler checks and limits
are in [frontend evidence](runtime.md#dashboard-frontend-implementation).

## Output participation

[V15 revision 10](../docs/architecture/visual_stimulus.md#v15) and
[G01 revision 65](../docs/architecture/gui.md#g01) align the GUI draft
corner conversion with front-attached side/Bottom screens. The operator plot adds
drag rotation and ideal centered-projector footprints from distance/throw and
assigned display aspect, including the Bottom 45° mirror fold beneath Right.
One Projection button/legend entry groups the optics, with distinct violet footprints.
The Bottom diagram uses a schematic pyramid from mirror center to footprint.
Valid central Bottom paths remain visible when outer-ray clearance is incomplete. Backend corner validation, off-axis math and output
corrections are unchanged. Local tests and native plot evidence are recorded in
[frontend evidence](runtime.md#dashboard-frontend-implementation); managed binding
and physical optical acceptance remain pending.

[V15 revision 6](../docs/architecture/visual_stimulus.md#v15) separates output
participation from the full fixed calibration. Optional `enabled` defaults true;
active-output/mapping properties drive preparation, native windows, renderer checks,
recording tiles/budgets and output evidence. Full profiles retain geometry/mappings.
Photodiode visibility/placement and pacing are independent under V20/V22.
Explicit `pacing_output_id` selects an enabled timing output; old pulse-enabled
profiles without it retain their photodiode target. `photodiode_enabled=false`
retains inactive/missing placement without target/bounds checks, suppresses the
patch and emits null marker fields. Enabled pulse placement remains validated.
Native swap order/intervals and review encoding use pacing, not pulse placement.
All 15 nonempty four-output subsets preserve projection matrices in local tests.
Those tests exposed a pre-existing frustum-distance sign opposite to the documented
`-dot(pa-pe, normal)` and model validator. Corrected the sign and removed an invalid
observer override from the earlier renderer test. Physical calibration and optical
accuracy remain unverified; see [rig checks](rig-verification.md).

Validation on 2026-10-03: combined GUI/client/Visual Stimulus suite passes 186 tests
(one optional dependency skip, one Windows deselection), authenticated transport
included with loopback permission. Contracts pass 40 tests and 79 subtests; 11 schemas
match, Ruff/format and Windows-target mypy (141 GUI/backend files) pass. Boundary
checker reports zero violations across 475 modules, with retained cohesion warnings.
[Native UI evidence](gui-dashboard-2026-10-01/README.md) is distinct from rig evidence.
GUI participation, timing and geometry drafts are not yet connected to managed
configuration transport. The rig editor produces canonical four-surface geometry
from entered centered screen/tank dimensions and subject offsets; tests validate
corner winding and projection matrices. Per-face projector distance/throw ratio,
scale/offset/reversal and imported calibration/mask paths remain local drafts;
applying authored corrections to adopted profiles is still integration work.

ARCH-002 review reuses immutable display records and filtered properties, without
new coordination/dependencies. Existing large native/engine/recording owners receive
only focused iteration changes; geometry and process/resource ownership stay intact.

## Implemented scope

Final Windows repair snapshot (2026-10-01, baseline HEAD
`826984255e0a8469afccbda2dcaf8c642b528b33` plus uncommitted repairs): 123 tests,
40 contract tests and 11 schemas pass. Concrete PyAV video stream/frame and TIFF
page/dtype/enum handling clears installed-extra Windows-target mypy; repository
check passes 525 source files. Bounded generated TIFF uint8/uint16 decoding preserves
exact pixel values and rejects float input; most other resource tests use fake
prepared decoders, so these results are not broad codec fidelity coverage. No physical projection,
calibration or full composite/encoder workload was performed. The installed PATH
FFmpeg4.3.2 failed bounded explicit-2080 Ti encoding; production encoding remains
unvalidated. [Dated evidence](rig-audit-2026-10-01/README.md) and the
[single rig worklist](rig-verification.md) retain current limitations.

[V01](../docs/architecture/visual_stimulus.md#v01) owns the Visual Stimulus name.
The runtime, tests, contracts, configuration and documentation use `visual_stimulus`;
console commands are `cephvr-visual-stimulus` and `cephvr-visual-stimulus-worker`.
Install the `visual_stimulus` dependency extra. Rebuild all clients against the renamed
Protobuf packages/services and update saved configuration to `visual_stimulus` and
`save_visual_stimulus_data` (`saveVisualStimulusData` in JSON). Field tags, decision IDs,
port 50054, output filenames and program/prepared format 2 are preserved. This changes
interface names, including recorded compatibility identifiers; it does not migrate
previous saved configurations or assert compatibility with older analysis consumers.

The runtime under `src/cephvr/visual_stimulus` includes canonical lightweight models/configuration,
strict program compilation, exact resolved timing and immutable transitions, protected
asset preparation and budgets, coordinator/worker services, lifecycle/resource tracking,
ModernGL/GLFW scene rendering, bounded video decoding and feedback consumption,
recording with analysis-ready recipe/evidence outputs. Offline replay/export is owned
by analysis software under V13 and is not implemented in this experiment package.
Controller-facing validation and writer schemas
remain graphics-free. Pydantic is a base dependency; native graphics/media libraries
are lazy imports supplied by the `visual_stimulus` extra. Entry points are `cephvr-visual-stimulus` and
`cephvr-visual-stimulus-worker`. The analysis request/report/export schemas remain shared contracts;
there is no experiment replay CLI, offscreen export adapter or recorded-state player.

Setup retains one canonical PreparedTrial and PreparedHandle per trial; controller
summaries derive from it. The coordinator publishes `_stimulus_LOG.json` at/after
confirmed release onset, including Save Off. The persistent renderer owns GL and live
state; the coordinator never relays pixels or per-frame commands. Recording uses bounded
capture ownership, required JSONL evidence and one fragmented-MP4 FFmpeg path. Recipe,
evidence and review video closure remain independent. Empty/all-dropped paths have
explicit predicates and do not insert frames or infer successful closure.

The rendering core supports four off-axis views, unlit GLB arenas, images/video,
procedural and image textures, ordered overlays, geometric mapping, photometric curves
and photodiode output. Linear-premultiplied composition preserves finite RGB excursions
until the named output clipping boundary. Bounded asynchronous GPU diagnostics retain
per-group/output coverage and compact Save Off counters; missing observations cannot
be interpreted as no clipping. Compatible instance state continues across epochs,
absent instances pause, and incompatible video asset changes select separately prepared
textures/decoder cursors. Arena reservation includes generated vertex attributes and
both material texture variants with all allocated mip levels. Feedback preserves ordered finite batches, generation/freshness
checks, holds, additive motion and constraint evidence. Tracking production/readiness is
not implemented or fabricated.

The retained recipe contains the authored snapshot, resolved timing/settings/seeds,
asset/dependency fingerprints, display/calibration references, renderer compatibility,
provenance and shader uniform layouts. Save On evidence retains exact consumed shader
words, effective poses, actual video selections/holds, output submission observations,
clipping coverage, recording omissions and completion state. Output-contract tests
check serialization and coverage without rendering/exporting offline. Save Off retains
the recipe but cannot guarantee actual-output reconstruction. Matching external assets
must be preserved separately. Analysis implementation and original-pixel equality
remain unverified.

## Local verification

The simplification audit on 2026-09-30 used the dirty working tree at HEAD
`7ae3767cea92bf7af94153d417e40df997e1fd05`; HEAD alone does not identify the tested
snapshot. Existing backend work and concurrent tracking changes were preserved.
[Raw evidence and source/test hashes](visual-stimulus-evidence-2026-09-30/simplification.txt)
record commands, baseline, increment checks and static results; the
[final integration output](visual-stimulus-evidence-2026-09-30/integration.txt) records
execution. These are E15 lightweight checks, not native, optical or performance acceptance.

- Baseline: **101 passed, 1 Windows-only test deselected**. The sandbox initially
  denied five authenticated loopback socket binds; those tests passed with local
  network permission, without changing their assertions.
- Recording increment: **112 passed, 1 deselected**. Final combined run: **663 passed,
  5 native-platform skips, 1 Windows-only test deselected**, including **121 stimulus
  passes** and acquisition/controller/supervisor/shared/launcher/client integration.
- Ruff lint/format: **134 files** clean. Windows-target mypy: **119 source files**
  clean. Boundary checker: **421 modules**, zero violations; its count includes
  concurrent work outside this backend. Cohesion exceptions are assessed below.
- Twenty added cases extend the existing recording/resources behavior modules:
  partial child launch and exact cleanup, retained deadlines/releases, pending
  capture/session ownership, loop/hold reset, stale decode/delivery, request
  coalescing, idempotent leases and mixed-size memory admission. Existing scenarios
  and E15 markers remain intact.

The earlier rename verification below is historical evidence, not a rerun during this
audit. It preserved all **639** scenarios collected before/after the rename; a
concurrent supervisor case was present in its execution run. The historical acquisition
failures have since been resolved and verified in the [acquisition report](acquisition.md)
and are included in the current integration run.

| Check | Result and scope |
| --- | --- |
| `python -m pytest -q tests` after the rename | **616 passed, 7 skipped, 17 failed**. The exact failing test names match the existing acquisition baseline. |
| Visual Stimulus tests in that run | **101 passed, 1 Windows-only skip**. |
| Controller/supervisor tests in that run | **294 passed**, including concurrent supervisor work. |
| `python -m pytest -q contracts/visual_stimulus/tests` and configuration checks | **43 passed, 79 subtests passed** (40 contract cases plus 3 configuration cases). |
| Tracking contract unittest discovery | **48 passed**. |
| `python contracts/visual_stimulus/generate_schemas.py --check` | **11 schemas**, no drift. |
| `python tools/generate_contracts.py` | **19 Protobuf sources** compiled; field tags and enum numbers compared against the pre-rename snapshot and retained. |
| Ruff check and format check over `src tests tools` | Passed; **553 files** formatted. |
| `python -m mypy --platform win32 src` | Passed across **460 source files**. |
| `python tools/check_backend_boundaries.py` | **390 backend modules**, zero dependency violations; reviewed size warnings below. |
| `python -m compileall -q src tests`, `git diff --check` | Passed. |
| TOML parsing, root register and Markdown path checks | Backend config/policy versions match; **112** decision revisions match; all renamed documentation paths resolve. |
| Packaging | Wheel and source distribution built. Extracted-wheel imports/descriptors/writer schemas pass without graphics/media initialization; only renamed backend packages, commands and dependency extra are shipped. |

Authenticated loopback checks exercise real controller, acquisition coordinator,
supervisor outbound/registry and Visual Stimulus service/runtime components. Coverage includes
configuration/display-status separation, resolved artifact handoff, lifecycle ordering,
retained duplicate/conflicting commands, stale generations, original deadlines,
worker errors, interruption and cleanup. The supervisor test uses the actual persistent
pre-session renderer launch shape and reconciles exact retained executor completion;
admission is not treated as cleanup success.

## ARCH-002 implementation review

Oct23 `hierarchical-code-review`: Luna discovery and Astra review of dummy recording
setup/scheduling/completion and optional preview reader fences found no new confirmed
defect. `recording/capture.py:217` sorts/rebuilds the bounded ready queue under its
lock on every completion. An ordered-append fast path with out-of-order fallback
is a conditional optimization only: profile first and preserve reservation ordering
under V12. No bottleneck or rig improvement was measured. No renderer changes are
recommended solely from size warnings. [Review scope/checks](runtime.md#maintainability-review).

Oct19 `code-sweep-oct19` removes the unused engine-access wrapper and unused scalar
sRGB decoder. Texture patterns reuse the identical existing `_mix`, `_smoothstep` and `_num`
functions from the geometry module they already import. This adds no dependency or
owner, and preserves V04 pixel formulas and resource lifetimes. The owning resources,
rendering and lifecycle selection passes 184 tests, including existing reference
raster hashes; native rendering/rig acceptance remains separate.
[Raw checks](runtime-evidence-2026-10-19/code-sweep/visual-after.txt);
the final numeric-helper consolidation also passes all 16 texture/recipe cases.
[AST equivalence](runtime-evidence-2026-10-19/code-sweep/equivalence.txt) confirms
the three retained function bodies match their removed duplicates.

Owner-approved Oct19 correction: polar geometry now clamps finite RGB channels
to 0–1 before multiplying by 255, matching ordinary patterns under
[V04](../docs/architecture/visual_stimulus.md#v04), revision 16. The parser continues
to accept finite out-of-range channels. The original parsed 8x8 polar recipe with
`color_a=[1e308,0,0]` raised `OverflowError`; it now generates successfully. The owning
reference-pixel test additionally compares positive/negative extreme channels and
an in-range midpoint against clamped inputs for both colors of ordinary and polar
gratings. Its original reference hash still passes. Rendering and resource tests:
133 passed. Scoped Ruff/format, Win32 mypy, boundaries and whitespace pass; this
does not establish native rendering or rig equivalence.
[Original probe](runtime-evidence-2026-10-19/code-sweep/probes.txt),
[regression failure](runtime-evidence-2026-10-19/code-sweep/approved-clamping-red.txt),
[passing tests](runtime-evidence-2026-10-19/code-sweep/approved-visual-green.txt),
[commands and provenance](runtime-evidence-2026-10-19/code-sweep/approved-context.json).

The Oct13 texture increment separates recipe parsing, formula rasterization, geometry,
protected dependencies and preparation admission. Linked-motion validation, compiler
pivot preflight and renderer binding are focused helpers over existing state fields.
No whole-runtime references, alternate renderer or per-frame recipe generation are
introduced. The 635-line pattern module remains one cohesive legacy formula catalogue;
its size warning was reviewed rather than split into generic dispatch scaffolding.
Tests extend existing compilation, rendering, resources and dashboard behavior owners.
Pillow is pinned for the legacy blur/image conversion semantics; GUI recipe inspection
keeps numerical/image dependencies lazy.

The 2026-10-07 V01 review keeps GL-thread output/Idle restoration in the native port
and engine, and one protected-source promotion/release registry in NativePreparation.
Calibration drawing and asset preparation now have focused helpers. Sol accepts these
cohesive state owners; their size warnings do not justify duplicating closure state.
The dedicated calibration behavior module uses distinct fake-GL context, protected-file,
restoration and partial-release fixtures. Hardware GL remains unexecuted locally.

Each increment used focused state and operations. Shared command admission and compatible
FFmpeg argument/capability/I/O mechanisms are reused; acquisition policy remains separate
from Visual Stimulus's lossy, fixed-composite, fragmented-MP4 requirements. Resource preparation,
trial admission/execution, feedback, scene allocation, arena drawing, GPU diagnostics,
capture and encoder ownership have separate cohesive modules. The V13 ownership
revision removed replay resource readers, offscreen GL, export orchestration and live
renderer branches for recorded-state playback. Small test-only evidence readers check
experiment output coverage; they are not shipped as an analysis product. No feature
module retains a reference to an entire backend runtime.

The simplification audit removed three write-only recording fields and an unused
encoding property, inlined a one-call output wrapper, and consolidated resource-release
classification while retaining each resource's own closure predicate (V12/E13, E06/E08).
The recording facade fell from 781 to 751 lines; native child/file ownership remains in
`EncoderTrialOwner`, not in a second bookkeeping owner. The canonical typed evidence
and output-result paths still retain failures and exact process/file identity.

Timestamp selection and its generation identity now live in the focused
`resources/video_selection.py` module (V09/V10). The decoder scheduler shares one
content-match operation at decode completion and delivery, and reuses its fixed worker
assignment for scheduling/closure (V11). Its file fell from 598 to 512 lines without
changing locks, decoder-thread ownership, clock progression or coalescing semantics.
The pure cursor algorithm itself is unchanged. A redundant texture-upload cast was
also removed; no graphics behavior changed.

The audit reproduced and corrected a pre-existing V11 admission error: multiplying the
latest frame size by the instance count admitted 40 bytes of mixed-size frames against
a 32-byte limit, and could reject valid mixtures in the opposite order. Admission now
sums the prepared frame sizes using one size calculation and checks both decoded and
working-memory limits before registering the instance. This intentionally corrects
admission behavior to the existing limits; it is not a new policy or a throughput claim.
No package was added: the existing standard-library, media and native dependencies
cover these mechanisms. No RPC/schema/configuration or architecture decision changed.

The 2026-10-01 cross-backend ARCH-002 sweep removed the write-only
`NativeRecording.video_sync_factory` attribute: the constructor still passes the
factory directly to `EncoderTrialOwner`, its sole runtime owner. The recording path,
process/resource identities and closure evidence are unchanged (V12/E13, E06/E08).
Visual Stimulus and Tracking `authenticate()` bodies use the same lookup and identity
check shape and both delegate credential proof to shared `require_authenticated_peer`.
A wider RPC boundary helper would blur their distinct command/worker admission and
deadline policies. No other
extraction or naming change was justified. Exact source provenance and local checks
are recorded in the [2026-10-01 evidence](visual-stimulus-evidence-2026-10-01/simplification.txt).

The boundary check's size warnings are reviewed cohesion exceptions: the canonical
program model owns the discriminated schema; recording/native owns the recording facade
with capture, encoder, outcomes and session work extracted; rendering/scene owns live
draw orchestration with allocations/shaders/arena draw/capture extracted;
rendering/native owns context/output lifetime and submission; rendering/engine owns
trial state and schedule orchestration; resources/video owns bounded playback scheduling
and lease delivery with selection/decoder/index/session bindings extracted; worker/lifecycle owns command routing and
progress with preparation, trial, timing and cleanup operations extracted. Existing
non-Visual Stimulus size warnings remain recorded in their owning reports. No complexity reduction
or source-level check is presented as a measured throughput improvement.

## Windows handoff and remaining acceptance

Run the [stimulus handoff procedure](rig-verification.md#stimulus-implementation-handoff--execution-procedure)
with explicit rig inputs and `tools/test_on_rig.ps1 -Install`. The runner installs Visual Stimulus
dependencies, performs automated checks and preserves logs. Windows-native launch,
process authority/worker loss, named pipes, protected files, partial allocation/cancel,
GPU identity/framebuffer precision, shader execution, display/projection/color/photodiode,
pacing, decoder/media fidelity, encoding throughput/storage/crash/empty-input behavior,
analysis-input evidence fidelity and combined workload remain pending rig procedures.
Offline export acceptance belongs to the analysis software and needs its own implementation. No GPU or Windows
native behavior has been exercised on this machine. Firmware, GUI authoring, tracking
implementation and calibration measurement remain outside this stage.

## Verification evidence — 2026-09-24

The following records the original declaration snapshot; no exact source revision
or full command transcript was recorded, and these checks were not rerun during
report consolidation. Counts and implementation limits describe that snapshot.

The ten [pure regression tests](../contracts/visual_stimulus/tests/test_simplification.py) passed:
version/complete-setting rejection, parameter/coefficient and coordinate-dependent units,
feedback gain/rate compatibility, consistent opaque output IDs, bounded strict JSON,
single-plan structure, exact evidence byte preservation and envelope checksums/bounds.
The [drift/hold source](../contracts/visual_stimulus/examples/drift-hold.json) validated as format 2.
The [generator](../contracts/visual_stimulus/generate_schemas.py) reproduced all 13 published schemas
without drift. Python implementations and interface declarations parsed successfully.

The complete 15-file Protobuf set compiled. The obsolete parallel schedule messages
and field were deliberately removed; the former control field's number/name are reserved.
All unrelated existing wire field names/numbers/types, enum values and reservations
remain intact. Program/PreparedTrial format 1 is intentionally rejected; rebuild clients
against the new declarations and use format 2. WatchState remains the only streaming RPC.
All 61 root-register revisions matched their owners; changed-document relative links resolved.

At that snapshot, the implemented Python changes were pure schemas/parsing/unit checks and evidence
payload/framing helpers. Compiler/native-transport/renderer/recorder/recovery interfaces
remained declarations. No Windows cleanup, GPU rendering, video encoding, recovery/export
runtime or rig behavior was tested. The existing encoder input-format, timestamp precision
and final-frame-duration feasibility deferrals remain. No runtime output-file validator,
new overload policy, original-pixel equality claim or measured speedup is introduced.

## Validation limits

Oct13 `long-protocol-resource-scaling` implements owner-authorized bounded residency
and advance loading for ordinary still images and image-producing CephVR1 recipes
under [V04 revision14](../docs/architecture/visual_stimulus.md#v04), while retaining
[E07](../docs/architecture/experiment.md#e07) whole-session validation and protected
sources. One CPU loader produces a bounded handoff; the GL owner uploads in bounded
chunks, polls completion without waiting, and evicts only unpinned completed resources.
Compatible image content/interpretation shares residency across trials. Setup retains
source descriptors and schedule metadata, validates every image sequentially, and
pins each instance's first-use image. Indexed next-use lookahead avoids scanning the
remaining protocol at every epoch; a 100,000-epoch regression covers this boundary.

If an image misses its scheduled onset, the previous texture remains selected while
current motion and original clocks continue. Save On evidence version4 records requested
and actual asset IDs/zero-based indices, readiness holds and repeated image identity;
version3 input remains accepted. Repetition means the preceding selection/render attempt,
not identical moving pixels or optical proof. Submission outcomes remain separate.
Save Off retains E13's absence of per-frame output and emits a bounded miss summary.
Reload/decode errors remain failures; readiness misses alone use the accepted hold.

ARCH-002 separates source interpretation, scheduling, CPU handoff, GL uploads and
residency from existing lifecycle owners, without new dependencies or processes.
The existing large preparation/session, renderer and recorder modules remain cohesive
orchestrators; new responsibilities are focused modules with explicit interfaces and
no runtime back-references. Worker joins protect source lifetime, and unresolved GPU
completion/release retains resources, reservations and cleanup obligations for retry.

This bounds decoded-image residency, not all protocol memory. Protected handles,
descriptors, schedule metadata, per-trial scene targets and eager video/arena/calibration
resources still consume existing budgets. The union of first-use anchors plus held/next
working sets must fit; Setup rejects insufficient capacity. Chunking does not bound a
native driver's allocation latency. Real storage/decode contention, native fence behavior,
peak RAM/VRAM, onset timing and simultaneous recording require the owner-deferred
[rig checks](rig-verification.md). Final local validation passes 296 owner tests (one platform/rig case deselected),
42 contract tests/79 subtests, 11 schemas, scoped Ruff/format (166 files), Win32 mypy
(150 sources) and boundaries (686 modules, zero violations). Luna writing, Sol6.1
integration and Astra main review are complete. Intermediate fixture/reservation
expectation failures and loopback restrictions remain identified separately.
Validation and review provenance are retained
in [image residency evidence](runtime-evidence-2026-10-13/image-residency/context.json).

The current checks exercise application behavior and authenticated transport on this
host. They do not establish native runtime or rig equivalence. Keep pending native/rendering/encoding, optical,
calibration, failure/durability and simultaneous-load checks in
[rig verification](rig-verification.md). No historical declaration pass closes them.

The 2026-10-03 GUI refinement moves pacing identity and the 60 Hz target to the Visual
Stimulus TOML under [V20](../docs/architecture/visual_stimulus.md#v20). TOML syntax is
checked; managed adoption/native refresh validation remains pending. No physical
refresh or render-rate guarantee is established by this configuration declaration.

The GUI geometry builder now positions parallel screen planes by explicit positive
perpendicular subject-to-screen distances under [V15](../docs/architecture/visual_stimulus.md#v15),
independently of tank walls. The GUI now derives the right-screen distance from
the left using equal tank-wall offsets, as explicitly confirmed by the owner;
o independent right distance remains in GUI calibration JSON v2. It shares corner generation with the schematic; backend
corner schema/rendering is unchanged. Physical placement and managed profile adoption
remain unverified. Local geometry tests cover independent planes and invalid distances.
## Startup GPU placement and closure

Oct13 actual launches record AMD Radeon OpenGL contexts rejected against the
required RTX 5060 Ti under [SYS-002](../architecture.md#sys-002). Evidence includes
[09:35 emergency](emergency-328494867654500-500f6310-e26f-453c-be55-81996dc33dd2.json)
and [screenshot-associated emergency](emergency-328763941422600-cc8b402d-c96c-42d3-82f2-d2c3ee11b8f0.json).
A task-owned identical executable with no Windows GPU preference reproduces AMD
on all four configured projectors. The existing configured managed executable
(`GpuPreference=2`) uses the RTX 5060 Ti in direct probes and two fresh managed
launches. Relocating GLFW's bootstrap does not correct the default selection; that
probe workaround is not adopted. The original failing launch route remains unknown.
No production Windows preference or driver was changed.

Under [V19 revision 6](../docs/architecture/visual_stimulus.md#v19), the startup
closure defect is repaired: narrowly classify a healthy wrong-adapter context as
unavailable output placement, reuse exact sessionless cleanup/rejection delivery,
and expose the managed executable's Windows Graphics remedy. No wrong-GPU rendering,
Idle/Ready claim, fallback or retry is allowed. CUDA driver/API failures, actual GPU
operation failures, cancellation, lateness and uncertain cleanup retain E06/E08
escalation. ARCH-002 adds only focused error classification/remedy to existing
owners; no new process, dependency or lifecycle state. The existing native renderer
cohesion advisory remains; window/context ownership stays together.

Final affected checks: 249 Visual Stimulus/platform tests pass (including authenticated
controller wrong-adapter rejection and fault/deadline/cleanup gates), Ruff/format
154 files, Win32 mypy 137 sources and boundaries 665 modules/zero violations pass.
Three actual isolated AMD contexts are rejected with exact native window/context/GLFW
release. Final managed GUI launch confirms all four outputs initialized, revision 1,
Configuration phase and no warnings/errors; it remains open for the owner. This
launch passed the existing exact RTX 5060 Ti verification. No camera, recording,
optical, electrical or full-load acceptance is implied. Raw methods/results and
source hashes: [GPU evidence](runtime-evidence-2026-10-13/gpu-selection/context.json).
