"""Metadata requests, completions and reservation marker records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cephvr.control.v1 import types_pb2 as pb


class StorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class MetadataWrite:
    command_id: str
    work: pb.WorkContext
    operation: pb.OperationContext
    path: Path
    action: Literal["create_json", "replace_json", "append_jsonl_record"]
    payload_utf8: bytes
    submitted_ns: int
    deadline_ns: int


@dataclass(frozen=True)
class MetadataCompletion:
    command_id: str
    path: Path
    state: Literal["synced", "failed", "unconfirmed"]
    completed_ns: int
    error: str = ""
    deadline_met: bool = True


@dataclass(frozen=True)
class ReservationMarker:
    session_id: str
    controller_generation: str
    complete: bool
