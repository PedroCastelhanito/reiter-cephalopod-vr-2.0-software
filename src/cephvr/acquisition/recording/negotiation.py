"""Bounded parsing of FFmpeg's live input/output stream initialization lines."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIMENSIONS = re.compile(r"\b([0-9]{1,6})x([0-9]{1,6})\b")
_VIDEO = re.compile(r"\bVideo:\s*(.+)$")


@dataclass(frozen=True)
class NegotiatedVideo:
    codec: str
    pixel_format: str
    width: int
    height: int


@dataclass(frozen=True)
class VideoNegotiationExpectation:
    input: NegotiatedVideo
    output: NegotiatedVideo


class VideoNegotiation:
    """Retain just two parsed stream facts; do not accumulate FFmpeg output."""

    def __init__(self, expectation: VideoNegotiationExpectation) -> None:
        self.expectation = expectation
        self.section: str | None = None
        self.input: NegotiatedVideo | None = None
        self.output: NegotiatedVideo | None = None
        self.error: str | None = None

    @property
    def complete(self) -> bool:
        return self.input is not None and self.output is not None

    def feed(self, line: str) -> None:
        stripped = line.strip()
        if stripped.startswith("Input #0,"):
            self.section = "input"
            return
        if stripped.startswith("Output #0,"):
            self.section = "output"
            return
        if self.section not in {"input", "output"}:
            return
        match = _VIDEO.search(stripped)
        if match is None:
            return
        try:
            parsed = _parse_video(match.group(1))
        except ValueError as exc:
            self.error = str(exc)
            return
        expected = (
            self.expectation.input
            if self.section == "input"
            else self.expectation.output
        )
        if parsed != expected:
            self.error = (
                f"FFmpeg {self.section} negotiated {parsed.codec}/"
                f"{parsed.pixel_format}/{parsed.width}x{parsed.height}; expected "
                f"{expected.codec}/{expected.pixel_format}/"
                f"{expected.width}x{expected.height}"
            )
            return
        if self.section == "input":
            self.input = parsed
        else:
            self.output = parsed
        self.section = None


def _parse_video(body: str) -> NegotiatedVideo:
    dimensions = _DIMENSIONS.search(body)
    if dimensions is None:
        raise ValueError("FFmpeg video stream initialization has no dimensions")
    before_dimensions = body[: dimensions.start()].rstrip(" ,")
    fields = _split_top_level_commas(before_dimensions)
    if len(fields) < 2:
        raise ValueError("FFmpeg video stream initialization has no pixel format")
    codec = fields[0].split("(", 1)[0].strip().split(" ", 1)[0]
    pixel_format = fields[1].split("(", 1)[0].strip().split(" ", 1)[0]
    if not codec or not pixel_format:
        raise ValueError("FFmpeg video stream initialization is incomplete")
    return NegotiatedVideo(
        codec,
        pixel_format,
        int(dimensions.group(1)),
        int(dimensions.group(2)),
    )


def _split_top_level_commas(value: str) -> list[str]:
    fields: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("FFmpeg video stream line has unbalanced parentheses")
        elif char == "," and depth == 0:
            fields.append(value[start:index].strip())
            start = index + 1
    if depth != 0:
        raise ValueError("FFmpeg video stream line has unbalanced parentheses")
    fields.append(value[start:].strip())
    return fields
