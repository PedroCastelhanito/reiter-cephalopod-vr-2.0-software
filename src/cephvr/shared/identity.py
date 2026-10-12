"""Canonical E08 UUID identity validation."""

from __future__ import annotations

import uuid


def require_uuid4(value: str) -> str:
    """Require the exact lowercase, hyphenated UUIDv4 wire spelling."""
    if not isinstance(value, str):
        raise ValueError("identity must be a string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("invalid UUID") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("identity must be a canonical lowercase UUIDv4")
    return value
