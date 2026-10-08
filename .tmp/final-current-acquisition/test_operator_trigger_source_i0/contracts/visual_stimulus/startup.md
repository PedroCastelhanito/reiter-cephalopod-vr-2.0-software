# Visual Stimulus startup Idle and output initialization

Authority: [V19](../../docs/architecture/visual_stimulus.md#v19), configuration [E07](../../docs/architecture/experiment.md#e07)
and process/failure [E06/E08](../../docs/architecture/system-contracts.md). This contract
binds the accepted startup behavior; it does not implement output initialization.

## Configuration and ownership

Start the registered Visual Stimulus coordinator and renderer without opening stimulus windows.
After the controller adopts the initial saved configuration through E07's existing
GUI/headless path, it requests one startup display initialization against that exact
controller/backend generation and configuration revision. A backend never loads a
competing copy of last_configuration.json or substitutes the rollback snapshot itself.
Use E07's existing history/default precedence and explicit saved-value rules; defaults
still cannot supply unselected output assignments, Idle brightness or calibration mode.

The controller runs the lightweight display-settings validators; the renderer owns
capability/resource checks and window/context creation through its normal display
preparation code. Check all configured required output identities, mappings, dimensions,
geometry, Idle values/units, requested pacing and explicit photometric mode/profiles.
V23's calibrated mode requires every necessary compatible profile; uncalibrated mode
must be explicitly selected. Prepare the same color/clipping/correction path used for
session Idle. File validity is not proof of current optical calibration or VSync.

Only display/Idle dependencies are required at this stage. Do not load images/videos/
arenas from trial programs, expand epochs, generate seeds, prepare camera/tracking,
reserve trial files, start recording-only threads or create session metadata. A
missing trial program cannot prevent an otherwise valid display-only initialization.
Full session validation/preparation still belongs to explicit Setup.

## Admission, evidence and failure

Use existing E08 command identity, retained admission/result and generation/revision
checks. The controller dispatches only after its initial configuration is available;
concurrent process startup does not give the backend authority to guess configuration.
Initialization runs outside control/health threads, with the existing E06 Setup
initial budget and shared recovery budget applied to this bounded preparation operation, not a new
independent timeout/retry policy. It does not enter session SettingUp or allocate a
session/trial identity. Missing configuration produces an actionable field issue
without waiting out a resource-preparation deadline.

Prepare resources before exposing windows where the platform permits. Confirm
configured Idle only after every required output has successfully submitted its
background using the normal presentation evidence. This is software evidence, not
simultaneous optical onset. Report exact applied configuration revision, renderer
identity, output IDs and per-output success/failure/unknown observations. Registration
or a heartbeat alone cannot mark outputs initialized, and one output's success cannot
satisfy the entire set. No new session Ready/Started report is generated.

Missing/invalid startup settings leave outputs uninitialized; the application stays
available for configuration with the same actionable issues in GUI and headless
views. Do not open arbitrary screens, invent black output, skip a required projector
or silently switch calibration mode. Uninitialized means CephVR has no confirmed
control of the output image; it does not mean the projector is dark.

A failure after partial resource creation invokes normal idempotent release of that
attempt's windows, contexts and related resources. Keep per-output evidence truthful
while cleanup is pending; there is no atomic multi-projector presentation guarantee.
Retain cleanup blockers if release is unconfirmed. Configuration errors are distinct
from confirmed process/GPU/device failures, which retain E06/E08 handling. No automatic
process restart, weakened failure policy or assumed resource release is introduced.

Before accepting completion, compare generations and revision with the current
request. Obsolete work cannot change readiness or validate a newer configuration;
retire its resources through the same cleanup path. Shutdown cancels initialization
and uses normal tracked process/resource obligations.

## Configuration edits and Setup handoff

Do not automatically apply ordinary edits or validation rollback to live outputs.
Once initialized, retain the last successfully applied Idle configuration until
fresh Setup changes it; status distinguishes that applied revision from pending
controller edits. After incomplete/failed startup, correct settings through normal
configuration and retry display preparation as part of explicit Setup. No new retry
button/RPC or repeated background attempt is required. Unsafe prior cleanup blocks
Setup under E06 even though configuration editing remains available.

Setup revalidates current display settings and actual output/capability/profile
bindings. Reuse existing renderer resources only when they match the newly prepared
configuration; otherwise release/replace through the same renderer-owned path.
Startup success is never evidence that the full session is Ready. Missing assets,
worker preparation, recording requirements and other E05/E07 gates remain mandatory.
If Setup fails, retain a prior Idle presentation only while its resources and validity
are still confirmed; otherwise expose uninitialized/failed output and cleanup state.
Do not claim rollback restored physical output or apply a fallback configuration.

After successful Setup, keep V19 Idle before/between/after trials under the accepted
lifecycle; Start locks effective session settings. Trial onset/cutoff and photodiode
execution remain trial-scoped. Starting the application or initializing Idle cannot
start/resume a session or advance trial stimulus state.

## Remaining bindings and verification

The [worker/control binding](worker-control.md) now declares the initial display
request/result, applied-output controller view, canonical display model and generated
schema. Existing lifecycle fields are not repurposed as session Ready. Concrete
window/context resource implementations and imported geometric-profile contents
remain local work; a valid display document does not certify asset/device readiness.
The [shared launch contract](../windows-launch.md) owns Windows containment; do not
copy its mechanism here. [Rig verification](../../reports/rig-verification.md) covers
actual display initialization, failure cleanup and optics later. No runtime or rig
behavior is verified by these declarations.
