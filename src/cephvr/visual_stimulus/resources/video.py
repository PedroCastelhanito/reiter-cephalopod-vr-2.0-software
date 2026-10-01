"""Bounded CPU video decode-ahead and frame delivery.

Container operations stay on one assigned worker for their entire lifetime. The
render thread only publishes a coalesced target and polls for a completed frame.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from cephvr.visual_stimulus.rendering.types import MediaSnapshot

from .assets import ProtectedSource
from .media import ImagePixels
from .video_decoder import (
    DecoderContext,
    DecoderFactory,
    VideoPlaybackError,
    make_pyav_context,
)
from .video_index import SourceFrame, VideoIndex
from .video_selection import PlaybackCursor, PlaybackSelection, VideoTarget


@dataclass(slots=True)
class DecodedFrameLease:
    target: VideoTarget
    pixels: ImagePixels
    _released: bool = False
    _release_callback: Any = None

    def release(self) -> None:
        if not self._released:
            self._released = True
            if self._release_callback is not None:
                self._release_callback(self)


@dataclass(slots=True)
class _Instance:
    instance_id: str
    evidence_instance_id: str
    asset_id: str
    profile: str
    source: ProtectedSource
    index: VideoIndex
    prepared_generation: str
    cursor: PlaybackCursor
    worker_id: int
    codec_threads: int
    initial_ns: int
    context: DecoderContext | None = None
    latest: VideoTarget | None = None
    latest_request_id: int = 0
    ready: DecodedFrameLease | None = None
    inflight: DecodedFrameLease | None = None
    failure: BaseException | None = None
    cancelled: bool = False
    last_decoded_index: int | None = None
    last_displayed: SourceFrame | None = None
    force_initial_upload: bool = False


@dataclass(frozen=True, slots=True)
class VideoPresentation:
    decoded: DecodedFrameLease | None
    selection: MediaSnapshot

    def release(self) -> None:
        if self.decoded is not None:
            self.decoded.release()


class VideoPlayback:
    """Session-owned bounded decoder workers and nonblocking playback consumer."""

    def __init__(
        self,
        *,
        decoder_threads: int,
        decoder_contexts: int,
        codec_threads_per_context: int,
        codec_threads_total: int,
        decoded_frames_per_instance: int,
        decoded_bytes_total: int,
        decoder_working_bytes_total: int,
        decoder_factory: DecoderFactory | None = None,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        positive = (
            decoder_threads,
            decoder_contexts,
            codec_threads_per_context,
            codec_threads_total,
            decoded_frames_per_instance,
            decoded_bytes_total,
            decoder_working_bytes_total,
        )
        if min(positive) <= 0:
            raise ValueError("video decoder limits must be positive")
        if codec_threads_per_context > codec_threads_total:
            raise ValueError("one codec context exceeds aggregate codec-thread budget")
        self.decoder_threads = decoder_threads
        self.decoder_contexts = decoder_contexts
        self.codec_threads_per_context = codec_threads_per_context
        self.codec_threads_total = codec_threads_total
        self.decoded_bytes_total = decoded_bytes_total
        self.decoder_working_bytes_total = decoder_working_bytes_total
        self.decoder_factory: DecoderFactory = decoder_factory or make_pyav_context
        self.clock_ns = clock_ns
        self._condition = threading.Condition()
        self._instances: dict[str, _Instance] = {}
        self._workers: list[threading.Thread] = []
        self._started = False
        self._cancelled = False
        self._next_id = 0
        self._initialized: set[str] = set()

    def register(
        self,
        *,
        instance_id: str,
        asset_id: str,
        profile: str,
        evidence_instance_id: str | None = None,
        source: ProtectedSource,
        index: VideoIndex,
        prepared_generation: str,
        end_behavior: str,
        initial_ns: int = 0,
    ) -> None:
        with self._condition:
            if self._started:
                raise VideoPlaybackError(
                    "video instances must be registered before decoder start"
                )
            if initial_ns < 0 or initial_ns > (1 << 63) - 1:
                raise ValueError(
                    "initial playback position must be a nonnegative int64"
                )
            if instance_id in self._instances:
                raise VideoPlaybackError(f"duplicate video instance {instance_id}")
            if len(self._instances) >= min(
                self.decoder_contexts,
                self.codec_threads_total // self.codec_threads_per_context,
            ):
                raise MemoryError(
                    "prepared video instances exceed admitted decoder contexts"
                )
            ordinal = len(self._instances)
            frame_bytes = _decoded_frame_bytes(index)
            workspace = frame_bytes * 3
            if (
                frame_bytes > self.decoded_bytes_total
                or workspace > self.decoder_working_bytes_total
            ):
                raise MemoryError(
                    "one video frame exceeds configured decode memory limits"
                )
            total_frame_bytes = frame_bytes + sum(
                _decoded_frame_bytes(item.index) for item in self._instances.values()
            )
            if (
                total_frame_bytes > self.decoded_bytes_total
                or total_frame_bytes * 3 > self.decoder_working_bytes_total
            ):
                raise MemoryError(
                    "prepared video instances exceed aggregate decode memory limits"
                )
            self._instances[instance_id] = _Instance(
                instance_id,
                evidence_instance_id or instance_id,
                asset_id,
                profile,
                source,
                index,
                prepared_generation,
                PlaybackCursor(index, end_behavior),
                ordinal % self.decoder_threads,
                self.codec_threads_per_context,
                initial_ns,
                last_displayed=index.frames[0],
            )

    def start(
        self, *, announce: Callable[[str, str | None], None], deadline_ns: int
    ) -> None:
        with self._condition:
            if self._started:
                return
            self._started = True
            if not self._instances:
                return
            count = min(self.decoder_threads, len(self._instances))
            # Freeze cleanup ownership before creating threads or native contexts.
            for worker_id in range(count):
                announce(f"visual_stimulus:video-decode-worker:{worker_id}", None)
            for instance in self._instances.values():
                announce(
                    f"visual_stimulus:video-decode-context:{instance.instance_id}", None
                )
                selection = instance.cursor.select(
                    Fraction(instance.initial_ns, 1_000_000_000)
                )
                instance.latest_request_id = 1
                instance.latest = VideoTarget(
                    instance.prepared_generation,
                    selection.playback_generation,
                    instance.latest_request_id,
                    selection,
                )
                if selection.source_frame.index == instance.index.frames[0].index:
                    instance.last_decoded_index = selection.source_frame.index
            for worker_id in range(count):
                worker = threading.Thread(
                    target=self._run_worker,
                    args=(worker_id,),
                    name=f"visual-stimulus-video-decode-{worker_id}",
                    daemon=True,
                )
                self._workers.append(worker)
                worker.start()
            while True:
                failed = next(
                    (
                        item
                        for item in self._instances.values()
                        if item.failure is not None
                    ),
                    None,
                )
                if failed is not None:
                    self._cancelled = True
                    self._condition.notify_all()
                    raise VideoPlaybackError(
                        f"video context failed during Setup for {failed.instance_id}: {failed.failure}"
                    ) from failed.failure
                contexts_ready = len(self._initialized) == len(self._instances)
                initial_frames_ready = all(
                    item.latest is not None
                    and item.last_decoded_index
                    == item.latest.selection.source_frame.index
                    for item in self._instances.values()
                )
                if contexts_ready and initial_frames_ready:
                    break
                remaining = deadline_ns - self.clock_ns()
                if remaining <= 0:
                    self._cancelled = True
                    self._condition.notify_all()
                    raise TimeoutError("video context initialization deadline expired")
                self._condition.wait(min(remaining / 1_000_000_000, 0.05))

    def reset(self, instance_id: str) -> int:
        with self._condition:
            instance = self._instance(instance_id)
            instance.cursor.reset()
            instance.latest = None
            instance.latest_request_id += 1
            instance.last_decoded_index = None
            instance.last_displayed = instance.index.frames[0]
            instance.force_initial_upload = True
            if instance.ready is not None:
                instance.ready.release()
                instance.ready = None
            self._condition.notify_all()
            return instance.cursor._generation

    def publish(
        self,
        instance_id: str,
        playback_seconds: float | Fraction,
        *,
        end_behavior: str | None = None,
    ) -> VideoTarget:
        with self._condition:
            if self._cancelled:
                raise VideoPlaybackError("video playback is cancelled")
            if not self._started:
                raise VideoPlaybackError(
                    "decoder workers were not admitted during Setup"
                )
            instance = self._instance(instance_id)
            if end_behavior is not None:
                instance.cursor.set_end_behavior(end_behavior)
            selection = instance.cursor.select(playback_seconds)
            instance.latest_request_id += 1
            target = VideoTarget(
                instance.prepared_generation,
                selection.playback_generation,
                instance.latest_request_id,
                selection,
            )
            instance.latest = target
            self._condition.notify_all()
            return target

    def poll(
        self, instance_id: str, *, target: VideoTarget
    ) -> DecodedFrameLease | None:
        with self._condition:
            instance = self._instance(instance_id)
            ready = instance.ready
            if ready is None:
                if instance.failure is not None:
                    raise VideoPlaybackError(
                        f"video decoder failed for {instance_id}: {instance.failure}"
                    )
                return None
            current = instance.latest
            if current is None or not ready.target.matches_content(current):
                ready.release()
                return None
            ready.target = current
            instance.ready = None
            instance.inflight = ready
            return ready

    def present(
        self,
        instance_id: str,
        playback_seconds: float | Fraction,
        *,
        end_behavior: str | None = None,
    ) -> VideoPresentation:
        """Publish one current target and return immediately with current/held media."""
        target = self.publish(instance_id, playback_seconds, end_behavior=end_behavior)
        with self._condition:
            instance = self._instance(instance_id)
            if instance.force_initial_upload:
                frame_zero = instance.index.frames[0]
                initial_selection = PlaybackSelection(
                    frame_zero,
                    target.playback_generation,
                    target.selection.loop_index,
                    target.selection.target,
                    "selected",
                )
                initial_target = VideoTarget(
                    target.prepared_generation,
                    target.playback_generation,
                    target.request_id,
                    initial_selection,
                )
                lease = DecodedFrameLease(initial_target, instance.index.initial_pixels)
                lease._release_callback = lambda value, key=instance.instance_id: (
                    self._lease_released(key, value)
                )
                instance.inflight = lease
                instance.force_initial_upload = False
                instance.last_displayed = frame_zero
            else:
                lease = None
        if lease is None:
            lease = self.poll(instance_id, target=target)
        with self._condition:
            instance = self._instance(instance_id)
            if lease is not None:
                instance.last_displayed = lease.target.selection.source_frame
            actual = instance.last_displayed
            if actual is None:
                raise VideoPlaybackError(
                    "video has no prepared or retained presentation frame"
                )
            if target.selection.disposition == "end_hold":
                disposition = "clip_end_hold"
            elif actual.index != target.selection.source_frame.index:
                disposition = "starvation_hold"
            else:
                disposition = "current"
            media = MediaSnapshot(
                instance_id=instance.evidence_instance_id,
                asset_id=instance.asset_id,
                stream_index=instance.index.stream_index,
                source_frame_index=actual.index,
                source_pts=actual.pts,
                time_base_numerator=actual.time_base.numerator,
                time_base_denominator=actual.time_base.denominator,
                playback_generation=target.playback_generation,
                loop_index=target.selection.loop_index,
                target_media_numerator=target.selection.target.numerator,
                target_media_denominator=target.selection.target.denominator,
                disposition=disposition,
            )
            return VideoPresentation(lease, media)

    def _lease_released(self, instance_id: str, lease: DecodedFrameLease) -> None:
        with self._condition:
            instance = self._instances.get(instance_id)
            if instance is not None:
                if instance.ready is lease:
                    instance.ready = None
                if instance.inflight is lease:
                    instance.inflight = None
            self._condition.notify_all()

    def _instance(self, instance_id: str) -> _Instance:
        try:
            return self._instances[instance_id]
        except KeyError as exc:
            raise VideoPlaybackError(f"unknown video instance {instance_id}") from exc

    def _run_worker(self, worker_id: int) -> None:
        cursor = 0
        assigned = [
            item for item in self._instances.values() if item.worker_id == worker_id
        ]
        for instance in assigned:
            try:
                instance.context = self.decoder_factory(
                    instance.source,
                    instance.index,
                    instance.profile,
                    instance.codec_threads,
                )
            except BaseException as exc:
                with self._condition:
                    instance.failure = exc
                    self._condition.notify_all()
            else:
                with self._condition:
                    self._initialized.add(instance.instance_id)
                    self._condition.notify_all()
        while True:
            with self._condition:
                candidates = [
                    item
                    for item in assigned
                    if not item.cancelled
                    and item.latest is not None
                    and item.ready is None
                    and item.inflight is None
                    and item.failure is None
                    and item.latest.selection.source_frame.index
                    != item.last_decoded_index
                ]
                if self._cancelled and not candidates:
                    break
                if not candidates:
                    self._condition.wait(timeout=0.05)
                    continue
                instance = candidates[cursor % len(candidates)]
                cursor += 1
                target = instance.latest
            assert target is not None
            try:
                if instance.context is None:
                    raise VideoPlaybackError(
                        "decoder context was not initialized during Setup"
                    )
                pixels = instance.context.decode(target.selection.source_frame)
                lease = DecodedFrameLease(target, pixels)
                lease._release_callback = lambda value, key=instance.instance_id: (
                    self._lease_released(key, value)
                )
                with self._condition:
                    current = instance.latest
                    if current is None:
                        lease.release()
                        continue
                    if (
                        self._cancelled
                        or instance.cancelled
                        or not target.matches_content(current)
                    ):
                        lease.release()
                        continue
                    lease.target = current
                    instance.ready = lease
                    instance.last_decoded_index = target.selection.source_frame.index
                    self._condition.notify_all()
            except BaseException as exc:
                with self._condition:
                    instance.failure = exc
                    self._condition.notify_all()
        # Only this owner closes its own contexts.
        for instance in assigned:
            if instance.context is not None:
                try:
                    instance.context.close()
                except Exception as exc:
                    instance.failure = exc
                instance.context = None

    def cleanup(self, *, deadline_ns: int) -> tuple[str, ...]:
        with self._condition:
            self._cancelled = True
            for instance in self._instances.values():
                instance.cancelled = True
            self._condition.notify_all()
        for worker in self._workers:
            remaining = max(0.0, (deadline_ns - self.clock_ns()) / 1_000_000_000)
            worker.join(remaining)
        outstanding = [worker.name for worker in self._workers if worker.is_alive()]
        with self._condition:
            for instance in self._instances.values():
                if instance.ready is not None:
                    instance.ready.release()
                    instance.ready = None
                if instance.inflight is not None:
                    instance.inflight.release()
                    instance.inflight = None
        return tuple(outstanding)


def _decoded_frame_bytes(index: VideoIndex) -> int:
    return index.width * index.height * (8 if max(index.component_bits) > 8 else 4)
