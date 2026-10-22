"""Offline A07 frame/counter/encoder reconciliation; no device interaction."""
import collections
import json
import sys
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from cephvr.platform.windows.paths import extended_path

out = Path(sys.argv[1]).resolve()
verification = json.loads((out / "output-verification.json").read_text(encoding="utf-8"))
terminal = json.loads((out / "terminal.json").read_text(encoding="utf-8"))
directory = Path(terminal["session"]["directory"]) / "protocol-data"
logs = {}
for candidate in directory.glob("*_LOG.json"):
    document = json.loads(candidate.read_text(encoding="utf-8"))
    if "trial_number" in document and "outputs" in document:
        logs[document["trial_number"]] = document
results = []
for path in sorted(directory.glob("*_cam_frames.jsonl")):
    header = completion = None
    received = encoded = dropped = invalid = 0
    pending = None
    first_host = last_host = first_counter = last_counter = None
    counter_gaps = counter_regressions = 0
    dispositions = collections.Counter()
    maximum_interval = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            assert line.endswith("\n")
            record = json.loads(line)
            assert completion is None, "records follow completion"
            kind = record["type"]
            if kind == "header":
                assert header is None and received == encoded == 0
                header = record
                assert header["schema_version"] == 5 and header["video"]["enabled"]
            elif kind == "frame":
                assert header is not None and pending is None
                assert record["frame_id"] == received
                received += 1
                timestamp = record["host_receipt_ns"]
                if last_host is not None:
                    assert timestamp >= last_host
                    maximum_interval = max(maximum_interval, timestamp - last_host)
                if first_host is None:
                    first_host = timestamp
                last_host = timestamp
                counter = record["camera_frame_counter"]
                if counter is not None:
                    if first_counter is None:
                        first_counter = counter
                    if last_counter is not None:
                        if counter <= last_counter:
                            counter_regressions += 1
                        else:
                            counter_gaps += counter - last_counter - 1
                    last_counter = counter
                dispositions[record["video_disposition"]] += 1
                dropped += bool(record["dropped"])
                invalid += record["invalid_code"] is not None
                if record["dropped"]:
                    assert record["video_frame"] is None
                else:
                    assert record["video_frame"] == encoded
                    pending = (record["frame_id"], timestamp)
            elif kind == "video_frame":
                assert record["encoded_frame_index"] == encoded
                assert pending == (record["source_frame_id"], record["source_host_receipt_ns"])
                assert record["disposition"] == "real"
                encoded += 1
                pending = None
            elif kind == "completion":
                completion = record
            else:
                raise AssertionError(kind)
    assert header is not None and completion is not None and pending is None
    assert completion["outcome"] == "completed"
    assert completion["timing"]["accounting_complete"]
    assert completion["timing"]["final_received_frame_count"] == received
    assert completion["post_cutoff"]["accounting_complete"]
    assert completion["video"]["recorded_frame_count"] == completion["video"]["selected_source_frame_count"] == encoded
    assert completion["video"]["duplicate_frame_count"] == 0
    identity = header["identity"]
    assert identity["session_id"] == terminal["session"]["context"]["session_id"]
    log = logs[identity["trial_number"]]
    assert identity["trial_id"] == log["trial_id"]
    expected_file = next(o for o in log["outputs"] if o["output_tag"] == identity["camera_role"] + "_cam_frames")
    assert Path(expected_file["path"]) == path
    trial = next(t for t in verification["trials"] if t["trial_number"] == identity["trial_number"])
    tag = identity["camera_role"] + "_cam"
    video = next(o for o in trial["outputs"] if o["tag"] == tag)
    assert encoded == int(video["decode"]["nb_read_frames"])
    video_path = Path(next(o for o in log["outputs"] if o["output_tag"] == tag)["path"])
    probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "format_tags", "-of", "json", extended_path(video_path)], capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0 and not probe.stderr
    tags = json.loads(probe.stdout)["format"]["tags"]
    assert tags["cephvr_identity_version"] == "1"
    for key in ("session_id", "trial_id", "camera_role", "device_id"):
        assert tags["cephvr_" + key] == str(identity[key])
    target = header["clocks"]["trial_start_monotonic_ns"]
    end = completion["timing"]["recording_end_monotonic_ns"]
    nominal = Fraction(str(header["video"]["nominal_frame_rate_hz"]))
    pulses = completion["pulses"]
    results.append({"path": str(path), "identity": identity, "mp4_identity_tags": tags, "received": received, "encoded": encoded, "dropped": dropped, "invalid": invalid, "dispositions": dict(dispositions), "native_counter_first": first_counter, "native_counter_last": last_counter, "native_counter_missing_within_observed_stream": counter_gaps, "native_counter_regressions": counter_regressions, "nominal_rate_hz": str(nominal), "nominal_trial_slot_count": str(nominal * Fraction(end - target, 1_000_000_000)), "first_host_receipt_minus_target_ns": None if first_host is None else first_host-target, "last_host_receipt_minus_boundary_ns": None if last_host is None else last_host-end, "maximum_host_receipt_interval_ns": maximum_interval, "pulses": pulses, "transport_summary": completion["transport_summary"], "diagnostics": completion["diagnostics"], "post_cutoff": completion["post_cutoff"], "limits": "Host receipt/native counters do not prove electrical trigger or exposure onset. Nominal slots are not an independently measured pulse count."})
    print(identity["trial_number"], identity["camera_role"], "received/encoded", received, encoded, "drops", dropped, "nativegaps", counter_gaps, flush=True)
assert len(results) == 2 * len(verification["trials"])
(out / "camera-accounting.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
