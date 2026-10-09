from threading import Condition
from types import SimpleNamespace
from cephvr.visual_stimulus.recording.capture import RecordingWorker
from cephvr.visual_stimulus.recording.evidence import EvidenceWriter
from cephvr.visual_stimulus.recording.session import RecordingSession
from cephvr.visual_stimulus.recording.native import NativeRecording


def owner(now):
    worker = RecordingWorker(capture_slots=1, evidence=EvidenceWriter(max_pending_bytes=100), encoder=SimpleNamespace(), video_start_ns=1_000_000_000, video_rate_hz=1)
    session = object.__new__(RecordingSession)
    session.worker, session._condition, session._closing = worker, Condition(), False
    native = object.__new__(NativeRecording)
    native.saving, native._session, native._capture_runtime = True, session, None
    native.clock_ns = lambda: now[0]
    native._cutoff_ns = native._finish_deadline_ns = None
    return native, session, worker

now = [500_000_000]
native, session, worker = owner(now)
try:
    native.begin_cancel(5_000_000_000)
except Exception as exc:
    print('pre_T_cancel:', type(exc).__name__, str(exc), 'closing=', session._closing)
now = [2_000_000_000]
native, session, worker = owner(now)
native.begin_cancel(5_000_000_000)
now[0] = 3_000_000_000
try:
    native.begin_cancel(6_000_000_000)
except Exception as exc:
    print('retry_cancel:', type(exc).__name__, str(exc), 'retained_cutoff=', native._cutoff_ns, 'deadline=', native._finish_deadline_ns, 'slots=', worker._cutoff_slots)
from cephvr.visual_stimulus.recording.completion import resolve_video_completion
now = [2_000_000_000]
native, session, worker = owner(now)
worker.encoder = SimpleNamespace(write_chunk=lambda data: len(data), close_input=lambda: None)
reservation, _, _ = worker.classify_and_reserve(0, 1_000_000_000)
worker.complete_capture(reservation, width=1, height=1, pixel_format='rgba8_bottom_up', pixels=b'abcd')
worker.classify_and_reserve(1, 1_500_000_000)
worker.set_cutoff(2_000_000_000)
while worker.drain_once():
    pass
counts = worker.finish_input()
result = resolve_video_completion(counts, final_cutoff_known=True, every_eligible_group_resolved=True, no_partial_input_write=True, encoder_cleanup_confirmed=True, encoder_finalized=True, file_sync_and_close_confirmed=True, artifact_present=True, artifact_created_by_session=True, reserved_path_absent_after_cleanup=False)
print('same_slot_completion:', counts, result)
