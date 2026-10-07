"""Pure launcher preflight: backend ports and policy versions (E08, E14).

Kept free of Win32 calls so the checks run in portable tests; ``main`` owns the
containment loop.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from pathlib import Path


def _read(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def read_backend_port(config_dir: Path, policy_root: Path, role: str) -> int:
    """The backend's ``rpc.port`` once its config and policy versions agree."""
    config = _read(config_dir / f"{role}_config.toml")
    policy = _read(policy_root / f"{role}_policy.toml")
    version = config.get("policy_version")
    if type(version) is not int or version != policy.get("policy_version"):
        raise ValueError(f"{role} config/policy version mismatch")
    rpc = config.get("rpc")
    port = rpc.get("port") if isinstance(rpc, dict) else None
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError(f"{role} rpc.port must be an integer in 1..65535")
    return port


def require_distinct_ports(ports: Iterable[int]) -> None:
    collected = list(ports)
    if len(set(collected)) != len(collected):
        raise ValueError("backend/controller/supervisor service ports collide")
