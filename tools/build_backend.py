"""Setuptools PEP 517 backend with generated bindings for every install/build.

Keep build mechanics outside the runtime package. Schemas are authoritative;
editable installs and wheels regenerate bindings with the pinned compiler.
"""

from __future__ import annotations

from typing import Any

from setuptools import build_meta


def __getattr__(name: str) -> Any:
    return getattr(build_meta, name)


def _generate() -> None:
    from generate_contracts import generate

    if generate() != 0:
        raise RuntimeError("Protobuf binding generation failed.")


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    _generate()
    return str(
        build_meta.build_wheel(wheel_directory, config_settings, metadata_directory)
    )


def build_editable(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    _generate()
    return str(
        build_meta.build_editable(wheel_directory, config_settings, metadata_directory)
    )
