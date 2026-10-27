"""Bounded output-space placement snapshots for sessionless diagnostics."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from .calibration_adjustments import CalibrationAdjustmentRejected
from .models.display_profile import (
    DisplayProfile,
    PhotodiodeMode,
    PhotodiodePatch,
    PixelRect,
)
from .models.schema_common import Model, OutputId, parse_json

PLACEMENT_VIEWS = frozenset({"photodiode_placement", "blackout_placement"})


class PlacementOutput(Model):
    output_id: OutputId
    blackout_zones: Annotated[tuple[PixelRect, ...], Field(max_length=256)] = ()


class CalibrationPlacement(Model):
    photodiode_mode: PhotodiodeMode = "landmarks"
    outputs: Annotated[tuple[PlacementOutput, ...], Field(min_length=1, max_length=4)]
    photodiode_output_id: OutputId | None = None
    photodiode_patch: PhotodiodePatch | None = None
    photodiode_patches: Annotated[
        dict[OutputId, PhotodiodePatch] | None, Field(max_length=4)
    ] = None

    @property
    def marker_patches(self) -> dict[str, PhotodiodePatch]:
        if self.photodiode_patches is not None:
            return self.photodiode_patches
        if self.photodiode_output_id is not None and self.photodiode_patch is not None:
            return {self.photodiode_output_id: self.photodiode_patch}
        return {}

    @model_validator(mode="after")
    def identities(self) -> Self:
        ids = [output.output_id for output in self.outputs]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate placement output")
        if (self.photodiode_output_id is None) != (self.photodiode_patch is None):
            raise ValueError("Placement pulse requires its output and rectangle")
        if (
            self.photodiode_output_id is not None
            and self.photodiode_output_id not in ids
        ):
            raise ValueError("Unknown placement pulse output")
        if (
            self.photodiode_patches is not None
            and self.photodiode_output_id is not None
        ):
            raise ValueError("Use either per-output pulses or a legacy single pulse")
        if not self.marker_patches.keys() <= set(ids):
            raise ValueError("Unknown placement pulse output")
        return self

    def validate_display(
        self, display: DisplayProfile, *, allow_empty_pulse: bool = False
    ) -> None:
        self.validate_view(
            display.calibration_view, allow_empty_pulse=allow_empty_pulse
        )
        outputs = {output.output_id: output for output in display.active_outputs}
        if {output.output_id for output in self.outputs} != set(outputs):
            raise CalibrationAdjustmentRejected(
                "Placement outputs differ from active diagnostic"
            )
        try:
            for output in self.outputs:
                for rect in output.blackout_zones:
                    display._check_rect(rect, outputs[output.output_id])
            for output_id, patch in self.marker_patches.items():
                pulse_output = outputs[output_id]
                display._check_rect(patch.rect, pulse_output)
                if patch.background_rect is not None:
                    display._check_rect(patch.background_rect, pulse_output)
        except ValueError as exc:
            raise CalibrationAdjustmentRejected(str(exc)) from exc

    def validate_view(self, view: str, *, allow_empty_pulse: bool = False) -> None:
        if (
            view == "photodiode_placement"
            and not self.marker_patches
            and not allow_empty_pulse
        ):
            raise CalibrationAdjustmentRejected(
                "Photodiode placement requires a pulse rectangle"
            )
        if view == "blackout_placement" and self.marker_patches:
            raise CalibrationAdjustmentRejected(
                "Blackout placement cannot change the photodiode"
            )

    @classmethod
    def from_display(cls, display: DisplayProfile) -> Self:
        return cls(
            outputs=tuple(
                PlacementOutput(output_id=o.output_id, blackout_zones=o.blackout_zones)
                for o in display.active_outputs
            ),
            photodiode_mode=display.photodiode_mode,
            photodiode_output_id=display.photodiode_output_id
            if display.photodiode_enabled
            else None,
            photodiode_patch=display.photodiode_patch
            if display.photodiode_enabled
            else None,
            photodiode_patches=display.photodiode_patches
            if display.photodiode_enabled
            else None,
        )


def parse_placement(value: str) -> CalibrationPlacement:
    if len(value.encode("utf-8")) > 65_536:
        raise CalibrationAdjustmentRejected("Placement update exceeds 64 KiB")
    try:
        return parse_json(CalibrationPlacement, value, max_bytes=65_536)
    except ValueError as exc:
        raise CalibrationAdjustmentRejected(str(exc)) from exc
