"""Strict video-profile indexing and source timestamp normalization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from cephvr.visual_stimulus.config.models.program_model import Asset

from .assets import ProtectedSource
from .ffv1_configuration import FFV1ConfigurationError, require_ffv1_version3
from .media import (
    Alpha,
    ImagePixels,
    MediaPreparationError,
    Transfer,
)


@dataclass(frozen=True, slots=True)
class SourceFrame:
    index: int
    pts: int
    time_base: Fraction
    start: Fraction
    end: Fraction
    seek_anchor: int


@dataclass(frozen=True, slots=True)
class VideoIndex:
    stream_index: int
    codec_name: str
    width: int
    height: int
    frames: tuple[SourceFrame, ...]
    duration: Fraction
    pixel_format: str
    component_bits: tuple[int, ...]
    channel_order: tuple[str, ...]
    source_alpha: Alpha
    transfer: Transfer
    color_range: Literal["full", "limited"]
    matrix: Literal["rgb", "bt601", "bt709"]
    chroma_location: Literal["none", "left", "center", "topleft"]
    initial_pixels: ImagePixels


def _relative_pts(pts: int, time_base: Fraction, origin: Fraction) -> Fraction:
    """Map a source PTS onto the first decoded presentation time as t=0."""
    return Fraction(pts) * time_base - origin


def index_video(
    asset: Asset,
    source: ProtectedSource,
    *,
    max_index_bytes: int,
    codec_threads: int = 1,
    check: Callable[[], None] | None = None,
    reserve: Callable[[int, int, int, int], None] | None = None,
) -> VideoIndex:
    """Decode one supported stream sequentially to resolve presentation intervals."""
    if asset.profile not in ("mp4_h264_sdr8_v1", "matroska_ffv1_v3_uint_v1"):
        raise MediaPreparationError("asset profile is not a supported video profile")
    if max_index_bytes <= 0 or codec_threads <= 0:
        raise ValueError("positive video index budget required")
    try:
        import av  # type: ignore[import-not-found]
    except ImportError as exc:
        raise MediaPreparationError("PyAV is required for video assets") from exc
    with source.independent_reader() as reader:
        try:
            container = av.open(reader, mode="r")
        except Exception as exc:
            raise MediaPreparationError(
                f"PyAV could not open protected video: {exc}"
            ) from exc
        try:
            format_names = set((getattr(container.format, "name", "") or "").split(","))
            if asset.profile == "mp4_h264_sdr8_v1" and "mp4" not in format_names:
                raise MediaPreparationError("H.264 profile requires an MP4 container")
            if (
                asset.profile == "matroska_ffv1_v3_uint_v1"
                and "matroska" not in format_names
            ):
                raise MediaPreparationError(
                    "FFV1 profile requires a Matroska container"
                )
            streams = [stream for stream in container.streams if stream.type == "video"]
            if len(streams) != 1:
                raise MediaPreparationError(
                    "video profile requires exactly one video stream"
                )
            stream = streams[0]
            stream.codec_context.thread_count = codec_threads
            stream.codec_context.thread_type = "SLICE"
            codec = stream.codec_context.name
            expected = "h264" if asset.profile == "mp4_h264_sdr8_v1" else "ffv1"
            if codec != expected:
                raise MediaPreparationError(f"expected {expected}, received {codec}")
            declared_format = getattr(stream.codec_context.format, "name", "")
            bits: tuple[int, ...]
            order: tuple[str, ...]
            alpha: Alpha
            range_name: Literal["full", "limited"]
            if asset.profile == "mp4_h264_sdr8_v1":
                profile_name = (stream.codec_context.profile or "").lower()
                if profile_name and profile_name not in (
                    "baseline",
                    "constrained baseline",
                    "main",
                    "high",
                    "high 10",
                ):
                    raise MediaPreparationError(
                        f"unsupported H.264 profile {profile_name!r}"
                    )
                if declared_format not in ("yuv420p", "yuvj420p"):
                    raise MediaPreparationError(
                        f"unsupported H.264 pixel format {declared_format!r}"
                    )
                if declared_format == "yuvj420p":
                    range_name = "full"
                else:
                    range_name = "limited"
                bits = (8, 8, 8)
                order = ("y", "cb", "cr")
                alpha = "none"
            elif declared_format in ("gray", "gray16le", "gray16be"):
                bits = (8,) if declared_format == "gray" else (16,)
                order, alpha, range_name = ("gray",), "none", "full"
            elif declared_format in (
                "rgb24",
                "bgr24",
                "gbrp",
                "gbrp16le",
                "gbrp16be",
                "rgba",
                "bgra",
                "gbrap16le",
                "gbrap16be",
                "bgr0",
            ):
                channels = (
                    4
                    if declared_format.startswith("gbrap")
                    or declared_format in ("rgba", "bgra")
                    else 3
                )
                bits = tuple(
                    (16 if "16" in declared_format else 8) for _ in range(channels)
                )
                order = ("red", "green", "blue", "alpha")[: len(bits)]
                alpha = (
                    "straight"
                    if len(bits) == 4 and "0" not in declared_format
                    else "none"
                )
                range_name = "full"
            else:
                raise MediaPreparationError(
                    f"unsupported FFV1 pixel format {declared_format!r}"
                )
            if asset.profile == "matroska_ffv1_v3_uint_v1":
                extradata = stream.codec_context.extradata
                try:
                    require_ffv1_version3(extradata or b"")
                except FFV1ConfigurationError as exc:
                    raise MediaPreparationError(
                        f"invalid FFV1 Configuration Record: {exc}"
                    ) from exc
            matrix_name: Literal["rgb", "bt601", "bt709"] = (
                "bt709"
                if getattr(stream.codec_context, "colorspace", None) in (1, "ITU709")
                else "rgb"
            )
            transfer: Transfer
            if asset.color_override is not None:
                transfer = asset.color_override.transfer
            elif asset.profile == "mp4_h264_sdr8_v1":
                transfer = "bt709"
            else:
                raise MediaPreparationError(
                    "FFV1 requires an explicit source transfer interpretation"
                )
            if asset.profile == "mp4_h264_sdr8_v1" and matrix_name == "rgb":
                raise MediaPreparationError(
                    "H.264 stream matrix is absent or outside the supported Rec.709 family"
                )
            if asset.profile == "mp4_h264_sdr8_v1" and getattr(
                stream.codec_context, "color_trc", None
            ) not in (1, "ITU709"):
                raise MediaPreparationError(
                    "H.264 stream transfer is absent or outside supported Rec.709"
                )
            if asset.profile == "mp4_h264_sdr8_v1" and getattr(
                stream.codec_context, "field_order", None
            ) not in (0, "progressive"):
                raise MediaPreparationError("interlaced H.264 video is unsupported")
            frames: list[SourceFrame] = []
            if reserve is not None:
                reserve(stream.width, stream.height, 4, max(bits))
            previous: Fraction | None = None
            source_origin: Fraction | None = None
            pending: tuple[int, Fraction, int, Fraction, int] | None = None
            seek_anchor: int | None = None
            decoded_format = None
            dimensions = (stream.width, stream.height)
            initial_pixels = None
            for decoded in container.decode(stream):
                if check is not None:
                    check()
                if getattr(decoded, "is_corrupt", False):
                    raise MediaPreparationError(
                        "decoder reported corrupt video content"
                    )
                if (decoded.width, decoded.height) != dimensions:
                    raise MediaPreparationError(
                        "video resolution changes during the stream"
                    )
                frame_format = decoded.format.name
                if decoded_format is None:
                    decoded_format = frame_format
                elif decoded_format != frame_format:
                    raise MediaPreparationError(
                        "video pixel representation changes during the stream"
                    )
                if decoded.pts is None or decoded.time_base is None:
                    raise MediaPreparationError(
                        "video frame has no source presentation timestamp"
                    )
                if initial_pixels is None:
                    import numpy as np

                    rgba_format = (
                        "rgba64le" if any(bit == 16 for bit in bits) else "rgba"
                    )
                    pixels = decoded.to_ndarray(format=rgba_format)
                    expected_dtype = (
                        np.uint16 if rgba_format == "rgba64le" else np.uint8
                    )
                    if (
                        pixels.shape != (stream.height, stream.width, 4)
                        or pixels.dtype != expected_dtype
                    ):
                        raise MediaPreparationError(
                            "initial video frame conversion produced an unexpected layout"
                        )
                    initial_pixels = ImagePixels(
                        stream.width,
                        stream.height,
                        str(pixels.dtype),
                        4,
                        ("red", "green", "blue", "alpha"),
                        pixels,
                        transfer,
                        alpha,
                    )
                    try:
                        pixels.setflags(write=False)
                    except AttributeError:
                        pass
                pts = int(decoded.pts)
                base = Fraction(
                    decoded.time_base.numerator, decoded.time_base.denominator
                )
                if decoded.key_frame:
                    seek_anchor = pts
                if seek_anchor is None:
                    raise MediaPreparationError(
                        "video begins without a decodable keyframe anchor"
                    )
                absolute_start = pts * base
                if source_origin is None:
                    source_origin = absolute_start
                start = _relative_pts(pts, base, source_origin)
                if previous is not None and start <= previous:
                    raise MediaPreparationError(
                        "video presentation timestamps are not strictly ordered"
                    )
                if pending is not None:
                    pindex, pstart, ppts, pbase, anchor = pending
                    frames.append(
                        SourceFrame(pindex, ppts, pbase, pstart, start, anchor)
                    )
                pending = (len(frames), start, pts, base, seek_anchor)
                previous = start
                if (len(frames) + 1) * 256 > max_index_bytes:
                    raise MemoryError(
                        "video source-frame index exceeds configured budget"
                    )
            if pending is None or initial_pixels is None:
                raise MediaPreparationError("video stream contains no decodable frames")
            final_index, final_start, final_pts, final_base, final_anchor = pending
            duration = None
            if stream.duration is not None and stream.time_base is not None:
                source_start = stream.start_time
                if source_origin is None:
                    raise MediaPreparationError("video source origin is unresolved")
                stream_base = Fraction(
                    stream.time_base.numerator, stream.time_base.denominator
                )
                absolute_end = (
                    Fraction(source_start + stream.duration) * stream_base
                    if source_start is not None
                    else source_origin + Fraction(stream.duration) * stream_base
                )
                candidate = absolute_end - source_origin
                final_absolute = Fraction(final_pts) * final_base - source_origin
                if candidate > final_absolute:
                    duration = candidate
            if duration is None:
                # Container duration can include unrelated tracks; it is not endpoint proof.
                raise MediaPreparationError(
                    "video final presentation endpoint is unresolved"
                )
            frames.append(
                SourceFrame(
                    final_index,
                    final_pts,
                    final_base,
                    final_start,
                    duration,
                    final_anchor,
                )
            )
            if any(frame.end <= frame.start for frame in frames):
                raise MediaPreparationError(
                    "video contains an unresolved frame interval"
                )
            return VideoIndex(
                stream.index,
                codec,
                stream.width,
                stream.height,
                tuple(frames),
                duration,
                decoded_format or declared_format,
                bits,
                order,
                alpha,
                transfer,
                range_name,
                matrix_name,
                "left" if asset.profile == "mp4_h264_sdr8_v1" else "none",
                initial_pixels,
            )
        finally:
            container.close()
