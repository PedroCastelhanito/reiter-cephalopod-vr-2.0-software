# Tracking integration contract review

Document-level review; no backend implementation or runtime/rig validation. Current
scope and the coding gate remain [GOV-001](../architecture.md#gov-001).

| Boundary | Finding and current owner |
| --- | --- |
| Acquisition → tracking → VR Setup | Missing metadata/confirmation routes are now declared in the [Setup handoff](../contracts/data-preparation.md). Independent Ready gates no longer need to form a dependency cycle. |
| First tracking activity | [Flow operations](../contracts/tracking/method-bindings.md#baseline-and-pair-operation-contract) and [lifecycle](../contracts/tracking/lifecycle.md) distinguish completed baseline from usable movement and require actual evaluation for Started. |
| Invalid pose or inadequate flow support | [Execution](../contracts/tracking/execution.md) and [proxy](../contracts/tracking/water-flow-proxy.md) already prohibit older-valid fallback, stale controls and filter continuation through invalid intervals; [VR feedback](../contracts/vr/feedback.md) owns holding applied movement. |
| Reset supersession and credits | R1A is accepted and bound in [feedback delivery](../contracts/tracking/feedback-delivery.md): monotonic generation markers, skip superseded transport markers, preserve the saved local chain, and credit each exact entry once. |
| Stopping and recording | [Stop ordering](../contracts/tracking/lifecycle.md#producer-cutoff-late-work-and-finalization) now binds local cutoff, commit versus retirement, late pose/result evidence, ring leftovers, truthful Stopped and later file closure. No runtime file reread is authorized. |
| Resource retirement | [Frame-buffer ownership](../contracts/acquisition/frame-buffers.md#cleanup-and-failure) and [E06](../docs/architecture/system-contracts.md#e06) require matched release/native completion; cancellation or pipe EOF alone is insufficient. |

This trace establishes the listed declaration findings, not whole-system readiness.
The Setup, reset/credit and stop/late-completion gaps identified in this trace are
reconciled. No further owner choice was identified for these boundaries. This is
closure of the listed contract findings, not an exhaustive audit of every backend
implementation contract or authorization to begin coding. Hardware capability, numeric rig tuning,
scientific response and throughput retain their explicit deferrals.
