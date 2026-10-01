"""T09 completed pose selection and bounded borrowed geometry retirement."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from cephvr.control.v1.types_pb2 import WorkContext
from cephvr.tracking.config.models.records import PoseUse
from cephvr.tracking.types import PoseGeometryObservation


@dataclass
class _Entry:
    value: PoseGeometryObservation
    borrowed: int = 0


class PoseHistory:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("positive pose history capacity required")
        self.capacity = capacity
        self.lock = threading.Lock()
        self.entries: list[_Entry] = []
        self.retired: list[_Entry] = []

    def publish(self, value: PoseGeometryObservation) -> None:
        with self.lock:
            if (
                self.entries
                and value.observation.source.frame_id
                <= self.entries[-1].value.observation.source.frame_id
            ):
                raise ValueError("pose completion source order regressed")
            if len(self.entries) == self.capacity:
                entry = self.entries.pop(0)
                self.retired.append(entry)
            self.entries.append(_Entry(value))

    def select(
        self,
        work: WorkContext,
        preparation: str,
        attachment: str,
        later_id: int,
        now: int,
        maximum_age: int,
    ) -> tuple[PoseUse, PoseGeometryObservation | None]:
        with self.lock:
            selected = next(
                (
                    entry
                    for entry in reversed(self.entries)
                    if entry.value.work == work
                    and entry.value.preparation_id == preparation
                    and entry.value.source_attachment_generation == attachment
                    and entry.value.observation.source.frame_id <= later_id
                ),
                None,
            )
            if selected is None:
                return PoseUse(
                    disposition="missing",
                    observation_id=None,
                    manual_geometry_id=None,
                    check_host_ns=now,
                    pose_source_host_ns=None,
                    age_ns=None,
                    maximum_age_ns=maximum_age,
                ), None
            value = selected.value
            observed = value.observation
            age = now - observed.source.host_receipt_ns
            if age < 0:
                raise ValueError("negative pose source age")
            disposition = "stale" if age > maximum_age else observed.validity
            selected.borrowed += 1
            return PoseUse(
                disposition=disposition,
                observation_id=observed.observation_id,
                manual_geometry_id=None,
                check_host_ns=now,
                pose_source_host_ns=observed.source.host_receipt_ns,
                age_ns=age,
                maximum_age_ns=maximum_age,
            ), value

    def release(self, value: PoseGeometryObservation) -> None:
        with self.lock:
            entry = next(
                (
                    item
                    for item in (*self.entries, *self.retired)
                    if item.value is value
                ),
                None,
            )
            if entry is None or entry.borrowed <= 0:
                raise ValueError("unknown or already returned pose borrow")
            entry.borrowed -= 1

    def clear(self) -> None:
        with self.lock:
            self.retired.extend(self.entries)
            self.entries.clear()

    def take_retired(self) -> tuple[PoseGeometryObservation, ...]:
        """Called only by geometry owner; borrowed arrays stay retained."""
        with self.lock:
            ready = tuple(entry.value for entry in self.retired if not entry.borrowed)
            self.retired[:] = [entry for entry in self.retired if entry.borrowed]
            return ready
