"""Reproduce pending owner decisions using temporary files and an 8x8 raster."""

import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from cephvr.gui.subject_history import find_subject_sessions
from cephvr.visual_stimulus.resources.texture_recipe import (
    generate_texture_recipe,
    parse_texture_recipe,
)

with TemporaryDirectory() as root:
    for name in (
        "20261019_Zulu/CEPH-007-090000",
        "20261019_Alpha/CEPH-007-180000",
    ):
        (Path(root) / name).mkdir(parents=True)
    history = find_subject_sessions(root, "CEPH-007", "Alpha", date(2026, 10, 19))
    print("Subject history:", history)
    print("Expected latest: 2026-10-19 Alpha 18:00")

corners = {
    "front": [[-50, 0, 0], [50, 0, 0], [50, 0, 80], [-50, 0, 80]],
    "left": [[-50, -100, 0], [-50, 0, 0], [-50, 0, 80], [-50, -100, 80]],
    "right": [[50, 0, 0], [50, 100, 0], [50, 100, 80], [50, 0, 80]],
    "bottom": [[-50, -100, 0], [50, -100, 0], [50, 0, 0], [-50, 0, 0]],
}
for pattern in ("grating", "polar_grating"):
    raw = json.dumps(
        {"pattern": pattern, "params": {"size": 8, "color_a": [1e308, 0, 0]}}
    ).encode()
    recipe = parse_texture_recipe(raw)
    print(pattern, "parse accepted")
    try:
        pixels = generate_texture_recipe(recipe, surface_corners=corners)
    except Exception as error:
        print(pattern, type(error).__name__, str(error))
    else:
        print(pattern, "generated", pixels.shape)
