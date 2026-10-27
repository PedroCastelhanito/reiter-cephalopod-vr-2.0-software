"""GPU screen-plane preview; the inspection camera never changes stimulus state."""

from __future__ import annotations

import math
import struct
from typing import Any

from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.config.models.artifact_models import (
    CompositeTile,
    ReviewLayout,
)
from cephvr.visual_stimulus.config.models.display_profile import Geometry, Surface
from cephvr.visual_stimulus.rendering.preview import StimulusPreview

_VERTEX = """#version 430
in vec2 in_position; in vec2 in_uv; out vec2 uv;
void main() { uv = in_uv; gl_Position = vec4(in_position, 0, 1); }
"""
_FRAGMENT = """#version 430
in vec2 uv; out vec4 color;
uniform sampler2D image; uniform vec4 crop; uniform bool outline;
uniform vec3 outline_color;
void main() {
    vec2 margin = 0.5 / vec2(textureSize(image, 0));
    vec2 point = clamp(crop.xy + uv * crop.zw,
                      crop.xy + margin, crop.xy + crop.zw - margin);
    color = outline ? vec4(outline_color, 1) : vec4(texture(image, point).rgb, 1);
}
"""


def projected_screens(
    geometry: Geometry, azimuth: float, elevation: float, width: int, height: int
) -> list[tuple[Surface, tuple[tuple[float, float], ...]]]:
    """Match the planning rig's orthographic rotation, fit and painter ordering."""
    yaw, pitch = math.radians(azimuth), math.radians(elevation)

    def project(point: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = point
        across = x * math.cos(yaw) - y * math.sin(yaw)
        away = x * math.sin(yaw) + y * math.cos(yaw)
        return (
            across,
            z * math.cos(pitch) - away * math.sin(pitch),
            away * math.cos(pitch) + z * math.sin(pitch),
        )

    faces = [
        (
            surface,
            tuple(
                project(p)
                for p in (
                    surface.bottom_left_mm,
                    surface.bottom_right_mm,
                    surface.top_right_mm,
                    surface.top_left_mm,
                )
            ),
        )
        for surface in geometry.surfaces
    ]
    points = [point for _, corners in faces for point in corners]
    low = tuple(min(p[i] for p in points) for i in (0, 1))
    high = tuple(max(p[i] for p in points) for i in (0, 1))
    scale = min(
        max(1, width - 48) / max(1, high[0] - low[0]),
        max(1, height - 48) / max(1, high[1] - low[1]),
    )
    return [
        (
            surface,
            tuple(
                (
                    (x - (low[0] + high[0]) / 2) * scale * 2 / max(1, width),
                    (y - (low[1] + high[1]) / 2) * scale * 2 / max(1, height),
                )
                for x, y, _ in corners
            ),
        )
        for surface, corners in sorted(
            faces, key=lambda item: sum(p[2] for p in item[1])
        )
    ]


def screen_uv(face: str, tile: CompositeTile) -> tuple[tuple[float, float], ...]:
    # Undo Monitor presentation transforms without reflecting physical surface motion.
    if face == "bottom":
        points = ((1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0))
    else:
        points = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    result = []
    for u, v in points:
        if tile.label in {"Left", "Front", "Right"}:
            u = 1 - u
        for _ in range(tile.rotation_clockwise_degrees // 90):
            u, v = v, 1 - u
        result.append((u, v))
    return tuple(result)


class RigStimulusPreview(StimulusPreview):
    def __init__(self, glfw: Any, moderngl: Any, changed: Any) -> None:
        super().__init__(glfw, moderngl, changed)
        self.title = "CephVR Visual stimulus · Rig (drag to rotate)"
        self.scene_geometry: Geometry | None = None
        self.layout: ReviewLayout | None = None
        self.hidden_surfaces: set[str] = set()
        self.azimuth, self.elevation = 25.0, 25.0
        self.drag_origin: tuple[float, float] | None = None
        self.last_press_ns = 0
        self.last_press_position: tuple[float, float] | None = None
        self.program: Any = None
        self.buffer: Any = None
        self.array: Any = None
        self.background = (0.035, 0.055, 0.07)
        self.surface_colors: dict[str, tuple[float, float, float]] = {}

    def prepare(self, shared_window: Any) -> None:
        super().prepare(shared_window)
        self.glfw.set_mouse_button_callback(self.window, self.mouse_button)
        self.glfw.set_cursor_pos_callback(self.window, self.cursor_position)
        self.glfw.set_window_focus_callback(self.window, self.focus_changed)

    def prepare_scene(self) -> None:
        self.program = self.context.program(
            vertex_shader=_VERTEX, fragment_shader=_FRAGMENT
        )
        self.resources.append(self.program)
        self.buffer = self.context.buffer(reserve=64, dynamic=True)
        self.resources.append(self.buffer)
        self.array = self.context.vertex_array(
            self.program, [(self.buffer, "2f 2f", "in_position", "in_uv")]
        )
        self.resources.append(self.array)

    def mouse_button(self, window: Any, button: int, action: int, mods: int) -> None:
        if button != self.glfw.MOUSE_BUTTON_LEFT:
            return
        if action == self.glfw.RELEASE:
            self.drag_origin = None
        elif action == self.glfw.PRESS:
            position = self.glfw.get_cursor_pos(window)
            now = host_time_ns()
            if (
                self.last_press_position is not None
                and 0 < now - self.last_press_ns <= 400_000_000
                and math.dist(position, self.last_press_position) <= 5
            ):
                self.azimuth, self.elevation = 25.0, 25.0
                self.last_press_position = None
                self.drag_origin = None
            else:
                self.drag_origin = position
                self.last_press_position = position
            self.last_press_ns = now

    def cursor_position(self, window: Any, x: float, y: float) -> None:
        if self.drag_origin is not None:
            dx, dy = x - self.drag_origin[0], y - self.drag_origin[1]
            self.azimuth = (self.azimuth + dx * 0.5) % 360
            self.elevation = max(-80.0, min(80.0, self.elevation + dy * 0.5))
            self.drag_origin = (x, y)
            # A completed drag must not turn the next click into a double-click.
            if (
                self.last_press_position
                and math.dist((x, y), self.last_press_position) > 5
            ):
                self.last_press_position = None

    def focus_changed(self, window: Any, focused: bool) -> None:
        if not focused:
            self.drag_origin = None
            self.last_press_position = None

    def draw(self, texture: Any, width: int, height: int) -> None:
        if not self.visible or (self.owner is not None and self.owner.minimized):
            return
        self.activate()
        context = self.context
        context.screen.use()
        w, h = self.glfw.get_framebuffer_size(self.window)
        context.viewport = (0, 0, w, h)
        self.draw_scene(texture, width, height, w, h)
        self.glfw.swap_buffers(self.window)
        self.rates.presented += 1

    def draw_scene(self, texture: Any, width: int, height: int, w: int, h: int) -> None:
        """Draw into the caller's bound framebuffer without readback or source writes."""
        context = self.context
        context.scissor = None
        context.disable(
            self.moderngl.DEPTH_TEST | self.moderngl.BLEND | self.moderngl.CULL_FACE
        )
        context.clear(*self.background)
        if self.scene_geometry is not None and self.layout is not None:
            texture.use(0)
            self.program["image"].value = 0
            tiles = {
                name.lower(): tile
                for tile in self.layout.tiles
                for name in tile.label.split(" / ")
            }
            for surface, corners in projected_screens(
                self.scene_geometry, self.azimuth, self.elevation, w, h
            ):
                if surface.surface_id in self.hidden_surfaces:
                    continue
                tile = tiles.get(surface.surface_id)
                if tile is not None:
                    rect = tile.rect
                    self.program["crop"].value = (
                        rect.x / width,
                        rect.y / height,
                        rect.width / width,
                        rect.height / height,
                    )
                uv_points = (
                    screen_uv(surface.surface_id, tile) if tile else ((0, 0),) * 4
                )
                vertices = [
                    v
                    for point, uv in zip(corners, uv_points, strict=True)
                    for v in (*point, *uv)
                ]
                self.buffer.write(struct.pack("16f", *vertices))
                if tile is not None:
                    self.program["outline"].value = False
                    self.array.render(mode=self.moderngl.TRIANGLE_FAN)
                self.program["outline"].value = True
                self.program["outline_color"].value = self.surface_colors.get(
                    surface.surface_id, (0.35, 0.72, 0.92)
                )
                self.array.render(mode=self.moderngl.LINE_LOOP)
