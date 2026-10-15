"""Build reviewable open-loop test copies; never open hardware or adopt settings."""

import copy
import hashlib
import json
import math
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.controller.configuration import load_controller_configuration
from cephvr.control.v1 import types_pb2 as pb
from cephvr.acquisition.v1 import camera_pb2
from cephvr.gui.calibration_profile import AssignedDisplay, MonitorBinding, diagnostic_display_profile
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.texture_links import validate_spin_pivot
from cephvr.visual_stimulus.config.models.program_model import Program

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
PEDRO = Path(r"C:\Users\ReiterU_PC\Desktop\Pedro")


def constant(value):
    return {"kind": "constant", "value": value}


def rate(value):
    return {"kind": "rate", "function": constant(value)}


def program(seconds, selection="combined", display=None):
    hold = {"kind": "hold"}
    settings = []
    sizes = {"front": (94, 85), "left": (126, 85), "right": (126, 85), "bottom": (94, 126)}
    for face, (width, height) in sizes.items():
        settings.append(dict(
            kind="texture", instance_id=face, linked_to=None if face == "bottom" else "bottom",
            space=dict(kind="physical_surface", frame_id="rig-mm", mappings=[dict(surface_id=face, matrix=[[1, 0, 0], [0, 1, 0]])]),
            initial=dict(x=0, y=0, rotation_deg=0), width=constant(1000), height=constant(1000),
            opacity=constant(1), motion=dict(x=hold, y=hold, rotation=hold), reset=True, assignments=[], feedback=[],
            pattern=dict(kind="image_tile", asset_id="gaussian35", period_x=constant(104), period_y=constant(104), sampling="linear"),
            initial_phase_x_cycles=0, initial_phase_y_cycles=0, phase_x=hold,
            phase_y=rate(-0.2) if face == "bottom" else hold,
            mean_linear_rgb=[0.5] * 3, modulation_linear_rgb=[0.5] * 3, contrast=constant(1)))
    rotation = copy.deepcopy(settings)
    for item in rotation:
        item["phase_y"] = hold
        if item["instance_id"] == "bottom":
            item["motion"]["rotation"] = rate(8)
            if display is None:
                raise RuntimeError("Final actual display geometry required for spin pivot")
            surface = next(s for s in display.geometry.surfaces if s.surface_id == "bottom")
            origin = surface.bottom_left_mm
            relative = [a - b for a, b in zip(display.geometry.observer_mm, origin)]
            for axis, corner in (("x", surface.bottom_right_mm), ("y", surface.top_left_mm)):
                extent = math.dist(origin, corner)
                unit = [(a - b) / extent for a, b in zip(corner, origin)]
                item["initial"][axis] = sum(a * b for a, b in zip(relative, unit)) - extent / 2
    arena = dict(kind="arena", instance_id="arena", asset_id="circular", world_frame_id="arena-mm",
                 asset_to_world=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                 initial=dict(position_mm=[0, 0], yaw_deg=0), fixed_height_mm=0, fixed_pitch_deg=0, fixed_roll_deg=0,
                 motion=dict(x=hold, y=hold, yaw=rate(12)), reset=True, assignments=[], feedback=[])
    epochs = []
    for name, scene, values, duration in (("linked_translation", "textures", settings, seconds // 3),
                                           ("linked_rotation", "textures", rotation, seconds // 3),
                                           ("arena_rotation", "arena", [arena], seconds - 2 * (seconds // 3))):
        epochs.append(dict(kind="epoch", epoch_id=name, scene_id=scene, duration=dict(kind="fixed", duration=dict(seconds=str(duration))), settings=values))
    if selection == "textures":
        epochs = epochs[:2]
        for epoch in epochs:
            epoch["duration"]["duration"]["seconds"] = str(seconds // 2)
    elif selection == "arena":
        epochs = epochs[2:]
        epochs[0]["duration"]["duration"]["seconds"] = str(seconds)
    value = dict(format_version=2,
        assets=[dict(asset_id="gaussian35", logical_path="media/textures/gaussian-noise/GaussianNoise_scale_35_primary_color_0.7_secondary_color_0.00.texture.json", color_override=None, profile="cephvr1_texture_json_v1"),
                dict(asset_id="circular", logical_path="media/arenas/open-loop-engineering/arena-unlit-engineering.glb", color_override=None, profile="glb2_static_unlit_v1")],
        instances=[dict(instance_id=face, family="texture") for face in sizes] + [dict(instance_id="arena", family="arena")],
        scenes=[dict(scene_id="textures", background_linear_rgb=[0, 0, 0], arena_instance_id=None, layer_instance_ids=list(sizes)),
                dict(scene_id="arena", background_linear_rgb=[0, 0, 0], arena_instance_id="arena", layer_instance_ids=[])],
        input_channels=[], duration=dict(kind="explicit_epochs"), sequence=epochs)
    if selection == "textures":
        value["assets"] = value["assets"][:1]
        value["instances"] = value["instances"][:-1]
        value["scenes"] = value["scenes"][:1]
    elif selection == "arena":
        value["assets"] = value["assets"][1:]
        value["instances"] = value["instances"][-1:]
        value["scenes"] = value["scenes"][1:]
    result = Program.model_validate_json(json.dumps(value))
    for epoch in result.sequence:
        for setting in epoch.settings:
            if getattr(setting, "instance_id", "") == "bottom":
                validate_spin_pivot(setting, display.geometry, (setting.initial.x, setting.initial.y))
    return result


def main():
    backup = OUT / "original-configuration.pb"
    saved_backup = OUT / "original-last-configuration.json"
    if backup.exists() != saved_backup.exists():
        raise RuntimeError("Incomplete immutable original backup set")
    if backup.exists():
        original = pb.ExperimentConfiguration.FromString(backup.read_bytes())
    else:
        original = load_controller_configuration(ROOT).configuration
        backup.write_bytes(original.SerializeToString())
        saved_backup.write_bytes((ROOT / "config/last_configuration.json").read_bytes())
    cameras = json.loads((PEDRO / "cameras_config.json").read_text())
    mcu = json.loads((PEDRO / "microcontroller_config.json").read_text())
    base = type(original).FromString(original.SerializeToString())
    base.subject = "DUMMY"
    base.experiment = "open_loop_soak_20261015"
    base.recording_root = str(PEDRO / "open-loop-recordings-20261015")
    base.asset_root = str(PEDRO)
    base.mode = pb.SESSION_MODE_OPEN_LOOP
    for backend in base.backends:
        backend.enabled = backend.backend_name in {"acquisition", "visual_stimulus"}
    acq = next(b.acquisition for b in base.backends if b.backend_name == "acquisition")
    roles = {"Behavior cam": "behavioral", "Tracking cam": "tracking", "Eye tracking": "eye_tracking"}
    for row in cameras["cameras"]:
        role = roles[row["role"]]
        camera, pulse = getattr(acq, role), getattr(acq.pulses, role)
        assert camera.device.device_id == row["serial"]
        camera.enabled, camera.save_video = row["enabled"], True
        values = row["values"]
        frequency = float(values["trigger_frequency_hz"])
        pulse.requested_frequency_hz = frequency
        pin = mcu["camera_pins"]["camera-" + row["serial"]]
        if pin:
            pulse.pin = pin
        else:
            pulse.ClearField("pin")
        if values["trigger_clock"] == "Internal clock":
            camera.device.frame_timing = camera_pb2.FRAME_TIMING_FREE_RUNNING
            camera.device.unaligned_free_running = True
            camera.device.settings.frame_rate_hz = frequency
            camera.device.settings.ClearField("trigger_source")
            camera.device.settings.ClearField("trigger_activation")
        else:
            camera.device.frame_timing = camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
            camera.device.unaligned_free_running = False
            camera.device.settings.trigger_source = values["trigger_source"]
    acq.pulses.port = mcu["port"]
    acq.pulses.trial_state_pin = mcu["trial_state"]["pin"]
    acq.pulses.trial_state_enabled = mcu["trial_state"]["enabled"]
    acq.pulses.projector_flip_enabled = False
    old_profile = json.loads(next(b.visual_stimulus.display.profile_json for b in base.backends if b.backend_name == "visual_stimulus"))
    monitors = tuple(MonitorBinding(**row) for row in json.loads((OUT / "displays.json").read_text()))
    assignments = []
    for mapping in old_profile["mappings"]:
        output = next(o for o in old_profile["outputs"] if o["output_id"] == mapping["output_id"])
        monitor = next(m for m in monitors if m.interface.casefold() == output["device_identity"].casefold())
        assignments.append(AssignedDisplay(mapping["surface_id"].title(), monitor.x, monitor.y, monitor.width, monitor.height, True, monitor.interface))
    calibration = json.loads((PEDRO / "projectors_config.json").read_text())
    # ProjectorFiles.validate maps the v11 envelope to calibration-values v8.
    calibration = dict(format=calibration["format"], version=8, values=calibration["values"])
    display, meshes = diagnostic_display_profile(calibration, tuple(assignments), monitors)
    destination = OUT / "display-assets" / "calibration"
    destination.mkdir(parents=True, exist_ok=True)
    for face, mesh in meshes.items():
        (destination / f"diagnostic_{face}.json").write_text(mesh.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (OUT / "display-profile.json").write_text(display.model_dump_json(indent=2) + "\n", encoding="utf-8")
    next(b.visual_stimulus for b in base.backends if b.backend_name == "visual_stimulus").display.profile_json = display.model_dump_json()
    # Device settings are test copies. Actual PFS import/readback precedes adoption.
    for label, seconds, selection in (("textures60", 60, "textures"), ("arena60", 60, "arena"), ("combined60", 60, "combined"), ("combined120", 120, "combined"), ("combined900", 900, "combined")):
        value = type(base).FromString(base.SerializeToString())
        del value.trials[1:]
        del value.gaps[:]
        authored = program(seconds, selection, display)
        value.trials[0].stimulus.program.program_json = authored.model_dump_json()
        value.trials[0].stimulus.program.logical_source_reference = str(OUT / f"program-{label}.json")
        value.trials[0].stimulus.stimulus_seed_decimal = "17015"
        value.trials[0].stimulus.arena_boundaries.boundaries_json = json.dumps(dict(format_version=1, bindings=[] if selection == "textures" else [dict(instance_id="arena", world_frame_id="arena-mm", region=dict(kind="unrestricted"))]))
        (OUT / f"program-{label}.json").write_text(authored.model_dump_json(indent=2) + "\n", encoding="utf-8")
        (OUT / f"candidate-{label}.pb").write_bytes(value.SerializeToString())
        (OUT / f"candidate-{label}.json").write_text(json.dumps(MessageToDict(value, preserving_proto_field_name=True), indent=2) + "\n", encoding="utf-8")
    files = [OUT / "prepare.py", OUT / "original-last-configuration.json", *OUT.glob("program-*.json"), *OUT.glob("candidate-*.pb")]
    (OUT / "preparation.json").write_text(json.dumps(dict(scope="offline copies, no device import/adoption; display profile uses actual native identities plus supplied Pedro geometry, optical calibration unverified; all_outputs_vsync test override", files=[dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]), indent=2) + "\n", encoding="utf-8")
    print("Built60s and900s test copies; actual device/PFS/display validation remains pending.")


if __name__ == "__main__":
    main()
