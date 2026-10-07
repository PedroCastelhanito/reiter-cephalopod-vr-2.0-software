"""Host-only SpikeGLX endpoint, budget, mapping and pulse inventory settings."""

from __future__ import annotations

import hashlib
import json
import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cephvr.synchronization.v1 import spikeglx_pb2 as wire

from .inventory import parse_inventory_bytes


@dataclass(frozen=True)
class HostSettings:
    address: str
    port: int
    native_call_timeout_s: float
    writing_start_timeout_s: float
    observation_interval_s: float
    no_progress_timeout_s: float
    stop_margin_s: float
    inventory: tuple[wire.PulseChannel, ...]
    mapping: Mapping[str, Any]
    file_sha256: str = ""


def load_host_settings(software_root: Path) -> HostSettings:
    path = software_root / "config/backends/synchronization_config.toml"
    raw = path.read_bytes()
    config = tomllib.loads(raw.decode("utf-8"))
    endpoint = config.get("spikeglx")
    monitor = config.get("monitor")
    if not isinstance(endpoint, dict) or not isinstance(monitor, dict):
        raise ValueError("SpikeGLX endpoint and monitor settings are required")
    address, port = endpoint.get("address"), endpoint.get("port")
    if (
        not isinstance(address, str)
        or not address.strip()
        or type(port) is not int
        or not 1 <= port <= 65535
    ):
        raise ValueError("SpikeGLX command-server endpoint is invalid")
    values = {}
    for name in (
        "native_call_timeout_s",
        "writing_start_timeout_s",
        "observation_interval_s",
        "no_progress_timeout_s",
        "stop_margin_s",
    ):
        value = monitor.get(name)
        if type(value) not in (int, float):
            raise ValueError(f"SpikeGLX monitor setting {name} is invalid")
        numeric = cast(int | float, value)
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError(f"SpikeGLX monitor setting {name} is invalid")
        values[name] = float(numeric)
    if values["native_call_timeout_s"] <= 0 or values["writing_start_timeout_s"] <= 0:
        raise ValueError("SpikeGLX native and writing deadlines must be positive")
    if (
        values["observation_interval_s"] <= 0
        or values["no_progress_timeout_s"] <= values["observation_interval_s"]
    ):
        raise ValueError("SpikeGLX no-progress budget must exceed its poll interval")
    if not isinstance(config.get("pulse_inventory"), dict):
        raise ValueError("SpikeGLX pulse_inventory table is required")
    mapping_path = software_root / "contracts/spikeglx_mapping_reference.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if (
        mapping.get("schema_version") != 1
        or mapping.get("evidence_status") != "source_reviewed_not_rig_validated"
    ):
        raise ValueError("SpikeGLX source mapping reference is unsupported")
    _inventory_digest, inventory = parse_inventory_bytes(software_root, raw)
    return HostSettings(
        address.strip(),
        port,
        values["native_call_timeout_s"],
        values["writing_start_timeout_s"],
        values["observation_interval_s"],
        values["no_progress_timeout_s"],
        values["stop_margin_s"],
        inventory,
        mapping,
        hashlib.sha256(raw).hexdigest(),
    )
