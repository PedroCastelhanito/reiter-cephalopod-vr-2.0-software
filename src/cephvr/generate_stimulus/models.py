"""Editable static arena documents, independent of widgets and rendering."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0, le=1e6)]
Unit = Annotated[float, Field(ge=0, le=1)]
Seed = Annotated[int, Field(ge=0, le=2**64 - 1, strict=True)]
SURFACES = ("floor", "roof", "wall_n", "wall_s", "wall_e", "wall_w")


class DesignModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Relief(DesignModel):
    pattern: Literal["none", "rock", "ridges", "waves"] = "none"
    height_mm: Annotated[float, Field(ge=0, le=10000)] = 0
    scale_mm: Positive = 20
    seed: Seed = 0


class Scatter(DesignModel):
    model: str
    density_per_cm2: Annotated[float, Field(ge=0, le=100)] = 0.01
    clustering: Unit = 0
    min_scale: Positive = 1
    max_scale: Positive = 1
    seed: Seed = 0

    @model_validator(mode="after")
    def scale_order(self) -> Self:
        if self.min_scale > self.max_scale:
            raise ValueError("Minimum scale must not exceed maximum scale")
        return self


class Surface(DesignModel):
    visible: bool = True
    color: tuple[Unit, Unit, Unit, Unit] = (0.5, 0.5, 0.5, 1)
    alpha_mode: Literal["OPAQUE", "MASK"] = "OPAQUE"
    alpha_cutoff: Unit = 0.5
    texture: str = ""
    texture_scale_mm: Positive = 100
    relief: Relief = Field(default_factory=Relief)
    scatters: list[Scatter] = Field(default_factory=list, max_length=16)


class ArenaDesign(DesignModel):
    format_version: Literal[1] = 1
    kind: Literal["arena_design"] = "arena_design"
    shape: Literal["rectangular", "circular", "torus", "two_choice", "cross"] = (
        "rectangular"
    )
    width_mm: Positive = 500
    depth_mm: Positive = 500
    height_mm: Positive = 100
    corridor_mm: Positive = 100
    segments: Annotated[int, Field(ge=8, le=256)] = 48
    subdivisions: Annotated[int, Field(ge=1, le=128)] = 12
    surfaces: dict[str, Surface] = Field(
        default_factory=lambda: {
            "floor": Surface(),
            "roof": Surface(visible=False),
            **{name: Surface() for name in SURFACES[2:]},
        }
    )

    @model_validator(mode="after")
    def geometry_rules(self) -> Self:
        if set(self.surfaces) != set(SURFACES):
            raise ValueError(
                "Arena requires floor, roof and four directional wall groups"
            )
        if self.shape in {"torus", "cross", "two_choice"} and self.corridor_mm >= min(
            self.width_mm, self.depth_mm
        ):
            raise ValueError(
                "Corridor width must be smaller than arena width and depth"
            )
        if (
            self.shape == "torus"
            and self.corridor_mm >= min(self.width_mm, self.depth_mm) / 2
        ):
            raise ValueError("Torus corridor must be smaller than its outer radius")
        return self
