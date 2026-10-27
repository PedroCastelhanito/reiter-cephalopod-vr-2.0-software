from __future__ import annotations

import hashlib
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from tests.visual_stimulus.support import (
    _geometric_profiles,
    glb_fixture,
    pack_glb,
    valid_display_json,
)

from cephvr.visual_stimulus.config.models.artifact_models import GeometricProfile
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    parse_display_json,
)
from cephvr.visual_stimulus.rendering.display_calibration import (
    DisplayCalibrationRenderer,
)
from cephvr.visual_stimulus.rendering.engine import RendererEngine
from cephvr.visual_stimulus.rendering.native import ModernGLPort, _OutputContext
from cephvr.visual_stimulus.rendering.types import (
    DisplayInitialization,
    OutputActivity,
    ResourceReleaseReport,
)
from cephvr.visual_stimulus.resources.arena import ArenaPreparation
from cephvr.visual_stimulus.resources.calibration import PreparedCalibration
from cephvr.visual_stimulus.resources.session import NativePreparation
from cephvr.visual_stimulus.v1 import messages_pb2


class _ProtectedFile:
    def __init__(self, path: Path, *, fail_close: bool = False) -> None:
        self.path = path
        self.fail_close = fail_close
        self.close_attempts = 0

    @contextmanager
    def independent_reader(self):
        with self.path.open("rb") as stream:
            yield stream

    def close_after_consumers(self) -> None:
        self.close_attempts += 1
        if self.fail_close:
            raise OSError("protected handle still has a consumer")


def _request(root: Path, arena: bytes) -> messages_pb2.OpenDisplayCalibrationCommand:
    profile_json = valid_display_json()
    request = messages_pb2.OpenDisplayCalibrationCommand(
        profile_json=profile_json,
        profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        asset_root=str(root),
        arena_relative_path="calibration/arena.glb",
        arena_size_bytes=len(arena),
        arena_sha256=hashlib.sha256(arena).hexdigest(),
    )
    request.policies.limits.max_document_bytes = 2_000_000
    request.policies.limits.max_asset_cpu_bytes = 2_000_000
    request.policies.limits.max_asset_gpu_bytes = 2_000_000
    return request


def _arena_bytes() -> bytes:
    document, binary = glb_fixture()
    return pack_glb(document, binary)


def test_native_preparation_supports_first_use_with_temporary_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.visual_stimulus.resources import display_calibration

    arena = _arena_bytes()
    target = tmp_path / "calibration" / "arena.glb"
    target.parent.mkdir()
    target.write_bytes(arena)
    protected: list[_ProtectedFile] = []

    def source_factory(path: Path) -> _ProtectedFile:
        source = _ProtectedFile(path)
        protected.append(source)
        return source

    monkeypatch.setattr(
        display_calibration,
        "prepare_calibration",
        lambda *_args, **_kwargs: PreparedCalibration(
            assets=(), resources=(), content={}
        ),
    )
    preparation = NativePreparation(
        _UnusedPort(),
        renderer_generation="renderer-generation",
        source_factory=source_factory,
    )
    accepted = parse_display_json(valid_display_json(), max_bytes=1_000_000)
    altered = json.loads(valid_display_json())
    altered["outputs"][0]["width_px"] = 120
    profile_json = json.dumps(altered)
    request = _request(tmp_path, arena)
    request.profile_json = profile_json
    request.profile_sha256 = hashlib.sha256(profile_json.encode()).hexdigest()
    accepted_calibration = PreparedCalibration(assets=(), resources=(), content={})
    preparation._display_profile = accepted
    preparation._display_calibration = accepted_calibration

    prepared = preparation.prepare_display_calibration(
        request, lambda *_args: None, time.perf_counter_ns() + 5_000_000_000
    )

    assert prepared.display != accepted
    assert prepared.previous_display == accepted
    assert prepared.previous_calibration is accepted_calibration
    assert prepared.arena.scene.nodes[0].primitives
    assert preparation.engine.display_matches(prepared.display) is False
    assert len(protected) == 1
    assert preparation.release_display_calibration(prepared)
    assert protected[0].close_attempts == 1
    assert preparation._protected_sources == []
    assert preparation._resource_keys == []


def test_calibration_after_display_cleanup_has_no_previous_renderer_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.visual_stimulus.resources import display_calibration
    from cephvr.visual_stimulus.resources import session as session_resources

    arena = _arena_bytes()
    target = tmp_path / "calibration" / "arena.glb"
    target.parent.mkdir()
    target.write_bytes(arena)
    monkeypatch.setattr(
        display_calibration,
        "prepare_calibration",
        lambda *_args, **_kwargs: PreparedCalibration(
            assets=(), resources=(), content={}
        ),
    )
    monkeypatch.setattr(
        session_resources,
        "prepare_calibration",
        lambda *_args, **_kwargs: PreparedCalibration(
            assets=(), resources=(), content={}
        ),
    )
    port = _RendererPort()
    preparation = NativePreparation(
        port,
        renderer_generation="renderer-generation",
        source_factory=_ProtectedFile,
    )
    display_request = messages_pb2.InitializeDisplay(asset_root=str(tmp_path))
    display_request.display.profile_json = valid_display_json()
    display_request.limits.max_document_bytes = 1_000_000
    display_request.limits.max_asset_cpu_bytes = 2_000_000
    display_request.limits.max_asset_gpu_bytes = 2_000_000
    display, initial_calibration = preparation.prepare_display(
        display_request, lambda *_args: None, time.perf_counter_ns() + 5_000_000_000
    )
    preparation.initialize_display(display, initial_calibration)

    retained_source = _ProtectedFile(target, fail_close=True)
    preparation._protected_sources.append(
        (retained_source, "visual_stimulus:display:calibration:front")
    )
    failed_cleanup = preparation.cleanup()
    assert failed_cleanup.outstanding
    assert preparation._display_profile is display
    assert preparation._display_calibration is initial_calibration
    assert preparation._display_budget is not None

    retained_source.fail_close = False
    assert not preparation.cleanup().outstanding
    preparation.engine.cleanup()

    request = _request(tmp_path, arena)
    prepared = preparation.prepare_display_calibration(
        request, lambda *_args: None, time.perf_counter_ns() + 5_000_000_000
    )
    has_previous_owner = (
        prepared.previous_display is None and prepared.previous_calibration is None
    )
    preparation.engine.present_display_calibration(prepared.display, prepared)
    activities, closed = preparation.engine.close_display_calibration(
        prepared.display, prepared
    )
    assert preparation.release_display_calibration(prepared)

    assert has_previous_owner and closed, (
        "confirmed display cleanup must retire both previous profile and calibration"
    )
    assert activities


@pytest.mark.parametrize("pattern", ["matching_bars", "wrong_pixel_length", "grid"])
def test_reference_file_controls_pixel_lengths_and_rejects_other_patterns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pattern: str
) -> None:
    from cephvr.gui.calibration_arena import make_reference_bars_glb
    from cephvr.visual_stimulus.resources import display_calibration

    raw = json.loads(valid_display_json())
    raw["calibration_view"] = "reference_bars"
    output = raw["outputs"][0]
    output["reference_bars"] = {"x_length_px": 50, "y_length_px": 30}
    arena = (
        _arena_bytes()
        if pattern == "grid"
        else make_reference_bars_glb(
            {
                output["output_id"]: (
                    100,
                    100,
                    51 if pattern == "wrong_pixel_length" else 50,
                    30,
                )
            }
        )
    )
    target = tmp_path / "calibration/reference_bars.glb"
    target.parent.mkdir()
    target.write_bytes(arena)
    request = _request(tmp_path, arena)
    request.arena_relative_path = "calibration/reference_bars.glb"
    request.profile_json = json.dumps(raw)
    request.profile_sha256 = hashlib.sha256(request.profile_json.encode()).hexdigest()
    sources: list[_ProtectedFile] = []

    def source_factory(path: Path) -> _ProtectedFile:
        source = _ProtectedFile(path)
        sources.append(source)
        return source

    monkeypatch.setattr(
        display_calibration,
        "prepare_calibration",
        lambda *_args, **_kwargs: PreparedCalibration(
            assets=(), resources=(), content={}
        ),
    )
    preparation = NativePreparation(
        _UnusedPort(),
        renderer_generation="renderer-generation",
        source_factory=source_factory,
    )
    deadline = time.perf_counter_ns() + 5_000_000_000
    if pattern != "matching_bars":
        with pytest.raises(ValueError, match="differs from the output pixel lengths"):
            preparation.prepare_display_calibration(
                request, lambda *_args: None, deadline
            )
        assert len(sources) == 1 and sources[0].close_attempts == 1
        return
    prepared = preparation.prepare_display_calibration(
        request, lambda *_args: None, deadline
    )
    primitive = prepared.arena.scene.nodes[0].primitives[0]
    assert len(primitive.positions) == 24
    horizontal, vertical = primitive.positions[16:20], primitive.positions[20:]
    assert max(p[0] for p in horizontal) - min(p[0] for p in horizontal) == 50
    assert max(p[1] for p in vertical) - min(p[1] for p in vertical) == 30
    assert preparation.release_display_calibration(prepared)
    assert sources[0].close_attempts == 1


def test_failed_protected_source_close_remains_owned_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.visual_stimulus.resources import display_calibration

    arena = _arena_bytes()
    target = tmp_path / "calibration" / "arena.glb"
    target.parent.mkdir()
    target.write_bytes(arena)
    protected: list[_ProtectedFile] = []

    def source_factory(path: Path) -> _ProtectedFile:
        source = _ProtectedFile(path, fail_close=True)
        protected.append(source)
        return source

    monkeypatch.setattr(
        display_calibration,
        "prepare_calibration",
        lambda *_args, **_kwargs: PreparedCalibration(
            assets=(), resources=(), content={}
        ),
    )
    preparation = NativePreparation(
        _UnusedPort(),
        renderer_generation="renderer-generation",
        source_factory=source_factory,
    )
    request = _request(tmp_path, arena)
    request.arena_sha256 = "0" * 64

    with pytest.raises(RuntimeError, match="protected inputs remain owned"):
        preparation.prepare_display_calibration(
            request, lambda *_args: None, time.perf_counter_ns() + 5_000_000_000
        )

    assert len(preparation._protected_sources) == 1
    report = preparation.cleanup()
    assert report.outstanding
    assert "protected-source:" in report.outstanding[0]
    assert preparation._protected_sources


class _UnusedPort:
    def service_display(self) -> bool:
        return False

    def poll_diagnostics(self):
        return ()

    @property
    def diagnostics_pending(self) -> bool:
        return False

    def release(self, deadline_ns: int | None = None) -> ResourceReleaseReport:
        return ResourceReleaseReport(())


class _RendererPort(_UnusedPort):
    def __init__(self) -> None:
        self.display: DisplayProfile | None = None
        self.events: list[object] = []

    def install_display_calibration(self, calibration: object) -> None:
        self.events.append(("install", calibration))

    def initialize_display(self, display: DisplayProfile) -> DisplayInitialization:
        self.display = display
        return _initialization(display)

    def present_display_calibration(self, display: object, prepared: object):
        self.events.append(("present", display, prepared))
        return _activities(display)

    def close_display_calibration(self, display: object, prepared: object):
        self.events.append(("close", display, prepared))
        return _activities(display), True


def _activities(display: object) -> tuple[OutputActivity, ...]:
    return tuple(
        OutputActivity(item.output_id, 10, 11, 1) for item in display.active_outputs
    )


def _initialization(display: DisplayProfile) -> DisplayInitialization:
    outputs = display.active_outputs
    return DisplayInitialization(
        output_ids=tuple(item.output_id for item in outputs),
        observed_rgb_bits=tuple(
            (
                item.output_id,
                item.rgb_bits_per_channel,
                item.rgb_bits_per_channel,
                item.rgb_bits_per_channel,
            )
            for item in outputs
        ),
        framebuffer_sizes=tuple(
            (item.output_id, item.width_px, item.height_px) for item in outputs
        ),
        requested_swap_intervals=tuple((item.output_id, 1) for item in outputs),
        idle_activity=_activities(display),
    )


def _prepared(
    display: DisplayProfile,
    *,
    previous: DisplayProfile | None = None,
    previous_calibration: PreparedCalibration | None = None,
):
    from cephvr.visual_stimulus.resources.arena import ArenaPreparation
    from cephvr.visual_stimulus.resources.assets import PreparedAssetSet
    from cephvr.visual_stimulus.resources.display_calibration import (
        PreparedDisplayCalibration,
    )

    return PreparedDisplayCalibration(
        display=display,
        display_calibration=PreparedCalibration(assets=(), resources=(), content={}),
        source=PreparedAssetSet(assets=(), cpu_bytes=0),
        arena=ArenaPreparation(scene=object(), sources=(), resources=(), textures={}),
        previous_display=previous,
        previous_calibration=previous_calibration,
    )


def test_renderer_calibration_first_use_closes_to_reconfigurable_idle() -> None:
    display = parse_display_json(valid_display_json(), max_bytes=1_000_000)
    port = _RendererPort()
    engine = RendererEngine(port, clock_ns=lambda: 10)
    prepared = _prepared(display)

    assert engine.present_display_calibration(display, prepared) == _activities(display)
    activities, closed = engine.close_display_calibration(display, prepared)

    assert closed
    assert activities == _activities(display)
    assert not engine.display_matches(display)
    assert [event[0] for event in port.events] == ["install", "present", "close"]


def test_renderer_restores_previous_profile_after_temporary_calibration() -> None:
    original = parse_display_json(valid_display_json(), max_bytes=1_000_000)
    changed = json.loads(valid_display_json())
    changed["outputs"][0]["width_px"] = 120
    temporary = parse_display_json(json.dumps(changed), max_bytes=1_000_000)
    port = _RendererPort()
    engine = RendererEngine(port, clock_ns=lambda: 10)
    previous_calibration = PreparedCalibration(assets=(), resources=(), content={})
    engine.replace_display(original, previous_calibration)
    prepared = _prepared(
        temporary, previous=original, previous_calibration=previous_calibration
    )

    engine.present_display_calibration(temporary, prepared)
    _, closed = engine.close_display_calibration(temporary, prepared)

    assert closed
    assert engine.display_matches(original)
    assert [event[0] for event in port.events] == [
        "install",
        "install",
        "present",
        "close",
        "install",
    ]


class _GLResource:
    def __init__(self, gl: _FakeGL, context_id: str, label: str) -> None:
        self.gl = gl
        self.context_id = context_id
        self.label = label
        self.size = (100, 100)
        self.glo = len(gl.resources) + 1
        self.released = False
        self.release_failures_remaining = 0
        gl.resources.append(self)

    def release(self) -> None:
        assert self.gl.current_context == self.context_id
        if self.release_failures_remaining:
            self.release_failures_remaining -= 1
            raise RuntimeError("deferred GL resource release")
        self.released = True
        self.gl.events.append(("release", self.context_id, self.label))

    def use(self, _unit: int = 0) -> None:
        assert self.gl.current_context == self.context_id

    def write(self, _data: bytes) -> None:
        assert self.gl.current_context == self.context_id
        self.last_write = _data


class _Uniform:
    def __init__(self) -> None:
        self.value = None

    def write(self, _data: bytes) -> None:
        pass


class _GLProgram(_GLResource):
    def __init__(self, gl: _FakeGL, context_id: str, role: str) -> None:
        super().__init__(gl, context_id, role)
        self.role = role
        self.uniforms: dict[str, _Uniform] = {}

    def __getitem__(self, name: str) -> _Uniform:
        return self.uniforms.setdefault(name, _Uniform())


class _GLFramebuffer(_GLResource):
    def use(self) -> None:
        super().use()
        self.gl.current_framebuffer = self.label
        self.gl.events.append(("framebuffer", self.context_id, self.label))

    def clear(self, *_args, **_kwargs) -> None:
        assert self.gl.current_context == self.context_id
        if "viewport" in _kwargs:
            self.gl.events.append(("mask", self.context_id, _args, _kwargs["viewport"]))


class _GLVertexArray(_GLResource):
    def __init__(self, gl: _FakeGL, context_id: str, role: str, label: str) -> None:
        super().__init__(gl, context_id, label)
        self.role = role

    def render(self, **_kwargs) -> None:
        assert self.gl.current_context == self.context_id
        self.gl.events.append(
            ("draw", self.context_id, self.role, self.gl.current_framebuffer)
        )


class _FakeContext:
    def __init__(self, gl: _FakeGL, context_id: str) -> None:
        self.gl = gl
        self.context_id = context_id
        self.screen = _GLFramebuffer(gl, context_id, "screen")
        self.viewport = None
        self.scissor = None

    def _assert_current(self) -> None:
        assert self.gl.current_context == self.context_id

    def program(self, *, vertex_shader: str, fragment_shader: str):
        self._assert_current()
        if "view_projection" in vertex_shader:
            role = "arena"
        elif "weight_tex" in fragment_shader:
            role = "warp"
        else:
            role = "output"
        return _GLProgram(self.gl, self.context_id, role)

    def vertex_array(self, program, *_args, **_kwargs):
        self._assert_current()
        return _GLVertexArray(
            self.gl, self.context_id, program.role, f"vao:{program.role}"
        )

    def buffer(self, *_args, **_kwargs):
        self._assert_current()
        return _GLResource(self.gl, self.context_id, "buffer")

    def texture(self, size, *_args, **_kwargs):
        self._assert_current()
        texture = _GLResource(self.gl, self.context_id, "texture")
        texture.size = size
        return texture

    def depth_renderbuffer(self, _size):
        self._assert_current()
        return _GLResource(self.gl, self.context_id, "depth")

    def framebuffer(self, *_args, **kwargs):
        self._assert_current()
        label = f"fbo:{self.context_id}:{len(self.gl.resources)}"
        return _GLFramebuffer(self.gl, self.context_id, label)

    def enable(self, _flag: int) -> None:
        self._assert_current()

    def disable(self, _flag: int) -> None:
        self._assert_current()

    def clear(self, *_args, **_kwargs) -> None:
        self._assert_current()
        if "viewport" in _kwargs:
            self.gl.events.append(("bar", self.context_id, _args, _kwargs["viewport"]))

    def copy_framebuffer(self, _destination, _source) -> None:
        self._assert_current()
        self.gl.events.append(("copy", self.context_id, self.gl.current_framebuffer))


class _FakeGL:
    def __init__(self) -> None:
        self.current_context: str | None = None
        self.current_framebuffer = "default"
        self.resources: list[_GLResource] = []
        self.events: list[tuple[object, ...]] = []


class _FakeGLFW:
    def __init__(self, gl: _FakeGL) -> None:
        self.gl = gl

    def make_context_current(self, window: str) -> None:
        self.gl.current_context = window

    def swap_buffers(self, window: str) -> None:
        self.gl.events.append(("swap", window))

    def terminate(self) -> None:
        self.gl.events.append(("terminate",))


def _two_output_display() -> DisplayProfile:
    raw = json.loads(valid_display_json())
    second = dict(raw["outputs"][0])
    second.update(output_id="projector/second", device_identity="edid:two")
    raw["outputs"].append(second)
    for mapping in tuple(raw["mappings"]):
        duplicate = dict(mapping)
        duplicate["mapping_id"] = mapping["mapping_id"] + "-second"
        duplicate["output_id"] = "projector/second"
        duplicate["geometric_profile"] = {
            "logical_path": "geometry-second/" + mapping["surface_id"] + ".json"
        }
        raw["mappings"].append(duplicate)
    return parse_display_json(json.dumps(raw), max_bytes=1_000_000)


def _native_calibration_inputs(gl: _FakeGL, display: DisplayProfile | None = None):
    display = display or _two_output_display()
    outputs = {}
    for output in display.active_outputs:
        context_id = output.output_id
        context = _FakeContext(gl, context_id)

        def activate(selected: str = context_id) -> None:
            gl.current_context = selected

        outputs[context_id] = SimpleNamespace(
            context=context,
            width=output.width_px,
            height=output.height_px,
            bits=output.rgb_bits_per_channel,
            activate=activate,
        )
    from cephvr.visual_stimulus.resources.glb import parse_glb

    document, binary = glb_fixture()
    scene = parse_glb(pack_glb(document, binary), max_bytes=1_000_000, max_elements=100)
    prepared = _prepared(display)
    prepared.arena = ArenaPreparation(
        scene=scene, sources=(), resources=(), textures={}
    )
    prepared.display_calibration = PreparedCalibration(
        assets=(), resources=(), content=_geometric_profiles(display)
    )
    return display, prepared, outputs


def _install_fake_gl_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    opengl = ModuleType("OpenGL")
    opengl.GL = SimpleNamespace(
        GL_SHADER_STORAGE_BUFFER=1,
        glBindBufferBase=lambda *_args: None,
    )
    monkeypatch.setitem(sys.modules, "OpenGL", opengl)


def test_replacing_display_preserves_only_unreused_native_release_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    from cephvr.visual_stimulus.rendering import native as native_module

    gl = _FakeGL()
    original = _two_output_display()
    raw_temporary = original.model_dump(mode="json")
    raw_temporary["outputs"][0]["width_px"] += 8
    temporary = parse_display_json(json.dumps(raw_temporary), max_bytes=1_000_000)
    outputs_by_id = {
        item.output_id: SimpleNamespace(
            context=_FakeContext(gl, item.output_id),
            width=item.width_px,
            height=item.height_px,
            bits=item.rgb_bits_per_channel,
            activate=lambda: None,
        )
        for item in temporary.active_outputs
    }
    registrations: list[tuple[str, str | None]] = []
    port = ModernGLPort(
        Path("."), announce=lambda key, path: registrations.append((key, path))
    )
    port._owner = threading.get_ident()
    port._glfw = _FakeGLFW(gl)
    port._glfw.destroy_window = lambda _window: None
    port._glfw.swap_interval = lambda _interval: None
    port._glfw.create_window = lambda _w, _h, title, _monitor, _share: title
    port._moderngl = SimpleNamespace(DEPTH_TEST=1, BLEND=2)
    port._display = temporary
    port._display_calibration = None
    port._outputs = {
        output_id: _OutputContext(
            output_id,
            output_id,
            item.context,
            item.width,
            item.height,
            item.bits,
            1,
            item.context.screen,
            item.activate,
        )
        for output_id, item in outputs_by_id.items()
    }
    port._window_obligations = set(outputs_by_id)
    port._orphan_windows = {}
    port._calibration_owner = SimpleNamespace(release=lambda: ())
    port.preview = None
    unrelated_key = "visual_stimulus:gpu:previous-session-resource"
    port._released = [unrelated_key]
    port.clock_ns = lambda: 10
    port._idle_device_color = lambda *_args: (0.0, 0.0, 0.0)
    port._release_partial = lambda _created: port._outputs.clear() or []

    def glfw_factory() -> _FakeGLFW:
        return _FakeGLFW(gl)

    def install_fake_graphics() -> None:
        port._glfw = glfw_factory()
        port._glfw.destroy_window = lambda _window: None
        port._glfw.swap_interval = lambda _interval: None
        port._glfw.create_window = lambda _w, _h, title, _monitor, _share: title
        port._moderngl = SimpleNamespace(DEPTH_TEST=1, BLEND=2)

    port._load_graphics = install_fake_graphics
    monkeypatch.setattr(
        native_module,
        "resolve_output_monitors",
        lambda display, _glfw, _resolver: [
            (output, object()) for output in display.active_outputs
        ],
    )
    monkeypatch.setattr(native_module, "configure_window", lambda *_args: None)
    monkeypatch.setattr(native_module, "hide_output_shell_entry", lambda *_args: None)
    contexts = iter(
        _FakeContext(gl, item.output_id) for item in original.active_outputs
    )
    monkeypatch.setattr(
        native_module, "attach_window_context", lambda _gl: next(contexts)
    )
    monkeypatch.setattr(native_module, "verify_framebuffer", lambda *_args: None)
    monkeypatch.setattr(native_module, "clear_valid_background", lambda *_args: None)

    engine = RendererEngine(port, clock_ns=lambda: 10)
    engine._display = temporary
    engine._display_observation = _initialization(temporary)
    prepared = _prepared(
        temporary,
        previous=original,
        previous_calibration=PreparedCalibration(assets=(), resources=(), content={}),
    )
    activities, closed = engine.close_display_calibration(temporary, prepared)

    assert closed and activities
    arena_key = "visual_stimulus:gpu:display-calibration:arena"
    assert arena_key in port._released
    assert unrelated_key in port._released
    assert {key for key, _path in registrations} == {
        f"visual_stimulus:window:{item.output_id}" for item in original.active_outputs
    }

    class FailedCalibrationOwner:
        def __init__(self, _outputs, _moderngl, announce, _upload):
            self.announce = announce

        def present(self, _display, _prepared):
            self.announce(arena_key, None)
            raise RuntimeError("arena upload failed")

        def release(self):
            return ("display-calibration arena release remains unconfirmed",)

    from cephvr.visual_stimulus.rendering import display_calibration

    monkeypatch.setattr(
        display_calibration, "DisplayCalibrationRenderer", FailedCalibrationOwner
    )
    with pytest.raises(RuntimeError, match="arena upload failed"):
        port.present_display_calibration(original, _prepared(original))
    failed_release = port.release()
    assert arena_key not in failed_release.released
    assert any(
        "arena release remains unconfirmed" in item
        for item in failed_release.outstanding
    )


@pytest.mark.parametrize("quarter_turn", [False, True])
@pytest.mark.parametrize("configured_bars", [False, True])
@pytest.mark.parametrize("calibration_view", ["reference_bars", "frame_grid"])
def test_native_calibration_owner_uses_surface_warp_and_output_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    configured_bars: bool,
    calibration_view: str,
    quarter_turn: bool,
) -> None:
    _install_fake_gl_binding(monkeypatch)
    gl = _FakeGL()
    moderngl = SimpleNamespace(
        DEPTH_TEST=1,
        CULL_FACE=2,
        BLEND=4,
        ONE=1,
        TRIANGLES=5,
        TRIANGLE_STRIP=6,
    )
    display = _two_output_display().model_copy(
        update={"calibration_view": calibration_view}
    )
    masked = display.model_dump(mode="json")
    for output in masked["outputs"]:
        output["blackout_zones"] = [dict(x=5, y=6, width=4, height=4)]
    display = parse_display_json(json.dumps(masked), max_bytes=1_000_000)
    if configured_bars:
        raw = display.model_dump(mode="json")
        for output in raw["outputs"]:
            output["reference_bars"] = dict(
                x_length_px=max(1, output["width_px"] // 3),
                y_length_px=max(1, output["height_px"] // 5),
            )
        display = parse_display_json(json.dumps(raw), max_bytes=1_000_000)
        raw["outputs"][0]["reference_bars"]["x_length_px"] = (
            raw["outputs"][0]["width_px"] + 1
        )
        with pytest.raises(ValueError, match="exceed"):
            parse_display_json(json.dumps(raw), max_bytes=1_000_000)
    display, prepared, outputs = _native_calibration_inputs(gl, display)
    if quarter_turn:
        for key, profile in prepared.display_calibration.content.items():
            prepared.display_calibration.content[key] = profile.model_copy(
                update={
                    "vertices": tuple(
                        v.model_copy(update={"uv": (v.uv[1], 1 - v.uv[0])})
                        for v in profile.vertices
                    )
                }
            )
    owner = DisplayCalibrationRenderer(
        outputs,
        moderngl,
        lambda *_args: None,
        lambda *_args, **_kwargs: None,
    )

    owner.present(display, prepared)

    draws = [event for event in gl.events if event[0] == "draw"]
    masks = [event for event in gl.events if event[0] == "mask"]
    assert len(masks) == (0 if calibration_view == "reference_bars" else len(outputs))
    for mask in masks:
        assert mask[2:] == ((0.0, 0.0, 0.0), (5, 6, 4, 4))
        output_draw = next(e for e in draws if e[1:3] == (mask[1], "output"))
        assert gl.events.index(mask) < gl.events.index(output_draw)
    copies = [event for event in gl.events if event[0] == "copy"]
    assert {event[1] for event in copies} == set(outputs)
    for output_id in outputs:
        copy = next(event for event in copies if event[1] == output_id)
        if calibration_view == "reference_bars":
            bars = [event for event in gl.events if event[:2] == ("bar", output_id)]
            assert bars and all(
                gl.events.index(bar) < gl.events.index(copy) for bar in bars
            )
            frame_rects = [bar[3] for bar in bars if bar[2] == (1.0, 1.0, 1.0)]
            assert len(frame_rects) == 4
            assert len(bars) == 8

    assert all(output.context.scissor is None for output in outputs.values())
    if configured_bars and calibration_view == "reference_bars":
        for output_id in outputs:
            bars = [event for event in gl.events if event[:2] == ("bar", output_id)]
            configured = next(
                o for o in display.active_outputs if o.output_id == output_id
            ).reference_bars
            assert configured is not None
            assert bars[-2][3][2] == configured.x_length_px
            assert bars[-1][3][3] == configured.y_length_px
    assert {event[2] for event in draws} == (
        set() if calibration_view == "reference_bars" else {"arena", "warp", "output"}
    )
    assert bool([e for e in gl.events if e[0] == "bar"]) == (
        calibration_view == "reference_bars"
    )
    for output_id in () if calibration_view == "reference_bars" else outputs:
        output_draws = [event for event in draws if event[1] == output_id]
        assert any(event[2] == "arena" and "fbo:" in event[3] for event in output_draws)
        assert any(event[2] == "warp" and "fbo:" in event[3] for event in output_draws)
        assert any(
            event[2] == "output" and "fbo:" in event[3] for event in output_draws
        )
    assert {
        resource.context_id
        for resource in gl.resources
        if resource.label.startswith("vao:")
    } == set(outputs)

    if calibration_view == "frame_grid":
        for frame in owner.frames.values():
            assert frame.arena_drawer.program["calibration_plane_active"].value == 1
            assert len(frame.arena_drawer.program["calibration_plane"].value) == 4
        allocation_count = len(gl.resources)
        owner.update(
            {
                m.mapping_id: ((0.1, 0.2), (0.8, 0.2), (0.1, 0.9), (0.8, 0.9))
                for m in display.active_mappings[:4]
            }
        )
        owner.present(display, prepared)
        assert len(gl.resources) == allocation_count
        for mapping in display.active_mappings[:4]:
            assert owner.valid_areas[mapping.mapping_id] == (0.1, 0.2, 0.8, 0.9)
            import struct

            data = (
                owner.frames[mapping.output_id]
                .warp_vertex_buffers[mapping.mapping_id]
                .last_write
            )
            words = struct.unpack("16f", data)
            du = -(words[5] - words[1]) if quarter_turn else words[4] - words[0]
            dv = words[8] - words[0] if quarter_turn else words[9] - words[1]
            assert (words[6] - words[2]) / 2 / du == pytest.approx(1)
            assert (words[11] - words[3]) / 2 / dv == pytest.approx(1)
            assert owner.frames[mapping.output_id].warp_program["valid_area"].value == (
                0.1,
                0.2,
                0.8,
                0.9,
            )
        first_mapping = display.active_mappings[0]
        last_valid = dict(owner.valid_areas)
        with pytest.raises(ValueError, match="unknown"):
            owner.update(
                {
                    first_mapping.mapping_id: (
                        (0.2, 0.2),
                        (0.8, 0.2),
                        (0.2, 0.8),
                        (0.8, 0.8),
                    ),
                    "unknown": ((0, 0), (1, 0), (0, 1), (1, 1)),
                }
            )
        assert owner.valid_areas == last_valid
        with pytest.raises(ValueError, match="one output pixel"):
            owner.update(
                {
                    first_mapping.mapping_id: (
                        (0.1, 0.1),
                        (0.100000000001, 0.1),
                        (0.1, 0.9),
                        (0.100000000001, 0.9),
                    )
                }
            )
        assert owner.valid_areas == last_valid
        with pytest.raises(ValueError, match="unknown"):
            owner.update({"unknown": ((0, 0), (1, 0), (0, 1), (1, 1))})
        with pytest.raises(ValueError):
            owner.update(
                {
                    display.active_mappings[0].mapping_id: (
                        (-1, 0),
                        (1, 0),
                        (-1, 1),
                        (1, 1),
                    )
                }
            )
        assert len(gl.resources) == allocation_count
    else:
        with pytest.raises(ValueError, match="frame/grid"):
            owner.update({})

    assert owner.release() == ()
    assert all(
        resource.released for resource in gl.resources if resource.label != "screen"
    )


def test_native_calibration_owner_can_prepare_again_after_confirmed_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_gl_binding(monkeypatch)
    gl = _FakeGL()
    moderngl = SimpleNamespace(
        DEPTH_TEST=1,
        CULL_FACE=2,
        BLEND=4,
        ONE=1,
        TRIANGLES=5,
        TRIANGLE_STRIP=6,
    )
    display, prepared, outputs = _native_calibration_inputs(gl)
    owner = DisplayCalibrationRenderer(
        outputs,
        moderngl,
        lambda *_args: None,
        lambda *_args, **_kwargs: None,
    )

    owner.present(display, prepared)
    assert owner.release() == ()


def test_native_calibration_owner_retains_failed_context_resource_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_gl_binding(monkeypatch)
    gl = _FakeGL()
    moderngl = SimpleNamespace(
        DEPTH_TEST=1,
        CULL_FACE=2,
        BLEND=4,
        ONE=1,
        TRIANGLES=5,
        TRIANGLE_STRIP=6,
    )
    display, prepared, outputs = _native_calibration_inputs(gl)
    owner = DisplayCalibrationRenderer(
        outputs,
        moderngl,
        lambda *_args: None,
        lambda *_args, **_kwargs: None,
    )
    owner.present(display, prepared)
    failed_drawer_vao = next(
        resource
        for resource in gl.resources
        if resource.label == "vao:arena" and resource.context_id == "projector/main"
    )
    failed_drawer_vao.release_failures_remaining = 1

    failures = owner.release()

    assert failures
    assert not failed_drawer_vao.released
    assert "projector/main" in owner.frames
    assert owner.release() == ()
    assert failed_drawer_vao.released
    owner.present(display, prepared)

    assert sum(event[0] == "draw" for event in gl.events) > 0
    assert owner.release() == ()


@pytest.mark.parametrize("mode", ["landmarks", "every_frame"])
@pytest.mark.parametrize("view", ["frame_grid", "photodiode_placement"])
def test_native_port_releases_owner_and_accepts_a_later_calibration(
    monkeypatch: pytest.MonkeyPatch,
    view: str,
    mode: str,
) -> None:
    _install_fake_gl_binding(monkeypatch)
    gl = _FakeGL()
    moderngl = SimpleNamespace(
        DEPTH_TEST=1,
        CULL_FACE=2,
        BLEND=4,
        ONE=1,
        TRIANGLES=5,
        TRIANGLE_STRIP=6,
    )
    display, prepared, outputs = _native_calibration_inputs(gl)
    if view == "photodiode_placement":
        display = display.model_copy(
            update={"calibration_view": view, "photodiode_mode": mode}
        )
        prepared.display = display
    port = ModernGLPort.__new__(ModernGLPort)
    port._owner = __import__("threading").get_ident()
    port._display = display
    port._display_calibration = prepared.display_calibration
    port._moderngl = moderngl
    port._outputs = {
        output_id: _OutputContext(
            output_id,
            output_id,
            output.context,
            output.width,
            output.height,
            8,
            1,
            output.context.screen,
            output.activate,
        )
        for output_id, output in outputs.items()
    }
    port._calibration_owner = None
    port._resources = {}
    port._glfw = _FakeGLFW(gl)
    port._capture_fences = []
    port.scene_renderer = None
    port._scene_keys = set()
    port.preview = None
    port._orphan_windows = {}
    port._window_obligations = set()
    port._released = []
    port._announce = lambda *_args: None
    ticks = iter(range(10, 10000))
    port.clock_ns = lambda: next(ticks)

    for index in range(2):
        activities = port.present_display_calibration(display, prepared)
        assert {item.output_id for item in activities} == set(outputs)
        assert port._calibration_owner.photodiode_index == 1
        if view == "photodiode_placement":
            from cephvr.visual_stimulus.rendering.photodiode import photodiode_level

            for submission in range(1, 65):
                gl.events.clear()
                if submission == 3:
                    from cephvr.visual_stimulus.config.calibration_placement import (
                        CalibrationPlacement,
                    )

                    payload = port._calibration_owner.placement.model_dump(mode="json")
                    payload["photodiode_patch"]["rect"] = dict(
                        x=2, y=3, width=6, height=7
                    )
                    port.update_display_calibration(
                        display,
                        prepared,
                        CalibrationPlacement.model_validate_json(json.dumps(payload)),
                    )
                else:
                    port.present_display_calibration(display, prepared)
                assert port._calibration_owner.photodiode_index == submission + 1
                white = [
                    e
                    for e in gl.events
                    if e[0] == "mask" and e[2] == (1.0, 1.0, 1.0, 1.0)
                ]
                assert bool(white) == photodiode_level(submission, mode)
                if submission >= 3:
                    pulse = [
                        e for e in gl.events if e[0] == "mask" and e[3] == (2, 3, 6, 7)
                    ]
                    assert len(pulse) == 1
                    level = float(photodiode_level(submission, mode))
                    assert pulse[0][2] == (level, level, level, 1.0)
        if view == "photodiode_placement":

            def fail_swap(_window):
                raise RuntimeError("swap failed")

            previous_swap = port._glfw.swap_buffers
            port._glfw.swap_buffers = fail_swap
            failed = port.present_display_calibration(display, prepared)
            assert all(item.error for item in failed)
            assert port._calibration_owner.photodiode_index == 65
            port._glfw.swap_buffers = previous_swap
        if index == 0:
            next(
                resource
                for resource in gl.resources
                if resource.label == "vao:arena"
                and resource.context_id == "projector/main"
            ).release_failures_remaining = 1
        _, released = port.close_display_calibration(display, prepared)
        if index == 0:
            assert not released
            assert port._calibration_owner is not None
            _, released = port.close_display_calibration(display, prepared)
        assert released
        assert port._calibration_owner is None

    assert port._released.count("visual_stimulus:gpu:display-calibration:arena") == 1


def test_native_generic_release_clears_calibration_owner_before_reinitialize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_gl_binding(monkeypatch)
    gl = _FakeGL()
    moderngl = SimpleNamespace(
        DEPTH_TEST=1,
        CULL_FACE=2,
        BLEND=4,
        ONE=1,
        TRIANGLES=5,
        TRIANGLE_STRIP=6,
    )
    display, prepared, outputs = _native_calibration_inputs(gl)
    port = ModernGLPort.__new__(ModernGLPort)
    port._owner = __import__("threading").get_ident()
    port._display = display
    port._display_calibration = prepared.display_calibration
    port._moderngl = moderngl
    port._outputs = {
        output_id: _OutputContext(
            output_id,
            output_id,
            output.context,
            output.width,
            output.height,
            8,
            1,
            output.context.screen,
            output.activate,
        )
        for output_id, output in outputs.items()
    }
    port._calibration_owner = None
    port._resources = {}
    port._glfw = _FakeGLFW(gl)
    port._capture_fences = []
    port.scene_renderer = None
    port._scene_keys = set()
    port.preview = None
    port._orphan_windows = {}
    port._window_obligations = set()
    port._released = []
    port._announce = lambda *_args: None
    ticks = iter(range(10, 10000))
    port.clock_ns = lambda: next(ticks)
    port._release_partial = lambda _created: port._outputs.clear() or []

    port.present_display_calibration(display, prepared)
    report = port.release()

    assert not report.outstanding
    assert port._calibration_owner is None
    assert port._display is None

    # Reinitialize the same native owner with its newly opened output contexts.
    port._moderngl = moderngl
    port._glfw = _FakeGLFW(gl)
    port._outputs = {
        output_id: _OutputContext(
            output_id,
            output_id,
            output.context,
            output.width,
            output.height,
            8,
            1,
            output.context.screen,
            output.activate,
        )
        for output_id, output in outputs.items()
    }
    port._display = display
    port._display_calibration = prepared.display_calibration
    port._release_partial = lambda _created: port._outputs.clear() or []

    activities = port.present_display_calibration(display, prepared)

    assert {item.output_id for item in activities} == set(outputs)
    assert port._calibration_owner is not None
    assert not port.release().outstanding


def test_cleanup_receipts_cover_all_announced_cpu_sources_only_after_close(
    tmp_path: Path,
) -> None:
    preparation = NativePreparation(
        _UnusedPort(), renderer_generation="renderer", source_factory=_ProtectedFile
    )
    target = tmp_path / "calibration.json"
    target.write_text("{}")
    announce = preparation._registered_announce(
        lambda *_args: None, "visual_stimulus:display"
    )
    announce("calibration:profile", str(target))
    source = preparation.source_factory(target)
    source.fail_close = True
    failed = preparation.cleanup()
    assert (
        failed.outstanding
        and "visual_stimulus:display:calibration:profile" not in failed.released
    )
    source.fail_close = False
    closed = preparation.cleanup()
    assert not closed.outstanding
    assert "visual_stimulus:display:calibration:profile" in closed.released
    assert not preparation._protected_sources and not preparation._resource_keys
    assert preparation.cleanup().released == closed.released
    # Reopening the same logical input invalidates its prior close receipt.
    announce("calibration:profile", str(target))
    source = preparation.source_factory(target)
    source.fail_close = True
    assert (
        "visual_stimulus:display:calibration:profile"
        not in preparation.cleanup().released
    )


@pytest.mark.parametrize("quarter_turn", [False, True])
def test_prepared_affine_view_raster_matches_valid_pixels_and_preserves_imported_targets(
    quarter_turn,
):
    from cephvr.visual_stimulus.rendering.scene_resources import SceneOutputBuilder

    gl = _FakeGL()
    display, prepared, outputs = _native_calibration_inputs(gl)
    content = {}
    for index, mapping in enumerate(display.active_mappings):
        profile = prepared.display_calibration.content[mapping.mapping_id]
        assert isinstance(profile, GeometricProfile)
        content[mapping.mapping_id] = profile.model_copy(
            update={
                "calibration_id": "reference_valid"
                if index == 0
                else "imported_optical",
                "valid_area": (0.25, 0.25, 0.75, 0.75),
                "vertices": tuple(
                    v.model_copy(update={"uv": (v.uv[1], 1 - v.uv[0])})
                    for v in profile.vertices
                )
                if quarter_turn
                else profile.vertices,
            }
        )
    artifact = SimpleNamespace(
        identity=SimpleNamespace(
            trial_id="valid-raster", resource_generation="generation"
        ),
        manifest=SimpleNamespace(resources=()),
        display=display,
        epochs=(),
    )
    builder = SceneOutputBuilder()
    frames = {}
    builder.prepare_trial(
        artifact, SimpleNamespace(prepared_content=content), outputs, {}, frames
    )
    for index, mapping in enumerate(display.active_mappings):
        target = frames[mapping.output_id].surface_textures[mapping.mapping_id]
        expected = (
            (mapping.viewport.width // 2, mapping.viewport.height // 2)
            if index == 0
            else (mapping.viewport.width, mapping.viewport.height)
        )
        if index == 0 and quarter_turn:
            expected = expected[::-1]
        assert target.size == expected
    for frame in frames.values():
        frame.activate()
        for resource in reversed(frame.owned_resources):
            resource.release()


@pytest.mark.parametrize(
    "view, empty",
    [
        ("photodiode_placement", False),
        ("photodiode_placement", True),
        ("blackout_placement", False),
    ],
)
def test_placement_preview_retains_outputs_and_rejects_invalid_live_rectangles(
    monkeypatch, view, empty
):
    from cephvr.visual_stimulus.config.calibration_adjustments import (
        CalibrationAdjustmentRejected,
        validated_update,
    )
    from cephvr.visual_stimulus.config.calibration_placement import (
        CalibrationPlacement,
        parse_placement,
    )

    gl = _FakeGL()
    raw = _two_output_display().model_dump(mode="json")
    raw["presentation_mode"] = "all_outputs_vsync"
    raw["calibration_view"] = view
    raw["photodiode_enabled"] = view == "photodiode_placement"
    if view == "photodiode_placement":
        raw["photodiode_output_id"] = raw["outputs"][0]["output_id"]
        raw["photodiode_patch"] = dict(
            rect=dict(x=12, y=14, width=8, height=6),
            background_rect=dict(x=10, y=10, width=20, height=20),
            high_linear_rgb=[1, 1, 1],
            low_linear_rgb=[0, 0, 0],
        )
    else:
        raw["photodiode_output_id"] = None
        raw["photodiode_patch"] = None
    if empty:
        raw["photodiode_enabled"] = False
        raw["photodiode_output_id"] = None
        raw["photodiode_patch"] = None
    for output in raw["outputs"]:
        output["blackout_zones"] = [dict(x=2, y=3, width=4, height=5)]
    display, prepared, outputs = _native_calibration_inputs(
        gl, parse_display_json(json.dumps(raw), max_bytes=1_000_000)
    )
    owner = DisplayCalibrationRenderer(
        outputs,
        SimpleNamespace(
            DEPTH_TEST=1, CULL_FACE=2, BLEND=4, ONE=1, TRIANGLES=5, TRIANGLE_STRIP=6
        ),
        lambda *_: None,
        lambda *a, **kw: None,
    )
    owner.present(display, prepared)
    assert not [event for event in gl.events if event[0] == "draw"]
    assert len([event for event in gl.events if event[0] == "copy"]) == len(outputs)
    masks = [event for event in gl.events if event[0] == "mask"]
    assert len([event for event in masks if event[2] == (1.0, 1.0, 1.0, 1.0)]) == (
        1 if view == "photodiode_placement" and not empty else 0
    )
    previous = owner.placement
    assert previous is not None
    payload = previous.model_dump(mode="json")
    if empty:
        assert previous.photodiode_patch is None
        with pytest.raises(CalibrationAdjustmentRejected):
            validated_update(view, (), json.dumps(payload))
        payload["photodiode_output_id"] = raw["outputs"][0]["output_id"]
        payload["photodiode_patch"] = dict(
            rect=dict(x=12, y=14, width=8, height=6),
            high_linear_rgb=[1, 1, 1],
            low_linear_rgb=[0, 0, 0],
        )
    payload["outputs"][0]["blackout_zones"] = [dict(x=1, y=1, width=10_000, height=2)]
    with pytest.raises(CalibrationAdjustmentRejected):
        owner.update(parse_placement(json.dumps(payload)))
    assert owner.placement is previous
    payload["outputs"][0]["blackout_zones"] = []
    placement = validated_update(view, (), json.dumps(payload))
    assert isinstance(placement, CalibrationPlacement)
    allocated = len(gl.resources)
    owner.update(placement)
    owner.present(display, prepared)
    assert len(gl.resources) == allocated
    assert not owner.placement.outputs[0].blackout_zones
    if empty:
        assert owner.placement.photodiode_patch.rect.x == 12
    with pytest.raises(CalibrationAdjustmentRejected):
        validated_update(
            view, (("diagnostic_front", (0, 0, 1, 0, 0, 1, 1, 1)),), json.dumps(payload)
        )
    with pytest.raises(CalibrationAdjustmentRejected):
        parse_placement('{"outputs":[],"outputs":[]}')
    with pytest.raises(CalibrationAdjustmentRejected):
        parse_placement(" " * 65_537)
    assert owner.release() == ()
    assert all(
        resource.released for resource in gl.resources if resource.label != "screen"
    )


def test_placement_native_pixels_use_gray_and_black():
    from cephvr.visual_stimulus.config.calibration_placement import parse_placement
    from cephvr.visual_stimulus.rendering.calibration_placement import draw_placement

    clears = []
    frame = SimpleNamespace(
        width=120,
        height=100,
        device_fbo=SimpleNamespace(
            use=lambda: None, clear=lambda *args, **kw: clears.append((args, kw))
        ),
    )
    context = SimpleNamespace(screen=None, scissor=None)
    placement = parse_placement(
        json.dumps(
            dict(
                outputs=[
                    dict(
                        output_id="screen",
                        blackout_zones=[dict(x=4, y=5, width=10, height=12)],
                    )
                ]
            )
        )
    )
    draw_placement(context, frame, "blackout_placement", "screen", placement)
    assert clears[0][0] == (0.25, 0.25, 0.25, 1.0)
    assert clears[1] == ((0.0, 0.0, 0.0, 1.0), {"viewport": (4, 5, 10, 12)})
    assert context.scissor is None
