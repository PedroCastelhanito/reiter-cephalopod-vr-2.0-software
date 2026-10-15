"""Compare all current saved settings before restoring fresh resume baselines."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from google.protobuf.json_format import ParseDict
from cephvr.control.v1 import types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import default_runtime_root

out = Path(__file__).resolve().parent
root = Path.cwd()
parser = argparse.ArgumentParser()
parser.add_argument("--exited-generation", required=True)
parser.add_argument("--last-run", type=Path, required=True)
args = parser.parse_args()
receipt = json.loads((default_runtime_root()/"recovery"/f"application-exit-{args.exited_generation}.json").read_text())
assert receipt["controller_generation"] == args.exited_generation and receipt["all_owned_processes_absent"]
endpoint = _existing_endpoint(default_runtime_root()) if (default_runtime_root() / "launcher.json").exists() else None
assert endpoint is None or endpoint.controller_generation == args.exited_generation
inventory = subprocess.run(["pwsh", "-NoProfile", "-Command", "ConvertTo-Json -InputObject @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'cephvr\\.|start_runtime_gui' } | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine) -Depth 3"], capture_output=True, text=True, check=True)
assert json.loads(inventory.stdout) == []
baselines = {name:(out/name).read_bytes() for name in ("last_configuration.json", "runtime_gui.json", "visual_stimulus_config.toml")}
targets = {name:root/"config"/("backends/"+name if name.endswith(".toml") else name) for name in baselines}
current = {name:path.read_bytes() for name,path in targets.items()}
assert json.loads(current["runtime_gui.json"]) == json.loads(baselines["runtime_gui.json"]), "Independent GUI settings changed; preserve them"
operator = json.loads((out/"operator-test-override.json").read_text())
assert hashlib.sha256(current["visual_stimulus_config.toml"]).hexdigest() in {operator["after_sha256"], operator["before_sha256"]}, "Independent operator settings changed; preserve them"
def configuration(data):
    return ParseDict(json.loads(data)["configuration"], pb.ExperimentConfiguration()).SerializeToString(deterministic=True)
saved = configuration(current["last_configuration.json"])
final = pb.Snapshot.FromString((args.last_run/"final.pb").read_bytes())
assert final.controller_generation == args.exited_generation
candidate = pb.ExperimentConfiguration.FromString((args.last_run/"effective-candidate.pb").read_bytes())
assert saved in {
    configuration(baselines["last_configuration.json"]),
    final.configuration_values.current.SerializeToString(deterministic=True),
    candidate.SerializeToString(deterministic=True),
}, "Independent experiment configuration changed; preserve it"
record = dict(scope="Restore only fresh resume-1 byte baselines after complete compare-before-write; calibration files and Pedro originals untouched", receipt=receipt, files=[])
for name,path in targets.items():
    assert path.read_bytes() == current[name], "Saved file changed after preflight; preserve it"
    path.write_bytes(baselines[name])
    actual = path.read_bytes()
    record["files"].append(dict(path=str(path), before_sha256=hashlib.sha256(current[name]).hexdigest(), baseline_sha256=hashlib.sha256(baselines[name]).hexdigest(), after_sha256=hashlib.sha256(actual).hexdigest(), byte_exact=actual == baselines[name]))
    (out/"saved-files-restoration.json").write_text(json.dumps(record, indent=2))
assert all(row["byte_exact"] for row in record["files"])
print(json.dumps(record, indent=2))
