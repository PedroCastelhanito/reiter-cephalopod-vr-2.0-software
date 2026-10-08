"""Acquisition-owned MP4 identity tags and JSONL header identity."""

from __future__ import annotations

from dataclasses import dataclass

from cephvr.acquisition.v1 import camera_pb2 as camera
from cephvr.shared.clock import HOST_CLOCK_ID
from cephvr.shared.identity import require_uuid4

_ROLES = {"behavioral", "tracking"}
MP4_IDENTITY_KEYS = (
    "cephvr_identity_version",
    "cephvr_session_id",
    "cephvr_trial_id",
    "cephvr_camera_role",
    "cephvr_device_id",
)


@dataclass(frozen=True)
class RecordingIdentity:
    session_id: str
    trial_id: str
    trial_number: int
    camera_role: str
    device_id: str
    session_config_reference: str
    camera_clock: camera.CameraClockDescriptor

    def validate(self) -> None:
        require_uuid4(self.session_id)
        require_uuid4(self.trial_id)
        if self.trial_number < 1:
            raise ValueError("recording trial number must be one-based")
        if self.camera_role not in _ROLES:
            raise ValueError("recording camera role is invalid")
        for label, value in (
            ("device ID", self.device_id),
            ("session config reference", self.session_config_reference),
        ):
            if not value or "\x00" in value:
                raise ValueError(
                    f"recording {label} must be nonempty UTF-8 without NUL"
                )
            value.encode("utf-8", "strict")
        if len(self.device_id.encode("utf-8")) > 1024:
            raise ValueError("camera device ID exceeds 1,024 UTF-8 bytes")
        clock = self.camera_clock
        if not clock.device_id or clock.device_id != self.device_id:
            raise ValueError("camera clock descriptor is not bound to recording device")
        _validate_clock_descriptor(clock)

    def header_identity(self) -> dict[str, object]:
        self.validate()
        return {
            "session_id": self.session_id,
            "trial_id": self.trial_id,
            "trial_number": self.trial_number,
            "camera_role": self.camera_role,
            "device_id": self.device_id,
            "session_config_reference": self.session_config_reference,
            "recording_identity_version": 1,
        }

    def mp4_tags(self) -> tuple[tuple[str, str], ...]:
        self.validate()
        return tuple(
            zip(
                MP4_IDENTITY_KEYS,
                ("1", self.session_id, self.trial_id, self.camera_role, self.device_id),
                strict=True,
            )
        )


def header_clocks(identity: RecordingIdentity, start_ns: int) -> dict[str, object]:
    descriptor = identity.camera_clock
    result: dict[str, object] = {
        "host_clock": HOST_CLOCK_ID,
        "timestamp_unit": "ns",
        "trial_start_monotonic_ns": start_ns,
        "camera_clock": "cephvr.camera.native.v1",
        "camera_clock_source": descriptor.timestamp_source,
        "camera_clock_conversion_available": descriptor.conversion_available,
        "camera_clock_tick_ns_numerator": (
            descriptor.tick_period_ns_numerator
            if descriptor.conversion_available
            else None
        ),
        "camera_clock_tick_ns_denominator": (
            descriptor.tick_period_ns_denominator
            if descriptor.conversion_available
            else None
        ),
        "camera_clock_timestamp_semantics": descriptor.timestamp_semantics,
        "camera_clock_reset_semantics": descriptor.reset_semantics,
        "camera_clock_wrap_semantics": descriptor.wrap_semantics,
        "camera_clock_unavailable_reason": descriptor.unavailable_reason,
        "camera_counter_source": descriptor.counter_source,
        "camera_counter_semantics": descriptor.counter_semantics,
        "camera_counter_width_bits": descriptor.counter_width_bits,
        "camera_counter_wrap_semantics": descriptor.counter_wrap_semantics,
        "camera_counter_unavailable_reason": descriptor.counter_unavailable_reason,
    }
    return result


def _validate_clock_descriptor(descriptor: camera.CameraClockDescriptor) -> None:
    required_text = (
        "timestamp_source",
        "timestamp_semantics",
        "reset_semantics",
        "wrap_semantics",
        "unavailable_reason",
        "counter_source",
        "counter_semantics",
        "counter_wrap_semantics",
        "counter_unavailable_reason",
    )
    for field in required_text:
        value = getattr(descriptor, field)
        optional_reason = field in {"unavailable_reason", "counter_unavailable_reason"}
        if (
            (not value and not optional_reason)
            or "\x00" in value
            or len(value.encode("utf-8", "strict")) > 1024
        ):
            raise ValueError(
                f"camera clock descriptor {field} is invalid or exceeds 1,024 bytes"
            )
    if not descriptor.HasField("conversion_available"):
        raise ValueError("camera timestamp conversion availability is unspecified")
    numerator = descriptor.HasField("tick_period_ns_numerator")
    denominator = descriptor.HasField("tick_period_ns_denominator")
    if descriptor.conversion_available:
        if (
            not numerator
            or not denominator
            or descriptor.tick_period_ns_numerator <= 0
            or descriptor.tick_period_ns_denominator <= 0
            or descriptor.unavailable_reason
        ):
            raise ValueError(
                "available camera clock requires a reduced positive tick ratio"
            )
        import math

        if (
            math.gcd(
                descriptor.tick_period_ns_numerator,
                descriptor.tick_period_ns_denominator,
            )
            != 1
        ):
            raise ValueError("camera clock tick ratio must be reduced")
    elif numerator or denominator or not descriptor.unavailable_reason:
        raise ValueError("unavailable camera clock requires null ratio and a reason")
    if not descriptor.HasField("counter_width_bits"):
        raise ValueError(
            "camera counter width must be explicit, with 0 meaning unknown"
        )
