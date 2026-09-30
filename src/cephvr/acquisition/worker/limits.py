"""Adopted, process-local acquisition worker retention ceilings (E08/A02)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AcquisitionControlLimits:
    """Immutable control budgets derived from shared transport limits at startup."""

    max_message_bytes: int
    max_records: int
    max_bytes: int
    normal_result_reservation_bytes: int
    large_result_reservation_bytes: int
    safety_reserve_records: int
    safety_reserve_bytes: int

    @classmethod
    def from_message_limit(cls, max_message_bytes: int) -> AcquisitionControlLimits:
        if type(max_message_bytes) is not int or max_message_bytes <= 0:
            raise ValueError("shared maximum message bytes must be a positive integer")
        return cls(
            max_message_bytes=max_message_bytes,
            max_records=1024,
            max_bytes=max(64 * 1024 * 1024, 4 * max_message_bytes),
            normal_result_reservation_bytes=64 * 1024,
            large_result_reservation_bytes=max_message_bytes,
            safety_reserve_records=16,
            safety_reserve_bytes=2 * 1024 * 1024,
        )

    def __post_init__(self) -> None:
        if (
            self.max_message_bytes <= 0
            or self.max_records != 1024
            or self.normal_result_reservation_bytes != 64 * 1024
            or self.large_result_reservation_bytes != self.max_message_bytes
            or self.max_bytes != max(64 * 1024 * 1024, 4 * self.max_message_bytes)
            or self.safety_reserve_records != 16
            or self.safety_reserve_bytes != 2 * 1024 * 1024
        ):
            raise ValueError("acquisition control limits do not match adopted ceilings")
