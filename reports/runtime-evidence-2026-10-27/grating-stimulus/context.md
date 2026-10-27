# Grating stimulus validation — 2026-10-27

Source revision c7881b1f87a5d294383d310ebcb92630cd825099 plus a dirty tree with
concurrent physical-field, protocol-media-families and photodiode changes.
[Commands, outcomes and source hashes](checks.json); [source scope](source-files.txt).
GUI commands use QT_QPA_PLATFORM=offscreen and external writable pytest basetemp
under C:/Users/ReiterU_PC/.codex/visualizations/2026/10/27/01a17c38-cacd-76c2-931f-b8e66467fa53.

Final behavioral evidence: [69 GUI passes](gui-verified.txt) and
[156 backend passes plus3 subtests](backend-final.txt). Eight focused Grating cases
cover all four screens and legacy/current recipes; four resource cases cover protected
eager/deferred preparation. Tests verify three controls, retained stationary angle,
12 compact repetitions with matching absolute rotation assignments and drift,
preview boundary application, save/reload, ignored source angle without byte changes,
per-candidate Asset periods, profile/family rejection and invalid motion declarations.

ARCH-002: the type is a texture specialization, not a new worker/family renderer.
Focused grating motion/validation and recipe interpretation owners reuse existing
Cartesian edits, rotation assignments, variation sampler, protected source handling
and resource residency. Recipe-profile classification is shared by GUI and backend.
No new dependency/process. Remaining size advisories belong to existing model
reference validation, parameter-form assembly and resource preparation; no runtime
back-reference or duplicated coordinator owner was introduced. Tests extend the
owning Dashboard, compilation and resources modules.

Earlier attempts and limits:
- An initial patch had unmatched context and was corrected before mutation. A
  malformed import path was corrected before runtime validation. A repeated indexed
  union needed a narrowed local for mypy. Ruff corrected import ordering/formatting.
- The first resource assertion picked two same-colour columns; a full contrast/range
  assertion now checks the intended invariant. Both preparation paths pass.
- Concurrent media-family work removed the Looming selector and motion restrictions.
  The broader raw [GUI](gui.txt) and [backend](backend.txt) outputs preserve those
  obsolete expectation failures. Final commands explicitly exclude that unrelated
  migration's two backend cases and old reference-type selector cases; its active
  TODO remains independent.
- A later [GUI run](gui-final.txt) and [focused retry](grating-current.txt) exposed
  mojibake in the shared test file: runtime captions had U+00B0 while test constants
  contained U+00C2 U+00B0. Restored160 UTF-8 character sequences, preserving test
  logic and concurrent additions; the final69-case selection passes. This is not a
  renderer/scientific failure or a weakened assertion.
- Concurrent edits intermittently recreated schema drift and formatting/import
  changes. Canonical schemas were regenerated and final scoped checks rerun.
- [Boundaries](boundaries.txt):780 modules, zero violations at that check, with
  existing size advisories. Final static/schema/whitespace results follow below.

No managed GUI restart, actual projected grating, full-workload timing or rig
acceptance was performed. Use the single rig checklist for those remaining checks.

Final verification:8 Grating GUI cases ([raw](grating-final.txt)) and5 Grating
compiler/resource cases ([raw](grating-backend-final.txt)) pass on the later working
snapshot. Final Ruff/check/format33 files, Windows-target mypy30 sources,14-schema
check and git diff --check pass. One concurrent Sparse caption variable shadowed
the existing stimulus caption tuple; renaming that local fixes mypy without changing
behavior. Schema drift/import/line-ending changes were normalized and rechecked.
The six earlier raw failure files remain historical evidence, not current passes.
