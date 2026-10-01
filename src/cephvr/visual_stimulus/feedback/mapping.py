"""Apply prepared feedback mappings to renderer-owned instance state (V24–V27)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from cephvr.visual_stimulus.config.models.program_model import (
    ArenaSettings,
    Feedback,
    PlanarFeedback,
    Program,
)
from cephvr.visual_stimulus.feedback.arena import (
    inset_convex_polygon,
    slide_displacement,
)
from cephvr.visual_stimulus.rendering.motion import evaluate_function


class FeedbackMappingError(ValueError):
    """A prepared feedback mapping cannot be applied to the current state."""


@dataclass(frozen=True, slots=True)
class FeedbackContribution:
    binding_id: str
    requested_increment: tuple[float, ...]
    applied_increment: tuple[float, ...]
    target_units: tuple[str, ...]
    target_frame_id: str | None
    constraint_occurred: bool = False


class FeedbackMappingApplier:
    """Render-thread adapter from one finite batch to stable instance state records.

    The caller supplies the active epoch and local application time on every batch;
    mappings never retain an epoch, scene, or runtime reference between updates.
    """

    def __init__(self, program: Program, *, arena_boundaries: Any) -> None:
        self._program = program
        self._channels = {
            channel.channel_id: channel for channel in program.input_channels
        }
        self._boundaries = {
            item.instance_id: item for item in arena_boundaries.bindings
        }

    def binding_ids(self, epoch: Any, stream_id: str) -> tuple[str, ...]:
        """Return active bindings fed by a stream, including rejected batches."""
        stream_channels = {
            channel.channel_id
            for channel in self._program.input_channels
            if channel.stream_id == stream_id
        }
        return tuple(
            binding.binding_id
            for setting in epoch.settings
            for binding in setting.feedback
            if stream_channels.intersection(binding.channel_ids())
        )

    def __call__(
        self,
        batch: tuple[Any, ...],
        trial_state: Any,
        epoch: Any,
        now_ns: int,
        epoch_start_ns: int,
    ) -> tuple[FeedbackContribution, ...]:
        contributions: list[FeedbackContribution] = []
        for result in batch:
            values = dict(result.values)
            if len(values) != len(result.values):
                raise FeedbackMappingError(
                    "feedback result contains duplicate channels"
                )
            if any(
                channel_id not in self._channels
                or self._channels[channel_id].stream_id != result.stream_id
                for channel_id in values
            ):
                raise FeedbackMappingError(
                    "feedback result contains an undeclared channel or wrong stream"
                )
            interval = _interval_seconds(result)
            local_ns = max(0, now_ns - epoch_start_ns)
            # Ordinary mapped increments are applied before the planar mapping so a
            # declared yaw channel determines the interval's midpoint heading.
            for setting in epoch.settings:
                for candidate in setting.feedback:
                    if not isinstance(candidate, Feedback):
                        continue
                    contribution = self._apply_binding(
                        setting.instance_id,
                        candidate,
                        values,
                        trial_state,
                        stream_id=result.stream_id,
                        local_ns=local_ns,
                        interval=interval,
                        now_ns=now_ns,
                    )
                    if contribution is not None:
                        contributions.append(contribution)

            for setting in epoch.settings:
                if not isinstance(setting, ArenaSettings):
                    continue
                for binding in setting.feedback:
                    if isinstance(binding, PlanarFeedback):
                        contribution = self._apply_planar(
                            setting.instance_id,
                            binding,
                            setting.feedback,
                            values,
                            trial_state,
                            local_ns=local_ns,
                            interval=interval,
                            now_ns=now_ns,
                            stream_id=result.stream_id,
                            target_frame_id=setting.world_frame_id,
                        )
                        if contribution is not None:
                            contributions.append(contribution)
        return tuple(contributions)

    def _apply_binding(
        self,
        instance_id: str,
        binding: Feedback,
        values: dict[str, float],
        trial_state: Any,
        *,
        stream_id: str,
        local_ns: int,
        interval: float | None,
        now_ns: int,
    ) -> FeedbackContribution | None:
        if binding.source_channel not in values:
            return None
        channel = self._channels[binding.source_channel]
        if channel.stream_id != stream_id:
            raise FeedbackMappingError(
                "feedback result stream differs from its prepared channel"
            )
        value = values[binding.source_channel]
        gain = _evaluate(binding.gain, local_ns)
        offset = _evaluate(binding.offset, local_ns)
        if binding.operation == "direct_value":
            if channel.value_kind != "absolute":
                raise FeedbackMappingError(
                    "direct assignment requires an absolute channel"
                )
            applied = gain * value + offset
        else:
            if channel.value_kind not in ("displacement", "interval_average_rate"):
                raise FeedbackMappingError(
                    "movement integration requires displacement or rate"
                )
            if interval is None:
                raise FeedbackMappingError(
                    "movement feedback requires a valid source interval"
                )
            applied = gain * value
            if channel.value_kind == "interval_average_rate":
                applied = (applied + offset) * interval
            else:
                applied += offset * interval
        instance = trial_state.instances.get(instance_id)
        if instance is None or not instance.active:
            return None
        instance.apply_feedback(
            binding.target, binding.operation, applied, now_ns=now_ns
        )
        return FeedbackContribution(
            binding.binding_id,
            (applied,),
            (applied,),
            (str(channel.unit),),
            channel.frame_id,
        )

    def _apply_planar(
        self,
        instance_id: str,
        binding: PlanarFeedback,
        bindings: tuple[Any, ...],
        values: dict[str, float],
        trial_state: Any,
        *,
        local_ns: int,
        interval: float | None,
        now_ns: int,
        stream_id: str,
        target_frame_id: str,
    ) -> FeedbackContribution | None:
        if interval is None:
            raise FeedbackMappingError(
                "planar feedback requires a valid source interval"
            )
        if (
            binding.forward_channel not in values
            or binding.sideways_channel not in values
        ):
            return None
        if (
            self._channels[binding.forward_channel].stream_id != stream_id
            or self._channels[binding.sideways_channel].stream_id != stream_id
        ):
            raise FeedbackMappingError(
                "planar pair is not from the result's prepared stream"
            )
        instance = trial_state.instances.get(instance_id)
        if instance is None or not instance.active:
            return None
        boundary = self._boundaries.get(instance_id)
        region = boundary.region if boundary is not None else None
        if region is None or region.kind != "convex_polygon_xy":
            raise FeedbackMappingError(
                "planar feedback requires a prepared convex arena boundary"
            )

        # Advance programmed yaw once to application time before measuring the
        # feedback turn increment used for midpoint-heading integration.
        instance.advance(now_ns)
        yaw_bindings = [
            item
            for item in bindings
            if isinstance(item, Feedback)
            and item.target == "yaw"
            and item.source_channel in values
        ]
        dyaw = 0.0
        for turn in yaw_bindings:
            channel = self._channels[turn.source_channel]
            sample = values[turn.source_channel]
            gain = _evaluate(turn.gain, local_ns)
            offset = _evaluate(turn.offset, local_ns)
            if channel.value_kind == "interval_average_rate":
                dyaw += (gain * sample + offset) * interval
            elif channel.value_kind == "displacement":
                dyaw += gain * sample + offset * interval
        yaw_after = instance.values["yaw"].value
        yaw_before = yaw_after - dyaw
        yaw_mid = math.radians(yaw_before + dyaw / 2)
        forward = values[binding.forward_channel]
        sideways = values[binding.sideways_channel]
        scale = _evaluate(binding.gain, local_ns) * interval
        dx = scale * (-math.sin(yaw_mid) * forward - math.cos(yaw_mid) * sideways)
        dy = scale * (math.cos(yaw_mid) * forward - math.sin(yaw_mid) * sideways)
        current = (instance.values["x"].value, instance.values["y"].value)
        walls = inset_convex_polygon(region.vertices_mm, region.margin_mm)
        position, actual, constrained = slide_displacement(
            current, (dx, dy), walls, tolerance=1e-7
        )
        instance.apply_feedback(
            "x", "movement_integration", position[0] - current[0], now_ns=now_ns
        )
        instance.apply_feedback(
            "y", "movement_integration", position[1] - current[1], now_ns=now_ns
        )
        return FeedbackContribution(
            binding.binding_id,
            (dx, dy),
            actual,
            ("mm", "mm"),
            target_frame_id,
            constrained,
        )


def _interval_seconds(result: Any) -> float | None:
    start = getattr(result, "source_interval_start_ns", None)
    end = getattr(result, "source_interval_end_ns", None)
    if start is None and end is None:
        return None
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise FeedbackMappingError(
            "feedback interval must be a positive half-open interval"
        )
    return (end - start) / 1_000_000_000


def _evaluate(function: Any, local_ns: int) -> float:
    result = float(evaluate_function(function, local_ns))
    if not math.isfinite(result):
        raise FeedbackMappingError("prepared feedback function evaluated non-finitely")
    return result
