"""Controller-owned E04 output reservation and bounded metadata persistence."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import queue
import re
import stat
import sys
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Literal

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4


class StorageError(RuntimeError):
    pass


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        raise StorageError("Windows directory durability helper unavailable")
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path: Path, payload: bytes, *, replace: bool) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            from cephvr.platform.windows.durable import create_synced, replace_synced

            if replace:
                replace_synced(temporary, path)
            else:
                create_synced(temporary, path)
        else:
            if replace:
                os.replace(temporary, path)
            else:
                os.link(temporary, path, follow_symlinks=False)
            _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


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
            reservation._lock_fd is None
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
            stream = os.fdopen(fd, "ab")
        except BaseException:
            os.close(fd)
            raise
        try:
            with self._lock:
                if (
                    self._sealed
                    or self._admissions_started
                    or self._log_stream is not None
                    or reservation._lock_fd is None
                ):
                    raise StorageError("recovery log adoption lost its admission race")
                self._owned.add(path)
                self._log_stream = stream
        except BaseException:
            stream.close()
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
                        first = write.path not in self._owned
                        if first:
                            if self._log_stream is not None:
                                raise StorageError(
                                    "session log handle is already owned"
                                )
                            self._log_stream = write.path.open("xb")
                        stream = self._log_stream
                        if stream is None:
                            raise StorageError("session log handle is unavailable")
                        handle_info = os.fstat(stream.fileno())
                        path_info = write.path.stat(follow_symlinks=False)
                        if not stat.S_ISREG(path_info.st_mode) or (
                            path_info.st_dev,
                            path_info.st_ino,
                        ) != (handle_info.st_dev, handle_info.st_ino):
                            raise StorageError(
                                "session log path changed after writer ownership"
                            )
                        stream.write(write.payload_utf8 + b"\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                        after_info = write.path.stat(follow_symlinks=False)
                        if (after_info.st_dev, after_info.st_ino) != (
                            handle_info.st_dev,
                            handle_info.st_ino,
                        ):
                            raise StorageError("session log path changed during append")
                        if first:
                            if os.name != "nt":
                                _sync_directory(write.path.parent)
                            self._owned.add(write.path)
                    else:
                        if (
                            write.action == "replace_json"
                            and write.path not in self._owned
                        ):
                            raise StorageError(
                                "replacement target was not created by this writer"
                            )
                        _atomic_json(
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


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    if not normalized or normalized in {".", ".."}:
        raise StorageError("experiment and subject require safe nonempty names")
    return normalized


class OutputReservation:
    """Exclusive session namespace ownership; never removes unlisted user files."""

    def __init__(
        self,
        root: Path,
        experiment: str,
        subject: str,
        session_id: str,
        generation: str,
        anchor: datetime,
    ):
        require_uuid4(session_id)
        require_uuid4(generation)
        self.root = root.resolve(strict=True)
        date = anchor.strftime("%Y%m%d")
        time = anchor.strftime("%H%M%S")
        self.experiment_directory = self.root / f"{date}_{_safe_component(experiment)}"
        self.session_directory = (
            self.experiment_directory / f"{_safe_component(subject)}-{time}"
        )
        self.protocol_directory = self.session_directory / "protocol-data"
        self.spikeglx_directory = self.session_directory / "spikeglx-data"
        self.marker = self.session_directory / ".cephvr-reservation.json"
        self.lock_path = self.session_directory / ".cephvr.lock"
        self.session_id = session_id
        self.generation = generation
        self._created: list[Path] = []
        self._lock_fd: int | None = None
        self._lock_created = False
        self.marker_issue: str | None = None

    @classmethod
    def open_existing(
        cls, session_directory: Path, session_id: str, generation: str
    ) -> OutputReservation:
        """Hold an exact existing namespace; inspect, never repair, its marker."""
        require_uuid4(session_id)
        require_uuid4(generation)
        directory = Path(session_directory)
        if not directory.is_absolute() or len(directory.parents) < 2:
            raise StorageError("recovery session directory is not absolute")
        if directory != directory.resolve(strict=True):
            raise StorageError("recovery session directory is not canonical")
        root = directory.parent.parent
        for path in (root, directory.parent, directory):
            if path.is_symlink() or not path.is_dir():
                raise StorageError("recovery namespace is missing or unsafe")
        instance = cls.__new__(cls)
        instance.root = root.resolve(strict=True)
        instance.experiment_directory = directory.parent
        instance.session_directory = directory
        instance.protocol_directory = directory / "protocol-data"
        instance.spikeglx_directory = directory / "spikeglx-data"
        for path in (instance.protocol_directory, instance.spikeglx_directory):
            if path.is_symlink() or not path.is_dir():
                raise StorageError("recovery child namespace is missing or unsafe")
        instance.marker = directory / ".cephvr-reservation.json"
        instance.lock_path = directory / ".cephvr.lock"
        instance.session_id = session_id
        instance.generation = generation
        instance._created = []
        instance._lock_fd = None
        instance._lock_created = False
        instance.marker_issue = None
        instance._acquire_lock(create=False)
        try:
            marker = instance.inspect_marker()
            if (marker.session_id, marker.controller_generation) != (
                session_id,
                generation,
            ):
                instance.marker_issue = "reservation marker identity mismatch"
            elif marker.complete:
                instance.marker_issue = "reservation marker already complete"
        except StorageError as exc:
            instance.marker_issue = str(exc)
        return instance

    def acquire(self) -> list[Path]:
        if self._lock_fd is not None:
            raise StorageError("reservation already held")
        for path in (
            self.experiment_directory,
            self.session_directory,
            self.protocol_directory,
            self.spikeglx_directory,
        ):
            if path.is_symlink():
                raise StorageError(f"symlink in reservation path: {path}")
            if not path.exists():
                path.mkdir()
                self._created.append(path)
            elif not path.is_dir():
                raise StorageError(f"reservation path is not a directory: {path}")
        self._acquire_lock(create=True)
        if self.marker.exists():
            raise StorageError("existing reservation marker requires recovery")
        conflicts = [p for p in self.protocol_directory.iterdir()] + [
            p for p in self.spikeglx_directory.iterdir()
        ]
        if conflicts:
            return conflicts
        self._write_marker()
        return []

    def _acquire_lock(self, *, create: bool) -> None:
        if not create and (self.lock_path.is_symlink() or not self.lock_path.is_file()):
            raise StorageError("existing session lock is missing or unsafe")
        if sys.platform == "win32":
            from cephvr.platform.windows.security import (
                WindowsSecurityError,
                open_owner_only_lock,
            )

            try:
                fd, self._lock_created = open_owner_only_lock(self.lock_path)
            except WindowsSecurityError as exc:
                raise StorageError(
                    "existing session lock is not a regular private file"
                ) from exc
            if not create and self._lock_created:
                os.close(fd)
                raise StorageError("recovery lock disappeared during opening")
        else:
            flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            try:
                if create:
                    fd = os.open(self.lock_path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                    self._lock_created = True
                else:
                    fd = os.open(self.lock_path, flags)
            except OSError as exc:
                if not create or exc.errno != errno.EEXIST:
                    raise StorageError(
                        "session lock could not be opened safely"
                    ) from exc
                try:
                    fd = os.open(self.lock_path, flags)
                except OSError as open_exc:
                    raise StorageError(
                        "existing session lock is not a regular file"
                    ) from open_exc
                self._lock_created = False
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                os.close(fd)
                raise StorageError("session lock owner/mode is unsafe")
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise StorageError("session output namespace is locked") from exc
        self._lock_fd = fd

    def inspect_marker(self) -> ReservationMarker:
        """Read bounded marker evidence only while this process holds the lock.

        Recovery authority and old-process absence are checked by the controller
        startup path, not inferred from an available OS lock or this marker.
        """
        try:
            raw = self._read_marker_bytes()
            data = json.loads(raw)
            if (
                not isinstance(data, dict)
                or set(data)
                != {"schema_version", "session_id", "controller_generation", "complete"}
                or data["schema_version"] != 1
                or type(data["complete"]) is not bool
            ):
                raise StorageError("reservation marker schema is invalid")
            session_id = require_uuid4(data["session_id"])
            generation = require_uuid4(data["controller_generation"])
            return ReservationMarker(session_id, generation, data["complete"])
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise StorageError("reservation marker is corrupt or unavailable") from exc

    def _read_marker_bytes(self) -> bytes:
        if self._lock_fd is None:
            raise StorageError("marker read requires held reservation lock")
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            descriptor = os.open(self.marker, flags)
        except OSError as exc:
            raise StorageError("reservation marker is absent or unsafe") from exc
        try:
            info = os.fstat(descriptor)
            path_info = self.marker.stat(follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or not stat.S_ISREG(path_info.st_mode)
                or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
            ):
                raise StorageError("reservation marker is not a stable regular file")
            chunks: list[bytes] = []
            remaining = 4097
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > 4096:
                raise StorageError("reservation marker byte bound exceeded")
            return raw
        finally:
            os.close(descriptor)

    def marker_fingerprint(self) -> str:
        """Bind an explicit recovery choice to the exact bounded marker bytes."""
        return hashlib.sha256(self._read_marker_bytes()).hexdigest()

    def finish_recovery(self, expected_marker_sha256: str) -> None:
        """Complete after caller's bounded evidence repair; never infer closure."""
        if not re.fullmatch(r"[0-9a-f]{64}", expected_marker_sha256):
            raise StorageError("recovery marker fingerprint is invalid")
        if self.marker_fingerprint() != expected_marker_sha256:
            raise StorageError("reservation marker changed during recovery")
        _atomic_json(
            self.marker,
            json.dumps(
                {
                    "schema_version": 1,
                    "session_id": self.session_id,
                    "controller_generation": self.generation,
                    "complete": True,
                },
                separators=(",", ":"),
            ).encode(),
            replace=True,
        )
        self.release()

    def resolve_collisions(self, listed_paths: list[Path]) -> None:
        """One explicit operator choice authorizes only the paths displayed."""
        if self._lock_fd is None or self.marker.exists():
            raise StorageError(
                "collision resolution requires an unmarked held reservation"
            )
        current = [p for p in self.protocol_directory.iterdir()] + [
            p for p in self.spikeglx_directory.iterdir()
        ]
        if set(current) != set(listed_paths):
            raise StorageError("output collision set changed during operator choice")
        for path in current:
            if (
                path.is_symlink()
                or not path.is_file()
                or path.parent not in {self.protocol_directory, self.spikeglx_directory}
            ):
                raise StorageError(f"collision is not a direct regular file: {path}")
        for path in current:
            path.unlink()
        if os.name != "nt":
            _sync_directory(self.protocol_directory)
            _sync_directory(self.spikeglx_directory)
        self._write_marker()

    def _write_marker(self) -> None:
        _atomic_json(
            self.marker,
            json.dumps(
                {
                    "schema_version": 1,
                    "session_id": self.session_id,
                    "controller_generation": self.generation,
                    "complete": False,
                },
                separators=(",", ":"),
            ).encode(),
            replace=False,
        )

    def complete(self) -> None:
        if self._lock_fd is None or not self.marker.exists():
            raise StorageError("reservation is not held")
        marker = self.inspect_marker()
        if (
            marker.session_id != self.session_id
            or marker.controller_generation != self.generation
            or marker.complete
        ):
            raise StorageError("reservation marker identity or state mismatch")
        _atomic_json(
            self.marker,
            json.dumps(
                {
                    "schema_version": 1,
                    "session_id": self.session_id,
                    "controller_generation": self.generation,
                    "complete": True,
                },
                separators=(",", ":"),
            ).encode(),
            replace=True,
        )
        self.release()

    def cancel(self) -> None:
        if self._lock_fd is None:
            raise StorageError("reservation is not held")
        for child in (self.protocol_directory, self.spikeglx_directory):
            if any(child.iterdir()):
                raise StorageError(f"unexpected files block cleanup: {child}")
        has_marker = self.marker.exists()
        if has_marker:
            marker = self.inspect_marker()
            if (
                marker.session_id != self.session_id
                or marker.controller_generation != self.generation
                or marker.complete
            ):
                raise StorageError("marker identity mismatch; cleanup blocked")
        for path in (self.spikeglx_directory, self.protocol_directory):
            if path in self._created:
                try:
                    path.rmdir()
                except OSError as exc:
                    raise StorageError(
                        f"unexpected files block cleanup: {path}"
                    ) from exc
        if os.name != "nt":
            _sync_directory(self.session_directory)
        if self.session_directory in self._created:
            quarantine = self.session_directory.with_name(
                f".{self.session_directory.name}.{uuid.uuid4()}.cleanup"
            )
            try:
                os.replace(self.session_directory, quarantine)
            except OSError as exc:
                raise StorageError(
                    "session quarantine failed; unfinished marker retained"
                ) from exc
            if os.name != "nt":
                _sync_directory(self.experiment_directory)
            self.release()
            if has_marker:
                (quarantine / self.marker.name).unlink()
            (quarantine / self.lock_path.name).unlink()
            quarantine.rmdir()
            if os.name != "nt":
                _sync_directory(self.experiment_directory)
            remaining = [
                p
                for p in reversed(self._created)
                if p
                not in {
                    self.session_directory,
                    self.protocol_directory,
                    self.spikeglx_directory,
                }
            ]
        else:
            tombstone: Path | None = None
            if self._lock_created:
                tombstone = self.lock_path.with_name(
                    f".{self.lock_path.name}.{uuid.uuid4()}.cleanup"
                )
                try:
                    os.replace(self.lock_path, tombstone)
                except OSError as exc:
                    raise StorageError(
                        "lock quarantine failed; unfinished marker retained"
                    ) from exc
                if os.name != "nt":
                    _sync_directory(self.session_directory)
            if has_marker:
                self.marker.unlink()
                if os.name != "nt":
                    _sync_directory(self.session_directory)
            self.release()
            if tombstone is not None:
                tombstone.unlink()
                if os.name != "nt":
                    _sync_directory(self.session_directory)
            remaining = [
                p
                for p in reversed(self._created)
                if p not in {self.protocol_directory, self.spikeglx_directory}
            ]
        for path in remaining:
            try:
                path.rmdir()
            except OSError as exc:
                raise StorageError(f"unexpected files block cleanup: {path}") from exc

    def release(self) -> None:
        if self._lock_fd is None:
            return
        fd, self._lock_fd = self._lock_fd, None
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
