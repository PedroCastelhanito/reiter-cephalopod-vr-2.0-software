from __future__ import annotations

import pytest

from cephvr.shared.ffmpeg_filter_expressions import (
    ExpressionError,
    resolve_dimensions,
)
from cephvr.shared.ffmpeg_filters import (
    ImageFormat,
    source_format,
    validate_filter_chain,
)


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


@pytest.mark.parametrize(
    ("expression", "width", "height", "color_range", "matrix"),
    [
        ("crop=w=320:h=240", 320, 240, "full", "bt709"),
        ("pad=w=800:h=600", 800, 600, "full", "bt709"),
        (
            "scale=w=320:h=240:in_range=full:out_range=limited:"
            "in_color_matrix=bt709:out_color_matrix=bt2020",
            320,
            240,
            "limited",
            "bt2020",
        ),
    ],
)
def test_geometry_filters_preserve_pixel_layout_and_resolve_color_metadata(
    expression: str, width: int, height: int, color_range: str, matrix: str
) -> None:
    source = ImageFormat("yuv420p10le", 10, 640, 480, 2, 2, "full", "bt709")
    result = validate_filter_chain(
        f"{expression},format=pix_fmts=yuv420p10le",
        source=source,
        target_depth=10,
        accepted_pixel_formats=frozenset({"yuv420p10le"}),
        terminal_pixel_format="yuv420p10le",
        output_range=color_range,
        output_matrix=matrix,
    )
    expected = ImageFormat("yuv420p10le", 10, width, height, 2, 2, color_range, matrix)
    assert result.stages == (source, expected, expected)
    assert result.image == expected
    assert source == ImageFormat("yuv420p10le", 10, 640, 480, 2, 2, "full", "bt709")
