"""Give each dummy grating an explicit surface-local physical mapping."""
import copy
import json
import math
from pathlib import Path

from google.protobuf.json_format import MessageToJson

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.config.models.program_model import Program

root = Path(__file__).resolve().parent
candidate_path = root / "dummy-candidate.pb"
backup = root / "dummy-candidate-original-angular.pb"
if not backup.exists():
    backup.write_bytes(candidate_path.read_bytes())
candidate = pb.ExperimentConfiguration.FromString(candidate_path.read_bytes())
program = json.loads(candidate.trials[0].stimulus.program.program_json)
profile = json.loads(
    next(b.visual_stimulus.display.profile_json for b in candidate.backends
         if b.backend_name == "visual_stimulus")
)
template = program["sequence"][1]["settings"][0]
settings = []
for surface in profile["geometry"]["surfaces"]:
    patch = copy.deepcopy(template)
    patch["instance_id"] = "dummy_" + surface["surface_id"]
    patch["space"] = {
        "kind": "physical_surface", "frame_id": profile["geometry"]["frame_id"],
        "mappings": [{"surface_id": surface["surface_id"],
                      "matrix": [[1, 0, 0], [0, 1, 0]]}],
    }
    width = math.dist(surface["bottom_left_mm"], surface["bottom_right_mm"])
    height = math.dist(surface["bottom_left_mm"], surface["top_left_mm"])
    patch["initial"] = {"x": width / 2, "y": height / 2, "rotation_deg": 0}
    patch["width"]["value"] = width
    patch["height"]["value"] = height
    patch["pattern"]["frequency"]["value"] = 0.05
    settings.append(patch)
program["instances"] = [{"instance_id": s["instance_id"], "family": "texture"}
                        for s in settings]
program["scenes"][1]["layer_instance_ids"] = [s["instance_id"] for s in settings]
program["sequence"][1]["settings"] = settings
validated = Program.model_validate_json(json.dumps(program))
candidate.trials[0].stimulus.program.program_json = validated.model_dump_json()
candidate_path.write_bytes(candidate.SerializeToString())
(root / "dummy-candidate.json").write_text(MessageToJson(candidate), encoding="utf-8")
(root / "dummy-assets/dummy_protocol.json").write_text(
    validated.model_dump_json(indent=2) + "\n", encoding="utf-8"
)
print("Four surface-local dummy gratings validated; duration remains 60 seconds.")
