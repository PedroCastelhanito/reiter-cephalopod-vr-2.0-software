"""The inherited worker bootstrap descriptor is validated before any channel opens."""

from __future__ import annotations

import base64
from uuid import uuid4

import pytest

from cephvr.acquisition.identity import camera_for_process_role
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import runtime_pb2
from cephvr.acquisition.worker.bootstrap import decode_worker_bootstrap
from cephvr.control.v1 import types_pb2 as control


def _encoded(message: object) -> str:
    return base64.b64encode(message.SerializeToString(deterministic=True)).decode()  # type: ignore[attr-defined]


def _document() -> dict[str, object]:
    role = "acquisition_behavioral_worker"
    worker = control.ProcessIdentity(role=role, generation=str(uuid4()))
    owner = control.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    camera = camera_for_process_role(role)
    policies = control.ControlPolicies()
    for name in (
        "setup",
        "setup_cancel",
        "trial_ready",
        "trial_finished",
        "supervisor_registration",
    ):
        getattr(policies, name).initial_ns = 1
    policies.recovery_ns = 1
    return {
        "role": role,
        "generation": worker.generation,
        "token": "worker-token",
        "owner_role": owner.role,
        "owner_generation": owner.generation,
        "owner_token": "owner-token",
        "supervisor_role": "supervisor",
        "supervisor_generation": str(uuid4()),
        "supervisor_token": "supervisor-token",
        "supervisor_endpoint": "127.0.0.1:20001",
        "coordinator_endpoint": "127.0.0.1:20002",
        "coordinator_token": "coordinator-token",
        "launch_command_id": str(uuid4()),
        "pid": 10,
        "creation_time_100ns": 11,
        "registration_deadline_ns": 12,
        "max_message_bytes": 1_000_000,
        "heartbeat_interval_ns": 5,
        "health_silence_ns": 15,
        "worker_context": _encoded(
            acq.WorkerContext(worker=worker, owner=owner, camera=camera)
        ),
        "control_policies": _encoded(policies),
        "file_policy": _encoded(runtime_pb2.CameraFilePolicy(camera=camera)),
    }


def test_a_complete_descriptor_decodes() -> None:
    decoded = decode_worker_bootstrap(_document())
    assert decoded.coordinator_endpoint == "127.0.0.1:20002"
    assert decoded.supervisor_endpoint == "127.0.0.1:20001"


@pytest.mark.parametrize("key", ["supervisor_endpoint", "coordinator_endpoint"])
@pytest.mark.parametrize(
    "endpoint",
    ["10.0.0.5:20001", "localhost:20001", "[::1]:20001", "0.0.0.0:20001", "127.0.0.1"],
)
def test_non_loopback_endpoints_are_rejected_before_any_channel_opens(
    key: str, endpoint: str
) -> None:
    document = _document()
    document[key] = endpoint
    with pytest.raises(ValueError, match="loopback"):
        decode_worker_bootstrap(document)


def test_unexpected_fields_are_rejected() -> None:
    document = _document()
    document["extra"] = "x"
    with pytest.raises(ValueError, match="fields mismatch"):
        decode_worker_bootstrap(document)
