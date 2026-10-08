"""Resolve the Save-On encoder from registered capability evidence at Setup."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.nvenc_capabilities import NvencProbeOwner
from cephvr.shared.encoder_probe import RegisteredCapabilityProbe
from cephvr.shared.ffmpeg_arguments import parse_option_tokens
from cephvr.shared.ffmpeg_capabilities import probe_nvenc_capabilities
from cephvr.shared.ffmpeg_types import EncoderCapabilities, EncodingOptionsError
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher
from cephvr.visual_stimulus.config.models.artifact_models import ReviewEncoding
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.identity import FFMPEG_PROBE_ROLE

from .encoding import (
    VISUAL_STIMULUS_FRAGMENT_FLAGS,
    ffmpeg_input_format,
    prepare_review_encoding,
)


def resolve_review_encoding(
    *,
    executable: Path,
    display: DisplayProfile,
    ffmpeg_args: Sequence[str],
    launcher: SupervisedEncoderLauncher,
    nvenc_owner: NvencProbeOwner,
    work: pb.WorkContext,
    parent_operation: pb.OperationContext,
    deadline_ns: int,
    register_resource: Callable[[str], None],
    report_probe_resource: Callable[[str, bool], None],
    input_pixel_format: str | None = None,
) -> tuple[ReviewEncoding, str]:
    parsed = parse_option_tokens(
        ffmpeg_args, owner="Visual Stimulus", error=EncodingOptionsError
    )
    codec = parsed["-c:v"][0]
    launcher.bind_operation(work, parent_operation)
    aggregate_key = f"ffmpeg_capability_probe_{uuid4()}"
    register_resource(aggregate_key)
    probe = RegisteredCapabilityProbe(
        launcher,
        work,
        parent_operation,
        lambda _key, success: report_probe_resource(aggregate_key, success),
        role=FFMPEG_PROBE_ROLE,
    )
    try:
        capabilities: EncoderCapabilities = probe_nvenc_capabilities(
            str(executable),
            codec=codec,
            nvenc_owner=nvenc_owner,
            probe=probe,
            deadline_ns=deadline_ns,
            required_muxer_flags=VISUAL_STIMULUS_FRAGMENT_FLAGS,
        )
    except BaseException:
        probe.retry_cleanup(deadline_ns=deadline_ns)
        raise
    capture_format = ffmpeg_input_format(display)
    if input_pixel_format is not None and input_pixel_format != capture_format:
        raise EncodingOptionsError(
            "configured raw-input format conflicts with the renderer capture ABI"
        )
    review, resolved = prepare_review_encoding(
        display,
        ffmpeg_args=ffmpeg_args,
        capabilities=capabilities,
        input_pixel_format=capture_format,
        capability_evidence_id=aggregate_key,
    )
    if (
        review.encoder_gpu_ordinal != resolved.encoder_gpu_ordinal
        or review.force_idr != resolved.force_idr
    ):
        raise RuntimeError("ReviewEncoding omitted resolved encoder device facts")
    return review, aggregate_key
