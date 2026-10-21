"""Non-executable subgroup editor metadata retained with canonical source epochs."""

from typing import Annotated, Literal

from pydantic import Field

from .schema_common import Model

Text = Annotated[str, Field(max_length=4096)]


class VariationDraft(Model):
    rig_coordinates: bool = False
    rig_angle_version: Literal[1, 2] = 1
    projector: Text
    projectors: tuple[Text, ...] = ()
    layer: Annotated[int, Field(ge=-1)]
    parameter: Text
    method: Annotated[int, Field(ge=0, le=2)]
    values: Text = ""
    minimum: Text = "0"
    maximum: Text = "100"
    precision: Text = "1"
    shared: bool = False
    seed: str = ""
    sample_key: tuple[Text, ...] = ()
    samples: Annotated[tuple[Text, ...], Field(max_length=32000)] = ()


class SubgroupDraft(Model):
    enabled: bool = False
    rules: Annotated[tuple[VariationDraft, ...], Field(max_length=64)] = ()
