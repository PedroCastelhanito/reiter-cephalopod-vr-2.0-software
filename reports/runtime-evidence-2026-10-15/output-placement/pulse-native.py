"""Production offscreen pixels over a pulse cycle with a live geometry edit."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import moderngl
import numpy as np

from cephvr.visual_stimulus.config.calibration_placement import parse_placement
from cephvr.visual_stimulus.rendering.calibration_placement import draw_placement
from cephvr.visual_stimulus.rendering.photodiode import photodiode_level

root = Path(__file__).parent
context = moderngl.create_standalone_context(require=430)
frame = SimpleNamespace(
    width=320, height=200,
    device_fbo=context.simple_framebuffer((320, 200), components=4),
)
value = dict(
    outputs=[dict(output_id="screen", blackout_zones=[])],
    photodiode_output_id="screen",
    photodiode_patch=dict(
        rect=dict(x=80, y=60, width=30, height=20),
        background_rect=dict(x=60, y=40, width=120, height=100),
        high_linear_rgb=[1, 1, 1], low_linear_rgb=[0, 0, 0],
    ),
)
levels = []
try:
    for index in range(66):
        if index == 3:
            value["photodiode_patch"]["rect"] = dict(x=100, y=70, width=40, height=30)
        placement = parse_placement(json.dumps(value))
        high = photodiode_level(index)
        levels.append(int(high))
        draw_placement(context, frame, "photodiode_placement", "screen", placement, high)
        pixels = np.frombuffer(frame.device_fbo.read(components=3), dtype=np.uint8).reshape(200, 320, 3)
        expected = np.zeros_like(pixels)
        rect = placement.photodiode_patch.rect
        if high:
            expected[rect.y:rect.y + rect.height, rect.x:rect.x + rect.width] = 255
        assert np.array_equal(pixels, expected), index
    sources = [
        "src/cephvr/visual_stimulus/rendering/photodiode.py",
        "src/cephvr/visual_stimulus/rendering/calibration_placement.py",
        "src/cephvr/visual_stimulus/rendering/display_calibration.py",
        "src/cephvr/visual_stimulus/rendering/native.py",
        "src/cephvr/visual_stimulus/worker/display_calibration.py",
    ]
    result = dict(
        date="2026-10-15", renderer=context.info["GL_RENDERER"],
        exact_frames=66, levels=levels, live_geometry_edit_at=3,
        scope="Production offscreen drawing; no native windows, swaps, GUI, projector or optical timing acceptance",
        source_sha256={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources},
    )
    (root / "pulse-native.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
finally:
    frame.device_fbo.release()
    context.release()
