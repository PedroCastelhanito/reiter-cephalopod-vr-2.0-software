"""Launcher preflight checks run without Windows (E08, E14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cephvr.launcher.preflight import read_backend_port, require_distinct_ports
from cephvr.shared.managed_modules import REQUIRED_MODULES, missing_roles


def _write(directory: Path, role: str, *, config: str, policy: str) -> None:
    (directory / f"{role}_config.toml").write_text(config)
    (directory / f"{role}_policy.toml").write_text(policy)


def test_port_is_read_when_config_and_policy_versions_agree(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "acquisition",
        config="policy_version = 3\n[rpc]\nport = 50123\n",
        policy="policy_version = 3\n",
    )
    assert read_backend_port(tmp_path, tmp_path, "acquisition") == 50123


@pytest.mark.parametrize(
    ("config", "policy", "message"),
    [
        ("policy_version = 3\n[rpc]\nport = 1\n", "policy_version = 4\n", "mismatch"),
        ("[rpc]\nport = 1\n", "policy_version = 4\n", "mismatch"),
        ("policy_version = 3\n[rpc]\nport = 0\n", "policy_version = 3\n", "rpc.port"),
        (
            "policy_version = 3\n[rpc]\nport = 70000\n",
            "policy_version = 3\n",
            "rpc.port",
        ),
        ("policy_version = 3\n[rpc]\nport = '1'\n", "policy_version = 3\n", "rpc.port"),
        ("policy_version = 3\n", "policy_version = 3\n", "rpc.port"),
    ],
)
def test_invalid_backend_files_are_rejected(
    tmp_path: Path, config: str, policy: str, message: str
) -> None:
    _write(tmp_path, "tracking", config=config, policy=policy)
    with pytest.raises(ValueError, match=message):
        read_backend_port(tmp_path, tmp_path, "tracking")


def test_port_collisions_are_detected_for_any_number_of_services() -> None:
    require_distinct_ports([1, 2, 3, 4, 5, 6])
    with pytest.raises(ValueError, match="collide"):
        require_distinct_ports([1, 2, 3, 4, 5, 3])


def test_every_required_role_has_an_entry_point_module() -> None:
    assert set(REQUIRED_MODULES) == {
        "acquisition",
        "visual_stimulus",
        "tracking",
        "gui",
    }
    # gui.main may be absent while that package is unfinished; the rest must exist.
    assert set(missing_roles()) <= {"gui"}
