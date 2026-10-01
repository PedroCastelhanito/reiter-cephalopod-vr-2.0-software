"""E04 exclusive reservation, marker and namespace cleanup ownership."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from datetime import datetime
from pathlib import Path

from cephvr.controller.metadata.files import atomic_json, safe_component, sync_directory
from cephvr.controller.metadata.types import ReservationMarker, StorageError
from cephvr.shared.identity import require_uuid4


def _sync(path: Path) -> None:
    if os.name != "nt":
        sync_directory(path)


class OutputReservation:
    """Exclusive session namespace ownership; never removes unlisted user files."""

    @property
    def held(self) -> bool:
        """Whether this owner currently retains its reservation lock descriptor."""
        return self._lock_fd is not None

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
        resolved_root = root.resolve(strict=True)
        date = anchor.strftime("%Y%m%d")
        time = anchor.strftime("%H%M%S")
        experiment_directory = resolved_root / f"{date}_{safe_component(experiment)}"
        self._bind_paths(
            resolved_root,
            experiment_directory,
            experiment_directory / f"{safe_component(subject)}-{time}",
            session_id,
            generation,
        )

    def _bind_paths(
        self,
        root: Path,
        experiment_directory: Path,
        session_directory: Path,
        session_id: str,
        generation: str,
    ) -> None:
        self.root = root
        self.experiment_directory = experiment_directory
        self.session_directory = session_directory
        self.protocol_directory = session_directory / "protocol-data"
        self.spikeglx_directory = session_directory / "spikeglx-data"
        self.marker = session_directory / ".cephvr-reservation.json"
        self.lock_path = session_directory / ".cephvr.lock"
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
        instance._bind_paths(
            root.resolve(strict=True),
            directory.parent,
            directory,
            session_id,
            generation,
        )
        for path in (instance.protocol_directory, instance.spikeglx_directory):
            if path.is_symlink() or not path.is_dir():
                raise StorageError("recovery child namespace is missing or unsafe")
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
        conflicts = self._direct_children()
        if conflicts:
            return conflicts
        self._write_marker()
        return []

    def _direct_children(self) -> list[Path]:
        return [*self.protocol_directory.iterdir(), *self.spikeglx_directory.iterdir()]

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
            keys = {"schema_version", "session_id", "controller_generation", "complete"}
            if (
                not isinstance(data, dict)
                or set(data) not in (keys, keys | {"outcome"})
                or data.get("outcome", "not_activated") != "not_activated"
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
        atomic_json(
            self.marker,
            self._marker_payload(complete=True),
            replace=True,
        )
        self.release()

    def resolve_collisions(self, listed_paths: list[Path]) -> None:
        """One explicit operator choice authorizes only the paths displayed."""
        if self._lock_fd is None or self.marker.exists():
            raise StorageError(
                "collision resolution requires an unmarked held reservation"
            )
        current = self._direct_children()
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
        _sync(self.protocol_directory)
        _sync(self.spikeglx_directory)
        self._write_marker()

    def _marker_payload(self, *, complete: bool, outcome: str | None = None) -> bytes:
        payload: dict[str, object] = {
            "schema_version": 1,
            "session_id": self.session_id,
            "controller_generation": self.generation,
            "complete": complete,
        }
        if outcome is not None:
            payload["outcome"] = outcome
        return json.dumps(payload, separators=(",", ":")).encode()

    def _write_marker(self) -> None:
        atomic_json(
            self.marker,
            self._marker_payload(complete=False),
            replace=False,
        )

    def _require_own_open_marker(self, message: str) -> None:
        marker = self.inspect_marker()
        if (
            marker.session_id != self.session_id
            or marker.controller_generation != self.generation
            or marker.complete
        ):
            raise StorageError(message)

    def _finish(self, outcome: str | None) -> None:
        if self._lock_fd is None or not self.marker.exists():
            raise StorageError("reservation is not held")
        self._require_own_open_marker("reservation marker identity or state mismatch")
        atomic_json(
            self.marker,
            self._marker_payload(complete=True, outcome=outcome),
            replace=True,
        )
        self.release()

    def complete(self) -> None:
        self._finish(None)

    def close_unactivated(self) -> None:
        """Keep all files; mark a never-activated Setup finished, then release.

        The caller seals the writer first and clears the recovery pointer after.
        """
        self._finish("not_activated")

    def cancel(self) -> None:
        if self._lock_fd is None:
            raise StorageError("reservation is not held")
        for child in (self.protocol_directory, self.spikeglx_directory):
            if any(child.iterdir()):
                raise StorageError(f"unexpected files block cleanup: {child}")
        has_marker = self.marker.exists()
        if has_marker:
            self._require_own_open_marker("marker identity mismatch; cleanup blocked")
        for path in (self.spikeglx_directory, self.protocol_directory):
            if path in self._created:
                try:
                    path.rmdir()
                except OSError as exc:
                    raise StorageError(
                        f"unexpected files block cleanup: {path}"
                    ) from exc
        _sync(self.session_directory)
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
            _sync(self.experiment_directory)
            self.release()
            if has_marker:
                (quarantine / self.marker.name).unlink()
            (quarantine / self.lock_path.name).unlink()
            quarantine.rmdir()
            _sync(self.experiment_directory)
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
                _sync(self.session_directory)
            if has_marker:
                self.marker.unlink()
                _sync(self.session_directory)
            self.release()
            if tombstone is not None:
                tombstone.unlink()
                _sync(self.session_directory)
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
