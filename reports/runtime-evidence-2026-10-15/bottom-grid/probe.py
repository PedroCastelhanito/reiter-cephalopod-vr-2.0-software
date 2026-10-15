"""Read-only CPU measurement of the saved Bottom diagnostic, not optical proof."""

import hashlib
import json
import math
import struct
from pathlib import Path

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.rendering.arena import off_axis_view_projection

root = globals().get("input_root") or Path(
    "C:/Users/ReiterU_PC/AppData/Local/CephVR/calibration/"
    "dc327f2d29bec448/frame_grid/calibration"
)
profile = DisplayProfile.model_validate_json(
    (root / "diagnostic_display_profile.json").read_text()
)
surface = next(s for s in profile.geometry.surfaces if s.surface_id == "bottom")
output = next(o for o in profile.outputs if o.output_id == "calibration_bottom")
mapping = json.loads((root / "diagnostic_bottom.json").read_text())
source = (root / "frame_grid.glb").read_bytes()
json_length = struct.unpack_from("<I", source, 12)[0]
document = json.loads(source[20 : 20 + json_length])
binary = memoryview(source)[28 + json_length :]
attributes = document["meshes"][0]["primitives"][0]["attributes"]


def attribute(name, size):
    accessor = document["accessors"][attributes[name]]
    view = document["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [
        struct.unpack_from(f"<{size}f", binary, offset + i * size * 4)
        for i in range(accessor["count"])
    ]


positions = attribute("POSITION", 3)
colors = attribute("COLOR_0", 4)
matrix = off_axis_view_projection(profile, surface)


def projected(point):
    vector = (*point, 1)
    clip = [sum(row[i] * vector[i] for i in range(4)) for row in matrix]
    uv = [(clip[i] / clip[3] + 1) / 2 for i in (0, 1)]
    a, b, c = [v["xy"] for v in mapping["vertices"][:3]]
    return (
        (a[0] + (b[0] - a[0]) * uv[0]) * output.width_px,
        (a[1] + (c[1] - a[1]) * uv[1]) * output.height_px,
    )


lines = {"image_x": [], "image_y": []}
for start in range(0, len(positions), 4):
    quad = positions[start : start + 4]
    color = colors[start]
    if not (0.34 < color[0] < 0.36 and 0.39 < color[1] < 0.41):
        continue
    if not all(abs(p[2] - (surface.bottom_left_mm[2] + 0.02)) < 1e-4 for p in quad):
        continue
    center = tuple(sum(p[i] for p in quad) / 4 for i in range(3))
    span_x = max(p[0] for p in quad) - min(p[0] for p in quad)
    axis = "image_x" if span_x > 1 else "image_y"
    pixel_axis = 0 if axis == "image_x" else 1
    lines[axis].append({"world_mm": center[1 if pixel_axis == 0 else 0], "pixel": projected(center)[pixel_axis]})

results = {}
for axis, records in lines.items():
    records.sort(key=lambda r: r["world_mm"])
    mm_steps = [b["world_mm"] - a["world_mm"] for a, b in zip(records, records[1:])]
    pixel_steps = [abs(b["pixel"] - a["pixel"]) for a, b in zip(records, records[1:])]
    results[axis] = {
        "line_count": len(records),
        "world_pitch_range_mm": [min(mm_steps), max(mm_steps)],
        "output_pitch_range_px": [min(pixel_steps), max(pixel_steps)],
        "lines": records,
    }

extent = (
    math.dist(surface.bottom_left_mm, surface.bottom_right_mm),
    math.dist(surface.bottom_left_mm, surface.top_left_mm),
)
result = {
    "method": "Saved GLB vertex centers through production CPU off-axis matrix and saved affine mapping; no GPU or projector action",
    "artifact_identity": {
        p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "mtime_ns": p.stat().st_mtime_ns}
        for p in (root / "diagnostic_display_profile.json", root / "diagnostic_bottom.json", root / "frame_grid.glb")
    },
    "output_px": [output.width_px, output.height_px],
    "full_raster_extent_mm": extent,
    "implied_pitch_mm_per_pixel": [extent[0] / output.width_px, extent[1] / output.height_px],
    "valid_area": mapping["valid_area"],
    "valid_pixels": [(mapping["valid_area"][2] - mapping["valid_area"][0]) * output.width_px, (mapping["valid_area"][3] - mapping["valid_area"][1]) * output.height_px],
    "grid": results,
    "limits": "Latest saved launch bundle is not a live resource/evidence snapshot. Live adjustments, physical measurements, optics, projector settings and observer perspective remain unverified.",
}
destination = globals().get("result_path") or Path(__file__).with_name("result.json")
destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "artifact_identity"}, indent=2))
