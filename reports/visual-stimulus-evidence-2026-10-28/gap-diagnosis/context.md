# Sparse-noise gap investigation — 2026-10-28

Source: e4dd8f2694aa075380fe6711a884fe5894763c6f plus the retained writable
JOB/CREDIT buffer repair and owning native regression. Windows rig; Python 3.11.15.
V04/V10/V20 apply; calibration, all-output VSync, recording and helper lookahead
settings are unchanged. No cameras or Tracking in these probes.

The previous `rig-tests/sparse-fixed-run` frame evidence splits startup stalls
mainly into swap/completion waits. At group2201, 152.93ms elapses between software
evaluation and the first swap entry, yielding the next166.708ms evaluation interval.
This evidence alone cannot distinguish texture upload, draw, scheduling or driver
work. All800 hashes match and every selection is current; generator starvation
does not explain the observed event. The older blank-scene276.482ms startup event
is separately documented in `reports/runtime.md`; these symptoms are not unique
evidence against sparse generation.

`trace_stages.py` temporarily wraps stage/GL calls and GC with buffered wall/CPU
timing. A three-line hook in worker/native.py loaded it at driver assembly. Only
spans >=0.5ms are retained (all GC callbacks retained); rows are nested and cannot
be added. Dumps occur at sparse finish/exit, outside playback. Windows thread CPU
time is coarse. The hook was removed before the subsequent uninstrumented restart;
no permanent instrumentation or timing-policy change was made.

Instrumented run command (repository Python):

```
reports/visual-stimulus-evidence-2026-10-28/rig-tests/native_sparse.py --execute --expected-controller-generation 1b6a48fb-1752-450e-b05c-80297dca0ab7 --output reports/visual-stimulus-evidence-2026-10-28/gap-diagnosis/baseline-traced
```

`trace-33436-2.json` and `stage-summary.json`: helper prepare916.718ms,
prefill744.964ms before Ready; max upload0.660ms, selection1.767ms, GC1.289ms,
render9.803ms, swap23.521ms and finish9.950ms. Sixty seconds completes with3599
decoded/count-matching frames,800 matching hashes, no holds; evaluation max34.269ms,
mean59.975Hz. Large historical gaps do not recur, so this is not a causal repair.

Lifecycle notes: the first requested relaunch overlapped old launcher cleanup and
waited at its replacement prompt. A separately started normal app generation was
already running; only our redundant waiting launcher child was cancelled. The
instrumented generation was then shut down normally; `traced-exit.json` confirms
all owned processes absent before the clean launch. This corrects LOG's earlier
wording suggesting the first relaunch waited for completed exit evidence.

`native_sparse_extended.py` derives from the guarded60s harness, retaining exact
generation/control/configuration/cleanup checks and fresh-output requirement.
It permits180s (600 patterns per screen). Its first extended attempt retained the
blank fixture's60s epoch by mistake: the exact-duration assertion aborted promptly,
confirmed cleanup and restored all11 saved files/runtime configuration. Evidence
is in `clean-180s`; this is a harness failure. The corrected fixture sets both epoch
duration and pattern count; dry-run authoritative validators pass. The corrected
execution is in `clean-180s-repeat` on generation87f0d50c-e748-4b56-b4ab-8c0232da092b.

Analysis commands: `rig-tests/assess.py RUN` regenerates first-display pattern
hashes and measures software evaluation/return intervals; `tools/encoding_probe.py
collect --directory RUN/recordings --output RUN/encoding-summary.json` fully decodes
and compares recording accounting. These are software/native checks, not optical
flip/onset measurements or combined-load acceptance.

Corrected180s outcome:10,799 video frames fully decoded and matched final accounting;
2,400 hashes regenerated and matched;43,196 selections current, no holds, recording
drops, duplicates or unresolved attempts. Mean59.993Hz, median16.667ms, max33.466ms
evaluation interval, max33.758ms per-output return interval. Exact trial cutoff and
cleanup pass. `final-snapshot.json` is idle Configuration, cleanup confirmed, and
its runtime configuration equals `before.json`; all11 file checks pass. The app
remains open. Tracing hook has no remaining diff in worker/native.py.

Collector invocation with launcher stderr initially exits1 because that file has
no recording_metrics; videos still decode correctly. Retained that result as
`encoding-missing-diagnostics.json`; recording-only collection exits0. Five native
sparse lifecycle cases pass (`native-regression.xml`); scoped Ruff/format, backend
boundaries791/zero violations and whitespace pass. No new production timing patch:
the historical large delays remain unreproduced and unproven fixed. Saved settings,
calibration and pacing were not changed. Concurrent GUI/generation-timing chats
were active; these runs are not a controlled OS-idle benchmark.
