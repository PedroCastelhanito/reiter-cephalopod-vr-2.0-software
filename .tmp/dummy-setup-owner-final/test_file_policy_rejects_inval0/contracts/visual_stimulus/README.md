# Visual stimulus backend contracts and status

Policy authority: [Visual Stimulus architecture](../../docs/architecture/visual_stimulus.md). The identified
rig-independent architecture choices and interface declarations are closed, including
V02 complete settings/conditions, V16 planar arena movement, V05 keyframe boundaries
and the V12/V28 in-process recording thread and JSON Lines evidence. No further user
choice is currently identified.
Implementation and local validation are tracked in the [Visual Stimulus report](../../reports/visual_stimulus.md);
contract closure is not rig acceptance.

| Area | Owning contracts / concrete declarations |
| --- | --- |
| Authoring, compilation and continuity | [Program/units/coordinates/compatibility](stimulus-schema.md), [complete settings](program-authoring.md), [canonical model](program_model.py)/[schema](program.schema.json), [fixed unit catalogue](parameter_catalogue.py), [shared primitives](schema_common.py), [prepared artifact](prepared-trial.schema.json), [compiler interface](preparation_types.pyi), [duration algorithm](durations.md), [transitions](prepared-plan.md). |
| Display, geometry and color | [Display model](display_profile.py)/[schema](display-profile.schema.json), [geometric schema](geometric-profile.schema.json), [geometry/provider implementation binding](runtime-bindings.md), [projection](projection.md), [color stages](color-pipeline.md), [photometric model](photometric_profile.py). |
| Media/resources | [Profiles](media-profiles.md), [protection](asset-lifetime.md), [manifest schema](resource-manifest.schema.json), [native adapters/reservation/cleanup](runtime-bindings.md), [provider interfaces](resource_types.pyi), [decoder interfaces](decoder_types.pyi). |
| Arena | [Movement](arena-movement.md), [protocol boundary schema](arena-boundaries.schema.json), [planar units/pose/constraints](stimulus-schema.md), [asset appearance](arena-appearance.md). |
| Worker/control/data paths | [Lifecycle](worker-control.md), [resource and data paths](runtime-bindings.md), [messages](../cephvr/visual_stimulus/v1/messages.proto), [runtime fields](../cephvr/visual_stimulus/v1/runtime.proto), [feedback/reset messages](../cephvr/visual_stimulus/v1/data.proto). |
| Recording | [Tiled composite capture/overload](recorded-outputs.md), [arguments and constant-rate review timing](encoding-options.md), [JSON Lines evidence](evidence-format.md)/[schema](evidence-record.schema.json), [closure predicates](video-completion.md). |
| Feedback | [Application/reset/holds](feedback.md), [writer/units binding](stimulus-schema.md), [heading-relative increment](planar_feedback.py), [result/reset transport](runtime-bindings.md), [data messages](../cephvr/visual_stimulus/v1/data.proto). Estimator design stays with tracking, last. |
| Analysis-owned replay | [Replay and partial labelling](replay.md), [export interface](evidence_types.pyi), [PNG export binding](evidence-format.md), generated request/report schemas alongside the canonical evidence model. |

## What is closed and what still needs work

**Closed at the declaration level:** ownership, accepted behavior, source/prepared/
calibration/resource/evidence schemas, protocol and private interfaces, bounded transport
mechanics, file naming/ownership, source adapters, validation pass obligations and
analysis-owned offline request/report interfaces. Generated JSON Schema expresses structure; cross-field,
resource and stream semantic checks also follow their owning contracts. The checked-in
pure validators implement only their documented subset, not every compiler obligation.

**Implementation ownership:** the experiment backend implements compilation,
preparation, live rendering and recording, including the immutable recipe and detailed
evidence needed for later analysis. Offline replay/export belongs to analysis software
and is not shipped by this package. GUI authoring remains outside the current stage.
See the implementation report for tested behavior and pending native acceptance.

**Explicitly deferred:** physical geometry/projector assignment and photodiode values,
measured calibration, checking/tuning the supplied engineering limits, full-workload performance,
optical/multi-output timing, crash behavior, and the previously accepted encoder
input-format/throughput verification.
[The rig verification plan](../../reports/rig-verification.md) remains authoritative.
A real Setup must block if required numeric inputs or a demonstrated encoder input path
are unavailable; deferral never means readiness or proven feasibility.

The example [drift-hold.json](examples/drift-hold.json) demonstrates complete blocks
with retained phase semantics; it is a schema example, not hardware-ready configuration.
Static schema/declaration/document checks cannot establish rendering fidelity, timing,
throughput, durability or pixel equality. Tracking remains last under GOV-001.
