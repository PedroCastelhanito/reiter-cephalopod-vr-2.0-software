"""GLFW window configuration, actual framebuffer checks and calibrated Idle values."""

import ctypes
from collections.abc import Callable
from typing import Any

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile, Output
from cephvr.visual_stimulus.config.models.photometric_profile import PhotometricProfile
from cephvr.visual_stimulus.resources.calibration import PreparedCalibration


def activate_window(glfw: Any, window: Any) -> None:
    """Avoid a redundant driver rebind; inspect the actual thread-local context."""
    current = glfw.get_current_context()
    if (
        current
        and ctypes.cast(current, ctypes.c_void_p).value
        == ctypes.cast(window, ctypes.c_void_p).value
    ):
        return
    glfw.make_context_current(window)


class NativeRenderingError(RuntimeError):
    pass


class DisplayUnavailableError(ValueError):
    """Required output placement is unavailable; no fallback is permitted."""

    code = "DISPLAY_OUTPUT_UNAVAILABLE"
    remedy = (
        "\nCheck power/cables and Windows Display settings, then Refresh in "
        "Devices > Projectors, check its assignment and run Setup."
    )


class DisplayGpuUnavailableError(DisplayUnavailableError):
    """A healthy context has the wrong adapter, rather than a GPU operation fault."""

    remedy = (
        "Visual Stimulus is using the wrong graphics card. Set cephvr-renderer.exe "
        "to use the RTX 5060 Ti in Windows graphics settings or the graphics driver, "
        "then shut down and restart all of CephVR. Reopening the dashboard alone "
        "will not apply the change."
    )


class DisplayAssetUnavailableError(DisplayUnavailableError):
    """Saved display inputs are inaccessible; configuration remains editable."""

    code = "DISPLAY_ASSET_UNAVAILABLE"
    remedy = (
        "Select the correct Protocol Assets folder and restore any missing "
        "calibration files, apply the configuration, then run Setup."
    )


def resolve_output_monitors(
    display: DisplayProfile,
    glfw: Any,
    resolve_monitor: Callable[[str, Any], object],
) -> list[tuple[Output, object]]:
    """Preflight all active assignments, identifying an unavailable projector."""
    monitors = []
    for output in display.active_outputs:
        try:
            monitor = resolve_monitor(output.device_identity, glfw)
        except DisplayUnavailableError as exc:
            faces = ", ".join(
                mapping.surface_id.capitalize()
                for mapping in display.mappings
                if mapping.output_id == output.output_id
            )
            raise type(exc)(
                f"{faces or output.output_id} projector: {exc}\n"
                f"Saved display: {output.device_identity} (output {output.output_id})"
            ) from exc
        monitors.append((output, monitor))
    return monitors


def attach_window_context(moderngl: Any) -> Any:
    """Load the current context while GLFW keeps sole native lifetime ownership."""
    # Detect-mode glcontext wrappers delete WGL contexts when released. The
    # loader-only API leaves native destruction with the creating GLFW window.
    moderngl.init_context()
    context = moderngl.get_context()
    if context.version_code < 430:
        context.release()
        raise NativeRenderingError("configured output requires OpenGL 4.3")
    return context


def configure_window(glfw: Any, output: Output) -> None:
    glfw.default_window_hints()
    glfw.window_hint(glfw.VISIBLE, glfw.TRUE)
    glfw.window_hint(glfw.CENTER_CURSOR, glfw.FALSE)
    # All projector windows must survive focus moving to another output or the GUI.
    glfw.window_hint(glfw.AUTO_ICONIFY, glfw.FALSE)
    glfw.window_hint(glfw.RED_BITS, output.rgb_bits_per_channel)
    glfw.window_hint(glfw.GREEN_BITS, output.rgb_bits_per_channel)
    glfw.window_hint(glfw.BLUE_BITS, output.rgb_bits_per_channel)
    glfw.window_hint(glfw.ALPHA_BITS, 2 if output.rgb_bits_per_channel == 10 else 8)
    glfw.window_hint(glfw.DEPTH_BITS, 24)
    glfw.window_hint(glfw.STENCIL_BITS, 0)
    glfw.window_hint(glfw.SAMPLES, 0)
    glfw.window_hint(glfw.REFRESH_RATE, nominal_refresh_hz(output))
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)


def verify_framebuffer(
    context: Any,
    glfw: Any,
    window: object,
    output: Output,
    gpu_identity: Callable[[str, str], str],
) -> None:
    renderer = str(context.info.get("GL_RENDERER", ""))
    vendor = str(context.info.get("GL_VENDOR", ""))
    selected_gpu = gpu_identity(renderer, vendor)
    if not selected_gpu.startswith("nvidia_uuid:GPU-"):
        raise NativeRenderingError(
            f"renderer context resolved to invalid SYS-002 identity {selected_gpu!r}"
        )
    from OpenGL import GL

    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
    sizes = tuple(
        int(
            GL.glGetFramebufferAttachmentParameteriv(
                GL.GL_FRAMEBUFFER,
                GL.GL_BACK_LEFT,
                size,
            )
        )
        for size in (
            GL.GL_FRAMEBUFFER_ATTACHMENT_RED_SIZE,
            GL.GL_FRAMEBUFFER_ATTACHMENT_GREEN_SIZE,
            GL.GL_FRAMEBUFFER_ATTACHMENT_BLUE_SIZE,
        )
    )
    GL.glDisable(GL.GL_DITHER)
    GL.glDisable(GL.GL_FRAMEBUFFER_SRGB)
    if sizes != (output.rgb_bits_per_channel,) * 3:
        raise NativeRenderingError(
            f"{output.output_id}: framebuffer RGB precision {sizes} does not match request"
        )
    framebuffer_size = glfw.get_framebuffer_size(window)
    if framebuffer_size != (output.width_px, output.height_px):
        raise NativeRenderingError(
            f"{output.output_id}: framebuffer size {framebuffer_size} does not match request"
        )
    monitor = glfw.get_window_monitor(window)
    mode = glfw.get_video_mode(monitor) if monitor else None
    if mode is None or mode.refresh_rate != nominal_refresh_hz(output):
        raise NativeRenderingError(
            f"{output.output_id}: active nominal refresh differs from the requested profile"
        )


def nominal_refresh_hz(output: Output) -> int:
    # GLFW expresses nominal mode selection in integer Hz; the retained rational
    # remains the review-file timebase, never an observed optical refresh claim.
    value = (2 * output.refresh_numerator + output.refresh_denominator) // (
        2 * output.refresh_denominator
    )
    if value <= 0:
        raise NativeRenderingError("requested refresh has no positive GLFW mode")
    return value


def idle_device_color(
    output: Output, display: DisplayProfile, calibration: PreparedCalibration | None
) -> tuple[float, float, float]:
    if display.photometric_mode == "calibrated":
        if calibration is None:
            raise NativeRenderingError(
                "calibrated startup Idle requires protected measured profiles"
            )
        profile = calibration.content.get(output.output_id)
        if not isinstance(profile, PhotometricProfile):
            raise NativeRenderingError(
                f"photometric profile for {output.output_id} is unavailable"
            )
        from cephvr.visual_stimulus.rendering.color import interpolate_inverse_lut

        values = tuple(
            interpolate_inverse_lut(curve, linear)
            for curve, linear in zip(
                (profile.red, profile.green, profile.blue),
                display.idle_linear_rgb,
                strict=True,
            )
        )
        return values[0], values[1], values[2]
    # In uncalibrated mode retain the explicit profile label and encode linear Idle
    # values to sRGB device codes. This does not claim physical linearization.
    from cephvr.visual_stimulus.rendering.color import linear_to_srgb

    red, green, blue = display.idle_linear_rgb
    return linear_to_srgb(red), linear_to_srgb(green), linear_to_srgb(blue)
