# Rig evidence review — 2026-09-29

The [handoff](rig-handoff-2026-09-29/README.md), its JSON evidence and diagnostic
source, and the [initial audit/repair follow-up](rig-audit-2026-09-29.md) support
keeping the selected architecture while tightening acquisition preparation. They
do not establish production throughput or validate a CephVR2.0 backend. Current
rules remain in the linked decisions; this report is an evidence assessment.

## Findings and design consequences

| Evidence | Assessment and governing decision |
| --- | --- |
| [Owner inputs](rig-handoff-2026-09-29/owner-inputs.json): behavioral 40065509 at 30 Hz; tracking 40747103 at 60 Hz | Already saved in acquisition defaults. [A01](../docs/architecture/acquisition.md#a01) no longer describes all device assignments as missing. ROI, source/recording depth, surface mapping and ephys address remain explicitly deferred. |
| [Camera nodes](rig-handoff-2026-09-29/evidence/camera-capabilities.json): behavioral payload 12,288,000 bytes; limiter On at 360,000,000 B/s; resulting-rate estimate 29.29630 Hz | At 30 Hz the payload alone needs 368,640,000 B/s, 2.4% above the saved limit. [A10](../docs/architecture/acquisition.md#a10) now explicitly checks this necessary transport budget. The supported SDK registry lacked the two device-link limit controls; their mappings are added without assigning tuning values. A recording-only crop cannot fix camera-link bandwidth. |
| Same readback: tracking payload 5,013,504 bytes; estimate 71.803 Hz | At 60 Hz, 300,810,240 B/s is below its saved 360,000,000 B/s limit. This removes that arithmetic conflict only; simultaneous capture, trigger acceptance and overhead remain untested under A10/E15. |
| [Encoder matrix](rig-handoff-2026-09-29/evidence/encoder-matrix.json): four successes, three rejections; three generated static frames per case | [A08](../docs/architecture/acquisition.md#a08) makes post-filter dimensions and actual encoding-device capability explicit. 4096-wide H.264 initialized; 4112-wide H.264 failed, while 4112-wide HEVC initialized. H.264 10-bit and AV1 failed. Keep the generic validator device-dependent and retain explicit codec/depth selection. |
| Synthetic gray16le → HEVC/P010 produced decoded 10-bit output | This does not validate 12-bit camera unpacking/quantization, Bayer reconstruction, color values or original-depth preservation. [A08](../docs/architecture/acquisition.md#a08)'s explicit reduction rule still applies; sensor formats and 16-bit containers are not evidence of supported recording precision. |
| Repaired 2080 Ti, small concurrent encodes; four projector outputs on 5060 Ti | Retain [SYS-002](../architecture.md#sys-002)'s GPU split and host-buffer path. There is no measured failure justifying a new transfer mechanism or workload reassignment. Full camera plus VR-composite load is still an open test, including composite dimensions under [E13](../docs/architecture/vr.md#e13). |
| PATH FFmpeg 4.3.2 lacks required hybrid MP4; probes used bundled 7.1 with older ffprobe | [SYS-003](../architecture.md#sys-003) and A08's fresh environment and deliberate tool baseline remain necessary. A working isolated encoder executable does not validate the deployment pair or VR's distinct fragmented-MP4 closure. |
| Display renumbering after driver update; GLFW RGB8 modes; small GL/flow/ONNX probes | Retain explicit output identities and precision validation under [V15/V20](../docs/architecture/vr.md#v15). No evidence selects physical faces, RGB10 capability, calibrated light or synchronized presentation. Keep [T07/T11](../docs/architecture/tracking.md#t07)'s accepted bindings: the old OpenCV wrapper and toy MatMul do not validate the native flow adapter or real pose model. |

Basler documents the resulting frame rate as a settings-dependent estimate useful
for trigger spacing, and the enabled device-link limiter as a bandwidth/frame-rate
constraint. The new contract distinguishes these checks from measured capture rates.
See [Basler resulting acquisition frame rate](https://docs.baslerweb.com/resulting-acquisition-frame-rate).

## Evidence quality and remaining choices

- The initial audit contains pre-repair GPU observations. Its headings and links now
  distinguish those from the repaired state and later camera assignments.
- `rig-handoff-2026-09-29/evidence/nvidia-gpus.csv` and the generated MP4 samples are
  absent here. Device health is supported by included machine JSON, and encode
  results by saved stderr/ffprobe JSON; raw PCIe details and video contents cannot
  be independently rechecked in this checkout. Do not fabricate replacements.
- The encoder script resolves an NVIDIA-SMI index from a UUID and passes it to
  FFmpeg. Production adapter resolution still must establish the API-specific
  identity under SYS-002; these probe indices are not configuration defaults.
- [E15](../docs/architecture/system-contracts.md#e15) now explicitly separates
  inventory, bounded probes and full-workload verification. Existing evidence
  closes discovery questions, not the entire verification worklist.

Operating-point selection follows [A10](../docs/architecture/acquisition.md#a10);
4096 × 3000 remains the current-ROI candidate, with field-of-view suitability and
final offsets still to confirm. The full-width HEVC probe remains a feasibility
lead, not a selected recording default or throughput result. Precision and blocking
incompatibility warnings follow [A08](../docs/architecture/acquisition.md#a08).
The [rig worklist](rig-verification.md) carries the remaining checks; no new numeric
ROI/depth/transport default or hardware validation is established by this review.

## Review validation

Checked the seven encoder cases against their recorded exits, errors, dimensions,
decoded formats and frame counts, and recomputed the camera payload budgets from
the saved nodes and owner rates. Documentation links, decision-register revisions
and TOML syntax/value preservation are checked locally. Hardware probes were not
rerun on the development machine; runtime, optical, electrical and durability
validation remain open.
