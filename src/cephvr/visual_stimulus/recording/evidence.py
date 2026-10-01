"""Bounded append-only writer for the V28 JSON Lines evidence stream."""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, Protocol

from pydantic import BaseModel

from cephvr.visual_stimulus.config.models.evidence_model import (
    ArtifactRef,
    EvidenceRecord,
    Header,
    Record,
)


class EvidenceWriter:
    """Reserve bounded evidence bytes before accepting any line.

    The render owner can reserve/write already-built records into memory. A single
    recording owner calls ``write_pending`` and prioritizes evidence before review
    video work. It is the caller's responsibility to keep model construction and JSON
    encoding off the GL thread; ``enqueue_json`` accepts pre-serialized bytes.
    """

    def __init__(
        self,
        *,
        max_pending_bytes: int,
        sync_file: Callable[[BinaryIO], None] | None = None,
    ) -> None:
        if max_pending_bytes <= 0:
            raise ValueError("evidence pending-byte limit must be positive")
        self.max_pending_bytes = max_pending_bytes
        self.sync_file = sync_file or (lambda stream: os.fsync(stream.fileno()))
        self._pending: deque[bytes] = deque()
        self._pending_bytes = 0
        self._lock = threading.Lock()
        self._opened = False
        self._completed = False

    @property
    def pending_bytes(self) -> int:
        with self._lock:
            return self._pending_bytes

    def open_after_recipe(
        self, path: Path, header: Header, published_recipe: ArtifactRef
    ) -> None:
        if self._opened:
            raise RuntimeError("evidence writer already opened")
        if published_recipe != header.recipe:
            raise ValueError(
                "published recipe receipt does not match evidence Header reference"
            )
        line = self._encode(EvidenceRecord(payload=header))
        # Open exclusively: the E04-reserved path must never be silently replaced.
        self._stream = open(path, "xb")
        self._opened = True
        self.enqueue_json(line)

    def enqueue(self, record: Record | EvidenceRecord) -> None:
        envelope = (
            record
            if isinstance(record, EvidenceRecord)
            else EvidenceRecord(payload=record)
        )
        self.enqueue_json(self._encode(envelope))

    def enqueue_json(self, line: bytes) -> None:
        if not line.endswith(b"\n") or b"\n" in line[:-1]:
            raise ValueError(
                "evidence must be exactly one newline-terminated JSON line"
            )
        with self._lock:
            if self._completed:
                raise RuntimeError("evidence has already been completed")
            if len(line) > self.max_pending_bytes - self._pending_bytes:
                raise BufferError(
                    "required Visual Stimulus evidence exceeded evidence_pending_bytes"
                )
            self._pending.append(line)
            self._pending_bytes += len(line)

    def write_pending(self, *, sync: bool = False) -> int:
        """Append all currently queued evidence in order, then optionally fsync."""
        if not self._opened:
            raise RuntimeError("evidence Header is not published")
        written = 0
        while True:
            with self._lock:
                if not self._pending:
                    break
                line = self._pending.popleft()
                self._pending_bytes -= len(line)
            self._stream.write(line)
            written += len(line)
            if line.find(b'"kind":"completion"') >= 0:
                self._completed = True
        self._stream.flush()
        if sync:
            self.sync_file(self._stream)
        return written

    def close(self, *, sync: bool = True) -> None:
        if not self._opened:
            return
        self.write_pending(sync=sync)
        self._stream.close()
        self._opened = False

    @staticmethod
    def _encode(record: BaseModel) -> bytes:
        raw = json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return raw + b"\n"


class EncoderInput(Protocol):
    """Bounded/nonblocking raw stdin writer owned by the recording thread."""

    def write_chunk(self, data: memoryview) -> int: ...

    def close_input(self) -> None: ...
