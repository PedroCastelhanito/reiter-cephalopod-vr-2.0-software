"""Per-family builders for new stimulus layers in the accepted V03 program grammar."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

HOLD_MOTION = {key: {"kind": "hold"} for key in ("x", "y", "rotation")}
MEDIA_KEYS = (
    "instance_id",
    "space",
    "initial",
    "width",
    "height",
    "opacity",
    "motion",
    "reset",
    "assignments",
    "feedback",
)


@dataclass(frozen=True)
class LayerSeed:
    """A new layer setting plus its instance family and optional backing asset."""

    setting: dict[str, Any]
    family: str
    profile: str | None = None
    path: str = ""


def _physical_surface(source: dict[str, Any]) -> None:
    source["space"] = {
        "kind": "physical_surface",
        "frame_id": "rig",
        "mappings": [
            {"surface_id": face, "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]}
            for face in source["space"]["surfaces"]
        ],
    }


def _hold_phase(source: dict[str, Any]) -> None:
    source["phase_x"] = {"kind": "hold"}
    source["phase_y"] = {"kind": "hold"}


def _media(preset: str, source: dict[str, Any], identity: str, _: float) -> LayerSeed:
    family = "video" if preset == "Video" else "image"
    setting = {key: value for key, value in source.items() if key in MEDIA_KEYS}
    setting.update(kind=family, asset_id=identity, sampling="linear")
    if family == "video":
        setting.update(
            initial_playback={"seconds": "0"}, end_behavior="hold_final_frame"
        )
    if preset == "Image":
        setting["fit"] = "resize"
    if preset == "Looming image":
        curve = {
            "kind": "keyframes",
            "interpolation": "linear",
            "knots": [
                {"time": {"seconds": "0"}, "value": 1.0},
                {"time": {"seconds": "10"}, "value": 90.0},
            ],
        }
        setting.update(width=curve, height=deepcopy(curve))
    if preset == "Video":
        return LayerSeed(setting, family, "mp4_h264_sdr8_v1", "video.mp4")
    return LayerSeed(setting, family, "png_uint_v1", "image.png")


def _sparse_noise(_: str, source: dict[str, Any], *args: Any) -> LayerSeed:
    """Playback-generated noise: no asset; compilation replaces width/height (V04)."""
    setting = {key: value for key, value in source.items() if key in MEDIA_KEYS}
    extent = {"kind": "constant", "value": 100.0}
    setting.update(
        kind="sparse_noise",
        width=extent,
        height=deepcopy(extent),
        appearance=dict(
            format_version=2,
            kind="sparse_noise",
            seed=0,
            square_size_mm=5.0,
            min_active_cell_distance_mm=0.0,
            active_probability=0.2,
            background_linear=0.5,
        ),
        pattern_count=1,
        pattern_duration=None,
        motion=deepcopy(HOLD_MOTION),
        opacity={"kind": "constant", "value": 1.0},
    )
    _physical_surface(setting)
    return LayerSeed(setting, "sparse_noise")


def _arena(
    _: str, __: dict[str, Any], identity: str, subject_height_mm: float
) -> LayerSeed:
    identity_matrix = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
    setting = dict(
        kind="arena",
        instance_id=identity,
        asset_id=identity,
        world_frame_id="rig",
        asset_to_world=identity_matrix,
        initial={"position_mm": [0.0, 0.0], "yaw_deg": 0.0},
        fixed_height_mm=subject_height_mm,
        fixed_pitch_deg=0.0,
        fixed_roll_deg=0.0,
        motion={key: {"kind": "hold"} for key in ("x", "y", "yaw")},
        reset=False,
        assignments=[],
        feedback=[],
    )
    return LayerSeed(setting, "arena", "glb2_static_unlit_v1", "arena.glb")


def _image_tile_pattern(identity: str) -> dict[str, Any]:
    return {
        "kind": "image_tile",
        "asset_id": identity,
        "period_x": {"kind": "constant", "value": 20.0},
        "period_y": {"kind": "constant", "value": 20.0},
        "sampling": "linear",
    }


def _uniform(_: str, source: dict[str, Any], *args: Any) -> LayerSeed:
    source["uniform"] = True
    source["contrast"] = {"kind": "constant", "value": 0.0}
    source["motion"] = deepcopy(HOLD_MOTION)
    _physical_surface(source)
    _hold_phase(source)
    return LayerSeed(source, "texture")


def _grating(_: str, source: dict[str, Any], *args: Any) -> LayerSeed:
    from cephvr.visual_stimulus.config.parameter_edits import patch_setting

    source["grating"] = True
    source["motion"] = deepcopy(HOLD_MOTION)
    source["pattern"] = {
        "kind": "sine_grating",
        "frequency": {"kind": "constant", "value": 0.05},
        "feature_sharpness": 1.0,
    }
    _physical_surface(source)
    _hold_phase(source)
    patch_setting(source, {"Orientation": "0", "Speed": "0"}, rig_coordinates=True)
    return LayerSeed(source, "texture")


def _texture(preset: str, source: dict[str, Any], identity: str, _: float) -> LayerSeed:
    source["pattern"] = _image_tile_pattern(identity)
    if preset == "Texture":
        _physical_surface(source)
        _hold_phase(source)
    return LayerSeed(source, "texture", "png_uint_v1", "texture.png")


def _checkerboard(_: str, source: dict[str, Any], *args: Any) -> LayerSeed:
    source["pattern"] = {
        "kind": "checkerboard",
        "frequency_x": {"kind": "constant", "value": 0.05},
        "frequency_y": {"kind": "constant", "value": 0.05},
    }
    return LayerSeed(source, "texture")


def _square_grating(_: str, source: dict[str, Any], *args: Any) -> LayerSeed:
    source["pattern"]["kind"] = "square_grating"
    return LayerSeed(source, "texture")


def _sine_grating(_: str, source: dict[str, Any], *args: Any) -> LayerSeed:
    return LayerSeed(
        source, "texture"
    )  # The review template is already a sine grating.


_BUILDERS: dict[str, Callable[[str, dict[str, Any], str, float], LayerSeed]] = {
    "Image": _media,
    "Looming image": _media,
    "Video": _media,
    "Sparse noise": _sparse_noise,
    "3D arena": _arena,
    "Uniform": _uniform,
    "Checkerboard": _checkerboard,
    "Square grating": _square_grating,
    "Grating": _grating,
    "Image tile": _texture,
    "Texture": _texture,
    "Sine grating": _sine_grating,
}


def new_layer(
    preset: str, source: dict[str, Any], identity: str, subject_height_mm: float
) -> LayerSeed:
    """Build one layer from the review template ``source``; ``preset`` is validated."""
    return _BUILDERS[preset](preset, source, identity, subject_height_mm)
