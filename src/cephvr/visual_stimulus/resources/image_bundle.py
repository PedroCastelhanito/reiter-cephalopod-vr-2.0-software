"""Reuse or bake persistent Fold sample bundles and replace image loaders before Ready."""

import hashlib
import json
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, cast

from .budget import BoundedBudget
from .image_bundle_store import (
    SAMPLES_NAME,
    BundleStore,
    StoredBundle,
    bundle_key,
)
from .image_schedule import ImageSchedule
from .image_source import ImageSource

if TYPE_CHECKING:
    from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial

    from .assets import PreparedAsset

PREPARATION_BATCH_IMAGES = 16
SAMPLE_FORMAT = "fold-samples-rgba32f-v1"


class ImageBundle:
    """Setup-owned bundle readers; bundles themselves outlive the Setup."""

    def __init__(
        self,
        asset_root: Path,
        announce: Callable[[str, str | None], None],
        *,
        names: Mapping[str, tuple[str, ...]],
        geometry: Mapping[str, str],
        on_replaced: Callable[[tuple[StoredBundle, ...]], None] | None = None,
    ) -> None:
        """`names`/`geometry`: per schedule key, relative source file names and the
        digest of each used projector's calibration and display geometry.
        `on_replaced` receives stale entries once their replacement is published."""
        self.key = "visual_stimulus:image-bundle"
        announce(self.key, None)
        self.store = BundleStore(asset_root)
        self.names = names
        self.geometry = geometry
        self.on_replaced = on_replaced
        self.manifest: dict[str, dict[str, Any]] = {}
        self.reused_references = 0
        self.reused_bundles = 0
        # Stale entries whose replacement is published; deleted only on request.
        self.replaced: list[StoredBundle] = []
        self._reused: list[StoredBundle] = []
        self._files: list[BinaryIO] = []
        self._buffer = bytearray()
        self._budget: BoundedBudget | None = None

    def progress_stage(self, completed: int, total: int) -> str:
        batches = max(
            1, (total + PREPARATION_BATCH_IMAGES - 1) // PREPARATION_BATCH_IMAGES
        )
        batch = (max(1, completed) - 1) // PREPARATION_BATCH_IMAGES + 1
        return (
            f"Preparing projector crop bundles (batch {batch}/{batches}; "
            f"{self.reused_bundles} saved bundles reused; "
            f"{self.reused_references} repeated uses shared)"
        )

    def _key_fields(
        self, source: ImageSource, device: Mapping[str, str], algorithm: str
    ) -> dict[str, Any]:
        return {
            "format": SAMPLE_FORMAT,
            "source": source.key,  # Protected source SHA-256 and interpretation.
            "geometry": self.geometry[source.key],
            "fit": "fold",
            "crops": _crop_records(source),
            "algorithm": algorithm,
            "device": dict(device),
        }

    def prepare(
        self,
        schedule: ImageSchedule,
        bake: Callable[..., bytes | bytearray],
        budget: BoundedBudget,
        progress: Callable[[int, int], None],
        *,
        device: Mapping[str, str],
        algorithm: str,
        finish_batch: Callable[[], None] | None = None,
    ) -> ImageSchedule:
        sources = dict(schedule.sources)
        # Schedule keys already combine content, interpretation and compatible mappings.
        selected = [source for source in sources.values() if source.output_crops]
        keys = {source.key for source in selected}
        references = sum(
            schedule.aliases[(trial, asset)] in keys
            for trial, rows in schedule.epochs.items()
            for row in rows
            for _, asset in row
        )
        self.reused_references = max(0, references - len(selected))
        size = max((s.gpu_bytes for s in selected), default=0)
        budget.reserve(owner=self.key, cpu_bytes=size, gpu_bytes=0)
        self._budget = budget
        self._buffer = bytearray(size)
        entries = self.store.entries()
        self._reused = []
        misses: list[tuple[ImageSource, dict[str, Any], tuple[StoredBundle, ...]]] = []
        progress(0, len(selected))
        for source in selected:
            fields = self._key_fields(source, device, algorithm)
            key = bundle_key(fields)
            entry = next(
                (e for e in entries if e.key == key and _matches(e, source)), None
            )
            if entry is not None:
                sources[source.key] = self._install(source, entry.directory, entry)
                self._reused.append(entry)
                self.reused_bundles += 1
                progress(self.reused_bundles, len(selected))
            else:
                stale = self.store.stale(entries, self.names[source.key])
                misses.append((source, {**fields, "key": key}, stale))
        # An entry reused here is open for reading; never offer it for deletion.
        reused = {entry.directory for entry in self._reused}
        offered: set[Path] = set()
        if misses:
            self._admit_disk(misses, budget)
        done = self.reused_bundles
        for start in range(0, len(misses), PREPARATION_BATCH_IMAGES):
            batch = misses[start : start + PREPARATION_BATCH_IMAGES]
            owner = "visual_stimulus:crop-bake"
            target_width = max(c.target[0] for s, _, _ in batch for c in s.output_crops)
            target_height = max(
                c.target[1] for s, _, _ in batch for c in s.output_crops
            )
            budget.reserve(
                owner=owner,
                cpu_bytes=max(s.cpu_bytes + 2 * s.gpu_bytes for s, _, _ in batch),
                gpu_bytes=max(s.width * s.height * 16 for s, _, _ in batch)
                + target_width * target_height * 16,
            )
            try:
                for source, fields, stale in batch:
                    check = budget.check_cancelled_or_expired
                    check()
                    directory = self._bake(source, fields, bake, check)
                    sources[source.key] = self._install(source, directory, None)
                    fresh = tuple(
                        entry
                        for entry in stale
                        if entry.directory not in reused | offered
                    )
                    offered.update(entry.directory for entry in fresh)
                    self.replaced.extend(fresh)
                    if fresh and self.on_replaced is not None:
                        self.on_replaced(fresh)
                    done += 1
                    progress(done, len(selected))
            finally:
                if finish_batch is not None:
                    finish_batch()
                budget.release(owner=owner)
        return replace(schedule, sources=sources)

    def _admit_disk(
        self,
        misses: list[tuple[ImageSource, dict[str, Any], tuple[StoredBundle, ...]]],
        budget: BoundedBudget,
    ) -> None:
        try:
            self.store.root.mkdir(exist_ok=True)
        except OSError as exc:
            raise OSError(
                f"asset folder is not writable for Fold bundles ({self.store.root}): {exc}"
            ) from exc
        required = sum(source.gpu_bytes for source, _, _ in misses)
        headroom = max(source.cpu_bytes for source, _, _ in misses)
        if shutil.disk_usage(self.store.root).free < required + headroom:
            raise OSError(
                f"asset folder lacks space for Fold bundles: {required} bytes "
                "plus preparation headroom required"
            )

    def _bake(
        self,
        source: ImageSource,
        fields: Mapping[str, Any],
        bake: Callable[..., bytes | bytearray],
        check: Callable[[], None],
    ) -> Path:
        writer = self.store.begin(self.names[source.key], fields["key"])
        try:
            raw = source.load(check)
            pixels = bake(source, raw, check)
            del raw
            if len(pixels) != source.gpu_bytes:
                raise ValueError("prepared crop byte count mismatch")
            writer.write(pixels)
            digest = hashlib.sha256(pixels).hexdigest()
            del pixels
            check()
            return writer.publish(
                {
                    "key": fields["key"],
                    "key_fields": {k: v for k, v in fields.items() if k != "key"},
                    "sources": sorted(self.names[source.key]),
                    "sha256": digest,
                    "byte_count": source.gpu_bytes,
                    "crops": _crop_records(source),
                }
            )
        except BaseException:
            writer.abandon()
            raise

    def _install(
        self, source: ImageSource, directory: Path, entry: StoredBundle | None
    ) -> ImageSource:
        manifest = (
            entry.manifest
            if entry is not None
            else json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
        )
        assert manifest is not None
        expected = str(manifest["sha256"])
        count = int(manifest["byte_count"])
        file = cast(BinaryIO, (directory / SAMPLES_NAME).open("rb"))
        self._files.append(file)
        self.manifest[source.key] = {
            "sha256": expected,
            "byte_count": count,
            "crops": tuple(asdict(c) for c in source.output_crops),
        }

        def load(check: Callable[[], None]) -> memoryview:
            check()
            started = time.perf_counter_ns()
            file.seek(0)
            data = memoryview(self._buffer)[:count]
            position = 0
            while position < count:
                check()
                received = cast(Any, file).readinto(data[position:])
                if not received:
                    raise ValueError("prepared crop bundle truncated")
                position += received
            source.timings.record("bundle_read", time.perf_counter_ns() - started)
            started = time.perf_counter_ns()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("prepared crop bundle content changed")
            source.timings.record("bundle_hash", time.perf_counter_ns() - started)
            check()
            return data

        # Loads fill the bundle-owned buffer reserved once in prepare().
        return replace(source, load=load, cpu_bytes=0)

    def close(self) -> None:
        """Close readers; bundles stay on disk for later Setups."""
        while self._files:
            self._files[-1].close()
            self._files.pop()
        self._buffer = bytearray()
        if self._budget is not None:
            self._budget.release(owner=self.key)
            self._budget = None


def _crop_records(source: ImageSource) -> list[dict[str, Any]]:
    """JSON-normalized crops, comparable with a stored manifest."""
    return cast(
        list[dict[str, Any]],
        json.loads(json.dumps([asdict(c) for c in source.output_crops])),
    )


def _matches(entry: StoredBundle, source: ImageSource) -> bool:
    """Reuse only when the manifest agrees with the prepared trial's crops."""
    manifest = entry.manifest
    return (
        manifest is not None
        and manifest["byte_count"] == source.gpu_bytes
        and manifest.get("crops") == _crop_records(source)
    )


def bundle_identities(
    schedule: ImageSchedule,
    artifacts: "tuple[PreparedTrial, ...]",
    assets: "Callable[[str], Mapping[str, PreparedAsset]]",
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Per image key: relative source file names and a digest of the display
    geometry plus each used projector's geometric calibration."""
    by_trial = {artifact.identity.trial_id: artifact for artifact in artifacts}
    names: dict[str, set[str]] = {}
    geometry: dict[str, str] = {}
    for (trial, asset_id), key in schedule.aliases.items():
        names.setdefault(key, set()).add(assets(trial)[asset_id].logical_path)
        crops = schedule.sources[key].output_crops
        if key in geometry or not crops:
            continue
        artifact = by_trial[trial]
        used = {crop.mapping_id for crop in crops}
        record = {
            "display_geometry": artifact.display.geometry.model_dump(mode="json"),
            "calibration": [
                profile.model_dump(mode="json")
                for profile in artifact.geometric_calibration
                if profile.mapping_id in used
            ],
        }
        geometry[key] = hashlib.sha256(
            json.dumps(record, sort_keys=True).encode()
        ).hexdigest()
    return {key: tuple(sorted(value)) for key, value in names.items()}, geometry
