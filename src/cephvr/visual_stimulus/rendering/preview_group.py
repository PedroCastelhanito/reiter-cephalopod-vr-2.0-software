"""One optional preview resource with Combined or bounded projector windows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cephvr.control.v1 import services_pb2 as rpc
from cephvr.shared.clock import host_time_ns
from cephvr.shared.preview_placement import valid_stimulus_tiles
from cephvr.shared.preview_rates import PreviewPacer
from cephvr.visual_stimulus.config.models.artifact_models import ReviewLayout
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.rendering.capture_sync import (
    order_shared_outputs,
    release_fences,
)
from cephvr.visual_stimulus.rendering.preview import StimulusPreview
from cephvr.visual_stimulus.rendering.preview_rig import RigStimulusPreview


def _rgb(color: int) -> tuple[float, float, float]:
    return ((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255


class StimulusPreviewGroup:
    def __init__(
        self,
        glfw: Any,
        moderngl: Any,
        changed: Callable[[bool, bool, str], None],
        layout: ReviewLayout,
        geometry: Geometry | None = None,
    ) -> None:
        self.glfw, self.moderngl, self.changed, self.layout = (
            glfw,
            moderngl,
            changed,
            layout,
        )
        self.combined = RigStimulusPreview(glfw, moderngl, self.window_changed)
        self.combined.scene_geometry = geometry
        self.combined.layout = layout
        self.windows: dict[str, StimulusPreview] = {"": self.combined}
        self.pending: list[Any] = []
        self.readers: dict[str, StimulusPreview] = {}
        self.mutating = False
        self.pacer = PreviewPacer()
        self.on_rates: Callable[[float | None, float, int], None] = lambda *_: None

    @property
    def context(self) -> Any:
        return self.combined.context

    @property
    def visible(self) -> bool:
        return any(window.visible for window in self.windows.values())

    def window_changed(self, available: bool, visible: bool, failure: str) -> None:
        if not self.mutating:
            self.changed(available, self.visible if available else False, failure)

    def prepare(self, shared_window: Any) -> None:
        self.combined.prepare(shared_window)

    def update_layout(
        self, layout: ReviewLayout, geometry: Geometry | None = None
    ) -> None:
        self.layout = layout
        self.combined.layout = layout
        if geometry is not None:
            self.combined.scene_geometry = geometry
        for name, window in self.windows.items():
            tile = self.tile(name)
            if tile is not None:
                rect = tile.rect
                window.crop = (
                    rect.x / layout.composite_width,
                    rect.y / layout.composite_height,
                    rect.width / layout.composite_width,
                    rect.height / layout.composite_height,
                )

    def tile(self, name: str) -> Any:
        # A single physical output may cover more than one named surface.
        return next(
            (tile for tile in self.layout.tiles if name in tile.label.split(" / ")),
            None,
        )

    def activate(self) -> None:
        # Order every consumer before the next compositor overwrite/recording read.
        order_shared_outputs({"combined": self.combined, **self.readers}, self.pending)
        self.readers.clear()

    def set_visible(self, visible: bool, placement: rpc.PreviewWindowPlacement) -> None:
        was_visible = self.visible
        if not valid_stimulus_tiles(placement):
            raise ValueError("Invalid projector preview placement")
        if placement.update_existing_only and not self.visible:
            return
        requested = {item.surface: item for item in placement.stimulus_tiles}
        if any(self.tile(name) is None for name in requested):
            raise ValueError("Preview projector is not in the prepared output layout")
        self.combined.hidden_surfaces = {
            name.lower() for name in placement.hidden_stimulus_surfaces
        }
        if placement.HasField("stimulus_background_rgb"):
            self.combined.background = _rgb(placement.stimulus_background_rgb)
        self.combined.surface_colors = {
            name.lower(): _rgb(color)
            for name, color in placement.stimulus_surface_colors.items()
        }
        self.mutating = True
        try:
            for name in requested:
                if name not in self.windows:
                    window = StimulusPreview(
                        self.glfw, self.moderngl, self.window_changed
                    )
                    window.title = f"CephVR Visual stimulus · {name}"
                    self.windows[name] = window
                    window.prepare(self.combined.window)
            self.update_layout(self.layout)
            for name, window in self.windows.items():
                hint = rpc.PreviewWindowPlacement()
                hint.CopyFrom(placement)
                hint.ClearField("stimulus_tiles")
                show = visible and (name in requested if requested else not name)
                if not name and len(self.combined.hidden_surfaces) == 4:
                    show = False
                # A layout-mode switch may open its alternate windows; ordinary polling cannot reopen an X-closed group.
                hint.update_existing_only = (
                    placement.update_existing_only and window.visible
                )
                if name in requested:
                    item = requested[name]
                    hint.x, hint.y, hint.side = item.x, item.y, item.side
                window.set_visible(show, hint)
            active = [window for window in self.windows.values() if window.visible]
            for window in self.windows.values():
                window.on_rates = lambda *_: None
            if active:
                if not was_visible:
                    self.pacer = PreviewPacer()
                active[0].on_rates = lambda *args: self.on_rates(*args)
        finally:
            self.mutating = False
        self.changed(True, self.visible, "")

    def source_frame(self) -> None:
        for window in self.windows.values():
            window.source_frame()

    def service(self) -> None:
        for window in self.windows.values():
            was_visible = window.visible
            window.service()
            if was_visible and not window.visible:
                self.set_visible(False, rpc.PreviewWindowPlacement())
                break

    def frame_due(self) -> bool:
        # Every visible consumer is drawn together, so they share one cadence.
        return any(
            window.visible and not (window.owner is not None and window.owner.minimized)
            for window in self.windows.values()
        ) and self.pacer.ready(host_time_ns())

    def draw(self, texture: Any, width: int, height: int) -> None:
        for name, window in self.windows.items():
            if not window.visible:
                continue
            order_shared_outputs(
                {"target": window, "source": self.combined}, self.pending
            )
            tile = self.tile(name)
            window.draw(
                texture,
                tile.rect.width if tile else width,
                tile.rect.height if tile else height,
            )
            self.readers[name] = window

    def clear(self) -> None:
        for window in self.windows.values():
            window.clear()

    def disable(self, error: Exception) -> None:
        self.mutating = True
        try:
            for window in self.windows.values():
                window.disable(error)
        finally:
            self.mutating = False
        self.changed(False, False, str(error)[:512])

    def release(self) -> None:
        self.combined.activate()
        release_fences(self.pending)
        for name in reversed(tuple(self.windows)):
            self.windows[name].release()
            del self.windows[name]
