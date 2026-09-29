"""Owner-private, bounded E04 startup pointer and launcher-exit evidence."""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from cephvr.shared.clock import require_int64_ns
from cephvr.shared.credentials import CredentialError, _check_private, _ensure_directory
from cephvr.shared.identity import require_uuid4

_MAX_RECORD_BYTES = 4096


class RecoveryStoreError(RuntimeError):
    """A recovery pointer or proof is unsafe, inconsistent or unavailable."""


@dataclass(frozen=True)
class UnfinishedSessionPointer:
    session_directory: str
    session_id: str
    controller_generation: str
    supervisor_generation: str
    format_version: Literal[1] = 1

    def __post_init__(self) -> None:
        if type(self.format_version) is not int or self.format_version != 1:
            raise ValueError("unsupported recovery pointer format")
        if not Path(self.session_directory).is_absolute() or not self.session_directory:
            raise ValueError("recovery session directory must be absolute")
        require_uuid4(self.session_id)
        require_uuid4(self.controller_generation)
        require_uuid4(self.supervisor_generation)


@dataclass(frozen=True)
class ApplicationExitReceipt:
    controller_generation: str
    supervisor_generation: str
    observed_monotonic_ns: int
    all_owned_processes_absent: bool
    format_version: Literal[1] = 1

    def __post_init__(self) -> None:
        require_uuid4(self.controller_generation)
        require_uuid4(self.supervisor_generation)
        require_int64_ns(self.observed_monotonic_ns)
        if type(self.format_version) is not int or self.format_version != 1:
            raise ValueError("unsupported exit receipt format")
        if (
            self.observed_monotonic_ns <= 0
            or self.all_owned_processes_absent is not True
        ):
            raise ValueError("application exit is not verified")


def _encode(record: UnfinishedSessionPointer | ApplicationExitReceipt) -> bytes:
    raw = json.dumps(asdict(record), sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > _MAX_RECORD_BYTES:
        raise RecoveryStoreError("recovery record exceeds byte limit")
    return raw


def _read(path: Path) -> dict[str, object] | None:
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RecoveryStoreError("cannot inspect recovery record") from exc
    try:
        _check_private(path, directory=False)
    except CredentialError as exc:
        raise RecoveryStoreError("recovery record is not owner-only") from exc
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RecoveryStoreError("cannot open recovery record") from exc
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_RECORD_BYTES:
            raise RecoveryStoreError("recovery record is not a bounded file")
        if sys.platform != "win32" and (
            info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1
        ):
            raise RecoveryStoreError("recovery record is not owner-only")
        raw = stream.read(_MAX_RECORD_BYTES + 1)
    if len(raw) > _MAX_RECORD_BYTES:
        raise RecoveryStoreError("recovery record exceeds byte limit")

    def unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
        values: dict[str, object] = {}
        for key, value in pairs:
            if key in values:
                raise RecoveryStoreError("recovery record repeats a field")
            values[key] = value
        return values

    def reject_constant(value: str) -> None:
        raise RecoveryStoreError(f"recovery record has invalid number {value}")

    try:
        record = json.loads(
            raw,
            object_pairs_hook=unique_fields,
            parse_constant=reject_constant,
        )
    except (ValueError, UnicodeError) as exc:
        raise RecoveryStoreError("recovery record is not JSON") from exc
    if not isinstance(record, dict):
        raise RecoveryStoreError("recovery record is not an object")
    return record


def _publish(path: Path, raw: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        if sys.platform == "win32":
            from cephvr.platform.windows.durable import create_synced
            from cephvr.platform.windows.security import create_owner_only

            create_owner_only(temporary, raw)
            create_synced(temporary, path)
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path, follow_symlinks=False)
            temporary.unlink()
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        _check_private(path, directory=False)
    finally:
        temporary.unlink(missing_ok=True)


class RecoveryStore:
    """One unfinished pointer; immutable exact old-generation exit receipts."""

    def __init__(self, runtime_root: Path) -> None:
        _ensure_directory(Path(runtime_root))
        self.runtime_root = Path(runtime_root) / "recovery"
        _ensure_directory(self.runtime_root)

    @property
    def pointer_path(self) -> Path:
        return self.runtime_root / "unfinished_session.json"

    def _receipt_path(self, controller_generation: str) -> Path:
        return self.runtime_root / (
            f"application-exit-{require_uuid4(controller_generation)}.json"
        )

    def read_pointer(self) -> UnfinishedSessionPointer | None:
        _check_private(self.runtime_root, directory=True)
        record = _read(self.pointer_path)
        if record is None:
            return None
        if set(record) != set(UnfinishedSessionPointer.__dataclass_fields__):
            raise RecoveryStoreError("recovery pointer fields differ from schema")
        try:
            return UnfinishedSessionPointer(**record)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise RecoveryStoreError("recovery pointer is invalid") from exc

    def write_pointer(self, pointer: UnfinishedSessionPointer) -> None:
        _check_private(self.runtime_root, directory=True)
        existing = self.read_pointer()
        if existing is not None:
            if existing == pointer:
                return
            raise RecoveryStoreError("another unfinished session is retained")
        try:
            _publish(self.pointer_path, _encode(pointer))
        except FileExistsError as exc:
            raise RecoveryStoreError(
                "unfinished pointer was concurrently created"
            ) from exc

    def clear_pointer(self, expected: UnfinishedSessionPointer) -> None:
        if self.read_pointer() != expected:
            raise RecoveryStoreError("unfinished pointer changed or is missing")
        self.pointer_path.unlink()
        if sys.platform != "win32":
            directory = os.open(self.runtime_root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    def read_exit_receipt(
        self, prior_controller_generation: str
    ) -> ApplicationExitReceipt | None:
        _check_private(self.runtime_root, directory=True)
        record = _read(self._receipt_path(prior_controller_generation))
        if record is None:
            return None
        if set(record) != set(ApplicationExitReceipt.__dataclass_fields__):
            raise RecoveryStoreError("exit receipt fields differ from schema")
        try:
            receipt = ApplicationExitReceipt(**record)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise RecoveryStoreError("exit receipt is invalid") from exc
        if receipt.controller_generation != prior_controller_generation:
            raise RecoveryStoreError("exit receipt generation mismatch")
        return receipt

    def write_exit_receipt(self, receipt: ApplicationExitReceipt) -> None:
        _check_private(self.runtime_root, directory=True)
        existing = self.read_exit_receipt(receipt.controller_generation)
        if existing is not None:
            if existing == receipt:
                return
            raise RecoveryStoreError("old application exit receipt changed")
        try:
            _publish(
                self._receipt_path(receipt.controller_generation), _encode(receipt)
            )
        except FileExistsError as exc:
            raise RecoveryStoreError("exit receipt was concurrently created") from exc
