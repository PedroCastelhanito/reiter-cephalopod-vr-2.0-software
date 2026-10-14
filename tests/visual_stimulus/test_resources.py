from __future__ import annotations

import io
import json
import struct
import threading
import time
from dataclasses import replace
from fractions import Fraction

import pytest
from tests.visual_stimulus.support import make_prepared_trial

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
from cephvr.visual_stimulus.resources.session import review_capture_cpu_bytes
from cephvr.visual_stimulus.resources.uniforms import build_uniform_layouts
from cephvr.visual_stimulus.resources.video import VideoPlayback
from cephvr.visual_stimulus.resources.video_index import (
    SourceFrame,
    VideoIndex,
    _relative_pts,
)
from cephvr.visual_stimulus.resources.video_selection import PlaybackCursor
from cephvr.visual_stimulus.resources.video_session import VideoSession


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
    assert source.cpu_bytes >= 2 * len(raw) + 4 * 3 * 192
    assert source.gpu_bytes == 4 * 3 * 16 * 3
    assert protected.readers == 5  # Validation, two source reads and two cache misses.
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


def test_polar_recipe_image_source_key_includes_explicit_surface_geometry():
    import hashlib
    from types import SimpleNamespace

    from cephvr.visual_stimulus.resources.assets import PreparedAsset
    from cephvr.visual_stimulus.resources.image_source import validate_image_source

    raw = b'{"pattern":"polar_grating","params":{"size":8,"bar_count":6}}'
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
    assert first.key != second.key
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


def glb_fixture(*, texture=False, external=False):
    binary = struct.pack("<9f3H", 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": 3},
            {"bufferView": 1, "componentType": 5123, "type": "SCALAR", "count": 3},
        ],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}
                ]
            }
        ],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "extensionsRequired": ["KHR_materials_unlit"],
        "materials": [
            {
                "extensions": {"KHR_materials_unlit": {}},
                "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.25, 1, 1]},
            }
        ],
    }
    if texture:
        document["images"] = [{"uri": "textures/fish.png"}]
        document["textures"] = [{"source": 0, "sampler": 0}]
        document["samplers"] = [{"wrapS": 33648, "minFilter": 9987}]
    if external:
        document["buffers"][0]["uri"] = "mesh.bin"
    return document, binary


def pack_glb(document, binary):
    data = json.dumps(document).encode()
    data += b" " * (-len(data) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(data), 0x4E4F534A) + data
    chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


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
