"""Host identity, deadlines, authentication, configuration and ingress bounds."""

from __future__ import annotations

import sys
import uuid
from fractions import Fraction
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
from cephvr.shared.config import ConfigurationError, load_pair
from cephvr.shared.credentials import (
    CredentialError,
    CredentialStore,
    default_runtime_root,
)
from cephvr.shared.deadlines import (
    Deadline,
    duration_ns,
    remaining_seconds,
)
from cephvr.shared.deadlines import (
    remaining_ns as deadline_remaining_ns,
)
from cephvr.shared.identity import require_uuid4
from cephvr.shared.ingress import BoundedEventIngress, IngressOverload
from cephvr.shared.nominal_video_grid import NominalVideoGrid
from cephvr.shared.transport_deadlines import (
    DeadlineMetadataError,
    deadline_metadata,
    parse_deadline_metadata,
)
from cephvr.shared.transport_deadlines import (
    remaining_ns as transport_remaining_ns,
)
from cephvr.shared.transport_deadlines import (
    remaining_seconds as transport_remaining_seconds,
)


def _id() -> str:
    return str(uuid.uuid4())


def test_nominal_video_grid_uses_half_open_rational_slots_and_ceil_cutoff() -> None:
    grid = NominalVideoGrid(10_000_000_000, Fraction(30_000, 1_001))
    first_boundary = grid.start_ns + (1_001_000_000 + 29) // 30
    assert grid.slot_for(grid.start_ns) == 0
    assert grid.slot_for(first_boundary - 1) == 0
    assert grid.slot_for(first_boundary) == 1
    assert grid.slots_before(grid.start_ns) == 0
    assert grid.slots_before(first_boundary - 1) == 1
    assert grid.slots_before(first_boundary) == 2
    assert grid.slots_before(first_boundary + 1) == 2
    integral_grid = NominalVideoGrid(0, Fraction(25, 1))
    assert integral_grid.slots_before(40_000_000) == 1


@pytest.mark.parametrize("rate", [0, -1, float("inf"), float("nan")])
def test_nominal_video_grid_rejects_nonpositive_or_nonfinite_rate(rate: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        NominalVideoGrid(0, rate)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="native Windows credential ACLs")
def test_windows_runtime_namespace_does_not_touch_legacy_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = tmp_path / "CephVR" / "runtime" / "controller"
    legacy.mkdir(parents=True)
    log = legacy / "controller.log"
    log.write_text("legacy log", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    root = default_runtime_root()
    assert root == tmp_path / "CephVR2" / "runtime"
    store = CredentialStore(root, _id())
    principal = store.provision_client("cli")
    assert store.lookup(principal.generation) == principal
    assert log.read_text(encoding="utf-8") == "legacy log"
    with log.open("a", encoding="utf-8") as stream:
        stream.write("\nstill writable")


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


def test_deadline_metadata_requires_one_positive_int64_decimal_value() -> None:
    encoded = deadline_metadata(1_000_000_000)
    assert parse_deadline_metadata((encoded,)) == 1_000_000_000
    assert transport_remaining_ns(15, clock=lambda: 10) == 5
    with pytest.raises(DeadlineMetadataError):
        parse_deadline_metadata((encoded, encoded))
    with pytest.raises(DeadlineMetadataError):
        parse_deadline_metadata((("x-cephvr-deadline-ns", "+10"),))
    with pytest.raises(DeadlineMetadataError):
        parse_deadline_metadata((("x-cephvr-deadline-ns", str(1 << 63)),))


def test_remaining_deadline_helpers_preserve_clamping_and_transport_validation() -> (
    None
):
    samples: list[int] = []

    def clock() -> int:
        samples.append(10)
        return 10

    assert remaining_seconds(15, clock=clock) == 5 / 1_000_000_000
    assert samples == [10]
    assert remaining_seconds(10, clock=lambda: 10) == 0.0
    assert remaining_seconds(9, clock=lambda: 10) == 0.0
    assert remaining_seconds(10**30, clock=lambda: 0) == 10**21
    assert deadline_remaining_ns(15, clock=lambda: 10) == 5
    assert transport_remaining_seconds(15, clock=lambda: 10) == 5 / 1_000_000_000
    assert transport_remaining_ns(15, clock=lambda: 10) == 5
    with pytest.raises(ValueError, match="signed int64"):
        transport_remaining_seconds(10**30, clock=lambda: 0)
    assert remaining_seconds(-1, clock=lambda: 0) == 0.0
    with pytest.raises(ValueError, match="signed int64"):
        transport_remaining_seconds(-1, clock=lambda: 0)
    with pytest.raises(ValueError, match="signed int64"):
        Deadline(100).remaining_ns(now_ns=-1)


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


def test_removing_a_credential_a_concurrent_remover_already_deleted_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CredentialStore(tmp_path / "runtime", _id())
    principal = store.provision_client("cli")
    real_unlink = Path.unlink

    def raced(self: Path, *args: object, **kwargs: object) -> None:
        real_unlink(self)
        raise FileNotFoundError(str(self))

    monkeypatch.setattr(Path, "unlink", raced)
    store.remove_client(principal)
    monkeypatch.undo()
    assert store.lookup(principal.generation) is None


def test_managed_gui_credential_uses_exact_process_generation(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "runtime", _id())
    generation = _id()
    principal = store.provision_client(
        "gui", generation=generation, token="launch-token"
    )
    assert principal.generation == generation
    assert store.lookup(generation) == principal
    with pytest.raises(CredentialError, match="already exists"):
        store.provision_client("gui", generation=generation, token="different-token")
    with pytest.raises(CredentialError, match="only a managed GUI"):
        store.provision_client("cli", generation=_id(), token="launch-token")
    store.remove_client(principal)
    assert store.lookup(generation) is None
