from __future__ import annotations

import io
import json
import struct
import threading
import time
from dataclasses import replace
from fractions import Fraction

import pytest
from tests.visual_stimulus.support import glb_fixture, make_prepared_trial, pack_glb

from cephvr.visual_stimulus.config.models.program_model import (
    Asset,
    ColorOverride,
    Time,
    VideoSettings,
)
from cephvr.visual_stimulus.resources.budget import (
    BoundedBudget,
    arena_mesh_bytes,
    arena_texture_bytes,
    review_capture_cpu_bytes,
    review_capture_gpu_bytes,
)
from cephvr.visual_stimulus.resources.ffv1_configuration import (
    FFV1ConfigurationError,
    read_ffv1_version,
    require_ffv1_version3,
)
from cephvr.visual_stimulus.resources.glb import GLBError, parse_glb
from cephvr.visual_stimulus.resources.image_headers import image_shape
from cephvr.visual_stimulus.resources.media import (
    ImagePixels,
    MediaPreparationError,
    decode_image,
)
from cephvr.visual_stimulus.resources.uniforms import build_uniform_layouts
from cephvr.visual_stimulus.resources.video import VideoPlayback
from cephvr.visual_stimulus.resources.video_index import (
    SourceFrame,
    VideoIndex,
    _relative_pts,
)
from cephvr.visual_stimulus.resources.video_selection import PlaybackCursor
from cephvr.visual_stimulus.resources.video_session import VideoSession


@pytest.mark.parametrize(
    "pattern",
    [
        "grating",
        "polar_grating",
        "checker",
        "dots_grid",
        "dots_rand",
        "noise_binary",
        "noise_gray",
        "filtered_noise",
        "calibration_grid",
        "flat",
    ],
)
def test_physical_fields_preserve_overlap_across_extents(pattern):
    import numpy as np

    from cephvr.visual_stimulus.resources.physical_field import raster_field

    small = raster_field(pattern, {}, 40, 24, 80, 48)
    large = raster_field(pattern, {}, 80, 48, 160, 96)
    assert np.array_equal(small, large[24:72, 40:120])


@pytest.mark.parametrize("axis", ["x", "y"])
def test_physical_field_exact_grating_period_and_anisotropic_pixels(axis):
    import numpy as np

    from cephvr.visual_stimulus.resources.physical_field import (
        raster_field,
        sample_field,
    )

    # A projector with X=0.1 mm/pixel and Y=0.25 mm/pixel.
    p = {"spatial_period_mm": 10.0, "orientation_deg": 0.0 if axis == "x" else 90.0}
    pixels = raster_field("grating", p, 40, 30, 400, 120)
    line = pixels[0, :, 0] if axis == "x" else pixels[:, 0, 0]
    period = 100 if axis == "x" else 40
    assert np.array_equal(line[:-period], line[period:])
    p["orientation_deg"] = 45.0
    x = np.arange(-110, 110, 0.31)
    y = np.full(x.shape, 0.123)
    shift = 10 / np.sqrt(2)
    a = sample_field("grating", p, x, y)
    b = sample_field("grating", p, x + shift, y + shift)
    assert np.array_equal(a, b)


@pytest.mark.parametrize("key", ["color_a", "color_b"])
@pytest.mark.parametrize("bad", ["notacolor", "#12345", "#gg0000", 7, [1, 2]])
def test_physical_field_direct_callers_reject_invalid_colors(key, bad):
    from cephvr.visual_stimulus.resources.physical_field import (
        sample_field,
        validate_field,
    )

    with pytest.raises(ValueError, match=key):
        validate_field("checker", {key: bad})
    with pytest.raises(ValueError, match=key):
        sample_field("checker", {key: bad}, [0.0], [0.0])
    for good in ("#ff0000", "00ff00", [1, 0, 0], (0.5, 0.5, 0.5), None):
        validate_field("checker", {key: good})


def test_physical_field_version_and_raster_parameters_rejected():
    from cephvr.visual_stimulus.resources.texture_recipe import parse_texture_recipe

    doc = dict(
        cephvr_asset_type="texture_field",
        format_version=1,
        kind="texture",
        pattern="grating",
        params={"spatial_period_mm": 10.0},
    )
    recipe = parse_texture_recipe(json.dumps(doc).encode())
    assert recipe.physical_field and recipe.tile_width_mm is None
    for key in (
        "texture_resolution",
        "tile_width_mm",
        "fit_cycles_to_tile",
        "screen_width_mm",
    ):
        changed = {**doc, "params": {**doc["params"], key: 10}}
        with pytest.raises(ValueError):
            parse_texture_recipe(json.dumps(changed).encode())
    for version in (0, 2, True, "1"):
        with pytest.raises(ValueError, match="version"):
            parse_texture_recipe(
                json.dumps({**doc, "format_version": version}).encode()
            )
    legacy = parse_texture_recipe(
        json.dumps({**doc, "cephvr_asset_type": "texture_design"}).encode()
    )
    assert not legacy.physical_field


@pytest.mark.parametrize("deferred", [False, True])
def test_physical_field_preparation_protects_recipe_without_rasterizing(
    tmp_path, monkeypatch, deferred
):
    import hashlib
    from types import SimpleNamespace

    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    raw = json.dumps(
        dict(
            cephvr_asset_type="texture_field",
            format_version=1,
            kind="texture",
            pattern="dots_rand",
            params={"seed": 173},
        )
    ).encode()
    (tmp_path / "field.json").write_bytes(raw)
    sources = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            sources.append(self)

        def independent_reader(self):
            assert not self.closed
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    def forbidden(*args, **kwargs):
        pytest.fail("Live physical fields must not be rasterized during preparation")

    monkeypatch.setattr(
        "cephvr.visual_stimulus.resources.texture_recipe.generate_texture_recipe",
        forbidden,
    )
    monkeypatch.setattr(
        "cephvr.visual_stimulus.resources.recipe_preparation.generate_texture_recipe",
        forbidden,
    )
    asset = Asset(
        asset_id="field",
        logical_path="field.json",
        profile="cephvr1_texture_json_v1",
        color_override=None,
    )
    budget = BoundedBudget(cpu_limit=50_000, gpu_limit=1000)
    bundle = prepare_resources(
        SimpleNamespace(assets=(asset,), instances=(), sequence=()),
        tmp_path,
        budget,
        announce=lambda *_: None,
        snapshot_limit_bytes=10000,
        video_index_limit_bytes=1000,
        glb_element_limit=1000,
        max_document_bytes=1000,
        source_factory=Source,
        defer_images=deferred,
    )
    try:
        resource = bundle.manifest.resources[0]
        assert resource.fingerprint.sha256 == hashlib.sha256(raw).hexdigest()
        content = (
            bundle.image_sources["field"]
            if deferred
            else bundle.prepared_content["field"]
        )
        assert content.field_recipe.physical_field
        assert content.field_recipe.params["seed"] == 173
        assert content.width == content.height == 1
        if deferred:
            assert len(content.load(lambda: None)) == 16
        assert (tmp_path / "field.json").read_bytes() == raw
    finally:
        assert bundle.asset_set.close() == ()
    assert all(source.closed for source in sources)


def test_physical_field_requires_physical_texture_placement():
    from types import SimpleNamespace as NS

    from cephvr.visual_stimulus.resources.physical_field import validate_field_uses

    for kind, space in (("image", "physical_surface"), ("texture", "visual_angle")):
        setting = NS(
            kind=kind,
            space=NS(kind=space),
            asset_id="field",
            pattern=NS(asset_id="field"),
        )
        group = NS(kind="group", body=(NS(kind="epoch", settings=(setting,)),))
        with pytest.raises(ValueError, match="physical-surface"):
            validate_field_uses((group,), {"field"})


def test_seeded_field_statistics_and_full_seed_range():
    import math

    import numpy as np

    from cephvr.visual_stimulus.resources.physical_field import sample_field

    rng = np.random.default_rng(172)
    x, y = rng.uniform(-10000, 10000, (2, 60000))
    seed = 2**64 - 59
    dots = sample_field(
        "dots_rand",
        {"density_per_cm2": 1.0, "dot_diameter_mm": 1.0, "seed": seed},
        x,
        y,
    )
    assert abs(np.mean(dots[:, 0] > 0) - math.pi / 400) < 0.002
    noise = sample_field("filtered_noise", {"black_fraction": 0.3, "seed": seed}, x, y)
    assert abs(np.mean(noise[:, 0] == 0) - 0.3) < 0.02
    other = sample_field("noise_binary", {"seed": seed - 2**32}, x, y)
    first = sample_field("noise_binary", {"seed": seed}, x, y)
    assert not np.array_equal(other, first)


def _glsl_field_hash(x, y, seed):
    """Pure-integer mirror of GLSL field_hash(ivec2, uint): uint(int) wraps mod 2**32."""
    from cephvr.visual_stimulus.resources.physical_field import seed32

    mask = 0xFFFFFFFF
    h = (((x & mask) * 0x1F123BB5) & mask) ^ (((y & mask) * 0x5F356495) & mask)
    h ^= seed32(seed)
    h = ((h ^ (h >> 16)) * 0x7FEB352D) & mask
    h = ((h ^ (h >> 15)) * 0x846CA68B) & mask
    return ((h ^ (h >> 16)) >> 8) / 16777216


def test_field_hash_wraps_negative_cells_like_glsl_uint():
    import numpy as np

    from cephvr.visual_stimulus.resources.physical_field import _hash

    cells = [
        (-1, -1),
        (-5, 2),
        (0, -7),
        (3, 3),
        (-123456, 99999),
        (-(2**31), 2**31 - 1),
    ]
    for seed in (0, 2**64 - 59):
        got = _hash(
            *(np.array(a, dtype=np.float64) for a in zip(*cells, strict=True)), seed
        )
        assert got.tolist() == [_glsl_field_hash(x, y, seed) for x, y in cells]
    assert _hash(np.array([-1.0]), np.array([-1.0]), 0)[0] == 0.3115309476852417


def test_dots_rand_matches_scalar_reference_across_negative_cells():
    import math

    import numpy as np

    from cephvr.visual_stimulus.resources.physical_field import sample_field

    seed, density, diameter = 7, 4.0, 3.0
    pitch = math.sqrt(25 / density)
    rng = np.random.default_rng(3)
    x, y = rng.uniform(-60, 60, (2, 300))

    def reference(px, py):
        cx, cy = math.floor(px / pitch), math.floor(py / pitch)
        for j in range(-2, 3):
            for i in range(-2, 3):
                ix, iy = cx + i, cy + j
                if _glsl_field_hash(ix, iy, seed) >= 0.25:
                    continue
                ox = (ix + _glsl_field_hash(ix, iy, seed ^ 12345)) * pitch
                oy = (iy + _glsl_field_hash(ix, iy, seed ^ 67890)) * pitch
                if math.hypot(px - ox, py - oy) <= diameter / 2:
                    return 255
        return 0

    got = sample_field(
        "dots_rand",
        {"density_per_cm2": density, "dot_diameter_mm": diameter, "seed": seed},
        x,
        y,
    )[:, 0]
    assert got.tolist() == [reference(px, py) for px, py in zip(x, y, strict=True)]
    assert 0 < np.count_nonzero(got) < len(got)


@pytest.mark.parametrize("consumed", [False, True])
def test_screen_image_preparation_rejects_only_consumed_nonlinear_profiles(
    tmp_path, monkeypatch, consumed
):
    from types import SimpleNamespace

    from cephvr.visual_stimulus.config.models.artifact_models import (
        GeometricProfile,
        Vertex,
    )
    from cephvr.visual_stimulus.config.models.display_profile import PixelRect
    from cephvr.visual_stimulus.resources import prepare
    from cephvr.visual_stimulus.resources.calibration import PreparedCalibration

    # The regular profile validator permits this nonlinear, nondegenerate quad.
    profile = GeometricProfile(
        format_version=1,
        calibration_id="test",
        mapping_id="mapped",
        surface_id="front",
        output_id="front",
        output_width=100,
        output_height=100,
        viewport=PixelRect(x=0, y=0, width=100, height=100),
        rows=2,
        columns=2,
        vertices=tuple(
            Vertex(uv=uv, xy=xy)
            for uv, xy in zip(
                ((0, 0), (1, 0), (0, 1), (1, 1)),
                ((0, 0), (1, 0), (0, 1), (0.8, 1)),
                strict=True,
            )
        ),
        orientation="preserving",
        diagonal="bottom_left_to_top_right",
        mask=None,
        weight=None,
        overlap_group=None,
        valid_area=(0, 0, 1, 1),
        intended_coverage=((0, 0), (1, 0), (0.8, 1), (0, 1)),
        coverage_tolerance=0.01,
        triangle_area_tolerance=0.0001,
    )
    monkeypatch.setattr(
        prepare,
        "prepare_calibration",
        lambda *args, **kwargs: PreparedCalibration((), (), {"mapped": profile}),
    )
    monkeypatch.setattr(
        prepare,
        "build_uniform_layouts",
        lambda *args: (
            SimpleNamespace(
                name="image_target_pixels_mapped"
                if consumed
                else "image_target_pixels_other"
            ),
        ),
    )
    budget = BoundedBudget(cpu_limit=10000, gpu_limit=10000)

    def run():
        return prepare.prepare_resources(
            SimpleNamespace(assets=(), sequence=(), instances=()),
            tmp_path,
            budget,
            announce=lambda *_: None,
            snapshot_limit_bytes=1000,
            video_index_limit_bytes=1000,
            glb_element_limit=100,
            display=SimpleNamespace(),
            component_provenance=(),
        )

    if consumed:
        with pytest.raises(ValueError, match="affine"):
            run()
    else:
        assert run().asset_set.close() == ()
    assert budget.usage.cpu_bytes == 0


def _sparse_recipe(**changes):
    from cephvr.visual_stimulus.config.models.sparse_noise import (
        parse_sparse_noise_json,
    )

    fields = {
        "format_version": 2,
        "kind": "sparse_noise",
        "seed": 12345,
        "surfaces": ["front", "left"],
        "square_size_mm": 10.0,
        "min_active_cell_distance_mm": 0.0,
        "active_probability": 0.2,
        "background_linear": 0.5,
        "pattern_count": 3,
        "pattern_duration": {"seconds": "20"},
    }
    fields.update(changes)
    return parse_sparse_noise_json(json.dumps(fields), max_bytes=10000)


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": True},
        {"seed": -1},
        {"seed": 1.5},
        {"seed": 2**64},
        {"active_probability": -0.1},
        {"active_probability": 1.1},
        {"min_active_cell_distance_mm": -1},
        {"min_active_cell_distance_mm": float("inf")},
        {"active_probability": float("nan")},
        {"active_density": 0.2},
        {"format_version": 1},
        {"square_size_mm": 0},
        {"square_size_mm": float("inf")},
        {"surfaces": ["front", "front"]},
        {"pattern_duration": {"seconds": "0"}},
        {"pattern_count": 1},
        {"unexpected": 1},
    ],
)
def test_sparse_noise_rejects_invalid_scientific_inputs(changes):
    with pytest.raises(ValueError):
        _sparse_recipe(**changes)


def test_sparse_noise_full_cells_probability_and_transparent_background():
    import math

    import numpy as np
    from tests.visual_stimulus.support import make_compile_context

    from cephvr.visual_stimulus.resources.sparse_noise import resolve_grids

    display = make_compile_context().display
    recipe = _sparse_recipe(square_size_mm=13.0, active_probability=0.0)
    grids = resolve_grids(recipe, display, max_cells=10000)
    for grid in grids:
        surface = next(
            s for s in display.geometry.surfaces if s.surface_id == grid.surface_id
        )
        assert (
            0
            <= math.dist(surface.bottom_left_mm, surface.bottom_right_mm)
            - grid.width_mm
            < 13
        )
    from cephvr.visual_stimulus.resources.sparse_noise import pattern_rgba

    pixels = np.frombuffer(pattern_rgba(recipe, grids[0], 0), dtype=np.uint8)
    assert not pixels[3::4].any()  # Probability zero: only transparent background.
    assert resolve_grids(
        _sparse_recipe(active_probability=1e-10), display, max_cells=10000
    )


def test_sparse_spacing_regenerates_layout_and_probability_is_independent():
    import math

    from cephvr.visual_stimulus.resources.sparse_noise import (
        eligible_cells,
        grid_for_extent,
        pattern_rgba,
    )

    recipe = _sparse_recipe(
        pattern_count=30, min_active_cell_distance_mm=25.0, active_probability=1.0
    )
    grid = grid_for_extent(recipe, "front", 100, 100, max_cells=1000)
    layouts = []
    counts = []
    for index in range(30):
        layout = eligible_cells(recipe, grid, index)
        layouts.append(frozenset(layout))
        assert len(layout) == len(set(layout))
        for i, a in enumerate(layout):
            for b in layout[i + 1 :]:
                assert (
                    math.hypot(
                        a % grid.columns - b % grid.columns,
                        a // grid.columns - b // grid.columns,
                    )
                    * recipe.square_size_mm
                    >= 25.0
                )
        # Every excluded cell is blocked by an eligible cell: the greedy layout is maximal.
        for cell in set(range(grid.columns * grid.rows)) - set(layout):
            assert any(
                math.hypot(
                    cell % grid.columns - other % grid.columns,
                    cell // grid.columns - other // grid.columns,
                )
                * 10
                < 25
                for other in layout
            )
        full = pattern_rgba(recipe, grid, index)
        assert {i for i, alpha in enumerate(full[3::4]) if alpha} == set(layout)
        low = recipe.model_copy(update={"active_probability": 0.25})
        high = recipe.model_copy(update={"active_probability": 0.75})
        assert (
            eligible_cells(low, grid, index)
            == layout
            == eligible_cells(high, grid, index)
        )
        low_pixels, high_pixels = (
            pattern_rgba(low, grid, index),
            pattern_rgba(high, grid, index),
        )
        active_low = {i for i, alpha in enumerate(low_pixels[3::4]) if alpha}
        active_high = {i for i, alpha in enumerate(high_pixels[3::4]) if alpha}
        assert active_low <= active_high <= set(layout)
        assert all(
            low_pixels[i * 4 : i * 4 + 4] == high_pixels[i * 4 : i * 4 + 4]
            for i in active_low
        )
        counts.append(len(active_low))
    assert len(set(layouts)) > 1
    assert len(set(counts)) > 1
    assert not any(
        pattern_rgba(recipe.model_copy(update={"active_probability": 0.0}), grid, 0)
    )
    assert pattern_rgba(recipe, grid, 2) == pattern_rgba(recipe, grid, 2)


def test_sparse_spacing_accepts_cells_exactly_at_the_minimum_distance():
    from cephvr.visual_stimulus.resources.sparse_noise import (
        SparseNoiseGrid,
        eligible_cells,
    )

    # 2.1 / 0.3 == 7.000000000000001, yet cells 0 and 7 are exactly 7 cells apart.
    grid = SparseNoiseGrid("front", 8, 1, 2.4, 0.3)
    both = 0
    for seed in range(40):
        recipe = _sparse_recipe(
            seed=seed, square_size_mm=0.3, min_active_cell_distance_mm=2.1
        )
        layout = eligible_cells(recipe, grid, 0)
        # Maximal: every excluded cell lies strictly inside 7 cells of a selected one.
        for cell in set(range(8)) - set(layout):
            assert any(abs(cell - other) < 7 for other in layout)
        both += {0, 7} <= set(layout)
    assert both


def test_sparse_noise_layouts_for_fixed_seeds_stay_identical():
    import hashlib

    from cephvr.visual_stimulus.resources.sparse_noise import (
        SparseNoiseGrid,
        eligible_cells,
        pattern_rgba,
    )

    golden = {
        "0.1/0.7/8x1/1/0": "311c7b3f7c96",
        "0.1/0.7/8x1/1/1": "ba39095e23c5",
        "0.1/0.7/8x1/1/2": "2f8bcefa3968",
        "0.1/0.7/8x1/12345/0": "2f8bcefa3968",
        "0.1/0.7/8x1/12345/1": "e6d4f665c4ab",
        "0.1/0.7/8x1/12345/2": "e6d4f665c4ab",
        "0.1/0.7/8x1/99/0": "ba39095e23c5",
        "0.1/0.7/8x1/99/1": "32d48f3e9a82",
        "0.1/0.7/8x1/99/2": "fee9a8497c40",
        "0.3/2.1/8x1/1/0": "311c7b3f7c96",
        "0.3/2.1/8x1/1/1": "ba39095e23c5",
        "0.3/2.1/8x1/1/2": "2f8bcefa3968",
        "0.3/2.1/8x1/12345/0": "2f8bcefa3968",
        "0.3/2.1/8x1/12345/1": "e6d4f665c4ab",
        "0.3/2.1/8x1/12345/2": "e6d4f665c4ab",
        "0.3/2.1/8x1/99/0": "ba39095e23c5",
        "0.3/2.1/8x1/99/1": "9c1e38bd35e7",
        "0.3/2.1/8x1/99/2": "fee9a8497c40",
        "10.0/0.0/6x6/1/0": "17d874591b19",
        "10.0/0.0/6x6/1/1": "5498f3b86b21",
        "10.0/0.0/6x6/1/2": "ad4d26ae8139",
        "10.0/0.0/6x6/12345/0": "5b3b65518c4a",
        "10.0/0.0/6x6/12345/1": "a3204afcb046",
        "10.0/0.0/6x6/12345/2": "76567f5f4559",
        "10.0/0.0/6x6/99/0": "b8ddb4bb87aa",
        "10.0/0.0/6x6/99/1": "528c4f9e2fda",
        "10.0/0.0/6x6/99/2": "9f71ace2cd18",
        "10.0/10.0/5x5/1/0": "663d217bcba0",
        "10.0/10.0/5x5/1/1": "c25b1a6c04ce",
        "10.0/10.0/5x5/1/2": "e6dbbda09309",
        "10.0/10.0/5x5/12345/0": "4aac16bb582f",
        "10.0/10.0/5x5/12345/1": "12a57304c01d",
        "10.0/10.0/5x5/12345/2": "ca44ce6260df",
        "10.0/10.0/5x5/99/0": "57a5cfb4c3c2",
        "10.0/10.0/5x5/99/1": "9efd2c60463b",
        "10.0/10.0/5x5/99/2": "75cb7a3fc56f",
        "10.0/25.0/12x9/1/0": "36c3b09e01fc",
        "10.0/25.0/12x9/1/1": "add75ff956e9",
        "10.0/25.0/12x9/1/2": "4edf4ca408fe",
        "10.0/25.0/12x9/12345/0": "cd0737d9d805",
        "10.0/25.0/12x9/12345/1": "84034c280efd",
        "10.0/25.0/12x9/12345/2": "38a3a2724205",
        "10.0/25.0/12x9/99/0": "2955491b1b09",
        "10.0/25.0/12x9/99/1": "1e6695f37df8",
        "10.0/25.0/12x9/99/2": "78b22121d017",
        "10.0/35.0/20x15/1/0": "add9b9eefdce",
        "10.0/35.0/20x15/1/1": "9498a6ec7713",
        "10.0/35.0/20x15/1/2": "5bb688900b30",
        "10.0/35.0/20x15/12345/0": "6080f06e1a86",
        "10.0/35.0/20x15/12345/1": "ba32710bb971",
        "10.0/35.0/20x15/12345/2": "b2860c15aabd",
        "10.0/35.0/20x15/99/0": "ad9adabebda8",
        "10.0/35.0/20x15/99/1": "e698fc614b28",
        "10.0/35.0/20x15/99/2": "762016751450",
    }
    for key, digest in golden.items():
        square, distance, size, seed, index = key.split("/")
        columns, rows = map(int, size.split("x"))
        recipe = _sparse_recipe(
            seed=int(seed),
            square_size_mm=float(square),
            min_active_cell_distance_mm=float(distance),
        )
        grid = SparseNoiseGrid(
            "front", columns, rows, columns * float(square), rows * float(square)
        )
        layout = eligible_cells(recipe, grid, int(index))
        pixels = pattern_rgba(recipe, grid, int(index))
        actual = hashlib.sha256(repr(layout).encode() + pixels).hexdigest()[:12]
        # The exact-distance recipes (0.3/2.1 and 0.1/0.7) may legitimately differ.
        if not key.startswith(("0.3/", "0.1/")):
            assert actual == digest, key


def test_sparse_noise_active_output_enforcement_needs_a_profile_or_surface_set():
    from tests.visual_stimulus.support import make_compile_context

    from cephvr.visual_stimulus.resources.sparse_noise import resolve_grids

    display = make_compile_context().display
    recipe = _sparse_recipe()  # front + left
    dropped = display.model_copy(
        update={
            "mappings": tuple(m for m in display.mappings if m.surface_id != "left")
        }
    )
    with pytest.raises(ValueError, match="left has no active output"):
        resolve_grids(recipe, dropped, max_cells=10000)
    with pytest.raises(ValueError, match="left has no active output"):
        resolve_grids(
            recipe, display.geometry, max_cells=10000, active_surfaces={"front"}
        )
    # A bare Geometry has no output data: every surface counts as active (documented).
    assert len(resolve_grids(recipe, display.geometry, max_cells=10000)) == 2


@pytest.mark.parametrize("distance,expected", [(0.0, 100), (10.0, 100), (1000.0, 1)])
def test_sparse_spacing_boundaries(distance, expected):
    from cephvr.visual_stimulus.resources.sparse_noise import (
        eligible_cells,
        grid_for_extent,
    )

    recipe = _sparse_recipe(min_active_cell_distance_mm=distance)
    grid = grid_for_extent(recipe, "front", 100, 100, max_cells=1000)
    assert len(eligible_cells(recipe, grid, 0)) == expected


def test_sparse_layout_observes_cancellation():
    from cephvr.visual_stimulus.resources.sparse_noise import (
        eligible_cells,
        grid_for_extent,
    )

    recipe = _sparse_recipe(min_active_cell_distance_mm=25.0)
    grid = grid_for_extent(recipe, "front", 500, 500, max_cells=10000)
    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise InterruptedError("cancelled during layout")

    with pytest.raises(InterruptedError, match="during layout"):
        eligible_cells(recipe, grid, 0, check=check)


@pytest.mark.parametrize("path", [None, "textures/image.png"])
def test_native_preparation_retains_intent_when_registration_receipt_is_lost(path):
    from cephvr.visual_stimulus.resources.session import NativePreparation

    preparation = NativePreparation(object(), renderer_generation="renderer")
    registered = []

    def lost_receipt(key, announced_path):
        registered.append((key, announced_path))
        raise TimeoutError("registration receipt lost")

    with pytest.raises(TimeoutError, match="receipt lost"):
        preparation._registered_announce(lost_receipt, "trial")("asset", path)
    assert registered == [("trial:asset", path)]
    assert not preparation._protected_sources
    released = preparation.cleanup()
    assert released.released == ("trial:asset",)
    assert not released.outstanding


def test_native_preparation_retains_release_proof_until_catalogue_retirement():
    from cephvr.visual_stimulus.resources.session import NativePreparation

    preparation = NativePreparation(object(), renderer_generation="renderer")

    def announce(*_):
        pass

    old_key = "visual_stimulus:display:calibration:diagnostic_front"
    preparation._registered_announce(announce, "visual_stimulus:display")(
        "calibration:diagnostic_front", "calibration/diagnostic_front.json"
    )
    first = preparation.cleanup()
    assert first.released == (old_key,)

    # A failed display initialization can be followed by Setup while these
    # released keys remain in the worker catalogue.
    preparation._registered_announce(announce, "visual_stimulus:trial:new")(
        "calibration:diagnostic_front", "calibration/diagnostic_front.json"
    )
    second = preparation.cleanup()
    assert set(second.released) == {
        old_key,
        "visual_stimulus:trial:new:calibration:diagnostic_front",
    }

    # Reopening the original identity invalidates its old proof until the new
    # owner confirms release.
    preparation._registered_announce(announce, "visual_stimulus:display")(
        "calibration:diagnostic_front", "calibration/diagnostic_front.json"
    )

    class Source:
        def close_after_consumers(self):
            raise OSError("source is still in use")

    preparation._protected_sources.append((Source(), old_key))
    reopened = preparation.cleanup()
    assert old_key not in reopened.released
    assert reopened.outstanding

    preparation.retire_released_resources()
    assert not preparation._released_resource_keys


def test_json_texture_preparation_retains_recipe_identity_and_budget(
    tmp_path, monkeypatch
):
    import hashlib
    from types import SimpleNamespace

    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    raw = b'{"pattern":"checker","params":{"texture_resolution":8,"tile_width_mm":104}}'
    path = tmp_path / "texture.json"
    path.write_bytes(raw)
    sources = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            sources.append(self)

        def independent_reader(self):
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    program = SimpleNamespace(
        assets=(
            Asset(
                asset_id="recipe",
                logical_path="texture.json",
                profile="cephvr1_texture_json_v1",
                color_override=None,
            ),
        ),
        instances=(),
        sequence=(),
    )
    budget = BoundedBudget(cpu_limit=100_000, gpu_limit=100_000)
    bundle = prepare_resources(
        program,
        tmp_path,
        budget,
        announce=lambda *_: None,
        snapshot_limit_bytes=100_000,
        video_index_limit_bytes=1000,
        glb_element_limit=1000,
        max_document_bytes=1000,
        source_factory=Source,
    )
    resource = bundle.manifest.resources[0]
    assert resource.fingerprint.sha256 == hashlib.sha256(raw).hexdigest()
    assert resource.fingerprint.logical_path == "texture.json"
    assert resource.profile_id == "cephvr1_texture_json_v1"
    assert resource.provider_compatibility == "cephvr1-texture-raster-v1"
    assert bundle.prepared_content["recipe"].pixels.shape == (8, 8, 3)
    assert bundle.prepared_content["recipe"].transfer == "linear"
    assert budget.usage.cpu_bytes == len(raw) + 8 * 8 * 64
    bundle.asset_set.close()
    assert all(source.closed for source in sources)

    def forbidden_generation(*args, **kwargs):
        pytest.fail("rasterization must not start before its full scratch reservation")

    monkeypatch.setattr(
        "cephvr.visual_stimulus.resources.recipe_preparation.generate_texture_recipe",
        forbidden_generation,
    )
    budget = BoundedBudget(cpu_limit=9000, gpu_limit=100_000)
    with pytest.raises(MemoryError):
        prepare_resources(
            program,
            tmp_path,
            budget,
            announce=lambda *_: None,
            snapshot_limit_bytes=1000,
            video_index_limit_bytes=1000,
            glb_element_limit=1000,
            max_document_bytes=1000,
            source_factory=Source,
        )
    assert all(source.closed for source in sources)
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0


def test_tiff_uint_decoder_accepts_supported_pixels_and_rejects_float() -> None:
    tifffile = pytest.importorskip("tifffile")
    np = pytest.importorskip("numpy")
    asset = Asset(
        asset_id="image",
        logical_path="image.tif",
        profile="tiff_uint_v1",
        color_override=ColorOverride(
            transfer="linear",
            primaries="rec709_d65",
            range="full",
            matrix="rgb",
            chroma_location="none",
            reason="decoder regression",
        ),
    )
    for pixels, expected_channels in (
        (np.arange(12, dtype=np.uint8).reshape(3, 4), 1),
        (np.arange(36, dtype=np.uint16).reshape(3, 4, 3), 3),
    ):
        encoded = io.BytesIO()
        tifffile.imwrite(encoded, pixels)
        decoded = decode_image(asset, encoded.getvalue())
        np.testing.assert_array_equal(decoded.pixels, pixels)
        assert decoded.pixels.shape == pixels.shape
        assert decoded.dtype == str(pixels.dtype)
        assert decoded.channel_count == expected_channels
        assert decoded.transfer == "linear"

    encoded = io.BytesIO()
    tifffile.imwrite(encoded, np.arange(12, dtype=np.float32).reshape(3, 4))
    with pytest.raises(MediaPreparationError, match="unsigned 8-bit or 16-bit"):
        decode_image(asset, encoded.getvalue())


def test_resource_budget_replacement_is_atomic() -> None:
    budget = BoundedBudget(cpu_limit=100, gpu_limit=50)
    budget.reserve(owner="texture", cpu_bytes=40, gpu_bytes=30)
    budget.reserve(owner="texture", cpu_bytes=60, gpu_bytes=40)
    assert (budget.usage.cpu_bytes, budget.usage.gpu_bytes) == (60, 40)
    with pytest.raises(MemoryError):
        budget.reserve(owner="geometry", cpu_bytes=50, gpu_bytes=20)
    assert (budget.usage.cpu_bytes, budget.usage.gpu_bytes) == (60, 40)
    budget.release(owner="texture")
    assert (budget.usage.cpu_bytes, budget.usage.gpu_bytes) == (0, 0)


def test_protected_image_source_reloads_linear_pixels_without_rehashing_or_closing():
    import hashlib

    import numpy as np
    import tifffile

    from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes
    from cephvr.visual_stimulus.resources.assets import PreparedAsset
    from cephvr.visual_stimulus.resources.image_source import (
        read_source_bytes,
        validate_image_source,
    )

    pixels = np.arange(36, dtype=np.uint16).reshape(3, 4, 3) * 1000
    stream = io.BytesIO()
    tifffile.imwrite(stream, pixels, photometric="rgb")
    raw = stream.getvalue()
    asset = Asset(
        asset_id="still",
        logical_path="still.tif",
        profile="tiff_uint_v1",
        color_override=ColorOverride(
            transfer="linear",
            primaries="rec709_d65",
            range="full",
            matrix="rgb",
            chroma_location="none",
            reason="residency test",
        ),
    )

    class Source:
        closed = False

        def __init__(self):
            self.readers = 0

        def independent_reader(self):
            self.readers += 1
            return io.BytesIO(raw)

        def close_after_consumers(self):
            self.closed = True

    protected = Source()
    prepared = PreparedAsset(
        asset.asset_id,
        asset.logical_path,
        asset.profile,
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        protected,
        None,
    )
    budget = BoundedBudget(cpu_limit=100_000, gpu_limit=100_000)
    source, info = validate_image_source(
        asset,
        prepared,
        budget=budget,
        owner="test:still",
        output_count=3,
        max_document_bytes=1000,
    )

    expected = linear_rgba_bytes(decode_image(asset, raw))
    first_read = read_source_bytes(prepared, lambda: None)
    second_read = read_source_bytes(prepared, lambda: None)
    assert first_read == second_read == raw
    assert hashlib.sha256(first_read).hexdigest() == prepared.sha256
    assert (info.width, info.height, info.dtype, info.transfer, info.alpha) == (
        4,
        3,
        "uint16",
        "linear",
        "none",
    )
    assert source.load(lambda: None) == expected
    assert source.load(lambda: None) == expected
    assert source.cpu_bytes >= 2 * len(raw) + 4 * 3 * 128
    reads = protected.readers
    reused, reused_info = validate_image_source(
        asset,
        prepared,
        budget=budget,
        owner="test:cached",
        output_count=3,
        max_document_bytes=1000,
        cached_info=info,
    )
    assert protected.readers == reads
    assert reused_info == info and reused.key == source.key
    assert reused.load(lambda: None) == expected
    assert source.gpu_bytes == 4 * 3 * 16 * 3
    assert protected.readers == 6  # Validation, two source reads and three loads.
    assert not protected.closed
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0


def test_image_source_budget_failure_precedes_opening_protected_source():
    import hashlib

    from cephvr.visual_stimulus.resources.assets import PreparedAsset
    from cephvr.visual_stimulus.resources.image_source import validate_image_source

    raw = b"x" * 64
    asset = Asset(
        asset_id="still",
        logical_path="still.tif",
        profile="tiff_uint_v1",
        color_override=ColorOverride(
            transfer="linear",
            primaries="rec709_d65",
            range="full",
            matrix="rgb",
            chroma_location="none",
            reason="budget test",
        ),
    )

    class Source:
        readers = 0

        def independent_reader(self):
            self.readers += 1
            return io.BytesIO(raw)

        def close_after_consumers(self):
            pass

    protected = Source()
    prepared = PreparedAsset(
        asset.asset_id,
        asset.logical_path,
        asset.profile,
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        protected,
        None,
    )
    budget = BoundedBudget(cpu_limit=10, gpu_limit=100)
    with pytest.raises(MemoryError, match="budget exceeded"):
        validate_image_source(
            asset,
            prepared,
            budget=budget,
            owner="test:still",
            output_count=1,
            max_document_bytes=1000,
        )
    assert protected.readers == 0
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0


def test_recipe_image_source_is_deterministic_and_preserves_dependency_dimensions():
    import hashlib

    from PIL import Image

    from cephvr.visual_stimulus.resources.assets import PreparedAsset
    from cephvr.visual_stimulus.resources.image_source import validate_image_source

    recipe_raw = b'{"pattern":"image","params":{"texture_path":"source.png"}}'
    recipe_asset = Asset(
        asset_id="recipe",
        logical_path="recipe.json",
        profile="cephvr1_texture_json_v1",
        color_override=None,
    )
    dependency_asset = Asset(
        asset_id="recipe-source",
        logical_path="source.png",
        profile="png_uint_v1",
        color_override=ColorOverride(
            transfer="linear",
            primaries="rec709_d65",
            range="full",
            matrix="rgb",
            chroma_location="none",
            reason="legacy recipe samples authored RGB values directly",
        ),
    )
    encoded = io.BytesIO()
    with Image.frombytes(
        "RGB",
        (3, 2),
        bytes(
            (255, 0, 0, 0, 255, 0, 0, 0, 255, 20, 40, 60, 80, 100, 120, 140, 160, 180)
        ),
    ) as image:
        image.save(encoded, format="PNG")
    dependency_raw = encoded.getvalue()

    class Source:
        def __init__(self, data):
            self.data = data
            self.closed = False

        def independent_reader(self):
            return io.BytesIO(self.data)

        def close_after_consumers(self):
            self.closed = True

    recipe_source = PreparedAsset(
        recipe_asset.asset_id,
        recipe_asset.logical_path,
        recipe_asset.profile,
        hashlib.sha256(recipe_raw).hexdigest(),
        len(recipe_raw),
        Source(recipe_raw),
        None,
    )
    dependency_source = PreparedAsset(
        dependency_asset.asset_id,
        dependency_asset.logical_path,
        dependency_asset.profile,
        hashlib.sha256(dependency_raw).hexdigest(),
        len(dependency_raw),
        Source(dependency_raw),
        None,
    )
    budget = BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000)
    image_source, info = validate_image_source(
        recipe_asset,
        recipe_source,
        budget=budget,
        owner="test:recipe",
        output_count=2,
        max_document_bytes=1000,
        dependency_asset=dependency_asset,
        dependency_source=dependency_source,
    )

    first = image_source.load(lambda: None)
    second = image_source.load(lambda: None)
    assert first == second
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    assert (image_source.width, image_source.height, info.width, info.height) == (
        3,
        2,
        3,
        2,
    )
    assert (info.dtype, info.channel_order, info.transfer, info.alpha) == (
        "uint8",
        ("red", "green", "blue"),
        "linear",
        "none",
    )
    assert image_source.gpu_bytes == 3 * 2 * 16 * 2
    assert image_source.cpu_bytes >= (
        2 * (len(recipe_raw) + len(dependency_raw)) + 32 * len(recipe_raw) + 3 * 2 * 192
    )
    checks = 0

    def cancel_during_read():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise InterruptedError("image loading cancelled")

    with pytest.raises(InterruptedError, match="cancelled"):
        image_source.load(cancel_during_read)
    assert checks == 2
    assert not recipe_source.source.closed and not dependency_source.source.closed
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0


@pytest.mark.parametrize("tile_local", [False, True])
def test_polar_recipe_image_source_key_includes_explicit_surface_geometry(tile_local):
    import hashlib
    from types import SimpleNamespace

    from cephvr.visual_stimulus.resources.assets import PreparedAsset
    from cephvr.visual_stimulus.resources.image_source import validate_image_source

    raw = (
        b'{"pattern":"polar_grating","params":{"size":8,"bar_count":6,"tile_local":'
        + (b"true" if tile_local else b"false")
        + b"}}"
    )
    asset = Asset(
        asset_id="polar",
        logical_path="polar.json",
        profile="cephvr1_texture_json_v1",
        color_override=None,
    )
    prepared = PreparedAsset(
        asset.asset_id,
        asset.logical_path,
        asset.profile,
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        SimpleNamespace(),
        raw,
    )
    display = make_prepared_trial().display
    first_surface = display.geometry.surfaces[0]
    shifted = first_surface.model_copy(
        update={
            "bottom_left_mm": tuple(
                value + 0.25 for value in first_surface.bottom_left_mm
            )
        }
    )
    changed_geometry = display.geometry.model_copy(
        update={"surfaces": (shifted, *display.geometry.surfaces[1:])}
    )
    changed_display = display.model_copy(update={"geometry": changed_geometry})
    budget = BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000)
    first, _ = validate_image_source(
        asset,
        prepared,
        budget=budget,
        owner="test:polar:first",
        output_count=1,
        max_document_bytes=1000,
        display=display,
    )
    second, _ = validate_image_source(
        asset,
        prepared,
        budget=budget,
        owner="test:polar:second",
        output_count=1,
        max_document_bytes=1000,
        display=changed_display,
    )
    assert (first.key == second.key) is tile_local
    if tile_local:
        assert first.load(lambda: None) == second.load(lambda: None)
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0


def test_review_capture_cpu_budget_includes_fixed_copy_and_row_scratch() -> None:
    frame_bytes = 1920 * 1080 * 4
    row_bytes = 1920 * 4
    assert review_capture_cpu_bytes(1920, 1080, 1) == 4 * frame_bytes + 540 * row_bytes
    assert review_capture_cpu_bytes(1920, 1080, 3) == 6 * frame_bytes + 540 * row_bytes
    assert review_capture_cpu_bytes(2, 3, 1) == 4 * 24 + 8
    with pytest.raises(ValueError, match="positive review capture"):
        review_capture_cpu_bytes(0, 1080, 1)


def test_arena_gpu_budget_covers_generated_attributes_and_both_mip_chains() -> None:
    from cephvr.visual_stimulus.rendering.arena_gpu import _interleaved_vertices
    from cephvr.visual_stimulus.resources.glb import GLBPrimitive

    identity = (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    primitive = GLBPrimitive(
        positions=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        indices=(0, 1, 2),
        texcoords=None,
        colors=None,
        material_index=None,
    )
    uploaded = _interleaved_vertices(identity, primitive)
    assert arena_mesh_bytes(3, 3) == len(uploaded) * 4 + 12
    # Non-square 3x8 -> 1x4 -> 1x2 -> 1x1; two float32 RGBA variants.
    assert arena_texture_bytes(3, 8, mipmapped=True) == (24 + 4 + 2 + 1) * 32
    assert arena_texture_bytes(3, 8, mipmapped=False) == 24 * 32


def test_glb_reader_rejects_malformed_or_unbounded_container() -> None:
    with pytest.raises(GLBError, match="header"):
        parse_glb(b"not-glb", max_bytes=100, max_elements=10)
    header = struct.pack("<4sII", b"glTF", 2, 24)
    json_chunk = struct.pack("<II", 4, 0x4E4F534A) + b"{}  "
    with pytest.raises(GLBError, match="JSON and BIN"):
        parse_glb(header + json_chunk, max_bytes=100, max_elements=10)
    with pytest.raises(GLBError, match="bounds"):
        parse_glb(header + json_chunk, max_bytes=19, max_elements=10)


def test_builtin_shader_layouts_cover_each_instance_without_binding_collisions() -> (
    None
):
    program = make_prepared_trial().source
    layouts = build_uniform_layouts(program)
    assert len(layouts) == 7
    assert len({item.binding_id for item in layouts}) == len(layouts)
    assert {item.instance_id for item in layouts} == {"texture"}
    assert {item.name for item in layouts} == {
        "opacity",
        "contrast",
        "mean_rgb",
        "modulation_rgb",
        "frequency",
        "phase",
        "period",
    }
    assert next(item for item in layouts if item.name == "mean_rgb").shape == (3,)
    assert next(item for item in layouts if item.name == "period").shape == (2,)


def _video_index() -> VideoIndex:
    pixels = ImagePixels(
        1,
        1,
        "uint8",
        4,
        ("red", "green", "blue", "alpha"),
        bytes((0, 0, 0, 255)),
        "bt709",
        "none",
    )
    frames = tuple(
        SourceFrame(i, i, Fraction(1, 30), Fraction(i, 30), Fraction(i + 1, 30), 0)
        for i in range(2)
    )
    return VideoIndex(
        0,
        "h264",
        1,
        1,
        frames,
        Fraction(2, 30),
        "yuv420p",
        (8, 8, 8),
        ("y", "cb", "cr"),
        "none",
        "bt709",
        "limited",
        "bt709",
        "left",
        pixels,
    )


def test_video_cursor_uses_pts_intervals_and_preserves_loop_remainder() -> None:
    index = _video_index()
    cursor = PlaybackCursor(index, "loop")
    first = cursor.select(Fraction(1, 30))
    assert first.source_frame.index == 1
    assert first.loop_index == 0
    wrapped = cursor.select(Fraction(5, 60))
    assert wrapped.source_frame.index == 0
    assert wrapped.loop_index == 1
    assert wrapped.target == Fraction(1, 60)
    assert wrapped.playback_generation == 1


def test_video_pts_are_normalized_to_the_first_presentation_timestamp() -> None:
    origin = Fraction(9000, 90000)
    assert _relative_pts(9000, Fraction(1, 90000), origin) == 0
    assert _relative_pts(12000, Fraction(1, 90000), origin) == Fraction(1, 30)


def test_ffv1_configuration_record_version_is_exactly_three() -> None:
    # The first unsigned range-coded symbols decode to 3 and 4, respectively.
    version3 = bytes.fromhex("4fb00000000000000000000000000000")
    version4 = bytes.fromhex("5fa00000000000000000000000000000")
    assert read_ffv1_version(version3) == 3
    assert read_ffv1_version(version4) == 4
    require_ffv1_version3(version3)
    with pytest.raises(FFV1ConfigurationError, match="received version 4"):
        require_ffv1_version3(version4)
    with pytest.raises(FFV1ConfigurationError, match="truncated"):
        require_ffv1_version3(b"\x00")


def test_video_cursor_holds_the_final_valid_frame_without_overshoot() -> None:
    index = _video_index()
    cursor = PlaybackCursor(index, "hold_final_frame")
    ended = cursor.select(Fraction(1, 5))
    later = cursor.select(Fraction(1, 2))
    assert ended.source_frame.index == 1
    assert later.source_frame.index == 1
    assert ended.target == later.target == index.duration
    assert ended.disposition == later.disposition == "end_hold"


def test_video_cursor_changes_end_behavior_without_resetting_playback_generation():
    cursor = PlaybackCursor(_video_index(), "loop")
    looped = cursor.select(Fraction(5, 60))
    assert looped.loop_index == 1
    cursor.set_end_behavior("hold_final_frame")
    held = cursor.select(Fraction(1, 5))
    assert held.loop_index == 1
    assert held.playback_generation == 1
    assert held.disposition == "end_hold"
    cursor.set_end_behavior("loop")
    resumed = cursor.select(Fraction(1, 5))
    assert resumed.loop_index == 3
    assert resumed.playback_generation == 3


def test_video_session_registers_and_selects_each_incompatible_asset_variant():
    class Playback:
        def __init__(self):
            self.registered = []
            self.presented = []
            self.reset_ids = []

        def register(self, **values):
            self.registered.append(values)

        def present(self, instance_id, playback_seconds, *, end_behavior):
            self.presented.append((instance_id, playback_seconds, end_behavior))
            return instance_id

        def reset(self, instance_id):
            self.reset_ids.append(instance_id)
            return len(self.reset_ids)

    class Budget:
        def __init__(self):
            self.reservations = []

        def reserve(self, **values):
            self.reservations.append(values)

    def setting(asset_id, end_behavior="loop"):
        return VideoSettings.model_construct(
            instance_id="shared-instance",
            space=None,
            initial=None,
            width=None,
            height=None,
            opacity=None,
            motion=None,
            reset=False,
            assignments=(),
            feedback=(),
            kind="video",
            asset_id=asset_id,
            sampling="nearest",
            initial_playback=Time(seconds="0"),
            end_behavior=end_behavior,
        )

    index_a = _video_index()
    index_b = replace(_video_index(), width=2)
    playback, budget = Playback(), Budget()
    session = VideoSession(playback, budget)
    artifact = type(
        "Artifact",
        (),
        {
            "epochs": (
                type("Epoch", (), {"settings": (setting("movie-a"),)})(),
                type(
                    "Epoch", (), {"settings": (setting("movie-b", "hold_final_frame"),)}
                )(),
            ),
            "identity": type(
                "Identity", (), {"trial_id": "trial", "prepared_generation": "prepared"}
            )(),
            "display": type("Display", (), {"active_outputs": (1, 2)})(),
        },
    )()
    asset_a = type("Asset", (), {"profile": "mp4_h264_sdr8_v1", "source": object()})()
    asset_b = type("Asset", (), {"profile": "mp4_h264_sdr8_v1", "source": object()})()
    bundle = type(
        "Bundle",
        (),
        {
            "asset_set": type(
                "AssetSet",
                (),
                {"by_id": lambda self: {"movie-a": asset_a, "movie-b": asset_b}},
            )(),
            "prepared_content": {"movie-a": index_a, "movie-b": index_b},
        },
    )()
    session.register_trial(artifact, bundle)

    assert len(playback.registered) == 2
    assert [item["index"].width for item in playback.registered] == [1, 2]
    assert [item["gpu_bytes"] for item in budget.reservations] == [32, 64]
    movie_a_setting, movie_b_setting = (
        artifact.epochs[0].settings[0],
        artifact.epochs[1].settings[0],
    )
    assert (
        session.present("trial", movie_a_setting, {"playback": 0.0})
        == playback.registered[0]["instance_id"]
    )
    assert (
        session.present("trial", movie_b_setting, {"playback": 0.0})
        == playback.registered[1]["instance_id"]
    )
    session.reset("trial", "shared-instance")
    assert set(playback.reset_ids) == {
        item["instance_id"] for item in playback.registered
    }


def test_bounded_video_worker_hands_off_a_leased_exact_frame_off_render_thread() -> (
    None
):
    ready = threading.Event()
    worker_ids: list[int] = []

    class Context:
        def decode(self, frame: SourceFrame) -> ImagePixels:
            worker_ids.append(threading.get_ident())
            ready.set()
            return ImagePixels(
                1,
                1,
                "uint8",
                4,
                ("red", "green", "blue", "alpha"),
                bytes((frame.index, 0, 0, 255)),
                "bt709",
                "none",
            )

        def close(self) -> None:
            worker_ids.append(threading.get_ident())

    class Source:
        pass

    playback = VideoPlayback(
        decoder_threads=1,
        decoder_contexts=1,
        codec_threads_per_context=1,
        codec_threads_total=1,
        decoded_frames_per_instance=2,
        decoded_bytes_total=16,
        decoder_working_bytes_total=128,
        decoder_factory=lambda source, index, profile, threads: Context(),
    )
    playback.register(
        instance_id="trial/video",
        evidence_instance_id="video",
        asset_id="movie",
        profile="mp4_h264_sdr8_v1",
        source=Source(),
        index=_video_index(),
        prepared_generation="prepared-1",
        end_behavior="loop",
    )
    playback.start(
        announce=lambda resource_key, path: None,
        deadline_ns=time.perf_counter_ns() + 1_000_000_000,
    )
    first = playback.present("trial/video", Fraction(1, 30))
    assert (
        first.selection.source_frame_index == 0
    )  # Initial content is already prepared.
    assert first.selection.disposition == "starvation_hold"
    first.release()
    assert ready.wait(1)
    current = playback.present("trial/video", Fraction(1, 30))
    assert current.selection.source_frame_index == 1
    assert current.selection.disposition == "current"
    assert current.decoded is not None
    assert current.decoded.pixels.pixels == bytes((1, 0, 0, 255))
    render_thread = threading.get_ident()
    current.release()
    assert worker_ids and all(item != render_thread for item in worker_ids)
    assert playback.cleanup(deadline_ns=time.perf_counter_ns() + 1_000_000_000) == ()


@pytest.mark.parametrize("external", [False, True])
def test_arena_bundle_subresource_ids_validate_and_bind_gpu_textures(
    tmp_path, monkeypatch, external
):
    from types import SimpleNamespace

    from PIL import Image

    from cephvr.visual_stimulus.config.models.artifact_models import ResourceManifest
    from cephvr.visual_stimulus.rendering import arena_gpu
    from cephvr.visual_stimulus.resources.assets import arena_subresource_id
    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    document, binary = glb_fixture(texture=True, external=external)
    binary += b"\0" * (-len(binary) % 4)
    offset = len(binary)
    binary += struct.pack("<6f", 0, 0, 1, 0, 0, 1)
    document["bufferViews"].append(
        {"buffer": 0, "byteOffset": offset, "byteLength": 24}
    )
    document["accessors"].append(
        {"bufferView": 2, "componentType": 5126, "type": "VEC2", "count": 3}
    )
    document["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"] = 2
    document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
    image = io.BytesIO()
    Image.new("RGB", (2, 2), (123, 45, 67)).save(image, format="PNG")
    if external:
        (tmp_path / "mesh.bin").write_bytes(binary)
        (tmp_path / "textures").mkdir()
        (tmp_path / "textures/fish.png").write_bytes(image.getvalue())
    else:
        offset = len(binary)
        binary += image.getvalue()
        document["bufferViews"].append(
            {"buffer": 0, "byteOffset": offset, "byteLength": len(image.getvalue())}
        )
        document["images"] = [{"bufferView": 3, "mimeType": "image/png"}]
    document["buffers"][0]["byteLength"] = len(binary)
    (tmp_path / "arena.glb").write_bytes(pack_glb(document, binary))
    sources = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            sources.append(self)

        def independent_reader(self):
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    asset_id = "a" * 128
    program = SimpleNamespace(
        assets=(
            Asset(
                asset_id=asset_id,
                logical_path="arena.glb",
                profile="glb2_static_unlit_v1",
                color_override=None,
            ),
        ),
        instances=(),
        sequence=(),
    )
    bundle = prepare_resources(
        program,
        tmp_path,
        BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000),
        announce=lambda *_: None,
        source_factory=Source,
        snapshot_limit_bytes=100_000,
        video_index_limit_bytes=1000,
        glb_element_limit=1000,
        output_count=4,
    )
    manifest = ResourceManifest.model_validate_json(bundle.manifest.model_dump_json())
    ids = {item.fingerprint.resource_id for item in manifest.resources}
    texture_id = arena_subresource_id(asset_id, "texture", 0)
    assert texture_id in ids
    assert all(len(identifier) <= 128 and ":" not in identifier for identifier in ids)
    assert all(set(item.dependencies) <= ids for item in manifest.resources)
    expected_sources = 3 if external else 1
    assert len(sources) == expected_sources
    assert len(bundle.asset_set.assets) == expected_sources
    assert len(ids) == expected_sources + 1
    allocations, uploaded = [], []

    class Allocation:
        def __init__(self):
            self.released = False
            allocations.append(self)

        def release(self):
            self.released = True

    class Context:
        def buffer(self, _):
            return Allocation()

    def upload(_output, _context, pixels, _opaque, _retain):
        uploaded.append(pixels)
        return Allocation()

    monkeypatch.setattr(arena_gpu, "configure_sampler", lambda *_: None)
    owner = arena_gpu.upload_arena(
        bundle.prepared_content[asset_id],
        {"front": SimpleNamespace(context=Context())},
        bundle.prepared_content,
        asset_id,
        upload,
    )
    assert len(uploaded) == 2
    assert all(pixels is bundle.prepared_content[texture_id] for pixels in uploaded)
    owner.release()
    assert allocations and all(item.released for item in allocations)
    assert bundle.asset_set.close() == ()
    assert all(source.closed for source in sources)


def test_glb_indexed_unlit_geometry_and_sampler_sources_are_preserved():
    document, binary = glb_fixture(texture=True, external=True)
    observed = []

    def resolve(path):
        observed.append(path)
        return binary if path == "mesh.bin" else b"\x89PNG\r\n\x1a\n"

    scene = parse_glb(
        pack_glb(document, binary), max_bytes=10000, max_elements=20, resolve=resolve
    )
    assert scene.nodes[0].primitives[0].indices == (0, 1, 2)
    assert scene.materials[0].base_color_factor == (0.5, 0.25, 1, 1)
    assert scene.textures[0].wrap_s == 33648
    assert scene.textures[0].min_filter == 9987
    assert observed == ["mesh.bin", "textures/fish.png"]


def test_glb_rejects_out_of_bounds_indices_and_repeated_scene_nodes():
    document, binary = glb_fixture()
    binary = binary[:-2] + struct.pack("<H", 100)
    with pytest.raises(GLBError, match="index"):
        parse_glb(pack_glb(document, binary), max_bytes=10000, max_elements=20)
    document, binary = glb_fixture()
    document["nodes"][0]["children"] = [0]
    with pytest.raises(GLBError, match="cyclic"):
        parse_glb(pack_glb(document, binary), max_bytes=10000, max_elements=20)


def test_glb_reserves_workspace_before_decoding_accessors():
    document, binary = glb_fixture()
    reservations = []
    parse_glb(
        pack_glb(document, binary),
        max_bytes=10000,
        max_elements=20,
        reserve_workspace=reservations.append,
    )
    assert len(reservations) == 3
    assert reservations[0] < reservations[1] < reservations[2]


def test_png_header_rejects_animated_content_before_pixel_allocation():
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + b"\x00" * 4

    header = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", 12, 10, 16, 6, 0, 0, 0)
    )
    assert image_shape(header + chunk(b"IEND", b""), "png_uint_v1") == (12, 10, 4, 16)
    with pytest.raises(ValueError, match="animated"):
        image_shape(header + chunk(b"acTL", struct.pack(">II", 2, 0)), "png_uint_v1")


def test_invalid_calibration_releases_source_and_parse_workspace(tmp_path):
    from types import SimpleNamespace as NS

    from cephvr.visual_stimulus.resources.calibration import prepare_calibration

    path = tmp_path / "broken.json"
    path.write_text('{"not": "a calibration"}')
    sources = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            sources.append(self)

        def independent_reader(self):
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    budget = BoundedBudget(cpu_limit=1000000, gpu_limit=1000000)
    display = NS(
        active_mappings=(
            NS(mapping_id="view", geometric_profile=NS(logical_path="broken.json")),
        )
    )
    with pytest.raises(ValueError):
        prepare_calibration(
            display,
            tmp_path,
            announce=lambda *_: None,
            budget=budget,
            max_document_bytes=1000,
            owner_prefix="test",
            source_factory=Source,
        )
    assert sources and all(source.closed for source in sources)
    assert budget.usage.cpu_bytes == 0 and budget.usage.gpu_bytes == 0


def test_video_cursor_reset_restarts_loop_clock_and_releases_final_hold():
    from cephvr.visual_stimulus.resources.video_decoder import VideoPlaybackError

    cursor = PlaybackCursor(_video_index(), "loop")
    assert cursor.select(Fraction(1, 5)).playback_generation == 3
    with pytest.raises(VideoPlaybackError, match="behind its retained loop"):
        cursor.select(0.0)
    cursor.reset()
    restarted = cursor.select(-1.0)
    assert restarted.source_frame.index == 0
    assert restarted.target == 0
    assert restarted.loop_index == 0
    assert restarted.playback_generation == 4
    cursor.set_end_behavior("hold_final_frame")
    assert cursor.select(1.0).disposition == "end_hold"
    assert cursor.select(0.0).disposition == "end_hold"
    cursor.reset()
    assert cursor.select(0.0).disposition == "selected"


def _playback_for_test(decoder_factory=None):
    playback = VideoPlayback(
        decoder_threads=1,
        decoder_contexts=1,
        codec_threads_per_context=1,
        codec_threads_total=1,
        decoded_frames_per_instance=2,
        decoded_bytes_total=16,
        decoder_working_bytes_total=128,
        decoder_factory=decoder_factory,
    )
    playback.register(
        instance_id="video",
        asset_id="movie",
        profile="mp4_h264_sdr8_v1",
        source=None,
        index=_video_index(),
        prepared_generation="prepared-1",
        end_behavior="loop",
    )
    return playback


@pytest.mark.parametrize("change", ["request", "frame", "generation", "loop"])
def test_video_delivery_coalesces_requests_but_rejects_stale_content(change):
    from cephvr.visual_stimulus.resources.video import DecodedFrameLease
    from cephvr.visual_stimulus.resources.video_selection import VideoTarget

    playback = _playback_for_test()
    instance = playback._instances["video"]
    selection = instance.cursor.select(Fraction(1, 30))
    original = VideoTarget("prepared-1", 0, 1, selection)
    current = replace(original, request_id=2)
    if change == "frame":
        current = replace(
            current, selection=replace(selection, source_frame=instance.index.frames[0])
        )
    elif change == "generation":
        current = replace(current, playback_generation=1)
    elif change == "loop":
        current = replace(current, selection=replace(selection, loop_index=1))
    else:
        current = replace(current, selection=replace(selection, target=Fraction(3, 60)))
    releases = []
    lease = DecodedFrameLease(
        original, instance.index.initial_pixels, _release_callback=releases.append
    )
    instance.ready = lease
    instance.latest = current
    result = playback.poll("video", target=current)
    if change == "request":
        assert result is lease
        assert result.target is current
        assert not releases
        result.release()
    else:
        assert result is None
        assert releases == [lease]
    lease.release()
    assert releases == [lease]  # Release is idempotent.


def test_video_worker_discards_decode_from_before_cursor_reset():
    decoding = threading.Event()
    proceed = threading.Event()
    decoded_generations = []
    closed = []

    class Context:
        def decode(self, frame):
            decoded_generations.append(frame.index)
            if len(decoded_generations) == 1:
                decoding.set()
                assert proceed.wait(2)
            return _video_index().initial_pixels

        def close(self):
            closed.append(threading.get_ident())

    playback = _playback_for_test(lambda *args: Context())
    playback.start(
        announce=lambda *args: None,
        deadline_ns=time.perf_counter_ns() + 1_000_000_000,
    )
    try:
        playback.publish("video", Fraction(1, 30))
        assert decoding.wait(2)
        playback.reset("video")
        current = playback.publish("video", Fraction(1, 30))
        proceed.set()
        with playback._condition:
            assert playback._condition.wait_for(
                lambda: playback._instances["video"].ready is not None, timeout=2
            )
        lease = playback.poll("video", target=current)
        assert lease is not None
        assert lease.target.playback_generation == 1
        assert decoded_generations == [1, 1]
        lease.release()
    finally:
        proceed.set()
        assert (
            playback.cleanup(deadline_ns=time.perf_counter_ns() + 2_000_000_000) == ()
        )
    assert len(closed) == 1
    assert closed[0] != threading.get_ident()


@pytest.mark.parametrize(
    ("widths", "decoded_limit", "working_limit", "accepted"),
    [
        ((2, 2, 1), 32, 128, 2),
        ((2, 2, 1), 64, 96, 2),
        ((1, 1, 2), 32, 96, 3),
    ],
)
def test_video_registration_sums_mixed_frame_sizes_atomically(
    widths, decoded_limit, working_limit, accepted
):
    playback = VideoPlayback(
        decoder_threads=1,
        decoder_contexts=3,
        codec_threads_per_context=1,
        codec_threads_total=3,
        decoded_frames_per_instance=2,
        decoded_bytes_total=decoded_limit,
        decoder_working_bytes_total=working_limit,
    )
    for ordinal, width in enumerate(widths):
        base = _video_index()
        pixels = replace(
            base.initial_pixels, width=width, height=2, pixels=bytes(width * 2 * 4)
        )
        index = replace(base, width=width, height=2, initial_pixels=pixels)

        def register(ordinal=ordinal, index=index):
            playback.register(
                instance_id=str(ordinal),
                asset_id="movie",
                profile="mp4_h264_sdr8_v1",
                source=None,
                index=index,
                prepared_generation="prepared-1",
                end_behavior="loop",
            )

        if ordinal < accepted:
            register()
        else:
            for _ in range(2):
                with pytest.raises(MemoryError, match="aggregate decode memory"):
                    register()
    assert len(playback._instances) == accepted


@pytest.mark.parametrize("source_dtype", ["uint8", "uint16"])
def test_image_recipe_protects_and_fingerprints_its_relative_input(
    tmp_path, source_dtype
):
    import hashlib
    from types import SimpleNamespace

    import numpy as np
    import tifffile
    from PIL import Image

    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    pixels = np.arange(45, dtype=source_dtype).reshape(3, 5, 3)
    stream = io.BytesIO()
    tifffile.imwrite(stream, pixels, photometric="rgb")
    encoded = stream.getvalue()
    with Image.open(io.BytesIO(encoded)) as original:
        expected = np.asarray(original.convert("RGB"))
    (tmp_path / "source.tif").write_bytes(encoded)
    raw = b'{"pattern":"image","params":{"texture_path":"source.tif"}}'
    (tmp_path / "recipe.json").write_bytes(raw)
    sources = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            sources.append(self)

        def independent_reader(self):
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    program = SimpleNamespace(
        assets=(
            Asset(
                asset_id="recipe",
                logical_path="recipe.json",
                profile="cephvr1_texture_json_v1",
                color_override=None,
            ),
        ),
        sequence=(),
        instances=(),
    )
    budget = BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000)
    bundle = prepare_resources(
        program,
        tmp_path,
        budget,
        announce=lambda *_: None,
        snapshot_limit_bytes=1000,
        video_index_limit_bytes=1000,
        glb_element_limit=1000,
        max_document_bytes=1000,
        source_factory=Source,
    )
    np.testing.assert_array_equal(bundle.prepared_content["recipe"].pixels, expected)
    recipe_resource, image_resource = bundle.manifest.resources
    assert recipe_resource.dependencies == (image_resource.fingerprint.resource_id,)
    assert image_resource.fingerprint.logical_path == "source.tif"
    assert image_resource.fingerprint.sha256 == hashlib.sha256(encoded).hexdigest()
    assert image_resource.interpretation is None
    assert image_resource.provider_compatibility == "Pillow-cephvr1-rgb8-input-v1"
    assert image_resource.fingerprint.resource_id not in bundle.prepared_content
    assert len(bundle.asset_set.assets) == 2
    bundle.asset_set.close()
    assert all(source.closed for source in sources)
    (tmp_path / "recipe.json").write_text(
        '{"pattern":"image","params":{"texture_path":"../outside.png"}}'
    )
    budget = BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000)
    with pytest.raises(ValueError, match="relative"):
        prepare_resources(
            program,
            tmp_path,
            budget,
            announce=lambda *_: None,
            snapshot_limit_bytes=1000,
            video_index_limit_bytes=1000,
            glb_element_limit=1000,
            max_document_bytes=1000,
            source_factory=Source,
        )
    assert all(source.closed for source in sources)
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0


@pytest.mark.parametrize("name", ["checkerboard", "noise", "sine_grating"])
def test_demo_image_recipes_preserve_authored_png_pixels(name, demo_assets):
    import numpy as np
    from PIL import Image

    from cephvr.visual_stimulus.resources.recipe_dependencies import (
        decode_recipe_image,
        image_dependency,
    )
    from cephvr.visual_stimulus.resources.texture_recipe import (
        generate_texture_recipe,
        parse_texture_recipe,
    )

    root = demo_assets
    logical_path = f"textures/{name}.texture.json"
    asset = Asset(
        asset_id="demo",
        logical_path=logical_path,
        profile="cephvr1_texture_json_v1",
        color_override=None,
    )
    recipe = parse_texture_recipe((root / logical_path).read_bytes())
    dependency = image_dependency(root, asset, recipe)
    assert dependency is not None
    source = (root / dependency.logical_path).read_bytes()
    reservations = []
    pixels = decode_recipe_image(
        dependency, source, lambda *shape: reservations.append(shape)
    ).pixels
    generated = generate_texture_recipe(recipe, image_pixels=pixels)
    with Image.open(io.BytesIO(source)) as original:
        expected = np.asarray(original.convert("RGB"))
    np.testing.assert_array_equal(generated, expected)
    assert reservations == [(expected.shape[1], expected.shape[0], 3, 8)]
    assert recipe.tile_width_mm == recipe.tile_height_mm == 40


def test_deferred_recipes_validate_sequentially_without_retaining_all_pixels(tmp_path):
    from types import SimpleNamespace

    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    assets = []
    sources = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            sources.append(self)

        def independent_reader(self):
            assert not self.closed
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    for index in range(5):
        path = tmp_path / f"recipe{index}.json"
        path.write_text(
            json.dumps(
                {
                    "pattern": "noise_binary",
                    "params": {"texture_resolution": 32, "seed": index},
                }
            )
        )
        assets.append(
            Asset(
                asset_id=f"recipe{index}",
                logical_path=path.name,
                profile="cephvr1_texture_json_v1",
                color_override=None,
            )
        )
    program = SimpleNamespace(assets=tuple(assets), sequence=(), instances=())
    budget = BoundedBudget(cpu_limit=300_000, gpu_limit=100_000)
    bundle = prepare_resources(
        program,
        tmp_path,
        budget,
        announce=lambda *_: None,
        snapshot_limit_bytes=300_000,
        video_index_limit_bytes=1000,
        glb_element_limit=1000,
        max_document_bytes=1000,
        source_factory=Source,
        defer_images=True,
    )
    assert len(bundle.image_sources) == 5
    assert not bundle.prepared_content
    assert all(asset.data is None for asset in bundle.asset_set.assets)
    assert bundle.asset_set.cpu_bytes == 0
    metadata_bytes = sum(
        4096 + 4 * len(asset.model_dump_json().encode("utf-8")) for asset in assets
    )
    assert budget.usage.cpu_bytes == metadata_bytes
    assert budget.usage.gpu_bytes == 0
    assert len({source.key for source in bundle.image_sources.values()}) == 5
    for source in bundle.image_sources.values():
        budget.reserve(
            owner="test-loader", cpu_bytes=source.cpu_bytes, gpu_bytes=source.gpu_bytes
        )
        first = source.load(budget.check_cancelled_or_expired)
        assert len(first) == 32 * 32 * 16
        assert first == source.load(budget.check_cancelled_or_expired)
        del first
        budget.release(owner="test-loader")
    assert not any(source.closed for source in sources)
    bundle.asset_set.close()
    assert all(source.closed for source in sources)


def test_image_worker_loads_off_thread_and_holds_reservation_until_handoff():
    import time

    from cephvr.visual_stimulus.resources.image_source import ImageSource
    from cephvr.visual_stimulus.resources.image_worker import ImageWorker

    budget = BoundedBudget(cpu_limit=100, gpu_limit=100)
    worker = ImageWorker(budget)
    started = threading.Event()
    proceed = threading.Event()
    main_thread = threading.get_ident()
    load_threads = []

    def load(check):
        load_threads.append(threading.get_ident())
        started.set()
        while not proceed.wait(0.001):
            check()
        check()
        return b"linear-rgba"

    source = ImageSource("image-key", 1, 1, 40, 16, load)
    try:
        assert worker.request(source)
        assert started.wait(1)
        assert not worker.request(source)
        assert budget.usage.cpu_bytes == 40
        assert worker.result() is None
        proceed.set()
        deadline = time.monotonic() + 1
        result = worker.result()
        while result is None and time.monotonic() < deadline:
            time.sleep(0.001)
            result = worker.result()
        assert result is not None and result.error is None
        assert result.pixels == b"linear-rgba"
        assert load_threads and load_threads[0] != main_thread
        assert worker.busy
        assert budget.usage.cpu_bytes == 40
        worker.release_result()
        assert worker.result() is None
        assert not worker.busy
        assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0
    finally:
        proceed.set()
        assert worker.close(time.monotonic_ns() + 1_000_000_000)


def test_image_worker_releases_pixel_payload_after_owner_release():
    import gc
    import time
    import weakref

    from cephvr.visual_stimulus.resources.image_source import ImageSource
    from cephvr.visual_stimulus.resources.image_worker import ImageWorker

    class Payload:
        pass

    payload_ref = None

    def load(check):
        nonlocal payload_ref
        check()
        payload = Payload()
        payload_ref = weakref.ref(payload)
        return payload  # type: ignore[return-value]

    budget = BoundedBudget(cpu_limit=100, gpu_limit=100)
    worker = ImageWorker(budget)
    source = ImageSource("weak-pixels", 1, 1, 32, 16, load)
    try:
        assert worker.request(source)
        deadline = time.monotonic() + 1
        result = worker.result()
        while result is None and time.monotonic() < deadline:
            time.sleep(0.001)
            result = worker.result()
        assert result is not None and result.pixels is not None
        assert payload_ref is not None and payload_ref() is not None
        assert budget.usage.cpu_bytes == 32
        worker.release_result()
        del result
        gc.collect()
        assert payload_ref() is None
        assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0
    finally:
        if worker.result() is not None:
            worker.release_result()
        assert worker.close(time.monotonic_ns() + 1_000_000_000)


@pytest.mark.parametrize("cancel_during_load", [False, True])
def test_image_worker_cancellation_is_shared_and_retains_result_reservation(
    cancel_during_load,
):
    import time

    from cephvr.visual_stimulus.resources.image_source import ImageSource
    from cephvr.visual_stimulus.resources.image_worker import ImageWorker

    cancelled = threading.Event()
    started = threading.Event()
    budget = BoundedBudget(cpu_limit=100, gpu_limit=100, cancelled=cancelled)
    calls = []

    def load(check):
        calls.append(True)
        started.set()
        while True:
            check()
            time.sleep(0.001)

    source = ImageSource("cancelled", 1, 1, 28, 16, load)
    if not cancel_during_load:
        cancelled.set()
    worker = ImageWorker(budget)
    try:
        assert worker.request(source)
        if cancel_during_load:
            assert started.wait(1)
            cancelled.set()
        deadline = time.monotonic() + 1
        result = worker.result()
        while result is None and time.monotonic() < deadline:
            time.sleep(0.001)
            result = worker.result()
        assert result is not None and result.pixels is None
        assert isinstance(result.error, RuntimeError)
        assert "image loading cancelled" in str(result.error)
        assert bool(calls) is cancel_during_load
        assert budget.usage.cpu_bytes == 28
        worker.release_result()
        assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0
    finally:
        if worker.result() is not None:
            worker.release_result()
        assert worker.close(time.monotonic_ns() + 1_000_000_000)


def test_image_worker_close_timeout_retains_reservation_until_thread_join():
    import time

    from cephvr.visual_stimulus.resources.image_source import ImageSource
    from cephvr.visual_stimulus.resources.image_worker import ImageWorker

    budget = BoundedBudget(cpu_limit=100, gpu_limit=100)
    worker = ImageWorker(budget)
    started = threading.Event()
    proceed = threading.Event()

    def load(check):
        started.set()
        assert proceed.wait(2)
        return b"decoded"

    source = ImageSource("slow", 1, 1, 52, 16, load)
    assert worker.request(source)
    assert started.wait(1)
    assert not worker.close(time.monotonic_ns() + 1_000_000)
    assert budget.usage.cpu_bytes == 52
    proceed.set()
    assert worker.close(time.monotonic_ns() + 1_000_000_000)
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0


def test_glb_retains_declared_arena_geometry_from_protected_content(tmp_path):
    document, binary = glb_fixture()
    geometry = {"shape": "rectangular", "width": 500, "depth": 400}
    document["extras"] = {"cephvr": {"metadata": {"geometry": geometry}}}
    scene = parse_glb(pack_glb(document, binary), max_bytes=10000, max_elements=20)
    assert json.loads(scene.arena_geometry_json) == geometry
    from cephvr.visual_stimulus.resources.arena_geometry import read_geometry_preview

    path = tmp_path / "arena.glb"
    path.write_bytes(pack_glb(document, binary))
    assert json.loads(read_geometry_preview(path, max_document_bytes=10000)) == geometry
    with pytest.raises(ValueError, match="oversized"):
        read_geometry_preview(path, max_document_bytes=1)
    from dataclasses import replace

    from tests.visual_stimulus.support import make_compile_context

    from cephvr.gui.arena_limits import boundary_document
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.visual_stimulus.compiler import compile_trial
    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    class Source:
        def __init__(self, path):
            self.path = path
            self.closed = False

        def independent_reader(self):
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    program = add_stimulus(blank_program(), 0, "3D arena", ())
    budget = BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000)
    bundle = prepare_resources(
        program,
        tmp_path,
        budget,
        announce=lambda *_: None,
        snapshot_limit_bytes=100_000,
        video_index_limit_bytes=1000,
        glb_element_limit=1000,
        source_factory=Source,
    )
    try:
        context = replace(
            make_compile_context(program.model_dump_json()),
            manifest=bundle.manifest,
            arena_boundaries=boundary_document(program, ""),
            arena_geometry={
                key: value.arena_geometry_json
                for key, value in bundle.prepared_content.items()
            },
        )
        artifact = compile_trial(
            program, context, max_expanded_epochs=8, max_prepared_plan_bytes=1_000_000
        )
        assert artifact.arena_boundaries.bindings[0].region.kind == "convex_polygon_xy"
        assert artifact.arena_boundaries.bindings[0].region.margin_mm == 30
        assert artifact.arena_boundaries.bindings[0].region.vertices_mm == (
            (-250, -200),
            (250, -200),
            (250, 200),
            (-250, 200),
        )
        assert (
            artifact.manifest.resources[0].fingerprint.sha256
            == bundle.asset_set.assets[0].sha256
        )
    finally:
        assert bundle.asset_set.close() == ()
    assert bundle.asset_set.assets[0].source.closed


def test_prepared_manifest_detects_shader_content_changes(tmp_path, monkeypatch):
    from tests.visual_stimulus.support import make_program

    from cephvr.visual_stimulus.rendering import shaders
    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    def manifest():
        return prepare_resources(
            make_program(),
            tmp_path,
            BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000),
            announce=lambda *_: None,
            snapshot_limit_bytes=1_000_000,
            video_index_limit_bytes=1000,
            glb_element_limit=1000,
        ).manifest

    before = manifest()
    monkeypatch.setattr(
        shaders,
        "_LAYER_FRAGMENT",
        shaders._LAYER_FRAGMENT.replace("float wave = cos(", "float wave = sin("),
    )
    after = manifest()
    assert before.provenance != after.provenance
    assert before.resources == after.resources == ()
    roles = {item.role for item in after.provenance}
    assert {"renderer", "shader", "color_transform", "os"} <= roles


def test_renderer_source_digest_detects_edits_and_is_relocatable(tmp_path):
    import shutil

    from cephvr.visual_stimulus.resources.provenance import source_digest

    root = tmp_path / "release-a"
    root.mkdir()
    source = root / "render.py"
    source.write_text("def render(): return 1\n")
    before = source_digest(root, lambda: None)
    shutil.copytree(root, tmp_path / "relocated")
    assert before == source_digest(tmp_path / "relocated", lambda: None)
    source.write_text("def render(): return 2\n")
    assert before != source_digest(root, lambda: None)

    def cancelled():
        raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError):
        source_digest(root, cancelled)
    source.unlink()
    with pytest.raises(ValueError, match="source is unavailable"):
        source_digest(root, lambda: None)


def test_shared_asset_library_reuses_files_and_retains_old_versions(tmp_path):
    from types import SimpleNamespace

    from cephvr.visual_stimulus.resources.prepare import prepare_resources

    class Source:
        def __init__(self, path):
            self.path = path

        def independent_reader(self):
            return self.path.open("rb")

        def close_after_consumers(self):
            pass

    for name, size in (("v1", 8), ("v2", 16)):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "texture.json").write_text(
            json.dumps(
                {
                    "pattern": "checker",
                    "params": {"texture_resolution": size, "tile_width_mm": 40},
                }
            )
        )
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    def prepare(relative):
        program = SimpleNamespace(
            assets=(
                Asset(
                    asset_id="recipe",
                    logical_path=relative,
                    profile="cephvr1_texture_json_v1",
                    color_override=None,
                ),
            ),
            instances=(),
            sequence=(),
        )
        bundle = prepare_resources(
            program,
            tmp_path,
            BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000),
            announce=lambda *_: None,
            snapshot_limit_bytes=100_000,
            max_document_bytes=1000,
            video_index_limit_bytes=1000,
            glb_element_limit=1000,
            source_factory=Source,
        )
        bundle.asset_set.close()
        return bundle.manifest.resources[0].fingerprint

    first = prepare("v1/texture.json")
    assert prepare("v1/texture.json") == first
    second = prepare("v2/texture.json")
    assert second.sha256 != first.sha256
    assert prepare("v1/texture.json") == first
    assert {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


@pytest.mark.parametrize(
    "pixel_format,target_bytes",
    [("rgba8_top_down", 4), ("r10g10b10a2_le_top_down", 16)],
)
def test_review_gpu_budget_includes_both_targets_and_bounded_pool(
    pixel_format, target_bytes
):
    assert review_capture_gpu_bytes(1280, 1000, 3, pixel_format) == 1280 * 1000 * (
        2 * target_bytes + 3 * 4
    )
    with pytest.raises(ValueError):
        review_capture_gpu_bytes(1280, 1000, 0, pixel_format)
    with pytest.raises(ValueError):
        review_capture_gpu_bytes(1280, 1000, 3, "unknown")


@pytest.mark.parametrize("dtype", ["uint8", "uint16"])
@pytest.mark.parametrize("channels", [0, 1, 3])
@pytest.mark.parametrize("opaque", [False, True])
def test_linear_opaque_upload_preserves_every_code_and_source(dtype, channels, opaque):
    np = pytest.importorskip("numpy")
    from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes

    maximum = np.iinfo(dtype).max
    codes = np.arange(maximum + 1, dtype=dtype).reshape(-1, 16)
    pixels = codes if channels == 0 else np.repeat(codes[..., None], channels, axis=2)
    if channels == 3:
        pixels[..., 1] = np.roll(codes, 1, axis=1)
        pixels[..., 2] = np.roll(codes, 2, axis=0)
    pixels = pixels[::-1, ::-1]  # Non-contiguous inputs must preserve orientation.
    original = pixels.copy()
    pixels.setflags(write=False)
    source = pixels.astype(np.float32) / float(maximum)
    expected = np.ones((*source.shape[:2], 4), dtype=np.float32)
    expected[..., :3] = source[..., None] if channels == 0 else source
    image = ImagePixels(
        pixels.shape[1],
        pixels.shape[0],
        dtype,
        channels or 1,
        ("gray",) if channels < 3 else ("red", "green", "blue"),
        pixels,
        "linear",
        "none",
    )
    assert linear_rgba_bytes(image, opaque=opaque) == expected[::-1].tobytes()
    np.testing.assert_array_equal(pixels, original)


@pytest.mark.parametrize("profile", ["png_uint_v1", "tiff_uint_v1"])
@pytest.mark.parametrize("dtype", ["uint8", "uint16"])
def test_untagged_images_default_to_linear_intensities(profile, dtype):
    np = pytest.importorskip("numpy")
    pixels = np.full((2, 3, 3), 128 if dtype == "uint8" else 32768, dtype=dtype)
    encoded = io.BytesIO()
    if profile == "png_uint_v1":
        imagecodecs = pytest.importorskip("imagecodecs")
        encoded.write(imagecodecs.png_encode(pixels))
    else:
        tifffile = pytest.importorskip("tifffile")
        tifffile.imwrite(encoded, pixels, photometric="rgb")
    asset = Asset(
        asset_id="noise",
        logical_path="textures/noise",
        profile=profile,
        color_override=None,
    )
    decoded = decode_image(asset, encoded.getvalue())
    assert decoded.transfer == "linear"
    np.testing.assert_array_equal(decoded.pixels, pixels)
    from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes

    linear = np.frombuffer(linear_rgba_bytes(decoded), dtype="float32").reshape(2, 3, 4)
    np.testing.assert_allclose(linear[..., :3], pixels / np.iinfo(pixels.dtype).max)
    np.testing.assert_array_equal(linear[..., 3], 1)


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ("srgb", "srgb"),
        ("linear", "linear"),
        ("unsupported", None),
        ("primaries", None),
    ],
)
def test_png_declared_transfer_still_precedes_linear_default(metadata, expected):
    from PIL import Image, PngImagePlugin

    info = PngImagePlugin.PngInfo()
    if metadata == "srgb":
        info.add(b"sRGB", b"\x00")
    elif metadata == "primaries":
        info.add(
            b"cHRM",
            struct.pack(">8I", 31270, 32900, 68000, 32000, 26500, 69000, 15000, 6000),
        )
    else:
        info.add(b"gAMA", struct.pack(">I", 100000 if metadata == "linear" else 70000))
    encoded = io.BytesIO()
    Image.new("RGB", (2, 2), (128, 128, 128)).save(encoded, format="PNG", pnginfo=info)
    asset = Asset(
        asset_id="image",
        logical_path="image.png",
        profile="png_uint_v1",
        color_override=None,
    )
    if expected is None:
        with pytest.raises(
            MediaPreparationError, match="gamma is outside|chromaticity metadata"
        ):
            decode_image(asset, encoded.getvalue())
        return
    assert decode_image(asset, encoded.getvalue()).transfer == expected
    override = ColorOverride(
        transfer="bt709",
        primaries="rec709_d65",
        range="full",
        matrix="rgb",
        chroma_location="none",
        reason="explicit test choice",
    )
    assert (
        decode_image(
            asset.model_copy(update={"color_override": override}), encoded.getvalue()
        ).transfer
        == "bt709"
    )


def test_tiff_icc_metadata_is_not_replaced_by_linear_default():
    np = pytest.importorskip("numpy")
    tifffile = pytest.importorskip("tifffile")
    encoded = io.BytesIO()
    tifffile.imwrite(
        encoded,
        np.zeros((2, 2, 3), dtype="uint8"),
        photometric="rgb",
        extratags=[(34675, "B", 4, b"test", False)],
    )
    asset = Asset(
        asset_id="image",
        logical_path="image.tif",
        profile="tiff_uint_v1",
        color_override=None,
    )
    with pytest.raises(MediaPreparationError, match="ICC metadata"):
        decode_image(asset, encoded.getvalue())


@pytest.mark.parametrize("cadence", [1_000_000_000, 25_000_000])
def test_setup_progress_throttles_counts_but_emits_stage_and_completion(cadence):
    from cephvr.visual_stimulus.resources.progress import SetupProgress

    now = [0]
    messages = []
    progress = SetupProgress(messages.append, lambda: now[0], cadence_ns=cadence)
    progress.update("Decoding textures", 0, 100)
    for count in range(1, 99):
        progress.update("Decoding textures", count, 100)
    assert messages == ["Decoding textures: 0/100"]
    now[0] = cadence
    progress.update("Decoding textures", 99, 100)
    progress.update("Decoding textures", 100, 100)
    progress.update("Decoding textures", 100, 100)
    progress.update("Uploading initial textures", 0, 20)
    assert messages[1:] == [
        "Decoding textures: 99/100",
        "Decoding textures: 100/100",
        "Uploading initial textures: 0/20",
    ]


@pytest.mark.parametrize("reference", [False, True])
def test_fold_preparation_requires_front_even_for_left_only(reference):
    from types import SimpleNamespace

    from tests.visual_stimulus.support import _geometric_profiles

    from cephvr.visual_stimulus.resources.uniforms import validate_image_layouts

    artifact = make_prepared_trial()
    profiles = _geometric_profiles(artifact.display)
    content = {"map-left": profiles["map-left"]}
    layouts = tuple(
        SimpleNamespace(name=name)
        for name in ("image_target_pixels_map-left", "image_fold_map_map-left")
    )
    if reference:
        content["map-front"] = profiles["map-front"]
        validate_image_layouts(layouts, artifact.display, content)
    else:
        with pytest.raises(ValueError, match="Front calibration"):
            validate_image_layouts(layouts, artifact.display, content)


def _mixed_candidate_artifact(field_first: bool):
    """An image-tile instance whose base asset and Asset-rule candidates mix kinds."""
    from cephvr.visual_stimulus.config.models.program_model import ImageTile
    from cephvr.visual_stimulus.config.models.repetition import AssetRepetitionRule

    artifact = make_prepared_trial()
    constant = dict(kind="constant", value=1.0)

    def tile(asset_id):
        return ImageTile.model_validate(
            dict(
                kind="image_tile",
                asset_id=asset_id,
                period_x=constant,
                period_y=constant,
                sampling="linear",
            )
        )

    epoch = artifact.source.sequence[0]
    base, other = ("field", "raster") if field_first else ("raster", "field")
    setting = epoch.settings[0].model_copy(update={"pattern": tile(base)})
    rule = AssetRepetitionRule(
        instance_id=setting.instance_id, asset_ids=(base, other), seed="0" * 32
    )
    node = epoch.model_copy(
        update={"settings": (setting,), "repetition_rules": (rule,)}
    )
    program = artifact.source.model_copy(update={"sequence": (node,)})
    return artifact, program, setting, tile


@pytest.mark.parametrize("field_first", [False, True])
def test_mixed_raster_and_field_candidates_build_field_layouts_and_evidence(
    field_first,
):
    from cephvr.visual_stimulus.rendering.evidence import uniform_values
    from cephvr.visual_stimulus.rendering.types import InstanceSnapshot

    artifact, program, setting, tile = _mixed_candidate_artifact(field_first)
    layouts = build_uniform_layouts(program, artifact.display, frozenset({"field"}))
    names = {item.name for item in layouts}
    for mapping in artifact.display.active_mappings:
        assert f"field_extent_mm_{mapping.mapping_id}" in names
        assert f"field_phase_mm_{mapping.mapping_id}" in names
    prepared = artifact.model_copy(update={"uniform_layouts": layouts})
    for drawn in ("raster", "field"):
        snapshot = InstanceSnapshot(
            setting.instance_id,
            "texture",
            True,
            (),
            setting.model_copy(update={"pattern": tile(drawn)}),
        )
        recorded = uniform_values(prepared, snapshot)
        # Mapped field uniforms are written by the layer draw, never by uniform_values.
        assert not any("field_" in key for key in recorded)
        assert any(key.endswith("-opacity") for key in recorded)
    # Raster-only rules add no field layouts.
    assert not any(
        item.name.startswith("field_")
        for item in build_uniform_layouts(program, artifact.display, frozenset({"x"}))
    )


def test_field_candidates_require_physical_texture_placement():
    from cephvr.visual_stimulus.resources.physical_field import validate_field_uses

    artifact, program, setting, _ = _mixed_candidate_artifact(False)
    validate_field_uses(program.sequence, {"unrelated"})
    validate_field_uses(program.sequence, {"field"})  # physical surface placement
    angular = setting.model_copy(
        update={"space": setting.space.model_copy(update={"kind": "visual_angle"})}
    )
    node = program.sequence[0].model_copy(update={"settings": (angular,)})
    validate_field_uses((node,), {"unrelated"})
    with pytest.raises(ValueError, match="physical-surface"):
        validate_field_uses((node,), {"field"})  # only a rule candidate is a field


def test_fold_layout_and_evidence_bind_the_mapped_coordinates():
    from cephvr.visual_stimulus.config.models.program_model import ImageSettings
    from cephvr.visual_stimulus.rendering.evidence import uniform_values
    from cephvr.visual_stimulus.rendering.types import InstanceSnapshot

    artifact = make_prepared_trial()
    epoch = artifact.source.sequence[0]
    data = epoch.settings[0].model_dump(include=set(ImageSettings.model_fields))
    data.update(kind="image", asset_id="image", sampling="linear", fit="fold")
    image = ImageSettings.model_validate(data)
    program = artifact.source.model_copy(
        update={"sequence": (epoch.model_copy(update={"settings": (image,)}),)}
    )
    layouts = build_uniform_layouts(program, artifact.display)
    mapped = [item for item in layouts if item.name.startswith("image_fold_map_")]
    assert mapped and all(item.shape == (3, 2) for item in mapped)
    recorded = uniform_values(
        artifact.model_copy(update={"uniform_layouts": layouts}),
        InstanceSnapshot(image.instance_id, "image", True, (), image),
    )
    assert all(item.binding_id not in recorded for item in mapped)


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("deferred", [False, True])
def test_grating_recipe_preparation_ignores_saved_angle_and_keeps_original_bytes(
    tmp_path, deferred, modern
):
    import hashlib
    from types import SimpleNamespace

    import numpy as np

    from cephvr.visual_stimulus.resources.grating_recipe import interpreted_recipe
    from cephvr.visual_stimulus.resources.prepare import prepare_resources
    from cephvr.visual_stimulus.resources.texture_recipe import (
        generate_texture_recipe,
        parse_texture_recipe,
    )

    raw = json.dumps(
        {
            "pattern": "grating",
            "params": {
                "orientation_deg": 73,
                "spatial_period_mm": 12,
                "tile_width_mm": 100,
                "tile_height_mm": 100,
                "texture_resolution": 8,
                "feature_sharpness": 1,
                "fit_cycles_to_tile": False,
            },
        }
    ).encode()
    if modern:
        from cephvr.generate_stimulus.textures import new_texture

        design = new_texture("grating")
        design["params"].update(
            spatial_period_mm=12, orientation_deg=73, feature_sharpness=1
        )
        raw = json.dumps(design).encode()
    path = tmp_path / "bars.json"
    path.write_bytes(raw)
    opened = []

    class Source:
        def __init__(self, path):
            self.path, self.closed = path, False
            opened.append(self)

        def independent_reader(self):
            return self.path.open("rb")

        def close_after_consumers(self):
            self.closed = True

    asset = Asset(
        asset_id="bars",
        logical_path="bars.json",
        profile="cephvr_grating_json_v1",
        color_override=None,
    )
    program = SimpleNamespace(assets=(asset,), instances=(), sequence=())
    budget = BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000)
    bundle = prepare_resources(
        program,
        tmp_path,
        budget,
        announce=lambda *_: None,
        snapshot_limit_bytes=10000,
        video_index_limit_bytes=1000,
        glb_element_limit=1000,
        max_document_bytes=1000,
        source_factory=Source,
        defer_images=deferred,
    )
    try:
        resource = bundle.manifest.resources[0]
        assert resource.profile_id == asset.profile
        assert resource.fingerprint.sha256 == hashlib.sha256(raw).hexdigest()
        if deferred:
            source = bundle.image_sources["bars"]
            pixels = np.frombuffer(source.load(lambda: None), dtype=np.float32).reshape(
                source.height, source.width, 4
            )
        else:
            pixels = bundle.prepared_content["bars"].pixels
        if modern:
            field = (
                bundle.image_sources["bars"].field_recipe
                if deferred
                else bundle.prepared_content["bars"].field_recipe
            )
            assert field.physical_field and field.params["orientation_deg"] == 0
            pixels = generate_texture_recipe(field)
        else:
            assert pixels.shape[:2] == (8, 8)
        assert np.array_equal(pixels, np.repeat(pixels[:1], pixels.shape[0], axis=0))
        assert np.ptp(pixels[..., 0]) > 0
        recipe = parse_texture_recipe(raw)
        normalized = interpreted_recipe(recipe, asset.profile)
        assert recipe.params["orientation_deg"] == 73
        assert normalized.tile_width_mm == normalized.tile_height_mm == 12
        other = json.loads(raw)
        other["params"]["orientation_deg"] = 11
        assert np.array_equal(
            generate_texture_recipe(normalized),
            generate_texture_recipe(
                interpreted_recipe(
                    parse_texture_recipe(json.dumps(other).encode()), asset.profile
                )
            ),
        )
        with pytest.raises(ValueError, match="Grating texture design"):
            interpreted_recipe(
                parse_texture_recipe(b'{"pattern":"checker","params":{}}'),
                asset.profile,
            )
        assert path.read_bytes() == raw
    finally:
        bundle.asset_set.close()
    assert all(s.closed for s in opened)


def sparse_layer_program(
    *, seconds: str = "60", pattern: str = "0.3", count: int = 400, epochs: int = 1
) -> str:
    """A program whose layers are generated sparse noise on front and left."""
    from tests.visual_stimulus.support import fixture_source

    data = json.loads(fixture_source())
    instances = ("noise-front", "noise-left")
    data["instances"] = [
        {"instance_id": name, "family": "sparse_noise"} for name in instances
    ]
    data["scenes"][0]["layer_instance_ids"] = list(instances)

    def setting(name: str, surface: str) -> dict:
        return {
            "kind": "sparse_noise",
            "instance_id": name,
            "space": {
                "kind": "physical_surface",
                "frame_id": f"plane-{surface}",
                "mappings": [{"surface_id": surface, "matrix": [[1, 0, 0], [0, 1, 0]]}],
            },
            "initial": {"x": 0, "y": 0, "rotation_deg": 0},
            "width": {"kind": "constant", "value": 1},
            "height": {"kind": "constant", "value": 1},
            "opacity": {"kind": "constant", "value": 1},
            "motion": {axis: {"kind": "hold"} for axis in ("x", "y", "rotation")},
            "reset": False,
            "assignments": [],
            "feedback": [],
            "appearance": {
                "format_version": 2,
                "kind": "sparse_noise",
                "seed": 11,
                "square_size_mm": 2.0,
                "min_active_cell_distance_mm": 4.0,
                "active_probability": 0.6,
                "background_linear": 0.25,
            },
            "pattern_count": count,
            "pattern_duration": {"seconds": pattern},
        }

    data["sequence"] = [
        {
            "kind": "epoch",
            "epoch_id": f"noise{index}",
            "scene_id": "scene",
            "duration": {"kind": "fixed", "duration": {"seconds": seconds}},
            "settings": [
                setting("noise-front", "front"),
                setting("noise-left", "left"),
            ],
        }
        for index in range(epochs)
    ]
    return json.dumps(data)


def test_generated_sparse_layers_compile_to_grid_extent_and_ordered_requests():
    from tests.visual_stimulus.support import make_prepared_trial

    from cephvr.visual_stimulus.resources.sparse_noise import pattern_rgba
    from cephvr.visual_stimulus.resources.sparse_noise_stream import (
        pattern_texels,
        requests,
        trial_layers,
    )

    plan = make_prepared_trial(sparse_layer_program(seconds="30", epochs=2))
    widths = {s.width.value for e in plan.epochs for s in e.settings}
    assert widths == {20.0}  # 10 complete 2 mm cells on a 20 mm surface.
    layers = trial_layers(plan)
    assert [(x.epoch_index, x.instance_id, x.shown) for x in layers] == [
        (0, "noise-front", 100),
        (0, "noise-left", 100),
        (1, "noise-front", 100),
        (1, "noise-left", 100),
    ]
    ordered = list(requests(layers))
    assert [r.sequence for r in ordered] == list(range(400))
    assert [r.due_ns for r in ordered] == sorted(r.due_ns for r in ordered)
    assert ordered[:3] == [
        type(ordered[0])(0, 0, 0, 0),
        type(ordered[0])(1, 1, 0, 0),
        type(ordered[0])(2, 0, 1, 300_000_000),
    ]
    # GL rows run bottom-up; cells are the PNG generator's for the same seed/surface.
    layer = layers[1]
    rgba = pattern_rgba(layer.recipe, layer.grid, 7)
    texels = pattern_texels(layer, 7)
    stride = layer.grid.columns * 4
    assert texels[:stride] == rgba[-stride:]
    assert sorted(texels) == sorted(rgba)
    # Same seed, different screen: independent per-screen streams.
    assert pattern_texels(layers[0], 7) != texels


@pytest.mark.parametrize("seed", [11, (1 << 64) - 1])
def test_epoch_sparse_patterns_follow_nested_repetitions(seed):
    from tests.visual_stimulus.support import make_prepared_trial

    from cephvr.visual_stimulus.resources.sparse_noise_stream import (
        pattern_texels,
        requests,
        trial_layers,
    )

    data = json.loads(sparse_layer_program(seconds="15"))
    for setting in data["sequence"][0]["settings"]:
        setting.pop("pattern_count")
        setting.pop("pattern_duration")
        setting["appearance"]["seed"] = seed

    def group(identity, body):
        return dict(
            kind="group",
            group_id=identity,
            repetitions=2,
            order="as_listed",
            order_unit="child_blocks",
            conditions=None,
            body=body,
        )

    data["sequence"] = [group("outer", [group("inner", data["sequence"])])]
    source = json.dumps(data)
    plan = make_prepared_trial(source)
    layers = trial_layers(plan)
    assert len(plan.epochs) == 4 and len(layers) == 8
    assert [e.start_ns for e in plan.epochs] == [
        0,
        15_000_000_000,
        30_000_000_000,
        45_000_000_000,
    ]
    assert [e.settings[0].appearance.seed for e in plan.epochs] == [
        (seed + i) % (1 << 64) for i in range(4)
    ]
    assert all(
        layer.shown == 1 and layer.pattern_duration_ns == 15_000_000_000
        for layer in layers
    )
    assert [r.due_ns for r in requests(layers)] == [
        i * 15_000_000_000 for i in range(4) for _ in range(2)
    ]
    assert len({pattern_texels(layer, 0) for layer in layers[::2]}) == 4
    assert all(
        s.pattern_at(14_999_999_999) == 0 for e in plan.epochs for s in e.settings
    )
    assert make_prepared_trial(source).epochs == plan.epochs
    assert (
        data["sequence"][0]["body"][0]["body"][0]["settings"][0]["appearance"]["seed"]
        == seed
    )


def test_epoch_sparse_pattern_count_cannot_override_group_repetitions():
    from tests.visual_stimulus.support import make_prepared_trial

    data = json.loads(sparse_layer_program(count=2))
    for setting in data["sequence"][0]["settings"]:
        setting["pattern_duration"] = None
    with pytest.raises(ValueError, match="one pattern per occurrence"):
        make_prepared_trial(json.dumps(data))


def test_sparse_layer_shows_only_patterns_inside_its_epoch_and_holds_the_last():
    from tests.visual_stimulus.support import make_prepared_trial

    from cephvr.visual_stimulus.resources.sparse_noise_stream import trial_layers

    short = make_prepared_trial(sparse_layer_program(count=10))
    assert {x.shown for x in trial_layers(short)} == {10}
    setting = short.epochs[0].settings[0]
    assert setting.pattern_at(-1) == 0
    assert setting.pattern_at(299_999_999) == 0
    assert setting.pattern_at(300_000_000) == 1
    assert setting.pattern_at(59_000_000_000) == 9  # Holds the final pattern.


def test_generated_sparse_layer_rejects_inactive_or_too_small_screens():
    from tests.visual_stimulus.support import make_prepared_trial

    data = json.loads(sparse_layer_program())
    data["sequence"][0]["settings"][0]["appearance"]["square_size_mm"] = 25.0
    with pytest.raises(ValueError, match="complete screen cell"):
        make_prepared_trial(json.dumps(data))


def test_sparse_wire_round_trips_jobs_credits_and_split_frames():
    from tests.visual_stimulus.support import make_prepared_trial

    from cephvr.visual_stimulus.resources.sparse_noise_stream import trial_layers
    from cephvr.visual_stimulus.resources.sparse_noise_wire import (
        FrameReader,
        decode_credit,
        decode_job,
        encode_credit,
        encode_job,
        frame_header,
    )

    layers = trial_layers(make_prepared_trial(sparse_layer_program()))
    assert decode_job(encode_job(layers)) == layers
    assert decode_credit(encode_credit(250)) == 250
    with pytest.raises(ValueError):
        decode_credit(b"MORE 1\n")
    digest = bytes(range(32))
    stream = (
        frame_header(0, 3, digest)
        + b"abc"
        + frame_header(1, 0, digest)
        + frame_header(2, 2, digest)
        + b"xy"
    )
    reader = FrameReader(16)
    frames = []
    for offset in range(0, len(stream), 5):
        frames += reader.feed(stream[offset : offset + 5])
    assert frames == [(0, b"abc", digest), (1, b"", digest), (2, b"xy", digest)]
    assert not reader.partial
    with pytest.raises(ValueError, match="malformed"):
        FrameReader(2).feed(frame_header(0, 3, digest) + b"abc")


def test_sparse_helper_streams_credited_patterns_over_pipes_and_stops_on_eof():
    import hashlib
    import subprocess
    import sys

    from tests.visual_stimulus.support import make_prepared_trial

    from cephvr.visual_stimulus.resources.sparse_noise import pattern_rgba
    from cephvr.visual_stimulus.resources.sparse_noise_stream import (
        pattern_texels,
        requests,
        trial_layers,
    )
    from cephvr.visual_stimulus.resources.sparse_noise_wire import (
        FrameReader,
        encode_credit,
        encode_job,
    )

    layers = trial_layers(make_prepared_trial(sparse_layer_program(count=20)))
    helper = subprocess.Popen(
        [sys.executable, "-m", "cephvr.visual_stimulus.sparse_noise_helper"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert helper.stdin is not None and helper.stdout is not None
    try:
        helper.stdin.write(encode_job(layers) + encode_credit(6))
        helper.stdin.flush()
        reader, frames = FrameReader(1 << 20), []
        while len(frames) < 6:
            chunk = helper.stdout.read1(1 << 16)
            assert chunk, "helper exited before its credit was used"
            frames += reader.feed(chunk)
        assert not reader.partial
        expected = list(requests(layers))[:6]
        assert [f[0] for f in frames] == list(range(6))
        assert [f[1] for f in frames] == [
            pattern_texels(layers[r.layer], r.pattern) for r in expected
        ]
        # Each frame carries the hash of the generator's top-row-first cell bytes.
        assert [f[2] for f in frames] == [
            hashlib.sha256(
                pattern_rgba(layers[r.layer].recipe, layers[r.layer].grid, r.pattern)
            ).digest()
            for r in expected
        ]
        helper.stdin.close()
        assert helper.wait(timeout=10) == 0
    finally:
        if helper.poll() is None:
            helper.kill()


@pytest.mark.windows
@pytest.mark.parametrize("unique", [1, 17])
def test_prepared_image_bundle_reads_ready_bytes_and_detects_damage(tmp_path, unique):
    from cephvr.shared import temporary_bundle
    from cephvr.visual_stimulus.resources.budget import BoundedBudget
    from cephvr.visual_stimulus.resources.image_bundle import ImageBundle
    from cephvr.visual_stimulus.resources.image_crops import ImageCrop
    from cephvr.visual_stimulus.resources.image_schedule import ImageSchedule
    from cephvr.visual_stimulus.resources.image_source import ImageSource

    calls = []

    def load(check):
        check()
        calls.append("decode")
        return bytes(64)

    crop = ImageCrop(
        "out",
        0,
        0,
        1,
        1,
        0,
        (1, 1),
        ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)),
        (0.0, 1.0, 1.0, 0.0, 0.0, -1.0),
        "map",
    )
    source = ImageSource("key", 2, 2, 64, 16, load, output_crops=(crop,))
    keys = ["key" if n == 0 else f"key{n}" for n in range(unique)]
    sources = {key: replace(source, key=key) for key in keys}
    aliases = {(trial, key): key for trial in ("trial", "other") for key in keys}
    rows = tuple((("layer", key),) for key in keys) * 3
    schedule = ImageSchedule(
        sources,
        aliases,
        {"trial": "gen", "other": "gen2"},
        {"trial": rows, "other": rows},
        {(trial, "layer"): "key" for trial in ("trial", "other")},
        {(trial, key): n for trial in ("trial", "other") for n, key in enumerate(keys)},
    )
    # Native owner test uses the isolated fixture runtime registry.
    from unittest.mock import patch

    with patch.object(
        temporary_bundle, "default_runtime_root", lambda: tmp_path / "runtime"
    ):
        bundle = ImageBundle(tmp_path, lambda *args: None)
    try:
        progress = []
        batches = []
        budget = BoundedBudget(cpu_limit=1024, gpu_limit=1024)
        result = bundle.prepare(
            schedule,
            lambda source, pixels, check: bytes([97 + keys.index(source.key)]) * 16,
            budget,
            lambda done, total: progress.append((done, total)),
            finish_batch=lambda: batches.append(len(calls)),
        )
        assert calls == ["decode"] * unique
        assert batches == ([1] if unique == 1 else [16, 17])
        assert len(bundle.storage.files) == len(batches) + 1
        assert budget.usage.cpu_bytes == 16
        assert budget.usage.gpu_bytes == 0
        assert progress == [(n, unique) for n in range(unique + 1)]
        assert bundle.reused_references == unique * 5
        assert f"batch {len(batches)}/{len(batches)}" in bundle.progress_stage(
            unique, unique
        )
        for n in reversed(range(unique)):
            assert result.sources[keys[n]].load(lambda: None) == bytes([97 + n]) * 16
        from cephvr.visual_stimulus.config.models.artifact_models import (
            PreparedImageBundle,
        )

        prepared = PreparedImageBundle(asset_id="asset", **bundle.manifest["key"])
        assert prepared.crops[0].width == 1
        assert result.sources["key"].load(lambda: None) == b"a" * 16
        first_buffer = result.sources["key"].load(lambda: None)
        assert result.sources["key"].load(lambda: None).obj is first_buffer.obj
        assert first_buffer == b"a" * 16
        assert calls == ["decode"] * unique
        assert result.sources["key"].cpu_bytes == 0
        file = bundle.storage.files[0]
        file.seek(0)
        file.write(b"b")
        file.flush()
        with pytest.raises(ValueError, match="content changed"):
            result.sources["key"].load(lambda: None)
    finally:
        bundle.close()
    assert not bundle.storage.directory.exists()


def test_image_validation_index_reuses_only_matching_content_and_validator(
    tmp_path, monkeypatch
):
    from cephvr.visual_stimulus.resources import image_validation_index as index
    from cephvr.visual_stimulus.resources.image_source import ImageInfo

    info = ImageInfo(12, 8, "uint8", ("red", "green", "blue"), "linear", "none")
    monkeypatch.setattr(index, "validator_identity", lambda: "decoder-version-1")
    cache = index.ImageValidationIndex(tmp_path)
    assert cache.get("content-1-linear") is None
    cache.put("content-1-linear", "stimuli/image.png", info)
    cache.save()
    loaded = index.ImageValidationIndex(tmp_path)
    assert loaded.get("content-1-linear") == info
    assert loaded.get("content-2-linear") is None
    assert loaded.get("content-1-srgb") is None
    monkeypatch.setattr(index, "validator_identity", lambda: "decoder-version-2")
    assert index.ImageValidationIndex(tmp_path).get("content-1-linear") is None
    (tmp_path / index.INDEX_NAME).write_text("incomplete JSON")
    assert index.ImageValidationIndex(tmp_path).get("content-1-linear") is None
    assert not list(tmp_path.glob(".cephvr-validation-*.tmp"))


@pytest.mark.parametrize("profile", ["png_uint_v1", "tiff_uint_v1"])
@pytest.mark.parametrize("decode_fails", [False, True])
def test_combined_image_preparation_validates_once_before_ready(
    profile, monkeypatch, decode_fails
):
    import hashlib

    import imagecodecs
    import numpy as np
    import tifffile

    from cephvr.visual_stimulus.resources import media
    from cephvr.visual_stimulus.resources.assets import PreparedAsset
    from cephvr.visual_stimulus.resources.image_source import validate_image_source

    pixels = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
    if profile == "png_uint_v1":
        raw = imagecodecs.png_encode(pixels)
    else:
        stream = io.BytesIO()
        tifffile.imwrite(stream, pixels, photometric="rgb")
        raw = stream.getvalue()

    class Source:
        def independent_reader(self):
            return io.BytesIO(raw)

    asset = Asset(
        asset_id="image", logical_path="image.png", profile=profile, color_override=None
    )
    prepared = PreparedAsset(
        "image",
        "image.png",
        profile,
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        Source(),
        None,
    )
    calls = []
    decode = media.decode_image

    def counted(*args, **kwargs):
        calls.append(kwargs.get("metadata_only", False))
        if decode_fails and not kwargs.get("metadata_only", False):
            raise ValueError("corrupt pixel stream")
        return decode(*args, **kwargs)

    monkeypatch.setattr(media, "decode_image", counted)
    published = []
    budget = BoundedBudget(cpu_limit=100_000, gpu_limit=100_000)
    source, info = validate_image_source(
        asset,
        prepared,
        budget=budget,
        owner="test",
        output_count=1,
        max_document_bytes=1000,
        defer_validation=True,
        validated=published.append,
    )
    assert calls == [True] and not published
    assert (info.width, info.height) == (4, 3)
    if decode_fails:
        with pytest.raises(ValueError, match="corrupt pixel stream"):
            source.finish_validation()
        assert not published
        assert budget.usage.cpu_bytes == 0
        return
    result = source.load(lambda: None)
    assert len(result) == 4 * 3 * 16
    assert published == [info] and calls == [True, False]
    stages = source.timings.snapshot()
    assert stages["source_decode"][0] == stages["source_convert"][0] == 1
    source.timings.clear()
    assert source.timings.snapshot() == {}
    source.finish_validation()
    assert calls == [True, False]
    assert budget.usage.cpu_bytes == 0
