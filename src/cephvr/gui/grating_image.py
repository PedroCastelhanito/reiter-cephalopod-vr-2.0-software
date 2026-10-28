"""Reduced-resolution preview of the renderer's centered physical grating."""

import numpy as np
from PyQt6.QtGui import QImage

from cephvr.visual_stimulus.config.models.program_model import Grating, TextureSettings


def grating_image(setting: TextureSettings, values: dict[str, float]) -> QImage:
    assert isinstance(setting.pattern, Grating)
    x = ((np.arange(512) + 0.5) / 512 - 0.5) * values["width"]
    cycles = values["frequency"] * x + values["phase_x"]
    alpha = 0.5 + 0.5 * np.cos(2 * np.pi * cycles)
    sharpness = setting.pattern.feature_sharpness
    edge = 0.5 * (1 - sharpness)
    if edge <= 0:
        mask = (alpha >= 0.5).astype(float)
    else:
        t = np.clip((alpha - 0.5 + edge) / (2 * edge), 0, 1)
        mask = t * t * (3 - 2 * t)
    signal = 2 * ((1 - sharpness) * alpha + sharpness * mask) - 1
    mean = np.asarray(setting.mean_linear_rgb, dtype=float)
    modulation = np.asarray(setting.modulation_linear_rgb, dtype=float)
    rgb = np.clip(
        mean + values.get("contrast", 1) * signal[..., None] * modulation,
        0,
        1,
    )
    encoded = np.where(
        rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.power(rgb, 1 / 2.4) - 0.055
    )
    pixels = np.rint(encoded * 255).astype(np.uint8)
    pixels = np.repeat(pixels[None, :, :], 4, axis=0)
    return QImage(pixels.tobytes(), 512, 4, 512 * 3, QImage.Format.Format_RGB888).copy()
