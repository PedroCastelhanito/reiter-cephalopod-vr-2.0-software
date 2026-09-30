"""Shared lexical validators and issue formatting for acquisition settings."""

from __future__ import annotations

import math
from decimal import Decimal

from cephvr.control.v1 import types_pb2


def valid_frequency(value: float) -> bool:
    return (
        math.isfinite(value) and value > 0 and Decimal(str(value)) % Decimal("0.1") == 0
    )


def firmware_token(value: str) -> bool:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return bool(value) and all(
        33 <= byte <= 126 and byte not in (44, 61) for byte in encoded
    )


def issue(
    result: types_pb2.ValidationResult, path: str, code: str, message: str
) -> None:
    item = result.issues.add(component="acquisition", field_path=path)
    item.failure.code = code
    item.failure.message = message
    result.valid = False
