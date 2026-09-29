# VR duration resolution contract

Governing policy: [V06](../../docs/architecture/vr.md#v06). Source/plan ownership is
[V03](../../docs/architecture/vr.md#v03); Setup, seed retention and logging are
[E07](../../docs/architecture/experiment.md#e07). This is a local implementation
contract, not runtime code or a complete stimulus-program/wire schema.

## Inputs and output

The resolver consumes the expanded epoch occurrence list, duration mode, resolved
trial seed and (for target-total mode) the requested trial total and one common
minimum/maximum range for random occurrences. Each occurrence has an unambiguous
identity including its repetition path and is either fixed-duration or random.
Group ordering is supplied by the program expander under
[V08](../../docs/architecture/vr.md#v08); this contract consumes that resolved order.
Do not automatically create epochs or infer a repetition count from the target.

Use positive integer nanoseconds for resolved durations and cumulative boundaries,
consistent with shared control timing. Parse authored seconds as decimal values,
without first converting through binary floating point. Fixed durations, target
and range endpoints must be exactly representable in whole nanoseconds; otherwise
return a field-specific precision error. This is storage precision, not a claimed
physical display resolution. Reject sums outside the positive signed-int64 range.

The output contains the occurrence-to-duration mapping, cumulative start/end offsets,
trial total and sampler identity. The full prepared program retains the seed and
these values in E07's planned-epoch evidence. Scientific presentation records remain
separate. Do not store only a seed and expect later regeneration to replace evidence.

## Resolution

For explicit mode, every occurrence has a fixed duration; calculate the checked
integer sum. For target-total mode, let:

- `F` be the sum of fixed occurrence durations;
- `N` be the number of random occurrences after expanding repetitions;
- `L`, `U` be the shared positive integer lower and upper bounds;
- `R = target_ns - F` be the remaining duration.

Require `L <= U` and `N*L <= R <= N*U`. With `N = 0`, require `R = 0`.
With `N = 1`, its duration is exactly `R`. With `L = U`, or the residual exactly
at either feasible extreme, return the uniquely determined vector and expose that
no duration variability is possible. Validate E05's minimum trial duration as well.
Return feasible total bounds and responsible input paths on rejection.

For a nondegenerate random case, sample uniformly from
`{d: L <= d[i] <= U, sum(d) = R}` with respect to its `(N-1)`-dimensional volume.
Use a Python implementation of Stafford's fixed-sum simplex-volume method; it
supports a shared interval and selects feasible combinations without rejection
sampling. Mathematical references: [author's algorithm description](https://www.mathworks.com/matlabcentral/fileexchange/9700-random-vectors-with-fixed-sum)
and [Emberson, Stafford and Davis](https://www.cs.york.ac.uk/rts/static/papers/R:Emberson:2010a.pdf).
This selects a mathematical method, not a MATLAB runtime dependency or permission
to copy third-party source without applicable terms.

Sample all random occurrence durations together. Each repeated occurrence is a
separate coordinate, not a reused template value or an independent draw followed
by scaling. Assign the exchangeable sampled coordinates to random occurrences in
the expander's stable order. Never sort durations by length before assignment;
coincident values are valid and must not trigger retries. Fixed occurrences are
excluded from sampling and retain their positions/durations.

Do not substitute independent draws plus scaling/clipping, a final-epoch residual,
sequential uniform feasible draws, rejection-until-success or a finite-step Markov
chain. Those do not implement the selected distribution/algorithm contract.

## Quantization and numeric failure

The statistical target is continuous. The stored schedule is its nanosecond
quantization, not an exactly uniform distribution over integer compositions.
For sampled values in nanoseconds, take each floor, then allocate the remaining
integer nanoseconds to eligible coordinates with largest fractional remainders;
break equal-remainder ties with the private duration RNG. An increment cannot
cross `U`. Each final duration must be a floor or ceiling of its sampled value,
within `[L,U]`, and the integer sum must equal `R` exactly.

Use sufficient arithmetic precision to meet those checks. If numerical error means
no such floor/ceiling allocation is possible, fail Setup with a numeric diagnostic;
do not silently clamp, rescale, redraw, or push a larger correction into one epoch.
Sampler numeric precision/evaluation order is part of its versioned implementation.
The rounding bound is less than one nanosecond per coordinate relative to a valid
continuous sample. It does not establish when a projector actually changes frames.
Construct all epoch boundaries with integer prefix sums, never repeated float sums.

## Shared control binding

`TrialDefinition` is authored configuration and contains no independent duration.
The reserved old field/name must not be reused or restored by a GUI, saved-history
loader or a headless edit. Legacy documents containing it require an explicit schema
migration/diagnostic, never a second authoritative duration.

VR returns each prepared occurrence plan and `TrialPlan.resolved_duration_ns` in its
resolved-plan/Ready evidence, scoped to the exact configuration revision and trial.
The value equals the sum of its quantized epoch durations. The controller checks
presence, signed-int64 representability and E05's minimum 60 seconds, then retains
and distributes this common plan to participating backends. Other backends echo or
validate it; they do not independently author or substitute the duration. Configuration
changes invalidate the corresponding plan/readiness under E07.

Before acknowledging ScheduleTrial, each backend checks the command context, retained
prepared plan and checked arithmetic: `normal_end - start == resolved_duration_ns`.
VR additionally checks its resolved epoch sum. Reject missing, stale, overflowing or
mismatched evidence; do not shift T, trim epochs or silently extend recording. Release
must match the retained schedule exactly. The existing shared schedule/E11 ownership
is unchanged. This binds schemas; it is not an implemented runtime validator.

## Seed stream and versioning

Use a private duration RNG, independent of stimulus ordering and other random
parameters. Seed a local Python `random.Random` instance with the nonnegative integer
formed from the big-endian SHA-256 digest of UTF-8
`cephvr.duration.v1:` followed by the canonical decimal resolved trial seed (no
leading zeros, except `0`). Do not incorporate session IDs, process IDs, wall time
or Python's randomized `hash()` into derivation. Use its `random()` stream; specify
any index/permutation selection in the sampler implementation rather than relying
on an unversioned library shuffle. See [Python's RNG documentation](https://docs.python.org/3/library/random.html).

Use sampler ID `stafford_continuous_ns_v1`. The ID covers the numerical method,
random-number consumption order, occurrence assignment and quantization rules.
Pin the numerical implementation and retain its version with the prepared plan;
a sequence-affecting change requires a new sampler version. Reproduce the same
schedule for the same expanded duration inputs, seed and sampler implementation.
Golden vectors must establish reproducibility for supported implementation builds;
no cross-platform result has been verified yet.

Resolve once per Setup and retain the result. Reconnect or a repeated control
request never resamples it. Fresh Setup with unchanged inputs/seed/version reproduces
it; getting a different randomized schedule requires an explicit seed change under
E07. Different epochs may receive equal values; different seeds do not guarantee
different vectors, especially in degenerate or quantized cases.

## Implementation and verification

Implementation checks must cover fixed/mixed schedules, repeated occurrences,
empty random sets, one-coordinate and boundary cases, infeasible inputs, overflow,
precision rejection, exact integer sums/bounds, and stable golden vectors. Check
quantization separately using fractional and tied-remainder cases. Validate sampling
against analytically tractable small-dimensional cases and permutation symmetry;
bounds/sum checks alone do not prove a uniform distribution.

The contract is declared; no sampler implementation or distribution/reproducibility
verification has been performed. [Program/schema/compiler interfaces](stimulus-schema.md), [private wire types](../cephvr/vr/v1/plan.proto)
and [presentation evidence](evidence-format.md) are now declared. Implement their providers
and the selected sampler; no additional random-parameter policy is implied. Rig timing stays deferred under E15; this
local mathematical contract is not a hardware feasibility result.
