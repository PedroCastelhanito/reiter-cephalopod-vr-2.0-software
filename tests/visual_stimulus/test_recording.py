from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from cephvr.visual_stimulus.config.models.evidence_model import (
    ArtifactRef,
    Clipping,
    FeedbackEvidence,
    Header,
    Identity,
    Interval,
)
from cephvr.visual_stimulus.recording.capture import (
    CaptureReservation,
    CompositeFrame,
    RecordingCounts,
    RecordingWorker,
)
from cephvr.visual_stimulus.recording.capture_runtime import RecordingCaptureRuntime
from cephvr.visual_stimulus.recording.completion import resolve_video_completion
from cephvr.visual_stimulus.recording.evidence import EvidenceWriter
from cephvr.visual_stimulus.recording.evidence_records import build_clipping_record
from cephvr.visual_stimulus.recording.recipe import PreparedRecipe, publish_recipe
from cephvr.visual_stimulus.recording.session import RecordingSession
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    EvidenceStateSnapshot,
    FeedbackEvidenceSnapshot,
    SubmissionSnapshot,
)


class _Input:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write_chunk(self, data: memoryview) -> int:
        size = min(3, len(data))
        self.data.extend(data[:size])
        return size

    def close_input(self) -> None:
        self.closed = True


class _DelayedInput(_Input):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.pending = False

    def write_chunk(self, data: memoryview) -> int:
        if not self.pending:
            self.events.append("write_pending")
            self.pending = True
            return 0
        self.events.append("write_completed")
        self.pending = False
        self.data.extend(data)
        return len(data)


def _identity() -> Identity:
    return Identity(
        session_id="session",
        trial_id="trial",
        configuration_revision=1,
        prepared_generation="prepared",
        renderer_generation="renderer",
        resource_generation="resources",
    )


def test_recipe_publication_is_precomputed_and_never_overwrites(tmp_path: Path) -> None:
    data = b'{"format_version":2}\n'
    digest = hashlib.sha256(data).hexdigest()
    recipe = PreparedRecipe(data, digest)
    path = tmp_path / "trial_stimulus_LOG.json"
    with pytest.raises(ValueError, match="before released"):
        publish_recipe(
            path,
            "trial_stimulus_LOG.json",
            recipe,
            expected_sha256=digest,
            expected_byte_length=len(data),
            trial_start_host_ns=10,
            now_host_ns=9,
        )
    reference = publish_recipe(
        path,
        "trial_stimulus_LOG.json",
        recipe,
        expected_sha256=digest,
        expected_byte_length=len(data),
        trial_start_host_ns=10,
        now_host_ns=10,
    )
    assert path.read_bytes() == data
    assert reference.sha256 == digest
    with pytest.raises(FileExistsError):
        publish_recipe(
            path,
            "trial_stimulus_LOG.json",
            recipe,
            expected_sha256=digest,
            expected_byte_length=len(data),
            trial_start_host_ns=10,
            now_host_ns=11,
        )


def test_recording_worker_copies_frames_and_prioritizes_evidence(
    tmp_path: Path,
) -> None:
    recipe_data = b"recipe"
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_bytes(recipe_data)
    header = Header(
        kind="header",
        format_version=1,
        identity=_identity(),
        writer_generation="writer",
        recipe=ArtifactRef(
            relative_path="recipe.json",
            sha256=hashlib.sha256(recipe_data).hexdigest(),
            byte_length=len(recipe_data),
            schema_id="prepared-v2",
        ),
        trial_start_host_ns=1,
        required_output_ids=("front",),
        renderer_compatibility="renderer-v1",
    )
    writer = EvidenceWriter(max_pending_bytes=4096)
    evidence_path = tmp_path / "evidence.jsonl"
    writer.open_after_recipe(evidence_path, header, header.recipe)
    writer.enqueue(
        Interval(
            kind="interval",
            interval_id="interval-1",
            phase="begin",
            category="starvation",
            instance_id=None,
            output_id=None,
            occurrence_index=None,
            observation_host_ns=2,
            reason="test",
        )
    )
    encoder = _Input()
    worker = RecordingWorker(
        capture_slots=1,
        evidence=writer,
        encoder=encoder,
        max_encoder_write_chunk=4,
    )
    pixels = bytearray(b"abcdefgh")
    admitted = worker.offer(CompositeFrame(0, 0, 2, 1, "rgba8_bottom_up", pixels))
    pixels[:] = b"XXXXXXXX"
    assert admitted.admitted
    assert (
        worker.offer(
            CompositeFrame(1, 1, 2, 1, "rgba8_bottom_up", b"12345678")
        ).disposition
        == "capacity_drop"
    )
    assert worker.drain_once()  # Header + interval are written before FFmpeg input.
    assert encoder.data == b""
    assert b'"kind":"header"' in evidence_path.read_bytes()
    while worker.drain_once():
        pass
    counts = worker.counts()
    assert counts.admitted_count == 1
    assert counts.input_submitted_count == 1
    assert counts.capacity_drop_count == 1
    assert bytes(encoder.data) == b"abcdefgh"  # A one-row frame needs no vertical flip.
    assert worker.finish_input() == counts
    assert encoder.closed
    writer.close()


@pytest.mark.parametrize(
    ("pixel_format", "pixels", "expected"),
    [
        ("rgba8_bottom_up", b"downUP!!", b"UP!!down"),
        (
            "r10g10b10a2_le_bottom_up",
            b"\x01\x02\x03\xff\x04\x05\x06\xc0",
            b"\x04\x05\x06\x00\x01\x02\x03\x3f",
        ),
    ],
)
def test_rawvideo_abi_flips_rows_and_clears_packed_x_bits(
    pixel_format: str, pixels: bytes, expected: bytes
) -> None:
    writer = EvidenceWriter(max_pending_bytes=64)
    encoder = _Input()
    worker = RecordingWorker(capture_slots=1, evidence=writer, encoder=encoder)
    assert worker.offer(
        CompositeFrame(0, 0, 1, 2, pixel_format, pixels)  # type: ignore[arg-type]
    ).admitted
    while worker.drain_once():
        pass
    assert bytes(encoder.data) == expected
    writer.close()


def test_evidence_pending_budget_fails_instead_of_growing() -> None:
    writer = EvidenceWriter(max_pending_bytes=1)
    with pytest.raises(BufferError, match="evidence_pending_bytes"):
        writer.enqueue_json(b"{}\n")


def test_recording_session_cancel_before_header_reconciles_process_without_output(
    tmp_path: Path,
) -> None:
    evidence = EvidenceWriter(max_pending_bytes=1024)
    events: list[str] = []
    worker = RecordingWorker(capture_slots=1, evidence=evidence, encoder=_Input())
    session = RecordingSession(
        worker=worker,
        evidence=evidence,
        evidence_path=tmp_path / "frames.jsonl",
        recipe_path=tmp_path / "recipe.json",
        max_queued_evidence_bytes=1024,
        finalizer=lambda _counts: (b"{}\n", b"{}\n"),
        startup=lambda: events.append("registered_child_started"),
        failure_cleanup=lambda: events.append("exact_child_reconciled"),
    )
    session.begin_cancel(deadline_ns=10)
    result = None
    for _ in range(100):
        result = session.poll_finished()
        if result is not None:
            break
        import time

        time.sleep(0.005)
    assert result is not None and not result.evidence_closed
    assert events == ["registered_child_started", "exact_child_reconciled"]
    assert not (tmp_path / "frames.jsonl").exists()


def test_empty_review_completion_requires_clean_encoder_exit_and_exact_absence() -> (
    None
):
    empty = RecordingCounts(0, 0, 0, 0, 0, 0, None)
    started_empty = resolve_video_completion(
        empty,
        final_cutoff_known=True,
        every_eligible_group_resolved=True,
        no_partial_input_write=True,
        encoder_cleanup_confirmed=True,
        encoder_finalized=True,
        file_sync_and_close_confirmed=True,
        artifact_present=True,
        artifact_created_by_session=True,
        reserved_path_absent_after_cleanup=False,
    )
    assert (started_empty.content, started_empty.closure) == ("NO_FRAMES", "CLOSED")
    absent_but_unknown_owner = resolve_video_completion(
        empty,
        final_cutoff_known=True,
        every_eligible_group_resolved=True,
        no_partial_input_write=True,
        encoder_cleanup_confirmed=True,
        encoder_finalized=False,
        file_sync_and_close_confirmed=False,
        artifact_present=False,
        artifact_created_by_session=None,
        reserved_path_absent_after_cleanup=True,
    )
    assert absent_but_unknown_owner.closure == "UNCONFIRMED"
    empty_encoder_error = resolve_video_completion(
        empty,
        final_cutoff_known=True,
        every_eligible_group_resolved=True,
        no_partial_input_write=True,
        encoder_cleanup_confirmed=True,
        encoder_finalized=False,
        file_sync_and_close_confirmed=False,
        artifact_present=False,
        artifact_created_by_session=False,
        reserved_path_absent_after_cleanup=True,
    )
    assert empty_encoder_error.closure == "UNCONFIRMED"


def test_video_presence_and_exit_are_insufficient_without_creator_identity() -> None:
    one_frame = RecordingCounts(1, 1, 1, 0, 0, 0, 0)
    outcome = resolve_video_completion(
        one_frame,
        final_cutoff_known=True,
        every_eligible_group_resolved=True,
        no_partial_input_write=True,
        encoder_cleanup_confirmed=True,
        encoder_finalized=True,
        file_sync_and_close_confirmed=True,
        artifact_present=True,
        artifact_created_by_session=None,
        reserved_path_absent_after_cleanup=False,
    )
    assert outcome.closure == "UNCONFIRMED"


def test_pending_capture_remains_owned_until_gl_cancellation_is_confirmed() -> None:
    outcomes: list[bool] = [False, True]
    cancel_calls: list[object] = []
    session_calls: list[CaptureReservation] = []

    class Renderer:
        def cancel_review_capture(self, pending: object) -> bool:
            cancel_calls.append(pending)
            return outcomes.pop(0)

    class Session:
        def cancel_capture(self, reservation: CaptureReservation) -> None:
            session_calls.append(reservation)

        def enqueue_evidence_factory(
            self, _factory: object, *, reserved_bytes: int
        ) -> None:
            assert reserved_bytes > 0

        enqueue_terminal_evidence_factory = enqueue_evidence_factory

    runtime = RecordingCaptureRuntime(
        Renderer(),  # type: ignore[arg-type]
        Session(),  # type: ignore[arg-type]
        NS(native_pixel_format="rgba8_bottom_up", encoder_pixel_format="yuv420p"),
        evidence_pending_bytes=4096,
        capture_slots=1,
    )
    reservation = CaptureReservation(1, 0, 0)
    runtime.pending[1] = (reservation, "pbo-fence")

    assert not runtime.cancel_pending("cutoff")
    assert 1 in runtime.pending
    assert runtime.cancel_pending("cutoff")
    assert not runtime.pending
    assert cancel_calls == ["pbo-fence", "pbo-fence"]
    assert session_calls == [reservation]


def test_capture_exception_still_queues_required_render_evidence() -> None:
    factories = []
    cancelled = []

    class Renderer:
        def capture_review_composite(self, *_args: object) -> object:
            raise RuntimeError("PBO allocation failed")

    class Session:
        def cancel_capture(self, reservation: CaptureReservation) -> None:
            cancelled.append(reservation)

        def enqueue_evidence_factory(
            self, factory: object, *, reserved_bytes: int
        ) -> None:
            assert reserved_bytes > 0
            factories.append(factory)

    state = EvidenceStateSnapshot(0, "scene", 12, (), (), (), ())
    submission = SubmissionSnapshot("front", 0, "returned", 13, 14, 1, 0, True, None)
    runtime = RecordingCaptureRuntime(
        Renderer(),  # type: ignore[arg-type]
        Session(),  # type: ignore[arg-type]
        NS(native_pixel_format="rgba8_bottom_up", encoder_pixel_format="yuv420p"),
        evidence_pending_bytes=4096,
        capture_slots=1,
    )
    reservation = CaptureReservation(3, 0, 0)
    runtime.reservation = reservation
    update = NS(
        group=NS(group_id=0, outputs=(object(),)),
        outputs=(object(),),
        evidence_state=state,
        evidence_submissions=(submission,),
    )
    with pytest.raises(RuntimeError, match="PBO allocation failed"):
        runtime.rendered(update)  # type: ignore[arg-type]
    assert cancelled == [reservation]
    assert runtime.next_group_id == 1
    assert len(factories) == 1
    queued = factories[0]()
    assert queued.state.evaluation_host_ns == 12
    assert queued.submissions[0].output_id == "front"
    assert queued.captures[0].disposition == "transfer_failed"
    assert all(value is not update for value in factories[0].__defaults__ or ())


def test_feedback_evidence_follows_group_and_records_hold_transitions() -> None:
    class Session:
        def __init__(self) -> None:
            self.records: list[object] = []

        def enqueue_evidence_factory(self, factory, *, reserved_bytes: int) -> None:
            self.records.append(factory())

        def enqueue_terminal_evidence_factory(
            self, factory, *, reserved_bytes: int
        ) -> None:
            self.records.append(factory())

    session = Session()
    runtime = RecordingCaptureRuntime(
        renderer=NS(),
        session=session,  # type: ignore[arg-type]
        encoding=NS(native_pixel_format="rgba8_bottom_up"),
        evidence_pending_bytes=4096,
        capture_slots=1,
    )
    runtime.last_group_id = 4
    held = FeedbackEvidenceSnapshot(
        stream_id="stream",
        result_id="r1",
        reset_generation="reset",
        binding_id="binding",
        group_id=None,
        source_frame_ids=(),
        source_receipt_ns=10,
        application_check_ns=11,
        age_limit_ns=None,
        disposition="invalid",
        requested_increment=(),
        applied_increment=(),
        target_units=(),
        target_frame_id=None,
    )
    applied = FeedbackEvidenceSnapshot(
        stream_id="stream",
        result_id="r2",
        reset_generation="reset",
        binding_id="binding",
        group_id=4,
        source_frame_ids=("frame",),
        source_receipt_ns=12,
        application_check_ns=13,
        age_limit_ns=10,
        disposition="applied",
        requested_increment=(1.0,),
        applied_increment=(1.0,),
        target_units=("mm",),
        target_frame_id="target",
    )
    runtime.feedback_snapshots((held,))
    runtime.feedback_snapshots((applied,))

    assert isinstance(session.records[0], FeedbackEvidence)
    assert session.records[0].result_id == "r1"
    assert isinstance(session.records[1], Interval)
    assert session.records[1].phase == "begin"
    assert session.records[2].result_id == "r2"
    assert isinstance(session.records[3], Interval)
    assert session.records[3].phase == "end"
    assert session.records[3].observation_host_ns == 13


def test_clipping_evidence_records_empty_coverage_and_exact_group_output() -> None:
    record = build_clipping_record(
        DiagnosticSnapshot(
            group_id=7,
            output_id="front",
            epoch_index=3,
            evaluation_host_ns=100,
            stages=(),
        )
    )
    assert isinstance(record, Clipping)
    assert record.kind == "clipping"
    assert (record.group_id, record.output_id, record.occurrence_index) == (
        7,
        "front",
        3,
    )
    assert record.observation_host_ns == 100
    assert record.stages == ()


def test_evidence_queue_runs_while_overlapped_encoder_write_is_pending(
    tmp_path: Path,
) -> None:
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_bytes(b"recipe")
    header = Header(
        kind="header",
        format_version=1,
        identity=_identity(),
        writer_generation="writer",
        recipe=ArtifactRef(
            relative_path="recipe.json",
            sha256=hashlib.sha256(b"recipe").hexdigest(),
            byte_length=6,
            schema_id="prepared-v2",
        ),
        trial_start_host_ns=1,
        required_output_ids=("front",),
        renderer_compatibility="renderer-v1",
    )
    evidence = EvidenceWriter(max_pending_bytes=4096)
    evidence.open_after_recipe(tmp_path / "evidence.jsonl", header, header.recipe)
    encoder = _DelayedInput()
    worker = RecordingWorker(capture_slots=1, evidence=evidence, encoder=encoder)
    worker.offer(CompositeFrame(0, 0, 1, 1, "rgba8_bottom_up", b"1234"))
    assert worker.drain_once()  # Write required Header before encoder input.
    assert encoder.events == []
    while evidence.pending_bytes:
        assert worker.drain_once()
    assert worker.drain_once() is False  # Start an overlapped write; no wait.
    assert encoder.events == ["write_pending"]
    evidence.enqueue_json(b'{"kind":"required"}\n')
    assert worker.drain_once()  # Pending evidence progresses before polling FFmpeg.
    assert encoder.events == ["write_pending"]
    while evidence.pending_bytes:
        worker.drain_once()
    assert worker.drain_once()
    assert encoder.events[-1] == "write_completed"
    evidence.close()


@pytest.fixture
def native_recording():
    from uuid import uuid4

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.shared.auth import Principal
    from cephvr.visual_stimulus.recording.native import NativeRecording

    generation = str(uuid4())
    # Construction is pure; these native ports must not be used by cleanup tests.
    recording = NativeRecording(
        ffmpeg_executable=None,
        supervisor=None,
        owner=Principal("visual_stimulus_renderer", generation, "test-token"),
        owner_identity=pb.ProcessIdentity(
            role="visual_stimulus_renderer", generation=generation
        ),
        windows_jobs=None,
        file_sync_owner=None,
        renderer=None,
        video_sync_factory=None,
        clock_ns=lambda: 10,
    )
    recording.saving = True
    recording._probe_aggregate_key = "probe"
    recording._child_key = "child"
    recording._owner_key = "owner"
    recording._capture_key = "capture"
    recording._announced_keys = {"probe", "child", "owner", "capture"}
    return recording


@pytest.mark.parametrize(
    ("attempted", "confirmed", "process_closed", "child_released"),
    [
        (False, True, None, True),
        (True, False, None, False),
        (True, True, None, True),
        (True, True, False, False),
        (True, False, True, True),
    ],
)
@pytest.mark.parametrize("session_pending", [False, True])
def test_recording_cleanup_requires_exact_child_and_session_release(
    native_recording,
    attempted,
    confirmed,
    process_closed,
    child_released,
    session_pending,
):
    recording = native_recording
    owner = recording.encoder_owner
    owner.launch_attempted = attempted
    owner.cleanup_confirmed = confirmed
    owner.process = (
        None if process_closed is None else NS(cleanup_complete=process_closed)
    )
    deadlines = []
    if session_pending:
        recording._session = NS(
            begin_cancel=lambda *, deadline_ns: deadlines.append(deadline_ns),
            poll_finished=lambda: None,
        )
    result = recording.cleanup(123)
    expected = {"probe"}
    if not child_released:
        expected.add("child")
    if session_pending:
        expected.update(("owner", "capture"))
    assert set(result.outstanding) == expected
    assert set(result.released) == recording._announced_keys - expected
    assert deadlines == ([123] if session_pending else [])


def test_recording_cleanup_retains_pending_capture_and_prior_releases(native_recording):
    recording = native_recording
    reasons = []
    capture = NS(pending=True, cancel_pending=reasons.append)
    recording._capture_runtime = capture
    recording._probe_released.add("probe")
    recording._released_keys.add("previous-child")
    recording._owner_key = "unannounced-owner"
    result = recording.cleanup(123)
    assert reasons == ["capture_cleanup"]
    assert result.outstanding == ("capture",)
    assert set(result.released) == {"probe", "child", "previous-child"}
    assert recording._capture_runtime is capture
    capture.pending = False
    final = recording.cleanup(123)
    assert final.outstanding == ()
    assert set(final.released) == {"probe", "child", "capture", "previous-child"}
    assert recording._capture_runtime is None
    assert recording.cleanup(123) == final
