"""Decode the protected, inherited worker bootstrap descriptor."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.backend_bootstrap import require_loopback_endpoint
from cephvr.shared.identity import require_uuid4

from .state import WorkerBootstrap

_FIELDS = frozenset(
    {
        "role",
        "generation",
        "token",
        "owner_role",
        "owner_generation",
        "owner_token",
        "supervisor_role",
        "supervisor_generation",
        "supervisor_token",
        "supervisor_endpoint",
        "coordinator_endpoint",
        "coordinator_token",
        "launch_command_id",
        "pid",
        "creation_time_100ns",
        "registration_deadline_ns",
        "max_message_bytes",
        "heartbeat_interval_ns",
        "health_silence_ns",
        "worker_context",
        "control_policies",
        "file_policy",
    }
)


def decode_worker_bootstrap(document: Mapping[str, object]) -> WorkerBootstrap:
    """Validate identities, credentials, and deterministic protobuf byte fields."""
    if set(document) != _FIELDS:
        missing = sorted(_FIELDS - set(document))
        extra = sorted(set(document) - _FIELDS)
        raise ValueError(
            f"worker bootstrap fields mismatch; missing={missing}, extra={extra}"
        )
    strings = {
        key: _string(document, key) for key in _FIELDS - _INTEGER_FIELDS - _BYTES_FIELDS
    }
    for endpoint in ("supervisor_endpoint", "coordinator_endpoint"):
        require_loopback_endpoint(strings[endpoint], f"worker {endpoint}")
    if strings["role"] not in {
        "acquisition_behavioral_worker",
        "acquisition_tracking_worker",
    }:
        raise ValueError("worker bootstrap role is not a camera worker role")
    worker = control.ProcessIdentity(
        role=strings["role"], generation=strings["generation"]
    )
    owner = control.ProcessIdentity(
        role=strings["owner_role"], generation=strings["owner_generation"]
    )
    supervisor = control.ProcessIdentity(
        role=strings["supervisor_role"], generation=strings["supervisor_generation"]
    )
    for identity in (worker, owner, supervisor):
        require_uuid4(identity.generation)
    require_uuid4(strings["launch_command_id"])
    if supervisor.role != "supervisor":
        raise ValueError("worker bootstrap supervisor identity has an invalid role")
    context = acq.WorkerContext.FromString(_bytes_field(document, "worker_context"))
    if (
        not context.HasField("worker")
        or not context.HasField("owner")
        or context.worker != worker
        or context.owner != owner
    ):
        raise ValueError(
            "protected worker context disagrees with descriptor identities"
        )
    if context.camera != camera_for_process_role(worker.role):
        raise ValueError(
            "protected worker context camera disagrees with registered role"
        )
    policies = control.ControlPolicies.FromString(
        _bytes_field(document, "control_policies")
    )
    file_policy = runtime_pb2.CameraFilePolicy.FromString(
        _bytes_field(document, "file_policy")
    )
    if file_policy.camera != context.camera:
        raise ValueError("worker file policy camera differs from registered role")
    pid = _integer(document, "pid")
    creation_time = _integer(document, "creation_time_100ns")
    deadline = _integer(document, "registration_deadline_ns")
    max_message_bytes = _integer(document, "max_message_bytes")
    heartbeat_interval_ns = _integer(document, "heartbeat_interval_ns")
    health_silence_ns = _integer(document, "health_silence_ns")
    if pid > (1 << 32) - 1 or creation_time > (1 << 64) - 1 or deadline > (1 << 63) - 1:
        raise ValueError(
            "worker bootstrap process identity or deadline exceeds wire bounds"
        )
    if (
        heartbeat_interval_ns > (1 << 63) - 1
        or health_silence_ns > (1 << 63) - 1
        or heartbeat_interval_ns >= health_silence_ns
    ):
        raise ValueError("worker bootstrap health timing bounds are invalid")
    return WorkerBootstrap(
        context=context,
        supervisor=supervisor,
        coordinator_endpoint=strings["coordinator_endpoint"],
        coordinator_credential=strings["coordinator_token"].encode("utf-8"),
        control_policies=policies,
        file_policy=file_policy,
        worker_credential=strings["token"],
        owner_credential=strings["owner_token"],
        supervisor_credential=strings["supervisor_token"],
        supervisor_endpoint=strings["supervisor_endpoint"],
        launch_command_id=strings["launch_command_id"],
        pid=pid,
        creation_time_100ns=creation_time,
        registration_deadline_ns=deadline,
        max_message_bytes=max_message_bytes,
        heartbeat_interval_ns=heartbeat_interval_ns,
        health_silence_ns=health_silence_ns,
    )


_INTEGER_FIELDS = frozenset(
    {
        "pid",
        "creation_time_100ns",
        "registration_deadline_ns",
        "max_message_bytes",
        "heartbeat_interval_ns",
        "health_silence_ns",
    }
)
_BYTES_FIELDS = frozenset({"worker_context", "control_policies", "file_policy"})


def _string(document: Mapping[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"worker bootstrap {key} must be a nonempty string")
    return value


def _integer(document: Mapping[str, object], key: str) -> int:
    value = document.get(key)
    if type(value) is not int or value <= 0:
        raise ValueError(f"worker bootstrap {key} must be a positive integer")
    return value


def _bytes_field(document: Mapping[str, object], key: str) -> bytes:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"worker bootstrap {key} must be base64 text")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"worker bootstrap {key} is invalid base64") from exc
    if not decoded:
        raise ValueError(f"worker bootstrap {key} is empty")
    return decoded
