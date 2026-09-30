"""Bounded serialized central metadata writer and completion ownership."""

from __future__ import annotations

import json
import os
import queue
import re
import stat
import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import BinaryIO

from cephvr.controller.metadata.files import atomic_json, sync_directory
from cephvr.controller.metadata.reservation import OutputReservation
from cephvr.controller.metadata.types import (
    MetadataCompletion,
    MetadataWrite,
    StorageError,
)
from cephvr.shared.identity import require_uuid4


class _NonCancellingFuture(Future[MetadataCompletion]):
    """Awaiter cancellation cannot erase the writer's accepted completion."""

    def cancel(self) -> bool:
        return False


class MetadataWriter:
    """One private writer; controller owns once-only IDs and terminal retirement.

    A caller reconciles an uncertain operation through its retained Future. It
    never resubmits a retired ID; external command retries belong to the controller
    ledger. Accepted and terminal-unconsumed records are not implicitly evicted.
    """

    def __init__(
        self,
        root: Path,
        *,
        max_operations: int,
        max_bytes: int,
        clock: Callable[[], int],
        session_id: str,
    ):
        if max_operations < 1 or max_bytes < 1:
            raise ValueError("metadata queue bounds must be positive")
        self.root = root.resolve(strict=True)
        self.max_operations = max_operations
        self.max_bytes = max_bytes
        self.clock = clock
        self.session_id = session_id
        # One extra slot is exclusively for the seal sentinel; work uses separate count bounds.
        self._queue: queue.Queue[
            tuple[MetadataWrite, Future[MetadataCompletion]] | None
        ] = queue.Queue(max_operations + 1)
        self._pending_count = 0
        self._pending_bytes = 0
        self._lock = threading.Lock()
        self._sealed = False
        self._admissions_started = False
        self._accepted: dict[str, tuple[MetadataWrite, Future[MetadataCompletion]]] = {}
        self._owned: set[Path] = set()
        self._log_stream: BinaryIO | None = None
        self._log_poison: str | None = None
        self._seal_failure: BaseException | None = None
        self._reserved: set[str] = {
            "SESSION_CONFIG.json",
            "SESSION_LOG.jsonl",
            "SCHEMA.json",
        }
        self._thread = threading.Thread(
            target=self._run, name="cephvr-metadata", daemon=True
        )
        self._thread.start()

    def submit(self, write: MetadataWrite) -> Future[MetadataCompletion]:
        if not write.command_id or not write.payload_utf8:
            raise StorageError("metadata operation identity and payload required")
        if write.operation.command_id != write.command_id:
            raise StorageError("metadata operation/command identity mismatch")
        work_kind = write.work.WhichOneof("work")
        if work_kind == "session":
            session = write.work.session
        elif work_kind == "trial":
            session = write.work.trial.session
            if not write.work.trial.trial_id or write.work.trial.trial_number < 1:
                raise StorageError("metadata trial context is incomplete")
        else:
            raise StorageError("metadata work context is missing")
        if session.session_id != self.session_id:
            raise StorageError("metadata work/session identity mismatch")
        try:
            require_uuid4(session.controller_generation)
        except ValueError as exc:
            raise StorageError("metadata controller generation is invalid") from exc
        path = write.path
        if not path.is_absolute() or path.parent != self.root:
            raise StorageError(
                "metadata path must be a direct reserved protocol-data file"
            )
        if path.name not in self._reserved:
            raise StorageError("metadata destination is not reserved")
        if write.action == "append_jsonl_record" and path.name != "SESSION_LOG.jsonl":
            raise StorageError("only SESSION_LOG.jsonl accepts appends")
        if write.action != "append_jsonl_record" and path.name == "SESSION_LOG.jsonl":
            raise StorageError("session event log is append only")
        try:
            document = json.loads(write.payload_utf8)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageError("metadata payload is not UTF-8 JSON") from exc
        if not isinstance(document, dict):
            raise StorageError("metadata payload must be a JSON object")
        if write.action != "append_jsonl_record" and (
            document.get("schema_version") != 1
            or document.get("session_id", self.session_id) != self.session_id
        ):
            raise StorageError("metadata schema or session identity mismatch")
        if write.action == "append_jsonl_record" and b"\n" in write.payload_utf8:
            raise StorageError("JSONL event must occupy exactly one line")
        if write.action not in {"create_json", "replace_json", "append_jsonl_record"}:
            raise StorageError("unknown metadata action")
        size = len(write.payload_utf8)
        with self._lock:
            previous = self._accepted.get(write.command_id)
            if previous is not None:
                if previous[0] != write:
                    raise StorageError(
                        "metadata command ID reused with different operation"
                    )
                return previous[1]
            if self._sealed:
                raise StorageError("metadata writer is sealed")
            if self.clock() > write.deadline_ns:
                raise StorageError("metadata submission deadline elapsed")
            if (
                self._pending_count >= self.max_operations
                or self._pending_bytes + size > self.max_bytes
            ):
                raise StorageError("metadata writer capacity exhausted")
            result: Future[MetadataCompletion] = _NonCancellingFuture()
            self._pending_count += 1
            self._pending_bytes += size
            self._admissions_started = True
            self._accepted[write.command_id] = (write, result)
            self._queue.put_nowait((write, result))
            return result

    def retire(self, command_id: str) -> None:
        """Release exact terminal evidence only after the state loop consumed it."""
        with self._lock:
            retained = self._accepted.get(command_id)
            if retained is None:
                raise StorageError("metadata operation is not retained")
            if not retained[1].done():
                raise StorageError("metadata operation has no terminal evidence")
            del self._accepted[command_id]

    def reserve_trial_log(self, name: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+_[0-9]{6}_LOG\.json", name):
            raise StorageError("invalid trial log reservation")
        with self._lock:
            if self._sealed:
                raise StorageError("metadata writer is sealed")
            self._reserved.add(name)

    def reserve_recovery_report(self, name: str) -> None:
        if not re.fullmatch(
            r"RECOVERY-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.json",
            name,
        ):
            raise StorageError("invalid recovery report reservation")
        with self._lock:
            if self._sealed:
                raise StorageError("metadata writer is sealed")
            self._reserved.add(name)

    def adopt_recovery_log(
        self,
        reservation: OutputReservation,
        *,
        expected_dev: int,
        expected_ino: int,
        expected_size: int,
    ) -> None:
        """Adopt only an intact, externally validated log under the held lock."""
        path = reservation.protocol_directory / "SESSION_LOG.jsonl"
        if (
            not reservation.held
            or self.root != reservation.protocol_directory
            or self.session_id != reservation.session_id
            or min(expected_dev, expected_ino, expected_size) < 0
        ):
            raise StorageError("recovery log reservation/identity is unavailable")
        with self._lock:
            if self._sealed or self._admissions_started or self._log_stream is not None:
                raise StorageError("recovery log adoption must precede all writes")
        flags = (
            os.O_WRONLY
            | os.O_APPEND
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise StorageError("recovery log cannot be opened safely") from exc
        try:
            info = os.fstat(fd)
            current = path.stat(follow_symlinks=False)
            expected = (expected_dev, expected_ino, expected_size)
            if (
                not stat.S_ISREG(info.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
                or getattr(current, "st_file_attributes", 0) & 0x400
                or (info.st_dev, info.st_ino, info.st_size) != expected
                or (current.st_dev, current.st_ino, current.st_size) != expected
            ):
                raise StorageError("recovery log changed since validation")
            stream = os.fdopen(fd, "ab", buffering=0)
        except BaseException:
            os.close(fd)
            raise
        try:
            with self._lock:
                if (
                    self._sealed
                    or self._admissions_started
                    or self._log_stream is not None
                    or not reservation.held
                ):
                    raise StorageError("recovery log adoption lost its admission race")
                self._owned.add(path)
                self._log_stream = stream
        except BaseException:
            stream.close()
            raise

    def _append_log(self, write: MetadataWrite) -> None:
        """Unbuffered append; any error poisons the log so old bytes never reappear."""
        if self._log_poison is not None:
            raise StorageError(
                f"session log is unconfirmed after an earlier append failure: {self._log_poison}"
            )
        try:
            first = write.path not in self._owned
            if first:
                if self._log_stream is not None:
                    raise StorageError("session log handle is already owned")
                self._log_stream = write.path.open("xb", buffering=0)
                self._owned.add(write.path)
            stream = self._log_stream
            if stream is None:
                raise StorageError("session log handle is unavailable")
            handle_info = os.fstat(stream.fileno())
            path_info = write.path.stat(follow_symlinks=False)
            if not stat.S_ISREG(path_info.st_mode) or (
                path_info.st_dev,
                path_info.st_ino,
            ) != (handle_info.st_dev, handle_info.st_ino):
                raise StorageError("session log path changed after writer ownership")
            view = memoryview(write.payload_utf8 + b"\n")
            while view:
                view = view[os.write(stream.fileno(), view) :]
            os.fsync(stream.fileno())
            after_info = write.path.stat(follow_symlinks=False)
            if (after_info.st_dev, after_info.st_ino) != (
                handle_info.st_dev,
                handle_info.st_ino,
            ):
                raise StorageError("session log path changed during append")
            if first and os.name != "nt":
                sync_directory(write.path.parent)
        except Exception as exc:
            self._log_poison = str(exc) or type(exc).__name__
            raise

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                try:
                    if self._log_stream is not None:
                        self._log_stream.close()
                except BaseException as exc:
                    self._seal_failure = exc
                self._queue.task_done()
                return
            write, result = item
            completion: MetadataCompletion | None = None
            failure: BaseException | None = None
            try:
                if self.clock() > write.deadline_ns:
                    completion = MetadataCompletion(
                        write.command_id,
                        write.path,
                        "unconfirmed",
                        self.clock(),
                        "deadline elapsed before write",
                        False,
                    )
                else:
                    if write.path.is_symlink():
                        raise StorageError("metadata path became a symlink")
                    if write.action == "append_jsonl_record":
                        self._append_log(write)
                    else:
                        if (
                            write.action == "replace_json"
                            and write.path not in self._owned
                        ):
                            raise StorageError(
                                "replacement target was not created by this writer"
                            )
                        atomic_json(
                            write.path,
                            write.payload_utf8,
                            replace=write.action == "replace_json",
                        )
                        self._owned.add(write.path)
                    at = self.clock()
                    completion = MetadataCompletion(
                        write.command_id,
                        write.path,
                        "synced",
                        at,
                        deadline_met=at <= write.deadline_ns,
                    )
            except Exception as exc:
                try:
                    completion = MetadataCompletion(
                        write.command_id, write.path, "failed", self.clock(), str(exc)
                    )
                except BaseException as clock_exc:
                    failure = clock_exc
            finally:
                try:
                    if not result.done():
                        if completion is not None:
                            result.set_result(completion)
                        elif failure is not None:
                            result.set_exception(failure)
                        else:
                            result.set_exception(
                                StorageError(
                                    "metadata writer failed without completion"
                                )
                            )
                finally:
                    with self._lock:
                        self._pending_count -= 1
                        self._pending_bytes -= len(write.payload_utf8)
                    self._queue.task_done()

    def seal(self, timeout_s: float) -> bool:
        with self._lock:
            if not self._sealed:
                self._sealed = True
                self._queue.put_nowait(None)
        self._thread.join(timeout_s)
        return not self._thread.is_alive() and self._seal_failure is None
