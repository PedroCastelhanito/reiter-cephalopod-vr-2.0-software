# Visual stimulus backend contracts and status

Policy authority: [VR architecture](../../docs/architecture/vr.md). The identified
rig-independent architecture choices and interface declarations are closed, including
V02 complete settings/conditions, V16 planar arena movement, V05 keyframe boundaries
and the V12/V28 in-process recording thread and JSON Lines evidence. No further user
choice is currently identified.
This is design/schema closure, not a claim that a working backend is implemented.

| Area | Owning contracts / concrete declarations |
| --- | --- |
| Authoring, compilation and continuity | [Program/units/coordinates/compatibility](stimulus-schema.md), [complete settings](program-authoring.md), [canonical model](program_model.py)/[schema](program.schema.json), [fixed unit catalogue](parameter_catalogue.py), [shared primitives](schema_common.py), [prepared artifact](prepared-trial.schema.json), [compiler interface](preparation_types.pyi), [duration algorithm](durations.md), [transitions](prepared-plan.md). |
| Display, geometry and color | [Display model](display_profile.py)/[schema](display-profile.schema.json), [geometric schema](geometric-profile.schema.json), [geometry/provider implementation binding](runtime-bindings.md), [projection](projection.md), [color stages](color-pipeline.md), [photometric model](photometric_profile.py). |
| Media/resources | [Profiles](media-profiles.md), [protection](asset-lifetime.md), [manifest schema](resource-manifest.schema.json), [native adapters/reservation/cleanup](runtime-bindings.md), [provider interfaces](resource_types.pyi), [decoder interfaces](decoder_types.pyi). |
| Arena | [Movement](arena-movement.md), [protocol boundary schema](arena-boundaries.schema.json), [planar units/pose/constraints](stimulus-schema.md), [asset appearance](arena-appearance.md). |
| Worker/control/data paths | [Lifecycle](worker-control.md), [resource and data paths](runtime-bindings.md), [messages](../cephvr/vr/v1/messages.proto), [runtime fields](../cephvr/vr/v1/runtime.proto), [feedback/reset messages](../cephvr/vr/v1/data.proto). |
| Recording | [Tiled composite capture/overload](recorded-outputs.md), [arguments and constant-rate review timing](encoding-options.md), [JSON Lines evidence](evidence-format.md)/[schema](evidence-record.schema.json), [closure predicates](video-completion.md). |
| Feedback | [Application/reset/holds](feedback.md), [writer/units binding](stimulus-schema.md), [heading-relative increment](planar_feedback.py), [result/reset transport](runtime-bindings.md), [data messages](../cephvr/vr/v1/data.proto). Estimator design stays with tracking, last. |
| Replay | [Replay and partial labelling](replay.md), [export interface](evidence_types.pyi), [PNG export binding](evidence-format.md), generated request/report schemas alongside the canonical evidence model. |

## What is closed and what still needs work

**Closed at the declaration level:** ownership, accepted behavior, source/prepared/
calibration/resource/evidence schemas, protocol and private interfaces, bounded transport
mechanics, file naming/ownership, source adapters, validation pass obligations and
offline export entry points. Generated JSON Schema expresses structure; cross-field,
resource and stream semantic checks also follow their owning contracts. The checked-in
pure validators implement only their documented subset, not every compiler obligation.

**Local runtime implementation remains:** the editor/compiler and Stafford sampler,
semantic passes, native readers/importers/indexing, renderer/shaders/window dispatch,
queue/GPU/resource providers, recording-thread/FFmpeg integration, evidence writer and
replay exporter. Implement and verify these against the declared interfaces. These are code
work, not another architectural-choice questionnaire and not rig-deferred work. No
running backend or simulated-backend milestone is claimed by these documents.

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
