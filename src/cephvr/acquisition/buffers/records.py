"""Authoritative per-received-frame record shared by acquisition writers (A07/A09)."""

from __future__ import annotations

from dataclasses import dataclass

_FRAME_DIAGNOSTIC_CODES = frozenset(
    {
        "INVALID_IMAGE",
        "NATIVE_COUNTER_GAP",
        "NATIVE_COUNTER_DISCONTINUITY",
        "NATIVE_TIMESTAMP_UNAVAILABLE",
        "NATIVE_COUNTER_UNAVAILABLE",
    }
)


@dataclass(frozen=True, slots=True)
class FrameDiagnostic:
    """One stable catalogue occurrence attached to a frame record."""

    code: str
    native_code: str | None = None
    details: str | None = None

    def __post_init__(self) -> None:
        if not self.code or len(self.code.encode("utf-8")) > 64:
            raise ValueError(
                "diagnostic code must be stable and at most 64 UTF-8 bytes"
            )
        if self.code not in _FRAME_DIAGNOSTIC_CODES:
            raise ValueError(f"unsupported frame diagnostic code {self.code!r}")
        if self.native_code is not None and len(self.native_code.encode("utf-8")) > 64:
            raise ValueError("native diagnostic code exceeds 64 UTF-8 bytes")
        if self.details is not None and len(self.details.encode("utf-8")) > 1024:
            raise ValueError("diagnostic details exceed 1024 UTF-8 bytes")


@dataclass(frozen=True, slots=True)
class FrameRecord:
    """Identity and capture-time evidence for one received frame, valid or invalid."""

    frame_id: int
    acquisition_time_ns: int
    camera_frame_counter: int | None
    camera_timestamp_ns: int | None
    valid_image: bool
    invalid_code: str | None
    diagnostics: tuple[FrameDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.frame_id < 0 or self.acquisition_time_ns <= 0:
            raise ValueError(
                "frame ID and host receipt time must be nonnegative/positive"
            )
        for name in ("camera_frame_counter", "camera_timestamp_ns"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be nonnegative when present")
        if self.valid_image and self.invalid_code is not None:
            raise ValueError("valid image cannot carry an invalid-image code")
        if not self.valid_image and self.invalid_code != "INVALID_IMAGE":
            raise ValueError("invalid SDK image must use stable INVALID_IMAGE code")
        if len(self.diagnostics) > 8:
            raise ValueError("frame diagnostic entries exceed the bounded catalogue")
