"""Replace current combined-work assessment without changing other chats' sections."""
from pathlib import Path

def replace_section(path,start,end,replacement):
    target=Path(path)
    text=target.read_text(encoding='utf-8')
    begin=text.index(start)
    finish=text.index(end,begin)
    target.write_text(text[:begin]+replacement+'\n\n'+text[finish:],encoding='utf-8')

link='[Dated raw evidence, verification and limits](runtime-evidence-2026-10-13/combined-camera-stimulus/context.json)'
runtime='''Oct13 combined recording/reset repair under [SYS-002](../architecture.md#sys-002),
[A07](../docs/architecture/acquisition.md#a07), [V12](../docs/architecture/visual_stimulus.md#v12)
and [E05](../docs/architecture/experiment.md#e05)/[E08](../docs/architecture/system-contracts.md#e08)/
[E11](../docs/architecture/experiment.md#e11) is verified in two
consecutive normal60s sessions in generation449c9382-c65d-4ed8-ae4e-393490ce9085.
Actual3602/3601 render groups give60.0333/60.0167 groups/s while Behavior30Hz and
Tracking60Hz record. Four samples per trial identify renderer23560 on RTX5060Ti/GPU0
and both camera plus review NVENC encoders on RTX2080Ti/GPU1. All six saved videos
externally count and fully CPU-decode; trial/output/metadata closure and reservation
release pass. Both NewSession/configuration restores succeed without shutdown.
The normal GUI is Configuration/no prompts, original full settings equal and cameras
released. All camera drain allowances remain the owner-selected125ms; Eye is disabled.

Reset repair acknowledges final coalesced warnings before Finished under A07
revision61, preserves exact pulse outcome retry identity, and retains canceled trial
health scope until cleanup. Shared absolute-clock waits correct early Windows async
wakes: a rejected lifecycle trace proves internal Stop3.38ms before normal end,
which the MCU channel correctly rejected. Preparation cleanup receipts now retire
only when all local source/consumer ownership has closed before a new preparation;
old resource-generation keys cannot enter the new cleanup catalogue. Strict evidence
checks and original deadlines remain intact.

The rendering repair moves native pixel work outside admission locking, uses bounded
native row conversion/completed PBO mapping and actual-context no-op checks, and
copies encoder input privately with a GIL-releasing native copy. No new dependency,
process, policy option or scientific/PFS/encoder tuning. CPU budget now covers retained
padding, readback/pipe copies and half-frame row scratch.1123 regressions pass,
3 skip/6 deselect; native Windows pipe14 pass. Ruff check/format, Win32 mypy427
sources, boundaries667/zero violations and whitespace pass. Existing large owners
remain cohesive: small context callbacks and preparation receipt/budget helpers do
not add whole-runtime references or a separable feature responsibility.

This verifies nominal60fps host cadence, not uniform16.67ms/optical timing. Repeat
median16.79ms, p9927.56ms/max37.88ms; camera queues drop6/19 frames and review captures
1176 real samples with2367 capacity drops,58 same-slot omissions and2424 identified
duplicates in3600 encoded frames. Full accounting remains explicit; recording is
not zero-loss. Eye/locomotion Tracking/paired/optical/electrical acceptance and the
dedicated Save On-to-Off verification remain open. Earlier failed attempts/recovery,
removed experiments and baseline39.47fps are retained in dated evidence.'''
replace_section('reports/runtime.md','Oct13 owner selects125ms','Oct13 owner-authorized throughput implementation',runtime+'\n'+link)

visual='''Oct13 owner-authorized combined rendering/reset repair verifies two consecutive
normal60s Behavior/Tracking recordings at3602/3601 actual render groups
(60.0333/60.0167 groups/s), improving the combined baseline39.47/s. Renderer GPU0
and both camera/review NVENC GPU1 are confirmed by exact live PIDs/UUIDs in four
samples per trial. All six videos externally count/fully decode; both sessions close,
reset and restore original settings in the same live generation.

Under [V12](../docs/architecture/visual_stimulus.md#v12)/
[E13](../docs/architecture/visual_stimulus.md#e13), native row conversion, completed
PBO mapping/private copy, actual-context no-op checks, normalization outside admission
lock and private native pipe copying remove recording contention. Original ownership,
slot bounds, precision and encoder settings remain. Preparation release receipts are
retained for cleanup retry until all source/consumer ownership closes, then retired at
new preparation; this fixes the reproduced On-to-On unknown-resource shutdown.
The owning CPU budget includes padding, readback/pipe copies and half-frame scratch.
ARCH-002 keeps the existing cohesive native/preparation owners with small helpers,
no new dependency/process or whole-runtime reference.1123 regressions pass/3 skip/
6 deselect, native pipe14 pass, Ruff/static mypy427/boundaries667 pass.

Nominal60fps is not uniform frame timing or optical proof: repeat p9927.56ms,
max37.88ms. Review fidelity remains limited:1176 real samples/2367 capacity drops/
58 same-slot omissions and2424 explicit duplicates in3600 encoded frames. Dedicated
Save On-to-Off native verification, Eye/locomotion Tracking and paired/optical
acceptance remain open. Original GUI/settings are restored. Historical stimulus-only
measurements below remain distinct from this combined result.'''
replace_section('reports/visual_stimulus.md','Oct13 subsequent real','Oct13 `stimulus-throughput-repair`',visual+'\n'+link)

acquisition='''Oct13 owner-selected125ms drain margins remain applied to all camera roles
under [A10](../docs/architecture/acquisition.md#a10); Eye is disabled/unmeasured.
Two consecutive final normal60s Behavior30Hz/Tracking60Hz plus stimulus recordings
close with1797/3596 valid received frames each, complete post-cutoff accounting/two
excluded frames per camera and SDK failed/missed counters0. All four camera videos
externally count1800/3600 and fully decode. Camera queues drop9/28 in the first run,
6/19 in the repeat; identified video duplicates remain, so no zero-loss claim.
Live PID/UUID/NVENC evidence proves camera encoding RTX2080Ti/GPU1 and renderer
RTX5060Ti/GPU0. Renderer reaches60.0333/60.0167 real groups/s.

[A07](../docs/architecture/acquisition.md#a07) revision61 orders final warning
acknowledgement before Finished. Exact terminal MCU retries compare the MCU outcome
after scope/connection checks, independent of fresh forwarding command ID. Worker
health retains canceled scheduled trial scope until proven session cleanup. Shared
absolute-clock waits correct early async ON/OFF/end dispatch while preserving E05/
E08/E11 boundaries and strict evidence validation. Both final NewSession/restore
operations succeed in the same generation, no shutdown. Original settings and released
cameras are verified. No camera/PFS/encoder/firmware tuning;125ms is an adopted
engineering allowance, not a guaranteed worst-case bound.

1123 affected-owner regressions pass/3 skip/6 deselect; native pipe14 pass; Ruff,
Win32 mypy427 files and boundaries667/zero violations pass. Source/context records
retain initial fixture/sandbox failures, exact failed-generation administrative recovery
and all removed experiments. Remaining review/camera recording drops and broader
Eye/Tracking/paired/optical acceptance stay explicit.'''
target=Path('reports/acquisition.md');body=target.read_text(encoding='utf-8');end=body.index('\n\n',body.index('[external video/accounting verification]'))
target.write_text(body[:body.index('Oct13 owner adopts125ms')]+acquisition+'\n'+link+'\n'+body[end:],encoding='utf-8')

rig='''Oct13 final combined repair verifies two consecutive normal60s Behavior/Tracking
recordings at60.0333/60.0167 actual render groups/s. Renderer RTX5060Ti/GPU0 and
camera/review NVENC RTX2080Ti/GPU1 are proven with exact live PID/UUID samples;
all six videos externally count and fully decode. Trial/output/metadata closure,
two NewSession/config restores, original settings and released cameras pass in one
generation, without shutdown. Owner-selected125ms drain margins remain all roles.
This closes the reproduced warning/boundary/On-to-On receipt-reuse failures within
this scope. Nominal cadence is not uniform16.67ms or optical proof (repeat p9927.56ms,
max37.88ms). Repeat camera queues drop6/19 and review has2367 capacity drops/
2424 identified duplicates: zero-loss recording remains open. Eye/locomotion
Tracking/paired/optical/electrical acceptance and dedicated Save On-to-Off native
verification remain outstanding.'''
replace_section('reports/rig-verification.md','Oct13 latest owner-selected','Oct13 later throughput repair',rig+'\n'+link)
print('Updated four owning reports; preserved unrelated sections.')
