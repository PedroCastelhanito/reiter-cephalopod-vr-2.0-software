"""Save the separately verified60s camera-codec candidate, never promote900 scope."""
import hashlib
import json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.control.v1 import types_pb2 as pb

out = Path(__file__).parent
run = out / "lossless60-r1"
collection = json.loads((run / "collection.json").read_text())
assert collection["collection_complete"] and not collection["errors"] and len(collection["videos"]) == 4
for name, video in collection["videos"].items():
    assert video["ffprobe_exit"] == video["decode_exit"] == 0 and not video["decode_error"] and not video["ffprobe_error"]
    assert video["ffprobe"]["streams"][0]["nb_read_frames"] == str(1800 if "behavioral_cam" in name else 3600)
snapshot = pb.Snapshot.FromString((run / "final.pb").read_bytes())
assert snapshot.session.cleanup_confirmed and snapshot.trial.outcome == pb.TRIAL_OUTCOME_COMPLETED
assert snapshot.trial.actual_end_monotonic_ns - snapshot.trial.start_monotonic_ns == 60_000_000_000
feasibility = json.loads((out / "lossless-feasibility.json").read_text())
assert feasibility["passed"] and all(row["identical_prepared_yuv_planes"] for row in feasibility["cases"])
value = pb.ExperimentConfiguration.FromString(snapshot.configuration_values.current.SerializeToString())
source = json.loads((out / "program-lossless60.json").read_text())
assert source == json.loads(value.trials[0].stimulus.program.program_json)
destination = Path(r"C:\Users\ReiterU_PC\Desktop\Pedro\media\protocols\open-loop-resume1-verified-20261015\camera-lossless60")
destination.mkdir(exist_ok=False)
program = destination / "program-lossless60.json"
program.write_text(json.dumps(source, indent=2))
value.trials[0].stimulus.program.logical_source_reference = str(program)
configuration = destination / "configuration-lossless60.json"
configuration.write_text(json.dumps(dict(format_version=1, configuration=MessageToDict(value, preserving_proto_field_name=True)), indent=2))
manifest = dict(scope="Separately verified60s all-three-camera lossless coding plus unchanged lossy stimulus review; no900s lossless endurance claim",
    observed_storage_gib_per_hour=dict(cameras=191.29061182960868, stimulus=4.234679918736219),
    workload_limit="Only current low-complexity rig scene tested; scene-dependent storage and throughput are not guaranteed for scientific imagery",
    codec_scope="Byte-exact versus already prepared8bit full-range YUV444 planes; production Bayer/RGB conversion and CFR omissions remain; not raw sensor pixel preservation",
    evidence=str(run.resolve()), fixture=str((out / "lossless-feasibility.json").resolve()),
    operator_overrides=dict(capture_slots=15, max_asset_gpu_bytes=1073741824),
    camera_args={row["camera"]:row["candidate_args"] for row in feasibility["cases"]},
    files=[dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in (program, configuration)])
(destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
(out / "lossless-reusable-manifest.json").write_text(json.dumps(manifest, indent=2))
print(destination)
