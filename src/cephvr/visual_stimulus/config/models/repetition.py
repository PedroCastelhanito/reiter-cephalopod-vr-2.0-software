"""Compact, reproducible numeric and asset rules resolved before rendering."""

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..random_grid import random_values
from .schema_common import Model, ProgramId


class RepetitionRule(Model):
    kind: Literal["uniform_grid_v1"] = "uniform_grid_v1"
    rig_coordinates: bool = False
    rig_angle_version: Literal[1, 2] = 1
    instance_id: ProgramId
    parameter: Literal[
        "Speed",
        "Direction",
        "Orientation",
        "Angular speed",
        "Start size",
        "End size",
        "Growth duration",
        "Playback start",
        "Longitudinal",
        "Lateral",
        "Angular",
    ]
    minimum: Annotated[str, Field(max_length=64)]
    maximum: Annotated[str, Field(max_length=64)]
    precision: Annotated[str, Field(max_length=64)]
    seed: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    stream: Annotated[str, Field(max_length=128)] = ""
    offset: Annotated[int, Field(ge=0)] = 0
    stride: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def grid(self) -> Self:
        random_values(self.minimum, self.maximum, self.precision, "1", lambda _: 0)
        low = Decimal(self.minimum)
        if self.parameter in ("Speed", "Playback start") and low < 0:
            raise ValueError("Speed and playback start ranges must be nonnegative")
        if self.parameter in ("Start size", "End size", "Growth duration") and low <= 0:
            raise ValueError("Size and growth duration ranges must be positive")
        return self


class AssetRepetitionRule(Model):
    kind: Literal["uniform_asset_v1"] = "uniform_asset_v1"
    instance_id: ProgramId
    parameter: Literal["Asset"] = "Asset"
    asset_ids: Annotated[tuple[ProgramId, ...], Field(min_length=1, max_length=2000)]
    grating_periods_mm: Annotated[
        tuple[Annotated[float, Field(gt=0)], ...], Field(max_length=2000)
    ] = ()
    seed: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    stream: Annotated[str, Field(max_length=128)] = ""
    offset: Annotated[int, Field(ge=0)] = 0
    stride: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(self.asset_ids) != len(set(self.asset_ids)):
            raise ValueError("Asset choices must be distinct")
        if self.grating_periods_mm and len(self.grating_periods_mm) != len(
            self.asset_ids
        ):
            raise ValueError("Grating periods must match Asset choices")
        return self


# Untagged legacy numeric declarations retain their default kind.
Repetition = RepetitionRule | AssetRepetitionRule
