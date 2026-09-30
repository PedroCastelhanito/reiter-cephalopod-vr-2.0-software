"""A01/A10 declaration only: no SDK imports, device access or implementation.

Called inside the camera worker by its serialized device/lifecycle owner.
Worker owns trial IDs, host receipt timestamps, rings and reports. Adapter owns
SDK operations and source metadata extraction/conversion. See README for gaps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from cephvr.shared.pixels.types import NativePixelFormat as NativePixelFormat
from cephvr.shared.pixels.types import PixelLayout as PixelLayout

CameraRole = Literal["behavioral", "tracking"]
FrameTiming = Literal["external_trigger", "free_running"]


# Mirrors camera.proto; None means unresolved/not applicable, never implicit zero.
# Validation, units and SDK mappings: camera-settings.md.
@dataclass(frozen=True)
class CameraRoi:
    width: int | None
    height: int | None
    offset_x: int | None
    offset_y: int | None


@dataclass(frozen=True)
class CameraGain:
    value: int | float
    unit: str
    selector: str | None


@dataclass(frozen=True)
class CameraSettings:
    exposure_us: float | None
    gain: CameraGain | None
    frame_rate_hz: float | None
    roi: CameraRoi | None
    pixel_format: str | None
    trigger_selector: str | None
    trigger_source: str | None
    trigger_activation: str | None
    exposure_duration_mode: str | None


TransportInterface = Literal["usb3", "gige"]
TransportValue = bool | int | float | str


@dataclass(frozen=True)
class TransportOverride:
    """Exact SDK transport name and native scalar value; never executable node access.

    Preserve types; float values must be finite and strings are SDK enum symbols.
    Validate against the supported mapping plus connected-node type/range/choices.
    """

    sdk_name: str
    value: TransportValue


@dataclass(frozen=True)
class TransportSettings:
    """Unique SDK-named entries from one camera's transport TOML table.

    SDK defaults fill omissions. Mapping selects node map and USB3/GigE applicability;
    concrete mappings are in sdk-mappings.md. Reject duplicates, unknown names,
    mismatched interfaces/types/units and unavailable or unwritable requested nodes.
    No arbitrary node writes, auto-tuning or OS changes; read back applied values.
    """

    overrides: tuple[TransportOverride, ...]


@dataclass(frozen=True)
class TransportCounters:
    """Optional uint64 SDK counters; None means unavailable, never measured zero.

    Camera worker supplies host observation time/run context. Adapter-specific counter
    continuity/reset rules must establish comparability before any delta is reported.
    """

    buffer_underruns: int | None
    failed_buffers: int | None
    missed_frames: int | None
    resend_requests: int | None
    resend_packets: int | None
    resynchronizations: int | None


FeatureAccess = Literal["unavailable", "read_only", "read_write"]


@dataclass(frozen=True)
class FloatCapability:
    access: FeatureAccess
    minimum: float | None
    maximum: float | None
    increment: float | None
    unit: str


@dataclass(frozen=True)
class IntegerCapability:
    access: FeatureAccess
    minimum: int | None
    maximum: int | None
    increment: int | None
    unit: str


@dataclass(frozen=True)
class EnumChoice:
    value: str
    sdk_symbol: str


@dataclass(frozen=True)
class EnumCapability:
    access: FeatureAccess
    choices: tuple[EnumChoice, ...]


@dataclass(frozen=True)
class GainCapability:
    numeric: FloatCapability | IntegerCapability | None
    selector: EnumCapability


@dataclass(frozen=True)
class RoiCapabilities:
    width: IntegerCapability
    height: IntegerCapability
    offset_x: IntegerCapability
    offset_y: IntegerCapability


@dataclass(frozen=True)
class TriggerRateLimit:
    maximum_hz: float | None
    evidence: str


@dataclass(frozen=True)
class CameraCapabilities:
    """Current connected settings combination; unknown trigger limit warns (A10)."""

    exposure_us: FloatCapability
    gain: GainCapability
    frame_rate_hz: FloatCapability
    roi: RoiCapabilities
    pixel_format: EnumCapability
    trigger_selector: EnumCapability
    trigger_source: EnumCapability
    trigger_activation: EnumCapability
    exposure_duration_mode: EnumCapability
    trigger_rate_limit: TriggerRateLimit


@dataclass(frozen=True)
class CameraDeviceIdentity:
    configured_id: str
    physical_id: str
    model: str
    transport_interface: TransportInterface


class SettingAdjustment(Protocol):
    @property
    def field(self) -> str: ...

    @property
    def requested_display(self) -> str: ...

    @property
    def actual_display(self) -> str: ...

    # Display text explains a warning; actual settings stay typed in CameraSettings.


class SettingsReadback(Protocol):
    @property
    def actual(self) -> CameraSettings: ...

    @property
    def adjustments(self) -> tuple[SettingAdjustment, ...]: ...

    @property
    def effective_exposure_us(self) -> float | None: ...

    # Warn/accept actual before locking; revalidate dependent consumers before Ready.


@dataclass(frozen=True)
class NativeMetadataWarning:
    code: Literal["NATIVE_TIMESTAMP_UNAVAILABLE", "NATIVE_COUNTER_UNAVAILABLE"]
    sdk_code: str | None
    details: str


@dataclass(frozen=True)
class CameraClockDescriptor:
    device_id: str
    timestamp_source: str
    conversion_available: bool
    tick_period_ns_numerator: int | None
    tick_period_ns_denominator: int | None
    timestamp_semantics: str
    reset_semantics: str
    wrap_semantics: str
    unavailable_reason: str
    counter_source: str
    counter_semantics: str
    counter_width_bits: int | None
    counter_wrap_semantics: str
    counter_unavailable_reason: str
    # Mirrors camera.proto. No host offset, guessed frequency or per-frame copy.


@dataclass(frozen=True)
class NativeMetadataSupport:
    """Effective optional capability; per-frame presence still requires validation.

    Timestamp units/counter meaning must be known. Warnings describe unavailable
    optional fields; confirmed device failures are raised/reported independently.
    Effective SDK setting readback follows the normal controller adoption path.
    """

    timestamp_available: bool
    frame_counter_available: bool
    warnings: tuple[NativeMetadataWarning, ...]  # Stable codes; never parse SDK prose.
    camera_clock: CameraClockDescriptor


class GrabResult(Protocol):
    valid_image: bool
    pixels: (
        memoryview | None
    )  # None for invalid images; no scientific pixel conversion.
    layout: PixelLayout | None
    # SDK result evidence for comparison with the prepared buffer descriptor.
    # Do not duplicate this description in each shared frame slot.
    camera_frame_counter: int | None
    camera_timestamp_ns: int | None  # Device origin, converted units, NOT host aligned.
    error_code: str | None
    error_message: str | None

    def release(self) -> None: ...

    # SDK pixels valid only until release. Worker copies before release, even when
    # the downstream consumer will later make its own protected working copy.


@dataclass(frozen=True)
class PurgeEvidence:
    # Disjoint SDK results discarded by this call, including internal SDK-stop flushes.
    # None = unavailable, never zero. Last counter uses unchanged native semantics.
    discarded_frame_count: int | None
    last_native_counter: int | None
    accounting_complete: bool


class CameraAdapter(Protocol):
    def open(self, device_id: str) -> None: ...
    def read_device_identity(self) -> CameraDeviceIdentity: ...
    # Exact opened device, including stable physical identity for duplicate detection.
    def capabilities(self) -> CameraCapabilities: ...
    # Query the connected SDK; do not substitute static model-limit tables.
    def apply_settings(self, settings: CameraSettings) -> SettingsReadback: ...
    # Failure (including partial application) raises; no automatic hardware rollback.
    # Owner keeps capture/pulses stopped and reports diagnostic readback if available.
    def read_settings(self) -> CameraSettings: ...

    def read_frame_timing(self) -> FrameTiming: ...
    # Readback can resolve missing features; controller adopts/publishes/logs values.
    # Readback after failure is actual-state evidence, not application success.
    # Before each trial, read back pixel format, dimensions, trigger mode, exposure
    # and gain against confirmed settings. Unreadable/mismatched values fail
    # preparation; never automatically reapply or adopt drift in a locked session.
    def apply_transport_settings(
        self, settings: TransportSettings
    ) -> TransportSettings: ...
    # Capture stopped; returns resolved settings for controller adoption. Fail explicit
    # invalid/unsupported overrides; leave omissions at SDK defaults, no auto-tuning.
    def read_transport_counters(self) -> TransportCounters: ...
    # Best-effort boundary observations, not a per-frame call. Unavailable diagnostic
    # values do not fail capture; confirmed device failures retain normal reporting.
    def configure_native_metadata(self) -> NativeMetadataSupport: ...
    # Setup, capture stopped, before final settings/layout readback and buffers.
    # Keep usable native metadata; enable supported timestamp/counter metadata if needed.
    # No trigger reconfiguration or invented units/counter semantics. Optional absence
    # warns/continues; SDK/device failures retain their existing classification.
    def read_layout(self) -> PixelLayout: ...
    # Resolve after applying settings, before buffer preparation/Ready. A changed
    # layout requires re-preparation; never resize/reinterpret active session rings.
    def configure_capture(self, timing: FrameTiming, sdk_buffer_count: int) -> None: ...
    def begin_terminal_drain(self) -> bool: ...
    def confirm_drain_margin(self) -> None: ...
    # Ordered delivery with Basler GrabLoop_ProvidedByUser (A02).
    # Worker owns retrieval; do not enable the SDK's callback/grab-loop thread.
    def purge_stale_frames(
        self,
        deadline_monotonic_ns: int,
        *,
        should_continue_drain: Callable[[], bool],
    ) -> PurgeEvidence: ...
    def arm_external_trigger(self) -> None: ...
    def start_free_running(self) -> None: ...
    def wait_for_frame_or_control(
        self, timeout_ns: int
    ) -> Literal["frame", "control", "timeout"]: ...
    # Lifecycle owner only; joint SDK-result/control wait, bounded by nearest deadline.
    # Must release GIL; idle mode excludes inactive SDK object. See capture-wait.md.
    def wake_control(self) -> None: ...
    # Thread-safe signal only; permitted from existing control/health handlers.
    def clear_control_wake(self) -> None: ...
    # Owner only under command-handoff lock, after finding no pending command.
    def retrieve(self, timeout_ns: int) -> GrabResult | None: ...
    # New loop uses timeout_ns=0 after combined wait; recheck commands between frames.
    # None = no result available, not itself a health-policy decision.
    # Worker calls shared host_time_ns() immediately on return, before payload copies.
    # Unshifted time.perf_counter_ns domain; see ../host-clock.md.
    # Report implicit SDK discards as well; do not silently flush trial evidence.
    # Stop/drain separation and bounded completion are SDK/rig verification obligations.
    def stop_capture(
        self,
        deadline_monotonic_ns: int,
        *,
        should_continue_drain: Callable[[], bool],
    ) -> PurgeEvidence: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class PfsSnapshot:
    """A10: SDK-generated snapshot of persistable camera features, not all device state.

    Retain with standard typed settings in controller configuration/reusable history.
    Exclude contents from session/trial logs; external preset references use filenames.
    Snapshot text is SDK data, not an arbitrary CephVR feature-write API.
    """

    text: str


class BaslerCameraAdapter(CameraAdapter, Protocol):
    # PFS operations require the assigned camera open via SDK; preview is unnecessary.
    # No offline pending import or export of cached snapshots as current device state.
    # Worker opens the assigned device on demand and retains an editing connection
    # across related calls, then closes/releases on explicit editing completion or
    # expiry of E03's control-loss grace. Setup also finishes editing and waits for
    # release before preparation. The adapter owns no client/grace/Setup timer.
    # Import/export methods do not independently close an existing preview connection.
    def apply_pfs_snapshot(self, snapshot: PfsSnapshot) -> SettingsReadback: ...
    # Assigned camera open, capture/pulses stopped; SDK LoadFromString with validation.
    # Apply retained baseline before explicit typed edits; no source-file reread/tempfile.
    # Failure/partial application raises, with diagnostic readback if possible.
    def capture_pfs_snapshot(self) -> PfsSnapshot: ...
    # Serialized SDK access after successful import/device edits and readback.
    # Caller binds the result to that same configuration revision before adoption.
    def import_pfs(self, path: str) -> SettingsReadback: ...
    # Load and SDK-validate on the assigned camera; no same-model-only gate.
    # Return imported actual camera values for controller adoption, then allow edits.
    # Failure/partial application raises under A10; never silently skip bad features.
    def export_pfs(self, new_path: str) -> None: ...

    # Worker first validates/applies pending camera edits, reads back and refreshes
    # the retained snapshot; failure prevents this export call, not a stale fallback.
    # Configuration-only, serialized SDK export to a user-selected new file.
    # Never silently overwrite the source PFS or start images.


# SDK failures raise adapter errors preserving a stable code and descriptive cause.
# Exception/native-format bindings are in sdk-mappings.md; no
# backend timeouts, automatic retries, trigger MCU ownership or logging live here.
