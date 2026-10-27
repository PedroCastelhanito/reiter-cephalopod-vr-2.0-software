# Sparse-noise recipe preparation

Authority: [V04](../../docs/architecture/visual_stimulus.md#v04),
[V14/V15](../../docs/architecture/visual_stimulus.md#v14),
[V13](../../docs/architecture/visual_stimulus.md#v13).

The backend prepares a recipe into an ordinary format-2 image program and compact
PNG grid assets before runtime Setup. There is no render-loop random generation.
This is not a CephVR1 static texture-design JSON: use the preparation API/CLI below,
then the existing program loader. No new GUI recipe picker is added.

## Recipe fields

Use [the schema](sparse-noise-recipe.schema.json) and
[example](examples/sparse-noise.json). All fields are required; unknown fields fail.
Example values are illustrative, not rig defaults.

| Field | Meaning |
| --- | --- |
| `format_version`, `kind` | `1`, `"sparse_noise"` |
| `seed` | Integer 0 through 18446744073709551615; preserve without floating-point conversion. |
| `surfaces` | Distinct physical screen names: `front`, `left`, `right`, `bottom`; each needs an active output mapping. |
| `square_size_mm` | Positive physical cell side length. |
| `active_density` | Fraction of grid cells active per pattern, from 0 to 1. |
| `background_linear` | Linear RGB brightness, 0 to 1, equal in all three channels. |
| `pattern_count` | Positive number of successive patterns. |
| `pattern_duration.seconds` | Positive decimal string, whole-nanosecond precision. Total must meet E05's 60-second minimum and int64 nanosecond bound. |

Columns/rows are the floors of calibrated screen width/height divided by square
size. The complete-cell field is centered with background-only residual margins;
there is no field repetition, angular sizing, partial edge square or stretching
to consume residual space. A square too large to fit fails preparation.
For N cells, select `floor(active_density * N + 0.5)` distinct cells uniformly
without replacement. Reject positive density rounding to zero; explicit zero is
background only. Active cells independently choose black (linear 0) or white
(linear 1) with equal probability; adjacency is allowed and polarity counts need
not balance. Retain count and grid dimensions; effective density is count/N.

One RGBA texel represents one cell: active texels are opaque black/white, inactive
ones transparent over the exact scene background. Fixed millimetre image layers
use nearest sampling and the existing calibrated projection/photometric pipeline.
Unselected outputs receive the background. Screens share epoch timing, not a claim
of simultaneous optical refresh. Regenerate when geometry changes; playback does
not reinterpret the source recipe.

## Reproducibility and retained outputs

Generator `cephvr-sparse-noise-python-sample-v1` hashes ASCII generator identity,
decimal seed, stable screen name and zero-based decimal pattern index separated
by newlines, without a trailing newline. The SHA-256 digest, read as a big-endian
integer, seeds a local Python `random.Random`; `sample(range(N), K)` selects cells,
then `getrandbits(1)` selects polarities in sample order. Bytes are row-major from
top-left. Global RNG state is unused. Reordering/removing other screens or extending
the sequence preserves existing patterns. Independent streams may produce repeats.

Keep the whole generated bundle. `provenance.json` retains recipe/seed, generator
and Python versions, display snapshot, resolved grids, pixel/file hashes and the
program hash. PNGs and the expanded program are authoritative. Regeneration needs
matching recipe, geometry and generator/Python implementation; cross-version
Python sampling compatibility is not assumed. Runtime E13/V13 retains its usual
resolved plan and actual presentation evidence; external bundle provenance is not
automatically copied into experiment output. A seed alone is not a replay archive.

## API and command

From the repository root with its Python environment:

```powershell
.venv/Scripts/python.exe tools/prepare_sparse_noise.py --recipe sparse-noise.json --display display-profile.json --output assets/sparse-noise-run
```

The display input is canonical backend DisplayProfile JSON, not GUI calibration
draft JSON. Optional `--config` selects the backend TOML for existing resource
limits. Output must be a new directory; load its `program.json` and use that
directory as asset root. Errors/cancellation may leave an incomplete directory;
the playable program is published last. Normal runtime Setup is still required.

Python: `prepare_sparse_noise(recipe, display, destination, *, max_cells,
max_patterns, max_document_bytes, check=...)` in
`cephvr.visual_stimulus.resources.sparse_noise`; parse recipes with
`parse_sparse_noise_json(source, max_bytes=...)`. The optional check callback may
raise for cancellation/expiry. The CLI derives a per-grid ceiling from the existing
CPU limit at 192 bytes/cell, and uses existing epoch/document limits. Conservative
4096 bytes per screen-pattern document admission precedes expansion. Normal Setup
still admits actual CPU/GPU/plan budgets and protects all sources.

Playback retains existing bounded image residency, original clocks, readiness
holds and requested/actual asset evidence. No new missed-onset policy or timing
guarantee is introduced. Physical size, calibration, margins, optical onsets and
combined-load acceptance belong to the [rig checklist](../../reports/rig-verification.md).
