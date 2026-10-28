"""Review-only grating candidate driven by the production Texture drift link maths."""

import json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QWidget

from cephvr.gui.rig_parameter_edits import patch_setting
from cephvr.gui.theme import apply_theme, load_terminal_font
from cephvr.gui.trial_preview import TrialPreview
from cephvr.visual_stimulus.config.models.program_model import (
    Constant, Hold, ImageTile, Program, Rate,
)
from cephvr.visual_stimulus.config.texture_links import linked_rates
from cephvr.visual_stimulus.rendering.state import InstanceState
from subject_projection_options import AMBER, BG, FACES, FONT, GEOMETRY, SMALL

ROOT = Path(__file__).parent
PAYLOAD = json.loads(Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/gratings_protocol.json").read_text(encoding="utf-8"))
BASE = PAYLOAD["trials"][PAYLOAD["selected_trial"]]["program"]
GEOMETRY_ARTIFACT = GEOMETRY.artifact().display.geometry
PERIOD = 5.0
SPEED = 20.0


def make_case(angle):
    data = json.loads(json.dumps(BASE))
    epoch = data["sequence"][0]["body"][0]
    epoch["repetition_rules"] = []
    source_data = next(s for s in epoch["settings"] if s.get("linked_to") is None)
    patch_setting(source_data, {"Orientation": str(angle), "Speed": str(SPEED)})
    source_data["pattern"]["frequency"]["value"] = 1 / PERIOD
    program = Program.model_validate_json(json.dumps(data))
    # Same settings model/geometry/rate resolver used by actual Texture drift.
    settings = program.sequence[0].body[0].settings
    source = next(s for s in settings if s.linked_to is None)
    state = InstanceState.initialize(source, now_ns=0, epoch_start_ns=0)
    initial = dict(state.snapshot(now_ns=0, epoch_start_ns=0))
    a = np.radians(initial["rotation"])
    c, s = float(np.cos(a)), float(np.sin(a))
    unit_pattern = ImageTile(kind="image_tile", asset_id="preview-wave",
                             period_x=Constant(kind="constant", value=1),
                             period_y=Constant(kind="constant", value=1), sampling="linear")
    source_texture = source.model_copy(update={
        "grating": False, "pattern": unit_pattern,
        "motion": source.motion.model_copy(update={
            "x": Rate(kind="rate", function=Constant(kind="constant", value=c)),
            "y": Rate(kind="rate", function=Constant(kind="constant", value=s)),
            "rotation": Hold(kind="hold")}),
        "phase_x": Hold(kind="hold"), "phase_y": Hold(kind="hold"),
    })
    mappings = {}
    for target in settings:
        texture = target.model_copy(update={"grating": False, "pattern": unit_pattern})
        px, py, angular = linked_rates(source_texture, texture, GEOMETRY_ARTIFACT,
                                      source_rotation=0, target_rotation=0)
        assert angular == 0
        vx, vy = -px, -py
        length = float(np.hypot(vx, vy))
        assert length > 0
        mappings[target.instance_id] = (target, vx, vy, length)
    return program, state, mappings


def layers_at(case, seconds):
    program, state, mappings = case
    state = InstanceState.initialize(state.settings, now_ns=0, epoch_start_ns=0)
    source_values = dict(state.snapshot(now_ns=round(seconds * 1e9), epoch_start_ns=0))
    a = np.radians(source_values["rotation"])
    c, s = float(np.cos(a)), float(np.sin(a))
    source = state.settings
    m, n = source.space.mappings[0].matrix
    centre = source_values["phase_x"] + source_values["frequency"] * (
        c * (m[2] - source_values["x"]) + s * (n[2] - source_values["y"]))
    layers = []
    for target, vx, vy, length in mappings.values():
        values = dict(InstanceState.initialize(target, now_ns=0, epoch_start_ns=0).snapshot(now_ns=0, epoch_start_ns=0))
        f = source_values["frequency"] / length
        angle = float(np.degrees(np.arctan2(vy, vx)))
        m, n = target.space.mappings[0].matrix
        phase = centre - f * (vx * m[2] + vy * n[2]) / length
        values.update(frequency=f, rotation=angle, x=0.0, y=0.0, phase_x=phase, phase_y=0.0)
        pattern = source.pattern.model_copy(update={"frequency": Constant(kind="constant", value=f)})
        setting = target.model_copy(update={"pattern": pattern,
            "mean_linear_rgb": source.mean_linear_rgb, "modulation_linear_rgb": source.modulation_linear_rgb})
        from cephvr.gui.trial_preview_plan import PreviewLayer
        layers.append(PreviewLayer(setting, values))
    return tuple(layers)


def pixels(layer, width, height):
    face = str(layer.setting.space.mappings[0].surface_id).title()
    surface = GEOMETRY.surfaces[face]
    values = layer.values
    x = ((np.arange(width) + 0.5) / width - 0.5) * surface.width
    y = (0.5 - (np.arange(height) + 0.5) / height) * surface.height
    m, n = layer.setting.space.mappings[0].matrix
    a = np.radians(values["rotation"])
    mx = m[0] * x[None, :] + m[1] * y[:, None] + m[2]
    my = n[0] * x[None, :] + n[1] * y[:, None] + n[2]
    phase = values["frequency"] * (mx * np.cos(a) + my * np.sin(a)) + values["phase_x"]
    return Image.fromarray(np.where(np.cos(2 * np.pi * phase) >= 0, 255, 0).astype(np.uint8)).convert("RGB")


def card(preview, case, angle, seconds, app):
    layers = layers_at(case, seconds)
    for canvas in preview.canvases.values():
        canvas.present(layers, round(seconds * 1e9), (0, 0, 0))
    preview.rig_view.invalidate_frames()
    app.processEvents()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert preview.rig_view.grab().save(buffer, "PNG")
    image = Image.new("RGB", (510, 470), BG)
    image.paste(Image.open(BytesIO(bytes(buffer.data()))).convert("RGB"), (5, 34))
    draw = ImageDraw.Draw(image)
    draw.text((12, 8), f"Bottom Orientation {angle} deg | speed {SPEED:g} mm/s", font=FONT, fill=AMBER)
    by_face = {str(l.setting.space.mappings[0].surface_id).title(): l for l in layers}
    for index, face in enumerate(FACES):
        layer = by_face[face]
        left = 9 + index * 126
        draw.text((left, 367), face, font=SMALL, fill=AMBER)
        surface = GEOMETRY.surfaces[face]
        scale = min(112 / surface.width, 65 / surface.height)
        width, height = round(surface.width * scale), round(surface.height * scale)
        image.paste(pixels(layer, width, height), (left + (112-width)//2, 390))
        a = np.radians(layer.values["rotation"])
        start = np.array((left + 90, 375))
        delta = np.array((np.cos(a), -np.sin(a))) * 16
        end = start + delta
        draw.line((tuple(start), tuple(end)), fill=AMBER, width=2)
        back = end - delta * 0.35
        normal = np.array((-delta[1], delta[0])) * 0.22
        draw.polygon((tuple(end), tuple(back + normal), tuple(back - normal)), fill=AMBER)
    return image


def check(case):
    initial, moved = layers_at(case, 0), layers_at(case, 0.025)
    for before, after in zip(initial, moved, strict=True):
        target, vx, vy, length = case[2][before.setting.instance_id]
        m, n = target.space.mappings[0].matrix
        det = m[0] * n[1] - m[1] * n[0]
        dx, dy = ((n[1] * vx - m[1] * vy) / det * SPEED * 0.025,
                  (-n[0] * vx + m[0] * vy) / det * SPEED * 0.025)
        def phase(layer, x, y):
            values = layer.values
            a = np.radians(values["rotation"])
            return values["frequency"] * ((m[0]*x+m[1]*y+m[2])*np.cos(a) +
                                           (n[0]*x+n[1]*y+n[2])*np.sin(a)) + values["phase_x"]
        assert np.isclose(phase(before, 7, 11), phase(after, 7+dx, 11+dy), atol=1e-9)


def main():
    app = QApplication([])
    load_terminal_font()
    apply_theme(app)
    app.setFont(QFont("IBM Plex Mono"))
    cases = {angle: make_case(angle) for angle in range(0, 360, 45)}
    for case in cases.values():
        check(case)
    directions = {angle: {str(target.space.mappings[0].surface_id): {
        "mapped_layer_velocity_mm_s": [vx * SPEED, vy * SPEED],
        "bar_normal_degrees": float(np.degrees(np.arctan2(vy, vx))),
        "layer_frequency_cycles_mm": 1 / (PERIOD * length),
    } for target, vx, vy, length in case[2].values()} for angle, case in cases.items()}
    assert directions[180]["left"]["mapped_layer_velocity_mm_s"][1] > 0
    assert directions[180]["right"]["mapped_layer_velocity_mm_s"][1] < 0
    (ROOT / "drift-link-preview-directions.json").write_text(json.dumps(directions, indent=2), encoding="utf-8")
    parent = QWidget()
    preview = TrialPreview(cases[0][0], FACES, PAYLOAD["asset_root"], GEOMETRY, parent)
    preview.rig_view.setFixedSize(500, 325)
    preview.rig_view.azimuth = 25
    preview.show()
    app.processEvents()
    for name, angles in (("cardinal", (0, 90, 180, 270)), ("diagonal", (45, 135, 225, 315))):
        frames = []
        for frame in range(25):
            image = Image.new("RGB", (1040, 1010), BG)
            draw = ImageDraw.Draw(image)
            draw.text((12, 10), "PREVIEW ONLY | Gratings using existing Texture drift motion links", font=FONT, fill=AMBER)
            draw.text((12, 36), "Full screen | bars normal to mapped drift | arrows show local motion | 1/4 speed", font=SMALL, fill="white")
            for index, angle in enumerate(angles):
                image.paste(card(preview, cases[angle], angle, frame/100, app),
                            (10 + (index % 2) * 515, 65 + (index // 2) * 470))
            frames.append(image)
        assert frames[0].tobytes() != frames[12].tobytes()
        frames[0].save(ROOT / f"drift-link-{name}-preview.png")
        frames[0].save(ROOT / f"drift-link-{name}-preview.gif", save_all=True,
                       append_images=frames[1:], duration=40, loop=0)
    preview.close()
    app.processEvents()
    print("Eight directions rendered with production linked_rates; no runtime or settings changes.")


if __name__ == "__main__":
    main()
