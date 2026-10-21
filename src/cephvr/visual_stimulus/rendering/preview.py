"""Optional renderer-owned GLFW viewer; no pixel transport or experiment control."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.shared.clock import host_time_ns
from cephvr.shared.preview_geometry import PreviewGeometryGuard
from cephvr.shared.preview_rates import PreviewPacer, PreviewRateMeter
from cephvr.visual_stimulus.rendering.capture import struct_quad
from cephvr.visual_stimulus.rendering.native_display import attach_window_context

_VERTEX = """#version 430
in vec2 in_position; in vec2 in_uv; out vec2 uv;
void main() { uv = in_uv; gl_Position = vec4(in_position, 0, 1); }
"""
_FRAGMENT = """#version 430
in vec2 uv; out vec4 color; uniform sampler2D image;
void main() { color = vec4(texture(image, uv).rgb, 1); }
"""


class StimulusPreview:
    def __init__(
        self, glfw: Any, moderngl: Any, changed: Callable[[bool, bool, str], None]
    ) -> None:
        self.glfw, self.moderngl, self.changed = glfw, moderngl, changed
        self.window: Any = None
        self.context: Any = None
        self.resources: list[Any] = []
        self.owner: Any = None
        self.visible = False
        self.geometry = PreviewGeometryGuard()
        self.owner_identity: tuple[int, int, int] | None = None
        self.title = "CephVR Visual stimulus"
        self.on_rates: Callable[[float | None, float, int], None] = lambda *_: None
        self.rates = PreviewRateMeter()
        self.pacer = PreviewPacer()
        self.source_count = 0

    def prepare(self, shared_window: Any) -> None:
        glfw = self.glfw
        glfw.default_window_hints()
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        self.window = glfw.create_window(640, 640, self.title, None, shared_window)
        if not self.window:
            raise RuntimeError("Visual Stimulus preview window creation failed")
        glfw.set_window_size_limits(self.window, 128, 128, 2048, 2048)
        glfw.make_context_current(self.window)
        self.context = context = attach_window_context(self.moderngl)
        glfw.swap_interval(0)
        program = context.program(vertex_shader=_VERTEX, fragment_shader=_FRAGMENT)
        self.resources.append(program)
        buffer = context.buffer(struct_quad())
        self.resources.append(buffer)
        self.resources.append(
            context.vertex_array(program, [(buffer, "2f 2f", "in_position", "in_uv")])
        )
        self.clear()
        self.changed(True, False, "")

    def set_visible(self, visible: bool, placement: rpc.PreviewWindowPlacement) -> None:
        if not self.window or self.context is None:
            raise ValueError("Visual Stimulus preview is not prepared")
        if placement.update_existing_only and not self.visible:
            return
        if visible:
            if not self.visible:
                self.rates = PreviewRateMeter()
                self.pacer = PreviewPacer()
            if placement.side and not 128 <= placement.side <= 2048:
                raise ValueError("preview side must be 128..2048 pixels")
            if not self.visible or placement.snap_to_grid:
                self.geometry = PreviewGeometryGuard()
            if self.owner is not None:
                self.geometry.observe(
                    self.owner.geometry(), self.owner.placement_revision()
                )
            if (
                placement.update_existing_only
                and self.geometry.manual
                and not placement.snap_to_grid
            ):
                return
            if placement.side:
                self.glfw.set_window_size(self.window, placement.side, placement.side)
                if sys.platform != "win32":
                    self.glfw.set_window_pos(self.window, placement.x, placement.y)
            if sys.platform == "win32" and placement.side:
                from cephvr.platform.windows.window_coordinates import (
                    position_preview_frame,
                )

                position_preview_frame(
                    self.title, placement.x, placement.y, topmost=False
                )
            # Binding the native owner can show the window; place it first.
            if placement.gui_window_handle and sys.platform == "win32":
                from cephvr.platform.windows.preview_owner import WindowsPreviewOwner

                identity = (
                    placement.gui_window_handle,
                    placement.gui_process_id,
                    placement.gui_process_creation_time_100ns,
                )
                if self.owner_identity != identity:
                    if self.owner is not None:
                        self.owner.close()
                        self.owner = None
                    self.owner = WindowsPreviewOwner(self.title, *identity)
                    self.owner_identity = identity
                    self.geometry.last = None
                    self.geometry.revision = None
            self.glfw.set_window_should_close(self.window, False)
            self.glfw.show_window(self.window)
        else:
            self.glfw.hide_window(self.window)
        if self.owner is not None and visible:
            self.geometry.arranged(
                self.owner.geometry(), self.owner.placement_revision()
            )
            self.owner.sync()
        self.visible = visible
        self.changed(True, visible, "")

    def source_frame(self) -> None:
        self.source_count += 1
        self.rates.received(self.source_count, host_time_ns())

    def service(self) -> None:
        if self.window and self.visible:
            now = host_time_ns()
            rates = self.rates.sample(now)
            if rates is not None:
                self.on_rates(*rates, now)
            if self.owner is not None:
                self.owner.sync()
            if self.glfw.window_should_close(self.window):
                self.set_visible(False, rpc.PreviewWindowPlacement())

    def activate(self) -> None:
        self.glfw.make_context_current(self.window)

    def frame_due(self) -> bool:
        return (
            self.visible
            and not (self.owner is not None and self.owner.minimized)
            and self.pacer.ready(host_time_ns())
        )

    def disable(self, error: Exception) -> None:
        self.visible = False
        try:
            if self.window:
                self.glfw.hide_window(self.window)
        except Exception:
            pass  # Cleanup still owns the window even if the native hide failed.
        self.changed(False, False, str(error)[:512])

    def draw(self, texture: Any, width: int, height: int) -> None:
        if not self.visible or (self.owner is not None and self.owner.minimized):
            return
        self.glfw.make_context_current(self.window)
        context = self.context
        context.screen.use()
        w, h = self.glfw.get_framebuffer_size(self.window)
        context.viewport = (0, 0, w, h)
        context.clear(0, 0, 0)
        fit = min(w / width, h / height)
        dw, dh = max(1, round(width * fit)), max(1, round(height * fit))
        context.viewport = ((w - dw) // 2, (h - dh) // 2, dw, dh)
        texture.use(0)
        self.resources[0]["image"].value = 0
        self.resources[2].render(mode=self.moderngl.TRIANGLE_STRIP)
        self.glfw.swap_buffers(self.window)
        self.rates.presented += 1

    def clear(self) -> None:
        if self.context is not None:
            self.glfw.make_context_current(self.window)
            self.context.screen.use()
            self.context.clear(0, 0, 0)
            self.glfw.swap_buffers(self.window)

    def release(self) -> None:
        if self.owner is not None:
            self.owner.close()
            self.owner = None
        if self.window:
            self.glfw.make_context_current(self.window)
            while self.resources:
                self.resources[-1].release()
                self.resources.pop()
            if self.context is not None:
                self.context.release()
                self.context = None
            self.glfw.destroy_window(self.window)
            self.window = None
        self.visible = False
        self.changed(False, False, "")
