"""GLSL sources for the scene, geometry and output pipelines."""

_QUAD_VERTEX = """#version 430
in vec2 in_position;
in vec2 in_uv;
out vec2 uv;
void main() { uv = in_uv; gl_Position = vec4(in_position, 0.0, 1.0); }
"""

_LAYER_VERTEX = """#version 430
in vec2 in_uv;
out vec2 uv;
uniform vec2 clip_vertices[4];
void main() { uv = in_uv; gl_Position = vec4(clip_vertices[gl_VertexID], 0.0, 1.0); }
"""

_LAYER_FRAGMENT = """#version 430
in vec2 uv;
out vec4 color;
uniform sampler2D image_tex;
uniform int mode;
uniform vec3 mean_rgb;
uniform vec3 modulation_rgb;
uniform float contrast;
uniform float opacity;
uniform vec2 frequency;
uniform vec2 phase;
uniform vec2 period;
layout(std430, binding = 3) buffer DiagnosticFlags { uint diagnostic_flags[]; };
void mark_alpha(float coverage, vec3 premultiplied_rgb) {
    if (any(isnan(premultiplied_rgb)) || any(isinf(premultiplied_rgb)) ||
        isnan(coverage) || isinf(coverage)) {
        atomicOr(diagnostic_flags[3], 8u);
    } else if (coverage < 0.0 || coverage > 1.0) {
        atomicOr(diagnostic_flags[0], 1u);
    }
}
void main() {
    float signal = 0.0;
    if (mode == 0 || mode == 4) {
        vec4 sample_value = texture(image_tex, uv);
        mark_alpha(sample_value.a, sample_value.rgb);
        if (mode == 0) {
            vec3 straight_sample = sample_value.a > 0.0
                ? sample_value.rgb / sample_value.a : vec3(0.0);
            float coverage_raw = sample_value.a * opacity;
            mark_alpha(coverage_raw, straight_sample);
            float coverage = clamp(coverage_raw, 0.0, 1.0);
            color = vec4(straight_sample * coverage, coverage); return;
        }
        vec2 tiled_uv = fract(uv * period + phase);
        sample_value = texture(image_tex, tiled_uv);
        mark_alpha(sample_value.a, sample_value.rgb);
        vec3 straight_sample = sample_value.a > 0.0
            ? sample_value.rgb / sample_value.a : vec3(0.0);
        vec3 tiled_rgb = mean_rgb + contrast * modulation_rgb * (2.0 * straight_sample - 1.0);
        float coverage_raw = sample_value.a * opacity;
        mark_alpha(coverage_raw, tiled_rgb * coverage_raw);
        float coverage = clamp(coverage_raw, 0.0, 1.0);
        color = vec4(tiled_rgb * coverage, coverage); return;
    } else if (mode == 1 || mode == 2) {
        float wave = cos(6.283185307179586 * (frequency.x * uv.x + phase.x));
        signal = mode == 1 ? wave : (wave >= 0.0 ? 1.0 : -1.0);
    } else if (mode == 3) {
        float x = cos(6.283185307179586 * (frequency.x * uv.x + phase.x)) >= 0.0 ? 1.0 : -1.0;
        float y = cos(6.283185307179586 * (frequency.y * uv.y + phase.y)) >= 0.0 ? 1.0 : -1.0;
        signal = x * y;
    }
    vec3 rgb = mean_rgb + contrast * modulation_rgb * signal;
    mark_alpha(opacity, rgb * opacity);
    float coverage = clamp(opacity, 0.0, 1.0);
    color = vec4(rgb * coverage, coverage);
}
"""

_ARENA_VERTEX = """#version 430
in vec3 in_position;
in vec2 in_uv;
in vec4 in_color;
uniform mat4 model;
uniform mat4 view_projection;
out vec2 uv;
out vec4 vertex_color;
void main() {
    uv = in_uv;
    vertex_color = in_color;
    gl_Position = view_projection * model * vec4(in_position, 1.0);
}
"""

_ARENA_FRAGMENT = """#version 430
in vec2 uv;
in vec4 vertex_color;
out vec4 color;
uniform sampler2D base_color_tex;
uniform int has_base_color_tex;
uniform vec4 base_color_factor;
uniform int alpha_mask;
uniform float alpha_cutoff;
layout(std430, binding = 3) buffer DiagnosticFlags { uint diagnostic_flags[]; };
void main() {
    vec4 base = base_color_factor * vertex_color;
    if (has_base_color_tex != 0) {
        vec4 texel = texture(base_color_tex, uv);
        if (alpha_mask != 0) {
            base.rgb *= texel.a > 0.0 ? texel.rgb / texel.a : vec3(0.0);
            base.a *= texel.a;
        } else {
            base.rgb *= texel.rgb;
        }
    }
    if (alpha_mask != 0 && base.a < alpha_cutoff) discard;
    if (any(isnan(base)) || any(isinf(base))) atomicOr(diagnostic_flags[3], 8u);
    color = vec4(base.rgb, 1.0);
}
"""

_WARP_FRAGMENT = """#version 430
in vec2 uv;
out vec4 color;
uniform sampler2D scene_tex;
uniform sampler2D mask_tex;
uniform sampler2D weight_tex;
uniform int has_mask;
uniform int has_weight;
void main() {
    vec4 scene = texture(scene_tex, uv);
    float mask_value = has_mask != 0 ? texture(mask_tex, uv).r : 1.0;
    float weight_value = has_weight != 0 ? texture(weight_tex, uv).r : 1.0;
    color = vec4(scene.rgb * mask_value * weight_value, 1.0);
}
"""

_OUTPUT_FRAGMENT = """#version 430
in vec2 uv;
out vec4 color;
uniform sampler2D source_tex;
uniform sampler2D lut_tex;
uniform int calibrated;
uniform int lut_size;
uniform float marker_active;
uniform vec4 marker_rect;
uniform vec3 marker_rgb;
layout(std430, binding = 3) buffer DiagnosticFlags { uint diagnostic_flags[]; };
void mark_range(uint stage, vec4 value) {
    if (any(isnan(value)) || any(isinf(value))) {
        atomicOr(diagnostic_flags[3], 8u);
    } else if (any(lessThan(value, vec4(0.0))) || any(greaterThan(value, vec4(1.0)))) {
        atomicOr(diagnostic_flags[stage], 1u);
    }
}
void main() {
    vec3 linear_rgb = texture(source_tex, uv).rgb;
    bool marker = marker_active > 0.5 && uv.x >= marker_rect.x && uv.x < marker_rect.z
        && uv.y >= marker_rect.y && uv.y < marker_rect.w;
    if (marker) linear_rgb = marker_rgb;
    mark_range(1u, vec4(linear_rgb, 1.0));
    linear_rgb = clamp(linear_rgb, 0.0, 1.0);
    if (calibrated != 0) {
        float x = clamp(linear_rgb.r, 0.0, 1.0) * float(lut_size - 1);
        float y = clamp(linear_rgb.g, 0.0, 1.0) * float(lut_size - 1);
        float z = clamp(linear_rgb.b, 0.0, 1.0) * float(lut_size - 1);
        color.rgb = vec3(texture(lut_tex, vec2((x + 0.5) / float(lut_size), 0.5)).r,
                         texture(lut_tex, vec2((y + 0.5) / float(lut_size), 0.5)).g,
                         texture(lut_tex, vec2((z + 0.5) / float(lut_size), 0.5)).b);
    } else {
        bvec3 low = lessThanEqual(linear_rgb, vec3(0.0031308));
        vec3 encoded = 1.055 * pow(max(linear_rgb, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055;
        color.rgb = mix(encoded, 12.92 * linear_rgb, low);
    }
    mark_range(2u, vec4(color.rgb, 1.0));
    color.rgb = clamp(color.rgb, 0.0, 1.0);
    color.a = 1.0;
}
"""
