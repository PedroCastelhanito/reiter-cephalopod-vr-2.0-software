"""Compile validated physical-field recipes into the existing layer shader."""

import math

from cephvr.visual_stimulus.resources.physical_field import (
    dot_neighbours,
    parameters,
    seed32,
    spectral_terms,
    threshold,
    validate_field,
)
from cephvr.visual_stimulus.resources.texture_recipe import TextureRecipe
from cephvr.visual_stimulus.resources.texture_recipe_geometry import _color

_HASH = """
float field_hash(ivec2 p, uint seed) {
    uint h = uint(p.x) * 0x1f123bb5u ^ uint(p.y) * 0x5f356495u ^ seed;
    h = (h ^ (h >> 16)) * 0x7feb352du;
    h = (h ^ (h >> 15)) * 0x846ca68bu;
    h ^= h >> 16;
    return float(h >> 8) / 16777216.0;
}
float field_mask(float d, float edge) {
    return edge <= 0.0 ? step(0.0, d) : smoothstep(-edge, edge, d);
}
uniform vec2 field_extent_mm;
uniform vec2 field_phase_mm;
"""


def field_glsl(recipe: TextureRecipe) -> str:
    validate_field(recipe.pattern, recipe.params)
    p = parameters(recipe.pattern, recipe.params)
    pattern = recipe.pattern

    def f(value: float) -> str:
        return f"{float(value):.17e}"

    edge = f(p.get("blur_mm", 0))
    body = "float bright = 1.0;"
    if pattern == "grating":
        angle = math.radians(p["orientation_deg"])
        body = f"""float wave = sin(6.283185307179586 * dot(q, vec2({f(math.cos(angle))}, {f(math.sin(angle))})) / {f(p["spatial_period_mm"])});
        float alpha = 0.5 + 0.5 * wave;
        float bright = mix(alpha, field_mask(alpha - 0.5, {f(0.5 * (1 - p["feature_sharpness"]))}), {f(p["feature_sharpness"])});"""
    elif pattern == "polar_grating":
        period = math.tau / p["bar_count"]
        body = f"""float radius = length(q);
        float angle = (radius == 0.0 ? 0.0 : atan(q.y, q.x)) + {f(math.radians(p["phase_deg"]))};
        float delta = mod(angle + {f(period / 2)}, {f(period)}) - {f(period / 2)};
        float bright = field_mask({f(p["bar_width_mm"] / 2)} - radius * abs(sin(delta)), 0.0);
        if (radius < {f(p["inner_radius_mm"])} || ({f(p["outer_radius_mm"])} > 0.0 && radius > {f(p["outer_radius_mm"])})) bright = 0.0;"""
    elif pattern in {"checker", "bars_horizontal", "bars_vertical"}:
        cell = p.get("cell_size_mm", p.get("bar_width_mm", 5))
        term = (
            "a * b"
            if pattern == "checker"
            else "b"
            if pattern == "bars_horizontal"
            else "a"
        )
        body = f"""float a = cos(3.141592653589793 * q.x / {f(cell)});
        float b = cos(3.141592653589793 * q.y / {f(cell)});
        float bright = field_mask(({term}) * {f(cell / math.pi)}, {edge});"""
    elif pattern == "dots_grid":
        pitch = p["spacing_mm"]
        body = f"vec2 d = mod(q + {f(pitch / 2)}, {f(pitch)}) - {f(pitch / 2)}; float bright = field_mask({f(p['dot_diameter_mm'] / 2)} - length(d), {edge});"
    elif pattern == "dots_rand":
        body = "float bright = 0.0;"
        if p["density_per_cm2"] > 0:
            pitch = math.sqrt(25 / p["density_per_cm2"])
            reach = dot_neighbours(p)
            seed = seed32(int(p["seed"]))
            body += f"""
            ivec2 cell = ivec2(floor(q / {f(pitch)}));
            for (int j = -{reach}; j <= {reach}; ++j) for (int i = -{reach}; i <= {reach}; ++i) {{
                ivec2 c = cell + ivec2(i,j);
                if (field_hash(c, {seed}u) < 0.25) {{
                    vec2 center = (vec2(c) + vec2(field_hash(c, {seed ^ 12345}u), field_hash(c, {seed ^ 67890}u))) * {f(pitch)};
                    bright = max(bright, field_mask({f(p["dot_diameter_mm"] / 2)} - length(q-center), {edge}));
                }}
            }}"""
    elif pattern in {"noise_binary", "noise_gray"}:
        seed = seed32(int(p["seed"]))
        value = f"field_hash(cell, {seed}u)"
        if pattern == "noise_binary":
            value = f"({value} < {f(p['density'])} ? 1.0 : 0.0)"
        else:
            value = f"(field_hash(cell, {seed ^ 54321}u) < {f(p['density'])} ? {value} : 0.0)"
        helper = "float field_noise(ivec2 cell) { return " + value + "; }\n"
        if p["blur_mm"] == 0:
            body = f"float bright = field_noise(ivec2(floor(q / {f(p['element_size_mm'])})));"
        else:
            cell = f(p["element_size_mm"])
            body = f"""vec2 location = q / {cell} - 0.5;
            ivec2 c = ivec2(floor(location));
            vec2 blend = smoothstep(vec2(-{edge}), vec2({edge}), (fract(location) - 0.5) * {cell});
            float bright = mix(mix(field_noise(c),field_noise(c+ivec2(1,0)),blend.x),
                               mix(field_noise(c+ivec2(0,1)),field_noise(c+ivec2(1,1)),blend.x),blend.y);"""
    elif pattern == "filtered_noise":
        body = "float value = 0.0;\n"
        for fx, fy, phase in spectral_terms(p):
            body += f"value += cos(6.283185307179586 * (dot(q, vec2({f(fx)}, {f(fy)})) + {f(phase)})) / 4.0;\n"
        body += f"float bright = field_mask(value - {f(threshold(p))}, {f(p['edge_smooth_mm'] / p['scale_mm'])});"
        if p["black_fraction"] in (0, 1):
            body += f"bright = {f(1 - p['black_fraction'])};"
    elif pattern == "calibration_grid":
        pitch = p["line_spacing_mm"]
        body = f"""vec2 d = abs(mod(q + {f(pitch / 2)}, {f(pitch)}) - {f(pitch / 2)});
        float bright = min(d.x,d.y) <= {f(p["line_width_mm"] / 2)} && mod(d.x < d.y ? q.y : q.x, {f(p["dash_length_mm"] + p["dash_gap_mm"])}) < {f(p["dash_length_mm"])} ? 1.0 : 0.0;"""
    a = ",".join(f(c / 255) for c in _color(p.get("color_a"), (255, 255, 255)))
    b = ",".join(f(c / 255) for c in _color(p.get("color_b"), (0, 0, 0)))
    foreground = f"vec3({a})"
    if pattern == "calibration_grid":
        from cephvr.visual_stimulus.resources.texture_recipe_patterns import _PALETTE

        colors = ",".join(
            "vec3(" + ",".join(f(int(c) / 255) for c in rgb) + ")" for rgb in _PALETTE
        )
        body += f"\nvec3 palette[16] = vec3[16]({colors});\nint index = int(mod(floor((d.x < d.y ? q.x : q.y) / {f(p['line_spacing_mm'])} + 0.5), {f(p['color_count'])}));"
        foreground += " * palette[index]"
    return (
        _HASH
        + (helper if pattern in {"noise_binary", "noise_gray"} else "")
        + "\nvec3 physical_field(vec2 q) {\n"
        + body
        + f"\nreturn mix(vec3({b}), {foreground}, bright);\n}}\n"
    )


def layer_fragment(recipe: TextureRecipe) -> str:
    from cephvr.visual_stimulus.rendering import shaders

    return shaders._LAYER_FRAGMENT.replace(
        "// PHYSICAL_FIELD_DECLARATION", field_glsl(recipe)
    ).replace(
        "// PHYSICAL_FIELD_SAMPLE",
        """
        if (mode == 9) {
            vec3 rgb = mean_rgb + contrast * modulation_rgb *
                (2.0 * physical_field((uv - 0.5) * field_extent_mm + field_phase_mm) - 1.0);
            mark_alpha(opacity, rgb * opacity);
            float coverage = clamp(opacity, 0.0, 1.0);
            color = vec4(rgb * coverage, coverage); return;
        }
        """,
    )
