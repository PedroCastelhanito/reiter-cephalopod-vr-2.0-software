"""Pure T19 JSON Lines helpers; no file I/O, sync, checksum or recovery scan.

One TrackingRecord serializes to one compact UTF-8 JSON line terminated by LF.
"""

from __future__ import annotations

from cephvr.tracking.config.models.records import TrackingRecord, parse_record


def encode_line(record: TrackingRecord, *, max_bytes: int) -> bytes:
    """Serialize once; max_bytes bounds the JSON text, excluding its LF."""
    if type(max_bytes) is not int or not 0 < max_bytes < 2**32:
        raise ValueError("invalid record limit")
    data = record.model_dump_json().encode("utf8")
    if len(data) > max_bytes:
        raise ValueError("record exceeds max_record_bytes")
    return data + b"\n"


def decode_lines(
    data: bytes, *, max_bytes: int
) -> tuple[tuple[TrackingRecord, ...], int]:
    """Parse every complete line; return records and the discarded incomplete-tail size.

    Only bytes after the last LF (a crash-truncated final line) are discarded. Any
    invalid complete line is an error, never skipped.
    """
    if not isinstance(data, bytes):
        raise TypeError("immutable bytes required")
    end = data.rfind(b"\n") + 1
    lines = data[:end].split(b"\n")[:-1]
    return tuple(
        parse_record(x.decode("utf8"), max_bytes=max_bytes) for x in lines
    ), len(data) - end
