# Rig inventory and deferred-check assessment — 2026-09-29

**Latest status:** RTX 2080 Ti error 31 is resolved following the NVIDIA 617.14
update. Both NVIDIA adapters report problem code 0 and driver 32.0.16.1714. See
the repair follow-up below; initial inventory files and earlier test rows preserve
the pre-update observations.
The later [handoff](../rig-handoff-2026-09-29/README.md) supplies owner camera roles/rates
and the full-resolution encoder matrix. See the
[evidence review](../rig-handoff-2026-09-29/review.md) for design implications and
limitations of the files available in this checkout.

The rig is accessible. Core camera, CUDA, optical-flow, OpenGL and NVENC capabilities
are present, but this is not full CephVR2.0 validation. The fresh Python 3.11
environment is specified by [SYS-003](../../architecture.md#sys-003); it has not been
created or populated in this audit. Existing environments, drivers, device settings,
firmware and system PATH were not changed. No camera acquisition or serial commands
were issued. Camera nodes were read through open/close SDK handles.

## Hardware observed — initial snapshot

| Component | Observation | Implication / limit |
| --- | --- | --- |
| OS | Windows 11 Pro x64, build 26200 | Windows-native contracts still require implementation tests. |
| CPU / memory | Ryzen 9 9950X, 16 cores / 32 threads; 2 × 32 GiB Micron DIMMs at 5600 MT/s | 64 GiB installed; Windows reports about 61.55 GiB usable. |
| Working NVIDIA GPU | RTX 5060 Ti, 16,311 MiB reported VRAM, driver 610.88 | Only GPU enumerated by NVIDIA-SMI/CUDA in this audit. SYS-002 now assigns rendering/projection/tracking GPU work here and video encoding to the currently unavailable RTX 2080 Ti. |
| Other display adapters | AMD Radeon integrated graphics OK; RTX 2080 Ti present with Windows error code 31 | Do not count the 2080 Ti as usable capacity. Cause not diagnosed or driver changed. |
| Storage | Crucial CT2000P3PSSD8, 2 TB NVMe; C: NTFS; approximately 1.48 TB free | Healthy inventory status; sustained write throughput and durability untested. |
| Displays | Follow-up after projector connection: Dell S2721HS on AMD integrated graphics plus four DLP5050 / ITE6801 outputs on RTX 5060 Ti; all at 60 Hz | Windows and GLFW detect all five active displays. Projector topology is detailed below; optical precision/pacing remain unverified. |
| Cameras | Basler acA4112-30uc, serial 40065509; a2A2464-77umPRO, serial 40747103 | Both enumerated and opened for readback with pypylon. Roles and desired operating modes are not inferred. |
| MCU | Arduino Uno on COM8 | Firmware identity, pin allocation, wiring and watchdog behavior unverified; port was not opened. |
| Other serial device | PL2303HXA device with a phased-out-device warning in its name | No usable COM assignment established for this device. |
| Wired networking | Realtek 2.5GbE link at 2.5 Gbps; Realtek 5GbE link at 100 Mbps | Both IPv4 addresses were link-local (169.254/16). Neither adapter's role or peer identity was established. |
| Wireless | Qualcomm Wi-Fi active, 286.8 Mbps reported link | Does not establish the dedicated SpikeGLX control link. |

The full present-device inventory, RAM, disks and adapter evidence is in
[hardware.json](hardware.json). Inventory cannot establish
unpowered/disconnected instruments, cable routing, trigger voltages or OneBox wiring.

### Projector connection follow-up

After the owner connected the projectors, Windows display-adapter enumeration and
GLFW both detected four separate active projector outputs on the RTX 5060 Ti.
The Dell operator monitor is on AMD integrated graphics. This resolves the earlier
missing-projector inventory finding; the original hardware.json remains the initial
snapshot. Updated evidence, including advertised modes, is in
[projector-topology.json](projector-topology.json).

| Windows display | Desktop image size | Refresh | Windows rotation | Desktop position (x, y) |
| --- | --- | --- | --- | --- |
| DISPLAY1 | 1280 × 720 | 60 Hz | 0° | -3840, 0 |
| DISPLAY2 | 1280 × 720 | 60 Hz | 0° | -2560, 1 |
| DISPLAY3 | 1280 × 720 | 60 Hz | 180° | -1280, 0 |
| DISPLAY4 | 720 × 1280 | 60 Hz | 90° | -2286, 721 |
| DISPLAY5 (Dell) | 1920 × 1080 | 60 Hz | 0° | 0, 0 |

GLFW reports RGB8 for each current mode. This is not a measurement of the cable's
signal depth, projector light precision, native imager resolution or synchronized
optical refresh. Physical surface assignments (left/right/front/floor) are unknown;
do not infer them from discovery order or desktop position. Windows numbering may
change on reconnect. No display settings were changed and no patterns projected.

## Camera readback

These are observed saved/current values, not selected CephVR2.0 defaults or achieved rates.

| Camera | Current image | Exposure | Current frame-rate node | Trigger readback | Advertised formats |
| --- | --- | --- | --- | --- | --- |
| acA4112-30uc | 4096 × 3000, BayerRG8 | 3000 microseconds | 30.00030 Hz | FrameStart, Off; Line1, RisingEdge | Mono8, BayerRG8, BayerRG12, BayerRG12p, RGB8, BGR8, YCbCr422_8 |
| a2A2464-77umPRO | 2448 × 2048, Mono8 | 5000 microseconds | 100 Hz | FrameStart, Off; Software | Mono8, Mono10, Mono10p, Mono12, Mono12p |

Frame-rate node values do not prove attainable external-trigger cadence. Firmware
and additional readback are preserved in [capability evidence](capability-probes.jsonl).
12-bit formats require explicit compatibility with A08's recording-depth rules;
the 10-bit encoder smoke test below does not validate a 12-bit source conversion.

## Installed software and fresh-environment implications

| Area | Observed installation | CephVR2.0 implication |
| --- | --- | --- |
| Python | Miniforge base 3.12.9; CephVR and Master8 environments 3.11.15; shell `python` resolves to WindowsApps alias; no `py` launcher on PATH | Use an explicitly activated, separate 3.11 environment. Availability is established; fresh installation remains work. |
| Camera SDK | pylon installed components 26.02.1.17903; pypylon 26.3.1; loaded pylon runtime reports 11.4.0.1134 | Installer, Python package and loaded runtime versions are distinct. Verify the fresh environment's actual loaded SDK. |
| CUDA | Toolkit 12.8; NVIDIA-SMI advertises CUDA UMD 13.3; cuDNN 9.20 installed with 12.9 and 13.2 DLL directories | Driver capability is not the installed toolkit version. Record resolved DLLs when constructing the fresh environment. |
| Native build tools | VS Build Tools 2022 17.14.28; MSVC 14.44.35207; Windows SDK 10.0.26100.0 | Native rebuilding tools exist; compiler/build execution not tested here. |
| OpenCV | Loaded 4.13.0 custom CUDA build, architecture 120, Python cp311; source/build tree at `C:/Dev/software/OpenCV_NVIDIAOF` | Preserve/reproduce this capability deliberately. Package metadata also lists opencv-python 4.13.0.92 and opencv-contrib-python-rolling 4.12.0.86; metadata alone does not describe the loaded binary. |
| Tracking | ONNX Runtime GPU 1.24.4; NumPy 2.4.4; Torch 2.11.0+cu128; TensorRT 10.16.0.72 in old environment | The accepted ONNX CUDA path does not require adopting Torch/TensorRT as runtime dependencies. |
| Rendering / device helpers | ModernGL 5.12.0, GLFW 2.10.0, glcontext 3.0.0, PyQt6 6.11.0, pyserial 3.5, pywin32 311 | Existing-package discovery is not fresh-environment validation or a new GUI-library decision. |
| Missing from old Python package inventory | grpcio, grpcio-tools, PyAV, imagecodecs, tifffile | Required control/media dependencies need resolving for the new environment; see E08 and V04 runtime bindings. |
| MCU tools | Arduino IDE 2.3.10 | Does not identify firmware currently flashed on COM8. |
| Ephys | No SpikeGLX/OneBox installation established on this host | Expected separate-machine scope under SYS-001; remote software, SDK and command server remain unverified. |

[Installed Windows software](installed-software.json) and
[old Python package inventory](legacy-python.json) preserve
the observed versions. Registry inventory does not enumerate every portable program.

### FFmpeg resolution is a concrete blocker

Three different builds were found:

- Current shell PATH: `C:/Dev/software/ffmpeg-4.3.2-2021/bin`, FFmpeg/ffprobe 4.3.2.
  Its MP4 help lacks `hybrid_fragmented`, required by [A08](../../docs/architecture/acquisition.md#a08).
- Old environment `Scripts/ffmpeg.exe` and `Scripts/ffprobe.exe`: N-55702-g920046a,
  built August 2013. These are another potential PATH shadowing source.
- imageio-ffmpeg bundled executable: FFmpeg 7.1, with `hybrid_fragmented` support.
  Used by explicit path for the isolated development probes only. This is not the
  PATH-resolved paired-tool deployment required by A08, nor a fully validated baseline.

The new environment needs a deliberate compatible FFmpeg/ffprobe pair on its PATH.
Do not copy the old environment's executable resolution. The upstream
[FFmpeg format documentation](https://www.ffmpeg.org/ffmpeg-formats.html)
describes hybrid fragmentation and graceful conversion to ordinary MP4.

## Executed capability probes — before driver repair

Executed with the old CephVR Python 3.11.15 installation, outside the nonexistent
CephVR2.0 backend. Each result must be repeated in the fresh environment.
All NVIDIA probes in this audit ran on the RTX 5060 Ti. Following the owner's
revised [GPU assignment](../../architecture.md#sys-002), encoder results below provide
no validation of the intended RTX 2080 Ti encoding path. The repair follow-up below
records the later driver resolution and separate checks on that device.

| Probe | Actual result | What remains unproven |
| --- | --- | --- |
| Basler SDK enumeration and node readback | Both cameras readable; no grabs or settings writes | Trigger/frame correspondence, simultaneous capture, timestamp units, native conversion and throughput |
| NVIDIA Optical Flow | One 640 × 480 synthetic image pair, 2-pixel horizontal shift; SHORT2 output shape 120 × 160 × 2, int16; interior median displacement 2 pixels | Real-camera accuracy, grids/settings, cost buffers, reset semantics and full workload |
| ModernGL standalone context | NVIDIA RTX 5060 Ti renderer, OpenGL 3.3; max texture size 32768 | GLFW presentation contexts on projectors, RGB10, optical calibration and pacing |
| ONNX Runtime CUDA | 32 × 32 identity MatMul succeeded after `preload_dlls()`, with `session.disable_cpu_ep_fallback=1` | Real pose model/operator coverage, cuDNN convolution, model accuracy and throughput. Provider list still includes CPU; that list alone is not inference evidence. |
| Three concurrent NVENC processes | Three raw RGB24 stdin streams, each 640 × 480 at 30 fps, 90 frames; h264_nvenc, p4, yuv420p, hybrid MP4; all exit 0, no warnings; ffprobe reports 90 frames and 3 seconds each | Planned two-camera plus Visual Stimulus-composite resolutions/rates, simultaneous tracking/rendering, startup/stop timing and dropped-frame behavior |
| 10-bit NVENC path | Separate gray16le stdin → hevc_nvenc/p010le, same size/rate/count; exit 0; decoded stream described as yuv420p10le, 90 frames, 3 seconds | Source-depth alignment, known-value/range/color correctness, real sensor conversion and crash-prefix behavior |

The ONNX DLL-loading mechanism is documented by
[ONNX Runtime](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html).
No package combination is promoted to a validated deployment from this small probe.

[Encoder evidence](encoder-probes.jsonl) contains exact commands,
return codes and ffprobe outputs. Synthetic MP4s and diagnostic scripts are retained
in the workspace `tmp/rig-audit-2026-09-29/` directory outside the software Git repo.
Post hoc file inspection here is development verification, not a proposed runtime
validation pass. Samples are static, short and small; they are not benchmarks.

## Disposition of rig-deferred work

| Governing records | Disposition after inspection |
| --- | --- |
| SYS-002 / SYS-003 | Requested GPU split recorded; RTX 2080 Ti device error resolved and bounded encoder probes pass. Fresh Python 3.11 environment creation and dependency pinning remain work. |
| A08 / E13 | Basic raw stdin and NVENC capability demonstrated, including three concurrent sessions at small sizes. Incompatible default FFmpeg discovered. Exact production tool baseline, source conversions, camera/composite rates and containers under failure remain open. |
| A10 / A11 | Device identities/current formats and COM port discovered. The later handoff supplies camera roles and requested rates; final image/transport settings, firmware, trigger levels, wiring, counter/timestamp semantics and drain/serial budgets remain open. |
| V04 / V15 / V19–V23 / V26 | GL context creation demonstrated; connection follow-up identifies all four projector outputs on RTX 5060 Ti at 60 Hz. Physical surface assignment, RGB8/RGB10 optical path, calibration, photodiode, pacing and end-to-end age remain open. |
| T07 / T11 / T08–T45 | Basic flow and CUDA inference execute. Model/threshold/reference geometry/scientific inputs and full tracking workload remain unverified. |
| E12 / SYS-004 | Dedicated ephys peer, command-server bind/firewall, installed SpikeGLX/SDK, OneBox saved channel/bit mapping and recorded pulse evidence remain unknown. Link speed alone cannot settle these. |
| E05–E08 / A03 / A07 / E15 | Lifecycle, Windows ownership, seqlocks/events, cleanup, fault handling, crash recovery, storage sync and production deadlines require implemented backends and execution. Inventory cannot close them. |

The [verification worklist](../rig-verification.md) remains the authority for outstanding
checks. Explicit scope deferrals (for example projector-synchronized MCU pulses,
assisted firmware flashing and general remote operator control) are not reopened
merely because the rig is now accessible. No unanswered scientific choice, role
assignment or calibration was inserted into operator configuration.

## RTX 2080 Ti repair follow-up

Initial evidence showed the 2080 Ti bound to 610.47 (`oem18.inf`) while the
5060 Ti and shared NVIDIA kernel service used 610.88 (`oem7.inf`). The latter
package did not match this 2080 Ti's hardware ID. This implicated mismatched
driver packages; it was not evidence of a failed GPU.

Both old driver packages were exported to the workspace's
`tmp/rig-audit-2026-09-29/driver-repair/` directory. A cached 617.14 package's
Microsoft-signed catalog was verified and its INF matched both GPU device IDs.
Our no-reboot installer attempt returned `0xE4000008` because a separate NVIDIA
installation was already active. That active installer subsequently reported all
packages successfully installed. No competing installer was terminated and no
reboot was initiated here.

Verification after the update:

- Both NVIDIA GPUs have Windows status OK, problem code 0, driver 617.14.
- NVIDIA-SMI index 0 is RTX 5060 Ti, UUID
  `GPU-77642118-1623-48dd-3686-1014aa86b818`; index 1 is RTX 2080 Ti, UUID
  `GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc`, 11264 MiB VRAM.
  These are observed indices, not permanent configuration defaults.
- Explicit FFmpeg `-gpu 1` passed three concurrent 640 × 480, 30 fps H.264
  sessions and a separate 10-bit HEVC session. Each produced 90 frames / 3 seconds,
  exit 0 and no warnings. Exact commands/results are in
  [2080 Ti encoder evidence](rtx2080-encoder-probes.jsonl).
  Full camera/composite workload, color/precision and failure tests remain open.
- Optical Flow's 2-pixel displacement check and ModernGL context creation still
  pass on RTX 5060 Ti under 617.14.
- The installer reset projector positions/rotations. Their saved settings were
  restored and verified using stable monitor instance matches: old DISPLAY1/2/3/4
  are now DISPLAY22/19/20/21, with their previous sizes, 60 Hz, positions and
  rotations. The Dell remains on AMD graphics. Windows additionally enumerates
  a Basic Display Driver output, DISPLAY10 at 1280 × 720 / 64 Hz; its origin is
  unverified and it was not reassigned or disabled. Do not use it as a projector
  identity. See [post-update topology](projector-topology-after-driver.json).

Error 31 and basic encoding availability are resolved. This does not establish
CephVR2.0 implementation readiness or sustained production throughput.
