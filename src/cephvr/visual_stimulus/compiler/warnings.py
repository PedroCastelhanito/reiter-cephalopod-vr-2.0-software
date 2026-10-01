"""Conservative source-range warnings; actual clipping remains GPU evidence."""

from cephvr.visual_stimulus.config.models.program_model import (
    Constant,
    Keyframes,
    Number,
    Ramp,
    Ref,
    Settings,
    Sine,
    TextureSettings,
)


def _number(value: Number) -> float:
    if isinstance(value, Ref):
        raise ValueError("warning analysis requires resolved condition values")
    return float(value)


def predicts_color_excursion(settings: tuple[Settings, ...], duration_ns: int) -> bool:
    for setting in settings:
        if not isinstance(setting, TextureSettings):
            continue
        contrast = setting.contrast
        if isinstance(contrast, Constant):
            peak = _number(contrast.value)
        elif isinstance(contrast, Ramp):
            peak = max(
                _number(contrast.initial),
                _number(contrast.initial)
                + _number(contrast.slope_per_s) * duration_ns / 1e9,
            )
        elif isinstance(contrast, Sine):
            peak = _number(contrast.mean) + abs(_number(contrast.amplitude))
        elif isinstance(contrast, Keyframes):
            peak = max(_number(knot.value) for knot in contrast.knots)
        else:
            continue
        for mean, modulation in zip(
            setting.mean_linear_rgb, setting.modulation_linear_rgb, strict=True
        ):
            excursion = peak * abs(_number(modulation))
            if _number(mean) - excursion < 0 or _number(mean) + excursion > 1:
                return True
    return False
