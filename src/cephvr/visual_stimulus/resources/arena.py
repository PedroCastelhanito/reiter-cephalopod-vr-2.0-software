"""Protected arena dependencies and decoded base-color textures for GPU preparation."""

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit

from cephvr.visual_stimulus.config.models.artifact_models import (
    Fingerprint,
    Interpretation,
    Resource,
)
from cephvr.visual_stimulus.config.models.program_model import Asset, ColorOverride

from .assets import PreparedAsset, PreparedAssetSet, ProtectedSource, prepare_assets
from .budget import PreparationBudget, arena_texture_bytes
from .glb import GLBScene, parse_glb
from .media import ImagePixels, decode_image


@dataclass(frozen=True)
class AssetInputs:
    assets: tuple[Asset, ...]


@dataclass(frozen=True)
class ArenaPreparation:
    scene: GLBScene
    sources: tuple[PreparedAsset, ...]
    resources: tuple[Resource, ...]
    textures: dict[str, ImagePixels]


def prepare_arena(
    authored: Asset,
    source: PreparedAsset,
    root: Path,
    budget: PreparationBudget,
    *,
    announce: Callable[[str, str | None], None],
    source_factory: Callable[[Path], ProtectedSource],
    max_bytes: int,
    max_elements: int,
    owner_prefix: str,
    output_count: int,
    path_overrides: Mapping[str, Path] | None = None,
) -> ArenaPreparation:
    if source.data is None:
        raise ValueError("arena requires retained immutable container bytes")
    dependencies: dict[str, PreparedAsset] = {}
    resources: list[Resource] = []

    def resolve(uri: str) -> bytes:
        parts = urlsplit(uri)
        decoded = unquote(parts.path)
        relative = PurePosixPath(decoded)
        if (
            parts.scheme
            or parts.netloc
            or parts.query
            or parts.fragment
            or relative.is_absolute()
            or "\\" in decoded
            or any(p in ("..", ".") for p in relative.parts)
        ):
            raise ValueError(
                "arena dependencies must be protected local relative paths"
            )
        logical = str(PurePosixPath(authored.logical_path).parent / relative)
        if logical in dependencies:
            data = dependencies[logical].data
            assert data is not None
            return data
        resource_id = f"{authored.asset_id}:dependency:{len(dependencies)}"
        dependency = Asset(
            asset_id=resource_id,
            logical_path=logical,
            profile="glb2_static_unlit_v1",
            color_override=None,
        )
        acquired = prepare_assets(
            AssetInputs((dependency,)),
            root,
            budget,
            announce=announce,
            source_factory=source_factory,
            snapshot_limit_bytes=max_bytes,
            owner_prefix=f"{owner_prefix}:{resource_id}",
            path_overrides=path_overrides,
        ).assets[0]
        dependencies[logical] = acquired
        resources.append(
            Resource(
                fingerprint=Fingerprint(
                    resource_id=resource_id,
                    logical_path=logical,
                    subresource=None,
                    sha256=acquired.sha256,
                    bytes=acquired.byte_count,
                ),
                kind="arena",
                profile_id="gltf2_local_dependency_v1",
                dependencies=(),
                interpretation=None,
                cpu_bytes=acquired.byte_count,
                gpu_bytes=0,
                provider_compatibility="glb2-static-unlit-v1",
            )
        )
        assert acquired.data is not None
        return acquired.data

    try:
        scene = parse_glb(
            source.data,
            max_bytes=max_bytes,
            max_elements=max_elements,
            resolve=resolve,
            reserve_workspace=lambda count: budget.reserve(
                owner=f"{owner_prefix}:{authored.asset_id}:arena-workspace",
                cpu_bytes=count,
                gpu_bytes=0,
            ),
        )
        textures = {}
        for index, texture in enumerate(scene.textures):
            budget.check_cancelled_or_expired()
            key = f"{authored.asset_id}:texture:{index}"

            def reserve(
                width: int,
                height: int,
                channels: int,
                bits: int,
                *,
                resource_id: str = key,
                mipmapped: bool = texture.min_filter in (9984, 9985, 9986, 9987),
            ) -> None:
                budget.reserve(
                    owner=f"{owner_prefix}:{resource_id}",
                    cpu_bytes=width * height * 64,
                    gpu_bytes=arena_texture_bytes(width, height, mipmapped=mipmapped)
                    * output_count,
                )

            profile: Literal["png_uint_v1", "jpeg8_v1"] = (
                "png_uint_v1" if texture.mime_type == "image/png" else "jpeg8_v1"
            )
            pixels = decode_image(
                Asset(
                    asset_id=key,
                    logical_path=authored.logical_path,
                    profile=profile,
                    color_override=ColorOverride(
                        transfer="srgb",
                        primaries="rec709_d65",
                        range="full",
                        matrix="rgb",
                        chroma_location="none",
                        reason="glTF base-color texture interpretation",
                    ),
                ),
                texture.image,
                reserve=reserve,
            )
            textures[key] = pixels
            resources.append(
                Resource(
                    fingerprint=Fingerprint(
                        resource_id=key,
                        logical_path=authored.logical_path,
                        subresource=f"textures/{index}",
                        sha256=hashlib.sha256(texture.image).hexdigest(),
                        bytes=len(texture.image),
                    ),
                    kind="image",
                    profile_id=profile,
                    dependencies=tuple(item.asset_id for item in dependencies.values()),
                    interpretation=Interpretation(
                        interpretation_id=f"{key}:source",
                        width=pixels.width,
                        height=pixels.height,
                        source_component_bits=tuple(
                            pixels.pixels.dtype.itemsize * 8
                            for _ in pixels.channel_order
                        ),
                        pixel_format=pixels.dtype,
                        channel_order=pixels.channel_order,
                        row_origin="top_left",
                        source_alpha=pixels.alpha,
                        transfer="srgb",
                        primaries="rec709_d65",
                        range="full",
                        matrix="rgb",
                        chroma_location="none",
                        orientation_degrees=0,
                        mirror_x=False,
                        sample_aspect_numerator=1,
                        sample_aspect_denominator=1,
                        resolution_origin="gltf_base_color",
                        effective_override_reason=None,
                    ),
                    cpu_bytes=int(pixels.pixels.nbytes),
                    gpu_bytes=arena_texture_bytes(
                        pixels.width,
                        pixels.height,
                        mipmapped=texture.min_filter in (9984, 9985, 9986, 9987),
                    )
                    * output_count,
                    provider_compatibility="glb2-static-unlit-v1",
                )
            )
        return ArenaPreparation(
            scene, tuple(dependencies.values()), tuple(resources), textures
        )
    except BaseException:
        PreparedAssetSet(tuple(dependencies.values()), 0).close()
        raise
