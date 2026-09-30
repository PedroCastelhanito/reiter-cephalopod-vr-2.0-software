"""Protected gRPC metadata binding for original absolute operation deadlines."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from cephvr.shared.clock import host_time_ns, require_int64_ns

DEADLINE_METADATA_KEY = "x-cephvr-deadline-ns"


class DeadlineMetadataError(ValueError):
    """An RPC deadline metadata value is absent, duplicated or malformed."""


def deadline_metadata(deadline_ns: int) -> tuple[str, str]:
    """Return one protected metadata pair for an absolute system-wide deadline."""
    require_int64_ns(deadline_ns)
    if deadline_ns <= 0:
        raise DeadlineMetadataError("deadline must be a positive absolute timestamp")
    return DEADLINE_METADATA_KEY, str(deadline_ns)


def parse_deadline_metadata(
    metadata: Iterable[tuple[str, str | bytes]],
) -> int:
    """Parse exactly one original deadline value from authenticated metadata."""
    matches = [value for key, value in metadata if key.lower() == DEADLINE_METADATA_KEY]
    if len(matches) != 1:
        raise DeadlineMetadataError("exactly one authenticated deadline is required")
    value = matches[0]
    try:
        text = value.decode("ascii") if isinstance(value, bytes) else value
        if not text or not text.isdecimal():
            raise ValueError("deadline must use unsigned decimal digits")
        deadline_ns = int(text)
        require_int64_ns(deadline_ns)
        if deadline_ns <= 0:
            raise ValueError("deadline must be positive")
        return deadline_ns
    except (UnicodeDecodeError, ValueError) as exc:
        raise DeadlineMetadataError("deadline metadata is malformed") from exc


def remaining_ns(deadline_ns: int, *, clock: Callable[[], int] = host_time_ns) -> int:
    require_int64_ns(deadline_ns)
    return max(0, deadline_ns - clock())


def remaining_seconds(
    deadline_ns: int, *, clock: Callable[[], int] = host_time_ns
) -> float:
    return remaining_ns(deadline_ns, clock=clock) / 1_000_000_000
