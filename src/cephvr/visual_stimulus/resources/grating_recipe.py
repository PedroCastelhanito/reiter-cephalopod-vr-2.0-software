"""Interpret grating designs as one unrotated, physically sized repeat period."""

from dataclasses import replace
from math import isfinite

from cephvr.visual_stimulus.config.media_profiles import GRATING_PROFILE
from cephvr.visual_stimulus.resources.texture_recipe import TextureRecipe


def interpreted_recipe(recipe: TextureRecipe, profile: str) -> TextureRecipe:
    if profile != GRATING_PROFILE:
        return recipe
    if recipe.pattern != "grating":
        raise ValueError("Grating requires a Grating texture design (.json)")
    params = dict(recipe.params)
    if recipe.physical_field:
        params["orientation_deg"] = 0.0
        return replace(
            recipe,
            params=params,
            tile_width_mm=float(str(params.get("spatial_period_mm", 12))),
            tile_height_mm=float(str(params.get("spatial_period_mm", 12))),
        )
    if "spatial_period_mm" in params:
        period = float(str(params["spatial_period_mm"]))
    else:
        width = recipe.tile_width_mm or 100.0
        cycles = float(str(params.get("cycles_per_texture", 4)))
        if not isfinite(cycles) or cycles <= 0:
            raise ValueError("Grating design needs a positive spatial period")
        period = width / cycles
    if not isfinite(period) or period <= 0:
        raise ValueError("Grating design needs a positive spatial period")
    params.update(
        orientation_deg=0.0,
        tile_width_mm=period,
        tile_height_mm=period,
        spatial_period_mm=period,
        cycles_per_texture=1.0,
        fit_cycles_to_tile=False,
    )
    params.pop("spatial_period_px", None)
    return replace(
        recipe,
        params=params,
        tile_width_mm=period,
        tile_height_mm=period,
        physical_field=False,
    )
