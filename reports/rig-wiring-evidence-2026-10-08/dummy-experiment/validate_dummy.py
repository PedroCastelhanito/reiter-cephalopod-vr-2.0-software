"""Run installed pure proposal validators; never open or start devices."""
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import controller_validators
from cephvr.controller.startup.providers import _installed_validators

OUT = Path(__file__).resolve().parent
candidate = pb.ExperimentConfiguration.FromString((OUT / "dummy-candidate.pb").read_bytes())
results = {}
for name, validate in controller_validators(_installed_validators(OUT.parents[2])).items():
    results[name] = MessageToDict(validate(candidate), preserving_proto_field_name=True)
(OUT / "pure-validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
