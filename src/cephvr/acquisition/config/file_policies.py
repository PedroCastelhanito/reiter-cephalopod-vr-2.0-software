"""Resolve acquisition file-only health, serial and recording policies."""

from __future__ import annotations

from pathlib import Path

from cephvr.acquisition.v1 import camera_pb2, runtime_pb2
from cephvr.controller.microcontroller.config import load_serial_policies

from .policy import CONTRACT_VERSION, _load_pair
from .values import (
    _duration_ns,
    _load_transport,
    _required,
)


def load_file_policies(root: Path) -> runtime_pb2.AcquisitionFilePolicies:
    """Resolve the file-only timing and transport policies for Setup."""
    pair = _load_pair(Path(root))
    config = pair.config
    result = runtime_pb2.AcquisitionFilePolicies(contract_version=CONTRACT_VERSION)
    for role, enum_value in (
        ("behavioral", camera_pb2.CAMERA_ROLE_BEHAVIORAL),
        ("tracking", camera_pb2.CAMERA_ROLE_TRACKING),
    ):
        values = config.get("cameras", {}).get(role, {})
        policy = result.cameras.add(camera=enum_value)
        if "frame_silence_timeout_s" in values:
            policy.frame_silence_timeout_ns = _duration_ns(
                values["frame_silence_timeout_s"],
                f"cameras.{role}.frame_silence_timeout_s",
                1_000_000_000,
            )
        if "post_cutoff_drain_margin_ms" in values:
            policy.post_cutoff_drain_margin_ns = _duration_ns(
                values["post_cutoff_drain_margin_ms"],
                f"cameras.{role}.post_cutoff_drain_margin_ms",
                1_000_000,
            )
        transport = values.get("transport", {})
        _load_transport(policy.transport, transport, role)
    serial = load_serial_policies(Path(root))
    for field, value in serial.ListFields():
        if field.name.startswith("serial_"):
            setattr(result, field.name, value)
    recording = config.get("recording", {})
    result.frame_log_sync_interval_ns = _duration_ns(
        _required(recording, "sync_interval_s", "recording.sync_interval_s"),
        "recording.sync_interval_s",
        1_000_000_000,
    )
    storage = _required(recording, "storage", "recording.storage")
    result.video_sync_interval_ns = _duration_ns(
        _required(
            storage, "video_sync_interval_s", "recording.storage.video_sync_interval_s"
        ),
        "recording.storage.video_sync_interval_s",
        1_000_000_000,
    )
    encoding = _required(recording, "encoding", "recording.encoding")
    result.fragment_target_ns = _duration_ns(
        _required(
            encoding, "fragment_target_s", "recording.encoding.fragment_target_s"
        ),
        "recording.encoding.fragment_target_s",
        1_000_000_000,
    )
    health = _required(recording, "health", "recording.health")
    result.encoder_stall_timeout_ns = _duration_ns(
        _required(health, "stall_timeout_s", "recording.health.stall_timeout_s"),
        "recording.health.stall_timeout_s",
        1_000_000_000,
    )
    return result
