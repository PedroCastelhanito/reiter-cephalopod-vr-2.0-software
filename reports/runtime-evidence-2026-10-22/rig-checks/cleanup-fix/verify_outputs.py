"""Independent decode/accounting and per-occurrence texture audit; no device control."""
import collections
import json
import shutil
import subprocess
import sys
from pathlib import Path

from cephvr.platform.windows.paths import extended_path
from cephvr.visual_stimulus.compiler import expand_program
from cephvr.visual_stimulus.resources.image_schedule import image_asset
from cephvr.visual_stimulus.config.models.program_model import Program

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tests.visual_stimulus.evidence_reader import read_evidence

out = Path(sys.argv[1]).resolve()
assert sys.argv[2:] in ([], ["--stopped-after-trial"])
stopped_after_trial = sys.argv[2:] == ["--stopped-after-trial"]
state = json.loads((out / "terminal.json").read_text(encoding="utf-8"))
configuration = json.loads((out / "test-configuration-attached.json").read_text(encoding="utf-8"))
expected_outcome = "SESSION_OUTCOME_STOPPED" if stopped_after_trial else "SESSION_OUTCOME_COMPLETED"
assert state["session"]["outcome"] == expected_outcome
if stopped_after_trial:
    assert state["session"]["stop_after_trial"] and state["session"]["trial_count"] == 1
    assert state["trial"]["outcome"] == "TRIAL_OUTCOME_COMPLETED"
    assert int(state["trial"]["actual_end_monotonic_ns"]) == int(state["trial"]["scheduled_end_monotonic_ns"])
    assert int(state["trial"]["scheduled_end_monotonic_ns"]) - int(state["trial"]["start_monotonic_ns"]) == 60_000_000_000
assert state["session"]["cleanup_confirmed"]
directory = Path(state["session"]["directory"])
probe = shutil.which("ffprobe")
assert probe
trials = configuration["trials"]
logs = []
for candidate in (directory / "protocol-data").glob("*_LOG.json"):
    document = json.loads(candidate.read_text(encoding="utf-8"))
    if "trial_number" in document and "outputs" in document:
        logs.append((document["trial_number"], document))
logs.sort(key=lambda row: row[0])
assert [number for number, _ in logs] == list(range(1, len(trials) + 1))
results = {"ffprobe": probe, "directory": str(directory), "trials": []}
for number, log in logs:
    assert log["complete"] and log["outcome"] == "completed"
    trial = trials[number - 1]
    source = trial["stimulus"]
    program = Program.model_validate_json(source["program"]["program_json"])
    assert all(asset.profile == "png_uint_v1" for asset in program.assets)
    indices = {asset.asset_id: index for index, asset in enumerate(sorted(program.assets, key=lambda asset: asset.asset_id))}
    expanded = expand_program(program, seed_decimal=source.get("stimulus_seed_decimal", "0"), max_expanded_epochs=4096)
    expected = [{setting.instance_id: image_asset(setting) for setting in epoch.settings if image_asset(setting) is not None} for epoch in expanded]
    assert all(len(row) in (0, 4) for row in expected)
    assert any(expected)
    offsets = [0]
    for epoch in expanded:
        offsets.append(offsets[-1] + epoch.source.duration.duration.ns())
    result = {"trial_number": number, "outputs": [], "expected_occurrences": len(expected)}
    videos = frames_files = 0
    for output in log["outputs"]:
        assert output["closure"] == "OUTPUT_CLOSURE_CLOSED" and output["artifact_present"]
        artifact = Path(output["path"])
        assert artifact.is_file()
        item = {"tag": output["output_tag"], "bytes": artifact.stat().st_size, "counts": output.get("counts")}
        if artifact.suffix == ".mp4":
            videos += 1
            command = [probe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", extended_path(artifact)]
            decoded = subprocess.run(command, capture_output=True, text=True, timeout=300)
            assert decoded.returncode == 0 and not decoded.stderr, decoded.stderr
            item["decode"] = json.loads(decoded.stdout)["streams"][0]
            assert int(item["decode"]["nb_read_frames"]) == output["counts"]["frames"]
        if artifact.name.endswith("_stimulus_frames.jsonl"):
            frames_files += 1
            groups, bindings, seen, first, previous, previous_output = 0, 0, set(), {}, None, {}
            captures, failures = collections.Counter(), collections.Counter()
            required_outputs, submission_phases, target_ns = None, collections.Counter(), None
            maximum_interval = 0
            output_intervals = collections.defaultdict(int)
            parsed = read_evidence(artifact, max_line_bytes=16_777_216)
            assert parsed.completion is not None and not parsed.discarded_partial_tail
            assert parsed.completion.outcome == "completed"
            assert parsed.completion.unresolved_attempt_count == 0
            assert parsed.header.format_version == 6
            input_ordinals, input_groups, encoder, latest_submissions = [], set(), None, {}
            for evidence_record in parsed.records:
                record = evidence_record.payload.model_dump(mode="json")
                if record["kind"] == "encoder_outcome":
                    assert encoder is None
                    encoder = record
                if record["kind"] in ("render_group", "group_update"):
                    for capture in record["captures"]:
                        captures[capture["disposition"]] += 1
                        if capture["disposition"] == "input_submitted":
                            assert record["group_id"] not in input_groups
                            input_groups.add(record["group_id"])
                            input_ordinals.append(capture["video_frame_index"])
                    for submission in record["submissions"]:
                        latest_submissions[(record["group_id"], submission["output_id"])] = submission
                if record["kind"] == "header":
                    assert record["identity"]["trial_id"] == log["trial_id"]
                    target_ns = record["trial_start_host_ns"]
                    required_outputs = set(record["required_output_ids"])
                    assert len(required_outputs) == 4
                    continue
                if record["kind"] != "render_group":
                    continue
                groups += 1
                snapshot = record["state"]
                occurrence = snapshot["epoch_occurrence"]
                assert 0 <= occurrence < len(expected)
                images = snapshot["images"]
                assert len(images) == len(expected[occurrence]) and {image["instance_id"] for image in images} == set(expected[occurrence])
                bindings += len(images)
                for image in images:
                    selected = expected[occurrence][image["instance_id"]]
                    assert image["requested_asset_id"] == image["asset_id"] == selected
                    assert image["requested_image_index"] == image["image_index"] == indices[selected]
                    assert image["disposition"] == "current"
                now = snapshot["evaluation_host_ns"]
                assert previous is None or now >= previous
                if previous is not None:
                    maximum_interval = max(maximum_interval, now - previous)
                previous = now
                assert target_ns is not None
                assert target_ns + offsets[occurrence] <= now < target_ns + offsets[occurrence + 1]
                seen.add(occurrence)
                first.setdefault(occurrence, {"group_id": record["group_id"], "evaluation_host_ns": now, "onset_delay_ns": now - target_ns - offsets[occurrence]})
            assert required_outputs is not None
            for group in parsed.groups:
                submissions = [latest_submissions[(group.group_id, output_id)] for output_id in required_outputs]
                for submission in submissions:
                    submission_phases[submission["phase"]] += 1
                    assert not submission["failure_code"]
                    if submission["phase"] == "cutoff_excluded":
                        assert group.group_id == parsed.last_group_id
                        assert all(submission[key] is None for key in ("attempt_index", "entry_host_ns", "return_host_ns", "marker_index", "marker_high"))
                        continue
                    assert submission["phase"] == "returned"
                    entry, returned = submission["entry_host_ns"], submission["return_host_ns"]
                    assert entry is not None and returned is not None and entry <= returned
                    key = submission["output_id"]
                    if key in previous_output:
                        output_intervals[key] = max(output_intervals[key], entry - previous_output[key])
                    previous_output[key] = entry
            assert input_ordinals == list(range(len(input_ordinals)))
            assert encoder is not None
            assert encoder["exit_code"] == 0 and encoder["eof_sent"] and encoder["drain_confirmed"]
            assert encoder["input_submitted_count"] == encoder["encoded_frame_count"] == len(input_ordinals)
            assert encoder["admitted_count"] == encoder["selected_real_count"] == len(input_ordinals)
            assert encoder["same_slot_omission_count"] == encoder["duplicate_frame_count"] == 0
            item["encoder"] = encoder
            assert groups and seen == set(range(len(expected)))
            assert not failures
            item["texture_audit"] = {"groups": groups, "bindings": bindings, "occurrences": len(seen), "mismatches": 0, "residency_holds": 0, "maximum_state_interval_ns": maximum_interval, "maximum_output_intervals_ns": dict(output_intervals), "captures": dict(captures), "submission_failures": dict(failures), "submission_phases": dict(submission_phases), "first_groups": first}
        result["outputs"].append(item)
    assert videos == 3 and frames_files == 1, (videos, frames_files)
    stimulus_video = next(item for item in result["outputs"] if item["tag"] == "stimulus")
    scientific = next(item for item in result["outputs"] if item["tag"] == "stimulus_frames")
    assert int(stimulus_video["decode"]["nb_read_frames"]) == scientific["encoder"]["input_submitted_count"]
    results["trials"].append(result)
    (out / "output-verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("verified", number, "complete decode/accounting + correct image/blank groups and onsets", flush=True)
assert len(results["trials"]) == len(trials)
