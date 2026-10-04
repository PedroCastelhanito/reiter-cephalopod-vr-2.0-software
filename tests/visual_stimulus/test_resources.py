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
from cephvr.visual_stimulus.resources.uniforms import build_uniform_layouts
from cephvr.visual_stimulus.resources.video import VideoPlayback
from cephvr.visual_stimulus.resources.video_index import (
    SourceFrame,
    VideoIndex,
    _relative_pts,
)
from cephvr.visual_stimulus.resources.video_selection import PlaybackCursor
from cephvr.visual_stimulus.resources.video_session import VideoSession


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
