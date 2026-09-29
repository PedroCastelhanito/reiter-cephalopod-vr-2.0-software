# Prepared epoch and transition plan

Authority: [V03](../../docs/architecture/vr.md#v03), [V06](durations.md),
[V07](state-continuity.md) and [V08](../../docs/architecture/vr.md#v08).
[PreparedTrial](artifact_models.py) is the sole prepared-plan representation, including
epochs, transitions and the resource manifest. The [renderer interface](prepared_plan_types.pyi)
accepts that model directly. Under E08's message limit the canonical artifact
([plan.proto](../cephvr/vr/v1/plan.proto) bytes) stays inside VR; ResolvedStimulusPlan
carries only its PreparedHandle (sha256, size, compiler identity) and a compact
planned-occurrence summary for E07's trial log. Every started trial retains the complete
plan in `_stimulus_LOG.json`, independently of Save VR data. This is the recipe itself,
not a second copy alongside a recipe file. Never regenerate a random plan from a seed
as a substitute for retaining the resolved plan. The handle digest/size identify its
exact canonical UTF-8 PreparedTrial JSON bytes; keep those same prepared bytes for writing.
ResolvedStimulusPlan.seed_decimal is copied once from PreparedTrial.seed_decimal.
Each PlannedOccurrence copies index/source epoch, start, duration, scene_id and the
ordered GroupVisit lineage (group, repetition, authored unit and visit index), including
nested groups. Derive these summaries from the same immutable artifact and reject
mismatches/oversized summaries under E08. An empty lineage is valid outside a group.
Local indexes are derived once after validation.
The compiler/runtime remain unimplemented.

## Source, resolution and execution

The authored program remains the only editable source. Setup performs bounded
expansion, resolves the retained seed and duration inputs, validates parameter/writer
compatibility, prepares assets and emits one immutable complete plan. Intermediate
expansion or a valid schedule alone is not Ready. No authored override ambiguity is
resolved by whichever dictionary/record happened to arrive last.

Use the existing configured max_expanded_epochs and max_prepared_plan_bytes from
ResourceLimits. Check recursive expansion counts/products before allocating expanded
lists; stop as soon as a bound is exceeded. Repetition/condition multiplication cannot
create unbounded memory or bypass E07's preparation deadline. Validate structural depth
with a finite parser/implementation limit before recursive traversal; reject excessive
nesting explicitly. Check final table/index/serialized sizes before adopting the plan.

Each expanded epoch has a dense occurrence index and source epoch ID. Its expansion
path retains each group ID, repetition index, authored unit ID and actual visit index,
including condition-row lineage. Repeated copies of an epoch are distinct occurrences;
shuffling changes visit order, never the authored unit identity. Scene/instance IDs
remain stable program-local identities independent of array position. Each CompiledEpoch
contains its resolved settings; runtime lookup indexes are derived after validation.

V08 expands complete child blocks or condition rows according to each group's selected
unit. V06 then samples all random-duration occurrences jointly in that resolved order.
Retain actual ordering and durations plus seed/implementation identities. Reconnect
must reuse them; replay cannot regenerate them from a seed instead of reading evidence.
Ordering implementation/version is bound in [stimulus-schema.md](stimulus-schema.md); the selected duration sampler still needs code, without a replacement method or hidden seed.

An epoch stores inclusive start and exclusive end in integer trial-relative nanoseconds.
The first start is zero; each next start equals the previous end; all durations are
positive and the final end is the resolved trial duration. Check signed-int64 sums and
E05's minimum trial duration. These are software boundaries, not refresh-grid rounding.
Retain fixed, sampled and uniquely constrained duration origins without implying that
coincident random values are invalid. Shared TrialPlan duration must equal this sum.

The complete plan retains source snapshot/content identity, configuration revision,
model/compiler compatibility, prepared/resource generations and complete resolved
settings (including assignments, feedback writers and initial values). The structural
references in the declarations must resolve within that immutable plan; they are not
permission to use arbitrary blobs or runtime plugin lookups. Typed payloads and canonical JSON transport are bound in [stimulus-schema.md](stimulus-schema.md).

## Boundary compilation

Emit one Boundary at every epoch start and one terminal boundary at normal end.
Normal-end transitions deactivate trial instances and hand presentation back to E05/V19
Idle. Interrupted execution stops at the confirmed local cutoff; it never runs remaining
scheduled boundaries to manufacture normal completion. Within a trial, derive each
instance action from actual adjacent active lists and its retained compatibility state:

| Situation | Prepared action |
| --- | --- |
| First appearance in this trial | initialize from that occurrence's prepared initial state |
| Still active, compatible | continue retained live state |
| Leaves the active scene | pause at the logical boundary |
| Returns after absence, compatible | resume and re-anchor at return |
| Explicit authored reset | reset from prepared initial state |
| Incompatible resource/coordinate interpretation | restart_incompatible with the reason visible in the plan |
| Normal end of trial (terminal boundary only) | deactivate exactly the final epoch's instances; no settings or assignments |

Explicit reset takes precedence over compatible continuation/return. A first activation
initializes once even if an authored reset is also present; retain the authored reset in
source lineage without applying initialization twice. Incompatibility requires a restart
regardless of an otherwise compatible-looking instance ID. Prepare the type-specific
compatibility decision and required resources before Ready. The [stimulus compatibility matrix](stimulus-schema.md) determines which state survives changed resources or coordinates.

After advancing old state to the boundary, initialize/reset when required, apply explicit
one-time state assignments, install the new fully resolved parameter/feedback blocks,
then re-anchor and activate the next scene. Pause has no new parameter block. Assignment
blocks are distinct from parameter defaults so omitted phase/pose cannot become a reset.
Transition.next_settings_index indexes the after-epoch's settings; assignment_indices
index assignments in that block. Pause has null next_settings_index and no assignments.
Each instance appears at most once in the boundary operation list. Shared frame state
is evaluated only after the whole boundary has applied, preserving all-view consistency.

Do not precompute numerical values that depend on future feedback or decoder outcomes.
The renderer retains the reached state and direct instance lookup. The prepared plan
stores operations/references, never copies of GPU images or a frame-by-frame future movie.
At a delayed update, process elapsed boundaries in order, preserving the logical state
path, then evaluate the current epoch's local time. V10 records unsubmitted epochs;
executing their logical transitions does not claim that their images were displayed.

## Runtime boundary and readiness

The renderer owns a cursor through immutable boundaries and the current active lists.
The coordinator passes preparation/schedule/release once through the existing lifecycle;
it does not dispatch each epoch or motion update. Select one render-update time, advance
scheduled state, consume eligible feedback under V24/V27 and freeze one state for all views.
No timeline search, JSON parsing, schema validation, resampling, hashing or blocking
media preparation belongs in this update path. Required local bounds/generation/health
checks remain; an unchecked index is not a performance optimization.

Require exact source/revision/resource identities when adopting the complete plan with
its worker PreparedHandle. The plan digest and byte count cover that single encoded artifact. Validate direct indexes, complete
scene/type membership, sorted contiguous times, exactly one terminal boundary and
writer overlap before adoption. A handle or matching duration cannot substitute for
those checks. Retain immutable source/plan through existing E07/E04 metadata/artifact
ownership; [runtime artifact binding](runtime-bindings.md) supplies file ownership and the canonical full schema supplies serialization.

Local syntax/static checks can verify the declared structure. They do not establish
that a compiler, sampler, renderer, decoder or actual-output replay exists or works.
