# VR program model and validation binding

Governing rule: [V03](../../docs/architecture/vr.md#v03). Configuration authority,
validation deadlines, readiness and locking follow [E07](../../docs/architecture/experiment.md#e07).
This binds the implementation approach. The [canonical stimulus model/schema](stimulus-schema.md) is declared; a runtime compiler is not delivered.

## One authoritative definition

Use Pydantic v2 BaseModel definitions in the VR lightweight configuration package as
the only maintained program structure. Generate the JSON Schema with
`Program.model_json_schema(mode="validation")`; publish it with its program-format
version and package compatibility identity. Generated schema may be checked into
source control for editors, but regenerate it from the model and check for drift;
never hand-edit a second field/constraint definition. Library versions belong in
implementation dependencies, not operator-selectable runtime plugins.

The lightweight package imports no renderer, GUI, decoder or device SDK. GUI and
headless requests call the same parsing/validation entry point. The GUI may use the
generated schema for field presentation, but local widgets are not validation
boundary authorities. Do not implement a parallel GUI-only interpretation of units,
condition references, duration feasibility, function types or state transitions.

[schema_common.py](schema_common.py) owns the strict base model, identifier primitives,
portable paths and bounded duplicate-key/nonfinite-safe JSON parser used by programs,
display/photometric profiles, prepared artifacts and evidence. Callers provide byte budgets;
program nesting is capped at 64. `parse_profile_json` also requires an explicit
`max_bytes` budget, matching the other public loaders. Output/frame/device IDs are opaque nonempty names up
to 128 characters, preserved verbatim; program-local IDs retain their stricter identifier
syntax. Display, geometric and photometric output IDs use the same primitive.
[generate_schemas.py](generate_schemas.py) regenerates all published schemas; `--check`
reports drift without writing.

Program and PreparedTrial now use format version 2: function/assignment units are derived
from the fixed catalogue and the prepared artifact is the only schedule representation.
Version 1 inputs fail explicitly; no implicit migration is supplied. Other formats retain
their existing versions. The removed control schedule field's name and number remain
reserved. Rebuild clients against the updated declarations before using version 2.

Use tagged unions for stimulus/function/duration variants. Reject unknown fields,
unsupported variants/versions, nonfinite numbers and inappropriate type coercions
rather than ignoring them or guessing another type. Use the equivalent of
`ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, validate_default=True)`
on the model hierarchy, supplemented by field-specific constraints. JSON numbers
may enter declared real-valued fields; strings and booleans are not numeric values.
Reject duplicate JSON object keys before model validation. Preserve missing versus
explicit false/zero under E07; validate defaults rather than silently repairing data.

Structural validation runs through the canonical model; exported JSON Schema exposes
the same structure to tools. Do not require a second full JSON Schema pass on every
model load. Cross-field, reference, unit, ordering, duration, animation and motion
rules use shared semantic validators in that package, linked to their owning
contracts. Schema validation alone cannot establish those semantic or asset rules.
No arbitrary Python expressions/callbacks or dynamically imported stimulus classes.

## Entry points and when they run

| Stage | Required behavior |
| --- | --- |
| GUI/headless load or edit | Parse with one shared JSON interpretation and run structural/pure semantic checks. Return field paths and actionable errors tied to configuration revision and module version. No media opens, hashing, decode or GPU work. E07 owns Unvalidated edits and deadlines. |
| Setup | Confirm format/module compatibility, validate the adopted source/settings, resolve existing seeds and expanded order/durations, bind assets through V04, and compile the resolved plan and transition operations. Backend/device/resource checks remain here. |
| Ready | Retain the immutable source snapshot, resolved plan and prepared-resource identity for the adopted revision. Controller adopts backend resolution under E07; a locally valid draft is not session Ready. |
| Trial/epoch execution | Select the prepared plan/operations and update V07 live state. Do not parse JSON, instantiate authoring models, regenerate schema, revalidate the whole program or rehash assets. Local bounds/generation/health checks remain necessary. |
| Fresh Setup | Validate changed configuration and rebuild affected prepared data through the same path; file edits cannot replace a prepared snapshot in place. |

One shared loader must give equivalent results for a JSON file and the same authored
payload submitted through GUI/headless control. Pydantic's Python-input and JSON-input
paths have different coercion rules; do not let the client path decide behavior.
Normalize requests through the declared JSON boundary before strict validation.
Parsing limits and expanded-plan/resource budgets must be enforced before readiness;
concrete capacity fields are bound in worker-control.md; installation values remain explicit inputs.

## Prepared ownership and compatibility

Compile authoring objects into private immutable execution data: resolved IDs,
epoch boundaries, typed function coefficients, transition operations and resource
references. Keep mutable live phase/pose/playback state separately under V07.
Do not assume `frozen=True` recursively freezes contained dictionaries/lists; detach
and freeze nested execution data and do not retain editable aliases. The plan is a
derived artifact, never a second editable program or source of independently drawn
random values. Retain actual resolved values under V06/V08/E07.

The [prepared-plan structure](prepared-plan.md) and [local declarations](prepared_plan_types.pyi)
bind occurrence lineage, contiguous epoch boundaries and ordered transitions. The [full source/prepared schemas](stimulus-schema.md) bind the payloads; compiler execution remains implementation work.

Bind the program-format version, configuration revision, model/compiler compatibility
identity and prepared-resource generation to the plan. Reject unsupported versions
before Ready; do not silently discard fields or use newer defaults to interpret an
old program. Explicit migration, if later supported, creates a new authored document
for normal validation/Setup and does not rewrite retained session recipes.
A library version string alone is not a declaration of renderer/replay compatibility.

Use E07/E04's existing setup metadata path for program/plan retention. The [artifact ownership](runtime-bindings.md) and [typed evidence](evidence-format.md) bind storage without another session log.
Input preparation is distinct from E05's external post hoc output-file validation.

Implementation references: [Pydantic schema generation](https://docs.pydantic.dev/latest/concepts/json_schema/),
[strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/), and
[model immutability limits](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability).
Static contract checks do not establish a working editor, compiler or rendering speed.
