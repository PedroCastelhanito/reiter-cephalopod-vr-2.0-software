"""Shared reference-column names and canonical batch parameter keys."""

from cephvr.visual_stimulus.config.models.program_model import Settings


def is_sparse_noise(setting: Settings) -> bool:
    return setting.kind == "sparse_noise"


def stimulus_columns(setting: Settings) -> tuple[tuple[str, str], ...]:
    if setting.kind == "texture" and setting.uniform:
        return ()
    if is_sparse_noise(setting):
        return ()
    if setting.kind == "texture" and setting.grating:
        return (("Orientation (°)", "Orientation"), ("Speed (mm/s)", "Speed"))
    if setting.kind == "arena":
        return (
            ("Longitudinal", "Longitudinal"),
            ("Lateral", "Lateral"),
            ("Angular", "Angular"),
        )
    unit = "mm" if setting.space.kind == "physical_surface" else "°"
    if setting.kind == "image" and setting.width.kind == "keyframes":
        return (
            (f"Start ({unit})", "Start size"),
            (f"End ({unit})", "End size"),
            ("Growth (s)", "Growth duration"),
        )
    if setting.kind == "video":
        return (("Start (s)", "Playback start"), ("At end", "At end"))
    if setting.kind == "image":
        return (
            ("Fit", "Fit"),
            (f"Move speed ({unit}/s)", "Speed"),
            ("Direction (°)", "Direction"),
        )
    return (
        (f"Speed ({unit}/s)", "Speed"),
        ("Direction (°)", "Direction"),
        ("Rotation (°/s)", "Angular speed"),
    )
