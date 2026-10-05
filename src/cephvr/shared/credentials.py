"""Ephemeral, generation-scoped local operator credentials for E08 clients."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from cephvr.shared.auth import Principal
from cephvr.shared.identity import require_uuid4

_MAX_RECORD_BYTES = 4_096
_FIELDS = frozenset({"controller_generation", "client_id", "role", "token"})


class CredentialError(RuntimeError):
    """Local credential storage is missing, unsafe or inconsistent."""


def default_runtime_root() -> Path:
    """Choose a user-private runtime location; CredentialStore verifies it."""
    if sys.platform == "win32":
        appdata = os.environ.get("LOCALAPPDATA")
        if not appdata:
            raise CredentialError("LOCALAPPDATA is required for local credentials")
        return Path(appdata) / "CephVR" / "runtime"
    parent = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(parent) / f"cephvr-{os.getuid()}"


def _windows_security() -> object:
    from cephvr.platform.windows import security

    return security


def _check_private(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CredentialError(f"cannot inspect credential path {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise CredentialError("credential path must not be a symlink")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise CredentialError("credential directory is not a directory")
    if not directory and not stat.S_ISREG(info.st_mode):
        raise CredentialError("credential file is not a regular file")
    if sys.platform == "win32":
        security = _windows_security()
        security.verify_owner_only(path)  # type: ignore[attr-defined]
    else:
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise CredentialError("credential path is not owner-only")
        if not directory and info.st_nlink != 1:
            raise CredentialError("credential file has multiple hard links")


def _ensure_directory(path: Path) -> None:
    if sys.platform == "win32":
        missing: list[Path] = []
        cursor = path
        while not cursor.exists():
            missing.append(cursor)
            if cursor.parent == cursor:
                raise CredentialError("credential runtime path has no existing parent")
            cursor = cursor.parent
        security = _windows_security()
        for directory in reversed(missing):
            security.create_owner_only_directory(directory)  # type: ignore[attr-defined]
        _check_private(path, directory=True)
        return
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        pass
    except OSError as exc:
        raise CredentialError(f"cannot create credential directory {path}") from exc
    _check_private(path, directory=True)


class CredentialStore:
    """Only operator clients use these files; service roles use launch bootstrap."""

    def __init__(self, runtime_root: Path, controller_generation: str) -> None:
        self.controller_generation = require_uuid4(controller_generation)
        self.runtime_root = Path(runtime_root)
        self.generation_dir = self.runtime_root / self.controller_generation
        _ensure_directory(self.runtime_root)
        _ensure_directory(self.generation_dir)

    def _path(self, client_id: str) -> Path:
        return self.generation_dir / f"{require_uuid4(client_id)}.json"

    def provision_client(
        self,
        role: Literal["cli", "gui"],
        *,
        generation: str | None = None,
        token: str | None = None,
    ) -> Principal:
        """Publish one fresh client or the exact supervisor-launched GUI identity."""
        if role not in ("cli", "gui"):
            raise CredentialError("unsupported local operator role")
        if (generation is None) != (token is None):
            raise CredentialError(
                "managed client identity and token must be supplied together"
            )
        if generation is not None:
            if role != "gui" or not token:
                raise CredentialError("only a managed GUI may use a supplied identity")
            generation = require_uuid4(generation)
        _check_private(self.runtime_root, directory=True)
        _check_private(self.generation_dir, directory=True)
        for _ in range(1 if generation is not None else 3):
            client_id = generation or str(uuid4())
            if generation is not None and self._path(client_id).exists():
                raise CredentialError("managed GUI credential already exists")
            principal = Principal(role, client_id, token or secrets.token_urlsafe(32))
            raw = json.dumps(
                {
                    "controller_generation": self.controller_generation,
                    "client_id": client_id,
                    "role": role,
                    "token": principal.token,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(raw) > _MAX_RECORD_BYTES:
                raise CredentialError("credential record exceeds byte limit")
            if sys.platform == "win32":
                security = _windows_security()
                try:
                    security.create_owner_only(self._path(client_id), raw)  # type: ignore[attr-defined]
                except FileExistsError:
                    if generation is not None:
                        raise CredentialError(
                            "managed GUI credential already exists"
                        ) from None
                    continue
                _check_private(self._path(client_id), directory=False)
                return principal
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(self._path(client_id), flags, 0o600)
            except FileExistsError:
                if generation is not None:
                    raise CredentialError(
                        "managed GUI credential already exists"
                    ) from None
                continue
            except OSError as exc:
                raise CredentialError("cannot create client credential") from exc
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                _check_private(self._path(client_id), directory=False)
            except Exception:
                self._path(client_id).unlink(missing_ok=True)
                raise
            return principal
        raise CredentialError("could not allocate unique client ID")

    def lookup(self, client_id: str) -> Principal | None:
        """Read bounded exact credentials outside the controller state loop."""
        path = self._path(client_id)
        _check_private(self.runtime_root, directory=True)
        _check_private(self.generation_dir, directory=True)
        try:
            path.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CredentialError("cannot inspect client credential") from exc
        _check_private(path, directory=False)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise CredentialError("cannot open client credential") from exc
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_RECORD_BYTES:
                raise CredentialError("client credential is not a bounded regular file")
            if sys.platform != "win32" and (
                info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1
            ):
                raise CredentialError("client credential is not owner-only")
            raw = stream.read(_MAX_RECORD_BYTES + 1)
        if len(raw) > _MAX_RECORD_BYTES:
            raise CredentialError("client credential exceeds byte limit")
        try:
            record = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise CredentialError("invalid client credential record") from exc
        if not isinstance(record, dict) or set(record) != _FIELDS:
            raise CredentialError("client credential fields differ from schema")
        if (
            record["controller_generation"] != self.controller_generation
            or record["client_id"] != client_id
            or record["role"] not in ("cli", "gui")
            or not isinstance(record["token"], str)
            or not record["token"]
        ):
            raise CredentialError("client credential context does not match")
        return Principal(record["role"], client_id, record["token"])

    def remove_client(self, principal: Principal) -> None:
        """Remove only this client's matching token; never another generation's."""
        retained = self.lookup(principal.generation)
        if retained is None:
            return
        if retained.role != principal.role or not hmac.compare_digest(
            retained.token, principal.token
        ):
            raise CredentialError("client credential ownership mismatch")
        try:
            self._path(principal.generation).unlink()
        except OSError as exc:
            raise CredentialError("cannot remove client credential") from exc
