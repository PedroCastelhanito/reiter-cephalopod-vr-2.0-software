"""Trial-to-session bindings for prepared video assets and renderer state."""

from __future__ import annotations

import json
from fractions import Fraction

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.config.models.program_model import VideoSettings

from .assets import PreparedResourceBundle
from .budget import BoundedBudget
from .video import VideoPlayback, VideoPresentation
from .video_decoder import VideoPlaybackError
from .video_index import VideoIndex


class VideoSession:
    """Own the narrow mapping from compiled instance IDs to video playback IDs."""

    def __init__(self, playback: VideoPlayback, budget: BoundedBudget) -> None:
        self.playback = playback
        self.budget = budget
        self._variants: dict[tuple[str, str], tuple[str, ...]] = {}

    def register_trial(
        self, artifact: PreparedTrial, bundle: PreparedResourceBundle
    ) -> None:
        variants: dict[tuple[str, str], VideoSettings] = {}
        for epoch in artifact.epochs:
            for setting in epoch.settings:
                if isinstance(setting, VideoSettings):
                    if isinstance(setting.asset_id, str):
                        variants.setdefault(
                            (setting.instance_id, setting.asset_id), setting
                        )
        assets = bundle.asset_set.by_id()
        by_instance: dict[str, list[str]] = {}
        for (instance_id, asset_id), setting in variants.items():
            asset = assets.get(asset_id)
            index = bundle.prepared_content.get(asset_id)
            if asset is None or not isinstance(index, VideoIndex):
                raise ValueError(
                    f"video instance {instance_id} lacks prepared source/index"
                )
            self.budget.reserve(
                owner=(
                    f"visual_stimulus:{artifact.identity.trial_id}:video-texture:"
                    f"{instance_id}:{asset_id}"
                ),
                cpu_bytes=0,
                gpu_bytes=index.width
                * index.height
                * 16
                * len(artifact.display.active_outputs),
            )
            playback_id = _playback_id(
                artifact.identity.trial_id, instance_id, asset_id
            )
            self.playback.register(
                instance_id=playback_id,
                evidence_instance_id=instance_id,
                asset_id=asset_id,
                profile=asset.profile,
                source=asset.source,
                index=index,
                prepared_generation=artifact.identity.prepared_generation,
                end_behavior=setting.end_behavior,
                initial_ns=setting.initial_playback.ns(),
            )
            by_instance.setdefault(instance_id, []).append(playback_id)
        for instance_id, playback_ids in by_instance.items():
            self._variants[(artifact.identity.trial_id, instance_id)] = tuple(
                playback_ids
            )

    def present(
        self,
        trial_id: str,
        setting: VideoSettings,
        values: dict[str, float | int | str | bool],
    ) -> VideoPresentation:
        try:
            position = values["playback"]
        except KeyError as exc:
            raise VideoPlaybackError(
                "video instance has no prepared playback position"
            ) from exc
        if type(position) not in (int, float):
            raise VideoPlaybackError("video playback position is not numeric")
        if not isinstance(setting.asset_id, str):
            raise VideoPlaybackError("video instance has an unresolved asset reference")
        return self.playback.present(
            _playback_id(trial_id, setting.instance_id, setting.asset_id),
            Fraction.from_float(float(position)),
            end_behavior=setting.end_behavior,
        )

    def reset(self, trial_id: str, instance_id: str) -> int:
        generations = tuple(
            self.playback.reset(playback_id)
            for playback_id in self._variants.get((trial_id, instance_id), ())
        )
        return max(generations, default=0)


def _playback_id(trial_id: str, instance_id: str, asset_id: str) -> str:
    """Encode the variant identity without interpreting opaque authored IDs."""
    return json.dumps((trial_id, instance_id, asset_id), separators=(",", ":"))
