"""Canonical V23 profile declaration and pure validation; no I/O or GPU runtime.

Generate photometric-profile.schema.json from PhotometricProfile.model_json_schema.
JSON Schema is generated structure; model validators additionally enforce cross-field
rules. Actual output compatibility/measurements remain preparation/rig obligations.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .schema_common import (
    DeviceIdentity,
    OutputId,
    PositiveInt,
    UnitValue,
    Version1,
    parse_json,
)
from .schema_common import Model as ProfileModel
from .schema_common import NonEmpty as Name

Curve = Annotated[tuple[UnitValue, ...], Field(min_length=2)]


class OperatingCondition(ProfileModel):
    name: Name
    value: Name


class OutputBinding(ProfileModel):
    output_id: OutputId
    device_identity: DeviceIdentity
    width_px: PositiveInt
    height_px: PositiveInt
    refresh_numerator: PositiveInt
    refresh_denominator: PositiveInt
    rgb_bits: tuple[PositiveInt, PositiveInt, PositiveInt]
    signal_encoding: Literal["full_range_rgb_device_codes"]
    # Required operating-condition names are those declared here: non-empty, unique.
    conditions: Annotated[tuple[OperatingCondition, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_conditions(self) -> Self:
        if self.rgb_bits not in ((8, 8, 8), (10, 10, 10)):
            raise ValueError("output RGB bits must be uniformly 8 or uniformly 10")
        names = [c.name for c in self.conditions]
        if len(set(names)) != len(names):
            raise ValueError("operating-condition names must be unique")
        return self


class MeasurementProvenance(ProfileModel):
    measurement_id: Name
    measured_at: Name  # UTC ISO-8601 Z string; checked without coercing to local time.
    method: Name
    instrument: Name
    reference: Name  # Provenance reference; not an instruction to open a file/URL.

    @model_validator(mode="after")
    def utc_measurement_time(self) -> Self:
        from datetime import datetime

        if not self.measured_at.endswith("Z") or "T" not in self.measured_at:
            raise ValueError("measured_at must be a UTC ISO-8601 timestamp ending in Z")
        datetime.fromisoformat(self.measured_at[:-1] + "+00:00")
        return self


class PhotometricProfile(ProfileModel):
    format_version: Version1
    profile_id: Name
    model: Literal["per_channel_measured_inverse_lut_v1"]
    working_space: Literal["linear_rec709_d65_relative"]
    normalization: Literal["per_channel_measured_black_to_white"]
    interpolation: Literal["piecewise_linear_uniform_input_grid"]
    output: OutputBinding
    measurement: MeasurementProvenance
    red: Curve
    green: Curve
    blue: Curve

    @model_validator(mode="after")
    def curve_rules(self) -> Self:
        if len({len(self.red), len(self.green), len(self.blue)}) != 1:
            raise ValueError("RGB tables must have equal sample counts")
        for name in ("red", "green", "blue"):
            values = getattr(self, name)
            if any(a > b for a, b in pairwise(values)):
                raise ValueError(f"{name} table must be nondecreasing")
            if values[-1] <= values[0]:
                raise ValueError(f"{name} table must have nonzero usable range")
        return self


def parse_profile_json(source: str, *, max_bytes: int) -> PhotometricProfile:
    return parse_json(PhotometricProfile, source, max_bytes=max_bytes, max_depth=32)
