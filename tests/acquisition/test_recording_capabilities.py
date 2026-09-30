"""Encoder capability parsing, device limits and exact probe ownership."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from cephvr.acquisition.identity import FFMPEG_PROBE_ROLE
from cephvr.acquisition.recording.capabilities import (
    _encoder_options,
    _parse_muxer_flags,
    _parse_options,
)
from cephvr.acquisition.recording.encoder import SupervisedEncoderLauncher
from cephvr.acquisition.recording.encoder_probe import SupervisedCapabilityProbe
from cephvr.acquisition.recording.encoding import (
    EncoderCapabilities,
    EncodingOptionsError,
    validate_arguments,
)
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.nvenc_features import _rate_control_modes


class _Process:
    launch_id = "probe-command"
    stdout_text = "ffmpeg version fixture"
    diagnostic_tail = ("fixture stderr",)

    def close_stdin(self, *, deadline_ns: int) -> None:
        assert deadline_ns == 500

    def wait(self, *, deadline_ns: int) -> int:
        assert deadline_ns == 500
        return 0


class _Launcher:
    def __init__(self) -> None:
        self.operation: tuple[types.WorkContext, types.OperationContext] | None = None
        self.launch_call: tuple[tuple[str, ...], dict[str, object]] | None = None
        self.process = _Process()

    def bind_operation(
        self, work: types.WorkContext, parent: types.OperationContext
    ) -> None:
        self.operation = (work, parent)

    def launch(self, argv: tuple[str, ...], **kwargs: object) -> _Process:
        self.launch_call = (argv, kwargs)
        return self.process


def test_probe_uses_setup_identity_and_reports_exact_local_release() -> None:
    launcher = _Launcher()
    work = types.WorkContext()
    parent = types.OperationContext(command_id="setup-command")
    reports: list[tuple[str, bool]] = []
    probe = SupervisedCapabilityProbe(
        cast(SupervisedEncoderLauncher, launcher),
        work,
        parent,
        lambda *item: reports.append(item),
    )

    result = probe.run("C:/ffmpeg.exe", ("-hide_banner", "-encoders"), deadline_ns=500)

    assert result.returncode == 0
    assert result.stdout == "ffmpeg version fixture"
    assert result.stderr == "fixture stderr"
    assert launcher.operation is not None
    assert launcher.operation[1].command_id == "setup-command"
    assert launcher.launch_call is not None
    argv, kwargs = launcher.launch_call
    assert argv == ("C:/ffmpeg.exe", "-hide_banner", "-encoders")
    assert kwargs["role"] == FFMPEG_PROBE_ROLE
    assert kwargs["output_path"] is None
    assert kwargs["capture_stdout"] is True
    assert reports == [("ffmpeg:probe-command", True)]


def test_nvenc_rate_control_mask_uses_enum_values() -> None:
    assert _rate_control_modes(0) == frozenset({"constqp"})
    assert _rate_control_modes(1) == frozenset({"constqp", "vbr"})
    assert _rate_control_modes(2) == frozenset({"constqp", "cbr"})
    assert _rate_control_modes(3) == frozenset({"constqp", "vbr", "cbr"})


def test_mp4_muxer_help_reads_only_flag_constants_under_movflags() -> None:
    text = """MP4 muxer AVOptions:
  -brand <string> E.......... Override major brand
  -movflags <flags> E.......... MOV muxer flags (default 0)
     frag_keyframe             4 E.......... Fragment at video keyframes
     use_metadata_tags        1024 E.......... Use mdta atom for metadata
     hybrid_fragmented        32768 E.......... Convert fragmented file at end
  -video_track_timescale <int> E.......... Set timescale
     use_stream_ids_as_track_ids 512 E.......... Use stream IDs
"""
    assert _parse_muxer_flags(text) == frozenset(
        {"frag_keyframe", "use_metadata_tags", "hybrid_fragmented"}
    )


def test_encoder_help_retains_declaration_line_bounds_and_video_aliases() -> None:
    text = """-rc-lookahead <int> E..V....... (from 0 to 32) (default 0)
-profile:v:0 <string> E..V....... Set profile
    baseline             66 E..V....... Baseline profile
    high                 77 E..V....... High profile
-maxrate <int64> E..V....... (from 0 to I64_MAX)
-surfaces <int> E..V....... (from 0 to INT_MAX) (default 0)
"""
    options, ranges = _parse_options(text)
    assert ranges["-rc-lookahead"] == (0.0, 32.0)
    assert "baseline" in options["-profile:v"]
    assert "high" in options["-profile:v"]
    assert "-profile:v" in options
    assert "-maxrate:v" in options
    assert ranges["-maxrate:v"] == (0.0, float(2**63 - 1))
    assert ranges["-surfaces"] == (0.0, float(2**31 - 1))


def test_selected_encoder_does_not_inherit_other_encoders_private_options() -> None:
    selected = """Encoder h264_nvenc:
  -preset <int> E..V....... (from 0 to 18)
     p4 15 E..V....... Medium preset
  -rc-lookahead <int> E..V....... (from 0 to 32)
"""
    full = """AVCodecContext AVOptions:
  -b <int64> E..V....... (from 0 to I64_MAX)
  -color_range <int> E..V....... (from 0 to 2)
     pc 2 E..V....... Full range
  -profile <int> E..V....... (from 0 to INT_MAX)

Other encoder AVOptions:
  -preset <string> E..V....... Preset
     alien 0 E..V....... Unrelated preset
  -rc-lookahead <int> E..V....... (from 0 to 250)
  -forced-idr <boolean> E..V....... Force IDR
  -color_range <int> E..V....... (from 0 to 99)
     alien 99 E..V....... Unrelated enum
"""
    options, ranges = _encoder_options(selected, full)
    assert options["-preset"] == frozenset({"p4"})
    assert ranges["-rc-lookahead"] == (0.0, 32.0)
    assert "-forced-idr" not in options
    assert "-profile:v" not in options
    assert "-b:v" in options
    assert options["-color_range"] == frozenset({"pc"})
    assert ranges["-color_range"] == (0.0, 2.0)


def _capabilities() -> EncoderCapabilities:
    """Small explicit device/build evidence for validation, never a rig claim."""
    return EncoderCapabilities(
        codecs=frozenset({"h264_nvenc"}),
        pixel_formats=frozenset({"yuv420p"}),
        options={
            "-forced-idr": frozenset({"0", "1"}),
            "-rc-lookahead": frozenset(),
            "-b:v": frozenset(),
        },
        numeric_ranges={"-rc-lookahead": (0, 32)},
        muxer_flags=frozenset(
            {"hybrid_fragmented", "frag_keyframe", "use_metadata_tags"}
        ),
        encoder_gpu_ordinal=1,
        device_uuid="GPU-00000000-0000-4000-8000-000000000001",
        codec_pixel_formats={"h264_nvenc": frozenset({"yuv420p"})},
        device_codec_pixel_formats={"h264_nvenc": frozenset({"yuv420p"})},
        device_codec_profiles={"h264_nvenc": frozenset({"high"})},
        device_rate_controls={"h264_nvenc": frozenset({"vbr"})},
        device_lookahead={"h264_nvenc": True},
        force_idr_codecs=frozenset({"h264_nvenc"}),
        device_max_dimensions={("h264_nvenc", "yuv420p"): (4096, 4096)},
    )


@pytest.mark.parametrize("size", [(4112, 480), (640, 4112)])
def test_output_beyond_device_dimensions_is_rejected(size: tuple[int, int]) -> None:
    with pytest.raises(EncodingOptionsError, match="exceeds device maximum"):
        validate_arguments(
            ["-c:v", "h264_nvenc", "-pix_fmt", "+yuv420p"],
            capabilities=_capabilities(),
            input_pixel_format="yuv420p",
            recording_bit_depth=8,
            input_width=size[0],
            input_height=size[1],
        )


@pytest.mark.parametrize("filter_size", [(4096, 480), (640, 4096)])
def test_device_limits_apply_after_explicit_filtering(
    filter_size: tuple[int, int],
) -> None:
    width, height = filter_size
    result = validate_arguments(
        [
            "-c:v",
            "h264_nvenc",
            "-pix_fmt",
            "+yuv420p",
            "-vf",
            f"scale=w={width}:h={height},format=pix_fmts=yuv420p",
        ],
        capabilities=_capabilities(),
        input_pixel_format="yuv420p",
        recording_bit_depth=8,
        input_width=4112,
        input_height=4112,
    )
    assert (result.output_width, result.output_height) == filter_size


def test_filter_cannot_enlarge_output_beyond_device_limit() -> None:
    with pytest.raises(EncodingOptionsError, match="exceeds device maximum"):
        validate_arguments(
            [
                "-c:v",
                "h264_nvenc",
                "-pix_fmt",
                "+yuv420p",
                "-vf",
                "scale=w=4112:h=480,format=pix_fmts=yuv420p",
            ],
            capabilities=_capabilities(),
            input_pixel_format="yuv420p",
            recording_bit_depth=8,
            input_width=640,
            input_height=480,
        )


@pytest.mark.parametrize("limits", [None, {}, {("h264_nvenc", "yuv420p"): (0, 4096)}])
def test_missing_or_invalid_device_dimension_evidence_blocks_preparation(
    limits: dict[tuple[str, str], tuple[int, int]] | None,
) -> None:
    with pytest.raises(EncodingOptionsError, match="dimension limits are missing"):
        validate_arguments(
            ["-c:v", "h264_nvenc", "-pix_fmt", "+yuv420p"],
            capabilities=replace(_capabilities(), device_max_dimensions=limits),
            input_pixel_format="yuv420p",
            recording_bit_depth=8,
            input_width=640,
            input_height=480,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ["-rc-lookahead", "abc"],
        ["-rc-lookahead", "1.5"],
        ["-rc-lookahead", "9" * 5000],
        ["-b:v", "9" * 400],
        ["-codec:v:0", "h264_nvenc"],
        ["-metadata:s:v:0", "title=a", "-metadata:s:v:0", "title=b"],
        ["-metadata:s:v:0", "cephvr_session_id=override"],
    ],
    ids=[
        "invalid",
        "fraction",
        "huge_integer",
        "infinite_bitrate",
        "alias_duplicate",
        "metadata_duplicate",
        "reserved_metadata",
    ],
)
def test_invalid_options_raise_the_encoding_boundary_error(
    arguments: list[str],
) -> None:
    with pytest.raises(EncodingOptionsError):
        validate_arguments(
            ["-c:v", "h264_nvenc", "-pix_fmt", "+yuv420p", *arguments],
            capabilities=_capabilities(),
            input_pixel_format="yuv420p",
            recording_bit_depth=8,
            input_width=640,
            input_height=480,
        )
