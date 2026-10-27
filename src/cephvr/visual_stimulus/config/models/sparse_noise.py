"""Explicit scientific inputs for sparse-noise program preparation."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from .program_model import Time
from .schema_common import (
    MINIMUM_TRIAL_DURATION_NS,
    PositiveInt,
    SurfaceId,
    parse_json,
)
from .sparse_noise_appearance import SparseNoiseAppearance as SparseNoiseAppearance


class SparseNoisePatternRecipe(SparseNoiseAppearance):
    surfaces: Annotated[tuple[SurfaceId, ...], Field(min_length=1, max_length=4)]
    pattern_count: PositiveInt
    pattern_duration: Time

    @model_validator(mode="after")
    def sequence_rules(self) -> Self:
        if len(set(self.surfaces)) != len(self.surfaces):
            raise ValueError("sparse-noise surfaces must be distinct")
        total = self.pattern_count * self.pattern_duration.ns()
        if self.pattern_duration.ns() == 0:
            raise ValueError("sparse-noise pattern duration must be positive")
        if not 0 < total <= (1 << 63) - 1:
            raise ValueError("sparse-noise trial duration is outside E05/int64 bounds")
        return self


class SparseNoiseRecipe(SparseNoisePatternRecipe):
    @model_validator(mode="after")
    def trial_duration(self) -> Self:
        if self.pattern_count * self.pattern_duration.ns() < MINIMUM_TRIAL_DURATION_NS:
            raise ValueError("sparse-noise trial duration is outside E05/int64 bounds")
        return self


def parse_sparse_noise_json(source: str, *, max_bytes: int) -> SparseNoiseRecipe:
    return parse_json(SparseNoiseRecipe, source, max_bytes=max_bytes)


def parse_sparse_noise_appearance(
    source: str, *, max_bytes: int
) -> SparseNoiseAppearance:
    """Accept appearance assets and validate full v2 recipes before stripping timing."""
    import json

    if len(source.encode("utf-8")) > max_bytes:
        raise ValueError("Sparse-noise document exceeds byte budget")
    data = json.loads(source)
    if isinstance(data, dict) and any(
        key in data for key in ("surfaces", "pattern_count", "pattern_duration")
    ):
        recipe = parse_sparse_noise_json(source, max_bytes=max_bytes)
        data = {key: getattr(recipe, key) for key in SparseNoiseAppearance.model_fields}
        return SparseNoiseAppearance.model_validate(data)
    return parse_json(SparseNoiseAppearance, source, max_bytes=max_bytes)
