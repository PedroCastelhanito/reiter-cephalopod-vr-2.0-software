"""E04 private controller writer interface; implementation is controller.storage."""

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from cephvr.control.v1.types_pb2 import OperationContext, WorkContext

@dataclass(frozen=True)
class MetadataWrite:
    command_id: str
    work: WorkContext
    operation: OperationContext
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

class MetadataWriter(Protocol):
    def __init__(
        self,
        root: Path,
        *,
        max_operations: int,
        max_bytes: int,
        clock: Callable[[], int],
        session_id: str,
    ) -> None: ...
    def submit(self, write: MetadataWrite) -> Future[MetadataCompletion]: ...
    def retire(self, command_id: str) -> None: ...
    def reserve_trial_log(self, name: str) -> None: ...
    def reserve_recovery_report(self, name: str) -> None: ...
    def adopt_recovery_log(
        self,
        reservation: OutputReservation,
        *,
        expected_dev: int,
        expected_ino: int,
        expected_size: int,
    ) -> None: ...
    def seal(self, timeout_s: float) -> bool: ...


class OutputReservation(Protocol):
    marker_issue: str | None
    session_directory: Path
    protocol_directory: Path
    session_id: str
    generation: str
    @classmethod
    def open_existing(
        cls, session_directory: Path, session_id: str, generation: str
    ) -> OutputReservation: ...
    def inspect_marker(self) -> ReservationMarker: ...
    def marker_fingerprint(self) -> str: ...
    def finish_recovery(self, expected_marker_sha256: str) -> None: ...
    def release(self) -> None: ...
