"""Subject-eye projection comparisons only; no runtime or saved configuration edits."""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cephvr.gui.projector_geometry import RigDimensions
from cephvr.gui.trial_preview_surfaces import PreviewGeometry

ROOT = Path(__file__).parent
VALUES = json.loads(
    Path("C:/Users/ReiterU_PC/Desktop/Pedro/configs/projectors_config.json").read_text()
)["values"]
FACES = ("Front", "Left", "Right", "Bottom")
RIG = RigDimensions(
    *(VALUES[f"rig.{key}"] for key in ("width", "depth", "height")),
    tuple(VALUES[f"rig.subject_{axis}"] for axis in "xyz"),
)
GEOMETRY = PreviewGeometry.from_drafts(
    RIG,
    {face: {key.rsplit(".", 1)[-1]: str(value)
            for key, value in VALUES.items() if key.startswith(f"screens.{face}.")}
     for face in FACES},
    {face: (int(VALUES[f"screens.{face}.reference_width_px"]),
            int(VALUES[f"screens.{face}.reference_height_px"])) for face in FACES},
)
EYE = np.array(RIG.subject)
DOWN = np.radians(30)
FORWARD = np.array((0, -np.cos(DOWN), -np.sin(DOWN)))
RIGHT = np.array((1, 0, 0))
UP = np.cross(FORWARD, RIGHT)
REFERENCE = np.mean(np.array(GEOMETRY.surfaces["Bottom"].corners), axis=0)
DISTANCE = np.linalg.norm(REFERENCE - EYE)
BG = (31, 40, 44)
AMBER = (255, 195, 95)
FONT = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 17)
SMALL = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 14)
RUNTIME_PLAN = None


def coordinates(vectors, mode):
    if mode == "forward":
        depth = vectors @ FORWARD
        safe = np.where(abs(depth) > 1e-10, depth, 1e-10)
        return np.stack((DISTANCE * (vectors @ RIGHT) / safe,
                         DISTANCE * (vectors @ UP) / safe), axis=-1), depth > 1e-8
    x, y, z = np.moveaxis(vectors, -1, 0)
    return np.stack((np.arctan2(x, -y),
                     np.arctan2(z, np.hypot(x, y))), axis=-1), np.ones(x.shape, bool)


def field(mode):
    # Match the same Bottom 45-degree normal and physical period locally at its centre.
    q0 = coordinates(REFERENCE - EYE, mode)[0]
    dx = coordinates(REFERENCE - EYE + (0, 0.001, 0), mode)[0] - q0
    dy = coordinates(REFERENCE - EYE + (-0.001, 0, 0), mode)[0] - q0
    jacobian = np.column_stack((dx, dy)) / 0.001
    gradient = -np.ones(2) / (5 * np.sqrt(2))
    wave = np.linalg.solve(jacobian.T, gradient)
    assert np.allclose(jacobian.T @ wave, gradient, atol=1e-9)
    return wave, q0


def intersect(rays):
    distance = np.full(rays.shape[:-1], np.inf)
    owner = np.full(rays.shape[:-1], -1)
    for index, face in enumerate(FACES):
        corners = np.array(GEOMETRY.surfaces[face].corners)
        right, up = corners[1] - corners[0], corners[3] - corners[0]
        normal = np.cross(right, up)
        denominator = rays @ normal
        safe = np.where(abs(denominator) > 1e-10, denominator, 1e-10)
        t = ((corners[0] - EYE) @ normal) / safe
        local = rays * t[..., None] + EYE - corners[0]
        x, y = (local @ right) / (right @ right), (local @ up) / (up @ up)
        valid = (t > 0) & (t < distance) & (x >= 0) & (x <= 1) & (y >= 0) & (y <= 1)
        distance[valid], owner[valid] = t[valid], index
    return owner


def views():
    width, height = 1000, 490
    extent = np.tan(np.radians(75))
    x, y = np.meshgrid(np.linspace(-extent, extent, width),
                       np.linspace(extent * height / width, -extent * height / width, height))
    perspective = FORWARD + x[..., None] * RIGHT + y[..., None] * UP
    az, el = np.meshgrid(np.linspace(-np.pi, np.pi, width),
                         np.linspace(np.pi / 2, -np.pi / 2, 250))
    panorama = np.stack((np.sin(az) * np.cos(el), -np.cos(az) * np.cos(el),
                         np.sin(el)), axis=-1)
    return ((perspective, intersect(perspective)), (panorama, intersect(panorama)))


def panel(rays, owner, mode, seconds):
    q, valid = coordinates(rays, mode)
    wave, origin = field(mode)
    phase = (q - origin) @ wave - 4 * seconds
    if RUNTIME_PLAN is not None:
        layers = {str(layer.setting.space.mappings[0].surface_id).title(): layer
                  for layer in RUNTIME_PLAN.seek(round(seconds * 1e9))}
        for index, face in enumerate(FACES):
            corners = np.array(GEOMETRY.surfaces[face].corners)
            right, up = corners[1] - corners[0], corners[3] - corners[0]
            normal = np.cross(right, up)
            mask = owner == index
            ray = rays[mask]
            distance = ((corners[0] - EYE) @ normal) / (ray @ normal)
            local = distance[:, None] * ray + EYE - (corners[0] + corners[2]) / 2
            x, y = (local @ right) / np.linalg.norm(right), (local @ up) / np.linalg.norm(up)
            values = layers[face].values
            a, b, c = (values[f"grating_numerator_{i}"] for i in range(3))
            d, e, f = (values[f"grating_denominator_{i}"] for i in range(3))
            depth = d * x + e * y + f
            valid[mask] = depth > 1e-6
            phase[mask] = (a * x + b * y + c) / np.where(depth > 1e-6, depth, 1) + values["grating_offset"]
    # Soft edges reduce diagnostic raster aliasing without changing the field phase.
    level = (255 * np.clip(0.5 + 4 * np.cos(2 * np.pi * phase), 0, 1)).astype(np.uint8)
    rgb = np.full((*owner.shape, 3), BG, dtype=np.uint8)
    active = (owner >= 0) & valid
    rgb[active] = level[active, None]
    rgb[(owner >= 0) & ~valid] = (93, 64, 28)
    edge = ((owner != np.roll(owner, 1, axis=0)) | (owner != np.roll(owner, 1, axis=1)))
    rgb[edge & (owner >= 0)] = AMBER
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    for index, face in enumerate(FACES):
        ys, xs = np.where(owner == index)
        if len(xs) < 100:
            continue
        x, y = int(np.median(xs)), int(np.median(ys))
        draw.rectangle((x - 40, y - 12, x + 40, y + 12), fill=BG)
        draw.text((x, y), face, font=SMALL, fill=AMBER, anchor="mm")
    return image


def render(mode, seconds, samples):
    image = Image.new("RGB", (1040, 930), BG)
    draw = ImageDraw.Draw(image)
    title = "A | One forward-facing flat sheet" if mode == "forward" else "B | One surrounding angular panorama"
    draw.text((20, 15), title, font=FONT, fill=AMBER)
    draw.text((20, 46), "SUBJECT EYE | looking forwards and 30 degrees down | wide-angle view", font=SMALL, fill="white")
    image.paste(panel(*samples[0], mode, seconds), (20, 72))
    draw.text((20, 579), "360-DEGREE OVERVIEW | rear / left / front / right / rear", font=SMALL, fill="white")
    image.paste(panel(*samples[1], mode, seconds), (20, 606))
    note = ("Brown: screen area outside the forward projection. Rear areas receive no image."
            if mode == "forward" else "Wrap at rear; angular mapping has a bottom pole. Pole/seam handling remains open.")
    draw.text((20, 871), note, font=SMALL, fill=AMBER)
    status = "Runtime field" if RUNTIME_PLAN is not None else "Concept only"
    draw.text((20, 897), status + " | Bottom 45 deg, 5 mm / 20 mm/s locally at centre | motion 1/4 speed",
              font=SMALL, fill="white")
    return image


if __name__ == "__main__":
    if "--runtime" in sys.argv:
        from cephvr.gui.rig_parameter_edits import patch_setting
        from cephvr.gui.trial_preview_plan import PreviewPlan
        from cephvr.visual_stimulus.config.models.program_model import Program

        protocol = json.loads(Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/gratings_protocol.json").read_text())
        data = protocol["trials"][protocol["selected_trial"]]["program"]
        epoch = data["sequence"][0]["body"][0]
        epoch["repetition_rules"] = []
        source = next(s for s in epoch["settings"] if s.get("linked_to") is None)
        patch_setting(source, {"Orientation": "45", "Speed": "20"})
        RUNTIME_PLAN = PreviewPlan(Program.model_validate_json(json.dumps(data)), GEOMETRY.artifact().display.geometry)
    samples = views()
    assert all(np.any(owner == index) for _, owner in samples for index in range(4))
    for mode in (("forward",) if RUNTIME_PLAN is not None else ("forward", "panorama")):
        label = "implemented" if RUNTIME_PLAN is not None else "concept"
        first = render(mode, 0, samples)
        first.save(ROOT / f"subject-{mode}-{label}.png")
        frames = [first] + [render(mode, index / 100, samples) for index in range(1, 25)]
        assert first.tobytes() != frames[12].tobytes()
        first.save(ROOT / f"subject-{mode}-{label}.gif", save_all=True,
                   append_images=frames[1:], duration=40, loop=0)
    print("Concept comparisons rendered; production and saved settings unchanged.")
