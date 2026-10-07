"""Lazy GLFW/ModernGL ownership for physical outputs and trial GPU resources.

The module has no graphics imports at import time. Device/display initialization is
performed by one worker-owned thread and fails closed when the selected adapter or
required scene pipeline cannot be established.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, cast

from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile, Output
from cephvr.visual_stimulus.rendering.native_display import (
    NativeRenderingError,
    configure_window,
    idle_device_color,
    verify_framebuffer,
)
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    DisplayInitialization,
    OutputActivity,
    RenderedOutput,
    RenderPassResult,
    ResourceReleaseReport,
)
from cephvr.visual_stimulus.resources.assets import PreparedResourceBundle
from cephvr.visual_stimulus.resources.calibration import PreparedCalibration
from cephvr.visual_stimulus.resources.display_calibration import (
    PreparedDisplayCalibration,
)
from cephvr.visual_stimulus.resources.glb import GLBScene
from cephvr.visual_stimulus.resources.media import ImagePixels


@dataclass(slots=True)
class _OutputContext:
    output_id: str
    window: object
    context: Any
    width: int
    height: int
    bits: int
    swap_interval: int
    screen: Any
    activate: Callable[[], None]
    context_released: bool = False


class ModernGLPort:
    """Single-thread GLFW window/context owner with strict physical device checks.

    A composed-scene renderer and calibration loader are required inputs. This class
    owns window/context lifecycle, output precision checks, Idle and presentation;
    it never invents an identity mapping or uncalibrated fallback for missing scene
    and calibration providers.
    """

    def __init__(
        self,
        software_root: Path,
        *,
        announce: Callable[[str, str | None], None],
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        monitor_resolver: Callable[[str, Any], object] | None = None,
        gpu_identity_provider: Callable[[str, str], str] | None = None,
        scene_renderer: Any | None = None,
        calibration_loader: Callable[[object, Path], object] | None = None,
    ) -> None:
        self.software_root = Path(software_root)
        self.announce = announce
        self.clock_ns = clock_ns
        self.monitor_resolver = monitor_resolver or self._resolve_monitor
        self.gpu_identity_provider = gpu_identity_provider or self._verify_render_gpu
        self.scene_renderer = scene_renderer
        self.calibration_loader = calibration_loader
        self._owner = threading.get_ident()
        self._glfw: Any = None
        self._moderngl: Any = None
        self._outputs: dict[str, _OutputContext] = {}
        self._orphan_windows: dict[str, object] = {}
        self._window_obligations: set[str] = set()
        self._scene_keys: set[str] = set()
        self._capture_fences: list[Any] = []
        self._display: DisplayProfile | None = None
        self._display_calibration: PreparedCalibration | None = None
        self._resources: dict[str, object] = {}
        self._calibration_owner: Any | None = None
        self._idle_activities: list[OutputActivity] = []
        self._idle_linear = (0.0, 0.0, 0.0)
        self._released: list[str] = []

    @staticmethod
    def _verify_render_gpu(renderer: str, vendor: str) -> str:
        from cephvr.platform.windows.nvidia_device import verify_opengl_rendering_device

        device = verify_opengl_rendering_device(renderer, vendor)
        return f"nvidia_uuid:{device.uuid}"

    def _assert_owner(self) -> None:
        if threading.get_ident() != self._owner:
            raise NativeRenderingError(
                "GLFW and ModernGL calls must stay on the owner thread"
            )

    @staticmethod
    def _resolve_monitor(device_identity: str, glfw: Any) -> object:
        from cephvr.platform.windows.display_identity import monitor_interface

        matches = [
            monitor
            for monitor in glfw.get_monitors()
            if monitor_interface(
                glfw.get_win32_adapter(monitor), glfw.get_win32_monitor(monitor)
            ).casefold()
            == device_identity.casefold()
        ]
        if len(matches) != 1:
            raise NativeRenderingError(
                f"display interface {device_identity!r} matched {len(matches)} active monitors"
            )
        return matches[0]

    def _load_graphics(self) -> None:
        if self._glfw is not None:
            return
        try:
            import glfw
            import moderngl
        except ImportError as exc:
            raise NativeRenderingError(
                "install the cephvr[visual_stimulus] graphics extra"
            ) from exc
        self.announce("visual_stimulus:glfw", None)
        glfw.ERROR_REPORTING = "raise"
        if not glfw.init():
            self._released.append("visual_stimulus:glfw")
            raise NativeRenderingError("GLFW initialization failed")
        self._glfw, self._moderngl = glfw, moderngl

    def initialize_display(self, display: object) -> DisplayInitialization:
        self._assert_owner()
        if not isinstance(display, DisplayProfile):
            raise TypeError("canonical display profile required")
        if self._display is not None:
            if display != self._display:
                raise NativeRenderingError(
                    "display cannot change without releasing its contexts"
                )
            return self._display_report
        self._released.clear()
        self._idle_activities.clear()
        self._load_graphics()
        glfw = self._glfw
        created: list[_OutputContext] = []
        try:
            for output in display.active_outputs:
                monitor = self.monitor_resolver(output.device_identity, glfw)
                self.announce(f"visual_stimulus:window:{output.output_id}", None)
                self._window_obligations.add(output.output_id)
                configure_window(glfw, output)
                share = created[0].window if created else None
                window = glfw.create_window(
                    output.width_px, output.height_px, output.output_id, monitor, share
                )
                if not window:
                    raise NativeRenderingError(
                        f"could not create output {output.output_id}"
                    )
                self._orphan_windows[output.output_id] = window
                glfw.make_context_current(window)
                context = self._moderngl.create_context(require=430)
                # Register ownership immediately after context creation so any
                # subsequent capability/identity failure releases this context.
                output_context = _OutputContext(
                    output.output_id,
                    window,
                    context,
                    output.width_px,
                    output.height_px,
                    output.rgb_bits_per_channel,
                    0,
                    context.screen,
                    partial(glfw.make_context_current, window),
                )
                created.append(output_context)
                self._outputs[output.output_id] = output_context
                self._orphan_windows.pop(output.output_id)
                verify_framebuffer(
                    context, glfw, window, output, self.gpu_identity_provider
                )
                swap_interval = (
                    1
                    if output.output_id == display.selected_pacing_output_id
                    or display.presentation_mode == "all_outputs_vsync"
                    else 0
                )
                glfw.swap_interval(swap_interval)
                entry = self.clock_ns()
                color = self._idle_device_color(output, display)
                context.disable(self._moderngl.DEPTH_TEST | self._moderngl.BLEND)
                context.screen.use()
                context.viewport = (0, 0, output.width_px, output.height_px)
                context.clear(*color, alpha=1.0)
                glfw.swap_buffers(window)
                returned = self.clock_ns()
                output_context.swap_interval = swap_interval
                self._idle_activities.append(
                    OutputActivity(output.output_id, entry, returned, swap_interval)
                )
            self._display = display
            self._display_report = DisplayInitialization(
                tuple(output.output_id for output in display.active_outputs),
                tuple(
                    (item.output_id, item.bits, item.bits, item.bits)
                    for item in created
                ),
                tuple((item.output_id, item.width, item.height) for item in created),
                tuple((item.output_id, item.swap_interval) for item in created),
                tuple(self._idle_activities),
            )
            return self._display_report
        except BaseException as initialization_error:
            cleanup_errors = self._release_partial(created)
            if cleanup_errors:
                raise NativeRenderingError(
                    "display initialization failed and partial resources remain: "
                    + "; ".join(cleanup_errors)
                ) from initialization_error
            raise

    _display_report: DisplayInitialization
    _idle_activities: list[OutputActivity]

    def _idle_device_color(
        self, output: Output, display: DisplayProfile
    ) -> tuple[float, float, float]:
        return idle_device_color(output, display, self._display_calibration)

    def install_display_calibration(self, calibration: PreparedCalibration) -> None:
        self._assert_owner()
        if self._display is not None:
            raise NativeRenderingError(
                "display calibration cannot change after output initialization"
            )
        self._display_calibration = calibration

    def prepare_trial(self, artifact: object, resources: object) -> None:
        self._assert_owner()
        if not isinstance(artifact, PreparedTrial) or not isinstance(
            resources, PreparedResourceBundle
        ):
            raise TypeError("canonical prepared trial and resource bundle required")
        if self._display is None or artifact.display != self._display:
            raise NativeRenderingError(
                "display contexts are not ready for this prepared trial"
            )
        contents = getattr(resources, "prepared_content", None)
        if contents is None:
            raise NativeRenderingError("prepared source data is missing")
        for resource in artifact.manifest.resources:
            resource_id = resource.fingerprint.resource_id
            key = f"{artifact.identity.resource_generation}:{resource_id}"
            if key in self._resources:
                continue
            if resource.kind == "video":
                continue  # Scene owns per-instance video textures and their reservations.
            if resource.profile_id == "gltf2_local_dependency_v1":
                continue
            if resource.fingerprint.subresource is not None:
                continue  # ArenaGPUSet owns its referenced texture subresources.
            self.announce(f"visual_stimulus:gpu:{key}", None)
            if resource.kind == "image":
                textures: list[Any] = []
                self._resources[key] = textures
                self._upload_linear_image(
                    cast(ImagePixels, contents[resource_id]), retained=textures
                )
            elif resource.kind == "arena":
                from cephvr.visual_stimulus.rendering.arena_gpu import upload_arena

                self._resources[key] = upload_arena(
                    cast(GLBScene, contents[resource_id]),
                    self._outputs,
                    contents,
                    resource_id,
                    lambda output_id, context, image, opaque, retained: (
                        self._upload_one_image(
                            output_id,
                            context,
                            image,
                            opaque=opaque,
                            retained=retained,
                        )
                    ),
                    retain=partial(self._resources.__setitem__, key),
                )
            elif resource.kind in ("geometry", "photometric"):
                self._resources[key] = contents[resource_id]
            else:
                raise NativeRenderingError(
                    f"unsupported prepared resource kind {resource.kind}"
                )
        scene_key = f"visual_stimulus:scene:{artifact.identity.resource_generation}"
        self.announce(scene_key, None)
        self._scene_keys.add(scene_key)
        if self.scene_renderer is None:
            from cephvr.visual_stimulus.rendering.scene import ModernGLSceneRenderer

            self.scene_renderer = ModernGLSceneRenderer()
        bind_api = getattr(self.scene_renderer, "bind_graphics_api", None)
        if bind_api is None:
            raise NativeRenderingError("scene pipeline lacks graphics API binding")
        bind_api(self._moderngl)
        prepare = getattr(self.scene_renderer, "prepare_trial", None)
        if prepare is None:
            raise NativeRenderingError("scene pipeline lacks prepare_trial")
        prepare(artifact, resources, self._outputs, self._resources)

    def _upload_linear_image(
        self, prepared_image: ImagePixels, *, retained: list[Any] | None = None
    ) -> tuple[Any, ...]:
        textures = retained if retained is not None else []
        for key, output in self._outputs.items():
            self._upload_one_image(
                key,
                output.context,
                prepared_image,
                retained=textures.append,
            )
        return tuple(textures)

    def _upload_one_image(
        self,
        output_id: str,
        context: Any,
        prepared_image: ImagePixels,
        opaque: bool = False,
        retained: Callable[[Any], None] | None = None,
    ) -> Any:
        from cephvr.visual_stimulus.rendering.upload import upload_linear_image

        self._outputs[output_id].activate()
        return upload_linear_image(
            context, prepared_image, opaque=opaque, retain=retained
        )

    def render(self, scene: object, state: object) -> RenderPassResult:
        self._assert_owner()
        if self.scene_renderer is None:
            raise NativeRenderingError("ModernGL scene pipeline is not installed")
        render = getattr(self.scene_renderer, "render_group", None)
        if render is None:
            raise NativeRenderingError("scene pipeline lacks render_group")
        result = render(scene, state, self._outputs, self._resources)
        if not isinstance(result, RenderPassResult):
            raise NativeRenderingError(
                "scene pipeline must return GPU outputs and exact evidence consumed by the shaders"
            )
        return result

    @property
    def diagnostics_pending(self) -> bool:
        return bool(
            self.scene_renderer is not None
            and getattr(self.scene_renderer, "diagnostics_pending", False)
        )

    def poll_diagnostics(self) -> tuple[DiagnosticSnapshot, ...]:
        self._assert_owner()
        if self.scene_renderer is None:
            return ()
        poll = getattr(self.scene_renderer, "poll_diagnostics", None)
        if poll is None:
            raise NativeRenderingError(
                "scene pipeline lacks clipping diagnostic polling"
            )
        return tuple(poll())

    def service_display(self) -> bool:
        """Pump the owning Windows message queue even while Idle remains unchanged."""
        self._assert_owner()
        if self._glfw is None:
            return False
        self._glfw.poll_events()
        closing = [
            item.window
            for item in self._outputs.values()
            if self._glfw.window_should_close(item.window)
        ]
        for window in closing:
            self._glfw.set_window_should_close(window, False)
        if closing:
            raise NativeRenderingError("a required display window requested closure")
        return bool(self._outputs)

    def present(self, outputs: Sequence[RenderedOutput]) -> tuple[OutputActivity, ...]:
        self._assert_owner()
        by_id = {item.output_id: item for item in outputs}
        if set(by_id) != set(self._outputs):
            raise NativeRenderingError(
                "rendered output set differs from active windows"
            )
        activities = []
        if self._display is None:
            raise NativeRenderingError("display missing during presentation")
        order = [
            key
            for key in self._outputs
            if key != self._display.selected_pacing_output_id
        ]
        if self._display.selected_pacing_output_id is not None:
            order.append(self._display.selected_pacing_output_id)
        for output_id in order:
            context = self._outputs[output_id]
            entry = self.clock_ns()
            error = None
            try:
                context.activate()
                entry = self.clock_ns()
                self._glfw.swap_buffers(context.window)
            except Exception as exc:
                error = f"VISUAL_STIMULUS_SWAP:{str(exc)[:512]}"
            returned = self.clock_ns()
            activities.append(
                OutputActivity(output_id, entry, returned, context.swap_interval, error)
            )
        return tuple(activities)

    def show_idle(self, display: object) -> tuple[OutputActivity, ...]:
        self._assert_owner()
        if not isinstance(display, DisplayProfile) or display != self._display:
            raise NativeRenderingError("active display is unavailable for Idle")
        activities = []
        for output in display.active_outputs:
            context = self._outputs[output.output_id]
            self._glfw.make_context_current(context.window)
            entry = self.clock_ns()
            context.context.screen.use()
            context.context.viewport = (0, 0, output.width_px, output.height_px)
            context.context.scissor = None
            context.context.disable(self._moderngl.DEPTH_TEST | self._moderngl.BLEND)
            context.context.clear(*self._idle_device_color(output, display), alpha=1.0)
            self._glfw.swap_buffers(context.window)
            returned = self.clock_ns()
            activities.append(
                OutputActivity(output.output_id, entry, returned, context.swap_interval)
            )
        return tuple(activities)

    def present_display_calibration(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> tuple[OutputActivity, ...]:
        """Present a protected arena through V15 surface and output calibration."""
        self._assert_owner()
        if self._display != display or not self._outputs:
            raise NativeRenderingError("active outputs are unavailable for calibration")
        from cephvr.visual_stimulus.rendering.display_calibration import (
            DisplayCalibrationRenderer,
        )

        if self._calibration_owner is None:
            self._calibration_owner = DisplayCalibrationRenderer(
                self._outputs,
                self._moderngl,
                self.announce,
                self._upload_one_image,
            )
        self._calibration_owner.present(display, prepared)
        activities: list[OutputActivity] = []
        order = [
            key for key in self._outputs if key != display.selected_pacing_output_id
        ]
        if display.selected_pacing_output_id is not None:
            order.append(display.selected_pacing_output_id)
        for output_id in order:
            output = self._outputs[output_id]
            entry = self.clock_ns()
            error = None
            try:
                output.activate()
                entry = self.clock_ns()
                self._glfw.swap_buffers(output.window)
            except Exception as exc:
                error = f"CALIBRATION_SWAP:{str(exc)[:512]}"
            returned = self.clock_ns()
            activities.append(
                OutputActivity(output_id, entry, returned, output.swap_interval, error)
            )
        return tuple(activities)

    def close_display_calibration(
        self, display: DisplayProfile, prepared: PreparedDisplayCalibration
    ) -> tuple[tuple[OutputActivity, ...], bool]:
        self._assert_owner()
        activities = self.show_idle(display)
        failures: list[str] = [
            f"idle:{item.output_id}:{item.error}"
            for item in activities
            if item.error is not None
        ]
        if self._calibration_owner is not None:
            failures.extend(self._calibration_owner.release())
            if not failures:
                self._calibration_owner = None
                self._released.append("visual_stimulus:gpu:display-calibration:arena")
        return activities, not failures

    def capture_review_composite(
        self, slot: object, outputs: tuple[RenderedOutput, ...], encoding: object
    ) -> object:
        self._assert_owner()
        if self.scene_renderer is None:
            raise NativeRenderingError(
                "capture requires the prepared composition pipeline"
            )
        from cephvr.visual_stimulus.rendering.capture_sync import order_shared_outputs

        order_shared_outputs(self._outputs, self._capture_fences)
        return self.scene_renderer.capture_review_composite(slot, outputs, encoding)

    def poll_review_capture(self, pending: object) -> bytes | None:
        self._assert_owner()
        first = next(iter(self._outputs.values()))
        self._glfw.make_context_current(first.window)
        if self.scene_renderer is None:
            raise NativeRenderingError("capture pipeline missing")
        return cast(bytes | None, self.scene_renderer.poll_review_capture(pending))

    def cancel_review_capture(self, pending: object) -> bool:
        self._assert_owner()
        if self.scene_renderer is None:
            raise NativeRenderingError("capture pipeline missing")
        next(iter(self._outputs.values())).activate()
        cancelled = self.scene_renderer.cancel_review_capture(pending)
        return cancelled is True

    def _release_partial(self, created: list[_OutputContext]) -> list[str]:
        errors: list[str] = []
        retained: list[_OutputContext] = []
        for item in reversed(created):
            try:
                if not item.context_released:
                    self._glfw.make_context_current(item.window)
                    item.context.release()
                    item.context_released = True
            except Exception as exc:
                errors.append(f"context:{item.output_id}:{exc}")
                retained.append(item)
                continue
            try:
                self._glfw.destroy_window(item.window)
                self._released.extend(
                    (
                        f"visual_stimulus:window:{item.output_id}",
                        f"display:{item.output_id}",
                    )
                )
            except Exception as exc:
                errors.append(f"window:{item.output_id}:{exc}")
                if item not in retained:
                    retained.append(item)
        for output_id, window in tuple(self._orphan_windows.items()):
            try:
                self._glfw.destroy_window(window)
                self._orphan_windows.pop(output_id)
            except Exception as exc:
                errors.append(f"window:{output_id}:{exc}")
        self._outputs = {item.output_id: item for item in retained}
        pending_ids = self._outputs.keys() | self._orphan_windows.keys()
        for output_id in self._window_obligations - pending_ids:
            self._released.append(f"visual_stimulus:window:{output_id}")
        self._window_obligations.intersection_update(pending_ids)
        if self._glfw is not None and not pending_ids:
            self._glfw.terminate()
            self._released.append("visual_stimulus:glfw")
            self._glfw = None
            self._moderngl = None
        return errors

    def release(self) -> ResourceReleaseReport:
        self._assert_owner()
        outstanding = []
        if self._capture_fences:
            from cephvr.visual_stimulus.rendering.capture_sync import release_fences

            try:
                next(iter(self._outputs.values())).activate()
                release_fences(self._capture_fences)
            except Exception as exc:
                outstanding.append(f"capture-fence:{exc}")
        if self.scene_renderer is not None:
            try:
                self.scene_renderer.release()
                self.scene_renderer = None
            except Exception as exc:
                outstanding.append(f"scene:{exc}")
        if self.scene_renderer is None:
            self._released.extend(self._scene_keys)
            self._scene_keys.clear()
        if self._calibration_owner is not None:
            failures = self._calibration_owner.release()
            if failures:
                outstanding.extend(f"calibration:{item}" for item in failures)
            else:
                self._calibration_owner = None
                self._released.append("visual_stimulus:gpu:display-calibration:arena")
        for key, resource in tuple(self._resources.items()):
            try:
                self._release_resource(resource)
                self._resources.pop(key)
                self._released.append(f"visual_stimulus:gpu:{key}")
            except Exception as exc:
                outstanding.append(f"gpu:{key}:{exc}")
        remaining = list(self._outputs.values())
        if not outstanding:
            outstanding.extend(self._release_partial(remaining))
        if not outstanding and not self._outputs:
            self._display = None
            self._display_calibration = None
        return ResourceReleaseReport(tuple(self._released), tuple(outstanding))

    @classmethod
    def _release_resource(cls, resource: object) -> None:
        if hasattr(resource, "release"):
            resource.release()
        elif isinstance(resource, (tuple, list)):
            for item in reversed(resource):
                cls._release_resource(item)
