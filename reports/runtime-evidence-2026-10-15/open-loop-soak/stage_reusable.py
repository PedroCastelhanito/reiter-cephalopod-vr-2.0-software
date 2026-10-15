"""Save reusable test copies only after completed soak verification."""

import hashlib
import json
from pathlib import Path
import shutil
import tomllib

from google.protobuf.json_format import MessageToDict

from cephvr.control.v1 import types_pb2 as pb

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
RUN = OUT / "combined900-reader-fixed-r2"
events = json.loads((RUN / "run.json").read_text())["events"]
final = next(row["value"] for row in events if row["label"] == "final")
assert final["session"]["outcome"] == "SESSION_OUTCOME_COMPLETED"
assert final["session"]["cleanup_confirmed"]
assert int(final["trial"]["actual_end_monotonic_ns"]) - int(final["trial"]["start_monotonic_ns"]) == 900_000_000_000
collection = json.loads((RUN / "collection.json").read_text())
assert not collection["errors"]
assert collection["collection_complete"]
assert len(collection["videos"]) == 4
for name, video in collection["videos"].items():
    count = 27000 if "behavioral_cam" in name else 54000
    assert video["ffprobe"]["streams"][0]["nb_read_frames"] == str(count)
operator_source = ROOT / "config/backends/visual_stimulus_config.toml"
operator_values = tomllib.loads(operator_source.read_text())
assert operator_values["resources"]["capture_slots"] == 15
assert operator_values["resources"]["max_asset_gpu_bytes"] == 1_073_741_824
destination = Path(r"C:\Users\ReiterU_PC\Desktop\Pedro\media\protocols\open-loop-engineering-20261015")
destination.mkdir(parents=True, exist_ok=False)
adopted_snapshot = pb.Snapshot.FromString((RUN / "final.pb").read_bytes())
effective = adopted_snapshot.configuration_values.current
submitted = pb.ExperimentConfiguration.FromString((RUN / "effective-candidate.pb").read_bytes())
submitted_matches_adopted = submitted.SerializeToString(deterministic=True) == effective.SerializeToString(deterministic=True)
files = []
for label in ("textures60", "arena60", "combined60", "combined120", "combined900"):
    candidate = pb.ExperimentConfiguration.FromString((OUT / f"candidate-{label}.pb").read_bytes())
    value = pb.ExperimentConfiguration.FromString(effective.SerializeToString())
    value.trials[0].CopyFrom(candidate.trials[0])
    program_path = destination / f"program-{label}.json"
    shutil.copy2(OUT / program_path.name, program_path)
    value.trials[0].stimulus.program.logical_source_reference = str(program_path)
    path = destination / f"configuration-{label}.json"
    path.write_text(json.dumps(dict(format_version=1, configuration=MessageToDict(value, preserving_proto_field_name=True)), indent=2))
    files.extend((path, program_path))
operator_path = destination / "visual_stimulus_config.test.toml"
shutil.copy2(operator_source, operator_path)
files.append(operator_path)
manifest = dict(scope="Reusable engineering open-loop test copies; supplied Pedro files preserved",
                launch=".venv/Scripts/python.exe scripts/start_runtime_gui.py --no-tracking",
                durations_seconds=dict(textures60=60, arena60=60, combined60=60, combined120=120, combined900=900),
                media_root=str(effective.asset_root), recording_root=str(effective.recording_root),
                required_test_overrides=dict(capture_slots=15, max_asset_gpu_bytes=1073741824, presentation_mode="all_outputs_vsync"),
                preserved="Supplied PFS exposure, ROI, pixel format and original camera/stimulus codec arguments. Eye imported normally, then explicit unaligned free-running60Hz override.",
                limitations=["Physical projection areas/seams and photometry uncalibrated", "Behavior/Tracking footage nearly black; Eye dim; engineering endurance does not prove scientific imagery quality", "Source camera counter continuity differs from CFR same-slot omission/duplication; inspect retained accounting", "Arena source is a circular textured floor only, no walls", "Arena model matrices retained; structured arena effective_poses empty, scientific virtual-camera semantics not accepted"],
                evidence_directory=str(OUT), successful_soak_directory=final["session"]["directory"],
                configuration_source="Actual final adopted configuration_values.current, not preSetup candidate",
                submitted_matches_adopted=submitted_matches_adopted,
                files=[dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in files])
(destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
(OUT / "reusable-files-manifest.json").write_text(json.dumps(manifest, indent=2))
print(destination)
