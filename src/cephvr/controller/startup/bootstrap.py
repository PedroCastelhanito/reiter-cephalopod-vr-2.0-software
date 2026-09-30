"""Protected bootstrap descriptor validation."""

from __future__ import annotations

from collections.abc import Mapping

from cephvr.controller.backend import BackendRegistration


def _bootstrap_value(bootstrap: Mapping[str, object], key: str, kind: type) -> object:
    value = bootstrap.get(key)
    if type(value) is not kind:
        raise ValueError(f"bootstrap {key} has invalid type")
    return value


def _backend_descriptors(bootstrap: Mapping[str, object]) -> list[BackendRegistration]:
    raw = bootstrap.get("backends", [])
    if not isinstance(raw, list):
        raise ValueError("bootstrap backend registry is not a list")
    result: list[BackendRegistration] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "backend_name",
            "backend_generation",
            "endpoint",
            "token",
            "launch_confirmed",
        }:
            raise ValueError("bootstrap backend registry entry differs from schema")
        if item["launch_confirmed"] is not False or any(
            not isinstance(item[key], str)
            for key in ("backend_name", "backend_generation", "endpoint", "token")
        ):
            raise ValueError("backend bootstrap cannot claim launch completion")
        registration = BackendRegistration(
            item["backend_name"],
            item["backend_generation"],
            item["endpoint"],
            item["token"],
        )
        if registration.backend_name in seen:
            raise ValueError("duplicate backend bootstrap role")
        seen.add(registration.backend_name)
        result.append(registration)
    return result
