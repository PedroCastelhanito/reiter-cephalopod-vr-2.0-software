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


@pytest.mark.parametrize("source_pixel_format", ["rgb24", "rgba"])
def test_shipped_rgb_to_yuv_default_filter_chain_has_explicit_output_matrix(
    source_pixel_format,
) -> None:
    result = validate_filter_chain(
        "scale=w=iw:h=ih:in_range=full:out_range=full:out_color_matrix=bt709,format=pix_fmts=yuv444p",
        source=source_format(source_pixel_format, 640, 480),
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


def test_packed_review_rgb10_requires_explicit_matrix_without_precision_loss():
    from cephvr.shared.ffmpeg_filters import FilterError

    source = source_format("x2bgr10le", 640, 480)
    arguments = dict(
        source=source,
        target_depth=10,
        accepted_pixel_formats=frozenset({"yuv444p10le"}),
        terminal_pixel_format="yuv444p10le",
        output_range="pc",
        output_matrix="bt709",
    )
    with pytest.raises(FilterError, match="explicit matrix"):
        validate_filter_chain(
            "scale=w=iw:h=ih,format=pix_fmts=yuv444p10le", **arguments
        )
    result = validate_filter_chain(
        "scale=w=iw:h=ih:in_range=full:out_range=full:out_color_matrix=bt709,format=pix_fmts=yuv444p10le",
        **arguments,
    )
    assert result.image.depth == 10
    assert (result.image.width, result.image.height) == (640, 480)
