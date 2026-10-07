"""Atomic, comment-preserving edits for the file-owned pulse inventory only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path

from cephvr.synchronization.channel_mapping import supported_digital_bits
from cephvr.synchronization.v1 import spikeglx_pb2 as wire

_ROLES = {
    wire.PULSE_ROLE_BEHAVIORAL_CAMERA: "behavioral_camera",
    wire.PULSE_ROLE_TRACKING_CAMERA: "tracking_camera",
    wire.PULSE_ROLE_PHOTODIODE: "photodiode",
}
_STREAMS = {
    wire.STREAM_FAMILY_NI: "ni",
    wire.STREAM_FAMILY_ONEBOX: "onebox",
    wire.STREAM_FAMILY_IMEC: "imec",
}
_SUPPLEMENTAL_KEYS = {
    wire.PULSE_ROLE_TRIAL_STATE: "trial_state",
    wire.PULSE_ROLE_PROJECTOR_FLIP: "projector_flip",
}
_INVENTORY_KEY_PATTERN = re.compile(
    r"^(?:behavioral_camera|tracking_camera|photodiode|trial_state|projector_flip|custom_[A-Za-z0-9_-]{1,80})$"
)


def _toml_path(software_root: Path) -> Path:
    return software_root / "config/backends/synchronization_config.toml"


def _mapping(software_root: Path) -> Mapping[str, object]:
    mapping = json.loads(
        (software_root / "contracts/spikeglx_mapping_reference.json").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(mapping, dict):
        raise ValueError("SpikeGLX mapping reference must be an object")
    return mapping


def _parse(
    path: Path, raw: bytes, mapping: Mapping[str, object]
) -> tuple[str, tuple[wire.PulseChannel, ...]]:
    document = tomllib.loads(raw.decode("utf-8"))
    section = document.get("pulse_inventory")
    if not isinstance(section, dict):
        raise ValueError("synchronization config has no pulse_inventory table")
    channels = []
    occupied: set[tuple[int, int, int, int | None]] = set()
    seen_roles: set[tuple[int, str]] = set()
    for key, item in section.items():
        if not isinstance(item, dict):
            raise ValueError(f"pulse_inventory.{key} must be a table")
        if key in _ROLES.values():
            role = next(role for role, role_key in _ROLES.items() if role_key == key)
            if "source_id" in item:
                raise ValueError(f"pulse_inventory.{key}.source_id is unsupported")
            source_id = ""
        elif key == "trial_state":
            if "source_id" in item:
                raise ValueError(f"pulse_inventory.{key}.source_id is unsupported")
            role, source_id = wire.PULSE_ROLE_TRIAL_STATE, ""
        elif key == "projector_flip":
            if "source_id" in item:
                raise ValueError(f"pulse_inventory.{key}.source_id is unsupported")
            role, source_id = wire.PULSE_ROLE_PROJECTOR_FLIP, ""
        elif key.startswith("custom_"):
            role = wire.PULSE_ROLE_CUSTOM
            source_id = item.get("source_id", "")
            suffix = key.removeprefix("custom_")
            if (
                not isinstance(source_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id)
                or source_id != suffix
            ):
                raise ValueError(f"pulse_inventory.{key}.source_id is invalid")
        else:
            raise ValueError(f"pulse_inventory.{key} has an unsupported source role")
        role_identity = (role, source_id)
        if role_identity in seen_roles:
            raise ValueError("pulse inventory repeats a source identity")
        seen_roles.add(role_identity)
        stream = item.get("stream")
        family = next(
            (number for number, name in _STREAMS.items() if name == stream), None
        )
        stream_index, channel_index = item.get("stream_index"), item.get("channel")
        bit = item.get("bit")
        if family is None:
            raise ValueError(f"pulse_inventory.{key}.stream is invalid")
        if (
            key in {"behavioral_camera", "tracking_camera"}
            and family != wire.STREAM_FAMILY_ONEBOX
        ):
            raise ValueError(f"pulse_inventory.{key} must use a OneBox stream")
        if type(stream_index) is not int or stream_index < 0:
            raise ValueError(f"pulse_inventory.{key}.stream_index is invalid")
        if type(channel_index) is not int or channel_index < 0:
            raise ValueError(f"pulse_inventory.{key}.channel is invalid")
        family_name = _STREAMS[family]
        if bit is not None and (
            type(bit) is not int
            or bit not in supported_digital_bits(mapping, family_name)
        ):
            raise ValueError(
                f"pulse_inventory.{key}.bit is outside its mapped digital word"
            )
        identity = (family, stream_index, channel_index, bit)
        if identity in occupied:
            raise ValueError("pulse_inventory cannot assign one saved line twice")
        occupied.add(identity)
        channel = wire.PulseChannel(
            role=role,
            family=family,
            stream_index=stream_index,
            channel_index=channel_index,
        )
        if bit is not None:
            channel.bit = bit
        if source_id:
            channel.source_id = source_id
        channels.append(channel)
    return hashlib.sha256(raw).hexdigest(), tuple(channels)


def read_inventory(software_root: Path) -> tuple[str, tuple[wire.PulseChannel, ...]]:
    path = _toml_path(software_root)
    raw = path.read_bytes()
    return parse_inventory_bytes(software_root, raw)


def parse_inventory_bytes(
    software_root: Path, raw: bytes
) -> tuple[str, tuple[wire.PulseChannel, ...]]:
    """Parse one exact TOML byte snapshot against its installed source mapping."""
    return _parse(_toml_path(software_root), raw, _mapping(software_root))


def _validate_channels(
    channels: tuple[wire.PulseChannel, ...],
    mapping: Mapping[str, object],
    *,
    required_roles: frozenset[int] = frozenset(),
) -> dict[str, str]:
    lines: dict[str, str] = {}
    identities = set()
    role_ids = set()
    for item in channels:
        key = _ROLES.get(item.role)
        stream = _STREAMS.get(item.family)
        if key is None:
            key = _SUPPLEMENTAL_KEYS.get(item.role)
        if item.role == wire.PULSE_ROLE_CUSTOM:
            source_id = item.source_id if item.HasField("source_id") else ""
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
                raise ValueError("custom pulse source requires a stable source_id")
            key = f"custom_{source_id}"
        else:
            source_id = ""
        if key is None or stream is None:
            raise ValueError("pulse inventory contains an unsupported role or stream")
        role_identity = (item.role, source_id)
        if role_identity in role_ids:
            raise ValueError("pulse inventory repeats a source identity")
        role_ids.add(role_identity)
        if (
            key in {"behavioral_camera", "tracking_camera"}
            and item.family != wire.STREAM_FAMILY_ONEBOX
        ):
            raise ValueError(f"{key} must use a OneBox stream")
        if item.channel_index < 0 or item.stream_index < 0:
            raise ValueError("pulse stream and channel indices must be nonnegative")
        if item.HasField("bit") and item.bit not in supported_digital_bits(
            mapping, stream
        ):
            raise ValueError("pulse bit is outside its source-mapped digital word")
        bit = item.bit if item.HasField("bit") else None
        identity = (item.family, item.stream_index, item.channel_index, bit)
        if identity in identities:
            raise ValueError("pulse inventory cannot assign one saved line twice")
        identities.add(identity)
        fields = [
            f'stream = "{stream}"',
            f"stream_index = {item.stream_index}",
            f"channel = {item.channel_index}",
        ]
        if bit is not None:
            fields.append(f"bit = {bit}")
        if source_id:
            fields.append(f'source_id = "{source_id}"')
        lines[key] = f"{key} = {{ " + ", ".join(fields) + " }"
    present_roles = {item.role for item in channels}
    if not required_roles <= present_roles:
        missing = sorted(
            wire.PulseRole.Name(role) for role in required_roles - present_roles
        )
        raise ValueError(f"pulse inventory omits required active roles: {missing}")
    return lines


def _patch_text(text: str, values: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^\s*\[pulse_inventory\]\s*(?:#.*)?$", line.rstrip("\r\n"))
        ),
        None,
    )
    if start is None:
        raise ValueError("synchronization config has no pulse_inventory table")
    end = len(lines)
    nested: dict[str, tuple[int, int]] = {}
    for index in range(start + 1, len(lines)):
        header = re.match(r"^\s*\[([^]]+)\]", lines[index])
        if not header:
            continue
        name = header.group(1)
        if name.startswith("pulse_inventory."):
            key = name.removeprefix("pulse_inventory.")
            section_end = next(
                (
                    candidate
                    for candidate in range(index + 1, len(lines))
                    if re.match(r"^\s*\[", lines[candidate])
                ),
                len(lines),
            )
            nested[key] = (index, section_end)
            continue
        end = index
        break
    root_end = min((first for first, _last in nested.values()), default=end)
    existing = set()
    replacements: list[tuple[int, int, str]] = []
    for index in range(start + 1, root_end):
        match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", lines[index])
        if match and _INVENTORY_KEY_PATTERN.fullmatch(match.group(1)):
            key = match.group(1)
            if key not in values:
                replacements.append((index, index, ""))
                continue
            value_start = match.end()
            value_end = _inline_table_end(lines, index, value_start)
            newline = (
                "\r\n"
                if any(line.endswith("\r\n") for line in lines[index : value_end + 1])
                else "\n"
            )
            replacements.append((index, value_end, values[key] + newline))
            existing.add(key)
    for key, (first, section_end) in nested.items():
        if key not in values:
            retained = [
                line
                for line in lines[first + 1 : section_end]
                if line.lstrip().startswith("#") or not line.strip()
            ]
            replacements.append((first, section_end - 1, "".join(retained)))
            continue
        assignment = tomllib.loads(f"entry = {values[key].split('=', 1)[1]}")["entry"]
        if not isinstance(assignment, dict):
            raise ValueError("pulse inventory update is not a TOML table")
        section_lines = list(lines[first + 1 : section_end])
        newline = "\r\n" if lines[first].endswith("\r\n") else "\n"
        present = set()
        for offset, line in enumerate(section_lines):
            field = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line)
            if field:
                name = field.group(1)
                if name in {"bit", "source_id"} and name not in assignment:
                    section_lines[offset] = ""
                elif name in assignment:
                    section_lines[offset] = (
                        f"{name} = {_toml_value(assignment[name])}{newline}"
                    )
                    present.add(name)
        missing_fields = [
            f"{name} = {_toml_value(value)}{newline}"
            for name, value in assignment.items()
            if name not in present
        ]
        section_lines.extend(missing_fields)
        replacements.append((first + 1, section_end - 1, "".join(section_lines)))
        existing.add(key)
    for first, last, replacement in reversed(replacements):
        lines[first : last + 1] = [replacement] if replacement else []
    missing = [value for key, value in values.items() if key not in existing]
    if missing:
        # Recompute after deletions/replacements: the original root_end can now
        # point into a later table or beyond the shortened document.
        current_start = next(
            index
            for index, line in enumerate(lines)
            if re.match(r"^\s*\[pulse_inventory\]\s*(?:#.*)?$", line.rstrip("\r\n"))
        )
        insert_at = len(lines)
        for index in range(current_start + 1, len(lines)):
            if re.match(r"^\s*\[", lines[index]):
                insert_at = index
                break
        if insert_at and not lines[insert_at - 1].endswith(("\n", "\r")):
            lines[insert_at - 1] += "\n"
        lines[insert_at:insert_at] = [value + "\n" for value in missing]
    return "".join(lines)


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if type(value) in {int, float, bool}:
        return str(value).lower() if isinstance(value, bool) else str(value)
    raise ValueError("unsupported pulse inventory TOML value")


def _inline_table_end(lines: list[str], line_index: int, value_start: int) -> int:
    """Find a possibly multiline inline table's closing line, ignoring strings/comments."""
    depth = 0
    in_string = False
    escaped = False
    for current in range(line_index, len(lines)):
        line = lines[current]
        offset = value_start if current == line_index else 0
        for character in line[offset:]:
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == "#":
                break
            if character == '"':
                in_string = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return current
    return line_index


def update_inventory(
    software_root: Path,
    *,
    expected_file_sha256: str,
    pulse_channels: tuple[wire.PulseChannel, ...],
    required_roles: frozenset[int] = frozenset(),
) -> str:
    path = _toml_path(software_root)
    current = path.read_bytes()
    mapping = _mapping(software_root)
    digest, _ = _parse(path, current, mapping)
    if digest != expected_file_sha256:
        raise ValueError("synchronization config changed since inventory was read")
    lines = _validate_channels(pulse_channels, mapping, required_roles=required_roles)
    original_document = tomllib.loads(current.decode("utf-8"))
    original_unrelated = {
        key: value
        for key, value in original_document.items()
        if key != "pulse_inventory"
    }
    patched = _patch_text(current.decode("utf-8"), lines)
    parsed = tomllib.loads(patched)
    if not isinstance(parsed.get("pulse_inventory"), dict):
        raise ValueError("pulse inventory table is invalid after update")
    if {
        key: value for key, value in parsed.items() if key != "pulse_inventory"
    } != original_unrelated:
        raise ValueError("pulse inventory update changed unrelated TOML values")
    _, actual_channels = _parse(path, patched.encode("utf-8"), mapping)
    expected_channels = tuple(pulse_channels)
    if sorted(
        item.SerializeToString(deterministic=True) for item in actual_channels
    ) != sorted(
        item.SerializeToString(deterministic=True) for item in expected_channels
    ):
        raise ValueError("pulse inventory update did not preserve the exact proposal")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(patched.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_file_sha256:
            raise ValueError("synchronization config changed before inventory commit")
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        temporary.unlink(missing_ok=True)
