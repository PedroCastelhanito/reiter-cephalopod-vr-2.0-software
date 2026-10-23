from __future__ import annotations

import hashlib
import sys
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from cephvr.platform.windows.paths import extended_path
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


def test_pending_encoder_write_preserves_normalized_row_order() -> None:
    encoder = _DelayedInput()
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        max_encoder_write_chunk=8,
        video_start_ns=0,
    )
    worker.offer(CompositeFrame(0, None, 1, 2, "rgba8_bottom_up", b"bottom!!"))
    assert not worker.drain_once()
    assert worker.drain_once()
    assert encoder.data == b"om!!bott"
    assert worker.counts().input_submitted_count == 1


def test_pixel_normalization_does_not_hold_capture_admission_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.visual_stimulus.recording import capture

    entered, release = threading.Event(), threading.Event()
    original = capture._ffmpeg_input_order

    def normalize(frame: CompositeFrame) -> CompositeFrame:
        entered.set()
        assert release.wait(2)
        return original(frame)

    monkeypatch.setattr(capture, "_ffmpeg_input_order", normalize)
    worker = RecordingWorker(
        capture_slots=2,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=_DelayedInput(),
        video_start_ns=0,
    )
    worker.offer(CompositeFrame(0, None, 1, 2, "rgba8_bottom_up", b"bottom!!"))
    recording = threading.Thread(target=worker.drain_once)
    recording.start()
    try:
        assert entered.wait(2)
        assert worker._lock.acquire(timeout=0.1)
        worker._lock.release()
        reservation, disposition, _ = worker.classify_and_reserve(1, 1_000_000_000)
        assert reservation is not None and disposition == "admitted"
        worker.cancel_reservation(reservation)
    finally:
        release.set()
        recording.join(2)
    assert not recording.is_alive()
    assert worker.drain_once()


@pytest.mark.parametrize("long_path", [False, True])
def test_recipe_publication_is_precomputed_and_never_overwrites(
    tmp_path: Path, long_path: bool
) -> None:
    data = b'{"format_version":2}\n'
    digest = hashlib.sha256(data).hexdigest()
    recipe = PreparedRecipe(data, digest)
    path = tmp_path / (("trial_" * 30 if long_path else "") + "trial_stimulus_LOG.json")
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
    assert (
        Path(extended_path(path) if sys.platform == "win32" else path).read_bytes()
        == data
    )
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


@pytest.mark.parametrize("long_path", [False, True])
def test_recording_worker_copies_frames_and_prioritizes_evidence(
    tmp_path: Path,
    long_path: bool,
) -> None:
    recipe_data = b"recipe"
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_bytes(recipe_data)
    header = Header(
        kind="header",
        format_version=3,
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
    evidence_path = tmp_path / (("frame_" * 30 if long_path else "") + "evidence.jsonl")
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
        video_start_ns=0,
    )
    pixels = bytearray(b"abcdefgh")
    admitted = worker.offer(CompositeFrame(0, None, 2, 1, "rgba8_bottom_up", pixels))
    pixels[:] = b"XXXXXXXX"
    assert admitted.admitted
    assert (
        worker.offer(
            CompositeFrame(
                1,
                None,
                2,
                1,
                "rgba8_bottom_up",
                b"12345678",
                source_host_ns=1_000_000_000,
            )
        ).disposition
        == "capacity_drop"
    )
    assert worker.drain_once()  # Header + interval are written before FFmpeg input.
    assert encoder.data == b""
    assert (
        b'"kind":"header"'
        in Path(
            extended_path(evidence_path) if sys.platform == "win32" else evidence_path
        ).read_bytes()
    )
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
    ("pixel_format", "pixels", "expected", "width", "height"),
    [
        ("rgba8_bottom_up", b"downUP!!", b"UP!!down", 1, 2),
        (
            "rgba8_bottom_up",
            b"abcdefghijklmnopqrstuvwx",
            b"qrstuvwxijklmnopabcdefgh",
            2,
            3,
        ),
        (
            "r10g10b10a2_le_bottom_up",
            b"\x01\x02\x03\xff\x04\x05\x06\xc0",
            b"\x04\x05\x06\x00\x01\x02\x03\x3f",
            1,
            2,
        ),
    ],
)
def test_rawvideo_abi_flips_rows_and_clears_packed_x_bits(
    pixel_format: str, pixels: bytes, expected: bytes, width: int, height: int
) -> None:
    writer = EvidenceWriter(max_pending_bytes=64)
    encoder = _Input()
    worker = RecordingWorker(
        capture_slots=1,
        evidence=writer,
        encoder=encoder,
        video_start_ns=0,
    )
    source = bytearray(pixels)
    assert worker.offer(
        CompositeFrame(0, None, width, height, pixel_format, source)  # type: ignore[arg-type]
    ).admitted
    while worker.drain_once():
        pass
    assert bytes(encoder.data) == expected
    assert source == pixels
    writer.close()


def test_sequential_frames_retain_same_times_and_real_repeats_without_padding() -> None:
    encoder = _Input()
    submitted = []
    worker = RecordingWorker(
        capture_slots=3,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        video_start_ns=0,
        on_submitted=submitted.append,
    )
    for group, timestamp, pixels in [
        (0, 2_000_000_000, b"aaaa"),
        (1, 2_000_000_000, b"aaaa"),
        (2, 9_000_000_000, b"bbbb"),
    ]:
        reservation, disposition, index = worker.classify_and_reserve(group, timestamp)
        assert reservation is not None and (disposition, index) == ("admitted", None)
        worker.complete_capture(
            reservation,
            width=1,
            height=1,
            pixel_format="rgba8_bottom_up",
            pixels=pixels,
        )
    worker.set_cutoff(40_000_000_000)
    while worker.drain_once():
        pass
    counts = worker.finish_input()
    assert (
        counts.eligible_group_count
        == counts.admitted_count
        == counts.selected_real_count
        == 3
    )
    assert counts.encoded_frame_count == counts.input_submitted_count == 3
    assert counts.same_slot_omission_count == counts.duplicate_frame_count == 0
    assert encoder.data == b"aaaaaaaabbbb"
    assert [(f.group_id, f.video_frame_index, f.source_host_ns) for f in submitted] == [
        (0, 0, 2_000_000_000),
        (1, 1, 2_000_000_000),
        (2, 2, 9_000_000_000),
    ]


@pytest.mark.parametrize("cancel_first", [False, True])
def test_out_of_order_readbacks_wait_for_earlier_capture_without_index_holes(
    cancel_first: bool,
) -> None:
    encoder = _Input()
    submitted = []
    worker = RecordingWorker(
        capture_slots=2,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        video_start_ns=0,
        on_submitted=submitted.append,
    )
    first, _, _ = worker.classify_and_reserve(0, 2_000_000_000)
    second, _, _ = worker.classify_and_reserve(1, 3_000_000_000)
    assert first is not None and second is not None
    worker.complete_capture(
        second, width=1, height=1, pixel_format="rgba8_bottom_up", pixels=b"bbbb"
    )
    assert not worker.drain_once()
    if cancel_first:
        worker.cancel_reservation(first)
    else:
        worker.complete_capture(
            first, width=1, height=1, pixel_format="rgba8_bottom_up", pixels=b"aaaa"
        )
    worker.set_cutoff(4_000_000_000)
    while worker.drain_once():
        pass
    assert encoder.data == (b"bbbb" if cancel_first else b"aaaabbbb")
    assert [f.video_frame_index for f in submitted] == list(range(len(submitted)))
    assert [f.group_id for f in submitted] == ([1] if cancel_first else [0, 1])
    assert worker.counts().failed_capture_count == int(cancel_first)


def test_capacity_drop_leaves_no_index_hole_and_releases_single_slot() -> None:
    encoder = _Input()
    submitted = []
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        video_start_ns=0,
        on_submitted=submitted.append,
    )
    assert worker.offer(
        CompositeFrame(0, None, 1, 2, "rgba8_bottom_up", b"downUP!!")
    ).admitted
    assert worker.classify_and_reserve(1, 1) == (None, "capacity_drop", None)
    while worker.drain_once():
        pass
    assert worker.offer(
        CompositeFrame(2, None, 1, 2, "rgba8_bottom_up", b"low!HIGH", 2)
    ).admitted
    worker.set_cutoff(4_000_000_000)
    while worker.drain_once():
        pass
    assert encoder.data == b"UP!!downHIGHlow!"
    assert [(f.group_id, f.video_frame_index) for f in submitted] == [(0, 0), (2, 1)]
    counts = worker.finish_input()
    assert counts.capacity_drop_count == 1
    assert counts.input_submitted_count == counts.selected_real_count == 2


@pytest.mark.parametrize("failure", ["partial_input", "mapping"])
def test_failed_input_or_mapping_cannot_retry_or_finalize(failure: str) -> None:
    encoder = _Input()
    submitted = []

    def record(frame: CompositeFrame) -> None:
        submitted.append(frame)
        raise OSError("mapping failed")

    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        video_start_ns=0,
        on_submitted=record,
    )
    worker.offer(CompositeFrame(0, None, 1, 1, "rgba8_bottom_up", b"aaaa"))
    assert worker.drain_once()  # three of four input bytes; no published index
    assert not submitted
    if failure == "partial_input":

        def fail(_data: memoryview) -> int:
            raise OSError("input failed")

        encoder.write_chunk = fail  # type: ignore[method-assign]
    with pytest.raises(OSError, match="failed"):
        worker.drain_once()
    accepted = 1 if failure == "mapping" else 0
    assert worker.counts().input_submitted_count == accepted
    assert len(submitted) == accepted
    size = len(encoder.data)
    with pytest.raises(RuntimeError, match="cannot retry"):
        worker.drain_once()
    with pytest.raises(RuntimeError):
        worker.finish_input()
    assert len(encoder.data) == size
    assert not encoder.closed


def test_evidence_pending_budget_fails_instead_of_growing() -> None:
    writer = EvidenceWriter(max_pending_bytes=1)
    with pytest.raises(BufferError, match="evidence_pending_bytes"):
        writer.enqueue_json(b"{}\n")


def test_recording_session_cancel_before_header_reconciles_process_without_output(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    evidence = EvidenceWriter(max_pending_bytes=1024)
    events: list[str] = []
    caplog.set_level("INFO", logger="cephvr.visual_stimulus.recording.session")
    worker = RecordingWorker(
        capture_slots=1,
        evidence=evidence,
        encoder=_Input(),
        video_start_ns=0,
    )
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

    assert not any("recording_metrics" in r.getMessage() for r in caplog.records)


def test_recording_session_services_video_sync_independently_of_evidence_sync(
    tmp_path: Path,
) -> None:
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_bytes(b"recipe")
    recipe = ArtifactRef(
        relative_path="recipe.json",
        sha256=hashlib.sha256(b"recipe").hexdigest(),
        byte_length=6,
        schema_id="prepared-v2",
    )
    header = Header(
        kind="header",
        format_version=3,
        identity=_identity(),
        writer_generation="writer",
        recipe=recipe,
        trial_start_host_ns=1,
        required_output_ids=("front",),
        renderer_compatibility="renderer-v1",
    )
    evidence = EvidenceWriter(max_pending_bytes=4096)
    worker = RecordingWorker(
        capture_slots=1,
        evidence=evidence,
        encoder=_Input(),
        video_start_ns=0,
    )
    clock_ns = [0]
    calls = 0

    def drain_once() -> bool:
        nonlocal calls
        calls += 1
        clock_ns[0] += 250_000_000
        return calls <= 4

    worker.drain_once = drain_once  # type: ignore[method-assign]
    video_sync_times: list[int] = []

    def periodic_sync() -> None:
        clock_ns[0] += 250_000_000
        video_sync_times.append(clock_ns[0])

    session = RecordingSession(
        worker=worker,
        evidence=evidence,
        evidence_path=tmp_path / "frames.jsonl",
        recipe_path=recipe_path,
        max_queued_evidence_bytes=4096,
        finalizer=lambda _counts: (b"{}\n", b"{}\n"),
        sync_interval_ns=1_000_000_000,
        periodic_sync=periodic_sync,
        clock_ns=lambda: clock_ns[0],
    )
    for _ in range(4):
        session.enqueue_evidence_json(b'{"kind":"evidence"}\n')
    session.publish_header(header, recipe)
    session.begin_finish(cutoff_ns=1_000_000_000, deadline_ns=2_000_000_000)

    result = None
    for _ in range(200):
        result = session.poll_finished()
        if result is not None:
            break
        import time

        time.sleep(0.005)

    assert result is not None and result.evidence_closed
    assert video_sync_times[:4] == [
        250_000_000,
        500_000_000,
        750_000_000,
        1_000_000_000,
    ]


def test_recording_finish_publishes_exact_cutoff_before_closing_wakes_owner(
    tmp_path: Path,
) -> None:
    evidence = EvidenceWriter(max_pending_bytes=1024)
    worker = RecordingWorker(
        capture_slots=1,
        evidence=evidence,
        encoder=_Input(),
        video_start_ns=1,
    )
    session = RecordingSession(
        worker=worker,
        evidence=evidence,
        evidence_path=tmp_path / "frames.jsonl",
        recipe_path=tmp_path / "recipe.json",
        max_queued_evidence_bytes=1024,
        finalizer=lambda _counts: (b"{}\n", b"{}\n"),
    )
    original_set_cutoff = worker.set_cutoff
    observed = []

    def set_cutoff_before_close(cutoff_ns: int) -> None:
        assert not session._closing
        original_set_cutoff(cutoff_ns)
        observed.append(cutoff_ns)

    worker.set_cutoff = set_cutoff_before_close  # type: ignore[method-assign]
    session.begin_finish(cutoff_ns=2_000_000_001, deadline_ns=3_000_000_000)
    assert observed == [2_000_000_001]
    assert worker._cutoff_ns == 2_000_000_001


def test_native_preonset_cancel_closes_real_session_without_cadence_cutoff(
    native_recording, tmp_path: Path
) -> None:
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    recording = native_recording
    now = [99]
    recording.clock_ns = lambda: now[0]
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=1024),
        encoder=_Input(),
        video_start_ns=100,
    )
    events: list[str] = []
    session = RecordingSession(
        worker=worker,
        evidence=worker.evidence,
        evidence_path=tmp_path / "frames.jsonl",
        recipe_path=tmp_path / "recipe.json",
        max_queued_evidence_bytes=1024,
        finalizer=lambda _counts: (b"{}\n", b"{}\n"),
        failure_cleanup=lambda: events.append("closed"),
    )
    schedule = visual.WorkerSchedule(start_monotonic_ns=100)
    schedule.outputs.add(
        output_key="video",
        output_tag="stimulus",
        path=str(tmp_path / "video.mp4"),
    )
    schedule.outputs.add(
        output_key="frames",
        output_tag="stimulus_frames",
        path=str(tmp_path / "frames.jsonl"),
    )
    recording._schedule = schedule
    recording._session = session
    recording._video_path = tmp_path / "video.mp4"
    recording._evidence_path = tmp_path / "frames.jsonl"

    recording.begin_cancel(deadline_ns=250)
    assert recording._cutoff_ns is None
    assert recording._finish_deadline_ns == 250
    assert worker._cutoff_ns is None
    now[0] = 120
    recording.begin_cancel(deadline_ns=300)
    recording.begin_finish(cutoff_ns=120, deadline_ns=300)
    assert recording._cutoff_ns is None
    assert recording._finish_deadline_ns == 250
    assert worker._cutoff_ns is None
    result = None
    for _ in range(100):
        result = recording.poll_finished()
        if result is not None:
            break
        import time

        time.sleep(0.005)
    assert result is not None
    assert events == ["closed"]
    assert worker._cutoff_ns is None


def test_native_cleanup_keeps_first_cutoff_and_original_finish_deadline(
    native_recording, tmp_path: Path
) -> None:
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    recording = native_recording
    now = [20_000_000_000]
    recording.clock_ns = lambda: now[0]
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=1024),
        encoder=_Input(),
        video_start_ns=10_000_000_000,
    )
    session = RecordingSession(
        worker=worker,
        evidence=worker.evidence,
        evidence_path=tmp_path / "frames.jsonl",
        recipe_path=tmp_path / "recipe.json",
        max_queued_evidence_bytes=1024,
        finalizer=lambda _counts: (b"{}\n", b"{}\n"),
        failure_cleanup=lambda: None,
    )
    recording._schedule = visual.WorkerSchedule(start_monotonic_ns=10_000_000_000)
    recording._session = session

    recording.begin_finish(cutoff_ns=15_000_000_000, deadline_ns=100_000_000_000)
    assert worker._cutoff_ns == 15_000_000_000
    now[0] = 30_000_000_000
    recording.begin_cancel(deadline_ns=200_000_000_000)
    assert recording._cutoff_ns == 15_000_000_000
    assert recording._finish_deadline_ns == 100_000_000_000
    assert worker._cutoff_ns == 15_000_000_000


def test_native_cancel_after_trial_end_uses_scheduled_end_as_cutoff(
    native_recording, tmp_path: Path
) -> None:
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    recording = native_recording
    recording.clock_ns = lambda: 30_000_000_000
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=1024),
        encoder=_Input(),
        video_start_ns=10_000_000_000,
    )
    session = RecordingSession(
        worker=worker,
        evidence=worker.evidence,
        evidence_path=tmp_path / "frames.jsonl",
        recipe_path=tmp_path / "recipe.json",
        max_queued_evidence_bytes=1024,
        finalizer=lambda _counts: (b"{}\n", b"{}\n"),
        failure_cleanup=lambda: None,
    )
    recording._schedule = visual.WorkerSchedule(
        start_monotonic_ns=10_000_000_000,
        normal_end_monotonic_ns=25_000_000_000,
    )
    recording._session = session

    recording.begin_cancel(deadline_ns=40_000_000_000)
    assert recording._cutoff_ns == 25_000_000_000
    assert recording._finish_deadline_ns == 40_000_000_000
    assert worker._cutoff_ns == 25_000_000_000
    result = None
    for _ in range(100):
        result = recording.poll_finished()
        if result is not None:
            break
        import time

        time.sleep(0.005)
    assert result is not None


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
    one_frame = RecordingCounts(
        1, 1, 1, 0, 0, 0, 0, encoded_frame_count=1, selected_real_count=1
    )
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


def test_capacity_drops_complete_capture_reconciliation_for_video_closure() -> None:
    counts = RecordingCounts(
        eligible_group_count=2,
        admitted_count=1,
        input_submitted_count=1,
        capacity_drop_count=1,
        failed_capture_count=0,
        unresolved_capture_count=0,
        final_input_group_id=0,
        encoded_frame_count=1,
        same_slot_omission_count=0,
        selected_real_count=1,
    )
    result = resolve_video_completion(
        counts,
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
    assert (result.content, result.closure) == ("FRAMES_SUBMITTED", "CLOSED")
    assert (
        resolve_video_completion(
            counts,
            final_cutoff_known=True,
            every_eligible_group_resolved=False,
            no_partial_input_write=True,
            encoder_cleanup_confirmed=True,
            encoder_finalized=True,
            file_sync_and_close_confirmed=True,
            artifact_present=True,
            artifact_created_by_session=True,
            reserved_path_absent_after_cleanup=False,
        ).closure
        == "UNCONFIRMED"
    )


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


@pytest.mark.parametrize("queue_sealed", [False, True])
@pytest.mark.parametrize("gl_retry", ["none", "pending", "error"])
def test_capture_cancellation_releases_resources_despite_evidence_failure(
    native_recording, queue_sealed, gl_retry
):
    from collections import deque

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    evidence = EvidenceWriter(max_pending_bytes=4096)
    worker = RecordingWorker(
        capture_slots=2, evidence=evidence, encoder=_Input(), video_start_ns=0
    )
    # A stopped recorder can retain byte reservations when serialization fails.
    # Exercise the real queue guard without starting a recording thread.
    session = object.__new__(RecordingSession)
    session.worker = worker
    session.evidence = evidence
    session._condition = threading.Condition()
    session._closing = queue_sealed
    session.max_queued_evidence_bytes = 4096
    session._line_bytes = 4096
    session._lines = deque()
    gl_calls = []

    def cancel(pending):
        gl_calls.append(pending)
        if pending == "first" and gl_calls.count("first") == 1:
            if gl_retry == "pending":
                return False
            if gl_retry == "error":
                raise RuntimeError("GL deletion failed")
        return True

    runtime = RecordingCaptureRuntime(
        NS(cancel_review_capture=cancel),
        session,
        NS(native_pixel_format="rgba8_top_down", encoder_pixel_format="yuv420p"),
        evidence_pending_bytes=4096,
        capture_slots=2,
    )
    for group, handle in enumerate(("first", "second")):
        reservation, _, _ = worker.classify_and_reserve(group, group)
        assert reservation is not None
        runtime.pending[reservation.token] = (reservation, handle)
    expected = RuntimeError if queue_sealed else BufferError
    with pytest.raises(expected, match="sealed|evidence_pending_bytes"):
        runtime.cancel_pending("capture_cleanup")
    # Required logging failure is still raised, after both releases are attempted.
    assert gl_calls == ["first", "second"]
    assert not worker._reservations
    assert worker.counts().failed_capture_count == 2
    assert worker.counts().input_submitted_count == 0
    assert worker.counts().unresolved_capture_count == 0
    assert len(runtime.pending) == (0 if gl_retry == "none" else 1)
    assert runtime.cancel_pending("capture_cleanup")
    assert not runtime.pending
    assert worker.counts().failed_capture_count == 2
    assert gl_calls == ["first", "second"] + ([] if gl_retry == "none" else ["first"])
    assert not session._lines  # no invented replacement for missing evidence
    # Completing resource cleanup must not promote the stopped recorder to success.
    session._done = True
    session._error = BufferError("original evidence serialization failure")
    session._result = None
    session._thread = NS(is_alive=lambda: False)
    recording = native_recording
    recording._session = session
    recording._capture_runtime = runtime
    recording._schedule = visual.WorkerSchedule(start_monotonic_ns=0)
    for tag in ("stimulus", "stimulus_frames"):
        recording._schedule.outputs.add(output_key=tag, output_tag=tag, path=f"/{tag}")
    recording.begin_cancel(123)
    results = recording.poll_finished()
    assert results is not None and len(results) == 2
    assert all(result.closure == pb.OUTPUT_CLOSURE_FAILED for result in results)
    assert all(
        "original evidence serialization failure" in result.failure.message
        for result in results
    )
    assert recording._finish_deadline_ns == 123
    recording._probe_released.add("probe")
    cleanup = recording.cleanup(999)
    assert not cleanup.outstanding
    assert {"owner", "capture"} <= set(cleanup.released)
    assert recording._capture_runtime is None


def test_capture_exception_still_queues_required_render_evidence() -> None:
    factories = []
    cancelled = []

    class Renderer:
        def capture_review_composite(self, *_args: object) -> object:
            raise RuntimeError("PBO allocation failed")

    class Session:
        def classify_capture(self, group_id: int, evaluation_host_ns: int):
            assert evaluation_host_ns == 12
            return (
                CaptureReservation(3, group_id, evaluation_host_ns),
                "admitted",
                0,
            )

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
    reservation = CaptureReservation(3, 0, 12)
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


@pytest.mark.parametrize("output_id", ["\x00" * 128, "😀" * 128, '"\\' * 64])
def test_clipping_reservation_covers_maximum_schema_record(output_id: str) -> None:
    from cephvr.visual_stimulus.config.models.evidence_model import EvidenceRecord

    reservations = []

    def enqueue(factory, *, reserved_bytes: int) -> None:
        encoded = EvidenceWriter._encode(EvidenceRecord(payload=factory()))
        assert len(encoded) <= reserved_bytes == 2048
        reservations.append(reserved_bytes)

    runtime = RecordingCaptureRuntime(
        NS(),
        NS(enqueue_evidence_factory=enqueue),
        None,
        evidence_pending_bytes=16_777_216,
        capture_slots=1,
    )
    runtime.last_group_id = (1 << 64) - 1
    runtime.diagnostics(
        (
            DiagnosticSnapshot(
                (1 << 64) - 1,
                output_id,
                (1 << 32) - 1,
                (1 << 63) - 1,
                ("alpha", "linear_output", "device_code"),
            ),
        )
    )
    assert reservations == [2048]


def test_clipping_burst_retains_all_records_across_recording_stall(
    tmp_path: Path,
) -> None:
    import json
    import time

    gate = threading.Event()
    recipe = ArtifactRef(
        relative_path="recipe.json",
        sha256="a" * 64,
        byte_length=1,
        schema_id="prepared-v2",
    )
    header = Header(
        kind="header",
        format_version=3,
        identity=_identity(),
        writer_generation="writer",
        recipe=recipe,
        trial_start_host_ns=1,
        required_output_ids=("front", "left", "right", "bottom"),
        renderer_compatibility="renderer-v1",
    )
    path = tmp_path / "frames.jsonl"
    session = RecordingSession(
        worker=None,
        evidence=EvidenceWriter(max_pending_bytes=16_777_216),
        evidence_path=path,
        recipe_path=tmp_path / "recipe.json",
        max_queued_evidence_bytes=16_777_216,
        finalizer=lambda _counts: (),
        startup=lambda: gate.wait(5),
    )
    runtime = RecordingCaptureRuntime(
        NS(), session, None, evidence_pending_bytes=16_777_216, capture_slots=1
    )
    state = EvidenceStateSnapshot(0, "scene", 12, (), (), (), ())
    try:
        session.publish_header(header, recipe)
        for group in range(32):
            runtime.rendered(
                NS(
                    group=NS(group_id=group, outputs=()),
                    evidence_state=state,
                    evidence_submissions=(),
                )
            )
            runtime.diagnostics(
                tuple(
                    DiagnosticSnapshot(group, face, 0, 12, ())
                    for face in ("front", "left", "right", "bottom")
                )
            )
        assert session._line_bytes < session.max_queued_evidence_bytes
        # Old 256 KiB clipping reservations exhausted 16 MiB after only 12 groups.
        assert 32 * 5 * 256 * 1024 > session.max_queued_evidence_bytes
    finally:
        gate.set()
        result = session.finish(deadline_ns=time.perf_counter_ns() + 5_000_000_000)
    assert result.evidence_closed
    records = [json.loads(line)["payload"] for line in path.read_text().splitlines()]
    assert [r["group_id"] for r in records if r["kind"] == "render_group"] == list(
        range(32)
    )
    assert [
        (r["group_id"], r["output_id"]) for r in records if r["kind"] == "clipping"
    ] == [
        (group, face)
        for group in range(32)
        for face in ("front", "left", "right", "bottom")
    ]


def test_evidence_queue_runs_while_overlapped_encoder_write_is_pending(
    tmp_path: Path,
) -> None:
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_bytes(b"recipe")
    header = Header(
        kind="header",
        format_version=3,
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
    worker = RecordingWorker(
        capture_slots=1,
        evidence=evidence,
        encoder=encoder,
        video_start_ns=0,
    )
    worker.offer(CompositeFrame(0, None, 1, 1, "rgba8_bottom_up", b"1234"))
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
    cancellation = []
    if session_pending:
        recording._session = NS(
            begin_cancel=lambda **values: cancellation.append(values),
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
    assert cancellation == (
        [{"deadline_ns": 123, "cutoff_ns": 10}] if session_pending else []
    )


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


def test_setup_declares_each_encoder_child_before_ready(native_recording, tmp_path):
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    recording = native_recording
    recording.ffmpeg_executable = tmp_path / "ffmpeg.exe"
    recording.nvenc_owner = NS()
    request = visual.WorkerSetup()
    request.settings.save_visual_stimulus_data = True
    request.session.trials.add().context.trial_id = "first"
    request.session.trials.add().context.trial_id = "second"
    request.policies.limits.capture_slots = 1
    request.policies.limits.evidence_pending_bytes = 1024
    request.policies.limits.max_prepared_plan_bytes = 1024
    for field in (
        "record_sync_interval_ns",
        "video_sync_interval_ns",
        "fragment_target_ns",
        "encoder_stall_timeout_ns",
        "record_stall_timeout_ns",
    ):
        setattr(request.policies, field, 1)
    announced = []
    recording.configure(request, lambda key, path: announced.append(key), 100)
    assert {"ffmpeg-child:first", "ffmpeg-child:second"} <= set(announced)
    closed = recording.cleanup(100)
    assert {"ffmpeg-child:first", "ffmpeg-child:second"} <= set(closed.released)
    assert not closed.outstanding


@pytest.mark.parametrize("ready", [False, True])
def test_normal_finish_drains_admitted_gpu_capture_before_sealing(
    native_recording, ready
):
    recording = native_recording
    now = [10]
    events = []
    capture = NS(pending={1: "admitted-pbo"})

    def poll():
        events.append("poll")
        if ready:
            capture.pending.clear()

    def cancel(reason):
        assert now[0] >= 20
        events.append(reason)
        capture.pending.clear()

    capture.poll_pending = poll
    capture.cancel_pending = cancel
    capture.close_feedback_intervals = lambda cutoff: events.append(
        ("feedback", cutoff)
    )
    recording.clock_ns = lambda: now[0]
    recording._capture_runtime = capture
    recording._session = NS(
        begin_finish=lambda **values: events.append(values),
        poll_finished=lambda: None,
    )
    recording.begin_finish(5, 20)
    assert events == [("feedback", 5)]
    assert recording.poll_finished() is None
    if not ready:
        assert events == [("feedback", 5), "poll"]
        now[0] = 20
        assert recording.poll_finished() is None
        assert "capture_unresolved_at_finalization_deadline" in events
    else:
        assert "capture_unresolved_at_finalization_deadline" not in events
    assert events[-1] == {"cutoff_ns": 5, "deadline_ns": 20}


def test_image_selection_evidence_preserves_repeated_actual_indices():
    from cephvr.visual_stimulus.config.models.evidence_model import EvidenceRecord
    from cephvr.visual_stimulus.recording.evidence_records import (
        build_render_group_record,
    )
    from cephvr.visual_stimulus.rendering.types import ImageSnapshot

    for group, requested, actual, repeated in (
        (0, 0, 0, False),
        (1, 1, 0, True),
        (2, 2, 0, True),
        (3, 2, 2, False),
    ):
        state = EvidenceStateSnapshot(
            group,
            "scene",
            group * 1_000_000,
            ("layer",),
            (),
            (),
            (),
            (
                ImageSnapshot(
                    "layer",
                    f"image-{requested}",
                    requested,
                    f"image-{actual}",
                    actual,
                    "current" if requested == actual else "residency_hold",
                    repeated,
                ),
            ),
        )
        record = build_render_group_record(group, state, (), (), "rgba", "yuv420p")
        decoded = EvidenceRecord.model_validate_json(
            EvidenceRecord(payload=record).model_dump_json()
        )
        image = decoded.payload.state.images[0]
        assert (image.requested_image_index, image.image_index, image.repeated) == (
            requested,
            actual,
            repeated,
        )
        assert image.asset_id == f"image-{actual}"
        assert image.disposition == (
            "current" if requested == actual else "residency_hold"
        )


@pytest.mark.parametrize("owned", [False, True])
def test_capture_handoff_owns_buffer_through_partial_blocked_writes(
    owned: bool,
) -> None:
    class BlockedInput(_Input):
        blocked = True

        def write_chunk(self, data: memoryview) -> int:
            return 0 if self.blocked else super().write_chunk(data)

    encoder = BlockedInput()
    submitted = []
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        video_start_ns=0,
        on_submitted=submitted.append,
    )
    reservation, _, _ = worker.classify_and_reserve(0, 0)
    assert reservation is not None
    pixels = bytearray(b"AAAABBBB")
    worker.complete_capture(
        reservation,
        width=1,
        height=2,
        pixel_format="rgba8_bottom_up",
        pixels=pixels,
        take_ownership=owned,
    )
    if not owned:
        pixels[:] = b"xxxxxxxx"
    assert not worker.drain_once()
    assert worker.classify_and_reserve(1, 1_000_000_000)[1] == "capacity_drop"
    with pytest.raises(RuntimeError, match="admitted captures"):
        worker.finish_input()
    encoder.blocked = False
    for _ in range(10):
        if not worker.drain_once():
            break
    assert encoder.data == b"BBBBAAAA"
    assert len(submitted) == 1
    assert (submitted[0].pixels is pixels) == owned
    assert worker.metrics.snapshot()["active_capture_slots"] == 0
    next_reservation, _, _ = worker.classify_and_reserve(2, 2_000_000_000)
    assert next_reservation is not None
    worker.cancel_reservation(next_reservation)
    worker.finish_input()
    assert encoder.closed


def test_capture_metrics_bound_pending_frames_and_separate_waits() -> None:
    now = [0]
    encoder = _DelayedInput()
    worker = RecordingWorker(
        capture_slots=2,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        video_start_ns=0,
        clock_ns=lambda: now[0],
    )
    first, _, _ = worker.classify_and_reserve(0, 0)
    now[0] = 10
    second, _, _ = worker.classify_and_reserve(1, 1_000_000_000)
    assert first is not None and second is not None
    now[0] = 20
    worker.complete_capture(
        second,
        width=1,
        height=1,
        pixel_format="rgba8_bottom_up",
        pixels=bytearray(b"BBBB"),
        take_ownership=True,
    )
    assert not worker.drain_once()  # Earlier GPU capture remains unresolved.
    for group in range(2, 100):
        assert (
            worker.classify_and_reserve(group, group * 1_000_000_000)[1]
            == "capacity_drop"
        )
    assert worker.metrics.snapshot()["active_capture_slots"] == 2
    now[0] = 30
    worker.complete_capture(
        first, width=1, height=1, pixel_format="rgba8_bottom_up", pixels=b"AAAA"
    )
    now[0] = 40
    assert not worker.drain_once()
    now[0] = 50
    assert worker.drain_once()
    now[0] = 60
    assert not worker.drain_once()
    now[0] = 70
    assert worker.drain_once()
    assert encoder.data == b"AAAABBBB"
    result = worker.metrics.snapshot()
    assert result["active_capture_slots"] == result["queued_captures"] == 0
    assert result["peak_capture_slots"] == 2
    assert result["submitted_bytes"] == 8
    assert result["zero_progress_writes"] == 2
    assert result["stages_ns"]["capture_ready"] == {"count": 2, "total": 40, "max": 30}
    assert result["stages_ns"]["queue_wait"] == {"count": 2, "total": 50, "max": 40}
    assert result["stages_ns"]["slot_hold"] == {"count": 2, "total": 110, "max": 60}
    assert result["stages_ns"]["frame_input"] == {"count": 2, "total": 20, "max": 10}
    assert len(result["stages_ns"]) == 8
    assert result["worst_stage_samples"]["queue_wait"] == {
        "group_id": 1,
        "start_monotonic_ns": 20,
        "end_monotonic_ns": 60,
        "elapsed_ns": 40,
    }
    assert result["worst_stage_samples"]["frame_input"] == {
        "group_id": 0,
        "video_frame_index": 0,
        "start_monotonic_ns": 40,
        "end_monotonic_ns": 50,
        "elapsed_ns": 10,
        "write_attempts": 2,
        "zero_progress_writes": 1,
    }
    assert result["unfinished_frame_input"] is None
    assert len(result["worst_stage_samples"]) <= len(result["stages_ns"])
    result["worst_stage_samples"]["queue_wait"]["group_id"] = -1
    assert (
        worker.metrics.snapshot()["worst_stage_samples"]["queue_wait"]["group_id"] == 1
    )


def test_invalid_capture_completion_preserves_reservation_and_cancel_releases_metrics() -> (
    None
):
    from dataclasses import replace

    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=_Input(),
        video_start_ns=0,
    )
    reservation, _, _ = worker.classify_and_reserve(0, 0)
    assert reservation is not None
    with pytest.raises(TypeError, match="bytearray"):
        worker.complete_capture(
            reservation,
            width=1,
            height=1,
            pixel_format="rgba8_bottom_up",
            pixels=b"AAAA",
            take_ownership=True,
        )
    with pytest.raises(RuntimeError, match="stale"):
        worker.complete_capture(
            replace(reservation, group_id=1),
            width=1,
            height=1,
            pixel_format="rgba8_bottom_up",
            pixels=bytearray(b"AAAA"),
            take_ownership=True,
        )
    assert worker.counts().unresolved_capture_count == 1
    worker.cancel_reservation(reservation)
    assert worker.metrics.snapshot()["active_capture_slots"] == 0
    assert worker.metrics.snapshot()["cancelled_captures"] == 1
    with pytest.raises(RuntimeError, match="stale"):
        worker.cancel_reservation(reservation)
    worker.finish_input()


def test_readback_poll_transfers_native_buffer_and_records_bounded_timings() -> None:
    now = [0]
    pixels = bytearray(b"RGBA")
    returns = iter((None, pixels))
    submitted = []
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=_Input(),
        video_start_ns=0,
        clock_ns=lambda: now[0],
        on_submitted=submitted.append,
    )
    reservation, _, _ = worker.classify_and_reserve(0, 0)
    assert reservation is not None

    def poll(_pending):
        now[0] += 5
        return next(returns)

    session = NS(
        metrics=worker.metrics,
        complete_capture=worker.complete_capture,
        enqueue_evidence_factory=lambda *_args, **_kwargs: None,
    )
    runtime = RecordingCaptureRuntime(
        NS(poll_review_capture=poll),
        session,
        NS(
            composite_width=1,
            composite_height=1,
            native_pixel_format="rgba8_bottom_up",
            encoder_pixel_format="yuv420p",
        ),
        evidence_pending_bytes=4096,
        capture_slots=1,
    )
    runtime.pending[reservation.token] = (reservation, object())
    runtime.poll_pending()
    assert len(runtime.pending) == 1
    runtime.poll_pending()
    assert not runtime.pending
    while worker.drain_once():
        pass
    assert submitted[0].pixels is pixels
    stages = worker.metrics.snapshot()["stages_ns"]
    assert stages["readback_poll_ready"] == {"count": 1, "total": 5, "max": 5}
    assert stages["readback_poll_pending"] == {"count": 1, "total": 5, "max": 5}


@pytest.mark.parametrize("consumed", [-1, 5])
def test_invalid_encoder_count_does_not_inflate_diagnostics(consumed: int) -> None:
    encoder = NS(write_chunk=lambda _data: consumed)
    worker = RecordingWorker(
        capture_slots=1,
        evidence=EvidenceWriter(max_pending_bytes=4096),
        encoder=encoder,
        video_start_ns=0,
    )
    worker.offer(CompositeFrame(0, None, 1, 1, "rgba8_bottom_up", b"RGBA"))
    with pytest.raises(RuntimeError, match="invalid write count"):
        worker.drain_once()
    assert worker.metrics.snapshot()["submitted_bytes"] == 0
    assert worker.counts().input_submitted_count == 0
    assert worker.counts().unresolved_capture_count == 1


@pytest.mark.parametrize("cancel", [False, True])
def test_native_video_off_retains_scientific_evidence_without_native_ports(
    native_recording, tmp_path, cancel
):
    import json

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.visual_stimulus.recording.recipe import prepare_recipe
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    from .support import make_prepared_trial

    recording = native_recording
    setup = visual.WorkerSetup()
    setup.settings.save_visual_stimulus_data = False
    setup.policies.limits.evidence_pending_bytes = 1_000_000
    setup.policies.limits.max_prepared_plan_bytes = 1_000_000
    setup.policies.record_sync_interval_ns = 1_000_000
    setup.policies.record_stall_timeout_ns = 1_000_000
    announced = []
    recording.configure(setup, lambda key, path: announced.append(key), 100)
    assert len(announced) == 1 and announced[0].startswith("recording-owner:")
    artifact = make_prepared_trial()
    assert artifact.review_encoding is None
    recording.prepare_artifacts((artifact,), 100).result(timeout=1)
    recipe = prepare_recipe(artifact, max_bytes=1_000_000)
    request = visual.WorkerSchedule(start_monotonic_ns=10, normal_end_monotonic_ns=100)
    request.command.target.work.trial.trial_id = artifact.identity.trial_id
    request.prepared.plan_sha256 = recipe.sha256
    for tag, extension in (("stimulus_LOG", "json"), ("stimulus_frames", "jsonl")):
        request.outputs.add(
            output_key=tag,
            output_tag=tag,
            extension=extension,
            path=str(tmp_path / f"trial_{tag}.{extension}"),
        )
    recording.schedule(request, artifact).result(timeout=1)
    assert recording._worker is None and recording._video_path is None
    if cancel:
        recording.begin_cancel(200)
    else:
        recipe_path = tmp_path / "trial_stimulus_LOG.json"
        recipe_path.write_bytes(recipe.data)
        recording.publication(
            visual.WorkerRecipePublication(
                published=True, prepared=request.prepared, path=str(recipe_path)
            )
        )
        state = EvidenceStateSnapshot(
            0, artifact.epochs[0].scene_id, 12, (), (), (), (), ()
        )
        update = NS(
            group=NS(group_id=0, outputs=()),
            evidence_state=state,
            evidence_submissions=(),
            feedback_evidence=(
                FeedbackEvidenceSnapshot(
                    stream_id="stream",
                    result_id="r1",
                    reset_generation="reset",
                    binding_id="binding",
                    group_id=None,
                    source_frame_ids=(),
                    source_receipt_ns=10,
                    application_check_ns=12,
                    age_limit_ns=None,
                    disposition="invalid",
                    requested_increment=(),
                    applied_increment=(),
                    target_units=(),
                    target_frame_id=None,
                ),
            ),
        )
        recording.before_render()
        recording.rendered(update)
        recording.diagnostics(
            (
                DiagnosticSnapshot(
                    0, artifact.display.active_outputs[0].output_id, 0, 12, ()
                ),
            )
        )
        recording.begin_finish(100, 200)
    result = None
    for _ in range(1000):
        result = recording.poll_finished()
        if result is not None:
            break
        threading.Event().wait(0.001)
    assert result is not None and len(result) == 1
    assert result[0].closure == (
        pb.OUTPUT_CLOSURE_NOT_STARTED if cancel else pb.OUTPUT_CLOSURE_CLOSED
    )
    assert not list(tmp_path.glob("*.mp4"))
    if not cancel:
        rows = [
            json.loads(line)["payload"]
            for line in Path(result[0].path).read_text().splitlines()
        ]
        assert [row["kind"] for row in rows] == [
            "header",
            "render_group",
            "feedback",
            "interval",
            "clipping",
            "interval",
            "completion",
        ]
        assert rows[0]["video_enabled"] is False and rows[0]["format_version"] == 6
        assert rows[1]["captures"] == []
        assert rows[1]["state"]["evaluation_host_ns"] == 12
        assert rows[-2]["phase"] == "end" and rows[-2]["observation_host_ns"] == 100
        assert rows[-1]["state_count"] == 1 and rows[-1]["capture_admission_count"] == 0
    assert not recording.cleanup(200).outstanding


@pytest.mark.parametrize("evidence_closed", [True, False])
def test_output_counts_use_completed_writer_evidence(evidence_closed):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.visual_stimulus.recording.outcomes import closed_results
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    schedule = visual.WorkerSchedule()
    for tag in ("stimulus", "stimulus_frames"):
        schedule.outputs.add(output_key=tag, output_tag=tag, path=f"/{tag}")
    counts = RecordingCounts(
        eligible_group_count=0,
        admitted_count=0,
        input_submitted_count=0,
        capacity_drop_count=0,
        failed_capture_count=0,
        unresolved_capture_count=0,
        final_input_group_id=None,
    )
    video, frames = closed_results(
        schedule,
        counts,
        encoder_exit=0,
        cutoff_known=True,
        encoder_cleanup_confirmed=True,
        video_sync_closed=True,
        evidence_closed=evidence_closed,
        artifact_present=False,
        artifact_created_by_session=False,
        state_count=7,
    )
    assert video.closure == pb.OUTPUT_CLOSURE_NOT_STARTED
    assert dict(video.counts) == {"frames": 0, "input_frames": 0, "duplicate_frames": 0}
    assert dict(frames.counts) == ({"render_groups": 7} if evidence_closed else {})


@pytest.mark.parametrize("interrupted", [False, True])
def test_sequential_session_persists_exact_group_timestamp_mapping(
    tmp_path: Path, interrupted: bool
) -> None:
    import json
    import time

    from cephvr.visual_stimulus.config.models.evidence_model import (
        Completion,
        EvidenceRecord,
    )

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_bytes(b"recipe")
    reference = ArtifactRef(
        relative_path="recipe.json",
        sha256=hashlib.sha256(b"recipe").hexdigest(),
        byte_length=6,
        schema_id="prepared-v2",
    )
    evidence = EvidenceWriter(max_pending_bytes=1_000_000)
    encoder = _Input()
    worker = RecordingWorker(
        capture_slots=2, evidence=evidence, encoder=encoder, video_start_ns=10
    )

    def finalize(counts: RecordingCounts) -> tuple[bytes, ...]:
        assert counts.eligible_group_count == 3
        assert counts.admitted_count == counts.input_submitted_count == 2
        assert counts.capacity_drop_count == 1
        assert counts.same_slot_omission_count == counts.duplicate_frame_count == 0
        return (
            EvidenceWriter._encode(
                EvidenceRecord(
                    payload=Completion(
                        kind="completion",
                        cutoff_host_ns=100,
                        last_group_id=2,
                        state_count=3,
                        submission_attempt_count=3,
                        capture_admission_count=2,
                        capture_drop_count=1,
                        same_slot_omission_count=0,
                        unresolved_attempt_count=0,
                        outcome="interrupted" if interrupted else "completed",
                    )
                )
            ),
        )

    session = RecordingSession(
        worker=worker,
        evidence=evidence,
        evidence_path=tmp_path / "frames.jsonl",
        recipe_path=recipe_path,
        max_queued_evidence_bytes=1_000_000,
        finalizer=finalize,
    )
    ready = set()

    class Renderer:
        def capture_review_composite(self, reservation, _outputs, _encoding):
            return reservation.group_id

        def poll_review_capture(self, pending):
            return (
                bytearray(b"aaaa" if pending == 0 else b"bbbb")
                if pending in ready
                else None
            )

    runtime = RecordingCaptureRuntime(
        Renderer(),
        session,
        NS(
            composite_width=1,
            composite_height=1,
            native_pixel_format="rgba8_bottom_up",
            encoder_pixel_format="yuv420p",
        ),
        evidence_pending_bytes=1_000_000,
        capture_slots=2,
    )
    worker.on_submitted = lambda frame: runtime.enqueue_capture_update(
        frame.group_id, "input_submitted", frame.video_frame_index, None, terminal=True
    )
    try:
        for group, timestamp in enumerate((12, 12, 30)):
            runtime.rendered(
                NS(
                    group=NS(group_id=group, outputs=(object(),)),
                    outputs=(object(),),
                    evidence_state=EvidenceStateSnapshot(
                        0, "scene", timestamp, (), (), (), ()
                    ),
                    evidence_submissions=(
                        SubmissionSnapshot(
                            "front",
                            group,
                            "returned",
                            timestamp + 1,
                            timestamp + 2,
                            1,
                            group,
                            True,
                            None,
                        ),
                    ),
                )
            )
        ready.add(1)
        runtime.poll_pending()  # later readback becomes ready first
        assert not worker.drain_once()
        ready.add(0)
        runtime.poll_pending()
        session.publish_header(
            Header(
                kind="header",
                format_version=6,
                identity=_identity(),
                writer_generation="writer",
                recipe=reference,
                trial_start_host_ns=10,
                required_output_ids=("front",),
                renderer_compatibility="renderer-v1",
            ),
            reference,
        )
        if interrupted:
            session.begin_cancel(
                cutoff_ns=100, deadline_ns=time.perf_counter_ns() + 2_000_000_000
            )
        else:
            session.begin_finish(
                cutoff_ns=100, deadline_ns=time.perf_counter_ns() + 2_000_000_000
            )
        result = session.finish(deadline_ns=time.perf_counter_ns() + 2_000_000_000)
        assert result.evidence_closed
    finally:
        if session._thread.is_alive():
            session.begin_cancel(deadline_ns=time.perf_counter_ns() + 2_000_000_000)
            session._thread.join(2)
    rows = [
        json.loads(line)["payload"]
        for line in (tmp_path / "frames.jsonl").read_text().splitlines()
    ]
    groups = {row["group_id"]: row for row in rows if row["kind"] == "render_group"}
    mappings = [
        (row["group_id"], capture["video_frame_index"])
        for row in rows
        for capture in row.get("captures", ())
        if capture["disposition"] == "input_submitted"
    ]
    assert mappings == [(0, 0), (1, 1)]
    assert [
        (
            groups[group]["state"]["evaluation_host_ns"],
            groups[group]["submissions"][0]["return_host_ns"],
        )
        for group, _ in mappings
    ] == [(12, 14), (12, 14)]
    assert all(
        capture["video_frame_index"] is None
        for row in rows
        for capture in row.get("captures", ())
        if capture["disposition"] != "input_submitted"
    )
    assert groups[2]["captures"][0]["disposition"] == "capacity_drop"
    assert rows[-1]["outcome"] == ("interrupted" if interrupted else "completed")
    assert rows[-1]["cutoff_host_ns"] == 100
    assert encoder.data == b"aaaabbbb" and encoder.closed


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_submitted_count", 0),
        ("encoded_frame_count", 0),
        ("selected_real_count", 0),
        ("duplicate_frame_count", 1),
        ("same_slot_omission_count", 1),
        ("failed_capture_count", 1),
    ],
)
def test_sequential_inconsistent_accounting_cannot_claim_closed(
    field: str, value: int
) -> None:
    from dataclasses import replace

    counts = replace(
        RecordingCounts(
            1, 1, 1, 0, 0, 0, 0, encoded_frame_count=1, selected_real_count=1
        ),
        **{field: value},
    )
    outcome = resolve_video_completion(
        counts,
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
    assert outcome.closure == "UNCONFIRMED"


@pytest.mark.parametrize("height", [1, 3, 4])
def test_top_down_rgba_input_keeps_owned_buffer_without_cpu_row_copy(height):
    from cephvr.visual_stimulus.recording.capture import _ffmpeg_input_order

    pixels = bytearray(range(height * 8))
    frame = CompositeFrame(0, 0, 2, height, "rgba8_top_down", pixels)
    assert _ffmpeg_input_order(frame) is frame
    assert frame.pixels is pixels
    assert pixels == bytearray(range(height * 8))


@pytest.mark.parametrize("cancel", [False, True])
def test_dummy_native_recording_creates_no_writer_or_output(
    native_recording, tmp_path, cancel
):
    from cephvr.visual_stimulus.v1 import messages_pb2 as visual

    from .support import make_prepared_trial

    recording = native_recording
    setup = visual.WorkerSetup()
    setup.settings.save_visual_stimulus_data = False
    backend = setup.session.configuration.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    backend.visual_stimulus.save_visual_stimulus_data = False
    announced = []
    recording.configure(setup, lambda key, path: announced.append(key), 100)
    artifact = make_prepared_trial()
    assert recording.prepare_artifacts((artifact,), 100) is None
    assert recording.schedule(visual.WorkerSchedule(), artifact) is None
    assert recording._session is None and recording._worker is None
    assert not recording._recipes and not announced
    assert recording.poll_finished() is None
    if cancel:
        recording.begin_cancel(200)
    else:
        recording.begin_finish(100, 200)
    assert recording.poll_finished() == ()
    assert not recording.cleanup(200).outstanding
    assert not list(tmp_path.iterdir())
