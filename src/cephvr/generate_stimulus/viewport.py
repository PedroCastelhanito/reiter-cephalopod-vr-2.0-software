"""Interactive unlit authoring viewport; it owns no projector or runtime session."""

import hashlib
import io
import math
from typing import Any

import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QSurfaceFormat, QWheelEvent
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from .arena import CompiledArena

VERTEX = """#version 330
in vec3 position; in vec2 uv; in vec4 color;
uniform mat4 mvp; out vec2 texcoord; out vec4 vertex_color;
void main(){gl_Position=mvp*vec4(position,1);texcoord=uv;vertex_color=color;}
"""
FRAGMENT = """#version 330
in vec2 texcoord; in vec4 vertex_color;
uniform vec4 factor; uniform sampler2D image; uniform bool textured;
uniform int alpha_mode; uniform float cutoff;
out vec4 fragment;
vec3 encode(vec3 x){return mix(12.92*x,1.055*pow(max(x,vec3(0)),vec3(1.0/2.4))-0.055,step(vec3(0.0031308),x));}
void main(){vec4 c=factor*vertex_color;
if(textured){vec4 t=texture(image,vec2(texcoord.x,1.0-texcoord.y));
if(alpha_mode==1){c.rgb*=t.a>0 ? t.rgb/t.a : vec3(0); c.a*=t.a;} else {c.rgb*=t.rgb;}}
if(alpha_mode==1 && c.a<cutoff) discard;
if(alpha_mode!=2)c.a=1;
fragment=vec4(encode(c.rgb),c.a);}
"""


class ArenaViewport(QOpenGLWidget):
    selected = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        surface_format = QSurfaceFormat()
        surface_format.setVersion(3, 3)
        surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        surface_format.setDepthBufferSize(24)
        self.setFormat(surface_format)
        self.setMinimumSize(280, 250)
        self.ctx: Any = None
        self.program: Any = None
        self.result: CompiledArena | None = None
        self.draws: list[Any] = []
        self.resources: list[Any] = []
        self.cached: dict[str, list[Any]] = {}
        self.dirty = False
        self.fitted: float | None = None
        self.yaw, self.pitch = 0.8, 0.65
        self.distance = 1000.0
        self.target = np.zeros(3)
        self.press: Any = None
        self.last: Any = None
        self.mvp = np.eye(4)
        self.error = ""

    def initializeGL(self) -> None:
        try:
            import moderngl

            self.ctx = moderngl.create_context(require=330)
            self.program = self.ctx.program(
                vertex_shader=VERTEX, fragment_shader=FRAGMENT
            )
            context = self.context()
            assert context is not None
            context.aboutToBeDestroyed.connect(self.release)
        except Exception as error:
            self.error = str(error)
            self.failed.emit(
                f"3D preview unavailable: {error}. Saving remains available."
            )

    def release(self) -> None:
        self.makeCurrent()
        for resource in reversed(self.resources):
            resource.release()
        self.resources.clear()
        self.cached.clear()
        self.draws.clear()
        self.doneCurrent()

    def set_arena(self, result: CompiledArena) -> None:
        self.result = result
        self.dirty = True
        # Keep the user's view for small edits; reframe when the arena size changes.
        low, high = self._bounds()
        diagonal = max(1.0, float(np.linalg.norm(high - low)))
        if self.fitted is None or abs(diagonal - self.fitted) > 0.05 * self.fitted:
            self.fit()
        self.update()

    def _bounds(self) -> tuple[np.ndarray, np.ndarray]:
        assert self.result is not None
        points = np.concatenate(
            [
                np.asarray(p.positions)
                for n in self.result.scene.nodes
                for p in n.primitives
            ]
        )
        return points.min(0), points.max(0)

    def fit(self) -> None:
        if self.result is None:
            return
        low, high = self._bounds()
        self.target = (low + high) / 2
        self.fitted = max(1.0, float(np.linalg.norm(high - low)))
        self.distance = self.fitted * 1.6
        self.update()

    def _upload(self) -> None:
        retained: dict[str, list[Any]] = {}
        self.draws.clear()
        assert self.result is not None
        scene = self.result.scene
        from cephvr.visual_stimulus.rendering.arena_gpu import configure_sampler
        from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes
        from cephvr.visual_stimulus.resources.media import ImagePixels

        def texture(index: int, opaque: bool) -> Any:
            """Upload the variant a draw needs; each draw uses one per material."""
            source = scene.textures[index]
            key = hashlib.sha256(
                source.image
                + repr(
                    (
                        source.wrap_s,
                        source.wrap_t,
                        source.min_filter,
                        source.mag_filter,
                        opaque,
                    )
                ).encode()
            ).hexdigest()
            existing = retained.get(key, self.cached.get(key))
            if existing is None:
                with Image.open(io.BytesIO(source.image)) as image:
                    rgba = np.asarray(image.convert("RGBA"))
                    pixels = ImagePixels(
                        image.width,
                        image.height,
                        "uint8",
                        4,
                        ("red", "green", "blue", "alpha"),
                        rgba,
                        "srgb",
                        "straight",
                    )
                    raw = linear_rgba_bytes(pixels, opaque=opaque)
                    gl_texture = self.ctx.texture(image.size, 4, raw, dtype="f4")
                configure_sampler(gl_texture, source)
                existing = [gl_texture]
                self.resources.extend(existing)
            retained[key] = existing
            return existing[0]

        for node in scene.nodes:
            for primitive in node.primitives:
                points = np.asarray(primitive.positions, dtype="f4")
                uv = (
                    np.zeros((len(points), 2), dtype="f4")
                    if primitive.texcoords is None
                    else np.asarray(primitive.texcoords, dtype="f4")
                )
                colors = np.ones((len(points), 4), dtype="f4")
                if primitive.colors is not None:
                    color = np.asarray(primitive.colors, dtype="f4")
                    colors[:, : color.shape[1]] = color
                vertices = (
                    np.concatenate([points, uv, colors], axis=1).astype("f4").tobytes()
                )
                index_bytes = np.asarray(primitive.indices, dtype="u4").tobytes()
                key = hashlib.sha256(vertices + index_bytes).hexdigest()
                existing = retained.get(key, self.cached.get(key))
                if existing is None:
                    buffer = self.ctx.buffer(vertices)
                    indices = self.ctx.buffer(index_bytes)
                    vao = self.ctx.vertex_array(
                        self.program,
                        [(buffer, "3f 2f 4f", "position", "uv", "color")],
                        index_buffer=indices,
                    )
                    existing = [buffer, indices, vao]
                    self.resources.extend(existing)
                retained[key] = existing
                vao = existing[-1]
                material = scene.materials[primitive.material_index or 0]
                self.draws.append(
                    (
                        vao,
                        material,
                        None
                        if material.texture_index is None
                        else texture(
                            material.texture_index, material.alpha_mode == "OPAQUE"
                        ),
                    )
                )
        for key, resources in self.cached.items():
            if key not in retained:
                for resource in reversed(resources):
                    resource.release()
        self.cached = retained
        self.resources = [
            resource for resources in retained.values() for resource in resources
        ]
        self.dirty = False

    def paintGL(self) -> None:
        if self.ctx is None or self.error:
            return
        try:
            import moderngl

            self.ctx.detect_framebuffer(self.defaultFramebufferObject()).use()
            self.ctx.viewport = (
                0,
                0,
                round(self.width() * self.devicePixelRatioF()),
                round(self.height() * self.devicePixelRatioF()),
            )
            self.ctx.clear(0.12, 0.13, 0.15, 1)
            if self.result is None:
                return
            if self.dirty:
                self._upload()
            eye = self.target + self.distance * np.array(
                [
                    math.cos(self.pitch) * math.cos(self.yaw),
                    math.cos(self.pitch) * math.sin(self.yaw),
                    math.sin(self.pitch),
                ]
            )
            forward = self.target - eye
            forward /= np.linalg.norm(forward)
            right = np.cross(forward, [0, 0, 1])
            right /= np.linalg.norm(right)
            up = np.cross(right, forward)
            view = np.eye(4)
            view[:3, :3] = np.stack([right, up, -forward])
            view[:3, 3] = -view[:3, :3] @ eye
            near, far = self.distance / 1000, self.distance * 100
            f = 1 / math.tan(math.radians(45) / 2)
            projection = np.array(
                [
                    [f / (self.width() / max(1, self.height())), 0, 0, 0],
                    [0, f, 0, 0],
                    [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
                    [0, 0, -1, 0],
                ]
            )
            self.mvp = projection @ view
            self.program["mvp"].write(self.mvp.T.astype("f4").tobytes())
            self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
            self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            for vao, material, texture in self.draws:
                if material.double_sided:
                    self.ctx.disable(moderngl.CULL_FACE)
                else:
                    self.ctx.enable(moderngl.CULL_FACE)
                self.program["factor"].value = material.base_color_factor
                self.program["alpha_mode"].value = {"OPAQUE": 0, "MASK": 1, "BLEND": 2}[
                    material.alpha_mode
                ]
                self.program["cutoff"].value = material.alpha_cutoff
                self.program["textured"].value = texture is not None
                if texture is not None:
                    texture.use(0)
                vao.render()
        except Exception as error:
            self.error = str(error)
            self.failed.emit(f"Preview failed: {error}; saving remains available")

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        self.press = self.last = event.position()

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self.last is None:
            return
        delta = event.position() - self.last
        self.last = event.position()
        if event.buttons() & Qt.MouseButton.RightButton:
            self.target += (
                self.distance
                * 0.001
                * np.array(
                    [
                        -delta.x() * math.sin(self.yaw),
                        delta.x() * math.cos(self.yaw),
                        delta.y(),
                    ]
                )
            )
        else:
            self.yaw -= delta.x() * 0.01
            self.pitch = float(np.clip(self.pitch + delta.y() * 0.01, -1.5, 1.5))
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if (
            self.press is not None
            and (event.position() - self.press).manhattanLength() < 4
        ):
            self._pick(event.position().x(), event.position().y())
        self.last = None

    def _pick(self, x: float, y: float) -> None:
        if self.result is None:
            return
        inverse = np.linalg.inv(self.mvp)
        ray = [
            inverse
            @ np.array([2 * x / self.width() - 1, 1 - 2 * y / self.height(), z, 1])
            for z in (-1, 1)
        ]
        start, end = [p[:3] / p[3] for p in ray]
        direction = end - start
        nearest = float("inf")
        selected = ""
        for node, name in zip(
            self.result.scene.nodes, self.result.surface_names, strict=True
        ):
            for primitive in node.primitives:
                triangles = np.asarray(primitive.positions)[
                    np.asarray(primitive.indices).reshape(-1, 3)
                ]
                e1, e2 = (
                    triangles[:, 1] - triangles[:, 0],
                    triangles[:, 2] - triangles[:, 0],
                )
                h = np.cross(direction, e2)
                det = np.einsum("ij,ij->i", e1, h)
                material = self.result.scene.materials[primitive.material_index or 0]
                good = np.abs(det) > 1e-9 if material.double_sided else det > 1e-9
                inv = np.divide(1, det, out=np.zeros_like(det), where=good)
                s = start - triangles[:, 0]
                u = inv * np.einsum("ij,ij->i", s, h)
                q = np.cross(s, e1)
                v = inv * (q @ direction)
                t = inv * np.einsum("ij,ij->i", e2, q)
                valid = good & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
                if valid.any() and float(t[valid].min()) < nearest:
                    nearest = float(t[valid].min())
                    selected = name
        if selected:
            self.selected.emit(selected)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is None:
            return
        self.distance = max(
            0.01, min(1e9, self.distance * math.exp(-event.angleDelta().y() / 1200))
        )
        self.update()
