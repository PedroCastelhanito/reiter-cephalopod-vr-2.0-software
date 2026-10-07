"""E14 policy integrity: one digest rule for every backend's fixed policy."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cephvr.acquisition.config import policy as acquisition_policy
from cephvr.shared.config import ConfigurationError, policy_digest
from cephvr.tracking.config import files as tracking_files
from cephvr.visual_stimulus import configuration as visual_stimulus_configuration

REPOSITORY = Path(__file__).resolve().parents[2]

LOADERS: dict[str, Callable[[Path], Any]] = {
    "acquisition": acquisition_policy._load_pair,
    "visual_stimulus": visual_stimulus_configuration._load_pair,
    "tracking": tracking_files.load_files,
}


def _root(tmp_path: Path, backend: str) -> Path:
    (tmp_path / "config/backends").mkdir(parents=True)
    (tmp_path / "contracts/policy").mkdir(parents=True)
    shutil.copyfile(
        REPOSITORY / f"config/backends/{backend}_config.toml",
        tmp_path / f"config/backends/{backend}_config.toml",
    )
    shutil.copyfile(
        REPOSITORY / f"contracts/policy/{backend}_policy.toml",
        tmp_path / f"contracts/policy/{backend}_policy.toml",
    )
    return tmp_path


def test_digest_ignores_key_order_and_the_policy_version() -> None:
    first = {"policy_version": 1, "a": {"x": 1, "y": 2}, "b": "s"}
    second = {"b": "s", "a": {"y": 2, "x": 1}, "policy_version": 99}
    assert policy_digest(first) == policy_digest(second)
    assert policy_digest(first) != policy_digest({**first, "b": "t"})


@pytest.mark.parametrize("backend", LOADERS)
def test_shipped_policy_matches_its_pinned_digest(tmp_path: Path, backend: str) -> None:
    assert LOADERS[backend](_root(tmp_path, backend)) is not None


@pytest.mark.parametrize("backend", LOADERS)
def test_comment_and_whitespace_edits_do_not_fail_startup(
    tmp_path: Path, backend: str
) -> None:
    root = _root(tmp_path, backend)
    path = root / f"contracts/policy/{backend}_policy.toml"
    path.write_text("# an operator note\n\n" + path.read_text() + "\n\n# trailing\n")
    assert LOADERS[backend](root) is not None


@pytest.mark.parametrize("backend", LOADERS)
def test_a_changed_policy_value_fails_startup(tmp_path: Path, backend: str) -> None:
    root = _root(tmp_path, backend)
    path = root / f"contracts/policy/{backend}_policy.toml"
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        key, separator, value = line.partition(" = ")
        if separator and value.isdecimal() and key != "policy_version":
            lines[index] = f"{key} = {int(value) + 1}"
            break
    else:  # pragma: no cover - every shipped policy has an integer
        pytest.fail("no integer policy value to change")
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ConfigurationError, match="differ"):
        LOADERS[backend](root)
