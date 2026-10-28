"""Byte-bounded image residency with an explicit last-image binding per consumer."""

from __future__ import annotations

import logging
import time
from collections import Counter, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from cephvr.shared.deadlines import Deadline, resolve_deadline
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.image_schedule import (
    ImageSchedule,
    image_asset,
)
from cephvr.visual_stimulus.resources.image_source import ImageSource, PixelBuffer
from cephvr.visual_stimulus.resources.image_worker import ImageWorker

from .types import ImageSnapshot, InstanceSnapshot

LOOKAHEAD_EPOCHS = 2


class ImageGpuPort(Protocol):
    def upload(
        self, source: ImageSource, pixels: PixelBuffer, textures: list[Any]
    ) -> bool: ...
    def fence(self, textures: list[Any], fences: list[Any]) -> None: ...
    def ready(self, fences: list[Any]) -> bool: ...
    def release(self, textures: list[Any], fences: list[Any]) -> None: ...


@dataclass(slots=True)
class ResidentImage:
    textures: list[Any] = field(default_factory=list)
    fences: list[Any] = field(default_factory=list)
    state: str = "absent"


class ImageResidency:
    """CPU worker and GL-owned residency share the existing preparation budget."""

    def __init__(
        self,
        schedule: ImageSchedule,
        budget: BoundedBudget,
        *,
        announce: Callable[[str, str | None], None],
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        announce_batch: Callable[[tuple[tuple[str, str | None], ...]], None]
        | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        self.schedule, self.budget, self.clock_ns = schedule, budget, clock_ns
        from cephvr.visual_stimulus.resources.image_timing import ImageTimings

        self.timings = ImageTimings()
        self._source_gpu_bytes = sum(s.gpu_bytes for s in schedule.sources.values())
        self.entries = {key: ResidentImage() for key in schedule.sources}
        self._bound: dict[tuple[str, str], str] = {}
        self._binding_counts: Counter[str] = Counter()
        self._anchors = schedule.anchors
        self._last_indices: dict[tuple[str, str], int] = {}
        self._counts: dict[str, tuple[int, int]] = {}
        self._gpu: ImageGpuPort | None = None
        self._resources: dict[str, Any] | None = None
        self._demand: Iterable[str] = tuple(self._anchors)
        self._cursor: tuple[str, int] | None = None
        self._error: BaseException | None = None
        self._allocated: set[str] = set()
        self._fenced: set[str] = set()
        self._pending: deque[str] = deque()
        self._plan_dirty = True
        self._desired: set[str] = set()
        self._validate_capacity()
        announce("visual_stimulus:image-loader", None)
        self.worker = ImageWorker(budget, clock_ns=clock_ns)
        self._announce_batch = announce_batch
        self._announced: set[str] = set()
        self._progress = progress
        self.released_keys: set[str] = set()

    def _validate_capacity(self) -> None:
        usage = self.budget.usage
        sources = self.schedule.sources
        anchors = sum(sources[key].gpu_bytes for key in self._anchors)
        # All first-use bindings remain available. One last image per instance
        # plus the next complete epoch bounds even a hold spanning many epochs.
        for trial, rows in self.schedule.epochs.items():
            maxima: dict[str, int] = {}
            largest_epoch = 0
            for row in rows:
                keys = {self.schedule.aliases[(trial, asset)] for _, asset in row}
                largest_epoch = max(
                    largest_epoch,
                    sum(
                        sources[key].gpu_bytes
                        for key in keys
                        if key not in self._anchors
                    ),
                )
                for instance, asset in row:
                    key = self.schedule.aliases[(trial, asset)]
                    maxima[instance] = max(
                        maxima.get(instance, 0),
                        0 if key in self._anchors else sources[key].gpu_bytes,
                    )
            required = min(
                sum(source.gpu_bytes for source in sources.values()),
                anchors + sum(maxima.values()) + largest_epoch,
            )
            if usage.gpu_bytes + required > self.budget.gpu_limit:
                raise MemoryError(
                    "image residency initial/held/next working sets exceed GPU budget "
                    f"for trial {trial}: fixed={usage.gpu_bytes}, images={required}, "
                    f"total={usage.gpu_bytes + required}, limit={self.budget.gpu_limit} bytes"
                )
        peak = max((source.cpu_bytes for source in sources.values()), default=0)
        if usage.cpu_bytes + peak > self.budget.cpu_limit:
            raise MemoryError(
                "image residency decode/conversion workspace exceeds CPU budget"
            )

    def attach(
        self,
        gpu: ImageGpuPort,
        resources: dict[str, Any],
        announce: Callable[[str, str | None], None],
    ) -> None:
        self._gpu, self._resources = gpu, resources
        prepare_pool = getattr(gpu, "prepare_pool", None)
        if prepare_pool is not None:
            prepare_pool(self.schedule, self.budget, announce)
        # Ready seals obligations, but loading/evicting their allocations stays lazy.
        planned = tuple((self._owner(key), None) for key in self.entries)
        if self._announce_batch is not None:
            self._announced.update(key for key, _ in planned)
            self._announce_batch(planned)
        else:
            for key, path in planned:
                self._announced.add(key)
                announce(key, path)
        for (trial, asset), key in self.schedule.aliases.items():
            resources[f"{self.schedule.generations[trial]}:{asset}:crops"] = {
                c.output_id: c for c in self.schedule.sources[key].output_crops
            }
            resources[f"{self.schedule.generations[trial]}:{asset}"] = self.entries[
                key
            ].textures

    def _owner(self, key: str) -> str:
        return f"visual_stimulus:gpu:resident-image:{key}"

    def _pinned(self) -> set[str]:
        return set(self._anchors) | set(self._binding_counts)

    def service(self, deadline_ns: int | None = None) -> None:
        if self._gpu is None:
            raise RuntimeError("image residency graphics owner is not attached")
        for key in tuple(self._fenced):
            entry = self.entries[key]
            if entry.state in ("uploading", "retiring") and self._gpu.ready(
                entry.fences
            ):
                if entry.state == "retiring":
                    self._gpu.release(entry.textures, entry.fences)
                    self.budget.release(owner=self._owner(key))
                    entry.state = "absent"
                    self._allocated.remove(key)
                else:
                    entry.state = "resident"
                self._fenced.remove(key)
                self._plan_dirty = True
        if self._plan_dirty:
            self._replan()
        result = self.worker.result()
        if result is not None:
            entry = self.entries[result.key]
            completed = False
            try:
                if result.error is not None:
                    self._error = result.error
                    raise result.error
                if result.key not in self._desired:
                    completed = True
                    if entry.textures:
                        self._gpu.fence(entry.textures, entry.fences)
                        entry.state = "retiring"
                        self._fenced.add(result.key)
                    else:
                        self.budget.release(owner=self._owner(result.key))
                        entry.state = "absent"
                        self._allocated.discard(result.key)
                    return
                assert result.pixels is not None
                completed = self._gpu.upload(
                    self.schedule.sources[result.key], result.pixels, entry.textures
                )
                if not completed:
                    return
                self._gpu.fence(entry.textures, entry.fences)
                entry.state = "uploading"
                self._fenced.add(result.key)
            except BaseException as exc:
                completed = True
                self._error = exc
                raise
            finally:
                if completed:
                    started = time.perf_counter_ns()
                    self.worker.release_result()
                    result = None
                    self.timings.record(
                        "result_release", time.perf_counter_ns() - started
                    )
        if self._error is not None:
            raise RuntimeError("protected image reload failed") from self._error
        if self._plan_dirty:
            self._replan()
        if self.worker.busy:
            return
        while self._pending:
            key = self._pending[0]
            entry = self.entries[key]
            if entry.state != "absent":
                if entry.state == "retiring":
                    return
                self._pending.popleft()
                continue
            source = self.schedule.sources[key]
            try:
                self.budget.reserve(
                    owner=self._owner(key),
                    cpu_bytes=0,
                    gpu_bytes=0
                    if getattr(self._gpu, "pool", None) is not None
                    else source.gpu_bytes,
                )
                if not self.worker.request(source, deadline_ns):
                    self.budget.release(owner=self._owner(key))
                    return
            except MemoryError:
                self.budget.release(owner=self._owner(key))
                return
            self._allocated.add(key)
            entry.state = "loading"
            self._pending.popleft()
            return

    def _replan(self) -> None:
        assert self._gpu is not None
        pinned = self._pinned()
        reserved = sum(self.schedule.sources[key].gpu_bytes for key in self._allocated)
        available = self.budget.gpu_limit - (self.budget.usage.gpu_bytes - reserved)
        if getattr(self._gpu, "pool", None) is not None:
            available = self._source_gpu_bytes
        desired = set(pinned)
        ordered_desired = sorted(pinned)
        desired_bytes = sum(self.schedule.sources[key].gpu_bytes for key in desired)
        for key in self._demand:
            if key in desired:
                continue
            size = self.schedule.sources[key].gpu_bytes
            if desired_bytes + size > available:
                break
            desired.add(key)
            ordered_desired.append(key)
            desired_bytes += size
        for key in tuple(self._allocated):
            entry = self.entries[key]
            if key not in desired and entry.state == "resident":
                self._gpu.fence(entry.textures, entry.fences)
                entry.state = "retiring"
                self._fenced.add(key)
        self._pending = deque(ordered_desired)
        self._desired = desired
        self._plan_dirty = False

    def prepare(self, deadline_ns: Deadline) -> None:
        future = tuple(
            key
            for trial in self.schedule.epochs
            for row in self.schedule.epochs[trial][: 1 + LOOKAHEAD_EPOCHS]
            for _, asset in row
            for key in (self.schedule.aliases[(trial, asset)],)
        )
        self._demand = tuple(dict.fromkeys((*sorted(self._anchors), *future)))
        self._plan_dirty = True
        while True:
            if self.budget.cancelled is not None and self.budget.cancelled.is_set():
                raise InterruptedError("image residency Setup cancelled")
            if self.clock_ns() >= resolve_deadline(deadline_ns):
                raise TimeoutError("initial image residency stopped making progress")
            self.service(resolve_deadline(deadline_ns))
            if self._progress is not None:
                self._progress(
                    sum(self.entries[key].state == "resident" for key in self._desired),
                    len(self._desired),
                )
            if (
                all(self.entries[key].state == "resident" for key in self._desired)
                and not self.worker.busy
            ):
                return
            time.sleep(0.001)

    def begin(self, trial: str) -> None:
        self.timings.clear()
        gpu_timings = getattr(self._gpu, "timings", None)
        if gpu_timings is not None:
            gpu_timings.clear()
        for source in self.schedule.sources.values():
            source.timings.clear()
        self._cursor = None
        self._bound.clear()
        self._binding_counts.clear()
        self._last_indices = {
            key: value for key, value in self._last_indices.items() if key[0] != trial
        }
        self._counts[trial] = (0, 0)
        self._plan_dirty = True

    def finish(self, trial: str) -> None:
        # Rebuild outside trial rendering, ready for any subsequent admission.
        selections, holds = self._counts.get(trial, (0, 0))
        logging.getLogger(__name__).log(
            logging.WARNING if holds else logging.INFO,
            "Texture residency trial=%s selections=%d readiness_holds=%d; "
            "detailed indices require Save On; stages=%s gpu=%s loader=%s",
            trial,
            selections,
            holds,
            self.timings.summary(),
            getattr(self._gpu, "timings", self.timings).summary(),
            self._loader_timings(),
        )

    def _loader_timings(self) -> object:
        from cephvr.visual_stimulus.resources.image_timing import ImageTimings

        totals = ImageTimings()
        for source in self.schedule.sources.values():
            for stage, (count, total, maximum) in source.timings.snapshot().items():
                n, elapsed, peak = totals.stages.get(stage, (0, 0, 0))
                totals.stages[stage] = n + count, elapsed + total, max(peak, maximum)
        return totals.summary()

    def select(
        self, trial: str, epoch: int, snapshots: tuple[InstanceSnapshot, ...]
    ) -> tuple[InstanceSnapshot, ...]:
        if self._cursor != (trial, epoch):
            if self._cursor is None or self._cursor[0] != trial:
                self._bound.clear()
                self._binding_counts.clear()
            self._cursor = (trial, epoch)
            self._demand = tuple(
                dict.fromkeys(
                    self.schedule.aliases[(trial, asset)]
                    for row in self.schedule.epochs[trial][
                        epoch : epoch + 1 + LOOKAHEAD_EPOCHS
                    ]
                    for _, asset in row
                )
            )
            self._plan_dirty = True
        self.service()
        selected = []
        for snapshot in snapshots:
            settings = snapshot.settings
            requested = image_asset(settings) if settings is not None else None
            if requested is None or (trial, requested) not in self.schedule.aliases:
                selected.append(snapshot)
                continue
            consumer = (trial, snapshot.instance_id)
            key = self.schedule.aliases[(trial, requested)]
            actual = self._bound.get(consumer, self.schedule.first[consumer])
            if self.entries[key].state == "resident":
                actual = requested
                if self._bound.get(consumer) != actual:
                    previous = self._bound.get(consumer)
                    if previous is not None:
                        previous_key = self.schedule.aliases[(trial, previous)]
                        self._binding_counts[previous_key] -= 1
                        if self._binding_counts[previous_key] == 0:
                            del self._binding_counts[previous_key]
                    self._bound[consumer] = actual
                    self._binding_counts[key] += 1
                    self._plan_dirty = True
            actual_key = self.schedule.aliases[(trial, actual)]
            if self.entries[actual_key].state != "resident":
                raise RuntimeError("prepared first/previous image is not resident")
            assert settings is not None
            if requested == actual:
                pass
            elif settings.kind == "image":
                settings = settings.model_copy(update={"asset_id": actual})
            else:
                assert settings.kind == "texture"
                settings = settings.model_copy(
                    update={
                        "pattern": settings.pattern.model_copy(
                            update={"asset_id": actual}
                        )
                    }
                )
            image_index = self.schedule.indices[(trial, actual)]
            image = ImageSnapshot(
                snapshot.instance_id,
                requested,
                self.schedule.indices[(trial, requested)],
                actual,
                image_index,
                "current" if requested == actual else "residency_hold",
                self._last_indices.get(consumer) == image_index,
            )
            self._last_indices[consumer] = image_index
            selections, holds = self._counts.get(trial, (0, 0))
            self._counts[trial] = (selections + 1, holds + int(requested != actual))
            selected.append(replace(snapshot, settings=settings, image_selection=image))
        return tuple(selected)

    def close(self, deadline_ns: int) -> bool:
        return self.worker.close(deadline_ns)

    def release_gpu(self, deadline_ns: int | None = None) -> tuple[str, ...]:
        if self._gpu is None:
            return ()
        errors = []
        for key, entry in self.entries.items():
            if entry.state == "absent":
                if self._owner(key) in self._announced:
                    self.released_keys.add(self._owner(key))
                continue
            try:
                if entry.textures:
                    if deadline_ns is not None and self.clock_ns() >= deadline_ns:
                        errors.append(f"{self._owner(key)}:GPU completion pending")
                        continue
                    if entry.state != "retiring":
                        self._gpu.fence(entry.textures, entry.fences)
                        entry.state = "retiring"
                    ready = False
                    while deadline_ns is None or self.clock_ns() < deadline_ns:
                        ready = self._gpu.ready(entry.fences)
                        if ready or deadline_ns is None:
                            break
                        # Recheck the shared budget after yielding on the GL owner.
                        time.sleep(0)
                    if (
                        ready
                        and deadline_ns is not None
                        and self.clock_ns() >= deadline_ns
                    ):
                        ready = False
                    if not ready:
                        errors.append(f"{self._owner(key)}:GPU completion pending")
                        continue
                self._gpu.release(entry.textures, entry.fences)
                self.budget.release(owner=self._owner(key))
                entry.state = "absent"
                self._allocated.discard(key)
                self.released_keys.add(self._owner(key))
            except Exception as exc:
                errors.append(f"{self._owner(key)}:{exc}")
        if not errors:
            close_pool = getattr(self._gpu, "close_pool", None)
            if close_pool is not None:
                try:
                    owner = close_pool(self.budget)
                    if owner is not None:
                        self.released_keys.add(owner)
                except Exception as exc:
                    errors.append(f"image-pool:{exc}")
        if self._resources is not None:
            for trial, asset in self.schedule.aliases:
                self._resources.pop(f"{self.schedule.generations[trial]}:{asset}", None)
                self._resources.pop(
                    f"{self.schedule.generations[trial]}:{asset}:crops", None
                )
        return tuple(errors)
