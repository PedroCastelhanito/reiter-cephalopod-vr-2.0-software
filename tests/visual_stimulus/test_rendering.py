from __future__ import annotations

import struct
import sys
from types import ModuleType
from types import SimpleNamespace as NS

import pytest
from tests.visual_stimulus.support import make_prepared_trial

from cephvr.visual_stimulus.config.models.evidence_model import UniformLayout
from cephvr.visual_stimulus.rendering.arena import (
    arena_model_matrix,
    gl_matrix_words,
    off_axis_view_projection,
)
from cephvr.visual_stimulus.rendering.color import (
    interpolate_inverse_lut,
    quantize_device_code,
    source_over,
)
from cephvr.visual_stimulus.rendering.diagnostics import (
    DIAGNOSTIC_SLOTS,
    decode_flags,
    reservation_bytes,
)
from cephvr.visual_stimulus.rendering.engine import RendererEngine
from cephvr.visual_stimulus.rendering.evidence import (
    clip_vertex_components,
    float32_words,
)
from cephvr.visual_stimulus.rendering.motion import (
    evaluate_function,
    integrate_function,
)
from cephvr.visual_stimulus.rendering.projection import off_axis_frustum
from cephvr.visual_stimulus.rendering.scene import ModernGLSceneRenderer
from cephvr.visual_stimulus.rendering.state import InstanceState
from cephvr.visual_stimulus.rendering.types import (
    DisplayInitialization,
    InstanceSnapshot,
    OutputActivity,
    RenderedOutput,
    RenderPassResult,
)


def test_reference_bars_share_exact_pixel_spans_and_restore_scissor():
    from cephvr.visual_stimulus.config.calibration_bars import (
        reference_lengths,
        reference_scale,
    )
    from cephvr.visual_stimulus.rendering.reference_bars import draw_reference_bars

    class Context:
        scissor = (1, 2, 3, 4)

        def clear(self, *color, alpha, viewport):
            calls.append((self.scissor, color, alpha, viewport))

    calls = []
    context = Context()
    width, height = 1279, 719
    x, y = reference_lengths(width, height)
    draw_reference_bars(context, width, height)
    assert context.scissor == (1, 2, 3, 4)
    assert calls[2][0][2] == x
    assert calls[3][0][3] == y
    assert all(scissor == viewport for scissor, _, _, viewport in calls)
    scale = reference_scale(width, height, x / 2, y / 2, 1.5)
    assert scale.mm_per_pixel_x == scale.mm_per_pixel_y == 0.5
    assert scale.projector_distance_mm == pytest.approx(width * 0.5 * 1.5)
    for invalid in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            reference_scale(width, height, invalid, y / 2, 1.5)
    context.clear = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("render failure")
    )
    with pytest.raises(RuntimeError, match="render failure"):
        draw_reference_bars(context, width, height)
    assert context.scissor == (1, 2, 3, 4)


def test_linear_rate_integral_and_keyframe_evaluation() -> None:
    ramp = NS(kind="ramp", initial=0.0, slope_per_s=0.5)
    assert integrate_function(ramp, 0, 2_000_000_000) == pytest.approx(1.0)
    keyframes = NS(
        kind="keyframes",
        interpolation="linear",
        knots=(
            NS(time=NS(seconds="0", ns=lambda: 0), value=0.0),
            NS(time=NS(seconds="2", ns=lambda: 2_000_000_000), value=4.0),
        ),
    )
    assert evaluate_function(keyframes, 1_000_000_000) == pytest.approx(2.0)
    assert integrate_function(keyframes, 0, 2_000_000_000) == pytest.approx(4.0)


def test_instance_absence_pauses_motion_and_return_reanchors() -> None:
    rate = NS(kind="rate", function=NS(kind="constant", value=2.0))
    settings = NS(
        instance_id="bar",
        kind="image",
        width=NS(kind="constant", value=10.0),
        height=NS(kind="constant", value=10.0),
        opacity=NS(kind="constant", value=1.0),
        motion=NS(x=rate, y=NS(kind="hold"), rotation=NS(kind="hold")),
        initial=NS(x=0.0, y=0.0, rotation_deg=0.0),
    )
    live = InstanceState.initialize(settings, now_ns=0, epoch_start_ns=0)
    live.advance(1_000_000_000)
    assert live.values["x"].value == pytest.approx(2.0)
    live.transition(
        None, action="pause", epoch_start_ns=1_000_000_000, now_ns=1_000_000_000
    )
    live.transition(
        settings, action="resume", epoch_start_ns=5_000_000_000, now_ns=5_000_000_000
    )
    live.advance(6_000_000_000)
    assert live.values["x"].value == pytest.approx(4.0)


def test_off_axis_projection_and_float_color_boundaries() -> None:
    frustum = off_axis_frustum(
        observer=(0.0, 0.0, 0.0),
        bottom_left=(-1.0, -1.0, -2.0),
        bottom_right=(1.0, -1.0, -2.0),
        top_left=(-1.0, 1.0, -2.0),
        near=0.1,
        far=10.0,
    )
    assert frustum == pytest.approx((-0.05, 0.05, -0.05, 0.05))
    assert source_over((0.5, 0.0, 0.0, 0.5), (0.0, 0.0, 1.0, 1.0)) == pytest.approx(
        (0.5, 0.0, 0.5, 1.0)
    )
    assert source_over((0.5, 0.5, 0.5, 0.5), (0.0, 0.0, 0.0, 1.0)) == pytest.approx(
        (0.5, 0.5, 0.5, 1.0)
    )
    assert interpolate_inverse_lut((0.0, 0.25, 1.0), 0.5) == pytest.approx(0.25)
    assert quantize_device_code(1.1, 8) == (255, True)


def test_projected_layer_vertices_are_retained_as_exact_shader_words() -> None:
    corners = ((-1.0, -0.5), (0.5, -0.5), (0.5, 1.0), (-1.0, 1.0))
    components = clip_vertex_components(corners)
    assert components == (-1.0, -0.5, 0.5, -0.5, -1.0, 1.0, 0.5, 1.0)
    assert float32_words(components) == tuple(
        int.from_bytes(struct.pack("<f", value), "little") for value in components
    )


@pytest.mark.parametrize("pulse_enabled", [True, False])
def test_engine_freezes_exact_provider_evidence_for_recording(pulse_enabled) -> None:
    artifact = make_prepared_trial()
    if not pulse_enabled:
        artifact = artifact.model_copy(
            update={
                "display": artifact.display.model_copy(
                    update={
                        "photodiode_enabled": False,
                        "pacing_output_id": artifact.display.photodiode_output_id,
                        "photodiode_output_id": "projector/disconnected",
                    }
                )
            }
        )
    display = artifact.display
    output = display.outputs[0]

    class Port:
        def initialize_display(self, selected):
            return DisplayInitialization(
                (output.output_id,),
                ((output.output_id, 8, 8, 8),),
                ((output.output_id, output.width_px, output.height_px),),
                ((output.output_id, 1),),
                (OutputActivity(output.output_id, 1, 2, 1),),
            )

        def prepare_trial(self, prepared, resources):
            assert prepared == artifact
            assert resources is not None

        def render(self, scene, state):
            return RenderPassResult(
                (
                    RenderedOutput(
                        output.output_id, output.width_px, output.height_px, 8, object()
                    ),
                ),
                (),
                (),
                (),
            )

        def present(self, frames):
            return (OutputActivity(output.output_id, 10, 11, 1),)

        def show_idle(self, selected):
            return (OutputActivity(output.output_id, 20, 21, 1),)

    engine = RendererEngine(
        Port(), clock_ns=lambda: 0, resource_provider=lambda _: object()
    )
    engine.initialize_display(display)
    engine.prepare_trial(artifact)
    cancelled_idle = engine.stop_trial()
    assert len(cancelled_idle) == 1 and cancelled_idle[0].output_id == output.output_id
    engine.begin_trial(artifact.identity.trial_id, 0)
    update = engine.render_tick(0)

    assert update.evidence_state.scene_id == update.group.scene_id
    assert update.evidence_state.evaluation_host_ns == 0
    assert update.evidence_state.active_instance_ids
    assert len(update.evidence_submissions) == 1
    assert update.evidence_submissions[0].phase == "returned"
    assert update.evidence_submissions[0].marker_high == update.group.photodiode_high
    if not pulse_enabled:
        assert update.group.photodiode_high is None
        assert update.evidence_submissions[0].marker_index is None
    stopped_idle = engine.stop_trial(1)
    assert len(stopped_idle) == 1 and stopped_idle[0].output_id == output.output_id


def test_arena_state_snapshot_has_no_planar_appearance_requirements():
    settings = NS(
        instance_id="world",
        kind="arena",
        initial=NS(position_mm=(10.0, 20.0), yaw_deg=30.0),
        motion=NS(x=NS(kind="hold"), y=NS(kind="hold"), yaw=NS(kind="hold")),
    )
    state = InstanceState.initialize(settings, now_ns=0, epoch_start_ns=0)
    assert dict(state.snapshot(now_ns=0, epoch_start_ns=0)) == {
        "x": 10.0,
        "y": 20.0,
        "yaw": 30.0,
    }
    state.apply_feedback("x", "movement_integration", 4.0, now_ns=10)
    assert dict(state.snapshot(now_ns=10, epoch_start_ns=0))["x"] == 14.0


def test_arena_model_and_physical_projection_are_finite_and_pose_sensitive():
    settings = NS(
        fixed_height_mm=100.0,
        fixed_pitch_deg=0.0,
        fixed_roll_deg=0.0,
        asset_to_world=(
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )
    origin = arena_model_matrix(settings, {"x": 0.0, "y": 0.0, "yaw": 0.0})
    moved = arena_model_matrix(settings, {"x": 25.0, "y": -5.0, "yaw": 30.0})
    assert origin[0][3] == 0.0 and origin[1][3] == 0.0
    assert moved[0][3] == 25.0 and moved[1][3] == -5.0
    assert moved[0][0] == pytest.approx(3**0.5 / 2)
    assert len(gl_matrix_words(moved)) == 16

    display = make_prepared_trial().display
    surface = display.geometry.surfaces[0]
    projection = off_axis_view_projection(display, surface)
    assert len(projection) == 4 and all(len(row) == 4 for row in projection)
    assert all(value == pytest.approx(value) for row in projection for value in row)


def test_clipping_diagnostic_reservation_and_flag_decode_are_bounded():
    assert DIAGNOSTIC_SLOTS == 16
    assert reservation_bytes(4) == 4 * 16 * 16
    with pytest.raises(ValueError):
        reservation_bytes(-1)
    assert decode_flags((1, 0, 1, 0)) == ("alpha", "device_code")
    with pytest.raises(RuntimeError, match="nonfinite"):
        decode_flags((0, 0, 0, 8))


def test_gpu_diagnostic_ring_preserves_group_order_across_slot_reuse(monkeypatch):
    import sys
    from types import SimpleNamespace

    from cephvr.visual_stimulus.rendering.diagnostics import DiagnosticRing

    class Buffer:
        def __init__(self):
            self.glo = id(self)

        def write(self, data):
            assert len(data) == 16

        def read(self, size):
            assert size == 16
            return bytes(16)

    class Context:
        def buffer(self, *, reserve):
            assert reserve == 16
            return Buffer()

    statuses = {}
    sequence = iter(range(1, 100))
    gl = SimpleNamespace(
        GL_SHADER_STORAGE_BARRIER_BIT=1,
        GL_BUFFER_UPDATE_BARRIER_BIT=2,
        GL_SHADER_STORAGE_BUFFER=3,
        GL_SYNC_GPU_COMMANDS_COMPLETE=4,
        GL_ALREADY_SIGNALED=5,
        GL_CONDITION_SATISFIED=6,
        GL_WAIT_FAILED=7,
        glBindBufferBase=lambda *_: None,
        glMemoryBarrier=lambda *_: None,
        glFenceSync=lambda *_: next(sequence),
        glFlush=lambda: None,
        glClientWaitSync=lambda sync, *_: statuses[sync],
        glDeleteSync=lambda *_: None,
    )
    monkeypatch.setitem(sys.modules, "OpenGL", SimpleNamespace(GL=gl))
    ring = DiagnosticRing(Context(), lambda item: item)
    for group_id in (0, 1):
        ring.begin(group_id, "output", 0, group_id)
        ring.end()
    statuses.update({1: 5, 2: 0})
    assert [item.group_id for item in ring.poll()] == [0]
    ring.begin(2, "output", 0, 2)
    ring.end()
    statuses.update({3: 5})
    assert ring.poll() == ()
    statuses[2] = 5
    assert [item.group_id for item in ring.poll()] == [1, 2]
    ring.begin(3, "output", 0, 3)
    ring.end()
    statuses[4] = 7
    with pytest.raises(RuntimeError, match="fence wait failed"):
        ring.poll()
    ring.release()


def test_scene_dispatch_draws_arena_before_layers_and_records_model_uniform(
    monkeypatch,
):
    artifact = make_prepared_trial()
    mapping = artifact.display.mappings[0]
    layer_setting = artifact.epochs[0].settings[0]
    clip_layout = UniformLayout(
        binding_id="layer-clip",
        instance_id=layer_setting.instance_id,
        output_id=mapping.output_id,
        shader_resource_id="shader",
        name=f"clip_vertices_{mapping.mapping_id}",
        scalar_type="float32",
        shape=(4, 2),
    )
    arena_layout = UniformLayout(
        binding_id="arena-model",
        instance_id="arena",
        output_id=None,
        shader_resource_id="arena-shader",
        name="arena_model_matrix",
        scalar_type="float32",
        shape=(4, 4),
    )
    artifact = artifact.model_copy(
        update={"uniform_layouts": (clip_layout, arena_layout)}
    )
    layer = InstanceSnapshot(
        layer_setting.instance_id,
        "texture",
        True,
        (
            ("x", 0.0),
            ("y", 0.0),
            ("rotation", 0.0),
            ("width", 20.0),
            ("height", 20.0),
            ("frequency", 0.1),
            ("phase_x", 0.0),
            ("phase_y", 0.0),
            ("opacity", 1.0),
            ("contrast", 1.0),
        ),
        layer_setting,
    )
    arena_settings = NS(
        kind="arena",
        instance_id="arena",
        fixed_height_mm=10.0,
        fixed_pitch_deg=0.0,
        fixed_roll_deg=0.0,
        asset_to_world=(
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )
    arena = InstanceSnapshot(
        "arena", "arena", True, (("x", 2.0), ("y", 3.0), ("yaw", 4.0)), arena_settings
    )
    scene = NS(arena_instance_id="arena", layer_instance_ids=(layer.instance_id,))
    events = []
    renderer = ModernGLSceneRenderer()
    renderer._moderngl = NS(TRIANGLE_STRIP=5)

    class Uniform:
        def __init__(self):
            self.value = None
            self.bytes = None

        def write(self, value):
            self.bytes = value

    class Program(dict):
        def __getitem__(self, key):
            return self.setdefault(key, Uniform())

    class Quad:
        def render(self, *, mode):
            assert mode == renderer._moderngl.TRIANGLE_STRIP
            events.append("layer")

    frame = NS(quad_array=Quad(), layer_program=Program(), video_textures={})

    def draw_arena(*_args):
        events.append("arena")

    monkeypatch.setattr(renderer, "_draw_arena", draw_arena)
    uniforms = {}
    renderer._draw_scene_layers(
        frame,
        artifact,
        mapping.output_id,
        mapping,
        scene,
        {"arena": arena, layer.instance_id: layer},
        {},
        uniforms,
    )
    assert events == ["arena", "layer"]
    assert arena_layout.binding_id in uniforms
    assert len(uniforms[arena_layout.binding_id].words) == 16
    assert clip_layout.binding_id in uniforms
    assert frame.layer_program["clip_vertices"].bytes is not None


def test_live_layer_skips_unmapped_surface():
    artifact = make_prepared_trial()
    setting = artifact.epochs[0].settings[0]
    mapping = artifact.display.mappings[0].model_copy(update={"surface_id": "unmapped"})
    snapshot = InstanceSnapshot(
        setting.instance_id,
        "texture",
        True,
        (),
        setting,
    )
    renderer = ModernGLSceneRenderer()
    uniforms = {}
    renderer._draw_scene_layers(
        object(),
        artifact,
        mapping.output_id,
        mapping,
        NS(arena_instance_id=None, layer_instance_ids=(setting.instance_id,)),
        {setting.instance_id: snapshot},
        {},
        uniforms,
    )
    assert not uniforms


def test_native_submission_orders_marker_last_and_preserves_failed_attempt():
    from pathlib import Path

    from cephvr.visual_stimulus.rendering.native import ModernGLPort

    artifact = make_prepared_trial()
    marker = artifact.display.outputs[0]
    other = marker.model_copy(
        update={"output_id": "projector/second", "device_identity": "second"}
    )
    display = artifact.display.model_copy(update={"outputs": (marker, other)})
    events = []

    class GLFW:
        def swap_buffers(self, window):
            events.append(window)
            if window == "second":
                raise RuntimeError("device lost")

    port = ModernGLPort(Path("."), announce=lambda *_: None, clock_ns=lambda: 5)
    port._glfw = GLFW()
    port._display = display
    port._outputs = {
        marker.output_id: NS(window="marker", swap_interval=1, activate=lambda: None),
        other.output_id: NS(window="second", swap_interval=0, activate=lambda: None),
    }
    observed = port.present(
        (NS(output_id=marker.output_id), NS(output_id=other.output_id))
    )
    assert events == ["second", "marker"]
    assert observed[0].error == "VISUAL_STIMULUS_SWAP:device lost"
    assert observed[1].error is None
    assert observed[0].swap_entry_ns == observed[0].swap_return_ns == 5


def test_native_window_attachment_preserves_glfw_context_ownership():
    from cephvr.visual_stimulus.rendering.native_display import (
        NativeRenderingError,
        attach_window_context,
    )

    contexts = []

    class GraphicsAPI:
        def init_context(self):
            contexts.append(NS(version_code=430, release=lambda: None))

        def get_context(self):
            return contexts[-1]

    api = GraphicsAPI()
    first = attach_window_context(api)
    second = attach_window_context(api)
    assert first is not second
    releases = []
    invalid = NS(version_code=420, release=lambda: releases.append("wrapper"))
    with pytest.raises(NativeRenderingError, match="OpenGL 4.3"):
        attach_window_context(
            NS(init_context=lambda: None, get_context=lambda: invalid)
        )
    assert releases == ["wrapper"]


def test_native_failed_gpu_release_keeps_context_for_cleanup_retry():
    from pathlib import Path

    from cephvr.visual_stimulus.rendering.native import ModernGLPort, _OutputContext

    calls = []

    class Resource:
        failing = True

        def release(self):
            if self.failing:
                raise RuntimeError("release pending")
            calls.append("gpu")

    port = ModernGLPort(Path("."), announce=lambda *_: None)
    port._glfw = NS(
        make_context_current=lambda _: None,
        destroy_window=lambda _: calls.append("window"),
        terminate=lambda: calls.append("glfw"),
    )
    resource = Resource()
    port._resources["prepared:image"] = resource
    port._outputs["screen"] = _OutputContext(
        "screen",
        object(),
        NS(release=lambda: calls.append("context")),
        1,
        1,
        8,
        1,
        None,
        lambda: None,
    )
    port._window_obligations.add("screen")
    first = port.release()
    assert first.outstanding and calls == []
    resource.failing = False
    second = port.release()
    assert not second.outstanding
    assert calls == ["gpu", "context", "window", "glfw"]
    assert {
        "visual_stimulus:gpu:prepared:image",
        "visual_stimulus:window:screen",
        "visual_stimulus:glfw",
    } <= set(second.released)


@pytest.mark.parametrize("source,target", [(2.0, 1.0), (1.0, 2.0), (1.0, 1.0)])
def test_image_fit_uv_spans_preserve_aspect_and_center(source, target):
    from cephvr.visual_stimulus.rendering.image_fit import fitted_uv_scale

    contain = fitted_uv_scale("contain", source, target)
    cover = fitted_uv_scale("cover", source, target)
    assert min(contain) == 1.0 and max(contain) >= 1.0
    assert max(cover) == 1.0 and min(cover) <= 1.0
    assert target * contain[1] / contain[0] == pytest.approx(source)
    assert target * cover[1] / cover[0] == pytest.approx(source)
    assert fitted_uv_scale("stretch", source, target) == (1.0, 1.0)


def test_shared_context_wait_uses_unsigned_64_bit_ignored_timeout(monkeypatch):
    from cephvr.visual_stimulus.rendering.capture_sync import order_shared_outputs

    gl = ModuleType("OpenGL.GL")
    events = []
    gl.GL_SYNC_GPU_COMMANDS_COMPLETE = 1
    gl.GL_TIMEOUT_IGNORED = -9223372036854775807
    gl.glFenceSync = lambda *_args: object()
    gl.glFlush = lambda: None
    gl.glWaitSync = lambda fence, flags, timeout: events.append((flags, timeout))
    gl.glDeleteSync = lambda fence: None
    monkeypatch.setitem(sys.modules, "OpenGL.GL", gl)
    root = ModuleType("OpenGL")
    root.GL = gl
    monkeypatch.setitem(sys.modules, "OpenGL", root)
    pending = []
    order_shared_outputs(
        {"one": NS(activate=lambda: None), "two": NS(activate=lambda: None)}, pending
    )
    assert events == [(0, 18446744073709551615)] * 2
    assert not pending


def test_review_capture_clears_framebuffer_in_creation_order(monkeypatch):
    from cephvr.visual_stimulus.rendering.capture import ReviewCapture

    gl = ModuleType("OpenGL.GL")
    gl.GL_PIXEL_PACK_BUFFER = 1
    gl.glBindBuffer = lambda *_args: None

    def stop(*_args):
        raise RuntimeError("reached PBO allocation")

    gl.glGenBuffers = stop
    root = ModuleType("OpenGL")
    root.GL = gl
    monkeypatch.setitem(sys.modules, "OpenGL", root)
    monkeypatch.setitem(sys.modules, "OpenGL.GL", gl)
    modern = ModuleType("moderngl")
    modern.TRIANGLE_STRIP = 1
    monkeypatch.setitem(sys.modules, "moderngl", modern)
    events = []
    texture = NS()
    fbo = NS(
        use=lambda: events.append("use"), clear=lambda *_args: events.append("clear")
    )
    context = NS(
        texture=lambda *_args, **_kwargs: texture,
        framebuffer=lambda **_kwargs: fbo,
        program=lambda **_kwargs: {"source_tex": NS(value=None)},
        buffer=lambda *_args: NS(),
        vertex_array=lambda *_args, **_kwargs: NS(),
    )
    capture = ReviewCapture()
    with pytest.raises(RuntimeError, match="reached PBO allocation"):
        capture.capture(
            (NS(output_id="one", texture_handle=NS(ctx=context)),),
            NS(composite_width=2, composite_height=2, tiles=()),
        )
    assert events == ["use", "clear"]
