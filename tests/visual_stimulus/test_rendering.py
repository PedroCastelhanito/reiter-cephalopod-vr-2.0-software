from __future__ import annotations

import struct
import subprocess
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
    calls.clear()
    draw_reference_bars(context, width, height, x_px=200, y_px=100)
    assert calls[2][0][2] == 200 and calls[3][0][3] == 100
    direct = reference_scale(width, height, 80, 60, x_px=200, y_px=100)
    assert direct.projector_distance_mm is None
    assert direct.projected_width_mm == pytest.approx(width * 0.4)
    custom = reference_scale(width, height, 80, 60, 1.5, x_px=200, y_px=100)
    assert custom.mm_per_pixel_x == pytest.approx(0.4)
    assert custom.mm_per_pixel_y == pytest.approx(0.6)
    assert context.scissor == (1, 2, 3, 4)
    for length in (0, -1, 1.5, width + 1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            reference_lengths(width, height, length, 100)
    for invalid in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            reference_scale(width, height, invalid, y / 2, 1.5)
    context.clear = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("render failure")
    )
    with pytest.raises(RuntimeError, match="render failure"):
        draw_reference_bars(context, width, height)
    assert context.scissor == (1, 2, 3, 4)


def test_output_blackouts_restore_scissor_on_success_and_failure():
    from cephvr.visual_stimulus.config.models.display_profile import PixelRect
    from cephvr.visual_stimulus.rendering.output_masks import clear_regions

    context = NS(scissor=(9, 9, 2, 2))
    calls = []

    def clear(*color, alpha, viewport):
        calls.append((context.scissor, color, alpha, viewport))

    zone = PixelRect(x=1, y=2, width=3, height=4)
    clear_regions(context, clear, (zone,))
    assert calls == [((1, 2, 3, 4), (0, 0, 0), 1, (1, 2, 3, 4))]
    assert context.scissor == (9, 9, 2, 2)

    def fail(*args, **kwargs):
        raise RuntimeError("clear failed")

    with pytest.raises(RuntimeError, match="clear failed"):
        clear_regions(context, fail, (zone,))
    assert context.scissor == (9, 9, 2, 2)


def test_photodiode_pulse_renders_after_blackouts_and_black_frame():
    from cephvr.visual_stimulus.config.models.display_profile import (
        PhotodiodePatch,
        PixelRect,
    )

    artifact = make_prepared_trial()
    output = artifact.display.active_outputs[0]
    zone = PixelRect(x=0, y=0, width=10, height=10)
    patch = PhotodiodePatch(
        rect=PixelRect(x=12, y=13, width=8, height=6),
        background_rect=PixelRect(x=5, y=6, width=30, height=40),
        high_linear_rgb=(1, 1, 1),
        low_linear_rgb=(0, 0, 0),
    )
    display = artifact.display.model_copy(
        update={
            "outputs": (output.model_copy(update={"blackout_zones": (zone,)}),),
            "photodiode_patch": patch,
            "photodiode_output_id": output.output_id,
        }
    )
    artifact = artifact.model_copy(update={"display": display})
    calls = []
    context = NS(scissor=None, screen=None, disable=lambda *_: None)
    program = {
        key: NS(value=None)
        for key in (
            "source_tex",
            "lut_tex",
            "calibrated",
            "lut_size",
            "marker_active",
            "marker_rect",
            "marker_rgb",
        )
    }
    frame = NS(
        context=context,
        output_fbo=NS(clear=lambda *c, **kw: calls.append((c, kw["viewport"]))),
        device_fbo=NS(use=lambda: None),
        output_texture=NS(size=(100, 100), use=lambda *_: None),
        lut_texture=NS(size=(2, 1), use=lambda *_: None),
        output_program=program,
        output_quad_array=NS(render=lambda **_: calls.append("marker/output")),
    )
    renderer = ModernGLSceneRenderer()
    renderer._moderngl = NS(BLEND=1, TRIANGLE_STRIP=5)
    renderer._apply_output(frame, artifact, output.output_id, True, 0)
    assert calls == [
        ((0, 0, 0), (0, 0, 10, 10)),
        ((0, 0, 0), (5, 6, 30, 40)),
        "marker/output",
    ]
    assert program["marker_rect"].value == (0.12, 0.13, 0.2, 0.19)
    assert program["marker_rgb"].value == (1, 1, 1)
    assert context.scissor is None
    with pytest.raises(ValueError, match="fit inside"):
        PhotodiodePatch.model_validate(
            dict(patch.model_dump(), rect=dict(x=0, y=0, width=1, height=1))
        )
    with pytest.raises(ValueError, match="exceeds"):
        type(output).model_validate(
            dict(
                output.model_dump(),
                blackout_zones=(dict(x=99, y=0, width=2, height=2),),
            )
        )


@pytest.mark.parametrize("matches", [0, 2])
def test_saved_monitor_requires_exact_unique_active_identity(monkeypatch, matches):
    from cephvr.platform.windows import display_identity
    from cephvr.visual_stimulus.rendering.native import ModernGLPort
    from cephvr.visual_stimulus.rendering.native_display import DisplayUnavailableError

    monkeypatch.setattr(display_identity, "monitor_interface", lambda *_: "saved")
    glfw = NS(
        get_monitors=lambda: list(range(matches)),
        get_win32_adapter=lambda monitor: monitor,
        get_win32_monitor=lambda monitor: monitor,
    )
    with pytest.raises(DisplayUnavailableError, match=f"matched {matches} active"):
        ModernGLPort._resolve_monitor("SAVED", glfw)
    glfw.get_monitors = lambda: [17]
    assert ModernGLPort._resolve_monitor("SAVED", glfw) == 17


def test_missing_second_monitor_opens_no_windows_and_releases_glfw(tmp_path):
    from cephvr.visual_stimulus.rendering.native import ModernGLPort
    from cephvr.visual_stimulus.rendering.native_display import DisplayUnavailableError
    from cephvr.visual_stimulus.rendering.types import ResourceReleaseReport

    display = make_prepared_trial().display
    first = display.active_outputs[0]
    second = first.model_copy(
        update={"output_id": "second", "device_identity": "missing"}
    )
    display = display.model_copy(update={"outputs": (first, second)})
    resolved, terminated = [], []

    def resolve(identity, glfw):
        resolved.append(identity)
        if identity == "missing":
            raise DisplayUnavailableError("missing saved projector")
        return object()

    port = ModernGLPort(tmp_path, announce=lambda *_: None, monitor_resolver=resolve)
    # Any window or GL call would fail: identity preflight must precede creation.
    port._glfw = NS(terminate=lambda: terminated.append(True))
    port._moderngl = object()
    with pytest.raises(DisplayUnavailableError, match="missing saved"):
        port.initialize_display(display)
    assert resolved == [first.device_identity, "missing"]
    assert terminated == [True]
    assert not port._outputs and not port._window_obligations
    assert port.release() == ResourceReleaseReport(("visual_stimulus:glfw",))


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_wrong_adapter_rejection_requires_native_context_and_window_release(
    monkeypatch, tmp_path, cleanup_fails
):
    from cephvr.platform.windows import nvidia_device
    from cephvr.visual_stimulus.rendering import native
    from cephvr.visual_stimulus.rendering.native_display import (
        DisplayGpuUnavailableError,
        NativeRenderingError,
    )

    selected = nvidia_device.NvidiaDevice(0, "GPU-board", "NVIDIA GeForce RTX 5060 Ti")
    monkeypatch.setattr(nvidia_device, "sys", NS(platform="win32"))
    monkeypatch.setattr(nvidia_device, "_enumerate_cuda_devices", lambda: [selected])
    released, destroyed, terminated = [], [], []

    def release():
        released.append(True)
        if cleanup_fails and len(released) == 1:
            raise RuntimeError("context release unconfirmed")

    context = NS(
        info={"GL_VENDOR": "ATI Technologies Inc.", "GL_RENDERER": "AMD Radeon"},
        screen=object(),
        release=release,
    )
    monkeypatch.setattr(native, "attach_window_context", lambda _: context)
    monkeypatch.setattr(native, "configure_window", lambda *_: None)
    port = native.ModernGLPort(
        tmp_path, announce=lambda *_: None, monitor_resolver=lambda *_: object()
    )
    port._glfw = NS(
        create_window=lambda *_: object(),
        get_current_context=lambda: None,
        make_context_current=lambda *_: None,
        destroy_window=destroyed.append,
        terminate=lambda: terminated.append(True),
    )
    port._moderngl = object()
    expected = NativeRenderingError if cleanup_fails else DisplayGpuUnavailableError
    with pytest.raises(expected, match="AMD Radeon") as failure:
        port.initialize_display(make_prepared_trial().display)
    assert isinstance(failure.value, DisplayGpuUnavailableError) is not cleanup_fails
    assert bool(port._outputs) is cleanup_fails
    if cleanup_fails:
        assert not destroyed and not terminated
        assert not port.release().outstanding
    assert destroyed and terminated and not port._outputs


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
    from dataclasses import replace

    from cephvr.visual_stimulus.rendering.types import ImageSnapshot

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

        def select_images(self, trial_id, epoch_index, snapshots):
            image = ImageSnapshot(
                snapshots[0].instance_id,
                "next",
                1,
                "previous",
                0,
                "residency_hold",
                True,
            )
            return (replace(snapshots[0], image_selection=image), *snapshots[1:])

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
    assert update.evidence_state.images[0].image_index == 0
    assert update.evidence_state.images[0].requested_image_index == 1
    assert update.evidence_state.images[0].repeated
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
        get_current_context=lambda: None,
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


def test_native_trial_skips_source_only_recipe_image_dependency():
    from pathlib import Path

    from cephvr.visual_stimulus.config.models.artifact_models import (
        Fingerprint,
        Resource,
        ResourceManifest,
    )
    from cephvr.visual_stimulus.rendering.native import ModernGLPort
    from cephvr.visual_stimulus.resources.assets import (
        PreparedAssetSet,
        PreparedResourceBundle,
    )

    artifact = make_prepared_trial()
    source = Resource(
        fingerprint=Fingerprint(
            resource_id="recipe-source",
            logical_path="source.png",
            subresource=None,
            sha256="0" * 64,
            bytes=12,
        ),
        kind="image",
        profile_id="Pillow-cephvr1-rgb8-input-v1",
        dependencies=(),
        interpretation=None,
        cpu_bytes=12,
        gpu_bytes=0,
        provider_compatibility="Pillow-cephvr1-rgb8-input-v1",
    )
    manifest = ResourceManifest(format_version=1, resources=(source,), provenance=())
    artifact = artifact.model_copy(update={"manifest": manifest})
    resources = PreparedResourceBundle(
        asset_set=PreparedAssetSet(assets=(), cpu_bytes=0),
        manifest=manifest,
        uniform_layouts=(),
        prepared_content={},
    )
    events = []

    class Scene:
        def bind_graphics_api(self, api):
            pass

        def prepare_trial(self, prepared, bundle, outputs, gpu_resources):
            events.append("scene")

    port = ModernGLPort(
        Path("."),
        announce=lambda key, value: events.append(key),
        scene_renderer=Scene(),
    )
    port._display = artifact.display
    port._moderngl = object()
    port.prepare_trial(artifact, resources)

    assert events == [
        f"visual_stimulus:scene:{artifact.identity.resource_generation}",
        "scene",
    ]
    assert not port._resources


def test_native_trial_keeps_missing_regular_image_content_as_error():
    from pathlib import Path

    from cephvr.visual_stimulus.config.models.artifact_models import (
        Fingerprint,
        Resource,
        ResourceManifest,
    )
    from cephvr.visual_stimulus.rendering.native import ModernGLPort
    from cephvr.visual_stimulus.resources.assets import (
        PreparedAssetSet,
        PreparedResourceBundle,
    )

    artifact = make_prepared_trial()
    resource = Resource(
        fingerprint=Fingerprint(
            resource_id="missing-image",
            logical_path="missing.png",
            subresource=None,
            sha256="0" * 64,
            bytes=12,
        ),
        kind="image",
        profile_id="png_uint_v1",
        dependencies=(),
        interpretation=None,
        cpu_bytes=12,
        gpu_bytes=12,
        provider_compatibility="png-rgb-v1",
    )
    manifest = ResourceManifest(format_version=1, resources=(resource,), provenance=())
    artifact = artifact.model_copy(update={"manifest": manifest})
    resources = PreparedResourceBundle(
        asset_set=PreparedAssetSet(assets=(), cpu_bytes=0),
        manifest=manifest,
        uniform_layouts=(),
        prepared_content={},
    )
    events = []
    port = ModernGLPort(Path("."), announce=lambda key, value: events.append(key))
    port._display = artifact.display

    with pytest.raises(KeyError, match="missing-image"):
        port.prepare_trial(artifact, resources)
    assert events == [
        f"visual_stimulus:gpu:{artifact.identity.resource_generation}:missing-image"
    ]


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


@pytest.mark.parametrize(
    ("pixel_format", "dtype"),
    [("rgba8_bottom_up", "f1"), ("r10g10b10a2_le_bottom_up", "f4")],
)
def test_review_capture_clears_framebuffer_in_creation_order(
    monkeypatch, pixel_format, dtype
):
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
    texture_types = []

    def allocate_texture(*_args, **kwargs):
        texture_types.append(kwargs["dtype"])
        return texture

    context = NS(
        texture=allocate_texture,
        framebuffer=lambda **_kwargs: fbo,
        program=lambda **_kwargs: {"source_tex": NS(value=None)},
        buffer=lambda *_args: NS(),
        vertex_array=lambda *_args, **_kwargs: NS(),
    )
    capture = ReviewCapture()
    with pytest.raises(RuntimeError, match="reached PBO allocation"):
        capture.capture(
            (NS(output_id="one", texture_handle=NS(ctx=context)),),
            NS(
                composite_width=2,
                composite_height=2,
                tiles=(),
                native_pixel_format=pixel_format,
            ),
        )
    assert events == ["use", "clear"]
    assert texture_types == [dtype]
    capture._ensure_compositor(context, 2, 2, pixel_format)
    assert texture_types == [dtype]
    other = (
        "r10g10b10a2_le_bottom_up"
        if pixel_format == "rgba8_bottom_up"
        else "rgba8_bottom_up"
    )
    with pytest.raises(RuntimeError, match="cannot change"):
        capture._ensure_compositor(context, 2, 2, other)
    with pytest.raises(ValueError, match="unsupported"):
        capture._ensure_compositor(context, 2, 2, "unknown")


@pytest.mark.parametrize("mapping", ["valid", "missing", "corrupted"])
def test_review_capture_polls_fence_then_fills_owned_host_buffer(mapping):
    import ctypes

    from cephvr.visual_stimulus.rendering.capture import ReviewCapture, _Pending

    events = []
    signaled = False

    expected = b"\x00\x01\x7f\xff\x02\x03\x80\xfe"
    storage = (ctypes.c_ubyte * 8).from_buffer_copy(expected)

    def read(target, offset, size, flags):
        assert (target, offset, size, flags) == (1, 0, 8, 16)
        events.append("map")
        return None if mapping == "missing" else ctypes.addressof(storage)

    def unmap(target):
        assert target == 1
        events.append("unmap")
        storage[:] = bytes(8)
        return mapping != "corrupted"

    gl = NS(
        GL_PIXEL_PACK_BUFFER=1,
        GL_ALREADY_SIGNALED=2,
        GL_CONDITION_SATISFIED=3,
        GL_WAIT_FAILED=4,
        GL_MAP_READ_BIT=16,
        glClientWaitSync=lambda *_args: 2 if signaled else 0,
        glBindBuffer=lambda *_args: None,
        glMapBufferRange=read,
        glUnmapBuffer=unmap,
        glDeleteSync=lambda *_args: events.append("fence"),
        glDeleteBuffers=lambda *_args: events.append("buffer"),
    )
    capture = ReviewCapture()
    pending = _Pending(gl, 7, 8, 8)
    capture._pending.append(pending)
    assert capture.poll(pending) is None
    assert not events
    signaled = True
    if mapping != "valid":
        with pytest.raises(RuntimeError, match="mapping"):
            capture.poll(pending)
        assert capture._pending == [pending]
        capture.release()
        assert not capture._pending
        assert events[-2:] == ["fence", "buffer"]
        return
    pixels = capture.poll(pending)
    assert isinstance(pixels, bytearray)
    assert pixels == expected
    assert events == ["map", "unmap", "fence", "buffer"]
    assert not capture._pending
    with pytest.raises(TypeError, match="invalid pending"):
        capture.poll(pending)


def test_context_activation_checks_actual_pointer_before_skipping_rebind():
    import ctypes

    from cephvr.visual_stimulus.rendering.native_display import activate_window

    target = ctypes.pointer(ctypes.c_int(1))
    other = ctypes.pointer(ctypes.c_int(2))
    current = ctypes.cast(target, ctypes.POINTER(ctypes.c_int))
    bindings = []
    glfw = NS(
        get_current_context=lambda: current,
        make_context_current=bindings.append,
    )
    activate_window(glfw, target)
    assert not bindings
    current = other
    activate_window(glfw, target)
    assert bindings == [target]
    current = None
    activate_window(glfw, target)
    assert bindings == [target, target]


def test_legacy_texture_recipe_parser_bounds_and_normalizes_json():
    from cephvr.visual_stimulus.resources.texture_recipe import parse_texture_recipe

    recipe = parse_texture_recipe(
        b'{"cephvr_asset_type":"texture_design","kind":"texture",'
        b'"pattern":"sine_grating","params":{"size":64,"tile_width_mm":88}}'
    )
    assert (recipe.pattern, recipe.resolution, recipe.tile_width_mm) == (
        "grating",
        64,
        88,
    )
    resolved = parse_texture_recipe(
        b'{"pattern":"flat","params":{"size":32,"texture_resolution":48}}'
    )
    assert resolved.resolution == 48
    assert (
        parse_texture_recipe(
            b'{"pattern":"flat","params":{"texture_resolution":null}}'
        ).resolution
        == 512
    )
    assert (
        parse_texture_recipe(
            b'{"pattern":"flat","params":{"texture_resolution":""}}'
        ).resolution
        == 512
    )
    legacy = parse_texture_recipe(
        b'{"pattern":"vertical_bars","pattern_params":{"texture_resolution":32}}'
    )
    assert (legacy.pattern, legacy.resolution) == ("bars_vertical", 32)
    with pytest.raises(ValueError, match="Unsupported legacy texture pattern"):
        parse_texture_recipe(b'{"pattern":"future_pattern"}')
    with pytest.raises(ValueError, match="positive integer"):
        parse_texture_recipe(b'{"pattern":"flat","params":{"size":0}}')
    with pytest.raises(ValueError, match="finite"):
        parse_texture_recipe(b'{"pattern":"grating","params":{"phase_cycles":NaN}}')
    with pytest.raises(ValueError, match="allocation limit"):
        parse_texture_recipe(
            b'{"pattern":"flat","params":{"size":65}}', max_texture_pixels=4096
        )
    with pytest.raises(ValueError, match="document limit"):
        parse_texture_recipe(b'{"pattern":"flat"}', max_document_bytes=4)
    with pytest.raises(ValueError, match="document limit"):
        parse_texture_recipe(b'{"pattern":"flat"}', max_document_bytes=0)
    with pytest.raises(ValueError, match="kind must be 'texture'"):
        parse_texture_recipe(b'{"kind":"arena","pattern":"checker"}')
    with pytest.raises(ValueError, match="kind must be 'texture'"):
        parse_texture_recipe(
            b'{"cephvr_asset_type":"texture_design","kind":"arena","pattern":"checker"}'
        )
    with pytest.raises(ValueError, match="does not contain legacy texture"):
        parse_texture_recipe(b'{"name":"a program document"}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        parse_texture_recipe(b'{"pattern":"flat","pattern":"checker"}')
    deeply_nested = (
        b'{"pattern":"flat","params":' + b'{"x":' * 65 + b"0" + b"}" * 65 + b"}"
    )
    with pytest.raises(ValueError, match="nesting budget"):
        parse_texture_recipe(deeply_nested)


def test_legacy_texture_recipe_pixels_match_cephvr1_reference_hashes():
    import hashlib

    import numpy as np

    from cephvr.visual_stimulus.resources.texture_recipe import (
        TextureRecipe,
        generate_texture_recipe,
    )

    # Hashes were generated from sibling CephVR1's texture_gen.py functions;
    # they pin representative deterministic preview outputs at 64x64 RGB8.
    recipes = {
        "grating": TextureRecipe(
            "grating",
            {
                "orientation_deg": 37,
                "cycles_per_texture": 5.5,
                "phase_cycles": 0.125,
                "contrast": 0.8,
                "mean_luminance": 0.42,
                "feature_sharpness": 0.35,
            },
            64,
            None,
            None,
        ),
        "checker": TextureRecipe(
            "checker",
            {
                "color_a": (1, 0.3, 0),
                "color_b": (0, 0, 1),
                "tile_width_mm": 104,
                "cell_size_mm": 20,
                "blur_mm": 0,
            },
            64,
            None,
            None,
        ),
        "checker_blurred": TextureRecipe(
            "checker",
            {
                "color_a": (1, 0.3, 0),
                "color_b": (0, 0, 1),
                "tile_width_mm": 104,
                "cell_size_mm": 20,
                "blur_mm": 2,
            },
            64,
            None,
            None,
        ),
        "noise_binary": TextureRecipe(
            "noise_binary",
            {"color_a": (0.9, 0.8, 0.7), "color_b": (0.05, 0.1, 0.2), "seed": 123},
            64,
            None,
            None,
        ),
        "noise_gray": TextureRecipe(
            "noise_gray",
            {"color_a": (0.9, 0.8, 0.7), "color_b": (0.05, 0.1, 0.2), "seed": 123},
            64,
            None,
            None,
        ),
        "filtered_noise": TextureRecipe(
            "filtered_noise",
            {
                "color_a": (1, 0.8, 0.6),
                "color_b": (0, 0.1, 0.3),
                "seed": 17,
                "features_per_tile": 12,
                "bandwidth_octaves": 0.8,
                "scale_mm": 18,
                "edge_smooth_mm": 0.25,
                "black_fraction": 0.4,
            },
            64,
            None,
            None,
        ),
        "bars_vertical": TextureRecipe(
            "bars_vertical",
            {
                "color_a": (1, 0, 0),
                "color_b": (0, 0, 0),
                "line_spacing_mm": 12,
                "tile_width_mm": 120,
                "line_width_mm": 3,
            },
            64,
            None,
            None,
        ),
        "calibration_grid": TextureRecipe(
            "calibration_grid",
            {
                "color_a": (1, 1, 1),
                "color_b": (0, 0, 0),
                "line_spacing_mm": 20,
                "line_width_mm": 3,
                "color_count": 6,
                "style_cycle_count": 2,
                "dash_length_mm": 8,
                "dash_gap_mm": 10,
            },
            64,
            None,
            None,
        ),
        "dots_grid": TextureRecipe(
            "dots_grid",
            {
                "color_a": (1, 1, 1),
                "color_b": (0, 0, 0),
                "spacing_mm": 30,
                "tile_width_mm": 100,
                "dot_diameter_mm": 10,
                "blur_mm": 0,
            },
            64,
            None,
            None,
        ),
        "dots_rand": TextureRecipe(
            "dots_rand",
            {
                "color_a": (1, 0.4, 0.2),
                "color_b": (0, 0, 0),
                "density_per_cm2": 5,
                "tile_size_mm": 200,
                "dot_diameter_mm": 8,
                "seed": 11,
            },
            64,
            None,
            None,
        ),
    }
    expected = {
        "grating": "592393cdc8e5057451581ba04589ce0f0fd659b969a4702c1e1044d6d5ab375c",
        "checker": "ace6603b143015ba7241d400210bc3eabe010c6d54ea96a3e7a4a51b85a5f6a1",
        "checker_blurred": "8ee0bd2a587d4c9d1bec46c4609b6c2f003171eed7af9d143570d42a079d41b9",
        "noise_binary": "f5b876df5197c62bbf3b937ef04bb58820079a05c7aceaf20de3cdb4253d7308",
        "noise_gray": "7815ffdef342bc6f6b7632b9ddee0c00808be43263d22a30ca08ac84aa004767",
        "filtered_noise": "e9caf46b0f068a5f5fedbc731628fa0f8a243bf2f2632dd6bf4c0fca37b1a8ce",
        "bars_vertical": "393b9a7ea47df5f5a655e8a846aedc1f44655d35418b8aced8a16e8c5b947b37",
        "calibration_grid": "d8dd88559c8b84503bc18c492564839ea3088b2a2b7541d67d4ceb1416096c4d",
        "dots_grid": "e048b51384efea1fcbd13bd38b642bd19d5ac5e794f0f1f72849b757c1eb7ac7",
        "dots_rand": "1aeadb5877918f235543f11909169add18085a62764832d1345bc2ebef14e807",
    }
    for pattern, recipe in recipes.items():
        pixels = generate_texture_recipe(recipe)
        assert pixels.dtype == np.uint8 and pixels.shape == (64, 64, 3)
        assert hashlib.sha256(pixels.tobytes()).hexdigest() == expected[pattern]


def test_legacy_polar_texture_requires_complete_geometry_and_matches_reference():
    import hashlib

    import numpy as np

    from cephvr.visual_stimulus.resources.texture_recipe import (
        TextureRecipe,
        generate_texture_recipe,
    )

    corners = {
        "front": np.array(
            [[-50, 0, 0], [50, 0, 0], [50, 0, 80], [-50, 0, 80]], dtype=np.float32
        ),
        "left": np.array(
            [[-50, -100, 0], [-50, 0, 0], [-50, 0, 80], [-50, -100, 80]],
            dtype=np.float32,
        ),
        "right": np.array(
            [[50, 0, 0], [50, 100, 0], [50, 100, 80], [50, 0, 80]], dtype=np.float32
        ),
        "bottom": np.array(
            [[-50, -100, 0], [50, -100, 0], [50, 0, 0], [-50, 0, 0]], dtype=np.float32
        ),
    }
    recipe = TextureRecipe(
        "polar_grating",
        {
            "origin_screen": "front",
            "target_screen": "right",
            "bar_count": 8,
            "phase_deg": 12,
            "bar_width_mm": 10,
            "feature_sharpness": 0.7,
            "inner_radius_mm": 3,
            "outer_radius_mm": 200,
        },
        64,
        None,
        None,
    )
    with pytest.raises(ValueError, match="surface corners"):
        generate_texture_recipe(recipe)
    with pytest.raises(ValueError, match="corners for bottom"):
        generate_texture_recipe(
            recipe,
            surface_corners={
                key: value for key, value in corners.items() if key != "bottom"
            },
        )
    pixels = generate_texture_recipe(recipe, surface_corners=corners)
    assert (
        hashlib.sha256(pixels.tobytes()).hexdigest()
        == "bfb631bdbde155bc01cea1a4d81cde8fea509aac0eb7128d5bc57bc84fab4ab3"
    )


def test_legacy_image_recipe_requires_explicit_decoded_rgb_pixels():
    import numpy as np

    from cephvr.visual_stimulus.resources.texture_recipe import (
        TextureRecipe,
        generate_texture_recipe,
    )

    recipe = TextureRecipe("image", {"texture_path": "ignored.png"}, 4, None, None)
    with pytest.raises(ValueError, match="explicitly decoded"):
        generate_texture_recipe(recipe)
    source = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    assert np.array_equal(generate_texture_recipe(recipe, image_pixels=source), source)
    gray = np.arange(8, dtype=np.uint8).reshape(2, 4)
    rgb_gray = generate_texture_recipe(recipe, image_pixels=gray)
    assert rgb_gray.shape == (2, 4, 3)
    assert np.array_equal(rgb_gray[:, :, 0], gray)
    assert np.array_equal(rgb_gray[:, :, 1], gray)
    rgba = np.concatenate((source, np.full((2, 4, 1), 128, dtype=np.uint8)), axis=2)
    assert np.array_equal(generate_texture_recipe(recipe, image_pixels=rgba), source)
    with pytest.raises(ValueError, match="8-bit"):
        generate_texture_recipe(recipe, image_pixels=source.astype(np.uint16))


def test_legacy_texture_generator_rejects_unbounded_dot_and_bar_work():
    from cephvr.visual_stimulus.resources.texture_recipe import (
        TextureRecipe,
        generate_texture_recipe,
    )

    huge_grid = TextureRecipe(
        "dots_grid",
        {"spacing_mm": 0.001, "tile_width_mm": 1e300},
        8,
        None,
        None,
    )
    with pytest.raises(ValueError, match="dot count exceeds the raster work limit"):
        generate_texture_recipe(huge_grid)
    overflowing_radius = TextureRecipe(
        "dots_grid",
        {
            "spacing_mm": 1,
            "tile_width_mm": 1,
            "dot_diameter_mm": 1e308,
        },
        8,
        None,
        None,
    )
    with pytest.raises(ValueError, match="finite generation bounds"):
        generate_texture_recipe(overflowing_radius)
    huge_bars = TextureRecipe(
        "bars_vertical",
        {"line_spacing_mm": 0.001, "tile_width_mm": 1e300},
        8,
        None,
        None,
    )
    with pytest.raises(ValueError, match="bar count exceeds the raster work limit"):
        generate_texture_recipe(huge_bars)


def test_legacy_texture_generator_checks_deadline_during_dot_loops():
    from cephvr.visual_stimulus.resources.texture_recipe import (
        TextureRecipe,
        generate_texture_recipe,
    )

    recipe = TextureRecipe(
        "dots_rand",
        {"density_per_cm2": 3, "tile_size_mm": 100, "seed": 1},
        16,
        None,
        None,
    )
    checks = 0

    def expire_after_three_checks():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise TimeoutError("preparation deadline expired")

    with pytest.raises(TimeoutError, match="deadline expired"):
        generate_texture_recipe(recipe, check=expire_after_three_checks)
    assert checks == 3


@pytest.mark.parametrize(
    "document",
    [
        b'{"pattern":"grating","params":{"contrast":"not-a-number"}}',
        b'{"pattern":"checker","params":{"color_a":"nope"}}',
        b'{"pattern":"grating","params":{"seamless":"maybe"}}',
        b'{"pattern":"polar_grating","params":{"origin_screen":12}}',
        b'{"pattern":"flat","params":{"pattern_params":[]}}',
    ],
)
def test_legacy_texture_parser_rejects_malformed_known_parameters(document):
    from cephvr.visual_stimulus.resources.texture_recipe import parse_texture_recipe

    with pytest.raises(ValueError):
        parse_texture_recipe(document)


def test_texture_working_byte_estimate_covers_procedural_peak_scratch():
    from cephvr.visual_stimulus.resources.texture_recipe import (
        TextureRecipe,
        estimated_working_bytes,
    )

    recipe = TextureRecipe("polar_grating", {}, 8, None, None)
    assert estimated_working_bytes(recipe) == 8 * 8 * 192


def test_texture_recipe_parser_import_does_not_load_raster_dependencies():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "from cephvr.visual_stimulus.resources.texture_recipe "
            "import parse_texture_recipe; "
            'parse_texture_recipe(b\'{"pattern":"flat"}\'); '
            "assert 'numpy' not in sys.modules; "
            "assert 'PIL' not in sys.modules",
        ],
        check=True,
    )


def test_texture_recipe_numeric_boolean_values_match_boolean_flags() -> None:
    import json

    import numpy as np

    from cephvr.visual_stimulus.resources.texture_recipe import (
        generate_texture_recipe,
        parse_texture_recipe,
    )

    base = {
        "pattern": "grating",
        "params": {"texture_resolution": 8, "cycles_per_texture": 2.5},
    }
    for numeric, flag in ((0.0, False), (1.0, True)):
        base["params"]["seamless"] = numeric
        numeric_pixels = generate_texture_recipe(
            parse_texture_recipe(json.dumps(base).encode())
        )
        base["params"]["seamless"] = flag
        boolean_pixels = generate_texture_recipe(
            parse_texture_recipe(json.dumps(base).encode())
        )
        np.testing.assert_array_equal(numeric_pixels, boolean_pixels)


def _resident_images(*, count=8):
    import threading

    from cephvr.visual_stimulus.rendering.image_residency import ImageResidency
    from cephvr.visual_stimulus.resources.budget import BoundedBudget
    from cephvr.visual_stimulus.resources.image_schedule import ImageSchedule
    from cephvr.visual_stimulus.resources.image_source import ImageSource

    gate = threading.Event()
    loads = []
    sources = {}
    for index in range(count):
        key = f"image-{index}"

        def load(check, index=index):
            loads.append((index, threading.get_ident()))
            if index == 3:
                while not gate.wait(0.001):
                    check()
            check()
            return bytes([index]) * 16

        sources[key] = ImageSource(key, 1, 1, 192, 16, load)
    schedule = ImageSchedule(
        sources,
        {("trial", key): key for key in sources},
        {"trial": "generation"},
        {"trial": tuple((("layer", key),) for key in sources)},
        {("trial", "layer"): "image-0"},
        {("trial", key): index for index, key in enumerate(sources)},
    )
    budget = BoundedBudget(cpu_limit=192, gpu_limit=48)
    cache = ImageResidency(schedule, budget, announce=lambda *args: None)

    class GPU:
        release_allowed = True
        fail_release = False
        uploads = []

        def upload(self, source, pixels, textures):
            self.uploads.append((source.key, pixels))
            textures.append(source.key)
            return True

        def fence(self, fences):
            fences.append(True)

        def ready(self, fences):
            if not self.release_allowed:
                return False
            fences.clear()
            return True

        def release(self, textures, fences):
            if self.fail_release:
                raise RuntimeError("release rejected")
            textures.clear()
            fences.clear()

    gpu = GPU()
    aliases = {}
    cache.attach(gpu, aliases, lambda *args: None)
    return cache, budget, gpu, gate, loads, aliases


def _resident_snapshot(asset, position=0):
    from cephvr.visual_stimulus.config.models.program_model import ImageTile

    setting = make_prepared_trial().epochs[0].settings[0]
    setting = setting.model_copy(
        update={
            "instance_id": "layer",
            "pattern": ImageTile(
                kind="image_tile",
                asset_id=asset,
                period_x={"kind": "constant", "value": 10},
                period_y={"kind": "constant", "value": 10},
                sampling="linear",
            ),
        }
    )
    return InstanceSnapshot(
        "layer", "texture", True, (("texture_phase_x", position),), setting
    )


def test_image_residency_holds_actual_texture_with_current_motion_and_bounded_reload():
    import threading
    import time

    cache, budget, gpu, gate, loads, aliases = _resident_images()
    try:
        cache.prepare(time.perf_counter_ns() + 2_000_000_000)
        assert set(index for index, _ in loads) == {0, 1, 2}
        assert all(thread != threading.get_ident() for _, thread in loads)
        first = cache.select("trial", 0, (_resident_snapshot("image-0"),))[0]
        assert first.image_selection.image_index == 0
        assert not first.image_selection.repeated
        deadline = time.monotonic() + 2
        held = cache.select("trial", 3, (_resident_snapshot("image-3", 75),))[0]
        assert held.settings.pattern.asset_id == "image-0"
        assert held.state == (("texture_phase_x", 75),)
        assert held.image_selection.requested_image_index == 3
        assert held.image_selection.disposition == "residency_hold"
        assert held.image_selection.repeated
        while not any(index == 3 for index, _ in loads) and time.monotonic() < deadline:
            cache.select("trial", 3, (_resident_snapshot("image-3", 80),))
            time.sleep(0.001)
        assert any(index == 3 for index, _ in loads)
        assert budget.usage.cpu_bytes == 192
        assert budget.usage.gpu_bytes <= 48
        gate.set()
        while time.monotonic() < deadline:
            shown = cache.select("trial", 3, (_resident_snapshot("image-3", 90),))[0]
            if shown.image_selection.image_index == 3:
                break
            time.sleep(0.001)
        assert shown.settings.pattern.asset_id == "image-3"
        assert shown.state == (("texture_phase_x", 90),)
        assert not shown.image_selection.repeated
        assert shown.image_selection.disposition == "current"
        assert aliases["generation:image-3"] == ["image-3"]
        repeated = cache.select("trial", 3, (_resident_snapshot("image-3", 100),))[0]
        assert repeated.image_selection.repeated
        assert budget.usage.cpu_bytes <= 192
        assert budget.usage.gpu_bytes <= 48
        cache.finish("trial")
        cache.begin("trial")
        restarted = cache.select("trial", 0, (_resident_snapshot("image-0"),))[0]
        assert restarted.image_selection.image_index == 0
        assert not restarted.image_selection.repeated
    finally:
        gate.set()
        assert cache.close(time.perf_counter_ns() + 2_000_000_000)
        assert cache.release_gpu() == ()
    assert budget.usage.cpu_bytes == budget.usage.gpu_bytes == 0
    assert not aliases


def test_image_residency_cleanup_retains_gpu_reservation_until_fence_and_release():
    import time

    cache, budget, gpu, gate, _, aliases = _resident_images()
    try:
        cache.prepare(time.perf_counter_ns() + 2_000_000_000)
        assert cache.close(time.perf_counter_ns() + 2_000_000_000)
        gpu.release_allowed = False
        assert cache.release_gpu()
        assert budget.usage.gpu_bytes == 48
        assert not cache.released_keys
        assert not aliases
        gpu.release_allowed = True
        gpu.fail_release = True
        assert cache.release_gpu()
        assert budget.usage.gpu_bytes == 48
        gpu.fail_release = False
        assert cache.release_gpu() == ()
        assert budget.usage.gpu_bytes == 0
        assert len(cache.released_keys) == 3
    finally:
        gate.set()
        cache.close(time.perf_counter_ns() + 2_000_000_000)
        gpu.fail_release = False
        gpu.release_allowed = True
        cache.release_gpu()


def test_image_upload_submits_bounded_chunks_without_repeating_color_conversion():
    from cephvr.visual_stimulus.rendering.image_gpu import ImageGpu
    from cephvr.visual_stimulus.resources.image_source import ImageSource

    calls = []

    class Texture:
        def write(self, data, *, viewport, alignment):
            calls.append((len(data), viewport, alignment))

    class Context:
        def texture(self, size, channels, *, dtype):
            assert size == (1024, 128) and channels == 4 and dtype == "f4"
            return Texture()

    gpu = ImageGpu({"output": NS(context=Context(), activate=lambda: None)})
    source = ImageSource("key", 1024, 128, 4_000_000, 2_097_152, lambda check: b"")
    textures = []
    pixels = bytes(2_097_152)
    assert not gpu.upload(source, pixels, textures)
    assert gpu.upload(source, pixels, textures)
    assert len(textures) == 1
    assert calls == [
        (1_048_576, (0, 0, 1024, 64), 1),
        (1_048_576, (0, 64, 1024, 64), 1),
    ]


def test_image_lookahead_skips_long_repeated_history_without_scanning_suffix():
    from cephvr.visual_stimulus.resources.image_schedule import ImageLookahead

    reads = []

    class Uses(tuple):
        def __getitem__(self, index):
            reads.append(index)
            return super().__getitem__(index)

    cursor = ImageLookahead(
        {
            "a": Uses(range(0, 100_000, 3)),
            "b": Uses(range(1, 100_000, 3)),
            "c": Uses(range(2, 100_000, 3)),
            "d": Uses((90_000,)),
        }
    )
    reads.clear()
    cursor.advance(50_001)
    assert tuple(cursor) == ("a", "b", "c", "d")
    assert len(reads) < 80
    reads.clear()
    cursor.advance(50_002)
    assert tuple(cursor) == ("b", "c", "a", "d")
    assert len(reads) < 25
    with pytest.raises(ValueError, match="backwards"):
        cursor.advance(1)
