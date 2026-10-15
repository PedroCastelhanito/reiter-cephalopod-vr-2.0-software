"""Isolated offscreen production arena/warp shader probe; no projector windows."""

import contextlib
import io
import json
import runpy
import struct
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image

from cephvr.visual_stimulus.rendering.arena_draw import _matrix_bytes
from cephvr.visual_stimulus.rendering.shaders import _ARENA_FRAGMENT, _ARENA_VERTEX, _WARP_FRAGMENT
from cephvr.visual_stimulus.rendering.scene_resources import SceneOutputBuilder

directory = Path(__file__).parent
with contextlib.redirect_stdout(io.StringIO()):
    data = runpy.run_path(str(directory / "probe.py"), init_globals=globals().get("probe_inputs"))
directory = globals().get("output_directory") or directory
ctx = moderngl.create_standalone_context(require=430)
size = (data["output"].width_px, data["output"].height_px)
target = ctx.simple_framebuffer(size, components=4, dtype="f4")
target.use()
target.clear(0, 0, 0, 1, depth=1)
program = ctx.program(vertex_shader=_ARENA_VERTEX, fragment_shader=_ARENA_FRAGMENT)
program["model"].write(_matrix_bytes(np.eye(4)))
program["view_projection"].write(_matrix_bytes(data["matrix"]))
program["calibration_plane_active"].value = 1
program["calibration_plane"].value = (0, 0, 1, -data["surface"].bottom_left_mm[2])
program["base_color_factor"].value = (1, 1, 1, 1)
program["has_base_color_tex"].value = 0
program["alpha_mask"].value = 0
program["alpha_cutoff"].value = 0.5
flags = ctx.buffer(reserve=16)
flags.bind_to_storage_buffer(3)
vertices = np.array([(*p, 0, 0, *c) for p, c in zip(data["positions"], data["colors"])], dtype="f4")
accessor = data["document"]["accessors"][2]
view = data["document"]["bufferViews"][accessor["bufferView"]]
offset = view.get("byteOffset", 0)
indices = bytes(data["binary"][offset:offset + accessor["count"] * 4])
vb, ib = ctx.buffer(vertices.tobytes()), ctx.buffer(indices)
vao = ctx.vertex_array(program, [(vb, "3f 2f 4f", "in_position", "in_uv", "in_color")], ib)
ctx.enable(moderngl.DEPTH_TEST)
ctx.depth_func = "<="
vao.render(moderngl.TRIANGLES)
ctx.disable(moderngl.DEPTH_TEST)
raw = target.read(components=4, dtype="f4")
texture = ctx.texture(size, 4, raw, dtype="f4")
warp = ctx.program(vertex_shader=SceneOutputBuilder._warp_vertex(), fragment_shader=_WARP_FRAGMENT)
warp["scene_tex"].value = 0
warp["has_mask"].value = 0
warp["has_weight"].value = 0
warp["valid_area"].value = tuple(data["mapping"]["valid_area"])
warp["output_size"].value = size
values = [value for v in data["mapping"]["vertices"] for value in (*v["uv"], 2*v["xy"][0]-1, 2*v["xy"][1]-1)]
wvb = ctx.buffer(struct.pack("16f", *values))
wib = ctx.buffer(struct.pack("6I", 0, 1, 3, 0, 3, 2))
wvao = ctx.vertex_array(warp, [(wvb, "2f 2f", "in_source", "in_position")], wib)
final = ctx.simple_framebuffer(size, components=4, dtype="f4")
final.use()
final.clear(0, 0, 0, 1)
texture.use(0)
wvao.render(moderngl.TRIANGLES)
pixels = np.frombuffer(final.read(components=3, dtype="f4"), dtype="f4").reshape(size[1], size[0], 3)
Image.fromarray(np.uint8(np.clip(pixels[::-1], 0, 1) * 255)).save(directory / "bottom-offscreen.png")
def visible_columns(image):
    # This row is inside the crop, away from horizontal lines and the label.
    active = np.flatnonzero(image[320, :, 0] > 0.1)
    groups = np.split(active, np.where(np.diff(active) > 1)[0] + 1)
    centers = [float(group.mean()) for group in groups if len(group)]
    gaps = np.diff(centers)
    return {"sample_y_px": 320, "line_centers_px": centers, "gap_range_px": [float(gaps.min()), float(gaps.max())]}

result = {"renderer": ctx.info["GL_RENDERER"], "scope": "Isolated offscreen production arena and warp shaders, saved GLB/profile; no live application, display submission or optical test", "artifact_identity": data["result"]["artifact_identity"], "size_px": size, "baseline": visible_columns(pixels)}

# Experimental geometry only: triple each grey stroke, keeping its center fixed.
for start in range(0, len(vertices), 4):
    if not 0.34 < vertices[start, 5] < 0.36:
        continue
    delta = vertices[start + 1, :3] - vertices[start, :3]
    vertices[start, :3] -= delta
    vertices[start + 1, :3] += delta
    vertices[start + 2, :3] += delta
    vertices[start + 3, :3] -= delta
vb.write(vertices.tobytes())
target.use()
target.clear(0, 0, 0, 1, depth=1)
ctx.enable(moderngl.DEPTH_TEST)
vao.render(moderngl.TRIANGLES)
ctx.disable(moderngl.DEPTH_TEST)
texture.write(target.read(components=4, dtype="f4"))
final.use()
final.clear(0, 0, 0, 1)
texture.use(0)
wvao.render(moderngl.TRIANGLES)
wider = np.frombuffer(final.read(components=3, dtype="f4"), dtype="f4").reshape(size[1], size[0], 3)
Image.fromarray(np.uint8(np.clip(wider[::-1], 0, 1) * 255)).save(directory / "bottom-wider-stroke-experiment.png")
result["wider_stroke_experiment"] = visible_columns(wider)
(directory / "render-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
ctx.release()
