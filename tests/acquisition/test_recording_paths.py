from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.paths import RecordingPaths, resolve_recording_paths
from cephvr.acquisition.recording_schema import get_writer_schemas
from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.control.v1 import types_pb2 as control
from cephvr.platform.windows.paths import extended_path
from tests.acquisition.support import _identity, _reservation


@pytest.mark.parametrize("role", ["behavioral", "tracking", "eye_tracking"])
def test_valid_backend_context_and_exact_scheduled_paths_are_accepted(
    tmp_path: Path,
    role: str,
) -> None:
    identity = _identity(role)
    plans = _reservation(identity)
    plans.validate(role, identity)
    prefix = tmp_path / "trial"
    schedule = acq.WorkerSchedule(
        command=acq.WorkerCommand(
            target=acq.WorkerContext(
                camera=camera.CameraRole.Value(f"CAMERA_ROLE_{role.upper()}"),
                work=control.WorkContext(
                    trial=control.TrialContext(
                        session=control.SessionContext(session_id=identity.session_id),
                        trial_id=identity.trial_id,
                        trial_number=identity.trial_number,
                    )
                ),
            )
        ),
        start_monotonic_ns=100,
        end_monotonic_ns=200,
        trial_file_prefix=str(prefix),
        outputs=plans.outputs,
    )
    for item in schedule.outputs:
        item.path = f"{prefix}_{item.output_tag}.{item.extension}"

    assert resolve_recording_paths(plans, role, identity, schedule) == (
        Path(f"{prefix}_{role}_cam.mp4"),
        Path(f"{prefix}_{role}_cam_frames.jsonl"),
    )


def test_non_acquisition_backend_context_is_rejected() -> None:
    identity = _identity()
    plans = _reservation(identity)
    plans.outputs[0].backend.backend_name = "tracking"
    with pytest.raises(ValueError, match="exact acquisition work identity"):
        plans.validate("behavioral", identity)


def test_stale_backend_generation_is_rejected() -> None:
    identity = _identity()
    plans = _reservation(identity)
    stale = RecordingPaths(plans.outputs, str(uuid4()))
    with pytest.raises(ValueError, match="exact acquisition work identity"):
        stale.validate("behavioral", identity)


@pytest.mark.parametrize("available", [False, True])
def test_recording_clock_accepts_schema_text_and_checks_explicit_conversion(
    available: bool,
) -> None:
    identity = _identity()
    if available:
        identity.camera_clock.conversion_available = True
        identity.camera_clock.tick_period_ns_numerator = 1
        identity.camera_clock.tick_period_ns_denominator = 1
        identity.camera_clock.unavailable_reason = ""
        identity.camera_clock.counter_unavailable_reason = ""
    identity.validate()
    identity.camera_clock.timestamp_source = ""
    with pytest.raises(ValueError, match="timestamp_source is invalid"):
        identity.validate()
    identity.camera_clock.timestamp_source = "SDK"
    identity.camera_clock.ClearField("conversion_available")
    with pytest.raises(ValueError, match="conversion availability is unspecified"):
        identity.validate()


@pytest.mark.parametrize("long_path", [False, True])
def test_frame_log_header_matches_declared_and_planned_cadence_schema(
    tmp_path: Path,
    long_path: bool,
) -> None:
    path = tmp_path / (("frame_" * 30 if long_path else "") + "camera_frames.jsonl")
    writer = FrameLogWriter(
        path,
        _identity(),
        start_ns=1_000_000_000,
        nominal_frame_rate_hz=30,
        nominal_rate_source="applied_mcu_rate",
        sync_interval_ns=1_000_000_000,
        syncer=SimpleNamespace(sync=lambda _: None),
    )
    writer.create()
    writer.close_failed()  # A header alone is deliberately not completed recording.
    header = json.loads(
        Path(extended_path(path) if sys.platform == "win32" else path)
        .read_text()
        .splitlines()[0]
    )
    declaration = tomllib.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts/acquisition/frame_log_schema.toml"
        ).read_text()
    )
    planned = get_writer_schemas()["acquisition", "behavioral_cam_frames", "jsonl"]
    assert (
        header["schema_version"]
        == declaration["schema_version"]
        == planned.schema_version
        == 6
    )
    assert "video_frame" in declaration["format"]["line_types"]
    assert "source_host_receipt_ns" in planned.fields["video_frame"]


@pytest.mark.parametrize("role", ["behavioral", "tracking", "eye_tracking"])
@pytest.mark.parametrize(
    "ending", ["completed", "continuous", "interrupted", "cancelled", "write_failure"]
)
def test_metadata_only_session_retains_sources_without_video_resources(
    tmp_path, role, ending
):
    from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
    from cephvr.acquisition.buffers.queue import (
        PendingRecordCapacityError,
        RecordingQueue,
    )
    from cephvr.acquisition.buffers.records import FrameRecord
    from cephvr.acquisition.recording.session import RecordingSession
    from cephvr.acquisition.recording.session_contracts import (
        PulseEvidence,
        RecordingCompletionContext,
        RecordingFailure,
    )

    identity = _identity(role)
    reserved = _reservation(identity)
    paths = RecordingPaths(
        tuple(p for p in reserved.outputs if p.extension == "jsonl"),
        reserved.backend_generation,
    )
    now = [90]
    queue = RecordingQueue(1, 2, metadata_only=True)
    session = RecordingSession(
        acq.RecordingSettings(
            metadata_only=True, frame_log_sync_interval_ns=1, pending_records_capacity=2
        ),
        camera.CameraImageLayout(),
        identity,
        paths,
        queue,
        None,
        None,
        None,
        None,
        None,
        SimpleNamespace(sync=lambda _: None),
        role=role,
        nominal_frame_rate_hz=60,
        nominal_rate_source="applied_mcu_rate",
        warning_occurrence=lambda *_: None,
        started_observed=lambda _: None,
        clock_ns=lambda: now[0],
    )
    session.prepare()
    trial = paths.outputs[0].trial
    schedule = acq.WorkerSchedule(
        command=acq.WorkerCommand(
            command_id="schedule",
            target=acq.WorkerContext(
                camera=camera.CameraRole.Value(f"CAMERA_ROLE_{role.upper()}"),
                work=control.WorkContext(trial=trial),
            ),
        ),
        start_monotonic_ns=100,
        end_monotonic_ns=200,
        trial_file_prefix=str(tmp_path / "trial"),
        outputs=paths.outputs,
    )
    schedule.outputs[0].path = str(tmp_path / f"trial_{role}_cam_frames.jsonl")
    session.schedule(schedule, deadline_ns=99)
    assert not list(tmp_path.iterdir())
    if ending == "cancelled":
        results = session.cancel_before_start(deadline_ns=99)
        assert results[0].closure == control.OUTPUT_CLOSURE_NOT_STARTED
        assert not results[0].artifact_present
        return
    session.release(
        acq.WorkerRelease(
            command=acq.WorkerCommand(target=schedule.command.target),
            schedule_operation=control.OperationContext(command_id="schedule"),
            start_monotonic_ns=100,
            end_monotonic_ns=200,
        ),
        deadline_ns=99,
    )
    queue.enqueue(FrameRecord(0, 110, 101, 1001, True, None), None)
    queue.enqueue(FrameRecord(1, 120, 102, 1002, False, "INVALID_IMAGE"), None)
    with pytest.raises(PendingRecordCapacityError):
        queue.enqueue(FrameRecord(2, 130, 103, 1003, True, None), None)
    now[0] = 120
    if ending == "write_failure":
        session._create_trial_outputs()
        session._frame_log.append_frame = lambda *a, **k: (_ for _ in ()).throw(
            OSError("disk full")
        )
        with pytest.raises(RecordingFailure, match="disk full"):
            session.process_available()
        results = session.fail_cleanup(deadline_ns=300)
        assert results[0].closure == control.OUTPUT_CLOSURE_FAILED
        assert queue.pending_records == 0
        return
    assert session.process_available() == 2
    end = 150 if ending == "interrupted" else 200
    now[0] = end
    continuous = ending == "continuous"
    outcome = "completed" if continuous else ending
    results = session.finish(
        CaptureEndMarker(
            2,
            end,
            None if continuous else end,
            0,
            None,
            True,
            admission_stop_monotonic_ns=end if continuous else None,
            accounting_observed_monotonic_ns=end,
            boundary_context=(
                FrameRecord(0, 90, 100, 1000, True, None),
                FrameRecord(0, 110, 101, 1001, True, None),
                FrameRecord(1, 120, 102, 1002, False, "INVALID_IMAGE"),
                None,
            ),
        ),
        PulseEvidence(),
        RecordingCompletionContext(
            outcome,
            end,
            None if continuous else end,
            None,
            stopped_admission_stop_monotonic_ns=end if continuous else None,
        ),
        deadline_ns=300,
    )
    assert results[0].closure == control.OUTPUT_CLOSURE_CLOSED
    assert results[0].camera_video_content == control.CAMERA_VIDEO_CONTENT_UNSPECIFIED
    rows = [json.loads(line) for line in Path(results[0].path).read_text().splitlines()]
    assert [r["type"] for r in rows] == ["header", "frame", "frame", "completion"]
    assert rows[0]["video"]["enabled"] is False
    assert [
        (r["frame_id"], r["camera_frame_counter"], r["camera_timestamp_ns"])
        for r in rows[1:3]
    ] == [(0, 101, 1001), (1, 102, 1002)]
    assert all(
        r["video_frame"] is None
        and r["video_disposition"] == "video_disabled"
        and not r["dropped"]
        for r in rows[1:3]
    )
    assert rows[2]["invalid_code"] == "INVALID_IMAGE"
    assert rows[-1]["timing"]["final_received_frame_count"] == 2
    assert rows[-1]["video"]["recorded_frame_count"] == 0
    assert rows[-1]["outcome"] == outcome
    assert rows[-1]["post_cutoff"]["scope"] == (
        "admission_snapshot" if continuous else "physical_stop"
    )
    assert rows[-1]["post_cutoff"]["observed_monotonic_ns"] == end
    assert rows[-1]["boundary_context"]["last_pretrial"]["camera_frame_counter"] == 100
    assert rows[-1]["boundary_context"]["first_excluded"] is None
    assert rows[-1]["boundary_context"]["absolute_pulse_offset"] is None
    assert len(list(tmp_path.iterdir())) == 1


def test_sequential_frame_log_preserves_loss_and_rejects_false_source_mappings(
    tmp_path: Path,
) -> None:
    from cephvr.acquisition.buffers.records import FrameRecord

    writer = FrameLogWriter(
        tmp_path / "frames.jsonl",
        _identity(),
        start_ns=100,
        nominal_frame_rate_hz=60,
        nominal_rate_source="applied_mcu_rate",
        sync_interval_ns=1,
        syncer=SimpleNamespace(sync=lambda _: None),
    )
    writer.create()
    with pytest.raises(ValueError, match="disposition"):
        writer.append_frame(
            FrameRecord(0, 110, 40, 90, True, None),
            dropped=True,
            video_disposition="same_slot_omission",
        )
    # Source IDs count losses; encoded indices count only images actually submitted.
    writer.append_frame(
        FrameRecord(0, 110, 40, 90, True, None),
        dropped=True,
        video_disposition="capacity_drop",
    )
    writer.append_frame(
        FrameRecord(1, 111, 41, 91, False, "INVALID_IMAGE"),
        dropped=True,
        video_disposition="invalid_image",
    )
    writer.append_frame(
        FrameRecord(2, 112, 42, 92, True, None),
        dropped=False,
        video_frame=0,
        video_disposition="real",
    )
    for index, source_id, receipt in [(1, 2, 112), (0, 1, 112), (0, 2, 113)]:
        with pytest.raises(ValueError):
            writer.append_video_frame(
                encoded_frame_index=index,
                source_frame_id=source_id,
                source_host_receipt_ns=receipt,
            )
    writer.append_video_frame(
        encoded_frame_index=0, source_frame_id=2, source_host_receipt_ns=112
    )
    with pytest.raises(ValueError, match="exactly once"):
        writer.append_video_frame(
            encoded_frame_index=1, source_frame_id=2, source_host_receipt_ns=112
        )
    writer.append_frame(
        FrameRecord(3, 113, 43, 93, True, None),
        dropped=False,
        video_frame=1,
        video_disposition="real",
    )
    writer.append_video_frame(
        encoded_frame_index=1, source_frame_id=3, source_host_receipt_ns=113
    )
    writer.close_failed()
    rows = [json.loads(line) for line in writer.path.read_text().splitlines()]
    source_rows = [row for row in rows if row["type"] == "frame"]
    assert [row["video_frame"] for row in source_rows] == [None, None, 0, 1]
    assert [row["video_disposition"] for row in source_rows] == [
        "capacity_drop",
        "invalid_image",
        "real",
        "real",
    ]
    assert [row["host_receipt_ns"] for row in source_rows] == [110, 111, 112, 113]
    assert writer.frame_count == writer.selected_source_count == 2
