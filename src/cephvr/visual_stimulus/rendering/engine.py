"""Thread-affine Visual Stimulus frame orchestration for live experiments."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cephvr.visual_stimulus.config.models.program_model import VideoSettings
from cephvr.visual_stimulus.rendering.state import InstanceState, TrialState
from cephvr.visual_stimulus.rendering.types import (
    DiagnosticSnapshot,
    DisplayInitialization,
    EvidenceStateSnapshot,
    FeedbackEvidenceSnapshot,
    InstanceSnapshot,
    RenderGroup,
    RenderPassResult,
    RenderPort,
    RenderUpdate,
    ResourceReleaseReport,
    SubmissionSnapshot,
)


class RendererStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedSession:
    artifact: Any
    scenes: dict[str, Any]
    epochs: tuple[Any, ...]

    @classmethod
    def from_artifact(cls, artifact: Any) -> PreparedSession:
        source = artifact.source
        scenes = {scene.scene_id: scene for scene in source.scenes}
        return cls(artifact, scenes, tuple(artifact.epochs))


class RendererEngine:
    """One-state, all-output renderer; caller owns this object on the GL thread."""

    def __init__(
        self,
        port: RenderPort,
        *,
        clock_ns: Callable[[], int],
        resource_provider: Callable[[str], object] | None = None,
        feedback_applier: Callable[..., object] | None = None,
        video_provider: Callable[..., Any] | None = None,
        video_reset: Callable[[str, str], object] | None = None,
    ) -> None:
        self._port = port
        self._clock_ns = clock_ns
        self._resource_provider = resource_provider
        self._feedback_applier = feedback_applier
        self._video_provider = video_provider
        self._video_reset = video_reset
        self._video_leases: list[Any] = []
        self._owner_thread = threading.get_ident()
        self._display: Any | None = None
        self._display_observation: DisplayInitialization | None = None
        self._prepared: PreparedSession | None = None
        self._prepared_resources: object | None = None
        self._sessions: dict[str, tuple[PreparedSession, object]] = {}
        self._trial_id: str | None = None
        self._start_ns: int | None = None
        self._photodiode_index = 0
        self._output_attempts: dict[str, int] = {}
        self._group_id = 0
        self._last_time_ns: int | None = None
        self._stopped = False
        self._state = TrialState()

    def _assert_owner(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RendererStateError(
                "renderer operations must stay on its GL-owner thread"
            )

    def initialize_display(self, display: Any) -> DisplayInitialization:
        self._assert_owner()
        if self._display_observation is not None:
            if display != self._display:
                raise RendererStateError("display changed; initialize a fresh renderer")
            return self._display_observation
        observation = self._port.initialize_display(display)
        requested = {
            item.output_id: item.rgb_bits_per_channel for item in display.active_outputs
        }
        observed = {
            output: (red, green, blue)
            for output, red, green, blue in observation.observed_rgb_bits
        }
        sizes = {
            output: (width, height)
            for output, width, height in observation.framebuffer_sizes
        }
        for output_id, bits in requested.items():
            if observed.get(output_id) != (bits, bits, bits):
                raise RendererStateError(
                    f"{output_id}: actual RGB framebuffer precision does not match request"
                )
            configured = next(
                item for item in display.active_outputs if item.output_id == output_id
            )
            if sizes.get(output_id) != (configured.width_px, configured.height_px):
                raise RendererStateError(
                    f"{output_id}: framebuffer dimensions do not match configuration"
                )
        expected = set(requested)
        if set(observed) != expected or set(sizes) != expected:
            raise RendererStateError(
                "display initialization did not report every configured output"
            )
        if {activity.output_id for activity in observation.idle_activity} != expected:
            raise RendererStateError(
                "startup Idle must issue and report one presentation attempt per output"
            )
        self._display, self._display_observation = display, observation
        return observation

    def display_matches(self, display: Any) -> bool:
        """Whether the currently observed output set matches an adopted profile."""
        self._assert_owner()
        return self._display_observation is not None and self._display == display

    def replace_display(
        self, display: Any, calibration: object
    ) -> DisplayInitialization:
        """Replace outputs only after CPU preparation has validated the new profile."""
        self._assert_owner()
        report = self.cleanup()
        if report.outstanding:
            raise RendererStateError(
                "cannot replace display while prior graphics resources remain outstanding"
            )
        install = getattr(self._port, "install_display_calibration", None)
        if install is None:
            raise RendererStateError(
                "render port cannot install prepared display calibration"
            )
        install(calibration)
        return self.initialize_display(display)

    def service_display(self) -> bool:
        self._assert_owner()
        return self._port.service_display()

    def poll_diagnostics(self) -> tuple[DiagnosticSnapshot, ...]:
        self._assert_owner()
        return self._port.poll_diagnostics()

    @property
    def diagnostics_pending(self) -> bool:
        self._assert_owner()
        return self._port.diagnostics_pending

    def set_feedback_applier(self, applier: Callable[..., object] | None) -> None:
        """Install the trial-local compiled feedback consumer on the GL owner."""
        self._assert_owner()
        self._feedback_applier = applier

    def set_video_provider(self, provider: Callable[..., Any] | None) -> None:
        """Install the session-owned CPU selector; rendering calls it without waiting."""
        self._assert_owner()
        self._video_provider = provider

    def set_video_reset(self, reset: Callable[[str, str], object] | None) -> None:
        """Install a trial-local operation that invalidates a video playback generation."""
        self._assert_owner()
        self._video_reset = reset

    def prepare_trial(
        self, artifact: Any, resources: object | None = None
    ) -> PreparedSession:
        self._assert_owner()
        if self._display is None:
            raise RendererStateError(
                "display must be initialized before trial preparation"
            )
        if artifact.display != self._display:
            raise RendererStateError(
                "prepared trial display differs from initialized display"
            )
        trial_id = artifact.identity.trial_id
        if resources is None and self._resource_provider is not None:
            resources = self._resource_provider(trial_id)
        existing = self._sessions.get(trial_id)
        if existing is not None and existing[0].artifact == artifact:
            self._prepared, self._prepared_resources = existing
            return existing[0]
        if resources is None:
            raise RendererStateError(
                "prepared trial requires its retained prepared resources"
            )
        self._port.prepare_trial(artifact, resources)
        self._prepared_resources = resources
        self._prepared = PreparedSession.from_artifact(artifact)
        self._sessions[trial_id] = (self._prepared, resources)
        return self._prepared

    def begin_trial(self, trial_id: str, start_ns: int) -> None:
        self._assert_owner()
        selected = self._sessions.get(trial_id)
        if selected is None or not trial_id or start_ns < 0:
            raise RendererStateError("prepared trial and a valid start are required")
        self._prepared, self._prepared_resources = selected
        if self._trial_id is not None and not self._stopped:
            raise RendererStateError("the preceding trial has not stopped")
        self._trial_id, self._start_ns = trial_id, start_ns
        self._photodiode_index = self._group_id = 0
        if self._display is None:
            raise RendererStateError("display unexpectedly absent")
        self._output_attempts = {
            output.output_id: 0 for output in self._display.active_outputs
        }
        self._last_time_ns = None
        self._stopped = False
        self._state.start()

    def _apply_due_boundaries(self, now_ns: int) -> None:
        assert self._prepared is not None and self._start_ns is not None
        assert self._trial_id is not None
        boundaries = self._prepared.artifact.boundaries
        while self._state.boundary_cursor < len(boundaries):
            boundary = boundaries[self._state.boundary_cursor]
            boundary_host_ns = self._start_ns + boundary.time_ns
            if boundary_host_ns > now_ns:
                break
            for live in self._state.instances.values():
                live.advance(boundary_host_ns)
            next_epoch = (
                self._prepared.epochs[boundary.after]
                if boundary.after is not None
                else None
            )
            settings_by_id = (
                {value.instance_id: value for value in next_epoch.settings}
                if next_epoch is not None
                else {}
            )
            for operation in boundary.operations:
                settings = settings_by_id.get(operation.instance_id)
                existing = self._state.instances.get(operation.instance_id)
                if operation.action == "deactivate":
                    if existing is not None:
                        existing.advance(boundary_host_ns)
                        existing.active = False
                    continue
                if operation.action == "initialize" or existing is None:
                    if settings is None or next_epoch is None:
                        raise RendererStateError(
                            "boundary initialization has no resolved settings"
                        )
                    self._state.instances[operation.instance_id] = (
                        InstanceState.initialize(
                            settings,
                            now_ns=boundary_host_ns,
                            epoch_start_ns=self._start_ns + next_epoch.start_ns,
                        )
                    )
                    if (
                        self._video_reset is not None
                        and isinstance(settings, VideoSettings)
                        and boundary.time_ns > 0
                    ):
                        self._video_reset(self._trial_id, operation.instance_id)
                    continue
                if (
                    self._video_reset is not None
                    and isinstance(settings, VideoSettings)
                    and operation.action in ("reset", "restart_incompatible")
                ):
                    self._video_reset(self._trial_id, operation.instance_id)
                existing.transition(
                    settings,
                    action=operation.action,
                    epoch_start_ns=(
                        self._start_ns + next_epoch.start_ns
                        if next_epoch
                        else boundary_host_ns
                    ),
                    now_ns=boundary_host_ns,
                )
            self._state.epoch_index = boundary.after or 0
            self._state.boundary_cursor += 1

    def _scene_state(
        self, epoch: Any, now_ns: int
    ) -> tuple[Any, tuple[InstanceSnapshot, ...]]:
        assert self._prepared is not None
        scene = self._prepared.scenes.get(epoch.scene_id)
        if scene is None:
            raise RendererStateError(
                f"prepared epoch references missing scene {epoch.scene_id}"
            )
        snapshots = []
        epoch_host_start = self._start_ns + epoch.start_ns
        for setting in epoch.settings:
            live = self._state.instances.get(setting.instance_id)
            if live is None or not live.active:
                raise RendererStateError(
                    f"active instance {setting.instance_id} was not initialized"
                )
            values = live.snapshot(now_ns=now_ns, epoch_start_ns=epoch_host_start)
            decoded_frame = None
            media_selection = None
            source_frame_index = source_pts = None
            if setting.kind == "video" and self._video_provider is not None:
                presentation = self._video_provider(self._trial_id, setting, values)
                decoded_frame = (
                    presentation.decoded.pixels if presentation.decoded else None
                )
                media_selection = presentation.selection
                source_frame_index = media_selection.source_frame_index
                source_pts = media_selection.source_pts
                if presentation.decoded is not None:
                    self._video_leases.append(presentation.decoded)
            snapshots.append(
                InstanceSnapshot(
                    instance_id=setting.instance_id,
                    family=setting.kind,
                    active=True,
                    state=values,
                    settings=setting,
                    source_frame_index=source_frame_index,
                    source_pts=source_pts,
                    decoded_frame=decoded_frame,
                    media_selection=media_selection,
                )
            )
        return scene, tuple(snapshots)

    def _release_video_leases(self) -> None:
        for lease in self._video_leases:
            lease.release()
        self._video_leases.clear()

    @staticmethod
    def photodiode_level(index: int) -> bool:
        """Pattern v1: HH H LLL, then alternating through a 60 submission cycle."""
        if index < 0:
            raise ValueError("submission index cannot be negative")
        position = index % 60
        if position < 3:
            return True
        if position < 6:
            return False
        return position % 2 == 0

    def render_tick(
        self, now_ns: int, feedback_batch: tuple[Any, ...] = ()
    ) -> RenderUpdate:
        self._assert_owner()
        if (
            self._prepared is None
            or self._trial_id is None
            or self._start_ns is None
            or self._stopped
        ):
            raise RendererStateError("no active prepared trial")
        if now_ns < self._start_ns or (
            self._last_time_ns is not None and now_ns < self._last_time_ns
        ):
            raise RendererStateError(
                "render time must be monotonic and at or after trial start"
            )
        elapsed = now_ns - self._start_ns
        epochs = self._prepared.epochs
        if elapsed >= self._prepared.artifact.resolved_duration_ns:
            raise RendererStateError(
                "render update is at or beyond the scheduled trial cutoff"
            )
        self._apply_due_boundaries(now_ns)
        index = 0
        while index + 1 < len(epochs) and elapsed >= epochs[index].end_ns:
            index += 1
        epoch = epochs[index]
        feedback_evidence: tuple[FeedbackEvidenceSnapshot, ...] = ()
        if feedback_batch:
            if self._feedback_applier is None:
                raise RendererStateError(
                    "ordered feedback arrived without the prepared feedback consumer"
                )
            applied_feedback = self._feedback_applier(
                feedback_batch,
                self._state,
                epoch,
                now_ns,
                self._start_ns + epoch.start_ns,
                self._group_id,
            )
            if not isinstance(applied_feedback, tuple) or any(
                not isinstance(item, FeedbackEvidenceSnapshot)
                for item in applied_feedback
            ):
                raise RendererStateError(
                    "feedback consumer must return immutable evidence snapshots"
                )
            feedback_evidence = applied_feedback
        try:
            scene, snapshots = self._scene_state(epoch, now_ns)
        except BaseException:
            self._release_video_leases()
            raise
        marker = self.photodiode_level(self._photodiode_index)
        # Marker is passed with the scene envelope so the GL owner can composite it
        # after geometric mapping and before per-output photometric correction.
        frame_scene = (
            scene,
            marker,
            self._photodiode_index,
            self._trial_id,
            self._group_id,
            epoch.occurrence_index,
            now_ns,
        )
        try:
            rendered = self._port.render(frame_scene, snapshots)
        finally:
            self._release_video_leases()
        if not isinstance(rendered, RenderPassResult):
            raise RendererStateError(
                "render provider must return exact output and evidence values"
            )
        frames = rendered.outputs
        if self._display is None:
            raise RendererStateError("display unexpectedly absent")
        expected = {item.output_id for item in self._display.active_outputs}
        if {frame.output_id for frame in frames} != expected:
            raise RendererStateError(
                "renderer did not produce exactly one image per configured output"
            )
        activities = tuple(self._port.present(frames))
        if {activity.output_id for activity in activities} != expected:
            raise RendererStateError(
                "presentation did not report exactly one outcome per output"
            )
        photodiode_id = self._display.marker_output_id
        if photodiode_id is not None and photodiode_id not in expected:
            raise RendererStateError(
                "trial display lacks its required photodiode output"
            )
        evidence_state = EvidenceStateSnapshot(
            epoch_occurrence=epoch.occurrence_index,
            scene_id=epoch.scene_id,
            evaluation_host_ns=now_ns,
            active_instance_ids=tuple(snapshot.instance_id for snapshot in snapshots),
            uniforms=rendered.uniforms,
            media=rendered.media,
            effective_poses=rendered.effective_poses,
        )
        submissions = []
        intervals = {item.output_id: item for item in activities}
        for output_id in sorted(expected):
            observation = intervals[output_id]
            attempt_index = self._output_attempts[output_id]
            self._output_attempts[output_id] += 1
            submissions.append(
                SubmissionSnapshot(
                    output_id=output_id,
                    attempt_index=attempt_index,
                    phase="failed" if observation.error else "returned",
                    entry_host_ns=observation.swap_entry_ns,
                    return_host_ns=observation.swap_return_ns,
                    swap_interval=observation.requested_swap_interval,
                    marker_index=(
                        self._photodiode_index if output_id == photodiode_id else None
                    ),
                    marker_high=(marker if output_id == photodiode_id else None),
                    failure_code=observation.error,
                )
            )
        group = RenderGroup(
            self._group_id,
            self._trial_id,
            now_ns,
            epoch.occurrence_index,
            epoch.scene_id,
            snapshots,
            activities,
            rendered.clipping_stages,
            marker if self._display.photodiode_enabled else None,
        )
        self._photodiode_index += 1
        self._group_id += 1
        self._last_time_ns = now_ns
        return RenderUpdate(
            group,
            frames,
            evidence_state,
            tuple(submissions),
            feedback_evidence,
        )

    def stop_trial(self, cutoff_ns: int | None = None) -> tuple[Any, ...]:
        self._assert_owner()
        if self._trial_id is None or self._stopped:
            # A scheduled trial may be cancelled before begin_trial. Its required
            # outputs still need an actual Idle submission for cleanup evidence.
            return self._show_idle()
        if self._start_ns is None:
            raise RendererStateError("active trial has no retained start time")
        if (
            cutoff_ns is not None
            and self._last_time_ns is not None
            and cutoff_ns < self._last_time_ns
        ):
            raise RendererStateError("cutoff precedes the last rendered update")
        if cutoff_ns is not None:
            if self._start_ns is None:
                raise RendererStateError("active trial has no retained start time")
            if cutoff_ns < self._start_ns:
                raise RendererStateError("cutoff precedes trial start")
            self._apply_due_boundaries(cutoff_ns)
        evaluation_ns = (
            cutoff_ns
            if cutoff_ns is not None
            else (self._last_time_ns or self._start_ns)
        )
        for live in self._state.instances.values():
            live.advance(evaluation_ns)
            live.active = False
        self._stopped = True
        return self._show_idle()

    def _show_idle(self) -> tuple[Any, ...]:
        if self._display is None:
            return ()
        idle = getattr(self._port, "show_idle", None)
        if idle is None:
            raise RendererStateError(
                "renderer port cannot submit uniform Idle at trial stop"
            )
        return tuple(idle(self._display))

    def cleanup(self) -> ResourceReleaseReport:
        self._assert_owner()
        self._prepared = None
        self._prepared_resources = None
        self._sessions.clear()
        self._trial_id = None
        self._start_ns = None
        self._last_time_ns = None
        self._state = TrialState()
        self._display = None
        self._display_observation = None
        return self._port.release()
