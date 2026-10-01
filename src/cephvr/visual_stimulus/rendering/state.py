"""Prepared boundary execution and trial-local instance state continuity."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cephvr.visual_stimulus.rendering.motion import (
    evaluate_function,
    integrate_function,
)


def _literal(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError("prepared state value must be a finite literal")
    return float(value)


def _motion_for(settings: Any) -> dict[str, Any]:
    motion = settings.motion
    if settings.kind == "arena":
        return {"x": motion.x, "y": motion.y, "yaw": motion.yaw}
    values = {"x": motion.x, "y": motion.y, "rotation": motion.rotation}
    if settings.kind == "texture":
        values.update(phase_x=settings.phase_x, phase_y=settings.phase_y)
    if settings.kind == "video":
        values["playback"] = None
    return values


def _initial_values(settings: Any) -> dict[str, float]:
    if settings.kind == "arena":
        return {
            "x": _literal(settings.initial.position_mm[0]),
            "y": _literal(settings.initial.position_mm[1]),
            "yaw": _literal(settings.initial.yaw_deg),
        }
    result = {
        "x": _literal(settings.initial.x),
        "y": _literal(settings.initial.y),
        "rotation": _literal(settings.initial.rotation_deg),
    }
    if settings.kind == "texture":
        result.update(
            phase_x=_literal(settings.initial_phase_x_cycles),
            phase_y=_literal(settings.initial_phase_y_cycles),
        )
    if settings.kind == "video":
        result["playback"] = settings.initial_playback.ns() / 1e9
    return result


@dataclass(slots=True)
class StateField:
    value: float
    mode: str
    function: Any | None
    epoch_start_ns: int
    anchor_ns: int
    active: bool = True

    def advance(self, now_ns: int) -> float:
        if not self.active or self.function is None or self.mode == "hold":
            self.anchor_ns = now_ns
            return self.value
        from_local = max(0, self.anchor_ns - self.epoch_start_ns)
        to_local = max(0, now_ns - self.epoch_start_ns)
        if self.mode == "rate":
            self.value += integrate_function(self.function, from_local, to_local)
        elif self.mode == "trajectory":
            self.value = evaluate_function(self.function, to_local)
        else:
            raise ValueError(f"unknown state motion mode {self.mode!r}")
        self.anchor_ns = now_ns
        return self.value

    def bind(self, motion: Any, *, epoch_start_ns: int, now_ns: int) -> None:
        if motion is None:
            self.mode, self.function = "hold", None
        else:
            self.mode = motion.kind
            self.function = getattr(motion, "function", None)
        self.epoch_start_ns = epoch_start_ns
        self.anchor_ns = now_ns
        self.active = True
        if self.mode == "trajectory" and self.function is not None:
            self.value = evaluate_function(
                self.function, max(0, now_ns - epoch_start_ns)
            )


@dataclass(slots=True)
class InstanceState:
    instance_id: str
    family: str
    values: dict[str, StateField]
    active: bool
    settings: Any
    last_epoch_start_ns: int
    appearance_overrides: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def _appearance(
        settings: Any, *, now_ns: int, epoch_start_ns: int
    ) -> dict[str, float]:
        if settings.kind == "arena":
            return {}
        local_ns = max(0, now_ns - epoch_start_ns)
        result = {
            name: evaluate_function(getattr(settings, name), local_ns)
            for name in ("width", "height", "opacity")
        }
        if settings.kind == "texture":
            result["contrast"] = evaluate_function(settings.contrast, local_ns)
            if settings.pattern.kind in ("sine_grating", "square_grating"):
                result["frequency"] = evaluate_function(
                    settings.pattern.frequency, local_ns
                )
            elif settings.pattern.kind == "checkerboard":
                result["frequency_x"] = evaluate_function(
                    settings.pattern.frequency_x, local_ns
                )
                result["frequency_y"] = evaluate_function(
                    settings.pattern.frequency_y, local_ns
                )
            else:
                result["period_x"] = evaluate_function(
                    settings.pattern.period_x, local_ns
                )
                result["period_y"] = evaluate_function(
                    settings.pattern.period_y, local_ns
                )
        return result

    @classmethod
    def initialize(
        cls, settings: Any, *, now_ns: int, epoch_start_ns: int
    ) -> InstanceState:
        motions = _motion_for(settings)
        values = {}
        for name, value in _initial_values(settings).items():
            item = StateField(value, "hold", None, epoch_start_ns, now_ns)
            item.bind(motions.get(name), epoch_start_ns=epoch_start_ns, now_ns=now_ns)
            values[name] = item
        return cls(
            settings.instance_id, settings.kind, values, True, settings, epoch_start_ns
        )

    def advance(self, now_ns: int) -> None:
        if self.active:
            for item in self.values.values():
                item.advance(now_ns)

    def transition(
        self, settings: Any, *, action: str, epoch_start_ns: int, now_ns: int
    ) -> None:
        if (
            action in ("initialize", "reset", "restart_incompatible")
            or settings is None
        ):
            if settings is None:
                self.active = False
                return
            fresh = InstanceState.initialize(
                settings, now_ns=now_ns, epoch_start_ns=epoch_start_ns
            )
            self.values, self.family, self.settings = (
                fresh.values,
                fresh.family,
                settings,
            )
            self.appearance_overrides.clear()
            self.active, self.last_epoch_start_ns = True, epoch_start_ns
            return
        if action == "pause":
            self.advance(now_ns)
            self.active = False
            for state_field in self.values.values():
                state_field.active = False
            return
        self.advance(now_ns)
        new_motion = _motion_for(settings)
        initial = _initial_values(settings)
        for name, value in initial.items():
            current = self.values.get(name)
            if current is None:
                current = StateField(value, "hold", None, epoch_start_ns, now_ns)
                self.values[name] = current
            # A compatible return re-anchors: absent time never advances motion.
            current.value = value if action == "reset" else current.value
            current.bind(
                new_motion.get(name), epoch_start_ns=epoch_start_ns, now_ns=now_ns
            )
        self.settings = settings
        allowed_appearance = self._appearance(
            settings, now_ns=now_ns, epoch_start_ns=epoch_start_ns
        )
        self.appearance_overrides = {
            name: value
            for name, value in self.appearance_overrides.items()
            if name in allowed_appearance
        }
        self.active = True
        self.last_epoch_start_ns = epoch_start_ns

    def apply_increment(self, target: str, amount: float, *, now_ns: int) -> None:
        if not self.active or target not in self.values or not math.isfinite(amount):
            raise ValueError("active target and finite increment are required")
        field = self.values[target]
        field.advance(now_ns)
        field.value += amount
        field.anchor_ns = now_ns

    def apply_feedback(
        self,
        target: str,
        operation: str,
        value: float,
        *,
        now_ns: int,
    ) -> None:
        """Apply one already-converted prepared feedback assignment or increment."""
        if not math.isfinite(value):
            raise ValueError("feedback value must be finite")
        if operation == "movement_integration":
            self.apply_increment(target, value, now_ns=now_ns)
            return
        if operation != "direct_value":
            raise ValueError(f"unsupported prepared feedback operation {operation!r}")
        if target in self.values:
            field = self.values[target]
            field.advance(now_ns)
            field.value = value
            field.anchor_ns = now_ns
            return
        allowed = self._appearance(
            self.settings, now_ns=now_ns, epoch_start_ns=self.last_epoch_start_ns
        )
        if target not in allowed:
            raise ValueError(
                f"feedback target {target!r} is not active for {self.instance_id}"
            )
        self.appearance_overrides[target] = value

    def snapshot(
        self, *, now_ns: int, epoch_start_ns: int
    ) -> tuple[tuple[str, float], ...]:
        values = {name: field.advance(now_ns) for name, field in self.values.items()}
        values.update(
            self._appearance(
                self.settings, now_ns=now_ns, epoch_start_ns=epoch_start_ns
            )
        )
        values.update(self.appearance_overrides)
        return tuple(sorted(values.items()))


@dataclass(slots=True)
class TrialState:
    instances: dict[str, InstanceState] = field(default_factory=dict)
    boundary_cursor: int = 0
    epoch_index: int = 0

    def start(self) -> None:
        self.instances.clear()
        self.boundary_cursor = 0
        self.epoch_index = 0
