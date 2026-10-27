"""Sparse-noise appearance shared by inline layers and imported recipes."""

from typing import Annotated, Literal

from pydantic import Field

from .schema_common import U64, Model, UnitValue, Version2


class SparseNoiseAppearance(Model):
    format_version: Version2
    kind: Literal["sparse_noise"]
    seed: U64
    square_size_mm: Annotated[float, Field(gt=0)]
    min_active_cell_distance_mm: Annotated[float, Field(ge=0)]
    active_probability: UnitValue
    background_linear: UnitValue
