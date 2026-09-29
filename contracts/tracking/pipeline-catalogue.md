# Initial tracking pipelines and connections

Authority: [T02/T04/T12/T27](../../docs/architecture/tracking.md#t02).
[pipeline_catalogue.py](pipeline_catalogue.py) is the pure versioned composition for
water_flow and fin_flow, both implementation version 1. This registers declarations;
runtime factories, SDK integration and actual Ready preparation remain unimplemented.

## Stages and direct connections

| Role | Water | Fin | Input → output |
| --- | --- | --- | --- |
| Automatic pose only | keypoint_model v1 or threshold_contour v2 | Same selectable methods | private image → candidates |
| Image flow | nvidia_optical_flow v1 | Same | ordered frame pair → leased native grid |
| Geometry | three_point_ellipse v2 | Same | selected landmark triplet → full sampling band |
| Estimator, including filter | water_flow_proxy v1 | fin_flow_proxy v1 | grid + geometry + pose-use → compact proxy result |

Use one shared numerical estimator implementation with concrete WaterFlowSettings and
FinFlowSettings; the latter adds FinRegionSettings. Both embed sections, quality, support
and smoothing. Field definitions live in [method_models.py](method_models.py); fixed rules
live in [water-flow-proxy.md](water-flow-proxy.md), [flow-quality.md](flow-quality.md),
[sectioning.md](sectioning.md) and [fin-flow.md](fin-flow.md). No optional fin field on a
water configuration, separate filtering stage or duplicated method tuning hierarchy.
The selected configuration resolves independently; no automatic copying of water tuning
to fin sessions. Inactive saved configurations remain outside active stage entries.

The host performs the following adapters; these are direct calls within the accepted
[execution model](execution.md), not additional workers or registry stages:

1. Acquisition attachment → immutable private frame and common image preparation (T01).
   Retain only the leases required by movement, pose and admitted optional preview.
2. Automatic pose worker → candidate validation/selection (T17) → exact geometry
   construction → immutable pair in bounded T09 history. Manual geometry is built at Setup;
   manual mode runs no pose worker. Sectioning/selection remain estimator responsibilities.
3. Movement worker → contiguous frame pair → NVIDIA flow lease → completion wait → one
   read-only host view. A source baseline/gap follows A06 and produces no invented pair.
4. Select/check the T09 completed pose/geometry pair at movement evaluation → borrow exact geometry.
   Pass pose-use evidence separately; missing/invalid/stale pose invalidates movement.
   Full-band coverage is diagnostic here; the estimator gates the actual required
   water/fin sections. Low full-band coverage alone cannot reject otherwise valid fin
   support confined to its selected wedge.
5. Pass complete grid, prepared mapping, selected geometry and pose-use into estimator.
   It owns sectioning, optional fin wedge, screening, support, response and filter state.
6. Map filtered_average's three named channels into the existing FeedbackResult. Preserve
   source pair, source interval, sequence and generation from the host, never generated
   by an estimator. Invalid evidence maps to invalid feedback with no usable values.
   Admit existing compact scientific records and release every consumed lease. Preview
   and writer admission cannot retain control buffers or block the movement worker.

[runtime_types.pyi](runtime_types.pyi) binds GeometryMethod, FlowProxyMethod and transient
views. FlowGridMapping supplies source positions and represented rectangular footprints
in acquired-image coordinates, in read-only float64 arrays allocated once per prepared
layout. Its mapping_id is repeated in each FlowLease;
[host-buffer validation](method-bindings.md#completed-host-buffer-contract) binds the
lease context, byte order, pitches and native availability before estimator access. The flow adapter must establish the actual SDK convention; never infer the sample
position from the footprint center or grid stride alone. Validate finite positions,
positive nonoverlapping footprints clipped to source bounds and exact grid dimensions
at Setup. Native mapping/SDK verification remains a runtime integration obligation.
Section and selected-area intersection follow water-flow-proxy.md without upsampling.
SamplingGeometry retains intended off-image support so clipping cannot erase a failed
required section. No per-sample Python objects, serialization or extra flow copy.
Host cache ownership keeps geometry alive through compute; a new pose cannot mutate a
view in use. Grid mapping and flow view identities/dimensions must match the prepared
source layout and current lease. Flow lease/source/processing-generation mismatch is a contract failure,
not ordinary rejected scientific evidence. Memory/progress budgets include all geometry,
section, neighbor-window and filter scratch; exceedance fails preparation/computation
through existing limits rather than silent subsampling.

## Configuration and preparation

resolve_pipeline validates selected family, explicit pose mode, exactly the active
stages, registered concrete schemas, supported implementations, compatible ports and
required cost availability. It returns canonical stage order and channel declarations.
All three channels are anatomical_body interval_average_rate: forward_drive and
sideways_drive in px/s; turn_drive in 1/s (radians per second).
The [output contract](locomotion-output.md) owns VR gain and integration compatibility.
No arbitrary GUI units or per-frame provider selection.

Both configuration validation and backend preparation use this same pure catalogue.
The existing lifecycle additionally checks manual/reference/search inputs, source
allocation/layout, assets, physical device capabilities, byte/time budgets, factory
versions and VR feedback bindings before Ready. These runtime checks are not implemented
by resolve_pipeline. Save the returned StageBindings and channels in PreparedMethods;
validate_prepared rejects mismatches and requires geometry/estimator binding identities.
Binding IDs identify prepared objects, unique within the preparation, and cannot refer
to a different configuration/layout/generation. Header identity supplies trial/source
lineage; the catalogue adds no duplicate control envelope.

Future methods add explicit compatible stage registrations and catalogue compatibility
entries, with versioned settings/evidence and runtime factories. The current supported
set remains deliberately small. No arbitrary graph, plugin discovery or hot swapping.

## Evidence

Both estimator registrations use tracking.flow-proxy-evidence.v1 with an explicit
pipeline_id. FlowProxyEvidence contains ordered full-outline section indices and
intended/visible/accepted areas, exclusive native-cell disposition counts, anatomical
centroid, mean velocity, centred flow moment and second moment, raw/filtered/end triplets and filter
state disposition. Units and formulas are owned by water-flow-proxy.md. Fin excluded
sections remain present with zero areas; section indices never change after cropping.
No dense flow, costs, section maps or per-cell residuals are recorded.

When geometry is unavailable, sections is empty and counts is null. Once a selection
can be formed, include every configured section, even when the estimate fails. Zero
selected cells is a measured zero-count selection, not null. Invalid results retain
available support/count evidence but set all response diagnostics/controls null and
filter_disposition=cleared. Use an explicit reason (for example pose_missing,
pose_invalid, pose_stale, empty_selection, flow_coverage or nonfinite_response;
clipping is logged, not a separate failure). Valid results require all controls/diagnostics, reason=null and
seeded/continued filter disposition. A numerical failure invalidates the full estimate;
it cannot preserve one usable channel.

Registered schema validation rejects malformed payloads. validate_proxy_evidence then
checks family, complete section indices/count, cost-test compatibility and the single
per-section accepted/intended-area gate against the resolved settings. Keep this
cross-validation in compact-record admission and file reading, with existing byte budgets.
Continuous filter/source arithmetic and equality to the paired FeedbackResult are
cross-record checks under [records.md](records.md); parsing one payload proves neither.
The host uses filtered_average directly in feedback and evidence so their values agree.
Historical readers use the matching registered schema/version or report unsupported;
no reinterpretation using later method rules.

## Completion boundary

The initial water/fin method choices, settings/evidence declarations and pipeline
connections are bound. Current work remains contract and cross-backend architecture
review under [GOV-001](../../architecture.md#gov-001). Runtime implementation is a later,
separately authorized phase; missing code is not itself another owner decision. Numeric
tuning uses tracking_config defaults; rig/subject inputs remain explicit. Actual hardware, timing, anatomical accuracy and scientific control performance retain
rig verification. These declarations alone do not run either pipeline or establish
that either proxy accurately measures swimming intent.
