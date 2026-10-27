# Sparse-noise generation

Authority: [V04](../../docs/architecture/visual_stimulus.md#v04),
[V14/V15](../../docs/architecture/visual_stimulus.md#v14),
[V13](../../docs/architecture/visual_stimulus.md#v13).

Sparse noise is a program layer generated during playback by a contained helper,
never inside the render loop. There are no image assets or prepared bundles; the
pre-generated PNG path was removed on 2026-10-28, and programs containing image-form
sparse sequences no longer load.

## Runtime generation (`sparse_noise` layer)

Choose Media presentation → Sparse noise in a projector/layer row and set square size
(mm), minimum center distance (mm), activation probability, background (linear),
explicit seed, pattern count and duration (seconds) in the epoch editor. Edits apply
directly to the program's `sparse_noise` layer (`appearance`, `pattern_count`,
`pattern_duration`); there are no image assets, prepared bundle or Apply step.
Compilation fixes the layer's width/height to the grid resolved from the active
display, so geometry changes need no re-authoring.

Each prepared trial containing sparse layers launches one contained generator helper
(`python -m cephvr.visual_stimulus.sparse_noise_helper` through the managed entry,
role `visual_stimulus_sparse_noise`) at PrepareTrial. Both processes derive the same
request order from the prepared trial: every shown pattern of every layer occurrence,
sorted by trial-relative due time, then layer order.

Pipe protocol (`resources/sparse_noise_wire.py`): stdin carries one `JOB <json>` line
(layers with recipe, resolved grid, epoch start, pattern duration and shown count),
then `CREDIT <n>` lines allowing requests with sequence < n; stdin EOF stops the
helper. stdout carries per request a 48-byte little-endian header (`SPN2`, u64
sequence, u32 length, 32-byte SHA-256 of the pattern's `pattern_rgba` bytes) and `columns × rows × 4` RGBA8 bytes, bottom row first, with
cells identical to `pattern_rgba` for the same seed and screen.

The renderer keeps 100 patterns (E14 `sparse_noise.lookahead_patterns`) ahead per
concurrently presented layer: the first window is resident before Ready and credit
grows as shown patterns retire. Textures are grid-sized RGBA8, reused from a bounded
pool, sampled nearest through the calibrated projection. A pattern not yet generated
holds the newest due resident pattern with `residency_hold` evidence; before the
occurrence's first pattern only the background shows, recorded as `background_hold`
with `image_index` null. The trial clock never waits. Helper failure or early exit
fails the trial. Evidence `State.images` records one selection per sparse layer:
`asset_id` and `requested_asset_id` are the instance ID, `requested_image_index` and
`image_index` the requested and actual zero-based pattern index within the current
epoch occurrence (`State.epoch_occurrence`). The first frame showing a pattern also
records `pattern_sha256`, the SHA-256 of `pattern_rgba` (top row first, before the GL
flip), and `pattern_generator`; repeated frames omit both.

## Appearance and recipe fields

A layer's `appearance` uses the [appearance schema](sparse-noise-appearance.schema.json).
The offline editor still accepts full version-2 recipe files
([schema](sparse-noise-recipe.schema.json), [example](examples/sparse-noise.json)) as
appearance input and ignores their timing and screens. All fields are required;
unknown fields fail. Example values are illustrative, not rig defaults.

| Field | Meaning |
| --- | --- |
| `format_version`, `kind` | `2`, `"sparse_noise"` |
| `seed` | Integer 0 through 18446744073709551615; preserve without floating-point conversion. |
| `surfaces` | Distinct physical screen names: `front`, `left`, `right`, `bottom`; each needs an active output mapping; Geometry-only callers must pass the active surface set to enforce this. |
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
center (integer cell offsets are compared with a 1e-9 tolerance on the squared cell
ratio, so exactly equal distances qualify despite float rounding). This regenerates a maximal eligible layout for every pattern; it does not
guarantee maximum packing, uniform spatial coverage or distinct consecutive layouts.
Zero distance allows every cell. Independently activate each eligible cell with
`active_probability`: zero produces background only; one activates the entire
eligible layout. Active counts vary, with expected count probability times the
eligible count. Active cells independently choose black or white with equal
probability. Inactive eligible cells remain background; they are not backfilled.

Version-1 density recipes must be explicitly updated to version 2 with both new
fields; density has no equivalent distance/probability conversion.

One RGBA texel represents one cell: active texels are opaque black/white, inactive
ones transparent over the exact scene background. Fixed millimetre image layers
use nearest sampling and the existing calibrated projection/photometric pipeline.
Unselected outputs receive the background. Screens share epoch timing, not a claim
of simultaneous optical refresh.

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

Nothing is written to disk during generation. Regeneration needs the same appearance,
screen, resolved grid (from the trial's logged display profile), generator id and
Python version; cross-version Python sampling compatibility is not assumed. The
experiment output retains the resolved plan and per-frame actual pattern indices
(E13/V13); a seed alone is not a replay archive. Physical size, calibration, margins,
optical onsets and combined-load acceptance belong to the
[rig checklist](../../reports/rig-verification.md).
