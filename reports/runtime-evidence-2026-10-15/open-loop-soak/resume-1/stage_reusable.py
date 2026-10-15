"""Package only independently verified current900 adopted settings; no device access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tomllib

from google.protobuf.json_format import MessageToDict
from cephvr.control.v1 import types_pb2 as pb

out = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--run", type=Path, required=True)
parser.add_argument("--destination", type=Path, required=True)
args = parser.parse_args()
run = args.run.resolve()
assert run.parent == out
events = json.loads((run / "run.json").read_text())["events"]
final = next(row["value"] for row in events if row["label"] == "final")
assert final["session"]["outcome"] == "SESSION_OUTCOME_COMPLETED"
assert final["session"]["cleanup_confirmed"]
assert int(final["trial"]["actual_end_monotonic_ns"]) - int(final["trial"]["start_monotonic_ns"]) == 900_000_000_000
collection = json.loads((run / "collection.json").read_text())
assert collection["collection_complete"] and not collection["errors"]
assert len(collection["videos"]) == 4
for name, video in collection["videos"].items():
    assert video["ffprobe_exit"] == video["decode_exit"] == 0
    assert not video["decode_error"] and not video["ffprobe_error"]
    assert video["ffprobe"]["streams"][0]["nb_read_frames"] == str(27000 if "behavioral_cam" in name else 54000)
operator = run / "operator-config.test.toml"
assert hashlib.sha256(operator.read_bytes()).hexdigest() == json.loads((out / "operator-test-override.json").read_text())["after_sha256"]
settings = tomllib.loads(operator.read_text())
assert settings["resources"]["capture_slots"] == 15
assert settings["resources"]["max_asset_gpu_bytes"] == 1_073_741_824
snapshot = pb.Snapshot.FromString((run / "final.pb").read_bytes())
adopted = snapshot.configuration_values.current
submitted = pb.ExperimentConfiguration.FromString((run / "effective-candidate.pb").read_bytes())
for case in ("combined120", "combined900"):
    candidate = pb.ExperimentConfiguration.FromString((out / f"candidate-{case}.pb").read_bytes())
    assert json.loads((out / f"program-{case}.json").read_text()) == json.loads(candidate.trials[0].stimulus.program.program_json)
    if case == "combined900":
        assert json.loads(candidate.trials[0].stimulus.program.program_json) == json.loads(adopted.trials[0].stimulus.program.program_json)
destination = args.destination.resolve()
destination.mkdir(parents=True, exist_ok=False)
files = []
for case in ("combined120", "combined900"):
    program_path = destination / f"program-{case}.json"
    shutil.copy2(out / program_path.name, program_path)
    candidate = pb.ExperimentConfiguration.FromString((out / f"candidate-{case}.pb").read_bytes())
    value = pb.ExperimentConfiguration.FromString(adopted.SerializeToString())
    value.trials[0].CopyFrom(candidate.trials[0])
    value.trials[0].stimulus.program.logical_source_reference = str(program_path)
    target = destination / f"configuration-{case}.json"
    target.write_text(json.dumps(dict(format_version=1, configuration=MessageToDict(value, preserving_proto_field_name=True)), indent=2))
    files.extend((program_path, target))
test_operator = destination / "visual_stimulus_config.test.toml"
shutil.copy2(operator, test_operator)
files.append(test_operator)
manifest = dict(
    scope="Verified current-calibration open-loop engineering protocols",
    launch=".venv/Scripts/python.exe scripts/start_runtime_gui.py --no-tracking",
    durations_seconds=dict(combined120=120, combined900=900),
    configuration_source="Actual successful900 final adopted configuration; duration variants reuse its device/display settings",
    submitted_matches_adopted=submitted.SerializeToString(deterministic=True) == adopted.SerializeToString(deterministic=True),
    required_operator_overrides=dict(capture_slots=15, max_asset_gpu_bytes=1073741824),
    presentation="Current saved GUI calibration retained; all_outputs_vsync",
    media_root=adopted.asset_root, recording_root=adopted.recording_root,
    evidence=str(run), recordings=final["session"]["directory"],
    preserved_fresh_baseline=str(out),
    limitations=[
        "900s completed and decoded; one stimulus capacity drop at T+0.2947451s, 598 same-slot omissions and 611 CFR duplicates; zero-loss acceptance remains open",
        "Software linking tested; physical projection alignment/photometry not accepted",
        "Camera CFR selection omissions/duplicates differ from capacity loss and native counter continuity",
        "Arena source is a textured circular floor only; structured arena effective_poses empty",
        "Scientific imagery quality and realistic scene-complexity encoding load not established",
        "Rapid reuse crossing retired interrupted boundary remains unproven; local ordering guards tested",
        "Original CQ18 baseline encoders are lossy; any later camera-lossless feasibility is separate evidence",
    ],
    files=[dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in files],
)
(destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
(out / "reusable-files-manifest.json").write_text(json.dumps(manifest, indent=2))
print(destination)
