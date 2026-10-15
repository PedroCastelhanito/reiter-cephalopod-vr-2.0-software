"""Duration-only interrupted-plan derivative for retired-boundary reuse evidence."""
import json
from pathlib import Path

from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.config.models.program_model import Program

out = Path(__file__).resolve().parent
source = json.loads((out / "program-combined120.json").read_text())
value = json.loads(json.dumps(source))
for epoch in value["sequence"]:
    assert epoch["duration"]["duration"]["seconds"] == "40"
    epoch["duration"]["duration"]["seconds"] = "60"
program = Program.model_validate_json(json.dumps(value))
candidate = pb.ExperimentConfiguration.FromString((out / "candidate-combined120.pb").read_bytes())
candidate.trials[0].stimulus.program.program_json = json.dumps(value, separators=(",", ":"))
candidate.trials[0].stimulus.program.logical_source_reference = str(out / "program-combined180.json")
for name, data in (
    ("program-combined180.json", json.dumps(value, indent=2).encode()),
    ("candidate-combined180.pb", candidate.SerializeToString()),
):
    path = out / name
    if path.exists():
        assert path.read_bytes() == data
    else:
        path.write_bytes(data)
print("validated duration-only three60second epochs; original120 and900 preserved")
