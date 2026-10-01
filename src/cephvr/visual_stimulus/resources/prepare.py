"""Concrete file-to-manifest provider stage used before program compilation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.config.models.program_model import Program
from cephvr.visual_stimulus.resources.arena import prepare_arena
from cephvr.visual_stimulus.resources.assets import (
    PreparedAssetSet,
    PreparedResourceBundle,
    ProtectedSource,
    prepare_assets,
)
from cephvr.visual_stimulus.resources.budget import PreparationBudget, arena_mesh_bytes
from cephvr.visual_stimulus.resources.calibration import prepare_calibration
from cephvr.visual_stimulus.resources.media import decode_image
from cephvr.visual_stimulus.resources.protected import ProtectedWindowsSource
from cephvr.visual_stimulus.resources.uniforms import build_uniform_layouts
from cephvr.visual_stimulus.resources.video_index import index_video


def _version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unavailable"


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
) -> PreparedResourceBundle:
    """Protect all source assets and return canonical manifest facts.

    The announced resource registration is completed before the Windows handle is
    acquired. Returned sources remain owned until the worker's cleanup receipt.
    """
    if video_index_limit_bytes <= 0 or glb_element_limit <= 0 or output_count <= 0:
        raise ValueError("video and GLB preparation limits must be positive")
    factory = source_factory or ProtectedWindowsSource
    source_set = prepare_assets(
        program,
        assets_root,
        budget,
        announce=announce,
        snapshot_limit_bytes=snapshot_limit_bytes,
        source_factory=factory,
        owner_prefix=owner_prefix,
        path_overrides=path_overrides,
    )
    try:
        from cephvr.visual_stimulus.config.models.artifact_models import (
            ComponentProvenance,
            Fingerprint,
            Interpretation,
            Resource,
            ResourceManifest,
        )

        entries: list[Resource] = []
        prepared_content: dict[str, object] = {}
        for source_asset in source_set.assets:
            budget.check_cancelled_or_expired()
            authored = next(
                item
                for item in program.assets
                if item.asset_id == source_asset.asset_id
            )
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

            if authored.profile in ("png_uint_v1", "tiff_uint_v1", "jpeg8_v1"):
                if source_asset.data is None:
                    raise MemoryError(
                        f"static asset {authored.asset_id} has no bounded source snapshot"
                    )
                image = decode_image(authored, source_asset.data, reserve=reserve_image)
                prepared_content[authored.asset_id] = image
                prepared_cpu_bytes = image.width * image.height * 64
                bits = image.pixels.dtype.itemsize * 8
                channel_bits = tuple(bits for _ in image.channel_order)
                interpretation = Interpretation(
                    interpretation_id=f"{authored.asset_id}-source-v1",
                    width=image.width,
                    height=image.height,
                    source_component_bits=channel_bits,
                    pixel_format=str(image.dtype),
                    channel_order=image.channel_order,
                    row_origin="top_left",
                    source_alpha=image.alpha,
                    transfer=image.transfer,
                    primaries="rec709_d65",
                    range=authored.color_override.range
                    if authored.color_override
                    else "full",
                    matrix=authored.color_override.matrix
                    if authored.color_override
                    else "rgb",
                    chroma_location=authored.color_override.chroma_location
                    if authored.color_override
                    else "none",
                    orientation_degrees=0,
                    mirror_x=False,
                    sample_aspect_numerator=1,
                    sample_aspect_denominator=1,
                    resolution_origin="explicit_override"
                    if authored.color_override
                    else "source_metadata",
                    effective_override_reason=authored.color_override.reason
                    if authored.color_override
                    else None,
                )
                gpu_bytes = image.width * image.height * 16 * output_count
                kind = "image"
                provider = "imagecodecs+tifffile-linear-premultiplied-v1"
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
                ComponentProvenance(
                    role="renderer",
                    implementation="CephVR",
                    version="2.0",
                    content_sha256=None,
                ),
                ComponentProvenance(
                    role="image_decoder",
                    implementation="imagecodecs",
                    version=_version("imagecodecs"),
                    content_sha256=None,
                ),
                ComponentProvenance(
                    role="image_decoder",
                    implementation="tifffile",
                    version=_version("tifffile"),
                    content_sha256=None,
                ),
                ComponentProvenance(
                    role="video_decoder",
                    implementation="PyAV",
                    version=_version("av"),
                    content_sha256=None,
                ),
                ComponentProvenance(
                    role="arena_importer",
                    implementation="cephvr.glb",
                    version="1",
                    content_sha256=None,
                ),
            ),
        )
        return PreparedResourceBundle(
            source_set,
            manifest,
            build_uniform_layouts(program, display),
            prepared_content,
        )
    except BaseException:
        source_set.close()
        budget.release(owner=f"{owner_prefix}:asset-snapshots")
        for source_asset in source_set.assets:
            budget.release(owner=f"{owner_prefix}:asset:{source_asset.asset_id}")
            budget.release(owner=f"{owner_prefix}:calibration:{source_asset.asset_id}")
        raise
