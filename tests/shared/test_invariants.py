"""Failure invariants for E08/E14's process-local shared mechanisms."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from cephvr.control.v1 import types_pb2 as wire
from cephvr.shared.auth import AuthenticationError, require_authenticated_peer
from cephvr.shared.clock import (
    HOST_CLOCK_ID,
    HostClockCompatibilityError,
    HostClockDescriptor,
    descriptor_from_wire,
    validate_host_clock,
)
from cephvr.shared.commands import CommandCapacityError, CommandConflict, CommandLedger
from cephvr.shared.config import ConfigurationError, load_pair
from cephvr.shared.credentials import CredentialError, CredentialStore
from cephvr.shared.deadlines import Deadline, duration_ns
from cephvr.shared.identity import require_uuid4
from cephvr.shared.ingress import BoundedEventIngress, IngressOverload


def _id() -> str:
    return str(uuid.uuid4())


def test_clock_requires_matching_validated_domain() -> None:
    expected = HostClockDescriptor(HOST_CLOCK_ID, "QPC", True, False, 1e-7)
    validate_host_clock(
        HostClockDescriptor(HOST_CLOCK_ID, "QPC", True, False, 1e-6), expected
    )
    with pytest.raises(HostClockCompatibilityError):
        validate_host_clock(
            HostClockDescriptor(HOST_CLOCK_ID, "other", True, False, 1e-7), expected
        )
    missing_optional = wire.HostClockDescriptor(
        clock_id=HOST_CLOCK_ID,
        implementation="QPC",
        monotonic=True,
        resolution_s=1e-7,
    )
    with pytest.raises(HostClockCompatibilityError, match="adjustable"):
        descriptor_from_wire(missing_optional)


def test_uuid_requires_canonical_v4() -> None:
    valid = _id()
    assert require_uuid4(valid) == valid
    with pytest.raises(ValueError):
        require_uuid4(valid.upper())
    with pytest.raises(ValueError):
        require_uuid4(str(uuid.uuid1()))


def test_deadline_does_not_renew_or_round() -> None:
    deadline = Deadline(100)
    assert deadline.constrain(Deadline(200)).absolute_ns == 100
    assert deadline.remaining_ns(now_ns=110) == 0
    assert not deadline.expired_at(100)
    assert deadline.expired_at(101)
    assert duration_ns(0.08, "s") == 80_000_000
    with pytest.raises(ValueError):
        duration_ns(0.0000000001, "s")


def test_ledger_deduplicates_and_never_evicts_active() -> None:
    generation, command, other, work = _id(), _id(), _id(), _id()
    ledger = CommandLedger(
        generation, 300, max_records=1, max_bytes=100, result_reservation_bytes=20
    )
    assert not ledger.admit(command, b"exact request", 1, work_key=work).replayed
    assert ledger.admit(command, b"exact request", 2, work_key=work).replayed
    with pytest.raises(CommandConflict):
        ledger.admit(command, b"changed", 2, work_key=work)
    assert ledger.prune(10_000) == 0
    with pytest.raises(CommandCapacityError):
        ledger.admit(other, b"new", 10_000, work_key=work)
    ledger.complete(command, b"accepted completion", 20)
    ledger.finalize_work(work, 30)
    assert ledger.prune(330) == 0
    assert ledger.prune(331) == 1
    assert not ledger.admit(other, b"new", 332, work_key=_id()).replayed


def test_ledger_reserves_result_capacity_at_admission() -> None:
    ledger = CommandLedger(
        _id(), 1, max_records=2, max_bytes=10, result_reservation_bytes=8
    )
    ledger.admit(_id(), b"x", 0, work_key=_id())
    with pytest.raises(CommandCapacityError):
        ledger.admit(_id(), b"x", 0, work_key=_id())


def test_finalization_is_scoped_and_pending_result_is_preserved() -> None:
    first_work, second_work = _id(), _id()
    completed, pending, other = _id(), _id(), _id()
    ledger = CommandLedger(
        _id(), 10, max_records=3, max_bytes=60, result_reservation_bytes=10
    )
    ledger.admit(completed, b"a", 0, work_key=first_work)
    ledger.complete(completed, b"done", 1)
    ledger.admit(pending, b"b", 0, work_key=first_work)
    ledger.admit(other, b"c", 0, work_key=second_work)
    ledger.finalize_work(first_work, 2)
    assert ledger.prune(13) == 1
    assert ledger.get(pending) is not None
    assert ledger.get(other) is not None
    with pytest.raises(CommandConflict, match="finalized work"):
        ledger.admit(_id(), b"new", 14, work_key=first_work)
    ledger.complete(pending, b"late", 20)
    assert ledger.prune(30) == 0
    assert ledger.prune(31) == 1


def test_interruption_remains_available_on_ordinary_overload() -> None:
    ingress: BoundedEventIngress[str] = BoundedEventIngress(
        2, 4, max_interruption_payload_bytes=2
    )
    assert ingress.put(b"ab", "ordinary")
    assert not ingress.put(b"a", "rejected")
    with pytest.raises(IngressOverload):
        ingress.put(b"a", "essential", essential=True)
    assert ingress.put_interruption(b"x", "stop")
    assert not ingress.put_interruption(b"x", "duplicate")
    assert ingress.pending_events == 2
    assert ingress.pending_payload_bytes == 3
    with pytest.raises(IngressOverload):
        ingress.put_interruption(b"y", "another cause")
    assert ingress.take().event == "stop"  # type: ignore[union-attr]
    assert ingress.take().event == "ordinary"  # type: ignore[union-attr]
    assert ingress.pending_payload_bytes == 0


def test_auth_requires_exact_registered_peer_token_and_generation() -> None:
    generation = _id()
    metadata = [
        ("x-cephvr-role", "controller"),
        ("x-cephvr-generation", generation),
        ("x-cephvr-token", "secret"),
    ]
    require_authenticated_peer(
        "ipv4:127.0.0.1:1234",
        metadata,
        expected_role="controller",
        expected_token="secret",
        expected_generation=generation,
    )
    with pytest.raises(AuthenticationError):
        require_authenticated_peer(
            "ipv4:192.0.2.1:1234",
            metadata,
            expected_role="controller",
            expected_token="secret",
            expected_generation=generation,
        )
    with pytest.raises(AuthenticationError):
        require_authenticated_peer(
            "ipv4:127.0.0.1:1234",
            metadata,
            expected_role="controller",
            expected_token="wrong",
            expected_generation=generation,
        )


def test_config_rejects_version_mismatch_and_unknown_keys(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    policy = tmp_path / "policy.toml"
    config.write_text(
        "format_version = 1\npolicy_version = 2\n[health]\nsilence_timeout_s = 15\n"
    )
    policy.write_text('policy_version = 2\n[health]\nloss = "shutdown"\n')
    pair = load_pair(
        config,
        policy,
        allowed_config_keys={"health.silence_timeout_s"},
        allowed_policy_keys={"health.loss"},
        expected_policy={"health.loss": "shutdown"},
    )
    assert pair.policy_version == 2
    policy.write_text('policy_version = 3\n[health]\nloss = "shutdown"\n')
    with pytest.raises(ConfigurationError, match="policy_version mismatch"):
        load_pair(
            config,
            policy,
            allowed_config_keys={"health.silence_timeout_s"},
            allowed_policy_keys={"health.loss"},
        )
    policy.write_text('policy_version = 2\n[health]\nloss = "shutdown"\n')
    config.write_text(
        "format_version = 1\npolicy_version = 2\n"
        "[health]\nsilence_timeout_s = 15\nremoved_grace_s = 1\n"
    )
    with pytest.raises(ConfigurationError, match="health.removed_grace_s"):
        load_pair(
            config,
            policy,
            allowed_config_keys={"health.silence_timeout_s"},
            allowed_policy_keys={"health.loss"},
        )


def test_operator_credentials_are_generation_scoped_and_owner_only(
    tmp_path: Path,
) -> None:
    first = CredentialStore(tmp_path / "runtime", _id())
    principal = first.provision_client("cli")
    assert first.lookup(principal.generation) == principal
    second = CredentialStore(tmp_path / "runtime", _id())
    assert second.lookup(principal.generation) is None
    assert "secret" not in repr(principal)
    with pytest.raises(CredentialError):
        first.remove_client(type(principal)("cli", principal.generation, "wrong"))
    first.remove_client(principal)
    assert first.lookup(principal.generation) is None


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX mode fixture; Windows ACLs have native tests"
)
def test_operator_credentials_reject_unsafe_file(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "runtime", _id())
    principal = store.provision_client("gui")
    path = store.generation_dir / f"{principal.generation}.json"
    path.chmod(0o644)
    with pytest.raises(CredentialError, match="owner-only"):
        store.lookup(principal.generation)
    path.chmod(0o600)
    alternate = tmp_path / "alternate.json"
    alternate.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(alternate)
    with pytest.raises(CredentialError, match="symlink"):
        store.lookup(principal.generation)
