# Offline stimulus authoring

Owners: [G01](../../docs/architecture/gui.md#g01),
[V04](../../docs/architecture/visual_stimulus.md#v04),
[V17/V18](../../docs/architecture/visual_stimulus.md#v18).

Run `.venv/Scripts/python.exe -m cephvr.generate_stimulus --asset-root PATH`,
optionally with `--geometry PATH` containing a saved rig calibration, a calibration's
`geometry` object or a canonical Geometry document. The main GUI's **Generate assets**
tab embeds the same editor, initialized once with the Assets root and current
validated geometry snapshot. Switching tabs preserves drafts;
closing the GUI prompts before discarding unsaved designs. Runtime-phase navigation
restrictions apply as for other non-Dashboard pages. Standalone invocation opens its
own window. Neither entry point starts controller, device, recorder or projector services.

Both hosts use the main GUI's cards, labeled fields, dropdowns and buttons.
Controls scroll independently beside the preview; narrow windows stack the columns
without rebuilding documents. Standalone reads the saved frontend appearance.
Preview pixels, arena meshes and compiled preview bytes stay in memory; no preview
file or temporary bundle is written. Only Save in the editor publishes a design
file. Save always opens Save As, suggesting the previous filename when available;
cancelling preserves the draft and saved files. Choosing an existing destination
uses the file dialog's overwrite confirmation. The preview has no footer caption or Cancel generation button, and routine
preview-progress/success messages are omitted. Errors remain visible; edits and
closure still cancel obsolete background work.

## Recipes and previews

The Textures workspace offers Grating with orientation instead of separate
horizontal/vertical bar choices, alongside the other texture families and sparse noise.
Procedural texture recipes describe appearance in physical units and retain their
seed. They contain no preview extent, projector selection, image-repeat dimensions
or fit-to-tile behavior. Their versioned executable representation must distinguish
them from legacy finite-raster recipes; removing legacy keys alone is insufficient.
The existing legacy JSON representation retains `cephvr_asset_type: texture_design`,
`kind: texture`, `pattern` and `params`, including physical tile dimensions and seeds.
Image `texture_path` is relative to the recipe directory, inside Assets. Sparse
noise uses the [appearance schema](sparse-noise-appearance.schema.json): version,
kind, seed, square size, minimum active cell distance, active probability and background. Duration, speed, pattern
count and projector assignment belong to Protocol. Legacy full recipes are
validated on Open, then reduced to appearance; Save/Export emits only appearance.
The preview screen/index selects an inspection view, not a saved schedule.
Save/Export emits the recipe;
select it through the existing protocol texture or sparse-noise picker.

The preview is a viewing window into the physical pattern, with no influence on
the saved recipe. Use the calibrated screen extent for screen inspection and a
preview-only sample extent otherwise. Grating period and orientation remain exact;
do not round cycles or alter angle to fit a window. Grating phase remains zero.
The same field interpretation is required during presentation: a preview-only
correction must not conceal runtime image-repeat seams. Seeded noise and random
dots follow this separation too. A seed defines a stable field: changing the
viewing window preserves features in the overlap. Dot density is an average per
physical area; visible counts can vary. Filtered-noise black fraction is statistical
across the field, never a per-window quantile that changes shared pixels. Existing
image files retain their finite pixels.

New files use `cephvr_asset_type: texture_field`, integer `format_version: 1`,
`kind: texture`, `pattern` and `params`. Unknown versions, raster/tile dimensions,
screen assignments and unsupported parameters are rejected by the runtime parser.
The existing JSON recipe transport profile carries both versioned fields and
legacy designs; content tags determine interpretation. Source files are protected
and fingerprinted unchanged. Preparation retains the validated field and a bounded
residency sentinel, never a pattern raster. Each output owns a shader compiled from
validated parameters before playback. Its fragment coordinates are centred local
millimetres, plus retained phase converted to millimetres; layer pose and the
calibrated surface/output mapping preserve independent X/Y scale. The physical
feature size never comes from the sentinel, viewport aspect ratio or tile periods.
Color endpoints retain the recipe RGB8 channel interpretation before float32
working composition. Physical fields require physical-surface texture placement and linear colors;
unsupported placements/interpretations fail preparation. Requested/actual asset
selection, shader-input evidence and existing cleanup ownership remain in force.

Field-version1 uses physical cell hashes for binary/gray noise, jittered independent
cell activation for random dots (average density per cm²), and32 seed-owned spectral
waves for filtered noise. A fixed Gaussian threshold sets statistical black fraction;
no view-dependent FFT or quantile is applied. Seeds are unsigned64-bit integers;
cell hashes fold both halves into the uint32 hash. Noise element size and blur are
millimetres; smooth cell transitions bound blur to half an element. Random-dot
neighbour work and spectral bandwidth are validated before shader compilation.
Other patterns use analytic physical distances/periods, including polar origin,
dot diameter, bar width and grid colors/dashes. CPU inspection and GL presentation
share parameter defaults, validation, seed derivation and spectral coefficients.
Raster sampling/float32/optical limitations still apply to the displayed result.

A static GLB consumer bakes each surface's finite physical extent and UVs once;
its raster is an exported arena detail, never a repeat tile in the source recipe.
Changing the arena's legacy image repeat scale does not resize procedural features.
Local implementation and checks are recorded in the
[owning report](../../reports/visual_stimulus.md#texture-independent-extent--2026-10-27).

Previously saved horizontal/vertical bars remain readable and expose only
`bar_width_mm`, `blur_mm` and two colors; the selector labels the saved recipe
without adding these patterns to its choices.
Each color occupies the same width; spatial period is twice bar width and frequency
is its reciprocal in cycles/mm. Newly saved bars use the same raster-independent
field representation. Width must be finite and at least0.001mm. Opening older bars
uses their line width as the shared bar width; source files remain unchanged until
Save. Direct runtime loading of older recipes retains their existing behavior.
Simple asset parameters share equal-width two-column rows. Colors, file pickers,
seed controls and nested groups span both columns. Color parameters come last;
Grating begins with spatial period/orientation, then sharpness. Texture resolution
is omitted from authoring documents and saved JSON. Open/Save strip
`params.texture_resolution` and legacy `size` aliases; raster sampling uses the
internal sampling resolution selected by the renderer. Texture previews preserve
physical aspect ratio within1920 × 1080 (square previews1080 × 1080), with procedural
fields sampled directly at the preview dimensions. Save
writes recipe JSON without a companion PNG; generated pixels stay in memory.
Direct runtime loading of existing recipes retains its resolution behavior.
All asset color controls place
RGB (and alpha when present) on one row.

Generated recipes contain no projector assignment. Physical polar recipes are
centred on the field origin, independently of the viewing window. Existing legacy
polar exports use `params.tile_local: true` and finite physical dimensions. The editor removes legacy
origin/target screen fields when opening/saving a polar design; existing legacy
files used directly by runtime retain their calibrated interpretation.

Default appearance previews need no calibration. Sparse noise shows an illustrative
100 x 100 mm sample using the existing indexed generator and a fixed stream; it
stores no sample extent or screen identity. Actual screen grids and independent
streams are resolved by Protocol preparation. Optional calibrated screen inspection
shows the selected screen's grid/stream and centered residual margins, or samples
the procedural field over that screen's physical extent. Its screen selection is never saved
in the asset. Previews use display sRGB; they do not certify optics.
Refreshing, reopening and changing preview index do not change a saved seed.

## Arena design and export

The version-1 [arena design schema](arena-design.schema.json) is generated from
`cephvr.generate_stimulus.models.ArenaDesign`. Dimensions are millimetres: X/Y
span width/depth about the origin, floor Z=0, roof Z=height. Shapes are rectangular,
elliptical circular, annular torus, T-shaped two-choice and cross. Corridor width
controls the annular passage or maze corridor. Segments control curved boundaries;
subdivisions control each surface patch's mesh resolution.

Floor, roof and four wall-orientation groups each carry visibility, linear RGBA,
explicit OPAQUE/MASK coverage and cutoff (BLEND is outside the runtime profile),
optional texture, physical repeat scale, relief and scatter layers. Polygon walls
are assigned by dominant outward normal, including inner torus walls. Multi-selection
applies edited properties to the selected groups. Rock, ridges and waves are actual
normal displacements with a saved seed, height and spatial scale; no light is added.

Scatter density is objects/cm² of triangulated surface area, rounded to the nearest
integer. Triangle selection is area-weighted. Clustering is the probability of
reusing a seed-selected anchor triangle; within-triangle positions are uniform.
Objects use uniform random yaw and scale within the saved limits, local +Z aligned
with the surface normal. Model units are interpreted as millimetres, as in the
existing GLB importer; models are not automatically rescaled or collision-resolved.

Arena textures are PNG/JPEG or static tile recipes, including tile-local polar
patterns. Legacy screen-dependent polar and time-varying sparse-noise recipes are
rejected as arena materials. GLB scatter models
must satisfy the existing static profile. All supported node transforms, materials,
vertex colors, alpha and textures are baked into a self-contained output. Legacy
RGB8 recipes are converted from linear to sRGB when embedded as glTF textures.

Export creates a **new directory**, containing `arena.glb`, `design.arena.json`
and `provenance.json`. The GLB is parsed by the production importer before publication.
The final directory appears only after generation/validation completes; cancellation
or failure leaves existing exports untouched. Provenance records generator/Python/
NumPy versions and dependency/output SHA-256 fingerprints. Retain the GLB for exact
replay; a seed does not promise identical output across future generator versions.
Design dependencies remain relative to the chosen asset root.

Resource ceilings reuse the Visual Stimulus file policies. Generation is independent
of Qt/OpenGL. The GUI runs one cancellable CPU job with one replaceable pending job,
rejects stale results and retains only the current per-surface geometry cache.
Saving remains available if the authoring viewport cannot initialize; headless arena
export is independent of the editor.
Runtime Setup independently admits assets and preserves V13 protected resources.

Opening a legacy raster `texture_design`, including horizontal/vertical bars, converts it to a physical field with a notice
listing the dropped fields and the rendering change; the document stays modified, Save
routes to Save as… with a `.converted.json` default, and the source is never overwritten.
This module does not add dynamic lighting or animation,
infer movement boundaries, modify protocols or solve projector calibration.
