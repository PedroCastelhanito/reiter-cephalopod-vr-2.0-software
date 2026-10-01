"""Worker-owned PyAV contexts used by bounded live video playback."""

from __future__ import annotations

from typing import Protocol

from .assets import ProtectedSource
from .ffv1_configuration import FFV1ConfigurationError, require_ffv1_version3
from .media import ImagePixels
from .video_index import SourceFrame, VideoIndex


class VideoPlaybackError(RuntimeError):
    """Video worker, profile, or playback contract failure."""


class DecoderContext(Protocol):
    def decode(self, frame: SourceFrame) -> ImagePixels: ...

    def close(self) -> None: ...


class DecoderFactory(Protocol):
    def __call__(
        self,
        source: ProtectedSource,
        index: VideoIndex,
        asset_profile: str,
        codec_threads: int,
    ) -> DecoderContext: ...


def make_pyav_context(
    source: ProtectedSource,
    index: VideoIndex,
    asset_profile: str,
    codec_threads: int,
) -> DecoderContext:
    return _PyAVContext(source, index, asset_profile, codec_threads)


class _PyAVContext:
    """A protected, seekable PyAV context; every method is worker-thread only."""

    def __init__(
        self,
        source: ProtectedSource,
        index: VideoIndex,
        asset_profile: str,
        codec_threads: int,
    ) -> None:
        try:
            import av  # type: ignore[import-not-found]
        except ImportError as exc:
            raise VideoPlaybackError("PyAV is required for video playback") from exc
        self._reader_context = source.independent_reader()
        self._reader = self._reader_context.__enter__()
        try:
            self._container = av.open(self._reader, mode="r")
            format_names = set(
                (getattr(self._container.format, "name", "") or "").split(",")
            )
            required_format = (
                "mp4" if asset_profile == "mp4_h264_sdr8_v1" else "matroska"
            )
            if required_format not in format_names:
                raise VideoPlaybackError(
                    "protected video container differs from prepared profile"
                )
            streams = [
                stream for stream in self._container.streams if stream.type == "video"
            ]
            if len(streams) != 1 or streams[0].index != index.stream_index:
                raise VideoPlaybackError(
                    "video stream identity changed after preparation"
                )
            self._stream = streams[0]
            codec = "h264" if asset_profile == "mp4_h264_sdr8_v1" else "ffv1"
            if self._stream.codec_context.name != codec:
                raise VideoPlaybackError("video codec changed after preparation")
            if (self._stream.width, self._stream.height) != (
                index.width,
                index.height,
            ):
                raise VideoPlaybackError("video dimensions differ from prepared index")
            if asset_profile == "matroska_ffv1_v3_uint_v1":
                try:
                    require_ffv1_version3(self._stream.codec_context.extradata or b"")
                except FFV1ConfigurationError as exc:
                    raise VideoPlaybackError(
                        f"invalid FFV1 Configuration Record: {exc}"
                    ) from exc
            self._stream.codec_context.thread_count = codec_threads
            self._stream.codec_context.thread_type = "SLICE"
            self._bits = max(index.component_bits)
            self._index = index
        except BaseException:
            self._reader_context.__exit__(None, None, None)
            raise

    def decode(self, frame: SourceFrame) -> ImagePixels:
        from fractions import Fraction

        import numpy as np

        self._container.seek(frame.seek_anchor, stream=self._stream, backward=True)
        wanted_pts = Fraction(frame.pts) * frame.time_base
        for decoded in self._container.decode(self._stream):
            if decoded.pts is None or decoded.time_base is None:
                continue
            source_time = Fraction(decoded.pts) * Fraction(decoded.time_base)
            if source_time < wanted_pts:
                continue
            if source_time > wanted_pts:
                break
            if decoded.format.name != self._index.pixel_format:
                raise VideoPlaybackError(
                    "decoded video format differs from prepared profile"
                )
            if decoded.pts != frame.pts and source_time == wanted_pts:
                continue
            pixel_format = "rgba64le" if self._bits > 8 else "rgba"
            pixels = decoded.to_ndarray(format=pixel_format)
            expected = np.uint16 if self._bits > 8 else np.uint8
            if (
                pixels.shape != (self._stream.height, self._stream.width, 4)
                or pixels.dtype != expected
            ):
                raise VideoPlaybackError(
                    "decoded video frame layout differs from prepared profile"
                )
            pixels.setflags(write=False)
            return ImagePixels(
                self._stream.width,
                self._stream.height,
                str(pixels.dtype),
                4,
                ("red", "green", "blue", "alpha"),
                pixels,
                self._index.initial_pixels.transfer,
                self._index.initial_pixels.alpha,
            )
        raise VideoPlaybackError(
            f"indexed source frame {frame.index} could not be decoded"
        )

    def close(self) -> None:
        try:
            self._container.close()
        finally:
            self._reader_context.__exit__(None, None, None)
