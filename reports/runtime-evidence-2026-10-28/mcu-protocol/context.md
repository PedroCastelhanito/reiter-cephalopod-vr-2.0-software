# Protocol validation / watchdog investigation — 2026-10-28

Base revision e4dd8f2694aa075380fe6711a884fe5894763c6f plus existing dirty tree.
Owner supplied C:/Users/ReiterU_PC/Desktop/Alsu/protocols. No supplied files edited.

Methods and retained outputs:

- `probe.py`: validates all three GUI protocol envelopes, checks declared asset
  paths and takes one authenticated read-only controller snapshot. Approved native
  execution permits temporary client credentials/loopback; client removed finally.
  [Inventory/hashes](protocol-inventory.json), [snapshot](baseline-snapshot.json).
  All valid; no missing declared assets. Live texture program exactly matches
  texture-presentation-1hr_protocol.json. Controller generation
  9008f087-060f-44fd-8a7a-748b8651395a is Configuration, cleanup_confirmed=true,
  retaining a failed Setup. No control takeover, device commands or restart.
- `validate_workload.py`: builds offline candidate configurations from that
  snapshot and each supplied protocol, executes the actual Visual Stimulus
  configuration validator. A same-process thread wakes with Event.wait(1ms);
  reported gaps include Windows scheduling/GIL, not just validator work. GC
  callbacks measure collection duration without disabling or changing GC policy.
  [Before](gc-probe-output.txt): texture validation3837.543ms, witness480.973ms,
  generation2 collection454.075ms. First uninstrumented-GC run showed3796.422ms /
  452.358ms. cProfile run additionally perturbed duration6367.187ms and witness
  483.684ms; binary profile retained. Other protocols had approximately33–54ms
  witness maxima. These are local workload measurements, not native serial timing.
- [After](gc-probe-after.txt): streamed validation texture1871.864ms,
  witness32.503ms, largest observed GC0.146ms; all three candidates remain valid.
  [Structured latest results](workload-validation.json).
- Repository Python3.11 command:
  `python -m pytest tests/visual_stimulus/test_compilation.py tests/visual_stimulus/test_configuration.py -q -m "not windows and not rig" --basetemp=.tmp-mcu-stream-validation-verified`:
  [47 passed and5 subtests](pytest.txt). Regression checks identical seeded
  materialized/streamed visits and bounded live occurrence retention in semantic
  validation. Initial retention assertion allowed2, but iterator/zip consumers can
  retain3 transient occurrences; corrected bound3 passes120 occurrences. Initial
  formatting check failed; corrected. Scoped Ruff/format on compile.py,
  expansion.py and owning test pass, Win32 mypy on both source files passes,
  boundaries792 modules/zero violations, whitespace passes.

Finding: whole expanded settings retention during pure controller validation
produces a GC pause longer than the200ms MCU acknowledgement budget. Streaming
removes that measured pause without new processes, GC policy, deadline relaxation,
retries or changed random/ordering/duration semantics. This is a concrete local
starvation mechanism; original native serial failures were not concurrently traced,
so it does not rule out additional driver/scheduler stalls.

Live application not restarted and Setup/Cancel not rerun; all hardware/optical,
serial and combined-workload acceptance remains pending. Input existence does not
establish media decode/calibration/throughput. Headless fixture/native state are not
interchanged; offline candidates never reach the running controller.
