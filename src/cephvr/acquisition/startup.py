"""Validate protected acquisition process inputs passed by the supervisor."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.identity import require_uuid4


@dataclass(frozen=True)
class AcquisitionBootstrap:
    software_root: Path
    identity: control.ProcessIdentity
    controller: control.ProcessIdentity
    supervisor: control.ProcessIdentity
    tracking: control.ProcessIdentity
    token: str
    controller_token: str
    supervisor_token: str
    endpoint_port: int
    controller_port: int
    supervisor_port: int
    max_message_bytes: int
    heartbeat_interval_ns: int
    health_silence_ns: int
    launch_command_id: str
    pid: int
    creation_time_100ns: int
    controller_pid: int
    controller_creation_time_100ns: int
    supervisor_pid: int
    supervisor_creation_time_100ns: int
    policies: control.ControlPolicies


def decode_acquisition_bootstrap(
    document: Mapping[str, object],
) -> AcquisitionBootstrap:
    """Decode only supervisor-owned bootstrap fields and resolved shared policy."""
    role = _string(document, "role")
    generation = require_uuid4(_string(document, "generation"))
    controller_generation = require_uuid4(_string(document, "controller_generation"))
    supervisor_generation = require_uuid4(_string(document, "supervisor_generation"))
    tracking_generation = require_uuid4(_string(document, "tracking_generation"))
    if role != "acquisition":
        raise ValueError("acquisition bootstrap role must be acquisition")
    launch_id = require_uuid4(_string(document, "launch_command_id"))
    pid = _positive_integer(document, "pid")
    created = _positive_integer(document, "creation_time_100ns")
    controller_pid = _positive_integer(document, "controller_pid")
    controller_created = _positive_integer(document, "controller_creation_time_100ns")
    supervisor_pid = _positive_integer(document, "supervisor_pid")
    supervisor_created = _positive_integer(document, "supervisor_creation_time_100ns")
    maximum = _positive_integer(document, "max_message_bytes")
    heartbeat_interval_ns = _positive_integer(document, "heartbeat_interval_ns")
    health_silence_ns = _positive_integer(document, "health_silence_ns")
    if heartbeat_interval_ns >= health_silence_ns:
        raise ValueError("acquisition health cadence exceeds its silence bound")
    if maximum > (1 << 31) - 1:
        raise ValueError("shared gRPC message limit exceeds signed 32-bit bounds")
    for field in ("endpoint_port", "controller_port", "supervisor_port"):
        value = _positive_integer(document, field)
        if value > 65535:
            raise ValueError(f"bootstrap {field} exceeds TCP port range")
    policies = _decode_policies(_string(document, "control_policies"))
    return AcquisitionBootstrap(
        software_root=Path(_string(document, "software_root")).resolve(),
        identity=control.ProcessIdentity(role=role, generation=generation),
        controller=control.ProcessIdentity(
            role="controller", generation=controller_generation
        ),
        supervisor=control.ProcessIdentity(
            role="supervisor", generation=supervisor_generation
        ),
        tracking=control.ProcessIdentity(
            role="tracking", generation=tracking_generation
        ),
        token=_string(document, "token"),
        controller_token=_string(document, "controller_token"),
        supervisor_token=_string(document, "supervisor_token"),
        endpoint_port=_positive_integer(document, "endpoint_port"),
        controller_port=_positive_integer(document, "controller_port"),
        supervisor_port=_positive_integer(document, "supervisor_port"),
        max_message_bytes=maximum,
        heartbeat_interval_ns=heartbeat_interval_ns,
        health_silence_ns=health_silence_ns,
        launch_command_id=launch_id,
        pid=pid,
        creation_time_100ns=created,
        controller_pid=controller_pid,
        controller_creation_time_100ns=controller_created,
        supervisor_pid=supervisor_pid,
        supervisor_creation_time_100ns=supervisor_created,
        policies=policies,
    )


def _decode_policies(encoded: str) -> control.ControlPolicies:
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("resolved ControlPolicies are not valid base64") from exc
    if not payload:
        raise ValueError("resolved ControlPolicies are empty")
    policies = control.ControlPolicies.FromString(payload)
    for name in (
        "setup",
        "setup_cancel",
        "trial_ready",
        "trial_finished",
        "supervisor_registration",
    ):
        wait = getattr(policies, name)
        if not wait.HasField("initial_ns") or wait.initial_ns <= 0:
            raise ValueError(f"resolved ControlPolicies.{name}.initial_ns is required")
    for name in (
        "start_lead_ns",
        "controller_release_offset_ns",
        "backend_release_offset_ns",
        "start_evidence_allowance_ns",
        "stop_evidence_allowance_ns",
        "metadata_timeout_ns",
        "command_retention_after_finalization_ns",
        "recovery_ns",
    ):
        value = getattr(policies, name)
        if value <= 0:
            raise ValueError(f"resolved ControlPolicies.{name} must be positive")
    if policies.trial_command_transport_retries != 1:
        raise ValueError("resolved trial command retry policy must equal one")
    return policies


def _string(document: Mapping[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"acquisition bootstrap {key} must be nonempty text")
    return value


def _positive_integer(document: Mapping[str, object], key: str) -> int:
    value = document.get(key)
    if type(value) is not int or value <= 0:
        raise ValueError(f"acquisition bootstrap {key} must be a positive integer")
    return value
