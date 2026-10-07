"""Strict E14 operator/policy TOML pairing without runtime side effects."""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """A default or fixed-policy file cannot be used for Setup."""


@dataclass(frozen=True)
class LoadedPair:
    config: Mapping[str, Any]
    policy: Mapping[str, Any]
    policy_version: int


def policy_digest(policy: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical parsed policy, without ``policy_version`` (E14).

    Content changes fail startup; comment and whitespace edits do not.
    """
    content = {key: value for key, value in policy.items() if key != "policy_version"}
    encoded = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: (
            format(item, "f") if isinstance(item, Decimal) else str(item)
        ),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_toml(path: Path, *, max_file_bytes: int) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            raw = stream.read(max_file_bytes + 1)
    except OSError as exc:
        raise ConfigurationError(f"cannot read {path}: {exc}") from exc
    if len(raw) > max_file_bytes:
        raise ConfigurationError(f"{path} exceeds TOML byte limit")
    try:
        parsed = tomllib.loads(raw.decode("utf-8"), parse_float=Decimal)
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"invalid TOML in {path}: {exc}") from exc
    return parsed


def _leaf_paths(value: Mapping[str, Any], prefix: str = "") -> set[str]:
    result: set[str] = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            result.update(_leaf_paths(child, path))
        elif (
            isinstance(child, list)
            and child
            and all(isinstance(x, dict) for x in child)
        ):
            for item in child:
                result.update(_leaf_paths(item, f"{path}.*"))
        else:
            result.add(path)
    return result


def _empty_table_paths(value: Mapping[str, Any], prefix: str = "") -> set[str]:
    result: set[str] = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            if child:
                result.update(_empty_table_paths(child, path))
            else:
                result.add(path)
    return result


def _allowed_table(path: str, patterns: Collection[str]) -> bool:
    parts = path.split(".")
    return any(
        len(other := pattern.split(".")) > len(parts)
        and all(a == b or b == "*" for a, b in zip(parts, other, strict=False))
        for pattern in patterns
    )


def _allowed(path: str, patterns: Collection[str]) -> bool:
    parts = path.split(".")
    return any(
        len(other := pattern.split(".")) == len(parts)
        and all(a == b or b == "*" for a, b in zip(parts, other, strict=True))
        for pattern in patterns
    )


def load_pair(
    config_path: str | Path,
    policy_path: str | Path,
    *,
    allowed_config_keys: Collection[str],
    allowed_policy_keys: Collection[str],
    allowed_empty_tables: Collection[str] = (),
    expected_policy: Mapping[str, object] | None = None,
    max_file_bytes: int = 1_048_576,
) -> LoadedPair:
    """Load only recognized keys and matching policy versions.

    Allowed keys are dotted leaf paths; use ``*`` for one array-table segment.
    The caller supplies its owned schema and any implementation constants.
    """
    if max_file_bytes <= 0:
        raise ValueError("TOML byte limit must be positive")
    config = _read_toml(Path(config_path), max_file_bytes=max_file_bytes)
    policy = _read_toml(Path(policy_path), max_file_bytes=max_file_bytes)
    config_version = config.get("policy_version")
    policy_version = policy.get("policy_version")
    if type(config.get("format_version")) is not int or config["format_version"] != 1:
        raise ConfigurationError("unsupported or missing config format_version")
    if (
        type(config_version) is not int
        or type(policy_version) is not int
        or config_version <= 0
        or config_version != policy_version
    ):
        raise ConfigurationError("config/policy policy_version mismatch")
    config_keys = _leaf_paths(config)
    policy_keys = _leaf_paths(policy)
    unknown_config = config_keys - {"format_version", "policy_version"}
    unknown_policy = policy_keys - {"policy_version"}
    bad_config = sorted(
        p for p in unknown_config if not _allowed(p, allowed_config_keys)
    )
    bad_policy = sorted(
        p for p in unknown_policy if not _allowed(p, allowed_policy_keys)
    )
    bad_config.extend(
        sorted(
            p
            for p in _empty_table_paths(config)
            if not _allowed_table(p, allowed_config_keys)
            and p not in allowed_empty_tables
        )
    )
    bad_policy.extend(
        sorted(
            p
            for p in _empty_table_paths(policy)
            if not _allowed_table(p, allowed_policy_keys)
        )
    )
    if bad_config or bad_policy:
        raise ConfigurationError(
            f"unknown config keys {bad_config}; unknown policy keys {bad_policy}"
        )
    if expected_policy is not None:
        for path, expected in expected_policy.items():
            value: Any = policy
            try:
                for segment in path.split("."):
                    value = value[segment]
            except (KeyError, TypeError) as exc:
                raise ConfigurationError(f"missing fixed policy {path}") from exc
            comparable = (
                Decimal(str(expected)) if isinstance(expected, float) else expected
            )
            if type(value) is not type(comparable) or value != comparable:
                raise ConfigurationError(
                    f"fixed policy {path} differs from implementation"
                )
    return LoadedPair(config, policy, policy_version)
