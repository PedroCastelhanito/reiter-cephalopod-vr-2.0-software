# CephVR2.0 rig-to-development handoff

Captured 2026-09-29, Asia/Tokyo, after the NVIDIA driver repair. Start here on the
development machine. This document summarizes evidence; the linked architecture
and contracts remain authoritative. Older audit snapshots describe earlier states.
The subsequent [evidence review](review.md) checks the
included records against current contracts and lists remaining evidence gaps.

The portable archive includes the **entire current CephVR2.0 directory**, including
uncommitted architecture amendments, contracts, schemas, operator configuration,
policy declarations, this report, diagnostic source and evidence. It is a design
snapshot, not an installed application. No backend implementation was added.

## Confirmed inputs versus deferred inputs

| Role | Confirmed owner choice | Hardware identity |
| --- | --- | --- |
| Rendering / projection / tracking GPU work | RTX 5060 Ti | UUID `GPU-77642118-1623-48dd-3686-1014aa86b818`; PCI `00000000:01:00.0` |
| All video encoding, including Visual Stimulus composite | RTX 2080 Ti | UUID `GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc`; PCI `00000000:03:00.0` |
| Operator display / GUI graphics | Ryzen 9 9950X integrated AMD Radeon | Windows PCI device `VEN_1002&DEV_13C0`; Dell S2721HS attached |
| Behavioral camera | **30 Hz** | Basler acA4112-30uc, serial **40065509** |
| Tracking camera | **60 Hz** | Basler a2A2464-77umPRO, serial **40747103** |
| Python | Separate fresh **3.11** environment | Not created; existing environment used only for diagnostic probes |

Resolution, source/recording bit depth, projector-to-surface mapping and the
SpikeGLX dedicated-link address are **deliberately deferred by the owner**.
They are null in [owner-inputs.json](owner-inputs.json), not assigned from discovery.
Camera serials and pulse rates are now saved in
[acquisition_config.toml](../../config/backends/acquisition_config.toml).
Existing enable defaults are preserved (behavioral true, tracking false); neither
is evidence of working hardware preparation. Required settings remain incomplete.
No physical camera settings, MCU settings or wiring were changed in this handoff.

GPU placement follows [SYS-002](../../architecture.md#sys-002); normal CPU control,
tracking preprocessing, geometry and estimation remain governed by T08. The GPU
assignment is not an instruction to port all Python/CPU operations to CUDA.

## Machine and data movement

- Windows 11 Pro x64, build 26200; Ryzen 9 9950X, 16 cores / 32 logical processors.
- MSI MPG X870E CARBON WIFI (MS-7E49), revision 1.0; 64 GiB installed RAM,
  two 32 GiB Micron DIMMs at 5600 MT/s. Windows usable memory is lower.
- Crucial CT2000P3PSSD8, 2 TB NVMe, NTFS C:, approximately 1.48 TB free at inspection.
  No sustained write or power-loss durability benchmark was performed.
- Active Windows power plan: Balanced. No power-management settings changed.
- Both NVIDIA cards now have device problem code 0 and driver **617.14**.
  5060 Ti: 16311 MiB reported VRAM, compute capability 12.0, PCIe **Gen5 ×8**.
  2080 Ti: 11264 MiB, compute capability 7.5, current PCIe **Gen3 ×4**, although
  the card reports maximum width ×16. Do not budget it as a ×16 connection.
- Camera USB parent chains lead to **different host controllers**. Behavioral:
  AMD USB 3.10 controller `DEV_43FD`; tracking: AMD USB 3.10 controller `DEV_15B7`.
  Separate controllers do not prove independent upstream bandwidth or sustained rates.

Use [machine.json](evidence/machine.json) and [power-plan.txt](evidence/power-plan.txt)
for included evidence. The referenced `evidence/nvidia-gpus.csv` is absent from this
checkout; the PCIe widths/generations above are retained handoff observations and
cannot be independently rechecked here. Recover the original CSV or capture a new
dated inventory before relying on those link details for performance budgeting.
Resolve stable identities to current API-specific device ordinals each run; the
observed CUDA/NVIDIA-SMI indices are 0 for rendering and 1 for encoding, not defaults
to hard-code. The driver upgrade already changed Windows display numbering.

The accepted raw-stdin path uses host memory: render/readback on 5060 Ti, then
FFmpeg upload/encode on 2080 Ti. No peer-to-peer/zero-copy capability was established.
For scale only, the current behavioral ROI at 30 Hz is 368.64 MB/s Bayer8 and
1105.92 MB/s reconstructed RGB24; tracking's current ROI at 60 Hz is 300.81 MB/s
Mono8. These are arithmetic payload rates, excluding copying, padding, chunks,
USB overhead, tracking buffers and Visual Stimulus recording. They are not measured throughput
or selected future resolutions. Wider precision multiplies memory/transfer costs.

## Acquisition: concrete device bindings

| Readback | Behavioral 40065509 | Tracking 40747103 |
| --- | --- | --- |
| Current ROI | 4096 × 3000, offset (8, 4) | 2448 × 2048, offset (0, 0) |
| Maximum ROI nodes | WidthMax 4112, HeightMax 3008 | WidthMax 2448, HeightMax 2048 |
| ROI increments | Width/OffsetX 4 pixels; Height/OffsetY 2 | Width/OffsetX 4; Height/OffsetY 1 |
| Current pixel format | BayerRG8 | Mono8 |
| Advertised formats | Mono8; BayerRG8, BayerRG12, BayerRG12p; RGB8, BGR8, YCbCr422_8 | Mono8; Mono10, Mono10p; Mono12, Mono12p |
| PayloadSize | 12,288,000 bytes | 5,013,504 bytes |
| Current exposure | 3000 microseconds | 5000 microseconds |
| Exposure node range | 26–10,000,000 microseconds, increment 1 | 5–10,000,000 microseconds, increment 1 |
| Configured frame-rate node | 30.00030 Hz | 100 Hz |
| **ResultingFrameRate readback** | **29.29630 Hz** | **71.803 Hz** |
| Current triggering | FrameStart, Off; Line1, RisingEdge | FrameStart, Off; Software |
| LineSelector symbols | Line1–Line4 | Line1–Line3 |
| SFNC version | 2.1.0 | 2.7.0 |
| ChunkModeActive | Off | Off |
| ChunkSelector includes | Timestamp, CounterValue, LineStatusAll, ExposureTime, Gain, CRC, sequencer set | Timestamp, FrameID, CounterValue, LineStatusAll, ExposureTime, Gain, CRC, sequencer set, brightness status |

Node ranges are conditional on the inspected selectors/settings. In particular,
behavioral Width.GetMax is 4104 with OffsetX=8, not WidthMax=4112; Height.GetMax is
3004 with OffsetY=4. Query ranges again after ROI/format/selector changes. A nominal
frame-rate node maximum of 1,000,000 Hz is not an achievable sensor rate.

**30 Hz constraint:** behavioral `DeviceLinkThroughputLimitMode=On` and limit
360,000,000 B/s; its current Bayer8 payload at 30 Hz requires 368,640,000 B/s before
overhead. This is a concrete transport-budget conflict with the requested cadence.
The node advertises up to 419,430,400 B/s, but that is not a measured reliable setting.
Once ROI/precision are chosen, explicitly tune the transport/settings and verify
30 Hz. Never lower the owner's requested cadence silently. Tracking's 71.803 Hz
readback supports investigating 60 Hz at current settings; it is not proof of capture.

Full feature values, read/write availability, units, ranges, supported enum entries,
firmware versions and stream-grabber settings are in
[camera-capabilities.json](evidence/camera-capabilities.json). The two `.pfs` files
are **read-only exported snapshots**, not accepted session settings. Do not load
them blindly: they contain the old ROI, trigger-Off and transport configuration.
Stream-grabber counters were read without acquisition; zeros do not prove no drops.

Implement against [A01–A11](../../docs/architecture/acquisition.md) and the
[SDK registry](../../contracts/acquisition/sdk-mappings.md). Device-advertised
YCbCr422_8 does not automatically become supported: that format is outside the
current declared conversion registry. Treat `Mono12p` and legacy packed types as
different formats; use pylon-native conversion and actual row/payload bounds.
No captured Bayer/high-depth image conversion was validated here.

### Camera clock evidence

Both devices expose `TimestampLatchValue` with unit `ns`; the captured value was
zero because this read-only inventory did not execute a latch command. Basler's
[timestamp documentation](https://docs.baslerweb.com/timestamp) lists both exact
models at 1 GHz, one nanosecond per tick. This supports the device-counter unit,
not a common origin, exposure semantics or a host-clock calibration.

Both advertise timestamp chunks, but chunks were disabled and no frame was grabbed.
Bind the chosen grab-result/chunk source under
[camera-clock.md](../../contracts/acquisition/camera-clock.md) and verify its unit,
event semantics, counter meaning, reset/wrap behavior and actual samples before
claiming per-frame provenance. Do not treat a frame counter as a trigger counter.
The authoritative alignment remains saved hardware pulses under SYS-004.

## Encoding on RTX 2080 Ti

Tested with FFmpeg 7.1's NVENC, selecting the 2080 Ti by resolving its UUID to the
current ordinal. This handoff's tests use **three generated static frames each**;
they establish initialization/representation feasibility, not sustained speed.

| Input / requested output | Result |
| --- | --- |
| 4096 × 3000 RGB24 → H.264, explicit full-range YUV444 8-bit | Pass; three frames |
| 2448 × 2048 Mono8 → H.264, explicit full-range YUV444 8-bit | Pass; three frames |
| 4112 × 3008 RGB24 → H.264 | **Reject: width 4112 exceeds 4096** |
| 4112 × 3008 RGB24 → HEVC YUV444 8-bit | Pass; three frames |
| 2448 × 2048 gray16le → HEVC P010 / decoded YUV420 10-bit | Pass; three frames; input is a synthetic container, not sensor-depth validation |
| H.264 10-bit | **Reject: 10-bit encode not supported** |
| AV1 | **Reject: codec not supported** |

Exact argv, errors, selected GPU and ffprobe results are in
[encoder-matrix.json](evidence/encoder-matrix.json). The generated MP4 samples are
not included in this checkout; the JSON retains ffprobe results but local file-content
reinspection is unavailable.
Failed cases can leave empty files; their nonzero exits remain failures. FFprobe
4.3.2 reports the full-range H.264 results as `yuvj444p`; retain range/component
semantics and tool versions when evaluating such representations. No pixel-value
color correctness, source-depth preservation or lossless compression is claimed.

Earlier 2080 Ti tests also passed three concurrent 640 × 480 / 30 fps H.264 sessions
and one separate 10-bit HEVC test (90 frames each). See
[concurrency evidence](../rig-audit-2026-09-29/rtx2080-encoder-probes.jsonl).
This does **not** show that two full-resolution cameras plus Visual Stimulus recording fit.
Do not choose a codec/depth automatically: A08 requires explicit compatible settings.
A full-width behavioral image cannot use the tested H.264 path unchanged; HEVC
or an explicitly selected narrower ROI/recording transform must be considered later.

FFmpeg resolution is still deployment work: shell PATH finds 4.3.2 without the
required hybrid MP4 option, old CephVR Scripts contains 2013 tools, and the tested
7.1 executable is bundled inside imageio-ffmpeg. Install/select a deliberate matching
FFmpeg/ffprobe pair for the new environment's PATH, then repeat validation. Camera
recording uses hybrid MP4 (A08); Visual Stimulus review retains fragmented MP4 (E13). The above
camera-style probes do not verify Visual Stimulus's separate finalization contract.

## Displays and Visual Stimulus

All four intended DLP5050 / ITE6801 projector outputs are on the 5060 Ti. Physical
surface mapping is deliberately deferred. Their reported EDID name does not
identify the projector's commercial model or prove native imager/color precision.

| Current Windows display | Current dimensions / refresh | Rotation | Position |
| --- | --- | --- | --- |
| DISPLAY22 | 1280 × 720 / 60 Hz | 0° | (-3840, 0) |
| DISPLAY19 | 1280 × 720 / 60 Hz | 0° | (-2560, 1) |
| DISPLAY20 | 1280 × 720 / 60 Hz | 180° | (-1280, 0) |
| DISPLAY21 | 720 × 1280 / 60 Hz | 90° | (-2286, 721) |
| DISPLAY5, Dell on AMD | 1920 × 1080 / 60 Hz | 0° | (0, 0) |

[displays.json](evidence/displays.json) holds device/monitor identities, actual modes
and advertised alternatives. Current GLFW modes report RGB8. RGB10 framebuffers,
cable/driver precision, synchronized swaps, optical response and photodiode timing
remain unverified. A separate Basic Display Driver DISPLAY10 (1280 × 720 / 64 Hz)
also remains enumerated; its origin is unknown. Never assign it by discovery order.

Standalone ModernGL context creation and a small Optical Flow check passed again
on 5060 Ti after driver repair. This is not a four-window render benchmark. Verify
actual adapter selection for every rendering context and CUDA provider. Attaching
the Dell to AMD does not prove a future GUI process renders there; no CephVR2.0 GUI
exists yet. A process-wide Python graphics preference may affect multiple Python
backends, so verify GUI and renderer placement independently in the implementation.

Geometry, photometry, marker locations, output precision, pacing mode and composite
layout still need the later installation/session inputs in
[V04/V15/V19–V23](../../docs/architecture/visual_stimulus.md).

## Tracking and native dependencies

- 5060 Ti Optical Flow executed a known two-pixel translation using the existing
  OpenCV CUDA wrapper. It returned native int16 two-component grid data with the
  expected displacement. This is mechanism evidence only.
- **The accepted T07 binding uses the native NVIDIA Optical Flow CUDA API**, not
  an obligation to reuse the existing OpenCV wrapper. A direct adapter's API version,
  buffer formats/pitches, grids 1/2/4, costs, native leases and cancellation remain
  to implement/verify under [method-bindings.md](../../contracts/tracking/method-bindings.md).
- Installed `nvofapi64.dll`, `nvEncodeAPI64.dll`, `nvcuda.dll` report 32.0.16.1714.
  CUDA toolkit 12.8 is installed. Driver-advertised CUDA capability is not a toolkit
  installation. OF SDK 2.0 headers exist in the old OpenCV build tree; they are not
  proof that this older header interface covers every declared requirement.
- ONNX Runtime GPU 1.24.4 completed a small CUDA MatMul with CPU fallback disabled.
  The real pose model, cuDNN convolution/operator coverage and pose performance
  were not tested. Model/threshold/reference-geometry choices remain unset.
- Existing custom OpenCV 4.13.0 targets **SM 120 only**, with no PTX architecture
  listed, Python cp311, and NumPy headers 2.4.3. It is not a universal CUDA binary
  for the 2080 Ti or another development GPU. A native OF adapter permits CPU
  OpenCV for T08; do not assume this custom build is a production requirement.

## MCU, synchronization and Windows services

Arduino Uno is present on COM8, USB VID:PID 2341:0043, serial
1344A474130351F057D6. Arduino IDE 2.3.10 is installed. The port was **not opened**,
so firmware identity/protocol, reset on DTR/RTS, output pins, trigger polarity,
electrical levels, watchdog and grouped ON/OFF timing remain unverified. Existing
legacy sketches do not establish what is flashed or compliance with
[A11 protocol](../../contracts/acquisition/microcontroller.md).

Realtek 2.5GbE is linked at 2.5 Gbps; the 5GbE adapter is linked at 100 Mbps.
Both have link-local IPv4 addresses in the saved inventory. The owner deliberately
deferred the dedicated SpikeGLX IP. No remote host/server was contacted, no firewall
changed and no ephys recording started. Installed remote SpikeGLX/SDK versions,
server bind/port 4142, saved OneBox pulse channels/bits and photodiode wiring remain
unknown. Use the [E12 control contract](../../contracts/spikeglx-control.md), retaining
configuration/readback/control evidence separately from scientific pulse timing.

Windows named memory/events, overlapped pipes, Job Objects, storage sync and the
host monotonic clock have declared contracts. Hardware inventory does not validate
their ownership/cleanup implementation. Keep the
[rig verification worklist](../rig-verification.md) for those later tests.

## Build on the other machine

1. Extract the archive and read [AGENTS.md](../../AGENTS.md),
   [architecture.md](../../architecture.md), the relevant backend architecture and
   contracts. The archive retains the current uncommitted design changes; a checkout
   at the recorded Git commit alone will not include them. Implementation order
   remains an owner decision under ARCH-001; this inventory does not select it.
2. Create a **fresh Python 3.11** environment there; do not clone the legacy rig
   environment or copy DLLs from its site-packages. The final rig deployment also
   needs its own fresh 3.11 environment. No environment was created by this audit.
3. Resolve dependencies for the accepted paths. Existing probe versions are useful
   reference points, not a lockfile or universally compatible installation recipe:

   | Area | Available reference / dependency work |
   | --- | --- |
   | Core/native Windows | Python 3.11.15 used; NumPy 2.4.4, pywin32 311, pyserial 3.5 present; gRPC/protobuf build tooling must be resolved |
   | Acquisition | pypylon 26.3.1, loaded pylon 11.4.0.1134; system installer components 26.02.1.17903 |
   | Rendering | ModernGL 5.12.0, GLFW 2.10.0, glcontext 3.0.0 present |
   | Media | PyAV, imagecodecs, tifffile required by V04 bindings; absent in inspected legacy package inventory |
   | Tracking | ONNX Runtime GPU 1.24.4; CUDA 12.8 toolkit; cuDNN 9.20 installed with separate DLL trees; validate actual DLL resolution, graph placement and native OF shim |
   | Native building | VS Build Tools 2022 17.14.28, MSVC 14.44.35207, Windows SDK 10.0.26100.0 available on rig |
   | GUI | PyQt6 6.11.0 present in old environment; availability alone does not select an undeclared GUI toolkit |
   | Encoding | FFmpeg 7.1 passed the listed probes; acquire a matching ffprobe and validate deployment PATH rather than inheriting old tools |

   Full package inventory, OpenCV build details and executable SHA256 hashes are in
   [software.json](evidence/software.json) and [opencv-build.txt](evidence/opencv-build.txt).
   Do not add Torch, TensorRT, Panda3D or multiple competing OpenCV wheels just because
   they exist in the old environment. The accepted ONNX CUDA/ModernGL paths govern.
4. Build the accepted backend contracts with hardware dependencies behind their
   existing adapters. A development machine lacking this hardware cannot establish
   rig readiness, real-time performance, CUDA placement or scientific calibration.
   Keep capability failures explicit; do not turn unavailable hardware into fake Ready.
5. Return to the rig for final ROI/depth/transport selection, trigger wiring and
   firmware verification, full-workload encoding/tracking/presentation, optical
   calibration, SpikeGLX pulse checks and failure/durability tests. No performance
   defaults or scientific thresholds were guessed to make this handoff look complete.

The scripts under `probes/` are bounded audit utilities, not backend implementation
or a simulated-backend milestone. Camera inventory only reads nodes/exports PFS;
encoder_matrix generates test files, uses NVIDIA-SMI and FFmpeg, and can load the
encoding GPU. It resolves the known rig UUID and refuses to guess another GPU.
Set RIG_FFMPEG/RIG_FFPROBE when paths differ. Re-running into existing outputs fails
because the encoder uses `-n`; keep new evidence separate rather than overwriting it.

## Evidence status and deliberate limits

The inventory, camera readback, signed-driver health, encoder accept/reject cases
and small dependency probes are observed. Owner role/rate/GPU assignments are
confirmed choices. Unchosen image settings/mapping/IP are deliberate deferrals.
Production throughput, full precision/color correctness, optical timing, MCU
electrical behavior and backend lifecycle/durability remain unverified.
This separation is essential when using the archive to start implementation.
