# Complete epoch settings and named conditions

Authority: [V02](../../docs/architecture/visual_stimulus.md#v02), structure/versioning
[V03](program-validation.md), continuity [V07](state-continuity.md), and ordering
[V08](../../docs/architecture/visual_stimulus.md#v08). This binds source-model semantics selected
by the owner. The [canonical model and vocabulary](stimulus-schema.md) now supply its typed source declaration.
The [prepared plan](prepared-plan.md) owns the derived execution representation.
[ProgramSource](../cephvr/visual_stimulus/v1/plan.proto) transports the complete canonical JSON,
with a descriptive source reference; execution never reloads that editable reference.
The existing VisualStimulusTrialSettings now carries this source and an optional retained seed.

## One complete settings block per active instance

Each authored epoch supplies a complete typed settings block for every instance in
its selected scene, including instances currently covered or at zero opacity. Reject
missing, duplicate, unknown or inactive-instance blocks. Match the block's stimulus
family to the referenced instance. Blank/background-only scenes require no instance
blocks. Scene layer order and arena slot remain owned by scene-composition.md.

Instances have stable IDs and type identity. Assets and immutable definitions may be
shared by reference. Sharing an asset does not share mutable state, and does not create
an implicit settings base. Each epoch explicitly supplies every applicable setting:
resource selection, coordinate interpretation, appearance, programmed motion and
feedback definitions, plus its type's initializer/reset inputs. The full family schemas
must enumerate those requirements; arbitrary parameter dictionaries are not a substitute.
Tagged alternatives require only fields of the chosen variant, not meaningless fields
for every possible stimulus type. Explicit no-motion/no-feedback values are permitted.

No epoch settings inherit from the previous epoch, a prior condition row, scene defaults
or an instance's base settings. Absence of a required field is an error, not an instruction
to carry its old value. V02 supersedes using runtime defaults to complete an authored
epoch: the editor may materialize an accepted backend default while creating a block,
but the stored block must be complete. For example, the accepted hold-final-frame video
default can initialize a new video's explicit end_behavior field; loading an incomplete
program cannot silently repair it. Persisted explicit zero/false remains explicit.

A GUI may provide Duplicate epoch, copy settings and bulk editing to reduce typing, but
must store the resulting complete blocks. Do not introduce hidden patches, template
inheritance or a second saved timing/program format as a shortcut. Repetition reuses its
authored body; there is no requirement to duplicate every expanded occurrence in the
source file. Condition references are explicit settings expressions, not missing values.

## Complete settings do not reset live state

Keep initialization/reset inputs separate from continuous settings and one-time state
assignments. Merely repeating an initial phase/pose in a complete block does not write
that value at every boundary. It is consumed only when the instance initializes,
explicitly resets or restarts after incompatibility under V07. An explicit one-time
state assignment remains visibly separate and overrides its declared field once.

For example, consecutive complete texture blocks specify drift rates 0.2, 0 and 0.2
cycles/s. With the same instance and compatible resource/coordinates, the middle epoch
holds the reached phase, and the last resumes from it. Each block also specifies all
other settings; none of them is borrowed from whichever epoch happened to run before.
Feedback increments/bias must also be stopped for a fully static hold under V27.

Selecting a new row or shuffling an epoch cannot silently change its settings through
inheritance. Reordering can still intentionally change its reached phase/pose because
state continuity follows actual execution order. The editor must distinguish resolved
settings from live-state-dependent outcomes rather than promise identical images merely
because the parameter block is complete.

## Named condition inputs

A condition table belongs to one group and declares named, typed columns with units
where applicable. Rows have stable row IDs and one explicit value for every declared
column. Reject duplicate IDs/columns/cells, missing/extra cells, incompatible types,
nonfinite numeric values and unsupported units. No Cartesian product is implied; each
authored row is one selected combination under V08. Nested groups retain their own tables.

A stimulus setting refers explicitly to a column in the current row of a named enclosing
group. The structural reference carries group_id and column_id; it is not a Python/string
expression evaluated at runtime. The GUI may display it as condition.speed. A nested
group can explicitly reference an enclosing row; qualification avoids shadowing or
nearest-name guessing. References to a sibling, descendant or table with no active row
are invalid. Same-named columns in different groups are distinct typed references.

Use one literal-or-condition-reference alternative at the declared setting/constant
input position. A row supplies values to those named positions only; it is not a patch
that overrides arbitrary instance fields. No row-versus-epoch priority rule or dynamic
lookup graph is needed. References inside function coefficients use the same substitution;
V05 still owns the resulting epoch-relative function clock. Reject a reference whose
column type/unit is incompatible with its destination before rendering. A complete
block may use literals for some fields and named references for others.

Resolve selected rows during bounded group expansion at Setup. Validate every reachable
row/epoch pairing and its resulting complete settings, including values inside ranges,
function definitions, asset selections and writer compatibility. Do not validate only
the first row and trust others. Retain selected row identity and actual resolved values
in the occurrence plan. No table lookup, string evaluation or input substitution runs
per frame. Changes require fresh validation/Setup; reconnect never changes a selected row.

Duration authoring remains V06's fixed epochs or jointly sampled target-total mode;
condition support does not silently add a third duration policy or replace its sampler.
Only positions explicitly permitted by the final typed source model accept references.
Randomized row order and random epoch durations remain independent resolved streams.

## Source-to-plan checks and completion boundary

The canonical model must check stable references, complete epoch blocks, exact active
instance sets, condition scope/types, and the distinction between settings and state
assignments. It must also apply V27 writer/alias checks after substitution. Use common
validators for GUI/headless and Setup, with actionable source paths for both a row cell
and its receiving setting. Reject ambiguous/incomplete source before Ready.

The [canonical model/generated schema and family vocabulary](stimulus-schema.md) now
bind source types, coordinates and compatibility; [compiler interfaces](preparation_types.pyi)
consume them. Runtime expansion/semantic preparation remains implementation work.
Runtime/GPU/rig verification is separate from declaration validation.
