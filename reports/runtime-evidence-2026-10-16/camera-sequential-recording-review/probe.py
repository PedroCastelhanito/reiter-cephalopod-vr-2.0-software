"""Local review probes; fake encoder/storage, real queue/pump/JSONL/finalizers."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import runpy

from cephvr.acquisition.buffers.end_marker import CaptureEndMarker
from cephvr.acquisition.buffers.records import FrameRecord
from cephvr.acquisition.buffers.queue import RecordingQueue
from cephvr.acquisition.buffers.pixel_pool import PixelBufferPool
from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.session_pump import write_ordered_entry
from cephvr.acquisition.recording.session_completion import finish_recording
from cephvr.acquisition.recording.session_cleanup import close_failed_recording
from cephvr.acquisition.recording.session_contracts import PulseEvidence, RecordingCompletionContext, RecordingFailure
from cephvr.acquisition.recording.session_diagnostics import RecordingDiagnostics
from cephvr.acquisition.recording.session_finalizer import FinalizationProgress
from cephvr.control.v1 import types_pb2 as control

fixtures = runpy.run_path('tests/acquisition/test_recording_cleanup.py')
paths = runpy.run_path('tests/acquisition/test_recording_paths.py')

class Preparer:
    layout = SimpleNamespace(pixel_format=SimpleNamespace(effective_bits=8))

    def prepare_recording_into(self, pixels, buffer, *, target_bits):
        buffer[:] = pixels
        return SimpleNamespace(data=memoryview(buffer), effective_bits=8, source_effective_bits=8)


with TemporaryDirectory() as directory:
    root = Path(directory)
    schedule = fixtures['_schedule'](root / 'trial.mp4', root / 'trial.jsonl')
    schedule.start_monotonic_ns = 1_000_000_000
    schedule.end_monotonic_ns = 3_000_000_000
    log = FrameLogWriter(root / 'trial.jsonl', paths['_identity'](), start_ns=1_000_000_000,
                         nominal_frame_rate_hz=30, nominal_rate_source='free_running_frame_rate',
                         sync_interval_ns=1, syncer=SimpleNamespace(sync=lambda _: None))
    log.create()
    queue = RecordingQueue(2, 4)
    records = [FrameRecord(i, timestamp, None, None, valid, None if valid else 'INVALID_IMAGE')
               for i, timestamp, valid in [(0, 1_000_000_001, True), (1, 1_000_000_001, False),
                                           (2, 1_000_000_001, True), (3, 1_600_000_000, True)]]
    for record in records:
        queue.enqueue(record, memoryview(bytes([record.frame_id] * 4)) if record.valid_image else None)
    encoder = fixtures['_Encoder'](identity='original')
    submitted = []
    for i in range(4):
        entry = queue.dequeue(0)
        write_ordered_entry(entry, expected_frame_id=i, schedule=schedule, frame_log=log,
                            encoder=encoder, pixel_preparer=Preparer(), prepared_buffer=bytearray(4),
                            target_bits=8, on_started=lambda: None, write_deadline=lambda: 4_000_000_000,
                            record_diagnostic=lambda _: None, on_video_frame_submitted=lambda: submitted.append(1))
        queue.complete(entry.record)
    video = fixtures['_Video']()
    outputs, _ = finish_recording(CaptureEndMarker(4, 1_800_000_000, 1_800_000_000, 0, None, True),
        PulseEvidence(), RecordingCompletionContext('interrupted', 1_800_000_000, 1_800_000_000, None),
        schedule=schedule, received=4, submitted=len(submitted), logged=4, last_frame_id=3,
        diagnostics=RecordingDiagnostics(lambda *_: None), encoder=encoder, frame_log=log,
        video_sync=video, finalization=FinalizationProgress(), video_path=root / 'trial.mp4',
        frame_log_path=root / 'trial.jsonl', video_identity='original', observe_video=lambda: video,
        stat_identity=lambda _: 'original', clock_ns=lambda: 1_900_000_000,
        original_deadline_ns=4_000_000_000, cleanup_deadline_ns=4_000_000_000)
    rows = [json.loads(line) for line in (root / 'trial.jsonl').read_text().splitlines()]
    sources = [row for row in rows if row['type'] == 'frame']
    mapped = [row for row in rows if row['type'] == 'video_frame']
    assert [row['video_disposition'] for row in sources] == ['capacity_drop', 'invalid_image', 'real', 'real']
    assert [row['video_frame'] for row in sources] == [None, None, 0, 1]
    assert [row['source_frame_id'] for row in mapped] == [2, 3]
    assert [row['source_host_receipt_ns'] for row in mapped] == [1_000_000_001, 1_600_000_000]
    assert rows[-1]['outcome'] == 'interrupted' and rows[-1]['timing']['accounting_complete']
    assert rows[-1]['video']['duplicate_frame_count'] == 0
    assert encoder.writes == 2 and outputs[0].closure == control.OUTPUT_CLOSURE_CLOSED
    print('PASS: queue overflow + invalid image + equal receipts + long gap + interrupted close; four sources -> two mapped images, no padding')

    class FailingMapping:
        frame_count = 0

        def append_frame(self, *args, **kwargs):
            pass

        def append_video_frame(self, **kwargs):
            raise OSError('injected mapping append failure')

        def close_failed(self):
            pass

    encoder = fixtures['_Encoder'](identity='original')
    submitted = []
    log = FailingMapping()
    try:
        write_ordered_entry(SimpleNamespace(record=records[0], pixels=memoryview(b'data'), dropped=False),
            expected_frame_id=0, schedule=schedule, frame_log=log, encoder=encoder,
            pixel_preparer=Preparer(), prepared_buffer=bytearray(4), target_bits=8,
            on_started=lambda: None, write_deadline=lambda: 4_000_000_000,
            record_diagnostic=lambda _: None, on_video_frame_submitted=lambda: submitted.append(1))
    except RecordingFailure:
        pass
    else:
        raise AssertionError('mapping append must fail')
    video = fixtures['_Video']()
    outputs, _ = close_failed_recording(schedule, root / 'trial.mp4', root / 'trial.jsonl',
        queue=RecordingQueue(1, 1), pool=PixelBufferPool(payload_bytes=4, capacity=1),
        encoder=encoder, frame_log=log, video_sync=video, finalization=FinalizationProgress(),
        submitted=len(submitted), observe_video=lambda: video, stat_identity=lambda _: 'original',
        clock_ns=lambda: 1_900_000_000, deadline_ns=4_000_000_000)
    assert encoder.writes == 1 and len(submitted) == 0
    print(outputs[0])
    assert outputs[0].camera_video_content == control.CAMERA_VIDEO_CONTENT_NO_FRAMES
    print('REPRODUCED: first image fully accepted, mapping append fails, cleanup incorrectly reports NO_FRAMES; pre-existing callback ordering')
