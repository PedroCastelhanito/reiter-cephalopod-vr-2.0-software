# Optimized preview comparison — 2026-10-26

Owner authorized implementation/testing of the proposed embedded alternatives under
G01's isolated benchmark exception. No managed backend, device, production GUI,
configuration or dependency changes are part of this increment. Concurrent GUI
polish remains outside the comparison. See the parent context for prior results;
do not mix those different workload/source implementations into this matrix.

## Implementation and scope

`benchmark_snapshot.py`, `widgets_snapshot.py` and `source-hashes.json` bind these
results to the working-tree implementation. The original tool's widget responsibility
is extracted to `tools/preview_benchmark_widgets.py` under ARCH-002 before extending
it; the tool retains process/timing orchestration. Installed Qt, NumPy, OpenGL and
ModernGL are reused. No new framework or dependency is introduced.

- `embedded`: original one-OpenGL-widget-per-stream QImage copy/QPainter baseline.
- `raster`: one ordinary QWidget drawing retained QImages over reusable, privately
  owned NumPy buffers. No OpenGL widget. Display resizing scales retained images.
- `texture`: one QOpenGLWidget, persistent RGB8 or R8 texture per stream, reusable
  owned CPU buffers, one texture update per new batch and retained-texture drawing
  on resize. A shader handles monochrome display without expanding grayscale pixels
  to RGB. Qt still owns/recreates the single canvas framebuffer on resize.
- `native-follow`: separate HighGUI process with production Win32 owner/geometry
  helpers and200ms placement updates, as in the preceding component experiment.

All modes use three independently phased moving bars,640-square source frames,
20Hz source updates and independent16ms host-geometry motion when enabled. Generated
source buffers are reused in every compared mode; source generation is included in
the appropriate measured process. Native CPU sums GUI and viewer. Each displayed
stream has an owned copy in optimized embedded modes, with no unsafe shared-memory
aliasing. The GUI owns mutations and painting on one thread; this does not test
live acquisition/shared-ring attachment or a producer surviving a GUI stall.

The `--channels 1` cases test grayscale without RGB expansion. RGB comparisons
retain three channels even though test-pattern RGB components have equal values.
`--verify` checks native-rendered top/bottom bands and per-stream moving-bar positions
after measurement and saves PNGs. It also checks two pending texture submissions
coalesce to one latest upload and repeat redraws do not upload again. These captures
and assertions are outside CPU/timing measurement. Owned-buffer self-checks mutate
the source after acceptance and verify retained QImage content and stable buffer
addresses across updates. GL resources are released while their Qt context is current.

Raster age ends at **paint completion**, GL age at **Qt frameSwapped**, and native
cadence at **imshow submission**. These are different endpoints, not interchangeable
physical display latency measurements. None measures photodiode/scanout latency.
`paint_cpu_submission` is CPU wall time, not completed GPU duration. CPU percentages
refer to one logical core and retain Windows process-time sampling limitations.

## Method

Run outside the restricted execution environment after prior native startup/exit
failures, without inferring their cause. RGB order by round: native-follow/embedded/
raster/texture; texture/raster/embedded/native-follow; raster/native-follow/texture/
embedded. Each round runs stationary then moving, with2s warmup and8s measured time
in a fresh process. This is24 cases. Execution is serial to avoid overlapping probes;
normal desktop/development background activity is not isolated or controlled.

Representative command:

```powershell
.venv/Scripts/cephvr-python.exe -m cephvr.platform.windows.python_entry tools.benchmark_preview_presentation --mode texture --seconds 8 --moving --verify --output reports/runtime-evidence-2026-10-26/embedded-preview-comparison/optimized/rgb-0-texture-True.json
```

Each measured case has JSON, stdout/stderr and numeric exit-code files. Successful
embedded cases additionally retain pixel captures. Smoke files are separate from
the repeated matrix. Actual GL renderer must report AMD Radeon(TM) Graphics;
raster uses Qt's raster painter, with desktop composition outside the process metric.
The final `texture_uploads` counter includes post-measurement verification, so its
one additional coalesced batch must not be mistaken for steady-state overhead.

This measures display components, not end-to-end camera/renderer transfer or other
backend interference. Recording, scientific Tracking and calibrated projection are
not running as part of the test. Existing separate stimulus readback measurements
remain historical; no asynchronous readback or cross-adapter sharing is implemented.
No performance result automatically selects production embedding or changes20Hz policy.

Owner-requested additional replay `owner-recheck-165317` completes60.005s with exit0
and pixel/coalescing checks passing on AMD Radeon(TM) Graphics. Automatic host motion
is disabled for manual observation; input interactions were not instrumented.
CPU sample3.39% of one core cannot be compared directly with continuous automatic
resize cases. Owner feedback: playback smooth, bars in different positions, desktop
froze on manual resize. The bars intentionally use stream phase offsets (`i * 9`).
This is a failed manual-resize usability test despite normal process exit. Workload
isolation remains unconfirmed. Maximum update/swap gap is approximately395ms;
measured copy/draw callbacks remain below1ms. This gap is not a measurement of the
desktop freeze duration. Sources advance on the same GUI timer, so zero skipped
sequences does not rule out stalls.

Read-only Windows event investigation on2026-10-26: `latest-resize-events.json`
queries application crash/hang and system display/reset-related events since16:50;
both arrays and query errors are empty. `resize-application-events.json` retains
older failures, including Qt failures before this replay, which are not evidence
of a crash during this resize. No driver-reset/app-crash cause is established.
No additional live GPU preview was launched during this investigation; no fix is
claimed. Future diagnosis needs resize/event-loop timing and workload isolation.

## Results and owner replay

`summary.json` validates23 successful RGB results and5 grayscale results against
their exit0 receipts, actual GPU identity, pixel checks, upload counts and coalescing
checks. RGB native moving round1 and grayscale native moving fail with exit
-1073740791; the former reports WinError1400 on the GUI owner handle. No cause is
established. The initial matrix stops on that failure; remaining independent round2
and grayscale cases are then run with their individual exit receipts. No failed case
is silently retried, replaced or included in successful medians.

| RGB variant | Stationary CPU median/range | Moving CPU median/range |
| --- | --- | --- |
| Native-follow |7.42 /5.47–8.54|25.99 /25.04–26.95 (n=2)|
| Original embedded |5.86 /3.49–8.93|28.71 /27.59–39.64|
| Raster |10.67 /7.42–11.06|28.33 /26.98–28.73|
| Shared textures |2.33 /1.56–5.24|20.51 /19.14–24.46|

All numbers are percent of one logical CPU core; n=3 except the marked cell.
All optimized modes pass pixel/ownership checks and report zero skipped generated
sequences. Grayscale raster and texture each pass stationary/moving checks; single
samples do not support a repeated grayscale performance conclusion. GPU moving
medians improve about29% over the original prototype; no full-backend benefit is proven.

`verify_colors.py`/`.json` additionally exercise red/green/blue tiles and changed
colors with reused buffers. Mutating source arrays after submission does not change
the accepted image; updated submissions produce the new colors without stale-image
caching. Both raster and texture pass; repeated GL capture adds no texture uploads.

Owner requested a replay after the first subjective question. `owner-replay-raster`
and `owner-replay-texture` each complete20s plus warmup with exit0 and pixel checks.
Owner says it felt smoother but the computer felt laggy, possibly due to this and
another chat's work. Asked after both windows closed, owner reports **Back to normal**.
Do not promote that feedback into system-wide smoothness acceptance or claim a
specific variant preference. Further preview runs were paused after that report.

Read-only load checks at about16:42 JST find no remaining benchmark process.
`after-preview-load.json` records a5.02s process CPU sample and three system/GPU
counter samples: two other Python workers near100% of one core each, total CPU
4.15–9.41%, available memory38,999–39,086MiB, peak listed individual GPU-engine
sample4.27%. NVIDIA query at the preceding snapshot reports both GPUs at0% utilization.
`after-preview-processes.json` identifies generic execnet-style Python workers; their
parent ancestry was already absent when queried, so exact worker attribution is
unconfirmed. The other repository chat, **Clean and review repository**, was active
and reporting GUI validation. No messages/actions were sent to that chat and no other
process was stopped. Low after-test utilization does not exclude transient stalls
during previews or establish that other work caused the lag. Repeat only with GUI
workloads serialized before making a production or full-load claim.

Ruff check/format, compilation and backend boundaries760/zero pass. Existing backend
size warnings concern unchanged source. Source hashes/snapshots, exit receipts and
pixel verification bind the experiment; no scientific/device/production test run.
