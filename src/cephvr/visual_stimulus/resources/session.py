"""Worker setup adapter: protected inputs, resource manifest and prepared trials."""

from __future__ import annotations

import logging
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from cephvr.platform.windows.protected_source import ProtectedWindowsSource
from cephvr.shared.deadlines import Deadline, resolve_deadline
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
    ProtectedFingerprintCache,
    ProtectedSource,
    _resolve_asset_path,
)
from cephvr.visual_stimulus.resources.budget import (
    BoundedBudget,
    review_capture_cpu_bytes,
    review_capture_gpu_bytes,
)
from cephvr.visual_stimulus.resources.calibration import (
    PreparedCalibration,
    prepare_calibration,
)
from cephvr.visual_stimulus.resources.display_calibration import (
    PreparedDisplayCalibration,
    prepare_display_calibration_request,
)
from cephvr.visual_stimulus.resources.prepare import prepare_resources
from cephvr.visual_stimulus.resources.prepared_heap import PreparedHeap
from cephvr.visual_stimulus.resources.progress import SetupProgress
from cephvr.visual_stimulus.resources.provenance import software_provenance
from cephvr.visual_stimulus.resources.video import VideoPlayback
from cephvr.visual_stimulus.resources.video_decoder import DecoderFactory
from cephvr.visual_stimulus.resources.video_session import VideoSession
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus_messages

if TYPE_CHECKING:
    from cephvr.visual_stimulus.rendering.image_residency import ImageResidency
    from cephvr.visual_stimulus.resources.image_bundle import ImageBundle
    from cephvr.visual_stimulus.resources.image_source import ImageInfo, ImageSource


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
        self._released_resource_keys: set[str] = set()
        self._pathless_resource_keys: list[str] = []
        self._cpu_limit = 0
        self._gpu_limit = 0
        self._budget: BoundedBudget | None = None
        self._deadline_ns: Deadline | None = None
        self.engine = RendererEngine(
            port, clock_ns=clock_ns, resource_provider=self.resources_for
        )
        self._display_calibration: PreparedCalibration | None = None
        self._display_budget: BoundedBudget | None = None
        self._display_asset_root: Path | None = None
        self._display_profile: DisplayProfile | None = None
        self.video_playback: VideoPlayback | None = None
        self.video_session: VideoSession | None = None
        self.image_residency: ImageResidency | None = None
        self._image_bundle: ImageBundle | None = None
        self._image_bundle_root: Path | None = None
        self._bundle_announce: Callable[[str, str | None], None] | None = None
        self._prepared_heap = PreparedHeap()
        self._progress = SetupProgress(None, clock_ns)

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
            # A lost receipt may still leave a registered, never-created obligation.
            self._released_resource_keys.discard(qualified)
            self._resource_keys.append(qualified)
            if path is not None:
                self._announced_paths[Path(path).resolve()] = qualified
            else:
                self._pathless_resource_keys.append(qualified)
            announce(qualified, path)

        return register

    def retire_released_resources(self) -> None:
        """Forget release proofs only after the worker catalogue retires them."""
        self._released_resource_keys.clear()

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

    def _check(self, deadline_ns: Deadline) -> None:
        if self.cancelled is not None and self.cancelled.is_set():
            raise InterruptedError("Visual Stimulus Setup was cancelled")
        if self.clock_ns() >= resolve_deadline(deadline_ns):
            raise TimeoutError("Visual Stimulus Setup inactivity expired")

    def prepare_trials(
        self,
        request: visual_stimulus_messages.WorkerSetup,
        announce: Callable[[str, str | None], None],
        deadline_ns: Deadline,
        *,
        announce_batch: Callable[[tuple[tuple[str, str | None], ...]], None]
        | None = None,
        progress: Callable[..., None] | None = None,
    ) -> tuple[PreparedTrial, ...]:
        if self._bundles:
            raise RuntimeError(
                "NativePreparation instances perform one Setup admission"
            )
        self._check(deadline_ns)
        self._deadline_ns = deadline_ns
        interval = request.session.policies.setup.initial_ns
        self._progress = SetupProgress(
            progress,
            self.clock_ns,
            cadence_ns=max(1, min(1_000_000_000, interval // 4))
            if interval
            else 1_000_000_000,
        )
        self._progress.update("Preparing stimulus resources")
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
        display = parse_display_json(
            request.settings.display.profile_json,
            max_bytes=limits.max_document_bytes,
        )
        configuration = request.session.configuration
        if not configuration.HasField("asset_root") or not configuration.asset_root:
            raise ValueError("Visual Stimulus Setup requires the adopted asset_root")
        assets_root = Path(configuration.asset_root)
        self._image_bundle_root = assets_root.resolve(strict=True)
        saving = (
            request.settings.HasField("save_visual_stimulus_data")
            and request.settings.save_visual_stimulus_data
        )
        if saving and self.review_encoding_provider is None:
            raise RuntimeError(
                "saving is enabled but no review encoder preflight provider is installed"
            )
        ffmpeg_args = tuple(request.settings.review_ffmpeg_args)
        components = software_provenance(self._budget.check_cancelled_or_expired)
        artifacts: list[PreparedTrial] = []
        validated_images: dict[str, tuple[ImageSource, ImageInfo]] = {}
        fingerprints = ProtectedFingerprintCache(self._budget)
        from cephvr.visual_stimulus.resources.progress import PreparationMetrics

        metrics = PreparationMetrics()
        try:
            for trial_number, trial in enumerate(request.session.trials, 1):
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
                if announce_batch is not None:
                    planned: list[tuple[str, str | None]] = []

                    def collect(
                        key: str,
                        path: str | None,
                        target: list[tuple[str, str | None]] = planned,
                    ) -> None:
                        target.append((key, path))

                    register = self._registered_announce(
                        collect,
                        f"visual_stimulus:{trial.context.trial_id}",
                    )
                    for asset in program.assets:
                        self._check(deadline_ns)
                        path = _resolve_asset_path(assets_root, asset.logical_path)
                        register(f"asset:{asset.asset_id}", str(path))
                    announce_batch(tuple(planned))
                label = f"Trial {trial_number}/{len(request.session.trials)}"
                self._progress.update(f"{label} — Protecting and reading assets")

                def image_progress(done: int, total: int, label: str = label) -> None:
                    self._progress.update(
                        f"{label} — Decoding and validating textures", done, total
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
                    defer_images=True,
                    combine_image_validation=True,
                    validated_images=validated_images,
                    component_provenance=components,
                    image_progress=image_progress,
                    fingerprints=fingerprints,
                    metrics=metrics,
                )
                self._progress.update(f"{label} — Compiling stimulus schedule")
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
                    cpu_bytes = review_capture_cpu_bytes(
                        review_encoding.composite_width,
                        review_encoding.composite_height,
                        limits.capture_slots,
                    )
                    if cpu_bytes > limits.recording_bytes_total:
                        raise MemoryError(
                            "review capture slots exceed the recording byte budget"
                        )
                    assert self._budget is not None
                    self._budget.reserve(
                        owner=f"visual_stimulus:{trial.context.trial_id}:review-capture",
                        cpu_bytes=cpu_bytes,
                        gpu_bytes=review_capture_gpu_bytes(
                            review_encoding.composite_width,
                            review_encoding.composite_height,
                            limits.capture_slots,
                            review_encoding.native_pixel_format,
                        ),
                    )
                from cephvr.visual_stimulus.resources.glb import GLBScene

                context = CompileContext(
                    identity=identity,
                    display=display,
                    arena_boundaries=boundaries,
                    arena_geometry={
                        key: value.arena_geometry_json
                        for key, value in bundle.prepared_content.items()
                        if isinstance(value, GLBScene)
                        and value.arena_geometry_json is not None
                    },
                    manifest=bundle.manifest,
                    seed_decimal=explicit_seed,
                    source_json=source_json,
                    uniform_layouts=bundle.uniform_layouts,
                    review_encoding=review_encoding,
                    saving=saving,
                )
                compile_started = time.perf_counter()
                artifact = compile_trial(
                    program,
                    context,
                    max_expanded_epochs=limits.max_expanded_epochs,
                    max_prepared_plan_bytes=limits.max_prepared_plan_bytes,
                    preparation_budget=self._budget,
                )
                metrics.compile_seconds += time.perf_counter() - compile_started
                from cephvr.visual_stimulus.config.review_layout import review_layout

                layout = review_layout(
                    display,
                    request.policies.review_scale_factor or 1,
                    bundle.prepared_content,
                )
                from cephvr.visual_stimulus.compiler.compile import (
                    serialize_prepared_trial,
                )
                from cephvr.visual_stimulus.config.models.artifact_models import (
                    GeometricProfile,
                )
                from cephvr.visual_stimulus.config.models.photometric_profile import (
                    PhotometricProfile,
                )

                artifact = artifact.model_copy(
                    update={
                        "preview_layout": layout,
                        "geometric_calibration": tuple(
                            value
                            for value in bundle.prepared_content.values()
                            if isinstance(value, GeometricProfile)
                        ),
                        "photometric_calibration": tuple(
                            value
                            for value in bundle.prepared_content.values()
                            if isinstance(value, PhotometricProfile)
                        ),
                    }
                )
                if (
                    len(serialize_prepared_trial(artifact))
                    > limits.max_prepared_plan_bytes
                ):
                    raise ValueError(
                        "prepared artifact with review metadata exceeds its byte limit"
                    )
                assert self._budget is not None
                # Label-free compositor and bounded native double-buffered viewer.
                compositor_bytes = (
                    layout.composite_width
                    * layout.composite_height
                    * (8 if max(t.source_code_bits for t in layout.tiles) == 8 else 32)
                )
                self._budget.reserve(
                    owner="visual_stimulus:preview",
                    cpu_bytes=0,
                    gpu_bytes=compositor_bytes + 2048 * 2048 * 8,
                )
                self._reserve_scene_gpu(artifact)
                assert self.video_session is not None
                self.video_session.register_trial(artifact, bundle)
                artifacts.append(artifact)
            self._progress.update(
                f"Image metadata prepared: {metrics.images_validated + metrics.images_inspected} unique, "
                f"{metrics.validations_reused} reused"
            )
            if any(bundle.image_sources for bundle in self._bundles.values()):
                from cephvr.visual_stimulus.rendering.image_residency import (
                    ImageResidency,
                )
                from cephvr.visual_stimulus.resources.image_schedule import (
                    ImageSchedule,
                )

                schedule = ImageSchedule.build(
                    tuple(artifacts), self._bundles, self._budget
                )
                self._bundle_announce = self._registered_announce(announce, "")
                self.image_residency = ImageResidency(
                    schedule,
                    self._budget,
                    announce=self._registered_announce(announce, ""),
                    clock_ns=self.clock_ns,
                    announce_batch=announce_batch,
                    progress=lambda done, total: self._progress.update(
                        "Decoding and uploading initial textures to projectors",
                        done,
                        total,
                    ),
                )
            if self.video_playback is not None:
                self.video_playback.start(
                    announce=self._registered_announce(announce, ""),
                    deadline_ns=resolve_deadline(deadline_ns),
                )
            return tuple(artifacts)
        except BaseException:
            # Sources stay referenced until closure is explicitly reported. The
            # worker's registered obligations remain available through cleanup().
            raise
        finally:
            logging.getLogger(__name__).info(
                "Setup CPU metadata/validation phase metrics: %s", asdict(metrics)
            )
            self._budget.release(owner="visual_stimulus:source-fingerprints")

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

    def prepare_graphics(
        self, artifacts: tuple[PreparedTrial, ...]
    ) -> tuple[PreparedTrial, ...]:
        """Allocate/validate GPU resources on the renderer's GL owner thread."""
        if self._deadline_ns is None:
            raise RuntimeError("CPU Setup preparation must precede graphics allocation")
        if not artifacts:
            raise ValueError("Setup requires at least one prepared trial")
        if self.video_session is None:
            raise RuntimeError("CPU video preparation must precede graphics allocation")
        self.engine.set_video_provider(self.video_session.present)
        self._progress.update("Preparing projector graphics")
        self.engine.set_video_reset(self.video_session.reset)
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
        components = self.port.replay_provenance()
        prepared = []
        for artifact in artifacts:
            manifest = artifact.manifest.model_copy(
                update={"provenance": (*artifact.manifest.provenance, *components)}
            )
            artifact = artifact.model_copy(update={"manifest": manifest})
            self._bundles[artifact.identity.trial_id] = replace(
                self.resources_for(artifact.identity.trial_id), manifest=manifest
            )
            prepared.append(artifact)
        artifacts = tuple(prepared)
        if self.image_residency is not None:
            if any(
                source.output_crops
                for source in self.image_residency.schedule.sources.values()
            ):
                from cephvr.visual_stimulus.resources.image_bundle import (
                    ImageBundle,
                    bundle_identities,
                )

                assert self._image_bundle_root is not None and self._budget is not None
                assert self._bundle_announce is not None
                names, geometry = bundle_identities(
                    self.image_residency.schedule,
                    artifacts,
                    lambda trial: self.resources_for(trial).asset_set.by_id(),
                )
                self._image_bundle = ImageBundle(
                    self._image_bundle_root,
                    self._bundle_announce,
                    names=names,
                    geometry=geometry,
                    on_replaced=self._progress.stale_bundles,
                )
                image_bundle = self._image_bundle
                prepare_bundle = getattr(self.port, "prepare_image_bundle", None)
                if prepare_bundle is None:
                    raise RuntimeError("render port lacks Fold sample preparation")
                self.image_residency.schedule = prepare_bundle(
                    self._image_bundle,
                    self.image_residency.schedule,
                    self._budget,
                    lambda done, total: self._progress.update(
                        image_bundle.progress_stage(done, total), done, total
                    ),
                )
                from cephvr.visual_stimulus.config.models.artifact_models import (
                    PreparedImageBundle,
                )

                schedule = self.image_residency.schedule
                artifacts = tuple(
                    artifact.model_copy(
                        update={
                            "image_bundles": tuple(
                                PreparedImageBundle(
                                    asset_id=asset, **self._image_bundle.manifest[key]
                                )
                                for (trial, asset), key in schedule.aliases.items()
                                if trial == artifact.identity.trial_id
                                and key in self._image_bundle.manifest
                            )
                        }
                    )
                    for artifact in artifacts
                )
            for source in self.image_residency.schedule.sources.values():
                self._check(self._deadline_ns)
                if source.finish_validation is not None:
                    source.finish_validation()
            install_images = getattr(self.port, "install_image_residency", None)
            if install_images is None:
                raise RuntimeError("render port lacks bounded image residency")
            install_images(self.image_residency, self._deadline_ns)
        for index, artifact in enumerate(artifacts, 1):
            self._check(self._deadline_ns)
            self._progress.update(f"Preparing trial graphics {index}/{len(artifacts)}")
            self.engine.prepare_trial(
                artifact, self.resources_for(artifact.identity.trial_id)
            )
            self._check(self._deadline_ns)

        deadline_ns = self._deadline_ns
        self._progress.update("Finalizing prepared stimulus memory")
        self._prepared_heap.prepare(lambda: self._check(deadline_ns))
        self._check(self._deadline_ns)
        self._progress.update("Initial textures ready; publishing prepared trials")
        return artifacts

    def cleanup(self, deadline_ns: int | None = None) -> ResourceReleaseReport:
        self._prepared_heap.release()
        released: list[str] = []
        outstanding: list[str] = []
        failed_sources: set[int] = set()
        closed_sources: set[int] = set()
        decoder_closed = True
        if self.image_residency is not None:
            deadline = deadline_ns if deadline_ns is not None else self.clock_ns()
            if self.image_residency.close(deadline):
                self.image_residency = None
            else:
                outstanding.append("image-loader:worker remains active")
                decoder_closed = False
        if self.video_playback is not None:
            deadline = deadline_ns if deadline_ns is not None else self.clock_ns()
            video_outstanding = self.video_playback.cleanup(deadline_ns=deadline)
            for worker in video_outstanding:
                outstanding.append(f"video-decoder:{worker}")
            if not video_outstanding:
                self.video_playback = None
            else:
                decoder_closed = False
        if decoder_closed:
            if self._image_bundle is not None:
                try:
                    self._image_bundle.close()
                    self._image_bundle = None
                except Exception as exc:
                    outstanding.append(f"image-bundle:{exc}")
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
            # All retained source owners and consumers are closed, including
            # announced intents whose creation failed before acquiring a handle.
            released.extend(self._resource_keys)
            self._pathless_resource_keys.clear()
            self._resource_keys.clear()
            self._announced_paths.clear()
            self._bundles.clear()
            self._budget = None
            self._display_budget = None
            self._display_calibration = None
            self._display_profile = None
        self._protected_sources = [
            item for item in self._protected_sources if id(item[0]) in failed_sources
        ]
        self._released_resource_keys.update(released)
        return ResourceReleaseReport(
            tuple(sorted(self._released_resource_keys)), tuple(outstanding)
        )
