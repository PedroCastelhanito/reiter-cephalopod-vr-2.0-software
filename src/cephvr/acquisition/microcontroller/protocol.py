"""Strict bounded ASCII protocol-v1 parsing for the pulse microcontroller (A11)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_LINE_BYTES = 512
PROTOCOL_VERSION = 1
FREQUENCY_STEP = Decimal("0.1")
_TOKEN = re.compile(r"^[!-~]+$")
_UINT = re.compile(r"^[0-9]+$")
_FREQUENCY = re.compile(r"^[0-9]+\.[0-9]$")
_APPLIED_FREQUENCY = re.compile(
    r"^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
ROLES = ("behavioral", "tracking")


class ProtocolError(ValueError):
    """The complete serial line is malformed or incompatible with protocol v1."""


@dataclass(frozen=True)
class Reply:
    ok: bool
    request_id: str | None
    fields: dict[str, str]
    error_code: str | None = None


def request_line(
    command: str, request_id: str, fields: dict[str, str] | None = None
) -> bytes:
    if not _token(request_id) or not _token(command):
        raise ProtocolError("command and request ID must be printable ASCII tokens")
    pieces = [command, f"id={request_id}"]
    for key, value in (fields or {}).items():
        if not _token(key) or not _token(value) or "=" in key or "," in value:
            raise ProtocolError("request field is not a safe protocol token")
        pieces.append(f"{key}={value}")
    encoded = (" ".join(pieces) + "\n").encode("ascii")
    if len(encoded) > MAX_LINE_BYTES:
        raise ProtocolError("request exceeds the 512-byte line limit")
    return encoded


def parse_reply(line: bytes) -> Reply:
    if len(line) > MAX_LINE_BYTES:
        raise ProtocolError("reply exceeds the 512-byte line limit")
    if not line.endswith(b"\n"):
        raise ProtocolError("reply is not LF terminated")
    content = line[:-1]
    if content.endswith(b"\r"):
        content = content[:-1]
    try:
        text = content.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("reply contains non-ASCII bytes") from exc
    if not text or "\t" in text or text.startswith(" ") or text.endswith(" "):
        raise ProtocolError("reply has invalid whitespace")
    parts = re.split(r" +", text)
    if parts[0] not in ("OK", "ERR"):
        raise ProtocolError("reply must begin with OK or ERR")
    fields: dict[str, str] = {}
    for item in parts[1:]:
        if item.count("=") != 1:
            raise ProtocolError("reply field must be one key=value token")
        key, value = item.split("=", 1)
        if not _token(key) or not _field_token(value) or "," in key:
            raise ProtocolError("reply contains an invalid token")
        if key in fields:
            raise ProtocolError(f"reply duplicates field {key}")
        fields[key] = value
    request_id = fields.pop("id", None)
    if request_id is not None and not _token(request_id):
        raise ProtocolError("reply ID is malformed")
    ok = parts[0] == "OK"
    if ok:
        if request_id is None or "code" in fields:
            raise ProtocolError(
                "success reply requires id and cannot contain error code"
            )
        return Reply(True, request_id, fields)
    code = fields.pop("code", None)
    if code is None or not re.fullmatch(r"[A-Z][A-Z0-9_]*", code):
        raise ProtocolError("error reply requires a symbolic uppercase code")
    return Reply(False, request_id, fields, code)


def parse_capabilities(
    reply: Reply,
) -> tuple[int, str, tuple[str, ...], float, float, int, int]:
    _require_ok(
        reply,
        {
            "protocol",
            "firmware",
            "pins",
            "min_hz",
            "max_hz",
            "watchdog_min_ms",
            "watchdog_max_ms",
        },
    )
    version = _uint(reply.fields["protocol"], 32, "protocol")
    firmware = _required_token(reply.fields["firmware"], "firmware")
    pins_text = reply.fields["pins"]
    pins = tuple(pins_text.split(","))
    if (
        not pins_text
        or any(not _token(pin) for pin in pins)
        or len(set(pins)) != len(pins)
    ):
        raise ProtocolError("CAPS pins must be a unique comma-separated token list")
    minimum = _request_frequency(reply.fields["min_hz"], "min_hz")
    maximum = _request_frequency(reply.fields["max_hz"], "max_hz")
    watchdog_min = _uint(reply.fields["watchdog_min_ms"], 32, "watchdog_min_ms")
    watchdog_max = _uint(reply.fields["watchdog_max_ms"], 32, "watchdog_max_ms")
    if minimum > maximum or watchdog_min > watchdog_max:
        raise ProtocolError("CAPS minimum exceeds maximum")
    return version, firmware, pins, minimum, maximum, watchdog_min, watchdog_max


def parse_state(reply: Reply, *, configured: bool) -> dict[str, object]:
    required = {"valid", "watchdog_stopped", "watchdog_ms"}
    for role in ROLES:
        required.update({f"{role}_enabled", f"{role}_running"})
    _require_ok(reply, required, allow_optional_role_fields=True)
    values: dict[str, object] = {
        "valid": _bool(reply.fields["valid"], "valid"),
        "watchdog_stopped": _bool(reply.fields["watchdog_stopped"], "watchdog_stopped"),
        "watchdog_ms": _uint(reply.fields["watchdog_ms"], 32, "watchdog_ms"),
        "outputs": {},
    }
    outputs: dict[str, dict[str, object]] = {}
    for role in ROLES:
        enabled = _bool(reply.fields[f"{role}_enabled"], f"{role}_enabled")
        running = _bool(reply.fields[f"{role}_running"], f"{role}_running")
        pin_key, rate_key = f"{role}_pin", f"{role}_applied_hz"
        if enabled:
            if pin_key not in reply.fields or rate_key not in reply.fields:
                raise ProtocolError(
                    f"enabled {role} output requires pin and applied frequency"
                )
            pin = _required_token(reply.fields[pin_key], pin_key)
            applied = _applied_frequency(reply.fields[rate_key], rate_key)
            outputs[role] = {
                "enabled": True,
                "running": running,
                "pin": pin,
                "frequency": applied,
            }
        else:
            if running or pin_key in reply.fields or rate_key in reply.fields:
                raise ProtocolError(
                    f"disabled {role} output must be stopped and omit pin/frequency"
                )
            outputs[role] = {"enabled": False, "running": False}
    values["outputs"] = outputs
    if configured and not values["valid"]:
        raise ProtocolError("firmware reports invalid pulse configuration")
    if values["watchdog_stopped"] and any(item["running"] for item in outputs.values()):
        raise ProtocolError("firmware reports running output after watchdog stop")
    return values


def parse_compact_state(reply: Reply) -> dict[str, bool]:
    expected = {f"{role}_running" for role in ROLES} | {"watchdog_stopped"}
    _require_ok(reply, expected)
    return {key: _bool(reply.fields[key], key) for key in expected}


def frequency_text(value: float) -> str:
    if not math.isfinite(value) or value <= 0:
        raise ProtocolError("requested frequency must be finite and positive")
    decimal = Decimal(str(value))
    if decimal % FREQUENCY_STEP:
        raise ProtocolError("requested frequency must use the exact 0.1 Hz grid")
    return f"{decimal:.1f}"


def _require_ok(
    reply: Reply, required: set[str], *, allow_optional_role_fields: bool = False
) -> None:
    if not reply.ok:
        raise FirmwareRejected(reply.error_code or "UNKNOWN_ERROR")
    allowed = set(required)
    if allow_optional_role_fields:
        allowed.update(
            f"{role}_{suffix}" for role in ROLES for suffix in ("pin", "applied_hz")
        )
    unknown = reply.fields.keys() - allowed
    missing = required - reply.fields.keys()
    if unknown or missing:
        raise ProtocolError(
            f"reply fields differ from protocol v1; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )


def _bool(value: str, name: str) -> bool:
    if value not in ("0", "1"):
        raise ProtocolError(f"{name} must be 0 or 1")
    return value == "1"


def _uint(value: str, bits: int, name: str) -> int:
    if not _UINT.fullmatch(value):
        raise ProtocolError(f"{name} must be an unsigned base-10 integer")
    parsed = int(value)
    if parsed >= 1 << bits:
        raise ProtocolError(f"{name} exceeds uint{bits}")
    return parsed


def _request_frequency(value: str, name: str) -> float:
    if not _FREQUENCY.fullmatch(value):
        raise ProtocolError(f"{name} must use one decimal digit")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ProtocolError(f"{name} is not a decimal frequency") from exc
    if not parsed.is_finite() or parsed <= 0 or parsed % FREQUENCY_STEP:
        raise ProtocolError(f"{name} must be positive and use 0.1 Hz steps")
    return float(parsed)


def _applied_frequency(value: str, name: str) -> float:
    if not _APPLIED_FREQUENCY.fullmatch(value):
        raise ProtocolError(f"{name} is not a decimal frequency")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ProtocolError(f"{name} is not a binary64 frequency") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ProtocolError(f"{name} must be finite and positive")
    return parsed


def _token(value: str) -> bool:
    return bool(
        value and _TOKEN.fullmatch(value) and "=" not in value and "," not in value
    )


def _field_token(value: str) -> bool:
    return bool(value and _TOKEN.fullmatch(value) and "=" not in value)


def _required_token(value: str, name: str) -> str:
    if not _token(value):
        raise ProtocolError(f"{name} must be a printable token")
    return value


class FirmwareRejected(RuntimeError):
    """A matched ERR response; it is evidence of rejection, not transport success."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
