"""Concrete file-to-manifest provider stage used before program compilation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Literal

from cephvr.platform.windows.protected_source import ProtectedWindowsSource
from cephvr.visual_stimulus.config.models.artifact_models import ComponentProvenance
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.resources.arena import prepare_arena
from cephvr.visual_stimulus.resources.assets import (
    RELOADABLE_IMAGE_PROFILES,
    PreparedAssetSet,
    PreparedResourceBundle,
    ProtectedSource,
    prepare_assets,
)
from cephvr.visual_stimulus.resources.budget import PreparationBudget, arena_mesh_bytes
from cephvr.visual_stimulus.resources.calibration import prepare_calibration
from cephvr.visual_stimulus.resources.image_interpretation import (
    image_interpretation,
    image_validation_key,
)
from cephvr.visual_stimulus.resources.media import decode_image
from cephvr.visual_stimulus.resources.provenance import software_provenance
from cephvr.visual_stimulus.resources.recipe_dependencies import (
    decode_recipe_image,
    image_dependency,
)
from cephvr.visual_stimulus.resources.recipe_preparation import prepare_recipe_image
from cephvr.visual_stimulus.resources.texture_recipe import parse_texture_recipe
from cephvr.visual_stimulus.resources.uniforms import build_uniform_layouts
from cephvr.visual_stimulus.resources.video_index import index_video

if TYPE_CHECKING:
    from cephvr.visual_stimulus.resources.image_source import ImageInfo, ImageSource


def prepare_resources(
    program: Program,
    assets_root: Path,
    budget: PreparationBudget,
    *,
    announce: Callable[[str, str | None], None],
    snapshot_limit_bytes: int,
    video_index_limit_bytes: int,
    glb_element_limit: int,
    output_count: int = 1,
    owner_prefix: str = "visual_stimulus",
    display: DisplayProfile | None = None,
    max_document_bytes: int | None = None,
    source_factory: Callable[[Path], ProtectedSource] | None = None,
    codec_threads: int = 1,
    path_overrides: Mapping[str, Path] | None = None,
    defer_images: bool = False,
    component_provenance: tuple[ComponentProvenance, ...] | None = None,
    validated_images: dict[str, tuple[ImageSource, ImageInfo]] | None = None,
) -> PreparedResourceBundle:
    """Protect all source assets and return canonical manifest facts.

    The announced resource registration is completed before the Windows handle is
    acquired. Returned sources remain owned until the worker's cleanup receipt.
    """
    if video_index_limit_bytes <= 0 or glb_element_limit <= 0 or output_count <= 0:
        raise ValueError("video and GLB preparation limits must be positive")
    factory = source_factory or ProtectedWindowsSource
    validation_cache = {} if validated_images is None else validated_images
    new_validation_keys: list[str] = []
    source_set = prepare_assets(
        program,
        assets_root,
        budget,
        announce=announce,
        snapshot_limit_bytes=snapshot_limit_bytes,
        source_factory=factory,
        owner_prefix=owner_prefix,
        path_overrides=path_overrides,
        max_document_bytes=max_document_bytes,
        defer_images=defer_images,
    )
    try:
        from cephvr.visual_stimulus.config.models.artifact_models import (
            Fingerprint,
            Interpretation,
            Resource,
            ResourceManifest,
        )

        recipes = {}
        authored_by_id = {item.asset_id: item for item in program.assets}
        metadata_bytes = {
            item.asset_id: 4096 + 4 * len(item.model_dump_json().encode("utf-8"))
            for item in program.assets
            if defer_images and item.profile in RELOADABLE_IMAGE_PROFILES
        }
        if defer_images:
            budget.reserve(
                owner=f"{owner_prefix}:image-metadata",
                cpu_bytes=sum(metadata_bytes.values()),
                gpu_bytes=0,
            )
        recipe_images = {}
        dependencies_to_prepare = []
        for source_asset in source_set.assets:
            authored = authored_by_id[source_asset.asset_id]
            if authored.profile != "cephvr1_texture_json_v1":
                continue
            if defer_images:
                from cephvr.visual_stimulus.resources.image_source import (
                    read_source_bytes,
                )

                parse_owner = f"{owner_prefix}:recipe-parse"
                budget.reserve(
                    owner=parse_owner,
                    cpu_bytes=source_asset.byte_count * 32,
                    gpu_bytes=0,
                )
                try:
                    raw = read_source_bytes(
                        source_asset, budget.check_cancelled_or_expired
                    )
                    recipe = parse_texture_recipe(
                        raw,
                        max_document_bytes=max_document_bytes or snapshot_limit_bytes,
                    )
                    dependency = image_dependency(assets_root, authored, recipe)
                    del raw, recipe
                finally:
                    budget.release(owner=parse_owner)
            else:
                assert source_asset.data is not None
                recipe = parse_texture_recipe(
                    source_asset.data,
                    max_document_bytes=max_document_bytes or snapshot_limit_bytes,
                )
                recipes[authored.asset_id] = recipe
                dependency = image_dependency(assets_root, authored, recipe)
            if dependency is not None:
                if dependency.asset_id in authored_by_id:
                    raise ValueError(
                        "recipe image dependency identity collides with an authored asset"
                    )
                authored_by_id[dependency.asset_id] = dependency
                if defer_images:
                    metadata_bytes[dependency.asset_id] = 4096 + 4 * len(
                        dependency.model_dump_json().encode("utf-8")
                    )
                    budget.reserve(
                        owner=f"{owner_prefix}:image-metadata",
                        cpu_bytes=sum(metadata_bytes.values()),
                        gpu_bytes=0,
                    )
                recipe_images[authored.asset_id] = dependency.asset_id
                dependencies_to_prepare.append(dependency)
        if dependencies_to_prepare:
            dependency_set = prepare_assets(
                SimpleNamespace(assets=tuple(dependencies_to_prepare)),
                assets_root,
                budget,
                announce=announce,
                snapshot_limit_bytes=snapshot_limit_bytes,
                source_factory=factory,
                owner_prefix=f"{owner_prefix}:recipe-dependencies",
                defer_images=defer_images,
            )
            source_set = PreparedAssetSet(
                (*source_set.assets, *dependency_set.assets),
                source_set.cpu_bytes + dependency_set.cpu_bytes,
            )
            budget.release(owner=f"{owner_prefix}:recipe-dependencies:asset-snapshots")
            budget.reserve(
                owner=f"{owner_prefix}:asset-snapshots",
                cpu_bytes=source_set.cpu_bytes,
                gpu_bytes=0,
            )
        entries: list[Resource] = []
        prepared_content: dict[str, object] = {}
        image_sources = {}
        dependency_ids = frozenset(item.asset_id for item in dependencies_to_prepare)
        sources_by_id = source_set.by_id()
        recipe_dependency_content = {}
        for dependency in dependencies_to_prepare:
            if defer_images:
                continue
            source = sources_by_id[dependency.asset_id]
            assert source.data is not None

            def reserve_dependency_image(
                width: int,
                height: int,
                channels: int,
                bits: int,
                *,
                identity: str = dependency.asset_id,
            ) -> None:
                budget.reserve(
                    owner=f"{owner_prefix}:asset:{identity}",
                    cpu_bytes=width * height * 64,
                    gpu_bytes=0,
                )

            recipe_dependency_content[dependency.asset_id] = decode_recipe_image(
                dependency,
                source.data,
                reserve_dependency_image,
            )
        for source_asset in source_set.assets:
            budget.check_cancelled_or_expired()
            authored = authored_by_id[source_asset.asset_id]
            interpretation = None
            cpu_bytes = source_asset.byte_count
            prepared_cpu_bytes = 0
            gpu_bytes = 0
            kind: Literal["image", "video", "arena"]
            dependencies: tuple[str, ...] = ()

            def reserve_image(
                width: int,
                height: int,
                channels: int,
                bits: int,
                *,
                asset_id: str = authored.asset_id,
            ) -> None:
                budget.reserve(
                    owner=f"{owner_prefix}:asset:{asset_id}",
                    cpu_bytes=width * height * 64,
                    gpu_bytes=width * height * 16 * output_count,
                )

            if authored.asset_id in dependency_ids:
                # Dependency bytes are replay inputs; only the generated recipe
                # has a renderer interpretation and resident image allocation.
                kind = "image"
                provider = "Pillow-cephvr1-rgb8-input-v1"
                recipe_dependency_content.pop(authored.asset_id, None)
                if defer_images:
                    cpu_bytes = metadata_bytes[authored.asset_id]
            elif defer_images and authored.profile in RELOADABLE_IMAGE_PROFILES:
                from cephvr.visual_stimulus.resources.image_source import (
                    validate_image_source,
                )

                dependency_id = recipe_images.get(authored.asset_id)
                if dependency_id is not None:
                    dependencies = (dependency_id,)
                dependency_asset = (
                    authored_by_id[dependency_id] if dependency_id is not None else None
                )
                dependency_source = (
                    sources_by_id[dependency_id] if dependency_id is not None else None
                )
                validation_key = image_validation_key(
                    authored,
                    source_asset,
                    display=display,
                    output_count=output_count,
                    dependency_asset=dependency_asset,
                    dependency_source=dependency_source,
                )
                if validation_key not in validation_cache:
                    validation_cache[validation_key] = validate_image_source(
                        authored,
                        source_asset,
                        budget=budget,
                        owner=f"{owner_prefix}:image-validation",
                        output_count=output_count,
                        max_document_bytes=max_document_bytes or snapshot_limit_bytes,
                        display=display,
                        dependency_asset=dependency_asset,
                        dependency_source=dependency_source,
                    )
                    new_validation_keys.append(validation_key)
                image_source, info = validation_cache[validation_key]
                image_sources[authored.asset_id] = image_source
                interpretation = image_interpretation(authored, info)
                kind = "image"
                provider = (
                    "cephvr1-texture-raster-v1"
                    if authored.profile == "cephvr1_texture_json_v1"
                    else "imagecodecs+tifffile-linear-premultiplied-v1"
                )
                cpu_bytes = metadata_bytes[authored.asset_id]
                # Residency admits this peak separately when a protected source
                # is decoded/uploaded, rather than retaining every validated image.
                gpu_bytes = 0
            elif authored.profile in (
                "png_uint_v1",
                "tiff_uint_v1",
                "jpeg8_v1",
                "cephvr1_texture_json_v1",
            ):
                if source_asset.data is None:
                    raise MemoryError(
                        f"static asset {authored.asset_id} has no bounded source snapshot"
                    )
                if authored.profile == "cephvr1_texture_json_v1":
                    recipe = recipes[authored.asset_id]
                    image_input = None
                    if authored.asset_id in recipe_images:
                        dependency_id = recipe_images[authored.asset_id]
                        dependencies = (dependency_id,)
                        image_input = recipe_dependency_content[dependency_id].pixels
                    image = prepare_recipe_image(
                        authored,
                        recipe,
                        budget,
                        owner=f"{owner_prefix}:asset:{authored.asset_id}",
                        output_count=output_count,
                        display=display,
                        image_pixels=image_input,
                    )
                    del image_input
                else:
                    image = decode_image(
                        authored, source_asset.data, reserve=reserve_image
                    )
                prepared_content[authored.asset_id] = image
                prepared_cpu_bytes = image.width * image.height * 64
                interpretation = image_interpretation(authored, image)
                gpu_bytes = image.width * image.height * 16 * output_count
                kind = "image"
                provider = (
                    "cephvr1-texture-raster-v1"
                    if authored.profile == "cephvr1_texture_json_v1"
                    else "imagecodecs+tifffile-linear-premultiplied-v1"
                )
            elif authored.profile in ("mp4_h264_sdr8_v1", "matroska_ffv1_v3_uint_v1"):
                video = index_video(
                    authored,
                    source_asset.source,
                    max_index_bytes=video_index_limit_bytes,
                    codec_threads=codec_threads,
                    check=budget.check_cancelled_or_expired,
                    reserve=reserve_image,
                )
                prepared_content[authored.asset_id] = video
                if authored.color_override is None:
                    raise ValueError(
                        f"video {authored.asset_id} has no explicit supported color interpretation"
                    )
                interpretation = Interpretation(
                    interpretation_id=f"{authored.asset_id}-source-v1",
                    width=video.width,
                    height=video.height,
                    source_component_bits=video.component_bits,
                    pixel_format=video.pixel_format,
                    channel_order=video.channel_order,
                    row_origin="top_left",
                    source_alpha=video.source_alpha,
                    transfer=authored.color_override.transfer,
                    primaries=authored.color_override.primaries,
                    range=video.color_range,
                    matrix=video.matrix,
                    chroma_location=video.chroma_location,
                    orientation_degrees=0,
                    mirror_x=False,
                    sample_aspect_numerator=1,
                    sample_aspect_denominator=1,
                    resolution_origin="explicit_override",
                    effective_override_reason=authored.color_override.reason,
                )
                prepared_cpu_bytes = (
                    len(video.frames) * 256 + video.width * video.height * 64
                )
                gpu_bytes = video.width * video.height * 16 * output_count
                kind = "video"
                provider = "pyav-index-v1"
            elif authored.profile == "glb2_static_unlit_v1":
                if source_asset.data is None:
                    raise MemoryError(
                        f"GLB asset {authored.asset_id} exceeds bounded importer input"
                    )
                arena = prepare_arena(
                    authored,
                    source_asset,
                    assets_root,
                    budget,
                    announce=announce,
                    source_factory=factory,
                    max_bytes=snapshot_limit_bytes,
                    max_elements=glb_element_limit,
                    owner_prefix=owner_prefix,
                    output_count=output_count,
                    path_overrides=path_overrides,
                )
                scene = arena.scene
                source_set = PreparedAssetSet(
                    (*source_set.assets, *arena.sources),
                    source_set.cpu_bytes
                    + sum(item.byte_count for item in arena.sources),
                )
                entries.extend(arena.resources)
                dependencies = tuple(
                    item.fingerprint.resource_id for item in arena.resources
                )
                prepared_content.update(arena.textures)
                prepared_content[authored.asset_id] = scene
                vertex_bytes = 0
                for node in scene.nodes:
                    for primitive in node.primitives:
                        vertex_bytes += len(primitive.positions) * 12
                        vertex_bytes += len(primitive.indices) * 4
                        if primitive.texcoords is not None:
                            vertex_bytes += len(primitive.texcoords) * 8
                        if primitive.colors is not None:
                            vertex_bytes += (
                                sum(len(color) for color in primitive.colors) * 4
                            )
                gpu_bytes = sum(
                    arena_mesh_bytes(len(primitive.positions), len(primitive.indices))
                    for node in scene.nodes
                    for primitive in node.primitives
                )
                prepared_cpu_bytes = vertex_bytes
                gpu_bytes *= output_count
                kind = "arena"
                provider = "glb2-static-unlit-v1"
            else:
                raise ValueError(
                    f"unsupported declared asset profile {authored.profile!r}"
                )
            budget.reserve(
                owner=f"{owner_prefix}:asset:{authored.asset_id}",
                cpu_bytes=prepared_cpu_bytes,
                gpu_bytes=gpu_bytes,
            )
            entries.append(
                Resource(
                    fingerprint=Fingerprint(
                        resource_id=authored.asset_id,
                        logical_path=authored.logical_path,
                        subresource=None,
                        sha256=source_asset.sha256,
                        bytes=source_asset.byte_count,
                    ),
                    kind=kind,
                    profile_id=authored.profile,
                    dependencies=dependencies,
                    interpretation=interpretation,
                    cpu_bytes=cpu_bytes + prepared_cpu_bytes,
                    gpu_bytes=gpu_bytes,
                    provider_compatibility=provider,
                )
            )
        if display is not None:
            calibration = prepare_calibration(
                display,
                assets_root,
                announce=announce,
                budget=budget,
                max_document_bytes=max_document_bytes or snapshot_limit_bytes,
                owner_prefix=owner_prefix,
                source_factory=source_factory or ProtectedWindowsSource,
                path_overrides=path_overrides,
            )
            existing_ids = {item.fingerprint.resource_id for item in entries}
            calibration_ids = {
                item.fingerprint.resource_id for item in calibration.resources
            }
            source_set = type(source_set)(
                (*source_set.assets, *calibration.assets),
                source_set.cpu_bytes
                + sum(asset.byte_count for asset in calibration.assets),
            )
            if existing_ids & calibration_ids:
                raise ValueError("authored assets and display calibration IDs collide")
            entries.extend(calibration.resources)
            prepared_content.update(calibration.content)
        manifest = ResourceManifest(
            format_version=1,
            resources=tuple(entries),
            provenance=(
                component_provenance
                if component_provenance is not None
                else software_provenance(budget.check_cancelled_or_expired)
            ),
        )
        return PreparedResourceBundle(
            source_set,
            manifest,
            build_uniform_layouts(program, display),
            prepared_content,
            image_sources,
        )
    except BaseException:
        for key in new_validation_keys:
            validation_cache.pop(key, None)
        source_set.close()
        budget.release(owner=f"{owner_prefix}:asset-snapshots")
        budget.release(owner=f"{owner_prefix}:recipe-dependencies:asset-snapshots")
        budget.release(owner=f"{owner_prefix}:image-metadata")
        for source_asset in source_set.assets:
            budget.release(owner=f"{owner_prefix}:asset:{source_asset.asset_id}")
            budget.release(owner=f"{owner_prefix}:calibration:{source_asset.asset_id}")
        raise
