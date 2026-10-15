"""Isolated native output-pixel checks; no application or projector windows."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import moderngl
import numpy as np
from PIL import Image

from cephvr.visual_stimulus.config.calibration_placement import parse_placement
from cephvr.visual_stimulus.rendering.calibration_placement import draw_placement

root = Path(__file__).parent
context = moderngl.create_standalone_context(require=430)
frame = SimpleNamespace(
    width=320,
    height=200,
    device_fbo=context.simple_framebuffer((320, 200), components=4),
)
results = {}
try:
    for view in ("photodiode_placement", "blackout_placement"):
        value = dict(outputs=[dict(output_id="screen", blackout_zones=[])])
        if view == "photodiode_placement":
            value.update(
                photodiode_output_id="screen",
                photodiode_patch=dict(
                    rect=dict(x=80, y=60, width=30, height=20),
                    background_rect=dict(x=60, y=40, width=80, height=60),
                    high_linear_rgb=[1, 1, 1], low_linear_rgb=[0, 0, 0],
                ),
            )
        else:
            value["outputs"][0]["blackout_zones"] = [dict(x=10, y=10, width=40, height=30)]
        placement = parse_placement(json.dumps(value))
        draw_placement(context, frame, view, "screen", placement)
        pixels = np.frombuffer(frame.device_fbo.read(components=3), dtype=np.uint8).reshape(200, 320, 3)
        expected = np.zeros_like(pixels)
        if view == "photodiode_placement":
            expected[60:80, 80:110] = 255
        else:
            expected[:] = 64
            expected[10:40, 10:50] = 0
        assert np.array_equal(pixels, expected), view
        assert context.scissor == (0, 0, 320, 200)
        Image.fromarray(pixels[::-1]).save(root / f"{view}.png")
        if view == "photodiode_placement":
            value["photodiode_patch"]["rect"]["x"] = 100
        else:
            value["outputs"][0]["blackout_zones"] = []
        draw_placement(context, frame, view, "screen", parse_placement(json.dumps(value)))
        updated = np.frombuffer(frame.device_fbo.read(components=3), dtype=np.uint8).reshape(200, 320, 3)
        if view == "photodiode_placement":
            expected[:] = 0
            expected[60:80, 100:130] = 255
        else:
            expected[:] = 64
        assert np.array_equal(updated, expected), f"updated {view}"
        results[view] = dict(initial_exact=True, updated_exact=True, output_px=[320,200])
    results["renderer"] = context.info["GL_RENDERER"]
    results["scope"] = "Production draw_placement on isolated offscreen framebuffer; no native windows, swaps, live application or optical timing acceptance"
    results["source_sha256"] = hashlib.sha256(Path("src/cephvr/visual_stimulus/rendering/calibration_placement.py").read_bytes()).hexdigest()
    (root / "native-result.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
finally:
    frame.device_fbo.release()
    context.release()
