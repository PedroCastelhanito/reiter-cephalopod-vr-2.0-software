"""Setup-only identities for software and the actual output graphics contexts."""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from cephvr.visual_stimulus.config.models.artifact_models import ComponentProvenance
from cephvr.visual_stimulus.rendering import shaders


def _version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unavailable"


def source_digest(root: Path, check: Callable[[], None]) -> str:
    """Hash relative names and source bytes, including uncommitted installed edits."""
    paths = sorted(root.rglob("*.py"))
    if not paths:
        raise ValueError("renderer source is unavailable for replay provenance")
    digest = hashlib.sha256()
    for path in paths:
        check()
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        content = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                check()
                content.update(chunk)
        digest.update(content.digest())
    return digest.hexdigest()


def software_provenance(check: Callable[[], None]) -> tuple[ComponentProvenance, ...]:
    """Collect once per Setup, never on the render/recording frame path."""
    root = Path(__file__).resolve().parents[1]
    digest = source_digest(root, check)
    result = [
        ComponentProvenance(
            role="renderer",
            implementation="cephvr.visual_stimulus.python-source-v1",
            version=_version("cephvr"),
            content_sha256=digest,
        ),
        ComponentProvenance(
            role="renderer",
            implementation="Python",
            version=platform.python_version(),
            content_sha256=None,
        ),
        ComponentProvenance(
            role="os",
            implementation=platform.system(),
            version=platform.version(),
            content_sha256=None,
        ),
        ComponentProvenance(
            role="color_transform",
            implementation="cephvr-linear-srgb-calibrated-output",
            version="1",
            content_sha256=digest,
        ),
        ComponentProvenance(
            role="arena_importer",
            implementation="cephvr.glb",
            version="1",
            content_sha256=digest,
        ),
        ComponentProvenance(
            role="image_decoder",
            implementation="cephvr1-compatible-raster",
            version="1",
            content_sha256=digest,
        ),
    ]
    for name, source in sorted(vars(shaders).items()):
        if isinstance(source, str) and source.startswith("#version "):
            result.append(
                ComponentProvenance(
                    role="shader",
                    implementation=f"cephvr.glsl.{name}",
                    version="1",
                    content_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                )
            )
    packages_by_role: tuple[
        tuple[Literal["renderer", "image_decoder", "video_decoder"], tuple[str, ...]],
        ...,
    ] = (
        ("renderer", ("numpy", "moderngl", "glcontext", "glfw", "PyOpenGL")),
        ("image_decoder", ("imagecodecs", "tifffile", "Pillow")),
        ("video_decoder", ("av",)),
    )
    for role, packages in packages_by_role:
        for package in packages:
            check()
            result.append(
                ComponentProvenance(
                    role=role,
                    implementation=package,
                    version=_version(package),
                    content_sha256=None,
                )
            )
    try:
        import av
    except ImportError:
        pass  # An unused optional video decoder is explicitly unavailable above.
    else:
        for library, library_version in sorted(av.library_versions.items()):
            result.append(
                ComponentProvenance(
                    role="video_decoder",
                    implementation=library,
                    version=".".join(map(str, library_version)),
                    content_sha256=None,
                )
            )
    return tuple(result)


def graphics_provenance(
    output_id: str, info: Mapping[str, object]
) -> tuple[ComponentProvenance, ...]:
    """Retain driver-supplied identity per output; missing facts reject preparation."""
    values = {}
    for key in ("GL_VENDOR", "GL_RENDERER", "GL_VERSION"):
        value = info.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{output_id}: missing graphics provenance {key}")
        values[key] = value
    return (
        ComponentProvenance(
            role="gpu",
            implementation=f"OpenGL output:{output_id}",
            version=json.dumps(
                {key: values[key] for key in ("GL_VENDOR", "GL_RENDERER")},
                sort_keys=True,
            ),
            content_sha256=None,
        ),
        ComponentProvenance(
            role="graphics_driver",
            implementation=f"OpenGL output:{output_id}",
            version=values["GL_VERSION"],
            content_sha256=None,
        ),
    )
