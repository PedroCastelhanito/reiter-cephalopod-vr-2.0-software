"""Writer durability, bounded admission and truthful failure closure."""

import hashlib
import json
import threading
from uuid import uuid4

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns
from cephvr.tracking.config.models.records import (
    Header,
    Identity,
    Reset,
    TrackingRecord,
)
from cephvr.tracking.configuration import load_file_policies
from cephvr.tracking.recording.writer import TrackingWriter

from .support import ROOT


def header():
    now = host_time_ns()
    return Header(
        kind="header",
        schema_version=3,
        stream_kind="tracking",
        identity=Identity(
            **{
                key: str(uuid4())
                for key in (
                    "session_id",
                    "trial_id",
                    "tracking_process_instance_id",
                    "writer_generation",
                    "prepared_generation",
                    "source_allocation_id",
                )
            },
            configuration_revision=1,
        ),
        trial_start_host_ns=now,
        trial_normal_end_host_ns=now + 10**9,
        pipeline_id="water_flow",
        pose_mode="manual",
        prepared_methods_json="{}",
        resolved_settings_json="{}",
        prepared_methods_sha256=hashlib.sha256(b"{}").hexdigest(),
        image_width_px=100,
        image_height_px=100,
    )


def test_idle_writer_syncs_then_completes_empty_scientific_stream(
    tmp_path, monkeypatch
):
    settings = load_file_policies(ROOT).recording
    settings.sync_interval_s = 0.01
    synced = threading.Event()
    from cephvr.tracking.recording import writer as module

    original = module.os.fsync

    def sync(fd):
        original(fd)
        synced.set()

    monkeypatch.setattr(module.os, "fsync", sync)
    writer = TrackingWriter(tmp_path / "trial_tracking.jsonl", "out", settings)
    writer.start(header())
    assert synced.wait(2), "idle Header must reach periodic fsync"
    writer.seal(host_time_ns())
    result = writer.finalize(host_time_ns() + 2 * 10**9)
    assert result.closure == pb.OUTPUT_CLOSURE_CLOSED and result.artifact_present
    lines = [
        json.loads(line)["record"] for line in writer.path.read_text().splitlines()
    ]
    assert [line["kind"] for line in lines] == ["header", "completion"]
    assert lines[-1]["result_records"] == 0


def test_sync_failure_is_closed_failure_not_success(tmp_path, monkeypatch):
    from cephvr.tracking.recording import writer as module

    def fail(_):
        raise OSError("disk synchronization failed")

    monkeypatch.setattr(module.os, "fsync", fail)
    writer = TrackingWriter(
        tmp_path / "trial_tracking.jsonl", "out", load_file_policies(ROOT).recording
    )
    writer.start(header())
    writer.seal(host_time_ns(), interrupted=True)
    result = writer.finalize(host_time_ns() + 2 * 10**9)
    assert result.closure == pb.OUTPUT_CLOSURE_FAILED
    assert result.artifact_present and writer.closed and writer.handle is None
    assert "synchronization" in result.failure.message


def test_admission_reserves_bookkeeping_and_rejects_preonset_start(tmp_path):
    settings = load_file_policies(ROOT).recording
    settings.max_pending_records = 5
    writer = TrackingWriter(tmp_path / "trial_tracking.jsonl", "out", settings)
    record = TrackingRecord(
        record=Reset(
            kind="reset",
            reset_generation="1",
            causes=("trial_start",),
            observed_host_ns=1,
        )
    )
    assert writer.try_admit(record)
    assert not writer.try_admit(record)
    assert writer.try_admit(record, bookkeeping=True)
    future = header().model_copy(update={"trial_start_host_ns": host_time_ns() + 10**9})
    with pytest.raises(ValueError, match="onset"):
        writer.start(future)
    assert not writer.path.exists()


@pytest.mark.parametrize("stage_mode", ["baseline", "no_sections", "sections"])
def test_movement_record_retains_decoded_payload_and_stage_order(stage_mode):
    from google.protobuf.json_format import ParseDict

    from cephvr.tracking.config.models.records import (
        FlowProxyEvidence,
        FlowSectionEvidence,
        PoseUse,
    )
    from cephvr.tracking.recording.results import movement_record
    from cephvr.visual_stimulus.v1.data_pb2 import FeedbackResult

    result = FeedbackResult(
        result_id="exact-result", reset_generation="2", source_frame_ids=["4", "5"]
    )
    result.values.add(channel_id="forward_drive", value=1.25)
    pose = PoseUse(
        disposition="missing",
        observation_id=None,
        manual_geometry_id=None,
        check_host_ns=100,
        pose_source_host_ns=None,
        age_ns=None,
        maximum_age_ns=10,
    )
    evidence = (
        None
        if stage_mode == "baseline"
        else FlowProxyEvidence(
            schema_version=1,
            pipeline_id="water_flow",
            validity="invalid",
            reason="insufficient_support",
            sections=()
            if stage_mode == "no_sections"
            else (
                FlowSectionEvidence(
                    section_index=0,
                    intended_area_px2=4,
                    visible_area_px2=3,
                    accepted_area_px2=0,
                ),
                FlowSectionEvidence(
                    section_index=1,
                    intended_area_px2=0,
                    visible_area_px2=0,
                    accepted_area_px2=0,
                ),
            ),
            counts=None,
            centroid_body_px=None,
            mean_velocity_body_px_per_s=None,
            centred_moment_px2_per_s=None,
            centred_second_moment_px2=None,
            raw=None,
            filtered_average=None,
            filter_end=None,
            filter_disposition="cleared",
        )
    )
    record = movement_record(
        result, produced_host_ns=101, pose=pose, evidence=evidence
    ).record
    assert (
        record.kind == "result"
        and record.produced_host_ns == 101
        and record.pose == pose
    )
    decoded = json.loads(record.model_dump_json())
    assert decoded["feedback_result"]["values"] == [
        {"channelId": "forward_drive", "value": 1.25}
    ]
    assert ParseDict(decoded["feedback_result"], FeedbackResult()) == result
    assert [stage.stage_id for stage in record.stage_evidence] == {
        "baseline": [],
        "no_sections": ["estimator"],
        "sections": ["geometry", "estimator"],
    }[stage_mode]
    if evidence is not None:
        assert record.stage_evidence[-1].schema_id == "tracking.flow-proxy-evidence.v1"
        assert decoded["stage_evidence"][-1]["payload"] == evidence.model_dump(
            mode="json"
        )
    if stage_mode == "sections":
        assert record.stage_evidence[0].schema_id == "tracking.geometry-evidence.v1"
        assert decoded["stage_evidence"][0]["payload"] == {
            "schema_version": 1,
            "regions": [
                {
                    "region_id": "section_0",
                    "requested_pixels": 4,
                    "visible_pixels": 3,
                    "clipped_fraction": 0.25,
                }
            ],
        }


def _result_record(result):
    from cephvr.tracking.config.models.records import PoseUse
    from cephvr.tracking.recording.results import movement_record

    return movement_record(
        result,
        produced_host_ns=101,
        pose=PoseUse(
            disposition="manual",
            observation_id=None,
            manual_geometry_id="fixed",
            check_host_ns=100,
            pose_source_host_ns=None,
            age_ns=None,
            maximum_age_ns=None,
        ),
        evidence=None,
    )


def test_decoded_file_preserves_64bit_values_optional_zero_and_immutable_admission(
    tmp_path,
):
    from google.protobuf.json_format import ParseDict

    from cephvr.tracking.recording.codec import decode_lines, encode_line
    from cephvr.visual_stimulus.v1.data_pb2 import (
        FEEDBACK_VALIDITY_BASELINE_ONLY,
        FeedbackResult,
    )

    result = FeedbackResult(
        result_id="exact",
        result_sequence=2**64 - 1,
        source_host_receipt_ns=2**63 - 1,
        interval_start_ns=0,
        validity=FEEDBACK_VALIDITY_BASELINE_ONLY,
    )
    result.work.trial.trial_number = 2**32 - 1
    record = _result_record(result)
    expected = result.SerializeToString(deterministic=True)
    result.result_id = "changed-after-admission"
    exported = record.model_dump(mode="json")
    exported["record"]["feedback_result"]["resultId"] = "changed-copy"
    line = encode_line(record, max_bytes=10000)
    decoded = json.loads(line)["record"]["feedback_result"]
    assert decoded["resultSequence"] == str(2**64 - 1)
    assert decoded["sourceHostReceiptNs"] == str(2**63 - 1)
    assert decoded["work"]["trial"]["trialNumber"] == 2**32 - 1
    assert decoded["intervalStartNs"] == "0" and "intervalEndNs" not in decoded
    assert decoded["validity"] == "FEEDBACK_VALIDITY_BASELINE_ONLY"
    assert (
        ParseDict(decoded, FeedbackResult()).SerializeToString(deterministic=True)
        == expected
    )
    assert decode_lines(line + b'{"record":', max_bytes=10000) == ((record,), 10)
    with pytest.raises(ValueError, match="max_record_bytes"):
        encode_line(record, max_bytes=len(line) - 2)
    writer = TrackingWriter(
        tmp_path / "trial_tracking.jsonl", "out", load_file_policies(ROOT).recording
    )
    writer.start(header())
    assert writer.try_admit(record)
    writer.seal(host_time_ns())
    assert (
        writer.finalize(host_time_ns() + 2 * 10**9).closure == pb.OUTPUT_CLOSURE_CLOSED
    )
    saved = [
        json.loads(line)["record"] for line in writer.path.read_text().splitlines()
    ]
    assert saved[0]["schema_version"] == 3
    assert saved[1]["feedback_result"] == decoded
    assert saved[-1]["result_records"] == 1


@pytest.mark.parametrize(
    "feedback",
    [
        {"protobuf_base64": "CA=="},
        {"unknown": 1},
        {"resultSequence": 9007199254740993},
        {"resultSequence": "01"},
        {"result_sequence": "1"},
        {"intervalStartNs": None},
        {"validity": 1},
        {"validity": 99},
        {"values": [{"channelId": "drive", "value": "NaN"}]},
        {"values": [{"channelId": "drive", "value": "Infinity"}]},
    ],
)
def test_decoded_reader_rejects_legacy_noncanonical_and_unknown_feedback(feedback):
    from cephvr.tracking.config.models.records import parse_record
    from cephvr.visual_stimulus.v1.data_pb2 import FeedbackResult

    document = _result_record(FeedbackResult()).model_dump(mode="json")
    document["record"]["feedback_result"] = feedback
    with pytest.raises(ValueError):
        parse_record(json.dumps(document), max_bytes=10000)


@pytest.mark.parametrize("fault", ["wire_field", "enum", "nan"])
def test_decoded_formatter_rejects_fields_that_cannot_be_saved_truthfully(fault):
    from cephvr.visual_stimulus.v1.data_pb2 import FeedbackResult

    result = FeedbackResult()
    if fault == "wire_field":
        result.ParseFromString(b"\xf8\x07\x01")
    elif fault == "enum":
        result.validity = 99
    else:
        result.values.add(channel_id="drive", value=float("nan"))
    with pytest.raises(ValueError):
        _result_record(result)


@pytest.mark.parametrize("version", [1, 2, 3.0, True, "3"])
def test_decoded_reader_rejects_unsupported_or_inexact_header_version(version):
    from cephvr.tracking.config.models.records import parse_record

    document = TrackingRecord(record=header()).model_dump(mode="json")
    document["record"]["schema_version"] = version
    with pytest.raises(ValueError):
        parse_record(json.dumps(document), max_bytes=10000)


@pytest.mark.parametrize("payload", ["{}", [], None])
def test_decoded_stage_payload_requires_an_object_on_disk(payload):
    from cephvr.tracking.config.models.records import parse_record
    from cephvr.visual_stimulus.v1.data_pb2 import FeedbackResult

    document = _result_record(FeedbackResult()).model_dump(mode="json")
    document["record"]["stage_evidence"] = [
        {
            "stage_id": "geometry",
            "schema_id": "tracking.geometry-evidence.v1",
            "payload": payload,
        }
    ]
    with pytest.raises(ValueError, match="object required"):
        parse_record(json.dumps(document), max_bytes=10000)


def test_decoded_admission_charges_expanded_object_workspace(tmp_path):
    from cephvr.tracking.recording.writer import _retained_bytes
    from cephvr.visual_stimulus.v1.data_pb2 import FeedbackResult

    result = FeedbackResult(result_id="budget")
    for index in range(10):
        result.values.add(channel_id=f"drive_{index}", value=index + 0.5)
    record = _result_record(result)
    settings = load_file_policies(ROOT).recording
    settings.max_record_bytes = 2000
    immutable = _retained_bytes(record, settings.max_pending_bytes)
    workspace = _retained_bytes(
        record.model_dump(mode="json"), settings.max_pending_bytes
    )
    copies = 2 * (settings.max_record_bytes + 1)
    settings.max_pending_bytes = 4 * copies + immutable + copies
    writer = TrackingWriter(tmp_path / "budget.jsonl", "out", settings)
    assert not writer.try_admit(record), (
        "text-only budget cannot cover expanded objects"
    )
    settings.max_pending_bytes += workspace
    assert writer.try_admit(record)
    assert writer.pending_bytes == immutable + workspace + copies
    assert writer.pending_count == 1 and not writer.path.exists()
