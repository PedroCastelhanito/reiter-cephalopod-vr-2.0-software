"""Offline authoring contracts: new owner, with no Qt or device fixtures."""

import json
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from PIL import Image

from cephvr.generate_stimulus.arena import compile_arena, export_arena
from cephvr.generate_stimulus.files import atomic_write, json_bytes
from cephvr.generate_stimulus.geometry import build_geometry
from cephvr.generate_stimulus.jobs import Cancelled, Jobs
from cephvr.generate_stimulus.models import ArenaDesign, Relief, Scatter
from cephvr.generate_stimulus.textures import (
    PATTERNS,
    new_texture,
    texture_pixels,
    validate_texture,
)
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoiseRecipe
from cephvr.visual_stimulus.resources.sparse_noise import pattern_rgba, resolve_grids


def geometry() -> Geometry:
    return Geometry.model_validate_json(
        json.dumps(
            {
                "frame_id": "tank",
                "observer_mm": [50, 50, 50],
                "near_mm": 1,
                "far_mm": 1000,
                "positional_tolerance_mm": 0.001,
                "orthogonality_tolerance": 0.001,
                "surfaces": [
                    {
                        "surface_id": name,
                        "bottom_left_mm": [0, 0, 0],
                        "bottom_right_mm": [100, 0, 0],
                        "top_right_mm": [100, 100, 0],
                        "top_left_mm": [0, 100, 0],
                    }
                    for name in ("front", "left", "right", "bottom")
                ],
            }
        )
    )


@pytest.mark.parametrize("pattern", list(PATTERNS))
def test_texture_backend_roundtrip(pattern: str, tmp_path: Path) -> None:
    from cephvr.generate_stimulus.documents import read_design, save_design

    document = new_texture(pattern)
    assert "texture_resolution" not in document["params"]
    document["params"]["texture_resolution"] = 32
    document["params"]["size"] = 64
    document["size"] = 128
    if pattern == "image":
        Image.new("RGB", (8, 8), (40, 60, 80)).save(tmp_path / "source.png")
        document["params"]["texture_path"] = "source.png"
    path = tmp_path / "recipe.json"
    atomic_write(path, json_bytes(document))
    restored = json.loads(path.read_bytes())
    first = texture_pixels(restored, tmp_path, geometry())
    assert np.array_equal(first, texture_pixels(document, tmp_path, geometry()))
    assert first.dtype == np.uint8
    saved = save_design(document, tmp_path, path, tmp_path)
    assert "texture_resolution" not in saved["params"]
    assert "size" not in saved["params"]
    assert "size" not in saved
    assert read_design(path) == saved == json.loads(path.read_bytes())
    assert document["params"]["texture_resolution"] == 32
    assert np.array_equal(first, texture_pixels(saved, tmp_path, geometry()))
    assert not path.with_suffix(".png").exists()


def test_sparse_backend_index_and_screen_identity(tmp_path: Path) -> None:
    document = new_texture("sparse_noise")
    recipe = SparseNoiseRecipe.model_validate_json(
        json.dumps(
            {
                **document,
                "surfaces": ["front"],
                "pattern_count": 600,
                "pattern_duration": {"seconds": "0.1"},
            }
        )
    )
    grid = resolve_grids(recipe, geometry(), max_cells=10000)[0]
    pixels = texture_pixels(document, tmp_path, geometry(), index=3)
    rgba = np.frombuffer(pattern_rgba(recipe, grid, 3), dtype=np.uint8).reshape(
        grid.rows, grid.columns, 4
    )
    assert np.array_equal(
        pixels[rgba[:, :, 3] != 0], rgba[:, :, :3][rgba[:, :, 3] != 0]
    )
    assert (rgba[:, :, 3] != 0).sum() <= grid.columns * grid.rows
    assert np.array_equal(
        pixels, texture_pixels(document, tmp_path, geometry(), index=3)
    )
    assert not np.array_equal(
        pixels, texture_pixels(document, tmp_path, geometry(), face="left", index=3)
    )
    with pytest.raises(ValueError):
        texture_pixels(document, tmp_path, geometry(), index=-1)
    assert texture_pixels(document, tmp_path).shape == (20, 20, 3)


@pytest.mark.parametrize(
    "shape", ["rectangular", "circular", "torus", "two_choice", "cross"]
)
def test_shapes_bounds_winding_and_roundtrip(shape: str, tmp_path: Path) -> None:
    design = ArenaDesign(shape=shape, subdivisions=2, segments=16)
    meshes = build_geometry(design, max_vertices=10000)
    points = np.concatenate([m.positions for m in meshes])
    assert np.isfinite(points).all()
    assert points[:, 0].min() == pytest.approx(-250)
    assert points[:, 0].max() == pytest.approx(250)
    assert points[:, 1].min() == pytest.approx(-250)
    assert points[:, 1].max() == pytest.approx(250)
    for mesh in meshes:
        tri = mesh.positions[mesh.indices.reshape(-1, 3)]
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        assert np.all(np.linalg.norm(normals, axis=1) > 0)
        if mesh.surface == "floor":
            assert (normals[:, 2] > 0).all()
        assert np.isfinite(mesh.uv).all()
    result = compile_arena(design, tmp_path)
    assert len(result.scene.nodes) == len(meshes)
    assert compile_arena(design, tmp_path).glb == result.glb


@pytest.mark.parametrize("pattern", ["rock", "ridges", "waves"])
def test_relief_seed_and_export_without_viewport(pattern: str, tmp_path: Path) -> None:
    design = ArenaDesign(subdivisions=3)
    design.surfaces["floor"].relief = Relief(pattern=pattern, height_mm=3, seed=42)
    first = compile_arena(design, tmp_path)
    assert first.glb == compile_arena(design, tmp_path).glb
    design.surfaces["floor"].relief.seed = 43
    assert first.glb != compile_arena(design, tmp_path).glb
    output = export_arena(design, tmp_path, tmp_path / "bundle")
    assert output.exists()
    assert (output.parent / "provenance.json").exists()
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        export_arena(design, tmp_path, output.parent)
    assert output.read_bytes() == before


def test_scatter_material_texture_and_dependency_provenance(tmp_path: Path) -> None:
    Image.new("RGBA", (8, 8), (100, 150, 200, 128)).save(tmp_path / "surface.png")
    small = ArenaDesign(width_mm=2, depth_mm=2, height_mm=2, subdivisions=1)
    small.surfaces["floor"].texture = "surface.png"
    small.surfaces["floor"].alpha_mode = "MASK"
    small.surfaces["floor"].alpha_cutoff = 0.25
    (tmp_path / "object.glb").write_bytes(compile_arena(small, tmp_path).glb)
    design = ArenaDesign(width_mm=20, depth_mm=20, subdivisions=2)
    design.surfaces["floor"].scatters = [
        Scatter(model="object.glb", density_per_cm2=1, seed=14)
    ]
    result = compile_arena(design, tmp_path)
    assert "object.glb" in result.dependencies
    assert result.scene.textures
    assert any(
        m.alpha_mode == "MASK" and m.alpha_cutoff == 0.25
        for m in result.scene.materials
    )
    assert result.glb == compile_arena(design, tmp_path).glb
    assert len(result.scene.nodes) > 5


def test_budgets_paths_and_cancelled_exports(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="budget"):
        build_geometry(ArenaDesign(), max_vertices=1)
    invalid = new_texture("grating")
    invalid["params"]["texture_resolution"] = 100000
    with pytest.raises(ValueError):
        validate_texture(invalid)
    design = ArenaDesign()
    design.surfaces["floor"].texture = "../escape.png"
    with pytest.raises(ValueError):
        compile_arena(design, tmp_path)

    def cancel() -> None:
        raise Cancelled()

    with pytest.raises(Cancelled):
        export_arena(ArenaDesign(), tmp_path, tmp_path / "cancelled", check=cancel)
    assert not (tmp_path / "cancelled").exists()


def test_worker_discards_obsolete_result() -> None:
    jobs = Jobs()
    started, release = Event(), Event()

    def slow(check):
        started.set()
        assert release.wait(3)
        check()
        return "old"

    jobs.submit(slow)
    assert started.wait(3)
    latest = jobs.submit(lambda check: "new")
    release.set()
    serial, result, error = jobs.results.get(timeout=3)
    jobs.close()
    assert (serial, result, error) == (latest, "new", None)


def test_geometry_cache_reuses_unaffected_surfaces() -> None:
    from cephvr.generate_stimulus.geometry import GeometryCache

    cache = GeometryCache()
    design = ArenaDesign(subdivisions=2)
    cache.build(design, 10000, lambda: None)
    floor, wall = cache.entries["floor"][1], cache.entries["wall_n"][1]
    design.surfaces["floor"].color = (1, 0, 0, 1)
    cache.build(design, 10000, lambda: None)
    assert cache.entries["floor"][1] is floor
    design.surfaces["floor"].relief = Relief(pattern="rock", height_mm=2, seed=4)
    cache.build(design, 10000, lambda: None)
    assert cache.entries["floor"][1] is not floor
    assert cache.entries["wall_n"][1] is wall


def test_failed_save_preserves_original_and_cleans_temporary(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "design.json"
    path.write_bytes(b"original")

    def fail(*args):
        raise OSError("injected replace failure")

    monkeypatch.setattr("cephvr.generate_stimulus.files.os.replace", fail)
    with pytest.raises(OSError):
        atomic_write(path, b"replacement")
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_image_recipe_rebase_matches_backend_dependency(tmp_path) -> None:
    from cephvr.generate_stimulus.documents import save_design
    from cephvr.visual_stimulus.config.models.program_model import Asset
    from cephvr.visual_stimulus.resources.recipe_dependencies import image_dependency
    from cephvr.visual_stimulus.resources.texture_recipe import parse_texture_recipe

    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (2, 2), (40, 60, 80)).save(images / "input.png")
    document = new_texture("image")
    document["params"]["texture_path"] = "images/input.png"
    path = images / "recipe.json"
    result = save_design(document, tmp_path, path, tmp_path)
    assert document["params"]["texture_path"] == "images/input.png"
    assert result["params"]["texture_path"] == "input.png"
    dependency = image_dependency(
        tmp_path,
        Asset(
            asset_id="image",
            logical_path="images/recipe.json",
            profile="cephvr1_texture_json_v1",
            color_override=None,
        ),
        parse_texture_recipe(path.read_bytes()),
    )
    assert dependency.logical_path == "images/input.png"
    assert texture_pixels(result, tmp_path, recipe_directory=images)[0, 0].tolist() == [
        40,
        60,
        80,
    ]


def test_sparse_preview_retains_centered_margins(tmp_path) -> None:
    from cephvr.generate_stimulus.texture_preview import preview_texture

    document = new_texture("sparse_noise")
    document.update(
        square_size_mm=7, min_active_cell_distance_mm=0.0, active_probability=1.0
    )
    pixels, caption = preview_texture(
        document,
        tmp_path,
        geometry(),
        face="front",
        index=2,
        screen=True,
        directory=tmp_path,
        check=lambda: None,
    )
    assert (pixels[0] == 128).all() and (pixels[:, 0] == 128).all()
    assert (pixels[-1] == 128).all() and (pixels[:, -1] == 128).all()
    inset = round(pixels.shape[0] * 0.02)
    assert set(np.unique(pixels[inset:-inset, inset:-inset])) <= {0, 255}
    assert "100" in caption


@pytest.mark.parametrize(
    ("width", "height", "shape"),
    [(160, 90, (1080, 1920, 3)), (90, 160, (1080, 608, 3))],
)
def test_preview_full_hd_preserves_screen_aspect(
    tmp_path, monkeypatch, width, height, shape
):
    from cephvr.generate_stimulus import texture_preview

    profile = geometry().model_dump(mode="json")
    for surface in profile["surfaces"]:
        surface.update(
            bottom_right_mm=[width, 0, 0],
            top_right_mm=[width, height, 0],
            top_left_mm=[0, height, 0],
        )
    document = new_texture("grating")
    original = json_bytes(document)
    generate = texture_preview.texture_pixels
    sampled = []

    def capture(*args, **kwargs):
        pixels = generate(*args, **kwargs)
        sampled.append(pixels.shape)
        return pixels

    monkeypatch.setattr(texture_preview, "texture_pixels", capture)
    pixels, _ = texture_preview.preview_texture(
        document,
        tmp_path,
        Geometry.model_validate_json(json.dumps(profile)),
        face="front",
        index=0,
        screen=True,
        directory=tmp_path,
        check=lambda: None,
    )
    assert pixels.shape == shape
    assert sampled == [shape]
    assert json_bytes(document) == original


def test_saved_calibration_uses_existing_geometry_conversion(tmp_path) -> None:
    from cephvr.generate_stimulus.textures import load_geometry
    from cephvr.gui.calibration_arena import geometry_from_calibration

    values = {
        "rig.width": 100,
        "rig.depth": 100,
        "rig.height": 100,
        "rig.subject_x": 50,
        "rig.subject_y": 50,
        "rig.subject_z": 50,
    }
    for name in ("Front", "Left", "Right", "Bottom"):
        values.update(
            {
                f"screens.{name}.width": 100,
                f"screens.{name}.height": 100,
                f"screens.{name}.subject_distance": 50,
            }
        )
    data = {"format": "cephvr-rig-calibration", "version": 8, "values": values}
    path = tmp_path / "calibration.json"
    path.write_bytes(json_bytes(data))
    result = load_geometry(path)
    _, screens = geometry_from_calibration(data)
    assert result.surfaces[0].bottom_left_mm == tuple(screens["Front"][0])


def test_cancel_after_staging_never_publishes_bundle(tmp_path) -> None:
    def cancel_at_publish():
        if list(tmp_path.glob(".cephvr-arena-*")):
            raise Cancelled()

    with pytest.raises(Cancelled):
        export_arena(
            ArenaDesign(subdivisions=1),
            tmp_path,
            tmp_path / "bundle",
            check=cancel_at_publish,
        )
    assert list(tmp_path.iterdir()) == []


def test_authored_physical_controls_have_no_tile_fields(tmp_path) -> None:
    from cephvr.generate_stimulus.documents import save_design

    for pattern in ("filtered_noise", "dots_rand"):
        document = new_texture(pattern)
        document["params"]["tile_width_mm"] = 200
        result = save_design(document, tmp_path, tmp_path / f"{pattern}.json", tmp_path)
        assert result["cephvr_asset_type"] == "texture_field"
        assert (
            not {"tile_width_mm", "tile_height_mm", "tile_size_mm", "features_per_tile"}
            & result["params"].keys()
        )


def test_sparse_appearance_save_and_legacy_import(tmp_path: Path) -> None:
    from cephvr.generate_stimulus.documents import read_design, save_design

    appearance = new_texture("sparse_noise")
    assert not {"surfaces", "pattern_count", "pattern_duration"} & appearance.keys()
    path = tmp_path / "appearance.json"
    save_design(appearance, tmp_path, path, tmp_path)
    assert read_design(path) == appearance
    legacy = {
        **appearance,
        "surfaces": ["front"],
        "pattern_count": 600,
        "pattern_duration": {"seconds": "0.1"},
    }
    path.write_text(json.dumps(legacy))
    assert read_design(path) == appearance
    assert np.array_equal(
        texture_pixels(legacy, tmp_path, geometry(), index=7),
        texture_pixels(appearance, tmp_path, geometry(), index=7),
    )
    save_design(legacy, tmp_path, path, tmp_path)
    assert json.loads(path.read_text()) == appearance


@pytest.mark.parametrize("pattern", ["polar_grating", "sparse_noise", "grating"])
def test_projector_independent_tile_preview(pattern, tmp_path):
    from cephvr.generate_stimulus.documents import save_design
    from cephvr.generate_stimulus.texture_preview import preview_texture
    from cephvr.visual_stimulus.resources.texture_recipe import (
        generate_texture_recipe,
        parse_texture_recipe,
    )

    document = new_texture(pattern)
    saved = save_design(document, tmp_path, tmp_path / "recipe.json", tmp_path)
    assert not {"origin_screen", "target_screen", "surfaces"} & saved.keys()
    assert not {"origin_screen", "target_screen"} & saved.get("params", {}).keys()
    options = dict(index=3, screen=False, directory=tmp_path, check=lambda: None)
    pixels, caption = preview_texture(saved, tmp_path, None, face="front", **options)
    other, other_caption = preview_texture(
        saved, tmp_path, geometry(), face="left", **options
    )
    assert np.array_equal(pixels, other)
    assert pixels.shape == (1080, 1080, 3)
    assert "texture_resolution" not in saved.get("params", {})
    assert json.loads((tmp_path / "recipe.json").read_bytes()) == saved
    assert caption == other_caption
    if pattern == "polar_grating":
        recipe = parse_texture_recipe((tmp_path / "recipe.json").read_bytes())
        assert np.array_equal(
            generate_texture_recipe(recipe), texture_pixels(saved, tmp_path)
        )
        design = ArenaDesign(subdivisions=2)
        design.surfaces["floor"].texture = "recipe.json"
        compile_arena(design, tmp_path)


@pytest.mark.parametrize("pattern", ["bars_horizontal", "bars_vertical"])
@pytest.mark.parametrize("width", [0.001, 5.0, 12.375])
def test_equal_width_bars_saved_backend_matches_preview(pattern, width, tmp_path):
    from cephvr.generate_stimulus.documents import read_design, save_design
    from cephvr.visual_stimulus.resources.texture_recipe import (
        generate_texture_recipe,
        parse_texture_recipe,
    )

    document = new_texture(pattern)
    document["params"].update(bar_width_mm=width, tile_width_mm=2000)
    path = tmp_path / "bars.json"
    saved = save_design(document, tmp_path, path, tmp_path)
    assert read_design(path) == saved
    params = saved["params"]
    assert params["bar_width_mm"] == width
    assert saved["cephvr_asset_type"] == "texture_field"
    assert not {"tile_width_mm", "tile_height_mm", "line_spacing_mm"} & params.keys()
    recipe = parse_texture_recipe(path.read_bytes())
    pixels = generate_texture_recipe(recipe, extent_mm=(2 * width, 2 * width))
    line = pixels[:, 0, 0] if pattern == "bars_horizontal" else pixels[0, :, 0]
    assert np.count_nonzero(line == 255) == np.count_nonzero(line == 0) == 256
    params["blur_mm"] = width / 10
    pixels = generate_texture_recipe(
        parse_texture_recipe(json_bytes(saved)), extent_mm=(2 * width, 2 * width)
    )
    assert np.any((pixels > 0) & (pixels < 255))


@pytest.mark.parametrize("width", [0, -1, float("nan"), float("inf")])
def test_bars_reject_invalid_width(width, tmp_path):
    document = new_texture("bars_horizontal")
    document["params"]["bar_width_mm"] = width
    with pytest.raises(ValueError, match="Bar width"):
        texture_pixels(document, tmp_path)


@pytest.mark.parametrize(
    "pattern", [p for p in PATTERNS if p not in {"bars_horizontal", "bars_vertical"}]
)
def test_selectable_texture_raster_independent_save(pattern, tmp_path):
    from cephvr.generate_stimulus.documents import read_design, save_design
    from cephvr.generate_stimulus.textures import authored_recipe

    document = new_texture(pattern)
    document["params"].update(tile_width_mm=200, tile_height_mm=300)
    if pattern == "grating":
        document["params"]["phase_cycles"] = 0.75
        document["params"]["fit_cycles_to_tile"] = True
    if pattern == "image":
        Image.new("RGB", (8, 8)).save(tmp_path / "source.png")
        document["params"]["texture_path"] = "source.png"
    path = tmp_path / "texture.json"
    path.write_text(json.dumps(authored_recipe(document)))
    opened = read_design(path)
    assert opened == authored_recipe(document)
    if pattern != "image":
        assert opened["cephvr_asset_type"] == "texture_field"
        assert (
            not {
                "tile_width_mm",
                "tile_height_mm",
                "phase_cycles",
                "fit_cycles_to_tile",
            }
            & opened["params"].keys()
        )
    saved = save_design(opened, tmp_path, path, tmp_path)
    assert read_design(path) == saved
    assert np.array_equal(
        texture_pixels(document, tmp_path), texture_pixels(saved, tmp_path)
    )


@pytest.mark.parametrize("pattern", [p for p in PATTERNS if p != "image"])
def test_saved_field_bytes_do_not_depend_on_consumer_extent_or_resolution(
    pattern, tmp_path
):
    from cephvr.generate_stimulus.documents import save_design

    document = new_texture(pattern)
    path = tmp_path / "field.json"
    saved = save_design(document, tmp_path, path, tmp_path)
    original = path.read_bytes()
    for extent, size in (((30, 50), (60, 100)), ((300, 80), (150, 40))):
        pixels = texture_pixels(
            saved, tmp_path, authored=False, extent_mm=extent, sample_size=size
        )
        assert pixels.shape == (size[1], size[0], 3)
        assert path.read_bytes() == original
    save_design(document, tmp_path, path, tmp_path)
    assert path.read_bytes() == original


def test_arena_field_baking_preserves_physical_scale_and_geometry_cache(tmp_path):
    from cephvr.generate_stimulus.documents import save_design
    from cephvr.generate_stimulus.geometry import GeometryCache

    document = new_texture("grating")
    document["params"].update(spatial_period_mm=13.0, orientation_deg=37.0)
    save_design(document, tmp_path, tmp_path / "field.json", tmp_path)
    design = ArenaDesign(subdivisions=2)
    design.surfaces["floor"].texture = "field.json"
    cache = GeometryCache()
    first = compile_arena(design, tmp_path, geometry_cache=cache)
    second = compile_arena(design, tmp_path, geometry_cache=cache)
    assert first.glb == second.glb
    design.surfaces["floor"].texture_scale_mm = 42
    third = compile_arena(design, tmp_path, geometry_cache=cache)
    assert first.scene.textures[0].image == third.scene.textures[0].image
