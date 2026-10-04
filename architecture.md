# CephVR2.0 architecture

Last updated: 2026-10-01

This overview and the linked records in `docs/architecture/` form the authoritative
architecture. Each decision has one home; this register locates it by permanent ID.
Accepted design does not imply implemented or rig-validated behavior.

## Reading and updating decisions

- Read this overview, [system contracts](docs/architecture/system-contracts.md), and
  the relevant backend pages before changing code or architecture.
- **Accepted** records govern implementation; **Deferred** work is outside current
  scope; **Undecided** entries provide no implementation authority.
- Update decisions under [GOV-001](#gov-001): replace the governing rule and update
  this register plus affected contracts/configs. Keep discussion and alternatives in
  the conversation.

## Current position

- Architecture and implementation-contract review is complete for every backend.
  [ARCH-001](#arch-001) selects GUI as the current implementation stage, following
  Tracking implementation/review, with SpikeGLX integration last. Firmware is deferred;
  analysis software is much later. The [acquisition review](reports/acquisition.md)
  records source review and pending rig verification; the [controller/supervisor review](reports/runtime.md)
  retains dated local results and pending E15 rig acceptance. Current Visual Stimulus and tracking
  status is recorded in [Visual Stimulus](reports/visual_stimulus.md) and [tracking](reports/tracking.md).
- Repository packaging and code ownership are accepted under [ARCH-002](#arch-002).
  Package scaffolding and development-tool configuration do not implement a backend.
- Contract indexes: [acquisition](contracts/acquisition/README.md),
  [visual stimulus](contracts/visual_stimulus/README.md), [tracking](contracts/tracking/README.md),
  [SpikeGLX control](contracts/spikeglx-control.md) and the
  [shared contract index](contracts/README.md).
- The decision register below is the authority map; supporting reports keep no
  separate decision history.
- The [2026-09-29 handoff](reports/rig-handoff-2026-09-29/README.md) supplies owner
  assignments, inventory and bounded capability results. Accepted engineering
  defaults still require workload validation; remaining scientific inputs and
  production checks stay in the [rig worklist](reports/rig-verification.md).

## Architecture documents

| Document | Scope |
| --- | --- |
| [System contracts](docs/architecture/system-contracts.md) | Cross-component failure handling, transport, timing evidence, configuration conventions and verification |
| [Experiment](docs/architecture/experiment.md) | Protocols, lifecycle/timing, configuration/preparation, central metadata writer, headless authority and participant modes |
| [Acquisition](docs/architecture/acquisition.md) | Camera workers, frame delivery, encoding, frame log and camera pulse control |
| [Supervisor](docs/architecture/supervisor.md) | Process supervision, emergency reports and shared E04 storage rules (output reservation and central metadata writer are controller-owned); links to supervision contracts |
| [GUI](docs/architecture/gui.md) | Navigation, disconnection, control ownership and GUI recovery |
| [Visual Stimulus](docs/architecture/visual_stimulus.md) | Runtime topology/rendering stack, stimulus scope/program model/storage, recording policy and interfaces |
| [Tracking](docs/architecture/tracking.md) | Complete initial water/fin pipeline declarations and Visual Stimulus result delivery; runtime outstanding |
| [Synchronization](docs/architecture/synchronization.md) | Controller-owned SpikeGLX session control, pulse inventory and external post hoc alignment |

## Decision register

| ID | Subject | Status | Revision |
| --- | --- | --- | ---: |
| [SYS-001](#sys-001) | Computer responsibilities | Accepted | 3 |
| [SYS-002](#sys-002) | GPU workload placement | Accepted | 2 |
| [SYS-003](#sys-003) | Backend language and environment | Accepted | 2 |
| [SYS-004](#sys-004) | Scientific synchronization authority | Accepted | 3 |
| [GOV-001](#gov-001) | Decision workflow and document format | Accepted | 26 |
| [ARCH-001](#arch-001) | Backend process boundaries and build order | Undecided | 18 |
| [ARCH-002](#arch-002) | Repository packaging and code ownership | Accepted | 5 |
| <a id="g01"></a>[G01](docs/architecture/gui.md#g01) | GUI navigation and settings ownership | Accepted | 77 |
| <a id="g02"></a>[G02](docs/architecture/gui.md#g02) | Shared frontend formatting | Accepted | 23 |
| <a id="e01"></a>[E01](docs/architecture/experiment.md#e01) | Protocol progression | Accepted | 13 |
| <a id="e02"></a>[E02](docs/architecture/experiment.md#e02) | Experiment authority and GUI role | Accepted | 11 |
| <a id="e03"></a>[E03](docs/architecture/gui.md#e03) | GUI disconnection and control lease | Accepted | 28 |
| <a id="e04"></a>[E04](docs/architecture/supervisor.md#e04) | Recording layout, identity, and metadata | Accepted | 87 |
| <a id="e05"></a>[E05](docs/architecture/experiment.md#e05) | Lifecycle and trial timing | Accepted | 95 |
| <a id="e06"></a>[E06](docs/architecture/system-contracts.md#e06) | Stop, interruption, timeout, and recovery | Accepted | 76 |
| <a id="e07"></a>[E07](docs/architecture/experiment.md#e07) | Configuration and protocol preparation | Accepted | 57 |
| <a id="e08"></a>[E08](docs/architecture/system-contracts.md#e08) | Processes and control transport | Accepted | 160 |
| <a id="e09"></a>[E09](docs/architecture/synchronization.md#e09) | Current SpikeGLX operation | Accepted | 4 |
| <a id="e10"></a>[E10](docs/architecture/experiment.md#e10) | Modes and required participants | Accepted | 22 |
| <a id="e11"></a>[E11](docs/architecture/experiment.md#e11) | Trial recording interval | Accepted | 17 |
| <a id="e12"></a>[E12](docs/architecture/synchronization.md#e12) | Remote SpikeGLX control | Accepted | 18 |
| <a id="e13"></a>[E13](docs/architecture/visual_stimulus.md#e13) | Save Visual Stimulus data | Accepted | 18 |
| <a id="e14"></a>[E14](docs/architecture/system-contracts.md#e14) | Backend configuration files | Accepted | 206 |
| <a id="e15"></a>[E15](docs/architecture/system-contracts.md#e15) | Contract artifacts and verification | Accepted | 9 |
| <a id="a01"></a>[A01](docs/architecture/acquisition.md#a01) | Camera acquisition and recording ownership | Accepted | 16 |
| <a id="a02"></a>[A02](docs/architecture/acquisition.md#a02) | Acquisition service and camera workers | Accepted | 29 |
| <a id="a03"></a>[A03](docs/architecture/acquisition.md#a03) | Frame transfer between processes | Accepted | 31 |
| <a id="a04"></a>[A04](docs/architecture/acquisition.md#a04) | Frame delivery and consumer overload | Accepted | 20 |
| <a id="a05"></a>[A05](docs/architecture/system-contracts.md#a05) | Acquisition-to-Visual Stimulus delay measurement | Accepted | 6 |
| <a id="a06"></a>[A06](docs/architecture/tracking.md#a06) | Tracking-result delivery to Visual Stimulus | Accepted | 14 |
| <a id="a07"></a>[A07](docs/architecture/acquisition.md#a07) | Recording frame log and crash behavior | Accepted | 57 |
| <a id="a08"></a>[A08](docs/architecture/acquisition.md#a08) | Video encoding and container | Accepted | 48 |
| <a id="a09"></a>[A09](docs/architecture/acquisition.md#a09) | Source-frame identity | Accepted | 12 |
| <a id="a10"></a>[A10](docs/architecture/acquisition.md#a10) | Camera capture lifetime and Basler settings | Accepted | 50 |
| <a id="a11"></a>[A11](docs/architecture/acquisition.md#a11) | Microcontroller command protocol | Accepted | 35 |
| <a id="v01"></a>[V01](docs/architecture/visual_stimulus.md#v01) | Visual Stimulus coordinator and rendering worker | Accepted | 13 |
| <a id="v02"></a>[V02](docs/architecture/visual_stimulus.md#v02) | Structured trial stimulus programs | Accepted | 11 |
| <a id="v03"></a>[V03](docs/architecture/visual_stimulus.md#v03) | Versioned JSON stimulus-program files | Accepted | 9 |
| <a id="v04"></a>[V04](docs/architecture/visual_stimulus.md#v04) | Rendering stack and required stimulus scope | Accepted | 10 |
| <a id="v05"></a>[V05](docs/architecture/visual_stimulus.md#v05) | Declarative parameter animation | Accepted | 6 |
| <a id="v06"></a>[V06](docs/architecture/visual_stimulus.md#v06) | Epoch durations and trial duration | Accepted | 5 |
| <a id="v07"></a>[V07](docs/architecture/visual_stimulus.md#v07) | Stimulus state continuity and trial initialization | Accepted | 5 |
| <a id="v08"></a>[V08](docs/architecture/visual_stimulus.md#v08) | Group ordering and repetition | Accepted | 2 |
| <a id="v09"></a>[V09](docs/architecture/visual_stimulus.md#v09) | Video clip completion | Accepted | 4 |
| <a id="v10"></a>[V10](docs/architecture/visual_stimulus.md#v10) | Clock-preserving playback and nonfatal timing misses | Accepted | 4 |
| <a id="v11"></a>[V11](docs/architecture/visual_stimulus.md#v11) | Bounded video decode-ahead preparation | Accepted | 5 |
| <a id="v12"></a>[V12](docs/architecture/visual_stimulus.md#v12) | Visual Stimulus recording thread and overload | Accepted | 9 |
| <a id="v13"></a>[V13](docs/architecture/visual_stimulus.md#v13) | Trial replay from program and actual render evidence | Accepted | 10 |
| <a id="v14"></a>[V14](docs/architecture/visual_stimulus.md#v14) | Explicit stimulus coordinate spaces | Accepted | 3 |
| <a id="v15"></a>[V15](docs/architecture/visual_stimulus.md#v15) | Four calibrated off-axis surface views | Accepted | 10 |
| <a id="v16"></a>[V16](docs/architecture/visual_stimulus.md#v16) | Explicit simple arena movement boundaries | Accepted | 4 |
| <a id="v17"></a>[V17](docs/architecture/visual_stimulus.md#v17) | Unlit arena appearance | Accepted | 2 |
| <a id="v18"></a>[V18](docs/architecture/visual_stimulus.md#v18) | Externally prepared arena assets | Accepted | 4 |
| <a id="v19"></a>[V19](docs/architecture/visual_stimulus.md#v19) | Uniform Idle background | Accepted | 4 |
| <a id="v20"></a>[V20](docs/architecture/visual_stimulus.md#v20) | Configurable projector presentation pacing | Accepted | 7 |
| <a id="v21"></a>[V21](docs/architecture/visual_stimulus.md#v21) | Output-range clipping with evidence | Accepted | 2 |
| <a id="v22"></a>[V22](docs/architecture/visual_stimulus.md#v22) | Photodiode frame alternation with landmarks | Accepted | 3 |
| <a id="v23"></a>[V23](docs/architecture/visual_stimulus.md#v23) | Explicit photometric calibration mode | Accepted | 3 |
| <a id="v24"></a>[V24](docs/architecture/visual_stimulus.md#v24) | Explicit feedback parameter mappings | Accepted | 7 |
| <a id="v25"></a>[V25](docs/architecture/visual_stimulus.md#v25) | Hold feedback-driven state during invalid input | Accepted | 4 |
| <a id="v26"></a>[V26](docs/architecture/visual_stimulus.md#v26) | Feedback freshness guard with local hold | Accepted | 8 |
| <a id="v27"></a>[V27](docs/architecture/visual_stimulus.md#v27) | Additive motion on retained stimulus state | Accepted | 2 |
| <a id="v28"></a>[V28](docs/architecture/visual_stimulus.md#v28) | Visual Stimulus evidence file and crash behavior | Accepted | 4 |
| <a id="t01"></a>[T01](docs/architecture/tracking.md#t01) | Tracking image representation | Accepted | 3 |
| <a id="t02"></a>[T02](docs/architecture/tracking.md#t02) | Named tracking pipelines with shared stages | Accepted | 4 |
| <a id="t03"></a>[T03](docs/architecture/tracking.md#t03) | One selected tracking camera per session | Accepted | 1 |
| <a id="t04"></a>[T04](docs/architecture/tracking.md#t04) | Water-flow and fin-flow pipeline options | Accepted | 6 |
| <a id="t05"></a>[T05](docs/architecture/tracking.md#t05) | Explicit manual or automatic pose mode | Accepted | 2 |
| <a id="t06"></a>[T06](docs/architecture/tracking.md#t06) | Selectable keypoint-model or threshold/contour pose | Accepted | 5 |
| <a id="t07"></a>[T07](docs/architecture/tracking.md#t07) | NVIDIA Optical Flow with need-driven extensions | Accepted | 7 |
| <a id="t08"></a>[T08](docs/architecture/tracking.md#t08) | One tracking process with internal workers | Accepted | 6 |
| <a id="t09"></a>[T09](docs/architecture/tracking.md#t09) | Independent automatic pose and ordered movement | Accepted | 4 |
| <a id="t10"></a>[T10](docs/architecture/tracking.md#t10) | Shared three-landmark pose | Accepted | 4 |
| <a id="t11"></a>[T11](docs/architecture/tracking.md#t11) | ONNX pose models with ONNX Runtime CUDA | Accepted | 4 |
| <a id="t12"></a>[T12](docs/architecture/tracking.md#t12) | Water-flow locomotion estimator | Accepted | 8 |
| <a id="t13"></a>[T13](docs/architecture/tracking.md#t13) | Fin-wave estimator | Superseded | 5 |
| <a id="t14"></a>[T14](docs/architecture/tracking.md#t14) | Independent tracking-data saving | Accepted | 3 |
| <a id="t15"></a>[T15](docs/architecture/tracking.md#t15) | Compact tracking scientific records | Accepted | 3 |
| <a id="t16"></a>[T16](docs/architecture/tracking.md#t16) | Fixed automatic-pose search rectangle | Accepted | 2 |
| <a id="t17"></a>[T17](docs/architecture/tracking.md#t17) | Highest-scoring eligible pose candidate | Accepted | 2 |
| <a id="t18"></a>[T18](docs/architecture/tracking.md#t18) | Fixed brightness threshold for contour pose | Accepted | 4 |
| <a id="t19"></a>[T19](docs/architecture/tracking.md#t19) | Tracking record file | Accepted | 3 |
| <a id="t20"></a>[T20](docs/architecture/tracking.md#t20) | Four labelled subject-reference points in Configuration | Accepted | 6 |
| <a id="t21"></a>[T21](docs/architecture/tracking.md#t21) | Anatomical mantle-tip landmarks | Accepted | 2 |
| <a id="t22"></a>[T22](docs/architecture/tracking.md#t22) | Pose-derived position, orientation and dimensions | Accepted | 2 |
| <a id="t23"></a>[T23](docs/architecture/tracking.md#t23) | Three-landmark reference ellipse | Accepted | 2 |
| <a id="t24"></a>[T24](docs/architecture/tracking.md#t24) | Analysis-region distances relative to landmark dimensions | Accepted | 5 |
| <a id="t25"></a>[T25](docs/architecture/tracking.md#t25) | Adjustable initial ellipse proportion | Accepted | 2 |
| <a id="t26"></a>[T26](docs/architecture/tracking.md#t26) | Clipped regions with logged coverage | Accepted | 2 |
| <a id="t27"></a>[T27](docs/architecture/tracking.md#t27) | Replaceable tracking-stage implementations | Accepted | 3 |
| <a id="t28"></a>[T28](docs/architecture/tracking.md#t28) | Tapered-superellipse sampling outline | Accepted | 3 |
| <a id="t29"></a>[T29](docs/architecture/tracking.md#t29) | Uniform-distance sampling band | Accepted | 4 |
| <a id="t30"></a>[T30](docs/architecture/tracking.md#t30) | Band scale and ROI dimension meanings | Accepted | 2 |
| <a id="t31"></a>[T31](docs/architecture/tracking.md#t31) | Full-band sampling geometry | Accepted | 5 |
| <a id="t32"></a>[T32](docs/architecture/tracking.md#t32) | Equal-arc outline sections | Accepted | 6 |
| <a id="t33"></a>[T33](docs/architecture/tracking.md#t33) | Full flow samples available to the estimator | Accepted | 3 |
| <a id="t34"></a>[T34](docs/architecture/tracking.md#t34) | Measured flow with separate pose evidence | Accepted | 2 |
| <a id="t35"></a>[T35](docs/architecture/tracking.md#t35) | Relative locomotion-control outputs | Accepted | 3 |
| <a id="t36"></a>[T36](docs/architecture/tracking.md#t36) | Full planar locomotion control | Accepted | 3 |
| <a id="t37"></a>[T37](docs/architecture/tracking.md#t37) | Drive controls virtual speed over source intervals | Accepted | 1 |
| <a id="t38"></a>[T38](docs/architecture/tracking.md#t38) | Direct estimator units through existing Visual Stimulus gains | Accepted | 4 |
| <a id="t39"></a>[T39](docs/architecture/tracking.md#t39) | Dense tracer-water flow for swimming intent | Accepted | 3 |
| <a id="t40"></a>[T40](docs/architecture/tracking.md#t40) | Flow-transport and turning proxy | Accepted | 2 |
| <a id="t41"></a>[T41](docs/architecture/tracking.md#t41) | Local flow-consistency screening | Accepted | 3 |
| <a id="t42"></a>[T42](docs/architecture/tracking.md#t42) | Linear area-weighted water-flow response | Accepted | 1 |
| <a id="t43"></a>[T43](docs/architecture/tracking.md#t43) | Turning rate centred on accepted support | Accepted | 3 |
| <a id="t44"></a>[T44](docs/architecture/tracking.md#t44) | Reliable flow coverage in every section | Accepted | 2 |
| <a id="t45"></a>[T45](docs/architecture/tracking.md#t45) | Source-time exponential command smoothing | Accepted | 3 |
| <a id="t46"></a>[T46](docs/architecture/tracking.md#t46) | Fin-edge profiles and NVIDIA fin flow | Superseded | 3 |
| <a id="t47"></a>[T47](docs/architecture/tracking.md#t47) | Local cross-correlation of fin-motion histories | Superseded | 2 |
| <a id="t48"></a>[T48](docs/architecture/tracking.md#t48) | One fin-motion method per session | Superseded | 2 |
| <a id="t49"></a>[T49](docs/architecture/tracking.md#t49) | Signed lateral fin-flow feature | Superseded | 2 |
| <a id="t50"></a>[T50](docs/architecture/tracking.md#t50) | Geometry-derived fin-analysis regions | Superseded | 2 |
| <a id="t51"></a>[T51](docs/architecture/tracking.md#t51) | Retained local fin-wave estimates | Superseded | 2 |

## System decisions

<a id="sys-001"></a>
### SYS-001 — Computer responsibilities

**Status:** Accepted · **Revision:** 3

- The main computer acquires and records camera streams, processes tracking, and
  renders Visual Stimulus/projection.
- A separate computer runs SpikeGLX and records electrophysiology and incoming
  synchronization pulses.
- Camera frames do not pass through the SpikeGLX computer.

<a id="sys-002"></a>
### SYS-002 — GPU workload placement

**Status:** Accepted · **Revision:** 2

- Use the RTX 5060 Ti for visual-stimulus rendering, all projector outputs and
  tracking GPU work (NVIDIA Optical Flow and ONNX CUDA inference). T08's CPU
  preparation/geometry/estimation and normal CPU control work retain their owners.
- Use the RTX 2080 Ti NVENC engines for all recorded video: both cameras and the
  Visual Stimulus review composite. Keep rendering/readback on the RTX 5060 Ti and the existing
  host-buffer/raw-stdin recording paths; no GPU-to-GPU sharing is assumed.
- Use the Ryzen 9 9950X's integrated AMD Radeon graphics for the main operator
  display and GUI graphics. GUI application logic continues on the CPU.
- Resolve physical adapters explicitly across Windows/OpenGL, CUDA and FFmpeg;
  never assume their ordinal numbers match or silently move a workload to another
  adapter. Missing/incompatible required placement blocks the affected preparation;
  runtime failures retain E06's scope and outcomes.
- The shared fixed declaration lives in `contracts/policy/experiment_policy.toml`.
  Validate actual context/provider/encoder placement, cross-adapter transfer cost
  and the complete simultaneous workload before making performance claims. The
  rig verification report owns current device health and measured encoding results.

<a id="sys-003"></a>
### SYS-003 — Backend language and environment

**Status:** Accepted · **Revision:** 2

- Implement the controller and supervisor in Python.
- Prefer Python for every CephVR backend.
- CephVR2.0 uses its own fresh Python 3.11 environment, separate from the existing
  CephVR environment. Resolve and verify dependencies independently; do not clone
  the old environment or inherit its package/PATH choices as a validated baseline.
- Python backends may call compiled libraries, device SDKs, codecs, shaders,
  firmware, and GPU code.
- A non-Python component requires a documented SDK limitation or measured failure
  to meet its backend's requirements. Keep such a component behind a Python
  interface where practical.

<a id="sys-004"></a>
### SYS-004 — Scientific synchronization authority

**Status:** Accepted · **Revision:** 3

- Hardware pulses recorded by SpikeGLX are authoritative for posthoc scientific
  alignment of camera, trial-start, and other selected events.
- CephVR's scheduled host-monotonic time remains the software trial boundary; a
  SpikeGLX pulse does not rebase that boundary.
- Preserve device-clock timestamps, frame/event counters, and host-observation
  times as diagnostic and pulse-matching evidence. Camera timestamps are converted
  to nanoseconds under A07 while retaining their separate device-clock origin.
- Do not require a device-to-host offset or affine calibration for pulse-covered
  events. A future fallback mapping must be explicitly specified and validated.
- SpikeGLX command acknowledgements, running/saving queries and exchanged session
  timestamps are control evidence only. They do not establish that any particular
  hardware pulse was recorded or calibrate the clocks between computers.
  Scientific pulse matching remains external post hoc under E09/E12.

<a id="gov-001"></a>
### GOV-001 — Decision workflow and document format

**Status:** Accepted · **Revision:** 26

- All backend architecture and implementation contracts have been reviewed against
  the owner's intended behavior. Runtime implementation requires explicit owner
  authorization; the authorized stage is recorded in ARCH-001. Accepted designs,
  completed contracts and requests to continue alone do not authorize another
  coding stage. All behavior still needs rig verification (E15); decisions remain
  open to optimization against implementation and rig evidence.
- Preserve existing declarative schemas/interfaces and contract checks; they are
  design artifacts and do not establish a working or validated backend.
- Prefer the simplest design that meets the agreed requirements. Review simpler
  alternatives before proposing additional states, fields, processes or coordination;
  tie added complexity to a concrete requirement. Offer the simpler viable approach
  explicitly and recommend it when it meets the same requirements.
- Complete each backend's architecture and implementation contracts before declaring
  its stage complete. For acquisition this includes schemas, internal interfaces,
  device mappings and execution/recording mechanisms; high-level agreement is not
  completion.
- Do not label local contract work rig-deferred. Rig checks retain E15's deferral
  until access is available; hardware facts remain unknown until supplied.
  Implementation order and its remaining choices belong to [ARCH-001](#arch-001).
- Apply accepted shared rules to each backend by default, without asking again.
  Reuse compatible contracts/helpers and reference their owning decisions. A rule
  specific to another backend is not automatically shared. Raise an exception only
  for a concrete conflict with the backend's required behavior; identify the rule,
  conflict and smallest necessary change, and continue unaffected work.
- Use the same decision depth across backends. Ask only about critical unresolved
  behavior, scope, ownership or guarantees affecting experiment correctness, data
  integrity or failure response. Resolve routine fields, schemas/RPCs and
  implementation mechanics under accepted rules autonomously, without another
  approval round.
- Keep encoding tuning values in per-camera FFmpeg arguments with concise comments.
  Architecture owns configuration/validation guarantees, not separate decisions for
  each codec parameter; do not turn ordinary tuning into architecture questionnaires.
- Present genuine critical choices in pairs, with options/recommendations; explain
  complex choices individually. Do not invent minor choices to fill a pair. When none
  remain for the current work, continue contract formalization autonomously.
- Record accepted choices and proceed with the next critical pair or authorized
  routine work. Partial answers accept only the specified choices; unanswered
  critical recommendations remain unresolved.
- Keep one concise current description per decision: owner, selected behavior,
  limits and failure response. Use short bullets or compact tables; no option
  history, repeated rationale, copied config-key inventories or repeated safeguards.
- Reference shared lifecycle/failure rules instead of repeating them per backend.
  Put wire fields, numeric schema layouts and implementation details in contracts.
  Operator TOMLs hold only changeable settings and their defaults; fixed policy
  declarations go in the versioned `contracts/policy/<backend>_policy.toml` (E14).
- Amendments replace the relevant bullet. Add a new decision only for a real
  behavior/ownership tradeoff. Before saving, remove duplication and check dependent
  configs/contracts. Development reports link to current decisions: maintain one
  current report per backend area (`reports/runtime.md`, `acquisition.md`, `visual_stimulus.md`,
  `tracking.md`), updated in place with scope, unresolved findings and dated validation
  evidence/limits. Keep outstanding rig checks and execution instructions only in
  `reports/rig-verification.md`; retain raw evidence and its assessment in dated
  bundles. Preserve result provenance and unresolved findings when consolidating;
  Git retains review history. Do not create per-review reports or duplicate policy.
  E04 runtime emergency/recovery reports retain their separate role.
- Root `TODO.md` indexes open tasks by status and affected backend; root `LOG.md`
  records brief dated actions, findings, code/report changes and verification limits.
  Contributors and agents keep them current as they work. Link authoritative
  decisions, current backend reports and the single rig checklist rather than
  copying them; task entries do not authorize new scope or close deferred acceptance.
- Keep the overview and global decision register in root `architecture.md`; store
  backend records in `docs/architecture/<backend>.md` and cross-component rules in
  `docs/architecture/system-contracts.md`. Use one authoritative home per decision;
  backend pages link to common rules instead of copying them. Worker processes stay
  with their owning backend. Document boundaries do not select process boundaries.
- Amend the owning record and root register together. Preserve permanent IDs and
  keep only the current rule. Increment the revision when a rule changes; moving an
  unchanged record preserves its revision.
- Keep design status separate from implementation and validation status.
- Design acquisition from requirements and rules. Do not use the existing camera
  implementation as a constraint or the basis for design findings unless the owner
  requests it; that implementation is intended to be rebuilt.

<a id="arch-001"></a>
### ARCH-001 — Backend process boundaries and build order

**Status:** Undecided · **Revision:** 18

- The owner has authorized GUI implementation following Tracking implementation
  and review. GUI is the current stage, beginning with reference review and operator
  workflow/layout design. Existing controller, supervisor, acquisition host, Visual
  Stimulus and Tracking work remains in scope for required integration and shared helpers.
- SpikeGLX integration comes last in this sequence, after Tracking and GUI.
  Acquisition firmware/flashing is deferred to a later stage. Analysis software,
  including V13 offline replay/export, is deferred much later; the experiment
  backend must continue recording the inputs that analysis requires.
- Code organization follows [ARCH-002](#arch-002). Local implementation/communication
  checks follow E15; Windows-native, scientific and full-workload acceptance remains
  rig work. Unavailable implementations never imply readiness or rig validation.
- The complete process split remains undecided. Selected process structure so far:
  - E08: separate controller, supervisor and GUI processes.
  - A02: acquisition coordinator and one camera worker process per camera (capture
    and recording threads), with encoding in an FFmpeg subprocess.
  - [V01](docs/architecture/visual_stimulus.md#v01): Visual Stimulus coordinator and separate rendering worker;
    [V12](docs/architecture/visual_stimulus.md#v12) adds a recording thread and FFmpeg subprocess
    inside the renderer when saving is enabled.
  - E12: no added process; the controller calls SpikeGLX directly. No separate
    alignment process is selected.
  - [T08](docs/architecture/tracking.md#t08): one tracking process with internal
    computation threads; no additional tracking coordinator/stage process.
- Other unresolved backend names identify logical responsibilities and configuration
  ownership without a selected process layout. One logical backend may contain
  several worker processes.
- GOV-001 owns decision review; the implementation sequence above is owner-selected.

<a id="arch-002"></a>
### ARCH-002 — Repository packaging and code ownership

**Status:** Accepted · **Revision:** 5

- Maintain one installable Python project, `cephvr`, with importable code under
  `src/cephvr/` and packaging/dependency/tool settings in root `pyproject.toml`.
  SYS-003 owns the Python environment; packaging does not merge E08's processes
  or remove component compatibility checks.
- Group runtime code by owner: `controller/`, `supervisor/`, `launcher/`, `client/`
  and later backend packages. Keep behavior and RPC handlers with their owner;
  E07's backend configuration modules remain lightweight and safe to import.
  Avoid large handwritten source files whenever their responsibilities can be
  separated into cohesive modules. Keep modules focused, with explicit interfaces
  and dependencies, so code is easy to maintain, test independently and change.
  Before extending an oversized file, extract separable responsibilities into
  owning modules while preserving state ownership and accepted behavior. Apply
  these rules to existing code and new contributions, including agent-written code.
- Runtime coordinators assemble components and supervise their tasks. Feature
  modules receive focused typed state records, peer interfaces and explicit
  operations; they must not depend on the whole runtime or import entry points or
  RPC adapters. Keep one authoritative copy of state and preserve lock scopes,
  deadlines and durable-write order during extraction. RPC adapters own transport
  authentication/admission and call explicit application operations. Review rejects
  whole-runtime back-references and separable responsibilities left in large files.
- Before each coding increment, review the affected code for oversized mixed
  responsibilities, duplication, unused behavior and unnecessary abstractions;
  simplify concrete problems before extending them. Prefer the standard library,
  existing dependencies, or a maintained package when it removes meaningful custom
  complexity while preserving accepted behavior, bounds and failure guarantees.
  Assess dependency/platform costs; do not add packages or split files merely to
  reduce line counts. Keep required safety mechanisms and distinguish refactoring
  checks from pending runtime/rig verification.
- Put E08's reusable in-process mechanisms in `shared/` and Windows mechanisms in
  `platform/windows/`. Shared code retains no cross-process authoritative state;
  backend policy and orchestration remain with their owners. Imports must not
  launch processes, initialize devices or load unrelated heavy runtimes.
- Keep versioned source contracts in `contracts/`. Generate Protobuf/gRPC Python
  bindings under the matching `src/cephvr/<component>/v1/` paths; never hand-edit
  generated bindings. Existing declarative Python models remain design artifacts
  until explicitly integrated, with one authoritative model per schema.
- Keep operator settings and fixed policies in their E14 homes. Existing docs and
  reports retain their roles; source packages do not introduce another decision
  register or change E04's data/report locations.
- Keep runtime tests in `tests/<owner>/`, grouped by stable behavior or contract.
  Extend the relevant existing module by default; create a module only for a
  distinct responsibility or materially different fixture/platform requirements.
  Do not create files per fix, review round or implementation file, or merge
  unrelated tests to meet a file-count target. Keep helpers local; share genuinely
  reused setup in the owner's support module or narrowly scoped `conftest.py`,
  never by importing another test module. Parameterize cases that differ only in
  inputs and expected results; retain readable scenario tests for distinct flows.
  Consolidation must preserve scenarios, assertions, markers and fixture isolation;
  review rejects redundant cases and unjustified file proliferation. Keep developer
  commands in `tools/` and existing contract checks separate. E15 still governs
  behavioral and rig verification; collection and static checks prove neither.
- Enforce UTF-8, LF, four-space Python indentation, an 88-character formatting
  target, Ruff formatting/linting and static type checking through the repository
  tool configuration. Use type annotations and concise behavioral docstrings;
  exclude generated code from handwritten-code checks. Packaging, lint or type
  errors fail their checks rather than being silently bypassed.
