"""Read-only compilation probe; does not open devices or perform Setup."""

import hashlib
import json
import tomllib
from dataclasses import replace
from pathlib import Path

from tests.visual_stimulus.support import make_compile_context

from cephvr.visual_stimulus.compiler import compile_trial, serialize_prepared_trial
from cephvr.visual_stimulus.config.models.display_profile import parse_display_json
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.configuration import load_file_policies

root = Path.cwd()
path = Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/sparse-noise_20mins_protocol.json")
raw = path.read_bytes()
source = json.dumps(json.loads(raw)["trials"][0]["program"])
program = Program.model_validate_json(source)
saved = json.loads((root / "config/last_configuration.json").read_text("utf-8"))
settings = next(
    b["visual_stimulus"]
    for b in saved["configuration"]["backends"]
    if b["backend_name"] == "visual_stimulus"
)
context = replace(
    make_compile_context(source),
    display=parse_display_json(settings["display"]["profile_json"], max_bytes=16_777_216),
)
limits = load_file_policies(root).limits
transport_limit = tomllib.loads(
    (root / "config/backends/experiment_config.toml").read_text("utf-8")
)["rpc"]["max_message_bytes"]
try:
    compile_trial(
        program, context, max_expanded_epochs=limits.max_expanded_epochs,
        max_prepared_plan_bytes=8_388_608,
    )
except ValueError as exc:
    print("old ceiling rejected:", exc)
else:
    raise AssertionError("Old ceiling should reproduce the reported rejection")
plan = compile_trial(
    program, context, max_expanded_epochs=limits.max_expanded_epochs,
    max_prepared_plan_bytes=limits.max_prepared_plan_bytes,
)
data = serialize_prepared_trial(plan)
assert len(data) <= limits.max_prepared_plan_bytes < transport_limit
print(json.dumps({
    "protocol_sha256": hashlib.sha256(raw).hexdigest(),
    "epochs": len(plan.epochs),
    "settings_records": sum(len(e.settings) for e in plan.epochs),
    "duration_ns": plan.epochs[-1].end_ns,
    "artifact_bytes": len(data),
    "ceiling_bytes": limits.max_prepared_plan_bytes,
    "transport_limit_bytes": transport_limit,
    "transport_headroom_bytes": transport_limit - len(data),
}, indent=2))
