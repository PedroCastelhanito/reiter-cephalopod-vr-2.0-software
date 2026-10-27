"""Per-prepared-trial lookups reused by every layer draw.

The layouts and calibrations of one PreparedTrial never change, so scans and
calibration-derived frames are computed once. The owner (the scene renderer) keeps
one cache per trial entry and drops it with the artifact; a cache never serves
another artifact object.
"""

from __future__ import annotations

from cephvr.visual_stimulus.config.models.artifact_models import (
    GeometricProfile,
    PreparedTrial,
)
from cephvr.visual_stimulus.config.models.evidence_model import UniformLayout
from cephvr.visual_stimulus.rendering.image_fit import screen_image_frame
from cephvr.visual_stimulus.rendering.image_fold import calibrated_fold_map

ScreenFrame = tuple[tuple[tuple[float, float], ...], tuple[int, int]]


class LayerCache:
    def __init__(self, artifact: PreparedTrial) -> None:
        self.artifact = artifact
        self._layouts: dict[tuple[str | None, str | None, str], UniformLayout] = {}
        self._by_instance: dict[str | None, list[UniformLayout]] = {}
        for item in artifact.uniform_layouts:
            self._layouts.setdefault(
                (item.instance_id, item.output_id, item.name), item
            )
            self._by_instance.setdefault(item.instance_id, []).append(item)
        self._profiles: dict[str, GeometricProfile] | None = None
        self._frames: dict[str, ScreenFrame] = {}
        self._folds: dict[str, tuple[float, ...]] = {}

    @classmethod
    def for_artifact(
        cls, artifact: PreparedTrial, cache: LayerCache | None
    ) -> LayerCache:
        """Reuse the owner's cache only when it was built for this artifact object."""
        return (
            cache if cache is not None and cache.artifact is artifact else cls(artifact)
        )

    def instance_layouts(self, instance_id: str) -> list[UniformLayout]:
        return self._by_instance.get(instance_id, [])

    def layout(
        self, instance_id: str, output_id: str, name: str, *, detail: str | None = None
    ) -> UniformLayout:
        item = self._layouts.get((instance_id, output_id, name))
        if item is None:
            raise RuntimeError(
                detail
                or f"prepared shader layout omits {name} for {instance_id} on {output_id}"
            )
        return item

    def profile(self, mapping_id: str) -> GeometricProfile:
        if self._profiles is None:
            self._profiles = {}
            for item in self.artifact.geometric_calibration:
                self._profiles.setdefault(item.mapping_id, item)
        try:
            return self._profiles[mapping_id]
        except KeyError:
            raise RuntimeError(
                f"prepared geometric calibration for mapping {mapping_id} is unavailable"
            ) from None

    def screen_frame(self, mapping_id: str) -> ScreenFrame:
        """Valid-area corners and target pixels of a mapped screen-space image."""
        frame = self._frames.get(mapping_id)
        if frame is None:
            corners, pixels = screen_image_frame(self.profile(mapping_id))
            frame = self._frames[mapping_id] = (tuple(corners), pixels)
        return frame

    def fold_map(self, mapping_id: str) -> tuple[float, ...]:
        fold = self._folds.get(mapping_id)
        if fold is None:
            fold = self._folds[mapping_id] = calibrated_fold_map(
                self.artifact.display.geometry,
                self.artifact.geometric_calibration,
                self.profile(mapping_id),
            )
        return fold
