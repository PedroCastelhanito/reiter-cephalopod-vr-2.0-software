# Acquisition status

Status: host implementation, source review and lightweight local verification are
recorded below (2026-09-30). Native Windows, device and full-workload acceptance remain
pending on the rig. This is not experiment-readiness approval.

[ARCH-001](../architecture.md#arch-001) selects this stage;
[ARCH-002](../architecture.md#arch-002) governs module boundaries. The
[acquisition decisions](../docs/architecture/acquisition.md) and their
[contracts](../contracts/acquisition/README.md) own behavior. The previous
[controller/supervisor review](runtime.md) remains separate.

## Ownership and review

Review covered coordinator/camera/recording/serial ownership, focused peer interfaces,
authenticated bounded admission and original deadlines. Integration closed private
handoffs for applied MCU rates, exact tracking-consumer cleanup and future output
function scopes. [Worker control](../contracts/acquisition/worker-control.md),
[Setup preparation](../contracts/acquisition/setup-preparation.md) and shared E06/E08
contracts own those bindings; public output formats were not changed by that review.

Admission review checked that ordinary and safety reservations charge retained
commands/evidence in one budget, including terminal results and session cleanup proof.
Lifecycle review checked controller-owned completion barriers and exact producer,
consumer and output closure; source review does not establish delivery or durability.

The simplification pass removes the camera wait gate's never-initialized alternate
control-wait branch and separates trial-report delivery/retention from lifecycle
aggregation. Idle control still waits on the native event; active capture retains
joint SDK waits, control priority and deadline rounding under
[A02/A10](../docs/architecture/acquisition.md#a02). No package, schema, public RPC,
configuration or policy change is needed. Existing shared FFmpeg/bootstrap extraction
and Visual Stimulus naming changes were preserved.

Three concrete runtime defects were corrected alongside the refactor: pulse outcome
validation and shared bootstrap wait validation called `HasField` on protobuf scalars
without presence; Finished delivery compared session work directly with trial work.
Validation now uses the existing UNSPECIFIED/positive-value rules and matches the
current trial, its containing session and exact report work. These are behavior fixes
under [A11](../docs/architecture/acquisition.md#a11) and
[E05/E08](../docs/architecture/system-contracts.md#e08), not equivalence claims.

### Cohesion review

The camera adapter remains the single SDK-facing owner and delegates settings,
features, ROI, transport, metadata, grabs and joint waits. Its size reflects the
required adapter interface rather than combined backend or transport ownership.
The capture-resource owner keeps attachment, reset, seal and release together because
they operate on the same native lifetime; layouts, ring operations and accounting
live in separate modules. The worker executor and RPC service are dispatch and
admission boundaries, with trial stopping, recording completion, preview, health
and reporting extracted into independently constructible components.

The recording session retains one sequencing owner for input, frame-log ordering,
watchdog and durable completion. Frame preparation, process launch, input pumping,
negotiation, synchronization and completion predicates are separate modules. These
are cohesive size exceptions reviewed by responsibility; a line-count threshold
alone neither requires extraction nor exempts later unrelated additions.

The MCU owner sequences one physical serial connection; protocol parsing, byte I/O,
scheduling and async handoff are separate. Trial lifecycle aggregation keeps the
Started/Stopped/Finished evidence join; validation predicates and controller delivery
are separate. `trial_lifecycle.py` is now 494 lines, down from 574.
`trial_delivery.py` receives the session slot, workers, controller port, command ledger
and clock; attempt counts and pending/accepted reports remain on the authoritative
trial record. Output evidence is retained before delivery, with the same three-attempt
limit and original deadline. Acquisition `runtime.py` contains dependency assembly and
thin public delegates; shutdown and authority-loss workflows are extracted. Typed
coordinator records live under `coordinator/state/`; `state.py` is their public export.
These are deliberate cohesive exceptions to size warnings, not permission to add
unrelated responsibilities.

The remaining size warnings concern those unchanged SDK, serial, recording,
capture-resource, dispatch and assembly owners; their existing responsibility-based
exceptions remain bounded as described above. Tests extend the existing behavior
modules, with no new test module. The trial-lifecycle module retains its common exact
worker/session fixtures for aggregation and delivery tests. Portable camera tests
replace only native event allocation; the five Win32 ring cases retain their skips.

The 2026-10-01 cross-backend ARCH-002 audit rechecked the acquisition package layout,
camera/worker/coordinator/recording ownership and the reported size-warning owners.
It found no additional safe shared extraction: camera waits and serial ownership keep
their A02/A10/A11 semantics, while the already-shared pixel and FFmpeg mechanisms
remain in `shared/`. No acquisition code or public interface changed in this audit.

## Dependencies and prerequisites

The `acquisition` extra pins pypylon 26.3.1, NumPy 2.4.4 and pySerial 3.5 from the
rig inventory. These are implementation pins, not a validated deployment lock.
Hardware imports remain lazy. FFmpeg and ffprobe remain externally installed and
resolved through PATH; no tested production FFmpeg baseline is asserted.

Basler API assumptions must be checked against the pinned binding. Missing joint
camera/control wait or GIL support blocks capture preparation under
[capture-wait.md](../contracts/acquisition/capture-wait.md). No polling substitute
or automatic dependency upgrade is permitted. The
[upstream releases](https://github.com/basler/pypylon/releases) document API changes;
they do not establish this rig's compatibility.

Source inspection used the public Windows wheel
`pypylon-26.3.1-cp39-abi3-win_amd64.whl` without installing or executing it. Its
Python wrapper exposes `WaitObjects.WaitForAny`, `WaitObject` handle construction
and `PylonImage.AttachMemoryView`. The matching
[26.03.1 build source](https://github.com/basler/pypylon/blob/26.03.1/setup.py)
enables SWIG thread support. The
[converter typemap](https://github.com/basler/pypylon/blob/26.03.1/src/pylon/pylon.i)
allocates the SDK conversion result internally; the C++ destination overload is
not a Python caller-supplied destination interface. These findings correct draft
binding assumptions; Windows wait results, cancellation and actual conversion
remain unexecuted rig checks.

The joint wait uses the pinned binding's no-index `WaitForAny(timeout)` call and
the existing control-event predicate. This avoids an undocumented Python-to-SWIG
output-pointer conversion while retaining command priority under the
[capture-wait contract](../contracts/acquisition/capture-wait.md).

Basler's [acquisition-stop documentation](https://docs.baslerweb.com/acquisition-start-stop-and-abort)
distinguishes ending acquisition from finishing image readout. Its
[stream-grabber guide](https://docs.baslerweb.com/pylonapi/c/programmingguide)
distinguishes queued buffers from retrieved results. The accepted cutoff/drain
contract therefore requires the prepared delivery bound and terminal stop evidence;
an empty result queue alone cannot establish complete post-cutoff accounting.

The narrow native NVENC capability binding is checked against
[nv-codec-headers n12.2.72.0](https://github.com/FFmpeg/nv-codec-headers/blob/n12.2.72.0/include/ffnvcodec/nvEncodeAPI.h).
Header layout inspection does not prove installed-driver compatibility. Actual
codec, format and dimension support must come from the adopted encoding device,
alongside the installed FFmpeg build's advertised capabilities.

The 2026-09-30 source audit corrected the following implementation findings:

| Finding | Change and governing rule |
| --- | --- |
| Shipped acquisition configuration had unsupported empty `basler` and `recording.tools` sections, causing strict loading to reject it | Removed those obsolete sections. TOML comparison confirms every setting and policy version is unchanged; static comparison now matches the owning allowlist. Existing loader regressions remain prepared for the rig. [E07/E14](../docs/architecture/system-contracts.md#e14) |
| Native NVENC maximum dimensions were collected but never consumed by encoding validation | Require positive device limits for the exact codec/pixel format and check the resolved post-filter width and height before preparation succeeds. Explicit scaling is evaluated; no automatic resize or fallback. [A08](../docs/architecture/acquisition.md#a08) |
| Full FFmpeg help could add another encoder's private option values/ranges, including forced-IDR support | Parse selected-encoder help separately; take only the supported common fields from the `AVCodecContext` section. This follows FFmpeg's [generic/private AVOption distinction](https://ffmpeg.org/ffmpeg.html#AVOptions). [A08](../docs/architecture/acquisition.md#a08) |
| Invalid lookahead text escaped as raw `ValueError`; very large bitrate text could become infinity | Validate individual options before device comparisons, reject nonfinite rates and translate oversized integer conversion failures into `EncodingOptionsError`. Source-layout errors use the same public validation boundary. [A08](../docs/architecture/acquisition.md#a08) |
| GPU discovery lacked a platform guard and malformed UUID/missing driver exports escaped its declared error boundary | Normalize these to `WindowsLaunchError`, retaining exact UUID selection and required RTX 2080 Ti placement. Python documents [Windows DLL loading and missing-symbol failures](https://docs.python.org/3.11/library/ctypes.html#loading-shared-libraries); no driver fallback was added. [SYS-002](../architecture.md#sys-002) |

The same review shortened argument validation into named stages, consolidated
camera/admission predicates, removed four unreferenced protocols and a resource-key
helper, and merged the request accessor into worker ports. No dependency was added.
Static results are retained in [runtime.md](runtime.md#verification-evidence);
these corrections do not establish native or hardware behavior.

Native pipe review uses Microsoft's
[ConnectNamedPipe requirements](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-connectnamedpipe):
an overlapped pipe requires a valid `OVERLAPPED` structure. Cancellation and cleanup
must retain that structure, its event and buffers until completion is observed.

pySerial cancellation is a request to interrupt I/O, not proof that firmware applied
a command or that transmitted bytes stopped. Matched replies, observed completion
and original deadlines remain necessary; see the
[pySerial cancellation API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.cancel_write).

FFmpeg's [stream discovery API](https://www.ffmpeg.org/doxygen/7.1/group__lavf__decoding.html)
reads input packets to establish stream information. The live negotiation review
therefore checks for a potential circular wait if the writer stops feeding after its
first frame while waiting for output initialization. Negotiation must remain bounded
by existing startup/recording deadlines; successful nonempty closure requires matching
input/output facts. This is a source-based review constraint, not a measured startup
latency or a validated installed FFmpeg behavior.

Unknown trigger pins/lines, firmware capabilities, final camera settings and deferred
rig timing stay unset. Firmware implementation/flashing remains outside the authorized scope;
[ARCH-001](../architecture.md#arch-001) owns other backend implementation stages.

## Verification record

The earlier rows below were recorded on 2026-09-30 against an uncommitted working
tree without an exact source revision or full transcript; report consolidation did
not rerun them. The new simplification rows use HEAD
`7ae3767cea92bf7af94153d417e40df997e1fd05` plus pre-existing and new uncommitted changes.
[Raw simplification evidence](acquisition-evidence-2026-09-30/simplification.txt)
records commands, baseline failures, outcomes and source/test SHA256 hashes; HEAD
alone does not identify that snapshot.

| Local check | Result |
| --- | --- |
| Ruff lint / format | Passed; 412 Python files formatted |
| Strict Windows-target mypy | Passed; 370 runtime/test files in the selected scope |
| Compilation | Passed for source, tests, tools and contracts |
| Dependency boundaries | Passed; 268 backend modules, zero violations; cohesive size exceptions reviewed |
| Protobuf / contract syntax | 18 sources generated; 17 TOMLs parsed; all 12 frame-log field groups matched |
| Hardware-free imports | Six provider/entry modules imported without NumPy, pypylon or pySerial |
| Build / package contents | Wheel and sdist built; all 375 packaged Python/stub files match source bytes |
| Earlier behavioral / native / hardware execution | Not executed in that historical static-only review |
| Simplification baseline: `pytest tests/acquisition -q -m 'not windows and not rig'` | 121 passed, 17 failed, five Win32 ring skips. Fifteen failures came from stale fixtures or uncontrolled Windows event allocation; two exposed the invalid protobuf-presence checks. |
| Fixture/presence corrections, then delivery regressions | 149 passed/five skipped, then 165 passed/five skipped; the final aggregation regression brings acquisition coverage to 166 passing cases. No scenario or platform marker was removed. |
| Final integration: acquisition/controller/supervisor/shared/launcher/client, excluding listener tests | 540 passed, five Win32 ring skips. Two authenticated controller RPC tests passed separately with loopback permission: 542 passing cases combined. |
| Current scoped Ruff lint/format and Windows-target mypy | Passed: 204 source/test files formatted; 181 acquisition/shared-bootstrap sources typed, then 204 files including all acquisition tests. Two test-only typing corrections passed the affected 30 cases; refreshed hashes are retained. |
| Current boundary checker and source comparison | 406 backend modules, zero violations. Moved delivery body matches the original AST after normalizing the two intentional scope checks, method name and type assertion; lock, retry, retention and await order remain unchanged. Source/test manifest stayed unchanged through checks. |

Fixture repairs restored the intended scenarios: exact worker UUIDs and startup health
values, serial-owner factory injection, complete fake-clock/ACK budgets, correct method
binding, replay before transport closure, and a started preview with an exact child
operation and explicit viewer-release synchronization. The preview failure found in
the controller pass is resolved. New cases cover missing/nonpositive bootstrap waits,
unspecified pulse outcomes, idle/joint waits, rejected/failed delivery, exhausted retries,
stale work, retained output evidence, finalization and duplicate Finished aggregation.
These local checks do not establish SDK/GIL behavior, ring atomics, device timing or
rig equivalence.

Mypy covered runtime sources, all acquisition tests and the touched integration
fixtures/regressions. An exploratory whole-test-tree check also exposed historical
typing errors in unchanged controller/shared/platform tests; this record does not
claim that the entire historical test tree passes strict mypy. The rig runner's
mandatory mypy step targets runtime sources.

Transfer artifacts recorded at that time: `dist/cephvr-acquisition-20260930.zip`
and its `.sha256`; contents included source, tests, wheel/sdist and static logs in
`verification/`. Their availability/currentness has not been revalidated here.

The supervising review accepted the host implementation for rig verification after
correcting partial-launch ownership, evidence admission before mutation, original
deadline retention, concurrent safety fan-out, encoder negotiation/closure and
manual-preview retirement. Components use explicit state records, ports and callbacks;
feature modules do not hold the coordinator runtime.

## Remaining work and references

Continue native/device/full-workload verification under current E15; the scoped local
passes above do not close rig acceptance. Native
wait/GIL support, conversion precision, firmware/electrical behavior, full-load encoding
and crash durability remain in the [single rig worklist](rig-verification.md).

Background references from the retired design review:
[Stytra](https://pmc.ncbi.nlm.nih.gov/articles/PMC6472806/),
[Basler feature persistence](https://docs.baslerweb.com/knowledge/saving-camera-features-or-user-sets-as-a-file-on-hard-disk),
[pylon persistence API](https://docs.baslerweb.com/pylonapi/cpp/class_pylon_1_1_c_feature_persistence),
[Braid saved-video processing](https://strawlab.github.io/strand-braid/processing-saved-videos.html),
[Unity interpolation](https://docs.unity3d.com/Manual/rigidbody-interpolation.html),
[NVIDIA FFmpeg guide](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html)
and [MP4 muxer source](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c).
These references do not govern CephVR behavior or establish rig compatibility.
