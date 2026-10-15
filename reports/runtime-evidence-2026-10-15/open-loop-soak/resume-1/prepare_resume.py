"""Fresh saved settings and latest GUI calibration; no hardware mutation."""

from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

from google.protobuf.json_format import MessageToDict, ParseDict

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.calibration_profile import AssignedDisplay, MonitorBinding, diagnostic_display_profile
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

OUT = Path(__file__).resolve().parent
OLD = OUT.parent
ROOT = OLD.parents[2]
PEDRO = Path(r"C:\Users\ReiterU_PC\Desktop\Pedro")
gui_backup = OUT / "runtime_gui.json"
if not gui_backup.exists():
    shutil.copy2(ROOT / "config/runtime_gui.json", gui_backup)
gui = json.loads(gui_backup.read_text())["projectors"]
cache = Path(r"C:\Users\ReiterU_PC\AppData\Local\CephVR\calibration\dc327f2d29bec448\frame_grid\calibration")
if not (OUT / "calibration-cache-before").exists():
    shutil.copytree(cache, OUT / "calibration-cache-before")
if not (OUT / "pedro-calibration-before").exists():
    shutil.copytree(PEDRO / "calibration", OUT / "pedro-calibration-before")
monitors = tuple(MonitorBinding(**row) for row in json.loads((OUT / "preflight.json").read_text())["displays"])
assignments = []
for interface, face in gui["assignments"].items():
    monitor = next(m for m in monitors if m.interface.casefold() == interface.casefold())
    assignments.append(AssignedDisplay(face, monitor.x, monitor.y, monitor.width, monitor.height,
                                       gui["participation"][interface], interface))
calibration = dict(format=gui["configuration"]["format"], version=8, values=gui["configuration"]["values"])
display, meshes = diagnostic_display_profile(calibration, tuple(assignments), monitors)
payload = display.model_dump(mode="json")
media = PEDRO / "media/calibration/open-loop-resume-1"
media.mkdir(parents=True, exist_ok=True)
for mapping in payload["mappings"]:
    face = mapping["surface_id"]
    path = media / f"diagnostic_{face}.json"
    value = meshes[face].model_dump_json(indent=2) + "\n"
    if path.exists():
        assert path.read_text() == value
    else:
        path.write_text(value)
    mapping["geometric_profile"]["logical_path"] = path.relative_to(PEDRO).as_posix()
display = DisplayProfile.model_validate_json(json.dumps(payload))
(OUT / "display-profile.json").write_text(display.model_dump_json(indent=2))
saved = json.loads((OUT / "last_configuration.json").read_text())
base = ParseDict(saved["configuration"], pb.ExperimentConfiguration())
original_pb = OUT / "original-configuration.pb"
if original_pb.exists():
    assert original_pb.read_bytes() == base.SerializeToString()
else:
    original_pb.write_bytes(base.SerializeToString())
(OUT / "imported-configuration.pb").write_bytes(base.SerializeToString())
base.mode = pb.SESSION_MODE_OPEN_LOOP
base.subject = "DUMMY"
base.experiment = "open_loop_resume1_20261015"
for backend in base.backends:
    backend.enabled = backend.backend_name in {"acquisition", "visual_stimulus"}
    if backend.backend_name == "tracking":
        backend.tracking.save_tracking_data = False
visual = next(b.visual_stimulus for b in base.backends if b.backend_name == "visual_stimulus")
visual.display.profile_json = display.model_dump_json()
visual.save_visual_stimulus_data = True
acquisition = next(b.acquisition for b in base.backends if b.backend_name == "acquisition")
for field in ("behavioral", "tracking", "eye_tracking"):
    camera = getattr(acquisition, field)
    assert camera.enabled
    camera.save_video = True
spec = importlib.util.spec_from_file_location("original_preparation", OLD / "prepare.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for label, seconds in (("combined120", 120), ("combined900", 900)):
    candidate = pb.ExperimentConfiguration.FromString(base.SerializeToString())
    del candidate.trials[1:]
    del candidate.gaps[:]
    program = module.program(seconds, "combined", display)
    candidate.trials[0].stimulus.program.program_json = program.model_dump_json()
    candidate.trials[0].stimulus.program.logical_source_reference = str(OUT / f"program-{label}.json")
    candidate.trials[0].stimulus.stimulus_seed_decimal = "17015"
    candidate.trials[0].stimulus.arena_boundaries.boundaries_json = json.dumps(dict(format_version=1, bindings=[dict(instance_id="arena", world_frame_id="arena-mm", region=dict(kind="unrestricted"))]))
    (OUT / f"program-{label}.json").write_text(program.model_dump_json(indent=2))
    (OUT / f"candidate-{label}.pb").write_bytes(candidate.SerializeToString())
    (OUT / f"candidate-{label}.json").write_text(json.dumps(MessageToDict(candidate, preserving_proto_field_name=True), indent=2))
record = dict(scope="Latest GUI values + native identities; new unique test mesh paths; originals/caches preserved. Physical calibration unverified.",
              gui_projectors=gui, assignments=[asdict(row) for row in assignments],
              source_files=[dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (OUT / "last_configuration.json", gui_backup)],
              test_mesh_files=[dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in media.glob("*.json")],
              source_presentation=gui["configuration"]["settings"], adopted_presentation=display.presentation_mode)
(OUT / "preparation.json").write_text(json.dumps(record, indent=2))
print(OUT / "preparation.json")
