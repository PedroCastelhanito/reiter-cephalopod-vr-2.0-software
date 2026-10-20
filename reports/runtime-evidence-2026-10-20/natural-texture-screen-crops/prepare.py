"""Reproduce the owner's calibrated crops and separate four-trial protocol, without devices."""

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from PIL import Image

from cephvr.gui.protocol_snapshot import validate_protocol
from cephvr.visual_stimulus.compiler.expansion import expand_program
from cephvr.visual_stimulus.config.models.program_model import parse_program_json

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PEDRO = Path(r"C:\Users\ReiterU_PC\Desktop\Pedro")
SOURCE = Path(r"C:\Users\ReiterU_PC\Desktop\Alsu\media")
MEDIA = PEDRO / "media"
FACES = ("Left", "Front", "Right", "Bottom")
CALIBRATION = PEDRO / "projectors_config.json"
VALUES = json.loads(CALIBRATION.read_text())["values"]
SIZES = {
    face: tuple(int(VALUES[f"screens.{face}.valid_{axis}_px"])
                for axis in ("width", "height"))
    for face in FACES
}
COLOR = dict(transfer="srgb", primaries="rec709_d65", range="full",
             matrix="rgb", chroma_location="none",
             reason="Untagged grayscale originals interpreted as full-range sRGB; crop sample values preserved.")


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Different output already exists: {path}")
    else:
        path.write_bytes(data)


def json_bytes(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def crop_boxes(width, height):
    # Center a contiguous cross; align the wall bottoms and center Bottom on Front.
    span = sum(SIZES[f][0] for f in FACES[:3])
    wall_height = max(SIZES[f][1] for f in FACES[:3])
    x = (width - span) // 2
    seam = (height - wall_height - SIZES["Bottom"][1]) // 2 + wall_height
    boxes = {}
    for face in FACES[:3]:
        w, h = SIZES[face]
        boxes[face] = (x, seam - h, x + w, seam)
        x += w
    w, h = SIZES["Bottom"]
    front = boxes["Front"]
    x = (front[0] + front[2] - w) // 2
    boxes["Bottom"] = (x, seam, x + w, seam + h)
    assert all(0 <= a < c <= width and 0 <= b < d <= height
               for a, b, c, d in boxes.values())
    return boxes


def constant(value):
    return {"kind": "constant", "value": value}


def epoch(name, scene, settings):
    return dict(kind="epoch", epoch_id=name, scene_id=scene,
                duration={"kind": "fixed", "duration": {"seconds": "0.3"}},
                settings=settings)


def main():
    runtime = json.loads((ROOT / "config/runtime_gui.json").read_text())
    assert runtime["projectors"]["configuration"]["values"] == VALUES
    base = {"format": "cephvr-protocol-config", "version": 1,
            "mode": "Open-loop", "asset_root": str(MEDIA),
            "selected_trial": 0, "trials": []}
    verification = {"date": "2026-10-20", "calibration_sha256": hashlib.sha256(
        CALIBRATION.read_bytes()).hexdigest(), "screen_pixels": SIZES,
        "crop_policy": "Centered contiguous Left-Front-Right cross, Bottom centered below Front. Native pixels; no resize, warp, flip, contrast change or synthesis.",
        "grey": {"srgb_code": 127, "linear_rgb": ((127/255 + .055)/1.055)**2.4},
        "collections": {}}
    for collection, folder, seed in (
        ("primate", "primate_3640x2110", 202610201),
        ("cuttlebase", "Cuttlebase_3640x2110", 202610202),
    ):
        files = sorted((SOURCE / folder).rglob("*.png"))
        assert len(files) == 240
        manifest = {"source_root": str(SOURCE), "seed": seed,
                    "calibration_sha256": verification["calibration_sha256"],
                    "crop_policy": verification["crop_policy"], "images": []}
        assets = []
        for index, source in enumerate(files):
            record = {"source": str(source.relative_to(SOURCE)),
                      "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                      "screens": {}}
            with Image.open(source) as original:
                assert original.size == (3640, 2110) and original.mode == "L"
                boxes = crop_boxes(*original.size)
                for face in FACES:
                    path = MEDIA / collection / f"{source.stem}_{face}.png"
                    crop = original.crop(boxes[face])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not path.exists():
                        crop.save(path, format="PNG")
                    with Image.open(path) as saved:
                        assert saved.size == SIZES[face] and saved.mode == "L"
                        assert saved.tobytes() == crop.tobytes(), path
                    asset_id = f"image_{index:03d}_{face.lower()}"
                    assets.append(dict(asset_id=asset_id,
                        logical_path=path.relative_to(MEDIA).as_posix(),
                        color_override=COLOR, profile="png_uint_v1"))
                    record["screens"][face] = dict(file=path.name, box=boxes[face],
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            manifest["images"].append(record)
            if (index+1) % 40 == 0:
                print(f"{collection}: {index+1}/240 originals, four crops each verified", flush=True)
        rng = random.Random(seed)
        schedule = list(range(240)) * 8 + rng.sample(range(240), 80)
        rng.shuffle(schedule)
        counts = Counter(schedule)
        assert len(schedule) == 2000 and Counter(counts.values()) == {8: 160, 9: 80}
        manifest["presentation_order_source_indices"] = schedule
        write_new(MEDIA / collection / "manifest.json", json_bytes(manifest))
        group_id = collection + "_presentations"
        settings = []
        for face in FACES:
            prefix = f"screens.{face}."
            width, height = (SIZES[face][i] * VALUES[prefix+f"reference_{axis}_mm"] /
                             VALUES[prefix+f"reference_{axis}_px"]
                             for i, axis in enumerate(("x", "y")))
            # Bottom's portrait image axes are the calibrated surface axes rotated 90 degrees.
            matrix = [[0., -1., 0.], [1., 0., 0.]] if face == "Bottom" else [[1., 0., 0.], [0., 1., 0.]]
            settings.append(dict(kind="image", instance_id=face.lower(),
                asset_id={"kind": "condition", "group_id": group_id, "column_id": face.lower()},
                sampling="nearest", fit="stretch",
                space={"kind": "physical_surface", "frame_id": "rig", "mappings": [
                    {"surface_id": face.lower(), "matrix": matrix}]},
                initial={"x": 0., "y": 0., "rotation_deg": 0.},
                width=constant(width), height=constant(height), opacity=constant(1.),
                motion={axis: {"kind": "hold"} for axis in ("x", "y", "rotation")},
                reset=True, assignments=[], feedback=[]))
        grey = verification["grey"]["linear_rgb"]
        program = dict(format_version=2, assets=assets,
            instances=[dict(instance_id=f.lower(), family="image") for f in FACES],
            scenes=[dict(scene_id="texture", background_linear_rgb=[grey]*3,
                         arena_instance_id=None, layer_instance_ids=[f.lower() for f in FACES]),
                    dict(scene_id="grey", background_linear_rgb=[grey]*3,
                         arena_instance_id=None, layer_instance_ids=[])],
            input_channels=[], duration={"kind": "explicit_epochs"}, sequence=[
                dict(kind="group", group_id=group_id, repetitions=1, order="as_listed",
                     order_unit="condition_rows", conditions={
                         "columns": [dict(column_id=f.lower(), value_type="asset_id", unit=None) for f in FACES],
                         "rows": [dict(row_id=f"presentation_{n:04d}", cells=[
                             dict(column_id=f.lower(), value=f"image_{i:03d}_{f.lower()}") for f in FACES])
                             for n, i in enumerate(schedule)]},
                     body=[epoch("Texture_300ms", "texture", settings), epoch("Grey_300ms", "grey", [])])])
        trial = dict(name=f"{collection.title()} - 20 minutes", path="", program=program,
                     stimulus_seed_decimal=str(seed), gap_after_seconds="0",
                     arena_boundaries_json='{"format_version":1,"bindings":[]}')
        parsed = parse_program_json(json.dumps(program), max_bytes=32*1024*1024)
        expanded = expand_program(parsed, seed_decimal=str(seed), max_expanded_epochs=100000)
        assert len(expanded) == 4000
        assert sum(e.source.duration.duration.ns() for e in expanded) == 1200_000_000_000
        for n, item in enumerate(expanded):
            assert item.source.scene_id == ("texture" if n % 2 == 0 else "grey")
            if n % 2 == 0:
                assert {s.asset_id.rsplit("_",1)[0] for s in item.settings} == {f"image_{schedule[n//2]:03d}"}
        # Two ten-minute blocks keep expanded artifacts below the existing 8 MiB cap.
        for block in range(2):
            block_trial = json.loads(json.dumps(trial))
            block_trial["name"] = f"{collection.title()} - Part {block+1} - 10 minutes"
            group = block_trial["program"]["sequence"][0]
            group["conditions"]["rows"] = group["conditions"]["rows"][block*1000:(block+1)*1000]
            base["trials"].append(block_trial)
        verification["collections"][collection] = dict(originals=240, crops=960,
            epochs=4000, duration_seconds=1200, trial_blocks=2, seconds_per_block=600, repetition_counts=dict(Counter(counts.values())),
            seed=seed, pixel_equality="All saved crops match source boxes exactly")
    base["trials"][-1]["gap_after_seconds"] = ""
    validate_protocol(base)
    output = PEDRO / "primate_cuttlebase_40min.json"
    write_new(output, json_bytes(base))
    validate_protocol(json.loads(output.read_text()))
    verification.update(protocol=str(output), protocol_bytes=output.stat().st_size,
        total_seconds=2400, separate_session=True,
        validation="GUI validator, canonical parsing, full expansion, durations, grouping, frequencies and pixel equality passed",
        limits="No GUI load, full Setup/resource preparation or physical playback performed.")
    write_new(EVIDENCE / "verification.json", json_bytes(verification))
    print(json.dumps(verification, indent=2), flush=True)


if __name__ == "__main__":
    main()
