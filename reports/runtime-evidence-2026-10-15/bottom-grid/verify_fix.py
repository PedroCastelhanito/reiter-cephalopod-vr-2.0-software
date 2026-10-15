"""Snapshot inputs and compare original/fixed native offscreen diagnostics."""

import hashlib
import json
import runpy
from pathlib import Path

from cephvr.gui.calibration_arena import make_calibration_glb
from cephvr.gui.projector_geometry import RigDimensions

directory = Path(__file__).parent
saved = Path("config/runtime_gui.json")
calibration = json.loads(saved.read_text())["projectors"]["configuration"]
values = calibration["values"]
rig = RigDimensions(
    values["rig.width"], values["rig.depth"], values["rig.height"],
    tuple(values[f"rig.subject_{axis}"] for axis in "xyz"),
)
source = Path(
    "C:/Users/ReiterU_PC/AppData/Local/CephVR/calibration/"
    "dc327f2d29bec448/frame_grid/calibration"
)
destination = directory / "fix-verification"
destination.mkdir(exist_ok=False)
(destination / "runtime_gui.json").write_bytes(saved.read_bytes())
profile = json.loads((source / "diagnostic_display_profile.json").read_text())
screens = {
    surface["surface_id"].title(): [surface[key] for key in (
        "bottom_left_mm", "bottom_right_mm", "top_right_mm", "top_left_mm"
    )]
    for surface in profile["geometry"]["surfaces"]
}
rasters = {
    mapping["surface_id"].title(): (mapping["viewport"]["width"], mapping["viewport"]["height"])
    for mapping in profile["mappings"]
}
for variant in ("before", "after"):
    root = destination / variant
    inputs = root / "calibration"
    inputs.mkdir(parents=True)
    for path in source.iterdir():
        if path.suffix in (".json", ".glb"):
            (inputs / path.name).write_bytes(path.read_bytes())
    if variant == "after":
        (inputs / "frame_grid.glb").write_bytes(
            make_calibration_glb(rig, screens, raster_sizes=rasters)
        )
    runpy.run_path(str(directory / "render_probe.py"), init_globals={
        "probe_inputs": {"input_root": inputs, "result_path": root / "cpu-result.json"},
        "output_directory": root,
    })
before = json.loads((destination / "before/render-result.json").read_text())["baseline"]
after = json.loads((destination / "after/render-result.json").read_text())["baseline"]
assert before["gap_range_px"][1] > 2 * before["gap_range_px"][0]
assert after["gap_range_px"][1] - after["gap_range_px"][0] <= 1
assert len(after["line_centers_px"]) > len(before["line_centers_px"])
summary = {
    "before": before,
    "after": after,
    "source_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path("src/cephvr/gui/calibration_arena.py"),
        Path("src/cephvr/gui/calibration_guides.py"),
        Path("src/cephvr/gui/calibration_profile.py"),
    )},
    "scope": "Isolated offscreen production shaders and fixed GLB generator; no projector presentation or calibration measurement",
}
(destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
