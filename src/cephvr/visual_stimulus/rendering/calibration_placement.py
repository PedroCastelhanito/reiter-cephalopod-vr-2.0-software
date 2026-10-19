"""Native-pixel placement previews using the existing diagnostic framebuffer."""

from typing import Any

from cephvr.visual_stimulus.config.calibration_placement import CalibrationPlacement


def draw_placement(
    context: Any,
    frame: Any,
    view: str,
    output_id: str,
    placement: CalibrationPlacement,
    pulse_high: bool = True,
) -> None:
    frame.device_fbo.use()
    context.viewport = (0, 0, frame.width, frame.height)
    context.scissor = None
    background = 0.25 if view == "blackout_placement" else 0.0
    frame.device_fbo.clear(background, background, background, 1.0)
    try:
        output = next(item for item in placement.outputs if item.output_id == output_id)
        rectangles = [(rect, 0.0) for rect in output.blackout_zones]
        patch = placement.marker_patches.get(output_id)
        if view == "photodiode_placement" and patch is not None:
            if patch.background_rect is not None:
                rectangles.append((patch.background_rect, 0.0))
            rectangles.append((patch.rect, float(pulse_high)))
        for rect, level in rectangles:
            bounds = rect.x, rect.y, rect.width, rect.height
            context.scissor = bounds
            frame.device_fbo.clear(level, level, level, 1.0, viewport=bounds)
    finally:
        context.scissor = None
    screen = getattr(context, "screen", None)
    if screen is not None:
        context.copy_framebuffer(screen, frame.device_fbo)
