# Sparse-noise recipe preparation

Authority: [V04](../../docs/architecture/visual_stimulus.md#v04),
[V14/V15](../../docs/architecture/visual_stimulus.md#v14),
[V13](../../docs/architecture/visual_stimulus.md#v13).

The backend prepares a recipe into an ordinary format-2 image program and compact
PNG grid assets before runtime Setup. There is no render-loop random generation.
This is not a CephVR1 static texture-design JSON: use the GUI picker or preparation
API/CLI below, then the existing program loader.

## Inline epoch authoring

Choose Media presentation → Sparse noise in a projector/layer row. Set square size
(mm), minimum center distance (mm), activation probability, background (linear),
explicit seed, pattern count and duration (seconds) directly in the epoch editor.
Apply sparse noise prepares a unique internal image bundle off the GUI thread using
configured geometry and the existing generator. No external recipe asset is required.
The protocol retains the appearance, seed, timing and generated resource identities.
Other layers and the epoch duration stay unchanged. Unapplied edits and missing
preparation block Save/preview; authority, Assets, enabled-screen or geometry changes
cancel/discard late results. Existing files are never overwritten; uncommitted bundles
may remain. Reapply after changing physical geometry.

Execution indexes the compact image sequence at epoch-local time, restarting each
occurrence, truncating at the epoch end and holding its final pattern at exhaustion.
Generated images use the usual protected source admission, byte budgets, residency,
nearest sampling and actual-image evidence. All sequence members form the admitted
working set. Each layer composites its own linear background behind inactive cells;
residual grid margins expose underlying content. Short sequences are permitted inside
an E05-valid trial. Standalone recipe trials retain their original minimum duration.

## Legacy recipe import

The existing recipe/CLI preparation and canonical program import remain supported.
The retained GUI trial-import helper independently selects per-screen external
appearance recipes, preserves seeds/provenance, and uses common count/duration with
matching backgrounds. It is not a Protocol type. It appends a prepared trial without
replacing existing trials. External recipe changes require explicit regeneration.
The per-layer preparation uses an internal `cephvr-sparse-noise-layer-v1` sequence
manifest, published as `sequence.json`, rather than advertising a short playable trial.

## Recipe fields

Use [the schema](sparse-noise-recipe.schema.json) and
[example](examples/sparse-noise.json). All fields are required; unknown fields fail.
Example values are illustrative, not rig defaults.

| Field | Meaning |
| --- | --- |
| `format_version`, `kind` | `2`, `"sparse_noise"` |
| `seed` | Integer 0 through 18446744073709551615; preserve without floating-point conversion. |
| `surfaces` | Distinct physical screen names: `front`, `left`, `right`, `bottom`; each needs an active output mapping. |
| `square_size_mm` | Positive physical cell side length. |
| `min_active_cell_distance_mm` | Nonnegative minimum center-to-center separation between eligible cells, in mm. |
| `active_probability` | Independent probability of activating each eligible cell, from 0 to 1. |
| `background_linear` | Linear RGB brightness, 0 to 1, equal in all three channels. |
| `pattern_count` | Positive number of successive patterns. |
| `pattern_duration.seconds` | Positive decimal string, whole-nanosecond precision. Total must meet E05's 60-second minimum and int64 nanosecond bound. |

Columns/rows are the floors of calibrated screen width/height divided by square
size. The complete-cell field is centered with background-only residual margins;
there is no field repetition, angular sizing, partial edge square or stretching
to consume residual space. A square too large to fit fails preparation.
For each pattern, shuffle all grid cells and greedily accept a cell only if its
center is at least `min_active_cell_distance_mm` from every previously accepted
center. This regenerates a maximal eligible layout for every pattern; it does not
guarantee maximum packing, uniform spatial coverage or distinct consecutive layouts.
Zero distance allows every cell. Independently activate each eligible cell with
`active_probability`: zero produces background only; one activates the entire
eligible layout. Active counts vary, with expected count probability times the
eligible count. Active cells independently choose black or white with equal
probability. Inactive eligible cells remain background; they are not backfilled.

Version-1 density recipes must be explicitly updated to version 2 with both new
fields; density has no equivalent distance/probability conversion. Already generated
image programs remain usable without interpreting or migrating their source recipes.

One RGBA texel represents one cell: active texels are opaque black/white, inactive
ones transparent over the exact scene background. Fixed millimetre image layers
use nearest sampling and the existing calibrated projection/photometric pipeline.
Unselected outputs receive the background. Screens share epoch timing, not a claim
of simultaneous optical refresh. Regenerate when geometry changes; playback does
not reinterpret the source recipe.

## Reproducibility and retained outputs

Generator `cephvr-sparse-noise-spaced-bernoulli-v2` hashes ASCII generator identity,
decimal seed, stable screen name, zero-based decimal pattern index and stream name
(`layout`, `activation`, `polarity`), separated by newlines without a trailing newline.
Each SHA-256 digest, read as a big-endian integer, seeds a local Python
`random.Random`. Layout uses `shuffle`; each eligible cell consumes one activation
`random()` and one polarity `getrandbits(1)`, including inactive cells. Changing
probability preserves the eligible layout and the polarity of shared active cells.
Bytes are row-major from top-left. Global RNG state is unused. Reordering/removing
other screens or extending the sequence preserves existing patterns. Independent
streams may produce repeats.

Keep the whole generated bundle. `provenance.json` retains recipe/seed, generator
and Python versions, display snapshot, resolved grids, actual active counts per pattern, pixel/file hashes and the
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
CPU limit at 512 bytes/cell, and uses existing epoch/document limits. Conservative
4096 bytes per screen-pattern document admission precedes expansion. Normal Setup
still admits actual CPU/GPU/plan budgets and protects all sources.

Playback retains existing bounded image residency, original clocks, readiness
holds and requested/actual asset evidence. No new missed-onset policy or timing
guarantee is introduced. Physical size, calibration, margins, optical onsets and
combined-load acceptance belong to the [rig checklist](../../reports/rig-verification.md).
