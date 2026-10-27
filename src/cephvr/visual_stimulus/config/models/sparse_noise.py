"""Explicit scientific inputs for sparse-noise program preparation."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .program_model import Time
from .schema_common import (
    MINIMUM_TRIAL_DURATION_NS,
    U64,
    Model,
    PositiveInt,
    SurfaceId,
    UnitValue,
    Version1,
    parse_json,
)


class SparseNoiseRecipe(Model):
    format_version: Version1
    kind: Literal["sparse_noise"]
    seed: U64
    surfaces: Annotated[tuple[SurfaceId, ...], Field(min_length=1, max_length=4)]
    square_size_mm: Annotated[float, Field(gt=0)]
    active_density: UnitValue
    background_linear: UnitValue
    pattern_count: PositiveInt
    pattern_duration: Time

    @model_validator(mode="after")
    def sequence_rules(self) -> Self:
        if len(set(self.surfaces)) != len(self.surfaces):
            raise ValueError("sparse-noise surfaces must be distinct")
        total = self.pattern_count * self.pattern_duration.ns()
        if self.pattern_duration.ns() == 0:
            raise ValueError("sparse-noise pattern duration must be positive")
        if not MINIMUM_TRIAL_DURATION_NS <= total <= (1 << 63) - 1:
            raise ValueError("sparse-noise trial duration is outside E05/int64 bounds")
        return self


def parse_sparse_noise_json(source: str, *, max_bytes: int) -> SparseNoiseRecipe:
    return parse_json(SparseNoiseRecipe, source, max_bytes=max_bytes)
