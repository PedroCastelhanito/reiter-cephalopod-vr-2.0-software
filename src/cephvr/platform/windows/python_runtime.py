"""Prepare and validate CephVR's exact Windows virtual-environment interpreter."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import sysconfig
from pathlib import Path
from typing import Any

_MANIFEST = "cephvr-python.runtime.json"
_WRAPPER = "cephvr-python.exe"
_STARTUP_DLL_NAMES = ("VCRUNTIME140.dll", "zlib.dll")


class PythonRuntimeError(RuntimeError):
    """The prepared venv interpreter is missing, stale, or inconsistent."""


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as exc:
        raise PythonRuntimeError(
            f"cannot hash Python runtime file {path}: {exc}"
        ) from exc
    return hasher.hexdigest()


def _venv_home(configuration: Path) -> Path:
    try:
        for line in configuration.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "home":
                return Path(value.strip()).resolve()
    except OSError as exc:
        raise PythonRuntimeError(
            f"cannot read virtual-environment config: {exc}"
        ) from exc
    raise PythonRuntimeError("virtual-environment config has no base interpreter home")


def _dll_directories(base_directory: Path) -> list[str]:
    candidates = (
        base_directory,
        base_directory / "DLLs",
        base_directory / "Library" / "bin",
    )
    return [str(path.resolve()) for path in candidates if path.is_dir()]


def _startup_dll_source(base_directory: Path, name: str) -> Path | None:
    candidates = (base_directory / name, base_directory / "Library" / "bin" / name)
    return next((path.resolve() for path in candidates if path.is_file()), None)


def _copy_atomic(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_python_runtime(
    venv_root: Path, base_executable: Path, base_dll: Path
) -> Path:
    """Copy matching base runtime files into venv Scripts and record provenance."""
    venv_root = venv_root.resolve()
    scripts = venv_root / "Scripts"
    configuration = venv_root / "pyvenv.cfg"
    base_executable = base_executable.resolve()
    base_dll = base_dll.resolve()
    for path in (configuration, base_executable, base_dll):
        if not path.is_file():
            raise PythonRuntimeError(f"required Python runtime file is missing: {path}")
    if _venv_home(configuration) != base_executable.parent:
        raise PythonRuntimeError("base executable does not match pyvenv.cfg home")
    expected_dll = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
    if (
        base_dll.parent != base_executable.parent
        or base_dll.name.casefold() != expected_dll
    ):
        raise PythonRuntimeError("base DLL does not match the Python executable")
    scripts.mkdir(parents=True, exist_ok=True)
    wrapper = scripts / _WRAPPER
    venv_dll = scripts / base_dll.name
    _copy_atomic(base_executable, wrapper)
    _copy_atomic(base_dll, venv_dll)
    startup_dlls: list[dict[str, str]] = []
    for name in _STARTUP_DLL_NAMES:
        source = _startup_dll_source(base_executable.parent, name)
        if source is None:
            if name == "VCRUNTIME140.dll":
                raise PythonRuntimeError(
                    "matching base Python VCRUNTIME140.dll is unavailable"
                )
            if (scripts / name).exists():
                raise PythonRuntimeError(
                    f"unexpected prepared startup DLL without a base copy: {name}"
                )
            continue
        destination = scripts / name
        _copy_atomic(source, destination)
        if _digest(source) != _digest(destination):
            raise PythonRuntimeError(f"prepared startup DLL copy differs: {name}")
        startup_dlls.append(
            {
                "name": name,
                "base_path": str(source),
                "base_sha256": _digest(source),
                "venv_path": str(destination.resolve()),
                "venv_sha256": _digest(destination),
            }
        )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "venv_root": str(venv_root),
        "pyvenv_cfg": str(configuration.resolve()),
        "pyvenv_cfg_sha256": _digest(configuration),
        "base_executable": str(base_executable),
        "base_executable_sha256": _digest(base_executable),
        "base_dll": str(base_dll),
        "base_dll_sha256": _digest(base_dll),
        "wrapper_executable": str(wrapper.resolve()),
        "wrapper_executable_sha256": _digest(wrapper),
        "venv_dll": str(venv_dll.resolve()),
        "venv_dll_sha256": _digest(venv_dll),
        "startup_dlls": startup_dlls,
        "dll_directories": _dll_directories(base_executable.parent),
    }
    manifest_path = scripts / _MANIFEST
    temporary = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return wrapper


def _validate_manifest(scripts: Path) -> tuple[dict[str, Any], Path]:
    manifest_path = scripts / _MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PythonRuntimeError(
            f"prepared Python runtime manifest unavailable: {exc}"
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise PythonRuntimeError("prepared Python runtime manifest is invalid")

    def checked_file(path_key: str, digest_key: str) -> Path:
        raw_path, expected = manifest.get(path_key), manifest.get(digest_key)
        if not isinstance(raw_path, str) or not isinstance(expected, str):
            raise PythonRuntimeError(f"prepared Python runtime is missing {path_key}")
        path = Path(raw_path)
        if not path.is_absolute() or not path.is_file() or _digest(path) != expected:
            raise PythonRuntimeError(f"prepared Python runtime file changed: {path}")
        return path.resolve()

    wrapper = checked_file("wrapper_executable", "wrapper_executable_sha256")
    base_executable = checked_file("base_executable", "base_executable_sha256")
    checked_file("base_dll", "base_dll_sha256")
    venv_dll = checked_file("venv_dll", "venv_dll_sha256")
    configuration = checked_file("pyvenv_cfg", "pyvenv_cfg_sha256")
    root = scripts.parent.resolve()
    if (
        not isinstance(manifest.get("venv_root"), str)
        or Path(str(manifest.get("venv_root"))).resolve() != root
        or wrapper.parent != scripts.resolve()
        or wrapper.name != _WRAPPER
        or venv_dll.parent != scripts.resolve()
        or venv_dll.name.casefold() != "python311.dll"
        or configuration != root / "pyvenv.cfg"
        or _venv_home(configuration) != base_executable.parent
        or Path(str(manifest.get("base_dll"))).resolve().parent
        != base_executable.parent
        or Path(str(manifest.get("base_dll"))).name.casefold() != "python311.dll"
        or _digest(wrapper) != _digest(base_executable)
        or _digest(venv_dll) != _digest(Path(str(manifest.get("base_dll"))))
    ):
        raise PythonRuntimeError(
            "prepared Python runtime provenance does not match venv"
        )
    expected_startup_dlls: list[dict[str, str]] = []
    for name in _STARTUP_DLL_NAMES:
        source = _startup_dll_source(base_executable.parent, name)
        if source is None:
            if name == "VCRUNTIME140.dll":
                raise PythonRuntimeError(
                    "matching base Python VCRUNTIME140.dll is unavailable"
                )
            if (scripts.resolve() / name).exists():
                raise PythonRuntimeError(
                    f"unexpected prepared startup DLL without a base copy: {name}"
                )
            continue
        destination = scripts.resolve() / name
        expected_startup_dlls.append(
            {
                "name": name,
                "base_path": str(source),
                "base_sha256": _digest(source),
                "venv_path": str(destination),
                "venv_sha256": _digest(destination),
            }
        )
        if _digest(source) != _digest(destination):
            raise PythonRuntimeError(f"prepared startup DLL copy differs: {name}")
    if manifest.get("startup_dlls") != expected_startup_dlls:
        raise PythonRuntimeError("prepared Python startup DLL provenance is invalid")
    directories = manifest.get("dll_directories")
    expected_directories = _dll_directories(base_executable.parent)
    if directories != expected_directories:
        raise PythonRuntimeError("prepared Python runtime DLL directories are stale")
    return manifest, wrapper


def resolve_python_runtime(
    requested: Path | None = None,
) -> tuple[Path, tuple[str, ...]]:
    """Return a verified executable and its verified base-runtime DLL paths."""
    candidate = Path(requested or sys.executable).resolve()
    if (
        candidate.parent.name.casefold() != "scripts"
        or candidate.name.casefold()
        not in {
            "python.exe",
            "pythonw.exe",
            _WRAPPER,
        }
    ):
        raise PythonRuntimeError(
            "managed Python path is not in a venv Scripts directory"
        )
    if (
        sys.platform != "win32"
        or struct.calcsize("P") != 8
        or sysconfig.get_platform() != "win-amd64"
        or sys.version_info[:2] != (3, 11)
    ):
        raise PythonRuntimeError("CephVR managed Python requires 64-bit Windows")
    manifest, wrapper = _validate_manifest(candidate.parent)
    if candidate.name.casefold() == _WRAPPER and candidate != wrapper:
        raise PythonRuntimeError(
            "requested wrapper differs from the prepared executable"
        )
    directories = manifest["dll_directories"]
    if not isinstance(directories, list):
        raise PythonRuntimeError("prepared Python runtime DLL directories are invalid")
    return wrapper, tuple(str(item) for item in directories)


def resolve_python_executable(requested: Path | None = None) -> Path:
    """Resolve a venv Python path to its verified, real executable image."""
    return resolve_python_runtime(requested)[0]


def module_arguments(module: str, arguments: list[str]) -> list[str]:
    """Build argv for the entry module that retains base-runtime DLL handles."""
    return ["-m", "cephvr.platform.windows.python_entry", module, *arguments]


def prepare_current_runtime() -> Path:
    if (
        sys.platform != "win32"
        or struct.calcsize("P") != 8
        or sysconfig.get_platform() != "win-amd64"
        or sys.version_info[:2] != (3, 11)
    ):
        raise PythonRuntimeError(
            "CephVR managed Python preparation requires 64-bit Windows"
        )
    base_path = getattr(sys, "_base_executable", None)
    if not isinstance(base_path, str):
        raise PythonRuntimeError("base Python executable is unavailable")
    base_executable = Path(base_path).resolve()
    base_dll = (
        base_executable.parent
        / f"python{sys.version_info.major}{sys.version_info.minor}.dll"
    )
    return prepare_python_runtime(Path(sys.prefix), base_executable, base_dll)


def main() -> None:
    if sys.argv[1:] == ["--prepare"]:
        print(prepare_current_runtime())
    elif sys.argv[1:] == ["--verify"]:
        print(resolve_python_executable())
    else:
        raise SystemExit(
            "usage: python -m cephvr.platform.windows.python_runtime --prepare|--verify"
        )


if __name__ == "__main__":
    main()
