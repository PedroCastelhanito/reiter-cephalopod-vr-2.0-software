"""Prepare immutable disk samples and replace image loaders before Ready."""

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, BinaryIO, cast

from cephvr.shared.temporary_bundle import TemporaryBundle

from .budget import BoundedBudget
from .image_schedule import ImageSchedule

PREPARATION_BATCH_IMAGES = 16


class ImageBundle:
    def __init__(
        self, parent: Path, announce: Callable[[str, str | None], None]
    ) -> None:
        self.key = "visual_stimulus:image-bundle"
        announce(self.key, None)
        self.storage = TemporaryBundle(parent)
        self.manifest: dict[str, dict[str, Any]] = {}
        self.reused_references = 0
        self._buffer = bytearray()
        self._budget: BoundedBudget | None = None

    def progress_stage(self, completed: int, total: int) -> str:
        batches = max(
            1, (total + PREPARATION_BATCH_IMAGES - 1) // PREPARATION_BATCH_IMAGES
        )
        batch = (max(1, completed) - 1) // PREPARATION_BATCH_IMAGES + 1
        return (
            f"Preparing projector crop bundle (batch {batch}/{batches}; "
            f"{self.reused_references} repeated uses shared)"
        )

    def prepare(
        self,
        schedule: ImageSchedule,
        bake: Callable[..., bytes | bytearray],
        budget: BoundedBudget,
        progress: Callable[[int, int], None],
        *,
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
        required = sum(source.gpu_bytes for source in selected)
        if shutil.disk_usage(self.storage.directory).free < required + max(
            (s.cpu_bytes for s in selected), default=0
        ):
            raise OSError(
                f"temporary crop bundle needs {required} bytes plus preparation headroom"
            )
        size = max((s.gpu_bytes for s in selected), default=0)
        budget.reserve(owner=self.key, cpu_bytes=size, gpu_bytes=0)
        self._budget = budget
        self._buffer = bytearray(size)
        index: dict[str, dict[str, Any]] = {}
        progress(0, len(selected))
        for start in range(0, len(selected), PREPARATION_BATCH_IMAGES):
            batch = selected[start : start + PREPARATION_BATCH_IMAGES]
            owner = "visual_stimulus:crop-bake"
            target_width = max(c.target[0] for s in batch for c in s.output_crops)
            target_height = max(c.target[1] for s in batch for c in s.output_crops)
            budget.reserve(
                owner=owner,
                cpu_bytes=max(s.cpu_bytes + 2 * s.gpu_bytes for s in batch),
                gpu_bytes=max(s.width * s.height * 16 for s in batch)
                + target_width * target_height * 16,
            )
            try:
                file = self.storage.add(b"")
                for number, source in enumerate(batch, start + 1):
                    check = budget.check_cancelled_or_expired
                    check()
                    raw = source.load(check)
                    pixels = bake(source, raw, check)
                    del raw
                    if len(pixels) != source.gpu_bytes:
                        raise ValueError("prepared crop byte count mismatch")
                    offset = file.tell()
                    if file.write(pixels) != len(pixels):
                        raise OSError("incomplete crop bundle write")
                    digest = hashlib.sha256(pixels).hexdigest()
                    self.manifest[source.key] = {
                        "sha256": digest,
                        "byte_count": len(pixels),
                        "crops": tuple(asdict(c) for c in source.output_crops),
                    }
                    index[source.key] = {"file": Path(file.name).name, "offset": offset}

                    def load(
                        check: Callable[[], None],
                        file: BinaryIO = file,
                        offset: int = offset,
                        count: int = len(pixels),
                        expected: str = digest,
                        timings: Any = source.timings,
                    ) -> memoryview:
                        check()
                        started = time.perf_counter_ns()
                        file.seek(offset)
                        data = memoryview(self._buffer)[:count]
                        position = 0
                        while position < count:
                            check()
                            received = cast(Any, file).readinto(data[position:])
                            if not received:
                                raise ValueError("prepared crop bundle truncated")
                            position += received
                        timings.record("bundle_read", time.perf_counter_ns() - started)
                        started = time.perf_counter_ns()
                        if (
                            len(data) != count
                            or hashlib.sha256(data).hexdigest() != expected
                        ):
                            raise ValueError("prepared crop bundle content changed")
                        timings.record("bundle_hash", time.perf_counter_ns() - started)
                        check()
                        return data

                    # Loads fill the bundle-owned buffer reserved once above.
                    sources[source.key] = replace(source, load=load, cpu_bytes=0)
                    del pixels
                    progress(number, len(selected))
                file.flush()
            finally:
                if finish_batch is not None:
                    finish_batch()
                budget.release(owner=owner)
        self.storage.add(
            json.dumps(
                {"images": self.manifest, "storage": index}, sort_keys=True
            ).encode(),
            suffix=".manifest.json",
        )
        return replace(schedule, sources=sources)

    def close(self) -> None:
        self.storage.close()
        self._buffer = bytearray()
        if self._budget is not None:
            self._budget.release(owner=self.key)
            self._budget = None
