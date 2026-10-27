"""Pipe protocol between the renderer and its sparse-noise generator helper (V04).

stdin: one ``JOB <json>`` line, then ``CREDIT <n>`` lines allowing requests with
sequence < n; EOF stops the helper. stdout: per request, a fixed header (with the
SHA-256 of the pattern's generated cells) then its RGBA8 texels. The helper never
reads files or the display.
"""

from __future__ import annotations

import json
import struct
from typing import Any

from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoisePatternRecipe

from .sparse_noise import SparseNoiseGrid
from .sparse_noise_stream import SparseLayer

FRAME = struct.Struct("<4sQI32s")
MAGIC = b"SPN2"
MAX_JOB_BYTES = 64 * 1024 * 1024


def encode_job(layers: tuple[SparseLayer, ...]) -> bytes:
    body = [
        {
            "epoch_index": layer.epoch_index,
            "instance_id": layer.instance_id,
            "start_ns": layer.start_ns,
            "pattern_duration_ns": layer.pattern_duration_ns,
            "shown": layer.shown,
            "recipe": layer.recipe.model_dump(mode="json"),
            "grid": [
                layer.grid.surface_id,
                layer.grid.columns,
                layer.grid.rows,
                layer.grid.width_mm,
                layer.grid.height_mm,
            ],
        }
        for layer in layers
    ]
    line = b"JOB " + json.dumps(body, separators=(",", ":")).encode("ascii") + b"\n"
    if len(line) > MAX_JOB_BYTES:
        raise ValueError("sparse-noise job exceeds its pipe bound")
    return line


def decode_job(line: bytes) -> tuple[SparseLayer, ...]:
    if len(line) > MAX_JOB_BYTES or not line.startswith(b"JOB "):
        raise ValueError("sparse-noise helper expected a JOB line")
    items: list[dict[str, Any]] = json.loads(line[4:])
    return tuple(
        SparseLayer(
            int(item["epoch_index"]),
            str(item["instance_id"]),
            int(item["start_ns"]),
            int(item["pattern_duration_ns"]),
            int(item["shown"]),
            SparseNoisePatternRecipe.model_validate_json(json.dumps(item["recipe"])),
            SparseNoiseGrid(*item["grid"]),
        )
        for item in items
    )


def encode_credit(limit: int) -> bytes:
    return b"CREDIT %d\n" % limit


def decode_credit(line: bytes) -> int:
    keyword, _, value = line.strip().partition(b" ")
    if keyword != b"CREDIT" or not value.isdigit():
        raise ValueError("sparse-noise helper expected a CREDIT line")
    return int(value)


def frame_header(sequence: int, length: int, digest: bytes) -> bytes:
    return FRAME.pack(MAGIC, sequence, length, digest)


class FrameReader:
    """Incrementally split helper stdout into (sequence, texels, digest) frames."""

    def __init__(self, max_frame_bytes: int) -> None:
        self.max_frame_bytes = max_frame_bytes
        self._pending = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[int, bytes, bytes]]:
        self._pending.extend(chunk)
        frames = []
        while len(self._pending) >= FRAME.size:
            magic, sequence, length, digest = FRAME.unpack_from(self._pending)
            if magic != MAGIC or length > self.max_frame_bytes:
                raise ValueError("sparse-noise helper sent a malformed frame")
            end = FRAME.size + length
            if len(self._pending) < end:
                break
            frames.append((sequence, bytes(self._pending[FRAME.size : end]), digest))
            del self._pending[:end]
        return frames

    @property
    def partial(self) -> bool:
        return bool(self._pending)
