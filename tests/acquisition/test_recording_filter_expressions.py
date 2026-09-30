from __future__ import annotations

import pytest

from cephvr.acquisition.recording.filter_expressions import (
    ExpressionError,
    resolve_dimensions,
)
from cephvr.acquisition.recording.filters import source_format, validate_filter_chain


def test_dimensions_resolve_oh_dependency_without_substituting_input_height() -> None:
    assert resolve_dimensions("oh*2", "ih/2", input_width=640, input_height=480) == (
        480,
        240,
    )


@pytest.mark.parametrize(
    ("width", "height"),
    [("oh", "ow"), ("max(1)", "ih"), ("iw//2", "ih")],
)
def test_dimension_parser_rejects_cycles_and_non_ffmpeg_expressions(
    width: str, height: str
) -> None:
    with pytest.raises(ExpressionError):
        resolve_dimensions(width, height, input_width=640, input_height=480)


def test_shipped_rgb_to_yuv_default_filter_chain_has_explicit_output_matrix() -> None:
    result = validate_filter_chain(
        "scale=w=iw:h=ih:in_range=full:out_range=full:out_color_matrix=bt709,format=pix_fmts=yuv444p",
        source=source_format("rgb24", 640, 480),
        target_depth=8,
        accepted_pixel_formats=frozenset({"yuv444p"}),
        terminal_pixel_format="yuv444p",
        output_range="pc",
        output_matrix="bt709",
    )
    assert result.image.pixel_format == "yuv444p"


def test_shipped_gray_to_yuv_default_filter_chain_needs_no_input_yuv_matrix() -> None:
    result = validate_filter_chain(
        "scale=w=iw:h=ih:in_range=full:out_range=full:out_color_matrix=bt709,format=pix_fmts=yuv444p",
        source=source_format("gray8", 640, 480),
        target_depth=8,
        accepted_pixel_formats=frozenset({"yuv444p"}),
        terminal_pixel_format="yuv444p",
        output_range="pc",
        output_matrix="bt709",
    )
    assert result.image.pixel_format == "yuv444p"
