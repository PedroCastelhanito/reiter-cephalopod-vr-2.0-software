from __future__ import annotations

import hashlib
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from tests.visual_stimulus.support import valid_display_json
from tests.visual_stimulus.test_resources import glb_fixture, pack_glb

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

    def release(self) -> ResourceReleaseReport:
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


def _geometric_profiles(display: DisplayProfile) -> dict[str, object]:
    profiles = {}
    for mapping in display.active_mappings:
        output = next(
            item
            for item in display.active_outputs
            if item.output_id == mapping.output_id
        )
        profiles[mapping.mapping_id] = GeometricProfile.model_validate(
            {
                "format_version": 1,
                "calibration_id": "calibration-test",
                "mapping_id": mapping.mapping_id,
                "surface_id": mapping.surface_id,
                "output_id": output.output_id,
                "output_width": output.width_px,
                "output_height": output.height_px,
                "viewport": mapping.viewport,
                "rows": 2,
                "columns": 2,
                "vertices": (
                    {"uv": (0, 0), "xy": (0, 0)},
                    {"uv": (1, 0), "xy": (1, 0)},
                    {"uv": (0, 1), "xy": (0, 1)},
                    {"uv": (1, 1), "xy": (1, 1)},
                ),
                "orientation": "preserving",
                "diagonal": "bottom_left_to_top_right",
                "mask": None,
                "weight": None,
                "overlap_group": None,
                "intended_coverage": ((0, 0), (1, 0), (1, 1), (0, 1)),
                "coverage_tolerance": 0.01,
                "triangle_area_tolerance": 0.0001,
            }
        )
    return profiles


def _native_calibration_inputs(gl: _FakeGL):
    display = _two_output_display()
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


def test_native_calibration_owner_uses_surface_warp_and_output_pipeline(
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

    draws = [event for event in gl.events if event[0] == "draw"]
    assert {event[2] for event in draws} == {"arena", "warp", "output"}
    for output_id in outputs:
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


def test_native_port_releases_owner_and_accepts_a_later_calibration(
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
    port._orphan_windows = {}
    port._window_obligations = set()
    port._released = []
    port.announce = lambda *_args: None
    ticks = iter(range(10, 1000))
    port.clock_ns = lambda: next(ticks)

    for index in range(2):
        activities = port.present_display_calibration(display, prepared)
        assert {item.output_id for item in activities} == set(outputs)
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

    assert port._released.count("visual_stimulus:gpu:display-calibration:arena") == 2


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
    port._orphan_windows = {}
    port._window_obligations = set()
    port._released = []
    port.announce = lambda *_args: None
    ticks = iter(range(10, 1000))
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
