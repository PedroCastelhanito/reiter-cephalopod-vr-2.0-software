"""Protected renderer bootstrap decoding and exact endpoint registration."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.backend_bootstrap import (
    decode_control_policies,
    require_loopback_endpoint,
)
from cephvr.shared.identity import require_uuid4
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus


@dataclass(frozen=True)
class WorkerBootstrap:
    context: visual_stimulus.WorkerContext
    supervisor: pb.ProcessIdentity
    controller: pb.ProcessIdentity
    token: str
    owner_token: str
    supervisor_token: str
    coordinator_endpoint: str
    supervisor_endpoint: str
    launch_command_id: str
    pid: int
    creation_time_100ns: int
    registration_deadline_ns: int
    max_message_bytes: int
    heartbeat_interval_ns: int
    health_silence_ns: int
    software_root: Path
    policies: pb.ControlPolicies
    owner_pid: int
    owner_creation_time_100ns: int
    supervisor_pid: int
    supervisor_creation_time_100ns: int


def decode(document: Mapping[str, object]) -> WorkerBootstrap:
    def text(key: str) -> str:
        value = document.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"renderer bootstrap missing {key}")
        return value

    def number(key: str) -> int:
        value = document.get(key)
        if type(value) is not int or value <= 0:
            raise ValueError(f"renderer bootstrap invalid {key}")
        return value

    context = visual_stimulus.WorkerContext.FromString(
        base64.b64decode(text("context"), validate=True)
    )
    if (
        context.worker.role != "visual_stimulus_renderer"
        or context.owner.role != "visual_stimulus"
        or context.worker.generation != require_uuid4(text("generation"))
        or context.owner.generation != require_uuid4(text("owner_generation"))
        or text("role") != "visual_stimulus_renderer"
    ):
        raise ValueError("renderer bootstrap identity mismatch")
    for endpoint in ("coordinator_endpoint", "supervisor_endpoint"):
        require_loopback_endpoint(text(endpoint), f"renderer {endpoint}")
    if number("heartbeat_interval_ns") >= number("health_silence_ns"):
        raise ValueError("invalid renderer health policy")
    return WorkerBootstrap(
        context,
        pb.ProcessIdentity(
            role="supervisor", generation=require_uuid4(text("supervisor_generation"))
        ),
        pb.ProcessIdentity(
            role="controller", generation=require_uuid4(text("controller_generation"))
        ),
        text("token"),
        text("owner_token"),
        text("supervisor_token"),
        text("coordinator_endpoint"),
        text("supervisor_endpoint"),
        require_uuid4(text("launch_command_id")),
        number("pid"),
        number("creation_time_100ns"),
        number("registration_deadline_ns"),
        number("max_message_bytes"),
        number("heartbeat_interval_ns"),
        number("health_silence_ns"),
        Path(text("software_root")),
        decode_control_policies(text("control_policies")),
        number("owner_pid"),
        number("owner_creation_time_100ns"),
        number("supervisor_pid"),
        number("supervisor_creation_time_100ns"),
    )
