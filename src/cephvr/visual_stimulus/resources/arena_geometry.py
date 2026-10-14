"""Bounded access to the legacy arena geometry declaration in GLB JSON extras."""

import json
import struct
from pathlib import Path
from typing import Any


def declared_geometry_json(document: dict[str, Any]) -> str | None:
    extras = document.get("extras", {})
    cephvr = extras.get("cephvr", {}) if isinstance(extras, dict) else {}
    metadata = cephvr.get("metadata", {}) if isinstance(cephvr, dict) else {}
    geometry = metadata.get("geometry") if isinstance(metadata, dict) else None
    return json.dumps(geometry) if isinstance(geometry, dict) else None


def read_geometry_preview(path: Path, *, max_document_bytes: int) -> str:
    """Read only the bounded JSON chunk; protected Setup performs full validation."""
    with path.open("rb") as stream:
        header = stream.read(20)
        if len(header) != 20:
            raise ValueError("Truncated arena GLB")
        magic, version, total, length, kind = struct.unpack("<4sIIII", header)
        if (
            magic != b"glTF"
            or version != 2
            or total != path.stat().st_size
            or kind != 0x4E4F534A
            or length % 4
            or length > total - 20
            or length > max_document_bytes
        ):
            raise ValueError("Invalid or oversized arena GLB JSON chunk")
        content = stream.read(length)
    if len(content) != length:
        raise ValueError("Truncated arena GLB JSON chunk")
    document = json.loads(content)
    geometry = declared_geometry_json(document) if isinstance(document, dict) else None
    if geometry is None:
        raise ValueError("No movement geometry declared in arena GLB")
    return geometry
