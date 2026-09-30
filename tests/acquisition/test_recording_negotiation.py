"""Prepared live FFmpeg input/output negotiation parser coverage."""

from __future__ import annotations

import threading
from collections import deque
from typing import cast

from cephvr.acquisition.recording.encoder_process import WindowsEncoderProcess
from cephvr.acquisition.recording.negotiation import (
    NegotiatedVideo,
    VideoNegotiation,
    VideoNegotiationExpectation,
)
from cephvr.platform.windows.byte_stream import OverlappedPipe


def _negotiation() -> VideoNegotiation:
    return VideoNegotiation(
        VideoNegotiationExpectation(
            input=NegotiatedVideo("rawvideo", "rgb48le", 1920, 1080),
            output=NegotiatedVideo("h264", "yuv444p", 1280, 720),
        )
    )


def test_accepts_exact_live_input_and_filtered_output_streams() -> None:
    negotiation = _negotiation()
    negotiation.feed("Input #0, rawvideo, from 'pipe:'")
    negotiation.feed(
        "  Stream #0:0: Video: rawvideo (RGB[48] / 0x...), "
        "rgb48le(pc, gbr/unknown/unknown, progressive), 1920x1080, 30 tbr"
    )
    negotiation.feed("Output #0, mp4, to 'recording.mp4':")
    negotiation.feed(
        "  Stream #0:0: Video: h264 (High 4:4:4) (avc1 / 0x...), "
        "yuv444p(tv, bt709/unknown/unknown, progressive), 1280x720, q=2-31"
    )
    assert negotiation.error is None
    assert negotiation.complete


def test_rejects_live_encoder_substitution() -> None:
    negotiation = _negotiation()
    negotiation.feed("Output #0, mp4, to 'recording.mp4':")
    negotiation.feed(
        "  Stream #0:0: Video: hevc (Main) (hev1 / 0x...), "
        "yuv444p(tv, bt709/unknown/unknown, progressive), 1280x720, q=2-31"
    )
    assert negotiation.error is not None
    assert "negotiated hevc" in negotiation.error


def test_incomplete_dimensions_do_not_count_as_negotiation() -> None:
    negotiation = _negotiation()
    negotiation.feed("Output #0, mp4, to 'recording.mp4':")
    negotiation.feed("  Stream #0:0: Video: h264 (High), yuv444p(tv, bt709)")
    assert not negotiation.complete
    assert negotiation.error is not None


def test_stream_analysis_may_finish_after_a_later_input_packet() -> None:
    """Output negotiation can lag the first frame without a blocking gate."""
    negotiation = _negotiation()
    negotiation.feed("Input #0, rawvideo, from 'pipe:'")
    negotiation.feed("  Stream #0:0: Video: rawvideo, rgb48le(pc), 1920x1080, 30 tbr")
    assert negotiation.complete is False
    assert negotiation.error is None

    # FFmpeg may need a second packet before it finishes stream analysis and
    # reports the filtered output. The recording pump must remain able to submit it.
    negotiation.feed("Output #0, mp4, to 'recording.mp4':")
    negotiation.feed(
        "  Stream #0:0: Video: h264 (High 4:4:4 Predictive) "
        "(avc1 / 0x31637661), yuv444p(tv, bt709, progressive), "
        "1280x720 [SAR 1:1 DAR 16:9], 30 fps, q=2-31"
    )
    assert negotiation.complete
    assert negotiation.error is None


class _DeferredPipe:
    def __init__(self) -> None:
        self.chunks: deque[bytes | None | TimeoutError] = deque(
            [
                TimeoutError(),
                b"Output #0, mp4, to 'recording.mp4':\n",
                b"  Stream #0:0: Video: h264 (High 4:4:4 Predictive) "
                b"(avc1 / 0x31637661), yuv444p(tv, bt709), 1280x720",
                None,
            ]
        )

    def read(self, *, deadline_ns: int) -> bytes | None:
        _ = deadline_ns
        value = self.chunks.popleft()
        if isinstance(value, TimeoutError):
            raise value
        return value


def test_reader_drains_terminal_stream_data_after_idle_timeout() -> None:
    """A late final stream line is parsed before EOF/cleanup is accepted."""
    process = object.__new__(WindowsEncoderProcess)
    process.stderr_pipe = cast(OverlappedPipe, _DeferredPipe())
    process._reader_drain_deadline_ns = 100
    process.clock_ns = lambda: 50
    process._stderr_partial = bytearray()
    process._stderr = deque()
    process._stderr_bytes = 0
    process.tail_max_lines = 16
    process.tail_max_bytes = 16 * 1024
    process._reader_error = None
    process._lock = threading.Lock()
    process.progress_pipe = cast(
        OverlappedPipe,
        _DeferredPipeWithProgress(),
    )
    process._progress_frame = None
    process.capture_stdout = False
    process._negotiation = VideoNegotiation(
        VideoNegotiationExpectation(
            input=NegotiatedVideo("rawvideo", "rgb48le", 1920, 1080),
            output=NegotiatedVideo("h264", "yuv444p", 1280, 720),
        )
    )
    process._negotiation.feed("Input #0, rawvideo, from 'pipe:'")
    process._negotiation.feed(
        "Stream #0:0: Video: rawvideo, rgb48le(pc), 1920x1080, 30 tbr"
    )

    process._read_stderr()

    assert process._negotiation.complete
    assert process._reader_error is None
    process._read_progress()
    assert process.progress_frame == 17


class _DeferredPipeWithProgress(_DeferredPipe):
    def __init__(self) -> None:
        self.chunks = deque([TimeoutError(), b"frame=17\n", None])
