"""Small typed requests for managed display calibration and SpikeGLX inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.synchronization.v1 import spikeglx_pb2


def spikeglx_inventory_request(client: HeadlessClient) -> rpc.SpikeGLXInventoryRequest:
    snapshot = client.snapshot
    if not snapshot.HasField("configuration_values"):
        raise ClientError("Controller configuration is not synchronized.")
    return rpc.SpikeGLXInventoryRequest(
        command=client.operator_command(),
        expected_configuration_revision=snapshot.configuration.revision,
    )


def spikeglx_inventory_update_request(
    client: HeadlessClient,
    *,
    expected_revision: int,
    expected_file_sha256: str,
    pulse_channels: tuple[spikeglx_pb2.PulseChannel, ...],
) -> rpc.SpikeGLXInventoryUpdateRequest:
    snapshot = client.snapshot
    if (
        not snapshot.HasField("configuration_values")
        or snapshot.configuration.revision != expected_revision
        or snapshot.configuration_values.revision != expected_revision
    ):
        raise ClientError("SpikeGLX inventory draft is for an older configuration.")
    if not expected_file_sha256:
        raise ClientError("Reload the saved SpikeGLX inventory before editing it.")
    request = rpc.SpikeGLXInventoryUpdateRequest(
        command=client.operator_command(),
        expected_configuration_revision=expected_revision,
        expected_file_sha256=expected_file_sha256,
    )
    request.pulse_channels.extend(pulse_channels)
    return request


def open_display_calibration_request(
    client: HeadlessClient,
    *,
    arena_path: str,
    expected_revision: int,
    expected_profile_sha256: str,
    expected_arena_sha256: str,
) -> rpc.OpenDisplayCalibrationRequest:
    snapshot = client.snapshot
    if not snapshot.HasField("configuration_values"):
        raise ClientError("Controller configuration is not synchronized.")
    if snapshot.configuration.revision != expected_revision:
        raise ClientError("Display calibration request is for an older configuration.")
    configuration = snapshot.configuration_values.current
    if not configuration.HasField("asset_root") or not configuration.asset_root:
        raise ClientError("Choose and accept a Protocol Assets folder first.")
    root = Path(configuration.asset_root).resolve(strict=True)
    arena = Path(arena_path).resolve(strict=True)
    try:
        arena_reference = arena.relative_to(root).as_posix()
    except ValueError as exc:
        raise ClientError(
            "The prepared calibration arena is outside the accepted asset root."
        ) from exc
    profile = (root / "calibration" / "diagnostic_display_profile.json").resolve(
        strict=True
    )
    try:
        profile_reference = profile.relative_to(root).as_posix()
    except ValueError as exc:
        raise ClientError(
            "The calibration profile is outside the accepted asset root."
        ) from exc
    profile_bytes = profile.read_bytes()
    arena_bytes = arena.read_bytes()
    if len(profile_bytes) > 16_777_216 or len(arena_bytes) > 67_108_864:
        raise ClientError("Display calibration assets exceed the allowed size bounds.")
    profile_digest = hashlib.sha256(profile_bytes).hexdigest()
    arena_digest = hashlib.sha256(arena_bytes).hexdigest()
    if (profile_digest, arena_digest) != (
        expected_profile_sha256,
        expected_arena_sha256,
    ):
        raise ClientError(
            "Prepared calibration assets changed before command admission."
        )
    return rpc.OpenDisplayCalibrationRequest(
        command=client.operator_command(),
        expected_configuration_revision=expected_revision,
        diagnostic_id=str(uuid4()),
        profile_asset_reference=profile_reference,
        arena_asset_reference=arena_reference,
        expected_profile_sha256=profile_digest,
        expected_arena_sha256=arena_digest,
    )


def capture_display_calibration_intent(
    snapshot: pb.Snapshot, *, arena_path: str
) -> dict[str, object]:
    """Freeze the revision and asset bytes at the GUI click/export boundary."""
    if not snapshot.HasField("configuration_values"):
        raise ValueError("Controller configuration is not synchronized.")
    configuration = snapshot.configuration_values.current
    if not configuration.HasField("asset_root") or not configuration.asset_root:
        raise ValueError("Choose and accept a Protocol Assets folder first.")
    root = Path(configuration.asset_root).resolve(strict=True)
    arena = Path(arena_path).resolve(strict=True)
    profile = (root / "calibration" / "diagnostic_display_profile.json").resolve(
        strict=True
    )
    for asset in (arena, profile):
        try:
            asset.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "Calibration asset is outside the accepted asset root."
            ) from exc
    profile_bytes = profile.read_bytes()
    arena_bytes = arena.read_bytes()
    if len(profile_bytes) > 16_777_216 or len(arena_bytes) > 67_108_864:
        raise ValueError("Display calibration assets exceed the allowed size bounds.")
    return {
        "arena_path": str(arena),
        "expected_revision": snapshot.configuration.revision,
        "expected_profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "expected_arena_sha256": hashlib.sha256(arena_bytes).hexdigest(),
    }


def close_display_calibration_request(
    client: HeadlessClient,
    *,
    expected_revision: int,
    diagnostic_id: str,
) -> rpc.CloseDisplayCalibrationRequest:
    snapshot = client.snapshot
    if not snapshot.HasField(
        "visual_stimulus_display"
    ) or not snapshot.visual_stimulus_display.HasField("calibration"):
        raise ClientError("No controller calibration session is available to close.")
    evidence = snapshot.visual_stimulus_display.calibration
    if (
        evidence.controller_generation != snapshot.controller_generation
        or snapshot.configuration.revision != expected_revision
        or evidence.configuration_revision != expected_revision
        or evidence.diagnostic_id != diagnostic_id
        or not diagnostic_id
    ):
        raise ClientError(
            "Calibration evidence is stale; review the current display state."
        )
    return rpc.CloseDisplayCalibrationRequest(
        command=client.operator_command(),
        expected_configuration_revision=expected_revision,
        diagnostic_id=diagnostic_id,
    )


def validate_inventory_snapshot(
    snapshot: rpc.SpikeGLXInventorySnapshot, expected_revision: int
) -> None:
    if (
        snapshot.configuration_revision != expected_revision
        or not snapshot.file_sha256
        or not snapshot.HasField("backend_enabled")
        or not snapshot.HasField("address")
        or not snapshot.HasField("command_port")
        or not snapshot.address.strip()
        or snapshot.command_port < 1
        or snapshot.command_port > 65535
    ):
        raise ClientError(
            "SpikeGLX inventory response does not match the requested revision."
        )
    if any(
        not isinstance(item, spikeglx_pb2.PulseChannel)
        for item in snapshot.pulse_channels
    ):
        raise ClientError("SpikeGLX inventory contains an invalid channel record.")


def required_inventory_roles(
    configuration: pb.ExperimentConfiguration,
) -> frozenset[int]:
    """Mirror the bounded E12 required-role projection for the installed draft."""
    from cephvr.acquisition.v1 import camera_pb2

    required: set[int] = set()
    for backend in configuration.backends:
        if not backend.enabled:
            continue
        if (
            backend.backend_name == "acquisition"
            and backend.WhichOneof("settings") == "acquisition"
        ):
            acquisition = backend.acquisition
            for name, role in (
                ("behavioral", spikeglx_pb2.PULSE_ROLE_BEHAVIORAL_CAMERA),
                ("tracking", spikeglx_pb2.PULSE_ROLE_TRACKING_CAMERA),
            ):
                camera = getattr(acquisition, name)
                if (
                    camera.HasField("enabled")
                    and camera.enabled
                    and camera.device.frame_timing
                    == camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
                ):
                    required.add(role)
            if acquisition.HasField("pulses"):
                if (
                    acquisition.pulses.HasField("trial_state_enabled")
                    and acquisition.pulses.trial_state_enabled
                ):
                    required.add(spikeglx_pb2.PULSE_ROLE_TRIAL_STATE)
                if (
                    acquisition.pulses.HasField("projector_flip_enabled")
                    and acquisition.pulses.projector_flip_enabled
                ):
                    required.add(spikeglx_pb2.PULSE_ROLE_PROJECTOR_FLIP)
        if (
            backend.backend_name == "visual_stimulus"
            and backend.WhichOneof("settings") == "visual_stimulus"
        ):
            try:
                profile = json.loads(backend.visual_stimulus.display.profile_json)
            except (TypeError, ValueError):
                continue
            if isinstance(profile, dict) and profile.get("photodiode_enabled") is True:
                required.add(spikeglx_pb2.PULSE_ROLE_PHOTODIODE)
    return frozenset(required)
