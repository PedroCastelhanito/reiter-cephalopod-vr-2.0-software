"""Worker setup adapter: protected inputs, resource manifest and prepared trials."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from cephvr.visual_stimulus.compiler import CompileContext, compile_trial
from cephvr.visual_stimulus.config.models.artifact_models import (
    PreparedTrial,
    ReviewEncoding,
)
from cephvr.visual_stimulus.config.models.display_profile import (
    DisplayProfile,
    parse_display_json,
)
from cephvr.visual_stimulus.config.models.evidence_model import Identity
from cephvr.visual_stimulus.config.models.program_model import (
    Program,
    TrialArenaBoundaries,
    parse_program_json,
)
from cephvr.visual_stimulus.config.models.schema_common import parse_json
from cephvr.visual_stimulus.rendering.engine import RendererEngine
from cephvr.visual_stimulus.rendering.types import (
    DisplayInitialization,
    RenderPort,
    ResourceReleaseReport,
)
from cephvr.visual_stimulus.resources.assets import (
    PreparedResourceBundle,
    ProtectedSource,
)
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.calibration import (
    PreparedCalibration,
    prepare_calibration,
)
from cephvr.visual_stimulus.resources.display_calibration import (
    PreparedDisplayCalibration,
    prepare_display_calibration_request,
)
from cephvr.visual_stimulus.resources.prepare import prepare_resources
from cephvr.visual_stimulus.resources.protected import ProtectedWindowsSource
from cephvr.visual_stimulus.resources.video import VideoPlayback
from cephvr.visual_stimulus.resources.video_decoder import DecoderFactory
from cephvr.visual_stimulus.resources.video_session import VideoSession
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus_messages


class ReviewEncodingProvider(Protocol):
    def __call__(
        self,
        display: DisplayProfile,
        ffmpeg_args: tuple[str, ...],
        limits: object,
        announce: Callable[[str, str | None], None],
    ) -> ReviewEncoding: ...


class NativePreparation:
    """Concrete Visual Stimulus Setup adapter retaining source owners through resource release."""

    def __init__(
        self,
        port: RenderPort,
        *,
        renderer_generation: str,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        cancelled: threading.Event | None = None,
        review_encoding_provider: ReviewEncodingProvider | None = None,
        source_factory: Callable[[Path], ProtectedSource] = ProtectedWindowsSource,
        decoder_factory: DecoderFactory | None = None,
    ) -> None:
        if not renderer_generation:
            raise ValueError("renderer process generation is required")
        self.renderer_generation = renderer_generation
        self.port = port
        self.clock_ns = clock_ns
        self.cancelled = cancelled
        self.review_encoding_provider = review_encoding_provider
        # Keep an independent owner reference immediately after creation. Lower
        # level parsers may fail while closing a partially prepared source; this
        # registry lets worker cleanup retry and retain an accurate receipt.
        self._protected_sources: list[tuple[ProtectedSource, str]] = []
        self._announced_paths: dict[Path, str] = {}
        self.source_factory = self._retain_source_factory(source_factory)
        self.decoder_factory = decoder_factory
        self._bundles: dict[str, PreparedResourceBundle] = {}
        self._resource_keys: list[str] = []
        self._pathless_resource_keys: list[str] = []
        self._cpu_limit = 0
        self._gpu_limit = 0
        self._budget: BoundedBudget | None = None
        self._deadline_ns: int | None = None
        self.engine = RendererEngine(
            port, clock_ns=clock_ns, resource_provider=self.resources_for
        )
        self._display_calibration: PreparedCalibration | None = None
        self._display_budget: BoundedBudget | None = None
        self._display_asset_root: Path | None = None
        self._display_asset_limit = 0
        self._display_document_limit = 0
        self._display_profile: DisplayProfile | None = None
        self.video_playback: VideoPlayback | None = None
        self.video_session: VideoSession | None = None

    def _retain_source_factory(
        self, factory: Callable[[Path], ProtectedSource]
    ) -> Callable[[Path], ProtectedSource]:
        def create(path: Path) -> ProtectedSource:
            source = factory(path)
            label = self._announced_paths.get(path.resolve(), str(path))
            self._protected_sources.append((source, label))
            return source

        return create

    def _registered_announce(
        self, announce: Callable[[str, str | None], None], namespace: str
    ) -> Callable[[str, str | None], None]:
        def register(key: str, path: str | None) -> None:
            qualified = f"{namespace}:{key}" if namespace else key
            announce(qualified, path)
            self._resource_keys.append(qualified)
            if path is not None:
                self._announced_paths[Path(path).resolve()] = qualified
            else:
                self._pathless_resource_keys.append(qualified)

        return register

    def prepare_display(
        self,
        request: visual_stimulus_messages.InitializeDisplay,
        announce: Callable[[str, str | None], None],
        deadline_ns: int,
    ) -> tuple[DisplayProfile, PreparedCalibration]:
        """Protect and validate display correction files without touching GL."""
        self._check(deadline_ns)
        if not request.asset_root:
            raise ValueError("display calibration requires the adopted asset_root")
        display = parse_display_json(
            request.display.profile_json, max_bytes=request.limits.max_document_bytes
        )
        display_budget = BoundedBudget(
            cpu_limit=request.limits.max_asset_cpu_bytes,
            gpu_limit=request.limits.max_asset_gpu_bytes,
            cancelled=self.cancelled,
            deadline_ns=deadline_ns,
            clock_ns=self.clock_ns,
        )
        self._display_asset_root = Path(request.asset_root).resolve(strict=True)
        self._display_asset_limit = request.limits.max_asset_cpu_bytes
        self._display_document_limit = request.limits.max_document_bytes
        calibration = prepare_calibration(
            display,
            Path(request.asset_root),
            announce=self._registered_announce(announce, "visual_stimulus:display"),
            budget=display_budget,
            max_document_bytes=request.limits.max_document_bytes,
            owner_prefix="visual_stimulus:display",
            source_factory=self.source_factory,
        )
        self._display_profile = display
        self._display_calibration = calibration
        self._display_budget = display_budget
        return display, calibration

    def prepare_display_calibration(
        self,
        request: visual_stimulus_messages.OpenDisplayCalibrationCommand,
        announce: Callable[[str, str | None], None],
        deadline_ns: int,
    ) -> PreparedDisplayCalibration:
        resource_key_start = len(self._resource_keys)
        prepared = prepare_display_calibration_request(
            request,
            self._registered_announce(announce, "visual_stimulus:calibration"),
            deadline_ns,
            check_deadline=self._check,
            clock_ns=self.clock_ns,
            cancelled=self.cancelled,
            source_factory=self.source_factory,
            previous_display=self._display_profile,
            previous_calibration=self._display_calibration,
        )
        prepared.resource_keys = tuple(self._resource_keys[resource_key_start:])
        return prepared

    def release_display_calibration(self, prepared: PreparedDisplayCalibration) -> bool:
        released = prepared.close_sources()
        closed = prepared.closed_source_ids
        if closed:
            self._protected_sources = [
                item for item in self._protected_sources if id(item[0]) not in closed
            ]
        if released:
            keys = set(prepared.resource_keys)
            self._resource_keys = [
                key for key in self._resource_keys if key not in keys
            ]
            self._pathless_resource_keys = [
                key for key in self._pathless_resource_keys if key not in keys
            ]
            self._announced_paths = {
                path: key
                for path, key in self._announced_paths.items()
                if key not in keys
            }
        return released

    def retry_incomplete_display_calibration(self, deadline_ns: int) -> bool:
        """Retry only calibration inputs retained by a failed preparation."""
        if self.clock_ns() >= deadline_ns:
            return False
        retained: list[tuple[ProtectedSource, str]] = []
        failed = False
        for source, label in reversed(self._protected_sources):
            if not label.startswith("visual_stimulus:calibration:"):
                retained.append((source, label))
                continue
            try:
                source.close_after_consumers()
            except Exception:
                failed = True
                retained.append((source, label))
        self._protected_sources = list(reversed(retained))
        if failed or self.clock_ns() >= deadline_ns:
            return False
        self._resource_keys = [
            key
            for key in self._resource_keys
            if not key.startswith("visual_stimulus:calibration:")
        ]
        self._pathless_resource_keys = [
            key
            for key in self._pathless_resource_keys
            if not key.startswith("visual_stimulus:calibration:")
        ]
        self._announced_paths = {
            path: key
            for path, key in self._announced_paths.items()
            if not key.startswith("visual_stimulus:calibration:")
        }
        return True

    def initialize_display(
        self, display: DisplayProfile, calibration: PreparedCalibration
    ) -> DisplayInitialization:
        """Install CPU-validated calibration, then perform startup Idle on GL owner."""
        install = getattr(self.port, "install_display_calibration", None)
        if install is None:
            raise RuntimeError(
                "render port does not accept prepared display calibration"
            )
        install(calibration)
        return self.engine.initialize_display(display)

    def _check(self, deadline_ns: int) -> None:
        if self.cancelled is not None and self.cancelled.is_set():
            raise InterruptedError("Visual Stimulus Setup was cancelled")
        if self.clock_ns() >= deadline_ns:
            raise TimeoutError("Visual Stimulus Setup deadline expired")

    def prepare_trials(
        self,
        request: visual_stimulus_messages.WorkerSetup,
        announce: Callable[[str, str | None], None],
        deadline_ns: int,
    ) -> tuple[PreparedTrial, ...]:
        if self._bundles:
            raise RuntimeError(
                "NativePreparation instances perform one Setup admission"
            )
        self._check(deadline_ns)
        self._deadline_ns = deadline_ns
        if not request.HasField("session") or not request.session.HasField(
            "configuration"
        ):
            raise ValueError("WorkerSetup requires its retained session configuration")
        if not request.HasField("settings") or not request.settings.HasField("display"):
            raise ValueError("WorkerSetup requires the adopted display profile")
        if not request.HasField("policies") or not request.policies.HasField("limits"):
            raise ValueError(
                "WorkerSetup requires resolved Visual Stimulus resource limits"
            )
        limits = request.policies.limits
        self.video_playback = VideoPlayback(
            decoder_threads=limits.decoder_threads,
            decoder_contexts=limits.decoder_contexts,
            codec_threads_per_context=limits.codec_threads_per_context,
            codec_threads_total=limits.codec_threads_total,
            decoded_frames_per_instance=limits.decoded_frames_per_instance,
            decoded_bytes_total=limits.decoded_bytes_total,
            decoder_working_bytes_total=limits.decoder_working_bytes_total,
            decoder_factory=self.decoder_factory,
        )
        self._cpu_limit, self._gpu_limit = (
            limits.max_asset_cpu_bytes,
            limits.max_asset_gpu_bytes,
        )
        self._budget = BoundedBudget(
            cpu_limit=self._cpu_limit,
            gpu_limit=self._gpu_limit,
            cancelled=self.cancelled,
            deadline_ns=deadline_ns,
            clock_ns=self.clock_ns,
        )
        self.video_session = VideoSession(self.video_playback, self._budget)
        self.engine.set_video_provider(self.video_session.present)
        self.engine.set_video_reset(self.video_session.reset)
        display = parse_display_json(
            request.settings.display.profile_json,
            max_bytes=limits.max_document_bytes,
        )
        configuration = request.session.configuration
        if not configuration.HasField("asset_root") or not configuration.asset_root:
            raise ValueError("Visual Stimulus Setup requires the adopted asset_root")
        assets_root = Path(configuration.asset_root)
        saving = (
            request.settings.HasField("save_visual_stimulus_data")
            and request.settings.save_visual_stimulus_data
        )
        if saving and self.review_encoding_provider is None:
            raise RuntimeError(
                "saving is enabled but no review encoder preflight provider is installed"
            )
        ffmpeg_args = tuple(request.settings.review_ffmpeg_args)
        artifacts: list[PreparedTrial] = []
        try:
            for trial in request.session.trials:
                self._check(deadline_ns)
                if not trial.HasField("definition") or not trial.definition.HasField(
                    "stimulus"
                ):
                    raise ValueError(
                        "prepared session trial has no Visual Stimulus stimulus definition"
                    )
                stimulus = trial.definition.stimulus
                if not stimulus.HasField("program") or not stimulus.HasField(
                    "arena_boundaries"
                ):
                    raise ValueError(
                        "trial requires canonical stimulus program and arena boundaries"
                    )
                source_json = stimulus.program.program_json
                program: Program = parse_program_json(
                    source_json, max_bytes=limits.max_document_bytes
                )
                boundaries = parse_json(
                    TrialArenaBoundaries,
                    stimulus.arena_boundaries.boundaries_json,
                    max_bytes=limits.max_document_bytes,
                )
                bundle = prepare_resources(
                    program,
                    assets_root,
                    self._budget,
                    announce=self._registered_announce(
                        announce, f"visual_stimulus:{trial.context.trial_id}"
                    ),
                    snapshot_limit_bytes=limits.max_asset_cpu_bytes,
                    video_index_limit_bytes=limits.decoded_bytes_total,
                    glb_element_limit=max(1, limits.max_asset_cpu_bytes // 256),
                    output_count=len(display.active_outputs),
                    owner_prefix=f"visual_stimulus:{trial.context.trial_id}",
                    display=display,
                    max_document_bytes=limits.max_document_bytes,
                    source_factory=self.source_factory,
                    codec_threads=limits.codec_threads_per_context,
                )
                trial_id = trial.context.trial_id
                if trial_id in self._bundles:
                    raise ValueError(f"duplicate Visual Stimulus trial ID {trial_id}")
                self._bundles[trial_id] = bundle
                explicit_seed = (
                    stimulus.stimulus_seed_decimal
                    if stimulus.HasField("stimulus_seed_decimal")
                    else str(secrets.randbelow(1 << 128))
                )
                prepared_generation = str(uuid.uuid4())
                resource_generation = str(uuid.uuid4())
                identity = Identity(
                    session_id=trial.context.session.session_id,
                    trial_id=trial.context.trial_id,
                    configuration_revision=request.session.configuration_revision,
                    prepared_generation=prepared_generation,
                    renderer_generation=self.renderer_generation,
                    resource_generation=resource_generation,
                )
                review_encoding = (
                    self.review_encoding_provider(
                        display, ffmpeg_args, limits, announce
                    )
                    if saving and self.review_encoding_provider is not None
                    else None
                )
                if saving and review_encoding is not None:
                    if not limits.HasField("capture_slots") or not limits.HasField(
                        "recording_bytes_total"
                    ):
                        raise ValueError(
                            "recording capture memory bounds must be explicit"
                        )
                    pixels = (
                        review_encoding.composite_width
                        * review_encoding.composite_height
                    )
                    queued_bytes = pixels * 4 * limits.capture_slots
                    if queued_bytes > limits.recording_bytes_total:
                        raise MemoryError(
                            "review capture slots exceed the recording byte budget"
                        )
                    assert self._budget is not None
                    self._budget.reserve(
                        owner=f"visual_stimulus:{trial.context.trial_id}:review-capture",
                        cpu_bytes=0,
                        gpu_bytes=pixels * 16 + pixels * 4 * limits.capture_slots,
                    )
                context = CompileContext(
                    identity=identity,
                    display=display,
                    arena_boundaries=boundaries,
                    manifest=bundle.manifest,
                    seed_decimal=explicit_seed,
                    source_json=source_json,
                    uniform_layouts=bundle.uniform_layouts,
                    review_encoding=review_encoding,
                    saving=saving,
                )
                artifact = compile_trial(
                    program,
                    context,
                    max_expanded_epochs=limits.max_expanded_epochs,
                    max_prepared_plan_bytes=limits.max_prepared_plan_bytes,
                    preparation_budget=self._budget,
                )
                self._reserve_scene_gpu(artifact)
                assert self.video_session is not None
                self.video_session.register_trial(artifact, bundle)
                artifacts.append(artifact)
            if self.video_playback is not None:
                self.video_playback.start(
                    announce=self._registered_announce(announce, ""),
                    deadline_ns=deadline_ns,
                )
            return tuple(artifacts)
        except BaseException:
            # Sources stay referenced until closure is explicitly reported. The
            # worker's registered obligations remain available through cleanup().
            raise

    def _reserve_scene_gpu(self, artifact: PreparedTrial) -> None:
        """Account retained linear render surfaces before any GL allocation."""
        from cephvr.visual_stimulus.rendering.diagnostics import (
            DIAGNOSTIC_SLOTS,
            reservation_bytes,
        )

        if self._budget is None:
            raise RuntimeError("scene preparation requires the active resource budget")
        mappings = sum(
            mapping.viewport.width * mapping.viewport.height
            for mapping in artifact.display.active_mappings
        )
        output_pixels = sum(
            output.width_px * output.height_px
            for output in artifact.display.active_outputs
        )
        # Each mapped surface retains RGBA32F color plus a 32-bit depth buffer;
        # final and calibrated-device outputs each retain an RGBA32F texture.
        gpu_bytes = (
            mappings * 20
            + output_pixels * 32
            + reservation_bytes(len(artifact.display.active_outputs))
        )
        self._budget.reserve(
            owner=f"visual_stimulus:{artifact.identity.trial_id}:scene-surfaces",
            cpu_bytes=len(artifact.display.active_outputs) * DIAGNOSTIC_SLOTS * 512,
            gpu_bytes=gpu_bytes,
        )

    def resources_for(self, trial_id: str) -> PreparedResourceBundle:
        try:
            return self._bundles[trial_id]
        except KeyError as exc:
            raise KeyError(
                f"no prepared Visual Stimulus resources for trial {trial_id}"
            ) from exc

    def prepare_graphics(self, artifacts: tuple[PreparedTrial, ...]) -> None:
        """Allocate/validate GPU resources on the renderer's GL owner thread."""
        if self._deadline_ns is None:
            raise RuntimeError("CPU Setup preparation must precede graphics allocation")
        if not artifacts:
            raise ValueError("Setup requires at least one prepared trial")
        display = artifacts[0].display
        first_bundle = self.resources_for(artifacts[0].identity.trial_id)
        calibration_ids = {
            item.fingerprint.resource_id
            for item in first_bundle.manifest.resources
            if item.kind in ("geometry", "photometric")
        }
        calibration_assets = tuple(
            item
            for item in first_bundle.asset_set.assets
            if item.asset_id in calibration_ids
        )
        calibration_resources = tuple(
            item
            for item in first_bundle.manifest.resources
            if item.kind in ("geometry", "photometric")
        )
        calibration = PreparedCalibration(
            assets=calibration_assets,
            resources=calibration_resources,
            content={
                key: first_bundle.prepared_content[key] for key in calibration_ids
            },
        )
        # Setup must reload protected calibration even when the JSON profile is
        # unchanged. Keep old Idle through CPU preparation, then replace outputs
        # and require fresh framebuffer/Idle observations before Ready.
        self.engine.replace_display(display, calibration)
        for artifact in artifacts:
            self._check(self._deadline_ns)
            self.engine.prepare_trial(
                artifact, self.resources_for(artifact.identity.trial_id)
            )
            self._check(self._deadline_ns)

    def create_engine(self) -> RendererEngine:
        return self.engine

    def cleanup(self, deadline_ns: int | None = None) -> ResourceReleaseReport:
        released: list[str] = []
        outstanding: list[str] = []
        failed_sources: set[int] = set()
        closed_sources: set[int] = set()
        decoder_closed = True
        if self.video_playback is not None:
            deadline = deadline_ns if deadline_ns is not None else self.clock_ns()
            for worker in self.video_playback.cleanup(deadline_ns=deadline):
                outstanding.append(f"video-decoder:{worker}")
            if not outstanding:
                self.video_playback = None
            else:
                decoder_closed = False
        if decoder_closed:
            for source, label in reversed(self._protected_sources):
                try:
                    source.close_after_consumers()
                    closed_sources.add(id(source))
                    released.append(label)
                except Exception as exc:
                    failed_sources.add(id(source))
                    outstanding.append(f"protected-source:{label}:{exc}")
        else:
            failed_sources.update(id(source) for source, _ in self._protected_sources)
        if not failed_sources and decoder_closed:
            released.extend(self._pathless_resource_keys)
            self._pathless_resource_keys.clear()
            self._resource_keys.clear()
            self._bundles.clear()
            self._budget = None
            if self._display_budget is not None:
                self._display_budget = None
                self._display_calibration = None
        self._protected_sources = [
            item for item in self._protected_sources if id(item[0]) in failed_sources
        ]
        return ResourceReleaseReport(tuple(dict.fromkeys(released)), tuple(outstanding))
