"""Full-coverage flat-panel motion candidate; no runtime or saved-input changes."""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from cephvr.gui.rig_parameter_edits import patch_setting
from cephvr.visual_stimulus.config.models.program_model import TextureSettings
from cephvr.visual_stimulus.rendering.state import InstanceState
from subject_projection_options import AMBER, BG, FACES, FONT, GEOMETRY, SMALL

ROOT = Path(__file__).parent
DATA = json.loads(Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/gratings_protocol.json").read_text(encoding="utf-8"))
EPOCH = DATA["trials"][DATA["selected_trial"]]["program"]["sequence"][0]["body"][0]
SOURCE = next(s for s in EPOCH["settings"] if s.get("linked_to") is None)
patch_setting(SOURCE, {"Orientation": "45", "Speed": "20"})
SETTING = TextureSettings.model_validate_json(json.dumps(SOURCE))
STATE = InstanceState.initialize(SETTING, now_ns=0, epoch_start_ns=0)
RUNTIME_PLAN = None


def phase_at(seconds):
    values = dict(STATE.snapshot(now_ns=round(seconds * 1e9), epoch_start_ns=0))
    angle = np.radians(values["rotation"])
    phase = values["phase_x"] - values["frequency"] * (
        values["x"] * np.cos(angle) + values["y"] * np.sin(angle))
    return float(angle), float(values["frequency"]), float(phase)


def frame(seconds):
    angle, frequency, phase = phase_at(seconds)
    output = Image.new("RGB", (1040, 870), BG)
    draw = ImageDraw.Draw(output)
    title = "IMPLEMENTED" if RUNTIME_PLAN is not None else "PROPOSED"
    draw.text((20, 15), title + " | Full-screen flat gratings, one shared local direction", font=FONT, fill=AMBER)
    draw.text((20, 45), "Bottom Orientation 45 deg | period 5 mm | speed 20 mm/s | motion 1/4 speed", font=SMALL, fill="white")
    draw.text((20, 70), "Each white outline is the full usable screen. No perspective divide, horizon or origin.", font=SMALL, fill="white")
    layers = ({str(layer.setting.space.mappings[0].surface_id).title(): layer
               for layer in RUNTIME_PLAN.seek(round(seconds * 1e9))}
              if RUNTIME_PLAN is not None else {})
    for index, face in enumerate(FACES):
        left, top = 20 + (index % 2) * 510, 110 + (index // 2) * 355
        surface = GEOMETRY.surfaces[face]
        scale = min(480 / surface.width, 305 / surface.height)
        width, height = round(surface.width * scale), round(surface.height * scale)
        x = ((np.arange(width) + 0.5) / width - 0.5) * surface.width
        y = (0.5 - (np.arange(height) + 0.5) / height) * surface.height
        cycles = frequency * (x[None, :] * np.cos(angle) + y[:, None] * np.sin(angle)) + phase
        if layers:
            layer = layers[face]
            values = layer.values
            m, n = layer.setting.space.mappings[0].matrix
            a = np.radians(values["rotation"])
            mx = m[0] * x[None, :] + m[1] * y[:, None] + m[2] - values["x"]
            my = n[0] * x[None, :] + n[1] * y[:, None] + n[2] - values["y"]
            cycles = values["frequency"] * (mx * np.cos(a) + my * np.sin(a)) + values["phase_x"]
        pixels = np.where(np.cos(2 * np.pi * cycles) >= 0, 255, 0).astype(np.uint8)
        assert pixels.min() == 0 and pixels.max() == 255
        image = Image.fromarray(pixels).convert("RGB")
        x0, y0 = left + (480 - width) // 2, top + 28
        output.paste(image, (x0, y0))
        draw.rectangle((x0 - 1, y0 - 1, x0 + width, y0 + height), outline="white")
        draw.text((left, top), face, font=FONT, fill=AMBER)
        # The same signed bar-normal velocity on every flat panel.
        start = (left + 455, top + 10)
        delta = np.array((np.cos(angle), -np.sin(angle))) * 25
        end = tuple(np.array(start) + delta)
        draw.line((start, end), fill=AMBER, width=3)
        normal = np.array((-delta[1], delta[0])) * 0.22
        back = np.array(end) - delta * 0.28
        draw.polygon((end, tuple(back + normal), tuple(back - normal)), fill=AMBER)
    footer = ("Actual runtime field | same screen-local tilt and phase drift | saved settings unchanged"
              if RUNTIME_PLAN is not None else
              "Visual candidate only | same screen-local tilt and phase drift | runtime and saved settings unchanged")
    draw.text((20, 838), footer,
              font=SMALL, fill="white")
    return output


if __name__ == "__main__":
    if "--runtime" in sys.argv:
        from cephvr.gui.trial_preview_plan import PreviewPlan
        from cephvr.visual_stimulus.config.models.program_model import Program

        EPOCH["repetition_rules"] = []
        program = Program.model_validate_json(json.dumps(DATA["trials"][DATA["selected_trial"]]["program"]))
        RUNTIME_PLAN = PreviewPlan(program, GEOMETRY.artifact().display.geometry)
    label = "implemented" if RUNTIME_PLAN is not None else "candidate"
    frames = [frame(index / 100) for index in range(25)]
    assert frames[0].tobytes() != frames[12].tobytes()
    # One complete period after0.25s must reproduce all four complete panels exactly.
    assert np.max(abs(np.asarray(frame(0.25)).astype(int) - np.asarray(frames[0]).astype(int))) == 0
    frames[0].save(ROOT / f"flat-four-projectors-{label}.png")
    frames[0].save(ROOT / f"flat-four-projectors-{label}.gif", save_all=True,
                   append_images=frames[1:], duration=40, loop=0)
    print("Four-panel candidate saved; no runtime/input/device change.")
