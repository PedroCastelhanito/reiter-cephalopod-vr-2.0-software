"""V15/V19/V20/V22/V23 canonical display declaration; no file/device/GPU I/O.

Generate display-profile.schema.json from DisplayProfile. Asset contents, actual
framebuffer capabilities and measured calibration remain preparation obligations.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from .schema_common import (
    DeviceIdentity,
    FrameId,
    Model,
    Name,
    NonnegativeInt,
    OutputId,
    PositiveInt,
    RGBBits,
    SurfaceId,
    Vec3,
    Version1,
    parse_json,
    portable_path,
)

Positive = Annotated[float, Field(gt=0)]


class AssetRef(Model):
    logical_path: Annotated[str, Field(min_length=1)]

    @field_validator("logical_path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        return portable_path(value)


class PixelRect(Model):
    x: NonnegativeInt  # Bottom-left output coordinates.
    y: NonnegativeInt
    width: PositiveInt
    height: PositiveInt


class Surface(Model):
    surface_id: SurfaceId
    bottom_left_mm: Vec3
    bottom_right_mm: Vec3
    top_right_mm: Vec3
    top_left_mm: Vec3


class Geometry(Model):
    frame_id: FrameId
    observer_mm: Vec3
    near_mm: Positive
    far_mm: Positive
    positional_tolerance_mm: Positive
    orthogonality_tolerance: Annotated[float, Field(gt=0, lt=1)]
    surfaces: Annotated[tuple[Surface, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def geometry_rules(self) -> Self:
        if self.near_mm >= self.far_mm:
            raise ValueError("near_mm must be less than far_mm")
        if {s.surface_id for s in self.surfaces} != {
            "front",
            "left",
            "right",
            "bottom",
        }:
            raise ValueError("exactly one of each required surface is needed")

        def sub(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
            return tuple(x - y for x, y in zip(a, b, strict=True))

        def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
            return sum(x * y for x, y in zip(a, b, strict=True))

        def cross(
            a: tuple[float, ...], b: tuple[float, ...]
        ) -> tuple[float, float, float]:
            return (
                a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0],
            )

        for s in self.surfaces:
            right = sub(s.bottom_right_mm, s.bottom_left_mm)
            up = sub(s.top_left_mm, s.bottom_left_mm)
            lr, lu = math.hypot(*right), math.hypot(*up)
            if (
                not math.isfinite(lr + lu)
                or min(lr, lu) <= self.positional_tolerance_mm
            ):
                raise ValueError(
                    f"{s.surface_id}: degenerate or unrepresentable surface extent"
                )
            r, u = tuple(x / lr for x in right), tuple(x / lu for x in up)
            if abs(dot(r, u)) > self.orthogonality_tolerance:
                raise ValueError(f"{s.surface_id}: nonorthogonal surface axes")
            expected = tuple(
                a + b + c for a, b, c in zip(s.bottom_left_mm, right, up, strict=True)
            )
            closure = math.hypot(*sub(s.top_right_mm, expected))
            if not math.isfinite(closure) or closure > self.positional_tolerance_mm:
                raise ValueError(
                    f"{s.surface_id}: fourth corner does not close rectangle"
                )
            normal = cross(r, u)
            distance = dot(sub(self.observer_mm, s.bottom_left_mm), normal)
            if not math.isfinite(distance) or distance <= self.positional_tolerance_mm:
                raise ValueError(f"{s.surface_id}: observer must be on the front side")
        return self


class Output(Model):
    enabled: bool = True
    output_id: OutputId
    device_identity: (
        DeviceIdentity  # Stable installation identity, never monitor array index.
    )
    width_px: PositiveInt
    height_px: PositiveInt
    refresh_numerator: PositiveInt
    refresh_denominator: PositiveInt
    rgb_bits_per_channel: RGBBits
    photometric_profile: AssetRef | None = None


class Mapping(Model):
    mapping_id: Name
    surface_id: SurfaceId
    output_id: OutputId
    viewport: PixelRect
    geometric_profile: AssetRef
    # Mask, weights, orientation and declared coverage live in that one profile.


class PhotodiodePatch(Model):
    rect: PixelRect
    high_linear_rgb: Vec3
    low_linear_rgb: Vec3

    @model_validator(mode="after")
    def distinct_levels(self) -> Self:
        if self.high_linear_rgb == self.low_linear_rgb:
            raise ValueError(
                "photodiode levels must differ; prepared codes must also differ"
            )
        return self


class DisplayProfile(Model):
    format_version: Version1
    geometry: Geometry
    outputs: Annotated[tuple[Output, ...], Field(min_length=1)]
    mappings: Annotated[tuple[Mapping, ...], Field(min_length=4)]
    # V20: new profiles default to mixed pacing; saved explicit selections are preserved.
    presentation_mode: Literal["all_outputs_vsync", "photodiode_only_vsync"] = (
        "photodiode_only_vsync"
    )
    photometric_mode: Literal["calibrated", "uncalibrated"]
    idle_linear_rgb: Vec3
    photodiode_enabled: bool = True
    pacing_output_id: OutputId | None = None
    photodiode_output_id: OutputId | None = None
    photodiode_patch: PhotodiodePatch | None = None

    @property
    def selected_pacing_output_id(self) -> str | None:
        # Legacy profiles coupled timing and marker placement; explicit pacing wins.
        return self.pacing_output_id or (
            self.photodiode_output_id if self.photodiode_enabled else None
        )

    @property
    def marker_output_id(self) -> str | None:
        return self.photodiode_output_id if self.photodiode_enabled else None

    @property
    def active_outputs(self) -> tuple[Output, ...]:
        return tuple(output for output in self.outputs if output.enabled)

    @property
    def active_mappings(self) -> tuple[Mapping, ...]:
        active = {output.output_id for output in self.active_outputs}
        return tuple(
            mapping for mapping in self.mappings if mapping.output_id in active
        )

    def review_refresh_rate(self) -> tuple[int, int]:
        """Use a designated rate or the common all-output VSync rate without guessing a face."""
        selected = self.selected_pacing_output_id
        outputs = tuple(
            output
            for output in self.active_outputs
            if selected is None or output.output_id == selected
        )
        if not outputs or (
            selected is None and self.presentation_mode != "all_outputs_vsync"
        ):
            raise ValueError(
                "review recording requires a pacing output or all-output VSync"
            )
        rates = {
            Fraction(output.refresh_numerator, output.refresh_denominator)
            for output in outputs
        }
        if len(rates) != 1:
            raise ValueError(
                "review recording without a pacer requires a common nominal output refresh rate"
            )
        rate = rates.pop()
        return rate.numerator, rate.denominator

    @model_validator(mode="after")
    def references(self) -> Self:
        for label, values in [
            ("output IDs", [x.output_id for x in self.outputs]),
            ("devices", [x.device_identity for x in self.outputs]),
            ("mapping IDs", [x.mapping_id for x in self.mappings]),
        ]:
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label}")
        outputs = {x.output_id: x for x in self.outputs}
        if not self.active_outputs:
            raise ValueError("at least one display output must be enabled")
        if (
            self.photodiode_enabled
            and self.photodiode_output_id in outputs
            and not outputs[self.photodiode_output_id].enabled
        ):
            raise ValueError("the designated photodiode output must be enabled")
        if {m.surface_id for m in self.mappings} != {
            "front",
            "left",
            "right",
            "bottom",
        }:
            raise ValueError("mappings must cover every required surface")
        if {m.output_id for m in self.mappings} != set(outputs):
            raise ValueError(
                "each output needs mappings; mapping output IDs must exist"
            )
        for m in self.mappings:
            self._check_rect(m.viewport, outputs[m.output_id])
        if self.photometric_mode == "calibrated" and any(
            o.photometric_profile is None for o in self.outputs
        ):
            raise ValueError("calibrated mode requires a profile for every output")
        if (
            self.photodiode_enabled
            and self.photodiode_output_id is not None
            and self.photodiode_output_id not in outputs
        ):
            raise ValueError("unknown photodiode output")
        if (
            self.presentation_mode == "photodiode_only_vsync"
            and self.selected_pacing_output_id is None
        ):
            raise ValueError("mixed pacing requires an explicit pacing output")
        pacing = self.selected_pacing_output_id
        if pacing is not None and (
            pacing not in outputs or not outputs[pacing].enabled
        ):
            raise ValueError("the pacing output must exist and be enabled")
        if self.photodiode_enabled and self.photodiode_patch is not None:
            if self.photodiode_output_id is None:
                raise ValueError("patch requires an explicit output")
            self._check_rect(
                self.photodiode_patch.rect, outputs[self.photodiode_output_id]
            )
        return self

    @staticmethod
    def _check_rect(rect: PixelRect, output: Output) -> None:
        if (
            rect.x + rect.width > output.width_px
            or rect.y + rect.height > output.height_px
        ):
            raise ValueError(f"rectangle exceeds output {output.output_id}")

    def require_trial_marker(self) -> None:
        """Setup-only requirement; startup Idle never needs a flashing patch."""
        if (
            self.presentation_mode != "all_outputs_vsync"
            and self.selected_pacing_output_id is None
        ):
            raise ValueError("trial Setup requires an explicit pacing output")
        if self.photodiode_enabled and (
            self.photodiode_output_id is None or self.photodiode_patch is None
        ):
            raise ValueError("trial Setup requires the photodiode output and patch")


def parse_display_json(source: str, *, max_bytes: int) -> DisplayProfile:
    return parse_json(DisplayProfile, source, max_bytes=max_bytes, max_depth=32)
