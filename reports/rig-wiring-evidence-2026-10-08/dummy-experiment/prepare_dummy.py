"""Create an explicit dummy protocol using retained native rig assignments."""

import json
from pathlib import Path

from PyQt6.QtCore import QSettings
from google.protobuf.json_format import MessageToJson

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.calibration_profile import (
    AssignedDisplay,
    active_monitor_bindings,
    write_diagnostic_bundle,
)
from cephvr.gui.protocol_document import review_program
from cephvr.visual_stimulus.config.models.program_model import Program

OUT = Path(__file__).resolve().parent
assets = OUT / "dummy-assets"
assets.mkdir(exist_ok=True)
calibration_path = Path("C:/Data/projects/reiter-cephalopod-vr/cephvr-assets/rig_geometry.json")
calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
settings = QSettings("CephVR", "Frontend")
saved = json.loads(settings.value("projectors/assignments"))
assignments = saved["assignments"]
monitors = active_monitor_bindings()
rows = []
for identity, face in assignments.items():
    monitor = next(m for m in monitors if m.interface.casefold() == identity.casefold())
    rows.append(AssignedDisplay(face, monitor.x, monitor.y, monitor.width, monitor.height, True))
write_diagnostic_bundle(assets, calibration, tuple(rows), monitors)

document = review_program().model_dump(mode="json")
texture = document["sequence"][1]["settings"][0]
texture["space"]["frame_id"] = "rig-mm"
texture["space"]["surfaces"] = ["left", "front", "right", "bottom"]
document["sequence"][0]["epoch_id"] = "Dummy_baseline"
document["sequence"][1]["epoch_id"] = "Dummy_moving_grating"
document["sequence"][2]["epoch_id"] = "Dummy_recovery"
program = Program.model_validate_json(json.dumps(document))
protocol = assets / "dummy_protocol.json"
protocol.write_text(program.model_dump_json(indent=2) + "\n", encoding="utf-8")

original = pb.Snapshot.FromString((OUT / "original-snapshot.pb").read_bytes())
candidate = pb.ExperimentConfiguration()
candidate.CopyFrom(original.configuration_values.current)
candidate.subject = "DUMMY"
candidate.experiment = "gui_backend_dummy"
candidate.recording_root = str(Path.home() / "Desktop")
candidate.asset_root = str(assets)
candidate.mode = pb.SESSION_MODE_OPEN_LOOP
del candidate.trials[:]
del candidate.gaps[:]
trial = candidate.trials.add(trial_number=1)
trial.stimulus.program.program_json = program.model_dump_json()
trial.stimulus.program.logical_source_reference = str(protocol)
trial.stimulus.stimulus_seed_decimal = "20261008"
acquisition = next(b.acquisition for b in candidate.backends if b.backend_name == "acquisition")
acquisition.behavioral.save_video = True
acquisition.tracking.save_video = True
visual = next((b for b in candidate.backends if b.backend_name == "visual_stimulus"), None)
if visual is None:
    visual = candidate.backends.add(backend_name="visual_stimulus", enabled=True)
visual.enabled = True
visual.visual_stimulus.display.profile_json = (
    assets / "calibration/diagnostic_display_profile.json"
).read_text(encoding="utf-8")
visual.visual_stimulus.save_visual_stimulus_data = True
visual.visual_stimulus.review_ffmpeg_args[:] = acquisition.behavioral.ffmpeg_args.values
tracking = next((b for b in candidate.backends if b.backend_name == "tracking"), None)
if tracking is None:
    tracking = candidate.backends.add(backend_name="tracking", enabled=False)
tracking.enabled = False
tracking.tracking.save_tracking_data = False
(OUT / "dummy-candidate.pb").write_bytes(candidate.SerializeToString())
(OUT / "dummy-candidate.json").write_text(MessageToJson(candidate), encoding="utf-8")
print(json.dumps({"protocol": str(protocol), "output": candidate.recording_root,
                  "scope": "60-second open-loop sine grating; both camera videos and stimulus video; no velocities",
                  "display_calibration": "saved geometry and assignments; diagnostic uncalibrated profiles",
                  "pairing": "pending operator answer"}, indent=2))
