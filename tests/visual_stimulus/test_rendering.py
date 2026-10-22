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


@pytest.mark.parametrize("bits", [8, 10])
def test_projector_window_recreation_preserves_operator_cursor(bits):
    from cephvr.visual_stimulus.rendering.native_display import configure_window

    output = (
        make_prepared_trial()
        .display.active_outputs[0]
        .model_copy(update={"rgb_bits_per_channel": bits})
    )

    class Windows:
        TRUE, FALSE = 1, 0
        hints = {}
        cursor = (300, 200)

        def __getattr__(self, name):
            if name.isupper():
                return name
            raise AttributeError(name)

        def default_window_hints(self):
            self.hints = {self.CENTER_CURSOR: self.TRUE, self.AUTO_ICONIFY: self.TRUE}

        def window_hint(self, hint, value):
            self.hints[hint] = value

        def create_fullscreen(self):
            if self.hints[self.CENTER_CURSOR]:
                self.cursor = (2560, 360)

    windows = Windows()
    for _ in range(3):
        configure_window(windows, output)
        windows.create_fullscreen()
        assert windows.cursor == (300, 200)
        assert windows.hints[windows.AUTO_ICONIFY] == windows.FALSE
        assert windows.hints[windows.RED_BITS] == bits
        assert windows.hints[windows.GREEN_BITS] == bits
        assert windows.hints[windows.BLUE_BITS] == bits
        assert windows.hints[windows.REFRESH_RATE] > 0


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
    assert calls[-2][0][2] == x
    assert calls[-1][0][3] == y
    assert [rectangle for rectangle, color, _, _ in calls if color == (1, 1, 1)] == [
        (0, 0, width, 2),
        (0, height - 2, width, 2),
        (0, 0, 2, height),
        (width - 2, 0, 2, height),
    ]
    assert all(scissor == viewport for scissor, _, _, viewport in calls)
    scale = reference_scale(width, height, x / 2, y / 2, 1.5)
    assert scale.mm_per_pixel_x == scale.mm_per_pixel_y == 0.5
    assert scale.projector_distance_mm == pytest.approx(width * 0.5 * 1.5)
    calls.clear()
    draw_reference_bars(context, width, height, x_px=200, y_px=100)
    assert calls[-2][0][2] == 200 and calls[-1][0][3] == 100
    assert len(calls) == 8
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


def test_idle_uses_prepared_valid_area_union_and_restores_scissor():
    from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
    from cephvr.visual_stimulus.rendering.output_masks import clear_valid_background

    display = make_prepared_trial().display
    output = display.active_outputs[0]
    mappings = [m for m in display.active_mappings if m.output_id == output.output_id]
    profiles = {}
    for mapping in mappings:
        profiles[mapping.mapping_id] = GeometricProfile.model_validate(
            dict(
                format_version=1,
                calibration_id="valid-area",
                mapping_id=mapping.mapping_id,
                surface_id=mapping.surface_id,
                output_id=output.output_id,
                output_width=output.width_px,
                output_height=output.height_px,
                viewport=mapping.viewport,
                rows=2,
                columns=2,
                vertices=tuple(
                    dict(uv=p, xy=p) for p in ((0, 0), (1, 0), (0, 1), (1, 1))
                ),
                orientation="preserving",
                diagonal="bottom_left_to_top_right",
                mask=None,
                weight=None,
                overlap_group=None,
                intended_coverage=((0, 0), (1, 0), (1, 1), (0, 1)),
                coverage_tolerance=1e-6,
                triangle_area_tolerance=1e-9,
                valid_area=(0.2, 0.3, 0.8, 0.9),
            )
        )
    calls = []
    context = NS(scissor=(2, 3, 4, 5))
    context.clear = lambda *color, **kwargs: calls.append(
        (context.scissor, color, kwargs)
    )
    clear_valid_background(
        context, (0.3, 0.4, 0.5), output, display, NS(content=profiles)
    )
    assert calls[0][0] is None and calls[0][1] == (0, 0, 0)
    assert len(calls) == len(mappings) + 1
    assert all(c[0] == (20, 30, 60, 60) and c[1] == (0.3, 0.4, 0.5) for c in calls[1:])
    assert context.scissor == (2, 3, 4, 5)
    for key in profiles:
        profiles[key] = profiles[key].model_copy(update={"valid_area": None})
    calls.clear()
    clear_valid_background(
        context, (0.3, 0.4, 0.5), output, display, NS(content=profiles)
    )
    assert len(calls) == 1 and calls[0][1] == (0.3, 0.4, 0.5)


@pytest.mark.parametrize("per_output", [False, True])
def test_photodiode_pulse_renders_after_blackouts_and_black_frame(per_output):
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
    if per_output:
        display = display.model_copy(
            update={
                "photodiode_output_id": None,
                "photodiode_patch": None,
                "photodiode_patches": {output.output_id: patch},
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
    if per_output:
        other = output.model_copy(
            update={
                "output_id": "other",
                "device_identity": "other",
                "blackout_zones": (),
            }
        )
        extra = patch.model_copy(
            update={
                "rect": PixelRect(x=20, y=21, width=2, height=3),
                "background_rect": None,
            }
        )
        display = display.model_copy(
            update={
                "outputs": (output, other),
                "photodiode_patches": {output.output_id: patch, "other": extra},
            }
        )
        second = artifact.model_copy(update={"display": display})
        calls.clear()
        renderer._apply_output(frame, second, "other", False, 0)
        assert calls == ["marker/output"]
        assert program["marker_rect"].value == (0.2, 0.21, 0.22, 0.24)
        assert program["marker_rgb"].value == (0, 0, 0)
        display = display.model_copy(
            update={"photodiode_patches": {output.output_id: patch}}
        )
        renderer._apply_output(
            frame, artifact.model_copy(update={"display": display}), "other", True, 0
        )
        assert program["marker_active"].value == 0
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
@pytest.mark.parametrize("multiple", [False, True])
def test_engine_freezes_exact_provider_evidence_for_recording(
    pulse_enabled, multiple
) -> None:
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
    if multiple:
        outputs = (
            output,
            output.model_copy(
                update={"output_id": "second", "device_identity": "second"}
            ),
            output.model_copy(
                update={"output_id": "blank", "device_identity": "blank"}
            ),
        )
        display = display.model_copy(
            update={
                "outputs": outputs,
                "photodiode_output_id": None,
                "photodiode_patch": None,
                "photodiode_patches": {
                    o.output_id: artifact.display.photodiode_patch for o in outputs[:2]
                },
                "pacing_output_id": output.output_id,
            }
        )
        artifact = artifact.model_copy(update={"display": display})
    outputs = display.active_outputs

    class Port:
        def initialize_display(self, selected):
            return DisplayInitialization(
                tuple(o.output_id for o in outputs),
                tuple((o.output_id, 8, 8, 8) for o in outputs),
                tuple((o.output_id, o.width_px, o.height_px) for o in outputs),
                tuple(
                    (o.output_id, display.requested_swap_interval(o.output_id))
                    for o in outputs
                ),
                tuple(
                    OutputActivity(
                        o.output_id, 1, 2, display.requested_swap_interval(o.output_id)
                    )
                    for o in outputs
                ),
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
                tuple(
                    RenderedOutput(o.output_id, o.width_px, o.height_px, 8, object())
                    for o in outputs
                ),
                (),
                (),
                (),
            )

        def present(self, frames):
            return tuple(
                OutputActivity(
                    o.output_id, 10, 11, display.requested_swap_interval(o.output_id)
                )
                for o in outputs
            )

        def show_idle(self, selected):
            return tuple(
                OutputActivity(
                    o.output_id, 20, 21, display.requested_swap_interval(o.output_id)
                )
                for o in outputs
            )

    engine = RendererEngine(
        Port(), clock_ns=lambda: 0, resource_provider=lambda _: object()
    )
    engine.initialize_display(display)
    engine.prepare_trial(artifact)
    cancelled_idle = engine.stop_trial()
    assert {o.output_id for o in cancelled_idle} == {o.output_id for o in outputs}
    engine.begin_trial(artifact.identity.trial_id, 0)
    update = engine.render_tick(0)

    assert update.evidence_state.scene_id == update.group.scene_id
    assert update.evidence_state.evaluation_host_ns == 0
    assert update.evidence_state.images[0].image_index == 0
    assert update.evidence_state.images[0].requested_image_index == 1
    assert update.evidence_state.images[0].repeated
    assert update.evidence_state.active_instance_ids
    assert len(update.evidence_submissions) == len(outputs)
    for submission in update.evidence_submissions:
        assert submission.phase == "returned"
        expected_marker = submission.output_id in display.marker_patches
        assert submission.marker_high == (
            update.group.photodiode_high if expected_marker else None
        )
        assert submission.marker_index == (0 if expected_marker else None)
    if not pulse_enabled:
        assert update.group.photodiode_high is None
    stopped_idle = engine.stop_trial(1)
    assert {o.output_id for o in stopped_idle} == {o.output_id for o in outputs}


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


@pytest.mark.parametrize(
    "angles", [(0, 0, 0), (90, 0, 0), (35, -20, 17), (-175, 80, -110)]
)
def test_effective_arena_pose_matches_rendered_rigid_transform(angles):
    from cephvr.visual_stimulus.rendering.arena import effective_arena_pose

    yaw, pitch, roll = angles
    settings = NS(
        kind="arena",
        instance_id="arena",
        world_frame_id="world",
        fixed_height_mm=12.0,
        fixed_pitch_deg=pitch,
        fixed_roll_deg=roll,
        asset_to_world=((1, 0, 0, 8), (0, 1, 0, 9), (0, 0, 1, 10), (0, 0, 0, 1)),
    )
    state = {"x": 2.0, "y": -3.0, "yaw": yaw}
    snapshot = InstanceSnapshot("arena", "arena", True, tuple(state.items()), settings)
    pose = effective_arena_pose(snapshot)
    assert pose.instance_id == "arena" and pose.frame_id == "world"
    assert pose.position_mm == (2.0, -3.0, 12.0)
    x, y, z, w = pose.orientation_xyzw
    assert x * x + y * y + z * z + w * w == pytest.approx(1)
    rotation = (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )
    model = arena_model_matrix(settings, state)
    for row in range(3):
        assert model[row][:3] == pytest.approx(rotation[row])
        assert model[row][3] == pytest.approx(
            pose.position_mm[row]
            + sum(rotation[row][j] * settings.asset_to_world[j][3] for j in range(3))
        )


def test_scene_render_group_retains_only_the_active_arena_pose():
    artifact = make_prepared_trial()
    trial_id = artifact.identity.trial_id
    renderer = ModernGLSceneRenderer()
    renderer._moderngl = NS()
    renderer._artifacts[trial_id] = artifact.model_copy(update={"uniform_layouts": ()})
    renderer._outputs[trial_id] = {}
    renderer._resources[trial_id] = {}
    renderer._gpu_resources[trial_id] = {}
    settings = NS(
        kind="arena",
        instance_id="arena",
        world_frame_id="world",
        fixed_height_mm=4,
        fixed_pitch_deg=0,
        fixed_roll_deg=0,
        asset_to_world=((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)),
    )
    snapshot = InstanceSnapshot(
        "arena", "arena", True, (("x", 1), ("y", 2), ("yaw", 0)), settings
    )
    scene = NS(arena_instance_id="arena")
    result = renderer.render_group(
        (scene, False, 0, trial_id, 0, 0, 0), (snapshot,), {}, {}
    )
    assert len(result.effective_poses) == 1
    assert result.effective_poses[0].position_mm == (1, 2, 4)
    result = renderer.render_group(
        (NS(arena_instance_id=None), False, 0, trial_id, 1, 0, 1), (), {}, {}
    )
    assert result.effective_poses == ()


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
    from cephvr.visual_stimulus.config.review_layout import review_layout

    artifact = artifact.model_copy(
        update={"preview_layout": review_layout(artifact.display)}
    )
    port.preview = NS()  # This source-dependency test uses an already prepared viewer.
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
    [("rgba8_top_down", "f1"), ("r10g10b10a2_le_top_down", "f4")],
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
    assert events == ["use", "clear", "use"]
    assert texture_types == [dtype, dtype]
    capture._ensure_compositor(context, 2, 2, pixel_format)
    assert texture_types == [dtype, dtype]
    other = (
        "r10g10b10a2_le_top_down"
        if pixel_format == "rgba8_top_down"
        else "rgba8_top_down"
    )
    with pytest.raises(RuntimeError, match="cannot change"):
        capture._ensure_compositor(context, 2, 2, other)
    with pytest.raises(ValueError, match="unsupported"):
        capture._ensure_compositor(context, 2, 2, "unknown")


@pytest.mark.parametrize("mapping", ["valid", "missing", "corrupted"])
def test_review_capture_polls_fence_then_fills_owned_host_buffer(mapping):
    import ctypes

    from cephvr.visual_stimulus.rendering.capture import (
        ReviewCapture,
        _Buffer,
        _Pending,
    )

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
    pending = _Pending(_Buffer(gl, 7, 8), 8)
    capture._pending.append(pending)
    assert capture.poll(pending) is None
    assert not events
    signaled = True
    if mapping != "valid":
        with pytest.raises(RuntimeError, match="mapping"):
            capture.poll(pending)
        assert capture._pending == [pending]
        with pytest.raises(RuntimeError, match="cleanup is required"):
            capture.poll(pending)
        capture.release()
        assert not capture._pending
        assert events[-2:] == ["fence", "buffer"]
        return
    pixels = capture.poll(pending)
    assert isinstance(pixels, bytearray)
    assert pixels == expected
    assert events == ["map", "unmap", "fence"]
    assert capture._available == [pending.buffer]
    assert not capture._pending
    with pytest.raises(TypeError, match="invalid pending"):
        capture.poll(pending)

    capture.release()
    assert not capture._available
    assert events[-1] == "buffer"


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
    import json

    import numpy as np

    from cephvr.visual_stimulus.resources.texture_recipe import (
        TextureRecipe,
        generate_texture_recipe,
        parse_texture_recipe,
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
    for pattern in ("grating", "polar_grating"):
        for channel in ("color_a", "color_b"):
            for values, clamped in (
                ([1e308, -1e308, 0.5], [1, 0, 0.5]),
                ([-1e308, 0.5, 1e308], [0, 0.5, 1]),
            ):
                rasters = [
                    generate_texture_recipe(
                        parse_texture_recipe(
                            json.dumps(
                                {
                                    "pattern": pattern,
                                    "params": {"size": 8, channel: rgb},
                                }
                            ).encode()
                        ),
                        surface_corners=corners,
                    )
                    for rgb in (values, clamped)
                ]
                np.testing.assert_array_equal(*rasters)


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


def _resident_images(*, count=8, batch=False, progress=None):
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
    registrations = []
    sealed = False

    def register_many(items):
        if sealed:
            raise RuntimeError("cannot add resources after Ready")
        registrations.append(items)

    cache = ImageResidency(
        schedule,
        budget,
        announce=lambda *args: None,
        announce_batch=register_many if batch else None,
        progress=progress,
    )

    class GPU:
        release_allowed = True
        fail_release = False
        uploads = []

        def upload(self, source, pixels, textures):
            self.uploads.append((source.key, pixels))
            textures.append(source.key)
            return True

        def fence(self, textures, fences):
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
    cache.attach(gpu, aliases, lambda key, path: register_many(((key, path),)))
    assert len(registrations) == (1 if batch else count)
    assert sum(len(items) for items in registrations) == count
    assert budget.usage.gpu_bytes == 0
    sealed = True
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


@pytest.mark.parametrize("batch", [False, True])
def test_image_residency_holds_actual_texture_with_current_motion_and_bounded_reload(
    batch,
):
    import threading
    import time

    cache, budget, gpu, gate, loads, aliases = _resident_images(batch=batch)
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
        assert cache.released_keys == {
            f"visual_stimulus:gpu:resident-image:image-{index}" for index in range(3, 8)
        }
        assert not aliases
        gpu.release_allowed = True
        gpu.fail_release = True
        assert cache.release_gpu()
        assert budget.usage.gpu_bytes == 48
        gpu.fail_release = False
        assert cache.release_gpu() == ()
        assert budget.usage.gpu_bytes == 0
        assert len(cache.released_keys) == 8
    finally:
        gate.set()
        cache.close(time.perf_counter_ns() + 2_000_000_000)
        gpu.fail_release = False
        gpu.release_allowed = True
        cache.release_gpu()


@pytest.mark.parametrize("completion", ["eventual", "pending", "error"])
def test_image_cleanup_services_fences_within_original_deadline(completion):
    import time

    cache, budget, gpu, gate, _, _ = _resident_images()
    try:
        cache.prepare(time.perf_counter_ns() + 2_000_000_000)
        assert cache.close(time.perf_counter_ns() + 2_000_000_000)
        original_ready = gpu.ready
        polls = []
        fence_calls = []
        original_fence = gpu.fence

        def fence(textures, fences):
            fence_calls.append(id(textures))
            original_fence(textures, fences)

        def ready(fences):
            polls.append(id(fences))
            if completion == "error":
                raise RuntimeError("completion check failed")
            if completion == "pending" or polls.count(id(fences)) == 1:
                return False
            return original_ready(fences)

        gpu.fence, gpu.ready = fence, ready
        # The previous one-shot path rejects even a fence that settles next poll.
        assert cache.release_gpu()
        assert budget.usage.gpu_bytes == 48
        polls.clear()
        ticks = iter(range(100, 1000))
        cache.clock_ns = lambda: next(ticks)
        errors = cache.release_gpu(deadline_ns=120)
        assert len(fence_calls) == len(set(fence_calls))
        if completion == "eventual":
            assert not errors
            assert budget.usage.gpu_bytes == 0
            assert len(polls) == 6
        else:
            assert errors
            assert budget.usage.gpu_bytes == 48
            assert len(cache.released_keys) == 5
            if completion == "error":
                assert all("completion check failed" in error for error in errors)
                assert len(polls) == 3
            else:
                assert all("GPU completion pending" in error for error in errors)
                assert len(polls) <= 20
    finally:
        gate.set()
        gpu.ready = original_ready
        cache.clock_ns = time.perf_counter_ns
        cache.close(time.perf_counter_ns() + 2_000_000_000)
        cache.release_gpu()


@pytest.mark.parametrize("expired", [False, True])
def test_image_cleanup_does_not_poll_after_original_deadline(monkeypatch, expired):
    import time

    cache, budget, gpu, gate, _, _ = _resident_images()
    original_ready = gpu.ready
    try:
        cache.prepare(time.perf_counter_ns() + 2_000_000_000)
        assert cache.close(time.perf_counter_ns() + 2_000_000_000)
        now, polls = [120 if expired else 100], []

        def ready(fences):
            polls.append(True)
            return len(polls) > 1

        gpu.ready = ready
        cache.clock_ns = lambda: now[0]
        monkeypatch.setattr(time, "sleep", lambda _: now.__setitem__(0, 120))
        assert cache.release_gpu(deadline_ns=120)
        assert len(polls) == (0 if expired else 1)
        assert budget.usage.gpu_bytes == 48
        assert len(cache.released_keys) == 5
    finally:
        gate.set()
        gpu.ready = original_ready
        cache.clock_ns = time.perf_counter_ns
        cache.close(time.perf_counter_ns() + 2_000_000_000)
        cache.release_gpu()


@pytest.mark.parametrize("physical", [False, True])
def test_image_schedule_unions_only_consuming_outputs_across_trials(physical):
    from cephvr.visual_stimulus.resources.image_schedule import ImageSchedule
    from cephvr.visual_stimulus.resources.image_source import ImageSource

    source = ImageSource("shared", 2, 3, 256, 2 * 3 * 16 * 4, lambda check: b"")
    artifacts, bundles = [], {}
    for trial, surface in (("first", "left"), ("second", "bottom")):
        space = (
            NS(kind="physical_surface", mappings=(NS(surface_id=surface),))
            if physical
            else NS(kind="visual_angle", surfaces=(surface,))
        )
        setting = NS(kind="image", asset_id="image", instance_id="layer", space=space)
        artifacts.append(
            NS(
                identity=NS(trial_id=trial, resource_generation=trial),
                display=NS(
                    active_mappings=tuple(
                        NS(surface_id=name, output_id=name)
                        for name in ("front", "left", "right", "bottom")
                    )
                ),
                epochs=(NS(settings=(setting,)),),
            )
        )
        bundles[trial] = NS(image_sources={"image": source})
    schedule = ImageSchedule.build(tuple(artifacts), bundles)
    assert schedule.sources["shared"].output_ids == ("bottom", "left")
    assert schedule.sources["shared"].gpu_bytes == 2 * 3 * 16 * 2
    assert source.output_ids is None  # Preparation sources remain immutable.


@pytest.mark.parametrize("selected", [("bottom",), ("left",), ("left", "bottom")])
def test_image_upload_and_release_skip_unconsumed_output_contexts(selected):
    from cephvr.visual_stimulus.rendering.image_gpu import ImageGpu
    from cephvr.visual_stimulus.resources.image_source import ImageSource

    allocated, writes, released = [], [], []

    class Texture:
        def __init__(self, name):
            self.name = name

        def write(self, data, **kwargs):
            writes.append(self.name)

        def release(self):
            released.append(self.name)

    class Context:
        def __init__(self, name):
            self.name = name

        def texture(self, *args, **kwargs):
            allocated.append(self.name)
            return Texture(self.name)

    names = ("front", "left", "right", "bottom")
    gpu = ImageGpu(
        {name: NS(context=Context(name), activate=lambda: None) for name in names}
    )
    source = ImageSource(
        "image", 2, 3, 256, 96 * len(selected), lambda check: b"", selected
    )
    textures = []
    for _ in range(5):
        if gpu.upload(source, bytes(96), textures):
            break
    else:
        pytest.fail("upload did not finish")
    assert allocated == list(selected)
    assert writes == list(selected)
    for index, name in enumerate(names):
        assert (index < len(textures) and textures[index] is not None) == (
            name in selected
        )
    gpu.release(textures, [])
    assert released == list(reversed(selected))
    assert textures == []


@pytest.mark.parametrize(
    "allocated", [(), (None, "left"), (None, "left", None, "bottom")]
)
def test_image_fences_only_allocated_contexts_including_partial_upload(
    monkeypatch, allocated
):
    from cephvr.visual_stimulus.rendering.image_gpu import ImageGpu

    active = []
    deleted = []
    gl = NS(
        GL_SYNC_GPU_COMMANDS_COMPLETE=1,
        GL_WAIT_FAILED=2,
        GL_ALREADY_SIGNALED=3,
        GL_CONDITION_SATISFIED=4,
        glFenceSync=lambda *_: active[-1],
        glFlush=lambda: None,
        glClientWaitSync=lambda *_: 3,
        glDeleteSync=deleted.append,
    )
    monkeypatch.setitem(sys.modules, "OpenGL", NS(GL=gl))
    outputs = {
        name: NS(activate=lambda n=name: active.append(n))
        for name in ("front", "left", "right", "bottom")
    }
    gpu = ImageGpu(outputs)
    fences = []
    gpu.fence(list(allocated), fences)
    expected = [name for name in allocated if name is not None]
    assert active == expected
    assert [fence for _, fence in fences] == expected
    active.clear()
    if expected:
        gl.glClientWaitSync = lambda *_: 5  # Not yet signalled.
        assert not gpu.ready(fences)
        assert [fence for _, fence in fences] == expected
        assert deleted == []
        active.clear()
        gl.glClientWaitSync = lambda *_: gl.GL_WAIT_FAILED
        with pytest.raises(RuntimeError, match="completion check failed"):
            gpu.ready(fences)
        assert [fence for _, fence in fences] == expected
        assert deleted == []
        active.clear()
        gl.glClientWaitSync = lambda *_: 3
    assert gpu.ready(fences)
    assert active == deleted == expected
    assert fences == []


def test_image_upload_submits_bounded_batches_without_repeating_color_conversion():
    from cephvr.visual_stimulus.rendering.image_gpu import ImageGpu
    from cephvr.visual_stimulus.resources.image_source import ImageSource

    calls = []

    class Texture:
        def write(self, data, *, viewport, alignment):
            calls.append((len(data), viewport, alignment))

    class Context:
        def texture(self, size, channels, *, dtype):
            assert size == (1024, 512) and channels == 4 and dtype == "f4"
            return Texture()

    gpu = ImageGpu({"output": NS(context=Context(), activate=lambda: None)})
    source = ImageSource("key", 1024, 512, 16_000_000, 8_388_608, lambda check: b"")
    textures = []
    pixels = bytes(8_388_608)
    assert not gpu.upload(source, pixels, textures)
    assert len(calls) == 4
    assert gpu.upload(source, pixels, textures)
    assert len(textures) == 1
    assert calls == [(1_048_576, (0, row, 1024, 64), 1) for row in range(0, 512, 64)]


def test_four_screen_image_set_upload_has_headroom_for_600ms_presentations():
    import tomllib
    from pathlib import Path

    from cephvr.visual_stimulus.rendering import image_gpu
    from cephvr.visual_stimulus.rendering.image_gpu import ImageGpu
    from cephvr.visual_stimulus.resources.image_source import ImageSource

    policy = tomllib.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts/policy/visual_stimulus_policy.toml"
        ).read_text()
    )["image_residency"]
    assert image_gpu.UPLOAD_CHUNK_BYTES == policy["upload_chunk_bytes"]
    assert image_gpu.UPLOAD_CHUNKS_PER_TURN == policy["upload_chunks_per_turn"]
    sizes = {
        "front": (760, 690),
        "left": (1030, 680),
        "right": (1025, 695),
        "bottom": (685, 940),
    }
    copied = bytearray()

    class Texture:
        def write(self, data, **kwargs):
            assert len(data) <= 1_048_576
            copied.extend(data)

    gpu = ImageGpu(
        {
            name: NS(
                activate=lambda: None,
                context=NS(texture=lambda *args, **kwargs: Texture()),
            )
            for name in sizes
        }
    )
    turns = 0
    for name, (width, height) in sizes.items():
        source = ImageSource(
            name, width, height, 0, width * height * 16, lambda check: b"", (name,)
        )
        pixels = bytes(range(256)) * (width * height // 16)
        pixels += bytes(range((width * height * 16) % 256))
        copied.clear()
        textures = []
        while True:
            turns += 1
            if gpu.upload(source, pixels, textures):
                break
            assert turns < 36
        assert copied == pixels
    # Leave at least half the 36 refresh turns for decode, fences and rendering.
    assert turns <= 18


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


def test_physical_corners_use_surface_center_as_local_origin():
    # V14: a stimulus centered on the surface spans -1..1; the map moves it elsewhere.
    from cephvr.visual_stimulus.rendering.layer_projection import physical_corners

    surface = NS(
        surface_id="front",
        bottom_left_mm=(0.0, 0.0, 0.0),
        bottom_right_mm=(200.0, 0.0, 0.0),
        top_left_mm=(0.0, 100.0, 0.0),
    )
    artifact = NS(display=NS(geometry=NS(surfaces=[surface])))
    identity = NS(matrix=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
    state = {"x": 0.0, "y": 0.0, "width": 200.0, "height": 100.0}
    corners = physical_corners(artifact, NS(state=state), "front", identity)
    assert corners == [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    edge = physical_corners(
        artifact, NS(state={**state, "x": 100.0, "y": 50.0}), "front", identity
    )
    assert edge[0] == (0.0, 0.0)


def test_native_provenance_uses_each_actual_context_and_detects_driver_changes(
    tmp_path,
):
    from cephvr.visual_stimulus.rendering.native import ModernGLPort

    port = ModernGLPort(tmp_path, announce=lambda *_: None)
    with pytest.raises(RuntimeError, match="initialized outputs"):
        port.replay_provenance()
    display = make_prepared_trial().display
    port._display = display
    activations = []
    for output in display.active_outputs:
        port._outputs[output.output_id] = NS(
            activate=lambda name=output.output_id: activations.append(name),
            context=NS(
                info={
                    "GL_VENDOR": "NVIDIA",
                    "GL_RENDERER": "fixture-GPU",
                    "GL_VERSION": "4.6 driver-a",
                }
            ),
        )
    before = port.replay_provenance()
    assert activations == [output.output_id for output in display.active_outputs]
    assert sum(item.role == "gpu" for item in before) == len(display.active_outputs)
    first = port._outputs[display.active_outputs[0].output_id]
    first.context.info["GL_VERSION"] = "4.6 driver-b"
    assert port.replay_provenance() != before
    del first.context.info["GL_VERSION"]
    with pytest.raises(ValueError, match="missing graphics provenance GL_VERSION"):
        port.replay_provenance()


class _CaptureGL:
    """Host model of buffer/fence ownership and same-size nearest framebuffer blit."""

    GL_PIXEL_PACK_BUFFER = 1
    GL_READ_FRAMEBUFFER = 2
    GL_DRAW_FRAMEBUFFER = 3
    GL_COLOR_ATTACHMENT0 = 4
    GL_STREAM_READ = 5
    GL_UNSIGNED_BYTE = 6
    GL_UNSIGNED_INT_2_10_10_10_REV = 7
    GL_RGBA = 8
    GL_SYNC_GPU_COMMANDS_COMPLETE = 9
    GL_SCISSOR_TEST = 10
    GL_COLOR_BUFFER_BIT = 11
    GL_NEAREST = 12
    GL_ALREADY_SIGNALED = 13
    GL_CONDITION_SATISFIED = 14
    GL_WAIT_FAILED = 15
    GL_MAP_READ_BIT = 16

    def __init__(self, pixels, width, height):
        self.pixels, self.width, self.height = pixels, width, height
        self.buffers, self.syncs = {}, set()
        self.bound = 0
        self.serial = 0
        self.signaled = True
        self.scissor = True
        self.allocations = self.storage_allocations = self.blits = 0
        self.delete_syncs = []
        self.fail = None

    def glGenBuffers(self, _count):
        self.serial += 1
        self.allocations += 1
        return self.serial

    def glBindBuffer(self, _target, pbo):
        if pbo == 0 and self.fail == "unbind":
            self.fail = None
            raise RuntimeError("unbind failed")
        self.bound = pbo

    def glBufferData(self, _target, size, _data, _usage):
        import ctypes

        self.storage_allocations += 1
        self.buffers[self.bound] = (ctypes.c_ubyte * size)()

    def glBindFramebuffer(self, _target, _fbo):
        pass

    def glReadBuffer(self, _buffer):
        pass

    def glDrawBuffer(self, _buffer):
        pass

    def glIsEnabled(self, _state):
        return self.scissor

    def glDisable(self, _state):
        self.scissor = False

    def glEnable(self, _state):
        self.scissor = True

    def glBlitFramebuffer(self, *args):
        assert args == (
            0,
            0,
            self.width,
            self.height,
            0,
            self.height,
            self.width,
            0,
            self.GL_COLOR_BUFFER_BIT,
            self.GL_NEAREST,
        )
        assert not self.scissor
        if self.fail == "blit":
            raise RuntimeError("blit failed")
        stride = self.width * 4
        self.oriented = b"".join(
            self.pixels[n : n + stride]
            for n in range(len(self.pixels) - stride, -1, -stride)
        )
        self.blits += 1

    def glReadPixels(self, _x, _y, width, height, _format, _type, _offset):
        assert (width, height) == (self.width, self.height)
        self.buffers[self.bound][:] = self.oriented

    def glFenceSync(self, _condition, _flags):
        if self.fail == "fence":
            return None
        self.serial += 1
        self.syncs.add(self.serial)
        return self.serial

    def glFlush(self):
        pass

    def glClientWaitSync(self, sync, _flags, timeout):
        assert timeout == 0 and sync in self.syncs
        return self.GL_ALREADY_SIGNALED if self.signaled else 0

    def glMapBufferRange(self, _target, _offset, _size, _flags):
        import ctypes

        return ctypes.addressof(self.buffers[self.bound])

    def glUnmapBuffer(self, _target):
        return True

    def glDeleteSync(self, sync):
        assert sync in self.syncs
        self.syncs.remove(sync)
        self.delete_syncs.append(sync)

    def glDeleteBuffers(self, _count, pbos):
        if self.fail == "delete":
            raise RuntimeError("delete failed")
        for pbo in pbos:
            del self.buffers[pbo]


def _review_capture_fixture(monkeypatch, gl, pixel_format="rgba8_top_down"):
    from cephvr.visual_stimulus.rendering.capture import ReviewCapture

    monkeypatch.setitem(sys.modules, "OpenGL", NS(GL=gl))
    monkeypatch.setitem(sys.modules, "moderngl", NS(TRIANGLE_STRIP=1))
    released = []

    def resource(name, **kwargs):
        return NS(release=lambda: released.append(name), **kwargs)

    context = NS()
    capture = ReviewCapture()
    capture._context = context
    capture._dimensions = (gl.width, gl.height, pixel_format)
    capture._shared = [
        resource("texture"),
        resource("fbo", glo=10, use=lambda: None, clear=lambda *_: None),
        {"source_tex": NS(value=0)},
        resource("quad"),
        resource("array"),
        resource("flipped"),
        resource("readback", glo=11),
    ]

    # Program needs mapping and release like the actual ModernGL resource.
    class Program(dict):
        def release(self):
            released.append("program")

    capture._shared[2] = Program(source_tex=NS(value=0))
    encoding = NS(
        composite_width=gl.width,
        composite_height=gl.height,
        tiles=(),
        native_pixel_format=pixel_format,
    )
    outputs = (NS(output_id="one", texture_handle=NS(ctx=context)),)
    return capture, outputs, encoding, released


@pytest.mark.parametrize("height", [1, 3, 4])
@pytest.mark.parametrize("pixel_format", ["rgba8_top_down", "r10g10b10a2_le_top_down"])
def test_gpu_oriented_readback_matches_previous_cpu_input_and_reuses_storage(
    monkeypatch, height, pixel_format
):
    from cephvr.visual_stimulus.recording.capture import (
        CompositeFrame,
        _ffmpeg_input_order,
    )

    width = 3
    source = bytes((i * 37) % 256 for i in range(width * height * 4))
    gl = _CaptureGL(source, width, height)
    capture, outputs, encoding, released = _review_capture_fixture(
        monkeypatch, gl, pixel_format
    )
    old = CompositeFrame(
        0, 0, width, height, pixel_format.replace("top_down", "bottom_up"), source
    )
    expected = _ffmpeg_input_order(old).pixels
    first_pixels = None
    old_pending = None
    for _ in range(30):
        pending = capture.capture(outputs, encoding)
        assert pending is not old_pending
        pixels = capture.poll(pending)
        result = _ffmpeg_input_order(
            CompositeFrame(0, 0, width, height, pixel_format, pixels)
        )
        assert result.pixels == expected
        assert gl.scissor and gl.bound == 0
        if old_pending is not None:
            with pytest.raises(TypeError):
                capture.poll(old_pending)
        if first_pixels is None:
            first_pixels = bytes(pixels)
        else:
            assert pixels == first_pixels
        old_pending = pending
    assert gl.allocations == gl.storage_allocations == 1
    assert gl.blits == 30
    capture.release()
    assert not gl.buffers and not gl.syncs
    assert len(released) == 7
    capture.release()  # exact successful releases are not repeated
    assert len(released) == 7


def test_readback_pool_high_water_and_unsignaled_cancellation(monkeypatch):
    gl = _CaptureGL(b"RGBA", 1, 1)
    capture, outputs, encoding, _ = _review_capture_fixture(monkeypatch, gl)
    gl.signaled = False
    pending = [capture.capture(outputs, encoding) for _ in range(3)]
    assert all(capture.poll(p) is None for p in pending)
    assert not capture._available and gl.allocations == 3
    cancelled = pending.pop(0)
    assert capture.cancel(cancelled)
    assert not capture._available  # no unsignaled storage can return to the pool
    gl.signaled = True
    snapshots = [capture.poll(p) for p in reversed(pending)]
    gl.pixels = b"DIFF"
    for _ in range(30):
        more = [capture.capture(outputs, encoding) for _ in range(2)]
        for p in more:
            assert capture.poll(p) == b"DIFF"
    assert snapshots == [b"RGBA", b"RGBA"]
    assert gl.allocations == 3 and len(capture._available) == 2
    capture.release()
    assert not gl.buffers and not gl.syncs


@pytest.mark.parametrize("failure", ["blit", "fence"])
def test_capture_failure_restores_state_and_discards_buffer(monkeypatch, failure):
    gl = _CaptureGL(b"RGBA", 1, 1)
    capture, outputs, encoding, _ = _review_capture_fixture(monkeypatch, gl)
    gl.fail = failure
    with pytest.raises(RuntimeError):
        capture.capture(outputs, encoding)
    assert not capture._pending and not capture._available
    assert not gl.buffers and not gl.syncs
    assert gl.scissor and gl.bound == 0
    capture.release()


def test_capture_cleanup_retry_keeps_exact_buffer_and_does_not_redelete_sync(
    monkeypatch,
):
    gl = _CaptureGL(b"RGBA", 1, 1)
    capture, outputs, encoding, released = _review_capture_fixture(monkeypatch, gl)
    pending = capture.capture(outputs, encoding)
    sync = pending.sync
    gl.fail = "delete"
    with pytest.raises(RuntimeError, match="delete failed"):
        capture.cancel(pending)
    assert pending in capture._pending and pending.sync is None
    assert gl.delete_syncs == [sync] and not released
    gl.fail = None
    capture.release()
    assert gl.delete_syncs == [sync]
    assert not capture._pending and not gl.buffers
    assert len(released) == 7


@pytest.mark.parametrize("signaled", [False, True])
@pytest.mark.parametrize("delete_fails", [False, True])
def test_readback_unbind_failure_retains_cancellable_ownership(
    monkeypatch, signaled, delete_fails
):
    gl = _CaptureGL(b"RGBA", 1, 1)
    capture, outputs, encoding, released = _review_capture_fixture(monkeypatch, gl)
    pending = capture.capture(outputs, encoding)
    sync = pending.sync
    gl.signaled = signaled
    gl.fail = "unbind"
    with pytest.raises(RuntimeError, match="unbind failed"):
        capture.poll(pending)
    assert pending in capture._pending and pending.failed
    assert not capture._available
    with pytest.raises(RuntimeError, match="cleanup is required"):
        capture.poll(pending)
    if delete_fails:
        gl.fail = "delete"
        with pytest.raises(RuntimeError, match="delete failed"):
            capture.cancel(pending)
        assert pending in capture._pending and not capture._available
        gl.fail = None
    assert capture.cancel(pending)
    assert gl.delete_syncs == [sync]
    assert not gl.syncs and not gl.buffers and not capture._pending
    assert not capture._available
    # Failed storage is discarded; a subsequent capture allocates a fresh buffer.
    gl.signaled = True
    next_pending = capture.capture(outputs, encoding)
    assert capture.poll(next_pending) == b"RGBA"
    assert gl.allocations == 2
    capture.release()
    assert len(released) == 7 and not gl.buffers


def test_idle_readback_buffer_delete_failure_remains_owned_for_retry(monkeypatch):
    gl = _CaptureGL(b"RGBA", 1, 1)
    capture, outputs, encoding, released = _review_capture_fixture(monkeypatch, gl)
    pending = capture.capture(outputs, encoding)
    assert capture.poll(pending) == b"RGBA"
    gl.fail = "delete"
    with pytest.raises(RuntimeError, match="delete failed"):
        capture.release()
    assert len(capture._available) == 1 and not released
    gl.fail = None
    capture.release()
    assert not gl.buffers and not capture._available
    assert len(released) == 7


def test_partial_compositor_allocation_keeps_failed_resource_release_for_retry():
    from cephvr.visual_stimulus.rendering.capture import ReviewCapture

    release_fails = True
    released = []

    def release():
        if release_fails:
            raise RuntimeError("texture release failed")
        released.append("texture")

    def fail_framebuffer(**_kwargs):
        raise RuntimeError("framebuffer allocation failed")

    context = NS(
        texture=lambda *_args, **_kwargs: NS(release=release),
        framebuffer=fail_framebuffer,
    )
    capture = ReviewCapture()
    with pytest.raises(RuntimeError, match="framebuffer allocation failed"):
        capture._ensure_compositor(context, 2, 2, "rgba8_top_down")
    assert len(capture._shared) == 1
    with pytest.raises(RuntimeError, match="partial resources"):
        capture._ensure_compositor(context, 2, 2, "rgba8_top_down")
    release_fails = False
    capture.release()
    assert released == ["texture"] and not capture._shared
    assert capture._context is None and capture._dimensions is None


@pytest.mark.parametrize("activation_fails", [False, True])
def test_native_capture_cleanup_activates_owner_before_scene_release(
    tmp_path, activation_fails
):
    from cephvr.visual_stimulus.rendering.native import ModernGLPort, _OutputContext

    calls = []
    fail = activation_fails

    def activate_first():
        calls.append("first")
        if fail:
            raise RuntimeError("context activation failed")

    port = ModernGLPort(
        tmp_path,
        announce=lambda *_: None,
        scene_renderer=NS(release=lambda: calls.append("scene")),
    )
    port._glfw = NS(
        make_context_current=lambda _: None,
        destroy_window=lambda _: None,
        terminate=lambda: None,
    )
    for name, activate in (
        ("first", activate_first),
        ("last", lambda: calls.append("last")),
    ):
        port._outputs[name] = _OutputContext(
            name, object(), NS(release=lambda: None), 1, 1, 8, 1, None, activate
        )
    assert not port._capture_fences  # successful transfers already retired their fences
    result = port.release()
    if activation_fails:
        assert result.outstanding and calls == ["first"]
        assert port.scene_renderer is not None and len(port._outputs) == 2
        fail = False
        calls.clear()
        result = port.release()
    assert not result.outstanding
    assert calls[:2] == ["first", "scene"]
    assert port.scene_renderer is None and not port._outputs


@pytest.mark.parametrize("angle", [0, 48, 90, 173])
def test_physical_texture_coverage_preserves_tile_scale_and_anchor(angle):
    import math

    from cephvr.visual_stimulus.rendering.layer_projection import covering_texture
    from cephvr.visual_stimulus.rendering.types import InstanceSnapshot

    surface = NS(
        surface_id="bottom",
        bottom_left_mm=(0, 0, 0),
        bottom_right_mm=(160, 0, 0),
        top_left_mm=(0, 120, 0),
    )
    artifact = NS(display=NS(geometry=NS(surfaces=[surface])))
    mapping = NS(surface_id="bottom", matrix=((1, 0, 0), (0, 1, 0)))
    setting = NS(
        kind="texture",
        pattern=NS(kind="image_tile"),
        space=NS(kind="physical_surface", mappings=[mapping]),
    )
    values = dict(
        x=15.0,
        y=-9.0,
        rotation=float(angle),
        width=90.0,
        height=90.0,
        period_x=20.0,
        period_y=30.0,
        phase_x=0.2,
        phase_y=0.3,
    )
    snapshot = InstanceSnapshot("tile", "texture", True, tuple(values.items()), setting)
    result = dict(covering_texture(artifact, snapshot, "bottom").state)
    for axis, name in enumerate(("width", "height")):
        period = values["period_x" if axis == 0 else "period_y"]
        added_cycles = (result[name] - values[name]) / (2 * period)
        assert added_cycles == pytest.approx(round(added_cycles))
    for x in (-80, 80):
        for y in (-60, 60):
            dx, dy = x - values["x"], y - values["y"]
            a = math.radians(angle)
            assert (
                abs(dx * math.cos(a) + dy * math.sin(a)) <= result["width"] / 2 + 1e-8
            )
            assert (
                abs(-dx * math.sin(a) + dy * math.cos(a)) <= result["height"] / 2 + 1e-8
            )
    assert dict(snapshot.state) == values
    assert result["phase_x"] == values["phase_x"]
    assert result["period_y"] == values["period_y"]
    image = NS(kind="image")
    from dataclasses import replace

    unchanged = replace(snapshot, settings=image)
    assert covering_texture(artifact, unchanged, "bottom") is unchanged


def test_stimulus_preview_places_before_owner_can_show_and_preserves_manual_moves(
    monkeypatch,
):
    import cephvr.visual_stimulus.rendering.preview as module
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.platform.windows import preview_owner, window_coordinates

    monkeypatch.setattr(module.sys, "platform", "win32")
    events = []
    revision = [0]
    owner = NS(
        geometry=lambda: (410, 220, 400, 430),
        placement_revision=lambda: revision[0],
        sync=lambda: events.append("sync"),
        close=lambda: None,
    )

    def bind(*args):
        events.append("bind-show")
        return owner

    monkeypatch.setattr(preview_owner, "WindowsPreviewOwner", bind)
    monkeypatch.setattr(
        window_coordinates,
        "position_preview_frame",
        lambda title, x, y, **kw: events.append(("position", x, y)),
    )
    glfw = NS(
        set_window_size=lambda window, w, h: events.append(("size", w, h)),
        set_window_pos=lambda *args: pytest.fail(
            "Win32 placement must use the visible frame"
        ),
        set_window_should_close=lambda *args: None,
        show_window=lambda window: events.append("show"),
        hide_window=lambda window: events.append("hide"),
    )
    preview = module.StimulusPreview(glfw, NS(), lambda *args: None)
    preview.window, preview.context = object(), object()
    hint = rpc.PreviewWindowPlacement(
        x=410,
        y=220,
        side=400,
        gui_window_handle=1,
        gui_process_id=2,
        gui_process_creation_time_100ns=3,
    )
    preview.set_visible(True, hint)
    assert events[:4] == [
        ("size", 400, 400),
        ("position", 410, 220),
        "bind-show",
        "show",
    ]
    events.clear()
    revision[0] += 1
    hint.update_existing_only = True
    preview.set_visible(True, hint)
    assert not events
    hint.snap_to_grid = True
    preview.set_visible(True, hint)
    assert events[:3] == [("size", 400, 400), ("position", 410, 220), "show"]
    preview.set_visible(False, rpc.PreviewWindowPlacement())
    events.clear()
    hint.update_existing_only = hint.snap_to_grid = False
    preview.set_visible(True, hint)
    assert events[:3] == [("size", 400, 400), ("position", 410, 220), "show"]


def test_stimulus_native_close_hides_and_failed_release_retains_ownership(monkeypatch):
    import cephvr.visual_stimulus.rendering.preview as module
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.visual_stimulus.rendering.preview import StimulusPreview

    monkeypatch.setattr(module.sys, "platform", "test")
    events = []
    glfw = NS(
        hide_window=lambda w: events.append("hide"),
        show_window=lambda w: events.append("show"),
        window_should_close=lambda w: True,
        set_window_should_close=lambda *args: None,
        make_context_current=lambda w: None,
        destroy_window=lambda w: events.append("destroy"),
    )
    preview = StimulusPreview(glfw, NS(), lambda *state: events.append(state))
    preview.window = object()
    preview.context = NS(release=lambda: events.append("context"))
    preview.set_visible(True, rpc.PreviewWindowPlacement())
    preview.service()
    assert not preview.visible and events[-1] == (True, False, "")
    failures = [True]

    def release():
        if failures.pop():
            raise RuntimeError("retained resource")

    resource = NS(release=release)
    preview.resources.append(resource)
    with pytest.raises(RuntimeError, match="retained resource"):
        preview.release()
    assert preview.window is not None and preview.resources == [resource]
    failures.append(False)
    preview.release()
    assert preview.window is None and not preview.resources
    assert events[-1] == (False, False, "")


@pytest.mark.windows
def test_native_review_layouts_crop_only_preview_and_rotate_full_recording():
    moderngl = pytest.importorskip("moderngl")
    from cephvr.visual_stimulus.config.models.artifact_models import ReviewEncoding
    from cephvr.visual_stimulus.config.models.display_profile import PixelRect
    from cephvr.visual_stimulus.config.review_layout import (
        layout_from_crops,
        recording_layout,
    )
    from cephvr.visual_stimulus.rendering.capture import ReviewCapture
    from cephvr.visual_stimulus.rendering.types import RenderedOutput

    context = moderngl.create_standalone_context(require=430)
    capture = ReviewCapture()
    preview = ReviewCapture()
    sources = []
    try:
        ids = ("left", "front", "right", "bottom")
        display = NS(
            active_outputs=tuple(
                NS(output_id=i, rgb_bits_per_channel=8, width_px=64, height_px=64)
                for i in ids
            )
        )
        display.active_mappings = tuple(
            NS(
                output_id=i,
                mapping_id=i,
                surface_id=i,
                viewport=PixelRect(x=0, y=0, width=64, height=64),
            )
            for i in ids
        )
        crop = PixelRect(x=16, y=16, width=32, height=32)
        layout = layout_from_crops(display, tuple((i, i.title(), crop) for i in ids), 1)
        pixels = bytearray()
        for y in range(64):
            for x in range(64):
                pixels.extend(
                    (0, 255 if y >= 32 else 0, 255 if x >= 32 else 0, 255)
                    if 16 <= x < 48 and 16 <= y < 48
                    else (255, 0, 0, 255)
                )
        sources = [context.texture((64, 64), 4, bytes(pixels)) for _ in ids]
        outputs = tuple(
            RenderedOutput(i, 64, 64, 8, t) for i, t in zip(ids, sources, strict=True)
        )
        image = preview.compose(outputs, layout)
        assert not preview._labels and not capture._labels
        preview_bytes = image.read()
        width, height = image.size

        def pixel(x, y):
            offset = (y * width + x) * 4
            return preview_bytes[offset : offset + 3]

        for tile in layout.tiles:
            r = tile.rect
            for x in (8, 24):
                for y in (8, 24):
                    source_x = 31 - x if tile.label in {"Left", "Right"} else x
                    source_y = 31 - y if tile.label == "Bottom" else y
                    assert pixel(r.x + x, r.y + y) == bytes(
                        (0, 255 if source_y >= 16 else 0, 255 if source_x >= 16 else 0)
                    )
        assert bytes((255, 0, 0, 0)) not in [
            preview_bytes[i : i + 4] for i in range(0, len(preview_bytes), 4)
        ]
        layout = recording_layout(display)
        image = capture.compose(outputs, layout)
        assert not preview._labels and not capture._labels
        preview_bytes = image.read()
        width, height = image.size
        for tile in layout.tiles:
            assert tile.source_rect == PixelRect(x=0, y=0, width=64, height=64)
            assert pixel(tile.rect.x + 4, tile.rect.y + 4) == bytes((255, 0, 0))
        bottom = layout.tiles[-1].rect
        assert pixel(bottom.x + 24, bottom.y + 24) == bytes((0, 0, 255))
        assert pixel(bottom.x + 40, bottom.y + 24) == bytes((0, 255, 255))
        for tile in layout.tiles[:-1]:
            assert pixel(tile.rect.x + 24, tile.rect.y + 24) == bytes((0, 0, 0))
            assert pixel(tile.rect.x + 40, tile.rect.y + 40) == bytes((0, 255, 255))
        encoding = ReviewEncoding.model_construct(
            **layout.model_dump(), native_pixel_format="rgba8_top_down"
        )
        # model_construct does not deserialize nested tiles.
        encoding = encoding.model_copy(update={"tiles": layout.tiles})
        pending = capture.capture(outputs, encoding)
        context.finish()
        recorded = capture.poll(pending)
        row = width * 4
        expected = b"".join(
            preview_bytes[y * row : (y + 1) * row] for y in reversed(range(height))
        )
        assert recorded == expected
    finally:
        capture.release()
        preview.release()
        for texture in sources:
            texture.release()
        context.release()


@pytest.mark.parametrize("stop", ["complete", "cancel", "deadline"])
def test_setup_texture_progress_waits_for_gpu_completion(stop):
    import threading
    import time

    progress = []
    cache, budget, gpu, gate, loads, aliases = _resident_images(
        count=1, progress=lambda done, total: progress.append((done, total))
    )
    gpu.release_allowed = False
    budget.cancelled = threading.Event()
    deadline = [time.perf_counter_ns() + 2_000_000_000]
    cache.clock_ns = lambda: deadline[0] - 1
    polls = [0]
    original_service = cache.service

    def service(bound):
        original_service(bound)
        if cache.entries["image-0"].state == "uploading":
            polls[0] += 1
            assert progress[-1] == (0, 1)
            if polls[0] == 3:
                if stop == "complete":
                    gpu.release_allowed = True
                elif stop == "cancel":
                    budget.cancelled.set()
                else:
                    deadline[0] += 2

    cache.service = service
    try:
        if stop == "complete":
            cache.prepare(deadline[0])
            assert progress[-1] == (1, 1)
            assert cache.entries["image-0"].state == "resident"
            assert len(loads) == 1
        else:
            expected = InterruptedError if stop == "cancel" else TimeoutError
            with pytest.raises(expected):
                cache.prepare(deadline[0])
            assert (1, 1) not in progress
        assert polls[0] >= 3
    finally:
        gate.set()
        gpu.release_allowed = True
        assert cache.close(time.perf_counter_ns() + 2_000_000_000)
        assert cache.release_gpu() == ()


def test_stimulus_preview_pacing_skips_hidden_and_minimized(monkeypatch):
    from cephvr.visual_stimulus.rendering import preview as module

    now = [0]
    monkeypatch.setattr(module, "host_time_ns", lambda: now[0])
    viewer = module.StimulusPreview(NS(), NS(), lambda *args: None)
    assert not viewer.frame_due()
    viewer.visible = True
    assert viewer.frame_due()
    now[0] = 49_999_999
    assert not viewer.frame_due()
    now[0] = 50_000_000
    assert viewer.frame_due()
    viewer.owner = NS(minimized=True)
    now[0] = 100_000_000
    assert not viewer.frame_due()
    viewer.owner.minimized = False
    assert viewer.frame_due()
    assert not viewer.frame_due()
