"""Prepared base-color-only glTF materials and bounded texture source resolution."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class GLBTexture:
    image: bytes
    mime_type: Literal["image/png", "image/jpeg"]
    subresource: str
    wrap_s: int
    wrap_t: int
    min_filter: int
    mag_filter: int


@dataclass(frozen=True, slots=True)
class GLBMaterial:
    base_color_factor: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    texture_index: int | None = None
    alpha_mode: str = "OPAQUE"
    alpha_cutoff: float = 0.5
    double_sided: bool = False


def prepare_materials(
    document: dict[str, Any],
    read_view: Callable[[int], bytes],
    resolve: Callable[[str], bytes] | None,
    *,
    max_bytes: int,
) -> tuple[tuple[GLBMaterial, ...], tuple[GLBTexture, ...]]:
    import math

    textures = []
    images = document.get("images", [])
    samplers = document.get("samplers", [])
    for texture in document.get("textures", []):
        if texture.get("extensions"):
            raise ValueError("unsupported texture extension")
        source = texture.get("source")
        if type(source) is not int or not 0 <= source < len(images):
            raise ValueError("texture image reference is invalid")
        image = images[source]
        if "bufferView" in image and "uri" not in image:
            data = read_view(image["bufferView"])
        elif "uri" in image and "bufferView" not in image and resolve is not None:
            data = resolve(image["uri"])
        else:
            raise ValueError("image requires one protected local source")
        if len(data) > max_bytes:
            raise MemoryError("GLB texture source exceeds preparation bound")
        mime: Literal["image/png", "image/jpeg"]
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif data.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        else:
            raise ValueError("GLB texture must contain PNG or JPEG")
        if image.get("mimeType", mime) != mime:
            raise ValueError("GLB texture MIME disagrees with its content")
        index = texture.get("sampler")
        if index is not None and (
            type(index) is not int or not 0 <= index < len(samplers)
        ):
            raise ValueError("texture sampler reference is invalid")
        sampler = {} if index is None else samplers[index]
        wrap_s, wrap_t = sampler.get("wrapS", 10497), sampler.get("wrapT", 10497)
        minimum, maximum = (
            sampler.get("minFilter", 9987),
            sampler.get("magFilter", 9729),
        )
        if (
            wrap_s not in (10497, 33071, 33648)
            or wrap_t not in (10497, 33071, 33648)
            or minimum not in (9728, 9729, 9984, 9985, 9986, 9987)
            or maximum not in (9728, 9729)
        ):
            raise ValueError("unsupported glTF sampler mode")
        textures.append(
            GLBTexture(data, mime, f"images/{source}", wrap_s, wrap_t, minimum, maximum)
        )
    materials = []
    for material in document.get("materials", []):
        extensions = material.get("extensions", {})
        if set(extensions) - {"KHR_materials_unlit"}:
            raise ValueError("material extension requires unsupported appearance")
        pbr = material.get("pbrMetallicRoughness", {})
        unlit = "KHR_materials_unlit" in extensions
        if (
            any(
                key in material
                for key in ("normalTexture", "occlusionTexture", "emissiveTexture")
            )
            or any(value != 0 for value in material.get("emissiveFactor", (0, 0, 0)))
            or "metallicRoughnessTexture" in pbr
            or (
                not unlit
                and (
                    pbr.get("metallicFactor", 1) != 1
                    or pbr.get("roughnessFactor", 1) != 1
                )
            )
        ):
            raise ValueError("lit/PBR appearance must be baked into base color")
        rgba = pbr.get("baseColorFactor", (1, 1, 1, 1))
        if len(rgba) != 4 or any(
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in rgba
        ):
            raise ValueError("invalid glTF base-color factor")
        alpha_mode = material.get("alphaMode", "OPAQUE")
        cutoff = material.get("alphaCutoff", 0.5)
        double_sided = material.get("doubleSided", False)
        if (
            alpha_mode not in ("OPAQUE", "MASK")
            or type(double_sided) is not bool
            or not isinstance(cutoff, (int, float))
            or not math.isfinite(cutoff)
            or cutoff < 0
        ):
            raise ValueError("invalid or unsupported material coverage")
        reference = pbr.get("baseColorTexture")
        texture_index = None
        if reference is not None:
            texture_index = reference.get("index")
            if (
                type(texture_index) is not int
                or not 0 <= texture_index < len(textures)
                or reference.get("texCoord", 0) != 0
                or reference.get("extensions")
            ):
                raise ValueError(
                    "base-color texture requires unsupported UV interpretation"
                )
        materials.append(
            GLBMaterial(
                (float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3])),
                texture_index,
                alpha_mode,
                float(cutoff),
                double_sided,
            )
        )
    return tuple(materials), tuple(textures)
