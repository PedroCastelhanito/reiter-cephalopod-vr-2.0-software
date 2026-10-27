# Raster-independent physical texture fields — 2026-10-27

Source: HEAD `c7881b1f87a5d294383d310ebcb92630cd825099` plus a dirty, concurrently
edited working tree. [Final source hashes](source-snapshot.json) identify the scoped
source snapshot. This is local implementation evidence, not physical rig acceptance.
Assessment: [current backend report](../../visual_stimulus.md#texture-independent-extent--2026-10-27).
Authority: [V04/V15](../../../docs/architecture/visual_stimulus.md#v04),
[G01](../../../docs/architecture/gui.md#g01),
[format/consumer binding](../../../contracts/visual_stimulus/stimulus-authoring.md).

Final commands are embedded verbatim at the start of each raw result:

| Evidence | Outcome | Scope |
| --- | --- | --- |
| [Affected backend tests](affected-tests.txt) |272 pass,3 subtests pass,44 deselect | Resource/render/configuration owners, legacy compatibility, physical field validation |
| [Authenticated tests](authenticated-tests.txt) |20 pass | Actual lightweight loopback transport/controller services, with narrow hardware adapters |
| [Authoring](authoring-final.txt) |95 pass,6 deselect | Saved byte independence, all procedural families, bar dimensions, seeds, arena baking and cache preservation |
| [Planning GUI](gui-field-tests.txt) |31 pass,1024 deselect | Current selected field/preview/physical speed/picker behaviors, including all four field import targets |
| [Native GL](native-final.txt) |39 pass,176 deselect | Field shader/CPU agreement, all four screen identities, unequal X/Y physical scales, both loading paths, cropped fields, phase conversion, source-image regression and glTF preview orientation |
| [Static checks](static-checks.txt) |All pass | Ruff/check/format26 files; Windows-target mypy21 sources;785 modules, zero boundary violations |
| [Whitespace](whitespace.txt) |Exit0 | Whole working-tree `git diff --check` |

[Structured final results](final-results.json) retain return codes and elapsed times.
[GL context identity](gl-context.json) identifies the local offscreen context; its
existence and these generated-frame checks establish neither projector behavior nor
full-load throughput. GPU cases sample up to240 ×160mm, across the former100mm tile
boundaries. Per-mapping field extent/phase evidence follows the actual shader upload.
CPU cases additionally check exact10mm period/45° invariance, stable overlapping
seeded views, statistical dot density/noise fraction and unsigned64-bit seeds.

Earlier broad evidence is retained separately: [backend](backend-tests.txt) has602
passes and two failures (Grating asset-list expectation during concurrent media-family
migration; native display cleanup returning closed=False); [GUI](gui-tests.txt) has35
passes/eight Grating control-layout failures during that migration. [Earlier native](native-tests.txt)
and [authoring](authoring-tests.txt) selections pass. [Earlier result summary](results.json).
These failures are not relabeled passes. The monitor subsequently identified the
display failure's missing fake `hide_output_shell_entry` boundary and owns its later
fixture recheck; this snapshot retains the original result.

Earlier tool-output-only attempts (no raw stdout file retained) encountered:

- Superseded finite-tile/square-raster assertions, replaced with the accepted field
  behavior in the existing test modules. New native fake settings were brought into
  agreement with concurrently added model fields without weakening assertions.
- Demo asset generation rejecting a repository-local pytest temp root; retained
  runs use the authorized external visualization root named in each command.
- A combined authoring/GUI suite access violation in theme fixture setup. Separate
  final runs pass; a combined-suite green result is not claimed.
- Windows asyncio blocking in `socket.socketpair()` while creating its event loop.
  A bounded20-second diagnostic identified that setup stack. Permitted loopback
  reruns pass with the same assertions; initial hung runs were interrupted.
- Scoped import/format/type findings corrected before final checks. Windows default
  text encoding on the first tracking edit was corrected to explicit UTF-8.

ARCH-002: field mathematics and shader generation are focused modules; the existing
large scene-resource/preparation files retain cohesive allocation/dispatch ownership.
No dependency, process, frame-time Python generator or per-fix test module was added.
The managed app was not restarted. Physical dimensions, optics, display transitions
and full-workload timing remain in the [single rig checklist](../../rig-verification.md#stimulus-authoring).
