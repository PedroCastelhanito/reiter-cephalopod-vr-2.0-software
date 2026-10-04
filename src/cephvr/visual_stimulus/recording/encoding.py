"""E13 composite geometry and Visual Stimulus-specific policy over shared FFmpeg validation."""

from __future__ import annotations

from collections.abc import Sequence
from math import isqrt
from pathlib import Path

from cephvr.shared.ffmpeg_arguments import parse_option_tokens
from cephvr.shared.ffmpeg_pixel_formats import pixel_format_depth
from cephvr.shared.ffmpeg_types import (
    EncoderCapabilities,
    EncodingOptionsError,
    ResolvedEncoding,
)
from cephvr.shared.ffmpeg_validation import validate_arguments
from cephvr.visual_stimulus.config.models.artifact_models import (
    CompositeTile,
    ReviewEncoding,
    ReviewTiming,
    tile_layout,
)
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    PixelRect,
)

VISUAL_STIMULUS_FRAGMENT_FLAGS = frozenset(
    {"frag_keyframe", "empty_moov", "default_base_moof"}
)


def prepare_review_encoding(
    display: DisplayProfile,
    *,
    ffmpeg_args: Sequence[str],
    capabilities: EncoderCapabilities,
    input_pixel_format: str,
    capability_evidence_id: str,
) -> tuple[ReviewEncoding, ResolvedEncoding]:
    """Validate one lossy encoder plan and derive the fixed E13 tile layout.

    The FFmpeg raw format is mechanically derived from the capture ABI and then
    validated against the installed build. Actual encoder input feasibility remains
    a rig check.
    """
    if not display.active_outputs or display.selected_pacing_output_id is None:
        raise EncodingOptionsError(
            "review encoding requires configured output and pacing identities"
        )
    expected_input = ffmpeg_input_format(display)
    if input_pixel_format != expected_input:
        raise EncodingOptionsError(
            f"capture ABI requires FFmpeg raw input format {expected_input!r}"
        )
    parsed = parse_option_tokens(
        ffmpeg_args, owner="Visual Stimulus", error=EncodingOptionsError
    )
    tune = parsed.get("-tune", [None])[0]
    rate_control = parsed.get("-rc", [None])[0]
    qp = parsed.get("-qp", [None])[0]
    if tune == "lossless" or (rate_control == "constqp" and qp == "0"):
        raise EncodingOptionsError(
            "Visual Stimulus review encoding must be explicitly lossy"
        )
    if not {"-cq", "-qp", "-b:v", "-maxrate:v"}.intersection(parsed):
        raise EncodingOptionsError(
            "Visual Stimulus review quality/rate-control mode must be explicit"
        )
    vf = parsed.get("-vf", [""])[0]
    if any(filter_name in vf for filter_name in ("crop", "pad", "hflip", "vflip")):
        raise EncodingOptionsError(
            "Visual Stimulus review filters cannot crop, pad, or flip tile contents"
        )
    if not VISUAL_STIMULUS_FRAGMENT_FLAGS.issubset(capabilities.muxer_flags):
        missing = ", ".join(
            sorted(VISUAL_STIMULUS_FRAGMENT_FLAGS - capabilities.muxer_flags)
        )
        raise EncodingOptionsError(
            f"installed MP4 muxer lacks Visual Stimulus fragmented-output flags: {missing}"
        )
    output_bits = pixel_format_depth(
        parsed["-pix_fmt"][0].removeprefix("+"), error=EncodingOptionsError
    )
    source_bits = max(item.rgb_bits_per_channel for item in display.active_outputs)
    if output_bits > source_bits:
        raise EncodingOptionsError(
            "review encoding cannot widen beyond the source device-code depth"
        )
    maximum = (
        capabilities.device_max_dimensions.get(
            (parsed["-c:v"][0], parsed["-pix_fmt"][0].removeprefix("+")),
        )
        if capabilities.device_max_dimensions
        else None
    )
    if maximum is None or min(maximum) <= 0:
        raise EncodingOptionsError("resolved encoder maximum dimensions are required")
    geometry = _composite_geometry(display, maximum)
    composite_width, composite_height, scale, tiles = geometry
    effective = validate_arguments(
        ffmpeg_args,
        capabilities=capabilities,
        input_pixel_format=input_pixel_format,
        recording_bit_depth=output_bits,
        input_width=composite_width,
        input_height=composite_height,
        owner="Visual Stimulus",
        required_muxer_flags=VISUAL_STIMULUS_FRAGMENT_FLAGS,
    )
    if (effective.output_width, effective.output_height) != (
        composite_width,
        composite_height,
    ):
        raise EncodingOptionsError(
            "Visual Stimulus review conversion must preserve prepared composite dimensions"
        )
    pacing = next(
        (
            item
            for item in display.active_outputs
            if item.output_id == display.selected_pacing_output_id
        ),
        None,
    )
    if pacing is None:
        raise EncodingOptionsError(
            "configured pacing output is missing from display profile"
        )
    review = ReviewEncoding(
        composite_width=composite_width,
        composite_height=composite_height,
        scale_denominator=scale,
        tiles=tuple(
            CompositeTile(
                output_id=output_id,
                rect=PixelRect(
                    x=next(tile[1] for tile in tiles if tile[0] == output_id),
                    y=next(tile[2] for tile in tiles if tile[0] == output_id),
                    width=next(tile[3] for tile in tiles if tile[0] == output_id),
                    height=next(tile[4] for tile in tiles if tile[0] == output_id),
                ),
                source_code_bits=next(
                    item.rgb_bits_per_channel
                    for item in display.active_outputs
                    if item.output_id == output_id
                ),
            )
            for output_id, *_ in tiles
        ),
        native_pixel_format="rgba8_bottom_up"
        if source_bits == 8
        else "r10g10b10a2_le_bottom_up",
        input_pixel_format=input_pixel_format,
        encoder_pixel_format=effective.output_pixel_format,
        encoder_gpu_ordinal=effective.encoder_gpu_ordinal,
        force_idr=effective.force_idr,
        effective_ffmpeg_args=tuple(ffmpeg_args),
        timing=ReviewTiming(
            pacing_output_id=pacing.output_id,
            rate_numerator=pacing.refresh_numerator,
            rate_denominator=pacing.refresh_denominator,
            implementation="ffmpeg_rawvideo_cfr_v1",
            capability_evidence_id=capability_evidence_id,
        ),
    )
    return review, effective


def ffmpeg_input_format(display: DisplayProfile) -> str:
    """Return the FFmpeg rawvideo format implied by the exact capture ABI."""
    bits = {output.rgb_bits_per_channel for output in display.active_outputs}
    if bits == {8}:
        return "rgba"
    if bits == {10}:
        # Little-endian packed pixels have R/G/B in the low 30 bits and two
        # unused high bits. FFmpeg's x2bgr10le has that same memory layout.
        return "x2bgr10le"
    raise EncodingOptionsError(
        "review capture requires uniform 8-bit or packed 10-bit RGB outputs"
    )


def build_review_argv(
    executable: Path,
    encoding: ReviewEncoding,
    output: Path,
    *,
    fragment_target_ns: int,
) -> list[str]:
    """Build Visual Stimulus's single lossy fragmented-MP4 command without acquisition flags."""
    if (
        not executable.is_absolute()
        or not output.is_absolute()
        or fragment_target_ns <= 0
    ):
        raise EncodingOptionsError(
            "prepared FFmpeg path and fragment interval are required"
        )
    seconds = format(fragment_target_ns / 1_000_000_000, ".9f").rstrip("0").rstrip(".")
    rate = f"{encoding.timing.rate_numerator}/{encoding.timing.rate_denominator}"
    force_keyframes = f"expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{seconds}))"
    args = [
        str(executable),
        "-hide_banner",
        "-nostdin",
        "-progress",
        "pipe:1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        encoding.input_pixel_format,
        "-s",
        f"{encoding.composite_width}x{encoding.composite_height}",
        "-framerate",
        rate,
        "-i",
        "-",
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        *encoding.effective_ffmpeg_args,
        "-gpu",
        str(encoding.encoder_gpu_ordinal),
        "-bf",
        "0",
        "-force_key_frames",
        force_keyframes,
        "-fps_mode:v",
        "passthrough",
        "-map_metadata",
        "-1",
        "-movflags",
        "+frag_keyframe+empty_moov+default_base_moof",
    ]
    if encoding.force_idr:
        args.extend(("-forced-idr", "1"))
    args.extend(("-n", "-f", "mp4", str(output)))
    return args


def _composite_geometry(
    display: DisplayProfile, maximum: tuple[int, int]
) -> tuple[int, int, int, tuple[tuple[str, int, int, int, int], ...]]:
    count = len(display.active_outputs)
    columns = isqrt(count - 1) + 1
    for scale in range(
        1, max(max(o.width_px, o.height_px) for o in display.active_outputs) + 1
    ):
        sizes = [
            (o.width_px // scale, o.height_px // scale) for o in display.active_outputs
        ]
        if any(min(size) <= 0 for size in sizes):
            break
        widths = [
            max(sizes[i][0] for i in range(col, count, columns))
            for col in range(min(columns, count))
        ]
        rows = (count + columns - 1) // columns
        heights = [
            max(
                sizes[i][1]
                for i in range(row * columns, min(count, (row + 1) * columns))
            )
            for row in range(rows)
        ]
        width, height = sum(widths), sum(heights)
        if width <= maximum[0] and height <= maximum[1]:
            layout = tile_layout(display.active_outputs, scale, height)
            return width, height, scale, tuple(layout)
    raise EncodingOptionsError(
        "no integer tile scale fits the selected encoder maximum"
    )
