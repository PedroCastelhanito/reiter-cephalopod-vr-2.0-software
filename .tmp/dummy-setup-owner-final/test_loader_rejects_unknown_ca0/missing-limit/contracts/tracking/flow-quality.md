# Shared native-grid consistency screening

Authority: [T41](../../docs/architecture/tracking.md#t41), W1A/W2A, inside the
[initial flow proxy](water-flow-proxy.md). Water and fin use the same test with their
independently resolved settings and selected support. No new stage or worker.

## Neighborhood and residual

Use the original eligible native grid, once per pair. Eligibility requires positive
selected visible ROI area, an available finite measured vector, native validity, and
(if configured) native cost <= maximum_native_cost. Zero displacement is eligible.
Cost is the adapter's raw UINT8 diagnostic, not a probability or per-frame normalization.
A configured cost test requires FlowSettings.output_cost; missing promised buffers are
an adapter failure, not permission to bypass the test.

For cell (r,c), take the square of grid indices within radius_cells in each direction,
excluding (r,c). Include only originally eligible cells with positive selected area.
Clip at image/grid and selected ROI boundaries: no padding, reflection, outside-ROI
neighbors, automatic expansion or replacement. Section labels do not block neighbors.
Use the original eligibility mask for every test; median rejection never changes another
cell's neighbors. Fewer than minimum_neighbors makes the tested sample unevaluable.
There is no unscreened acceptance fallback. T44's area gates decide the complete result.

Work on acquired-image **displacements**, after native scaling and before body-basis
rotation or division by source dt. The configured noise_floor_px is positive acquired-
image pixels per displacement sample, not pixels/s. For each component j in camera x,y:

```text
m_j = median(neighbor displacement component j)
s_j = median(abs(neighbor displacement component j - m_j))
z_j = abs(tested displacement component j - m_j) / (s_j + noise_floor_px)
score = hypot(z_x, z_y)
```

Accept score <= maximum_normalized_residual. Both medians exclude the tested cell.
An even-sized median is the arithmetic mean of the middle two values. Each eligible
neighbor contributes once, without area/cost weighting. Use float64 finite arithmetic;
nonfinite derived statistics cannot pass. Never replace or alter measured vectors.
This is a component-wise normalized local test; it is not rotation invariant, an
amplitude cutoff, tissue classifier or proof of valid swimming-intent measurement.

[LocalMedianSettings](method_models.py) requires radius_cells, minimum_neighbors,
noise_floor_px, maximum_normalized_residual and explicit maximum_native_cost (null to
disable). tracking_config defaults are 1 cell, 4 neighbors, 0.1 px and 2.0 (standard
normalized-median-test starting values); saved values win. Require
minimum_neighbors <= (2*radius_cells+1)^2-1.
TOML omits maximum_native_cost to resolve the explicit JSON null; other missing fields
fail validation. Settings are session locked. A radius is in provider-grid cells;
changing grid resolution changes the physical neighborhood and needs tuning verification.

## Execution and compact evidence

Keep sample counts mutually exclusive in this order: unavailable/native-invalid,
nonfinite, cost-rejected, neighbor-unevaluable, median-rejected, accepted. Count every
native cell with positive selected area once. Keep all sample details transient. The
[complete evidence binding](pipeline-catalogue.md#evidence) retains only compact counts,
per-section areas and response diagnostics. Insufficient support invalidates all controls
and clears the existing filter; it does not stop the session as an ordinary low-quality
observation. Provider/lease/contract failures keep the existing backend-failure path.

Implement in the existing CPU estimator using bounded NumPy array operations. Allocate
and account for masks, local-window scratch and section support at Setup under existing
memory/progress limits; process bounded chunks with complete neighborhood halos when
necessary. Avoid a Python callback per sample or materializing an unbounded image-wide
window tensor. Chunking must give the same neighborhoods as processing the full grid.
No OpenPIV runtime dependency, iterative cleanup, dense recording or extra worker.
Runtime construction and rig tuning/verification remain outstanding.
