"""Shared FFmpeg option spellings and strict one-value token parsing."""

from __future__ import annotations

from collections.abc import Callable, Sequence

ALIASES = {
    "-codec:v": "-c:v",
    "-vcodec": "-c:v",
    "-c:v:0": "-c:v",
    "-codec:v:0": "-c:v",
    "-filter:v": "-vf",
    "-filter:v:0": "-vf",
    "-vb": "-b:v",
    "-profile:v:0": "-profile:v",
    "-level:v:0": "-level:v",
    "-b:v:0": "-b:v",
    "-maxrate": "-maxrate:v",
    "-maxrate:v:0": "-maxrate:v",
    "-minrate": "-minrate:v",
    "-minrate:v:0": "-minrate:v",
    "-bufsize": "-bufsize:v",
    "-bufsize:v:0": "-bufsize:v",
}
CANONICAL_STEMS = {
    "-c": "-c:v",
    "-pix_fmt": "-pix_fmt",
    "-vf": "-vf",
    "-preset": "-preset",
    "-tune": "-tune",
    "-profile": "-profile:v",
    "-level": "-level:v",
    "-rc": "-rc",
    "-cq": "-cq",
    "-qp": "-qp",
    "-b": "-b:v",
    "-maxrate": "-maxrate:v",
    "-minrate": "-minrate:v",
    "-bufsize": "-bufsize:v",
    "-rc-lookahead": "-rc-lookahead",
    "-surfaces": "-surfaces",
    "-spatial-aq": "-spatial-aq",
    "-temporal-aq": "-temporal-aq",
    "-zerolatency": "-zerolatency",
    "-aq-strength": "-aq-strength",
    "-multipass": "-multipass",
    "-color_range": "-color_range",
    "-colorspace": "-colorspace",
    "-color_primaries": "-color_primaries",
    "-color_trc": "-color_trc",
}
SIMPLE_OPTIONS = frozenset(
    {
        "-c:v",
        "-pix_fmt",
        "-vf",
        "-preset",
        "-tune",
        "-profile:v",
        "-level:v",
        "-rc",
        "-cq",
        "-qp",
        "-b:v",
        "-maxrate:v",
        "-minrate:v",
        "-bufsize:v",
        "-rc-lookahead",
        "-surfaces",
        "-spatial-aq",
        "-temporal-aq",
        "-zerolatency",
        "-aq-strength",
        "-multipass",
        "-color_range",
        "-colorspace",
        "-color_primaries",
        "-color_trc",
        "-metadata:s:v:0",
    }
)
BACKEND_OWNED_OPTIONS = frozenset(
    {
        "-framerate",
        "-s",
        "-r",
        "-fpsmax",
        "-vsync",
        "-fps_mode",
        "-t",
        "-to",
        "-ss",
        "-frames",
        "-copyts",
        "-itsoffset",
        "-enc_time_base",
        "-force_key_frames",
        "-g",
        "-movflags",
        "-f",
        "-filter_complex",
        "-map",
        "-metadata",
        "-map_metadata",
        "-map_chapters",
        "-gpu",
        "-bf",
        "-i",
        "-y",
        "-n",
        "-pass",
        "-passlogfile",
        "-vstats_file",
        "-segment_time",
    }
)


def canonical_option(option: str) -> str:
    if option in ALIASES:
        return ALIASES[option]
    selector = (
        ":v:0" if option.endswith(":v:0") else ":v" if option.endswith(":v") else ""
    )
    stem = option[: -len(selector)] if selector else option
    return CANONICAL_STEMS.get(stem, option)


def parse_option_tokens(
    values: Sequence[str],
    *,
    owner: str,
    error: Callable[[str], Exception],
) -> dict[str, list[str]]:
    """Parse argv as separate option/value tokens without selecting backend policy."""
    parsed: dict[str, list[str]] = {}
    i = 0
    while i < len(values):
        raw = values[i]
        if not raw or "\x00" in raw:
            raise error(f"invalid empty/NUL argument at token {i}")
        if not raw.startswith("-") or raw == "-":
            raise error(f"positional token {i} is unsupported")
        if "=" in raw:
            raise error("each supported FFmpeg option takes a separate value token")
        canonical = canonical_option(raw)
        if canonical in BACKEND_OWNED_OPTIONS:
            raise error(f"{raw} is {owner}-owned")
        if canonical not in SIMPLE_OPTIONS:
            raise error(f"unsupported FFmpeg option {raw!r} at token {i}")
        if i + 1 >= len(values) or values[i + 1].startswith("-"):
            raise error(f"{raw} is missing its one value")
        value = values[i + 1]
        i += 2
        if not value or "\x00" in value:
            raise error(f"{raw} has an empty/NUL value")
        parsed.setdefault(canonical, []).append(value)
    for option, supplied in parsed.items():
        if option != "-metadata:s:v:0" and len(supplied) != 1:
            raise error(f"duplicate single-value option {option}")
    if "-c:v" not in parsed or "-pix_fmt" not in parsed:
        raise error("-c:v and explicit -pix_fmt are required")
    return parsed
