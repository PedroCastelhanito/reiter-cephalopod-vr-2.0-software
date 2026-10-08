"""Prepare explicit unpaired test and preserve prior validation evidence."""
from pathlib import Path
from google.protobuf.json_format import MessageToJson
from cephvr.control.v1 import types_pb2 as pb

out = Path(__file__).resolve().parent
path = out / "dummy-candidate.pb"
candidate = pb.ExperimentConfiguration.FromString(path.read_bytes())
sync = next((b for b in candidate.backends if b.backend_name == "synchronization"), None)
if sync is None:
    sync = candidate.backends.add(backend_name="synchronization")
sync.enabled = False
for trial in candidate.trials:
    trial.stimulus.arena_boundaries.boundaries_json = '{"format_version":1,"bindings":[]}'
path.write_bytes(candidate.SerializeToString())
(out / "dummy-candidate.json").write_text(MessageToJson(candidate), encoding="utf-8")
config = out.parents[2] / "config/backends/visual_stimulus_config.toml"
original = config.read_bytes().replace(b'pacing_output_id = "calibration_front"', b'# pacing_output_id = "<configured output ID>"')
(out / "original-visual_stimulus_config.toml").write_bytes(original)
validation = out / "pure-validation.json"
if validation.exists():
    (out / "pure-validation-before-pacing.json").write_bytes(validation.read_bytes())
