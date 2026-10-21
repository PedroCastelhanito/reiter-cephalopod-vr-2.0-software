"""Focused presentation records; these do not confer controller authority."""

from dataclasses import dataclass
from enum import StrEnum


class Phase(StrEnum):
    CONFIGURATION = "Configuration"
    SETTING_UP = "Setting up"
    READY = "Ready"
    STARTING = "Starting"
    RUNNING = "Running"
    STOPPING = "Stopping"
    FINALIZING = "Finalizing"
    ENDED = "Ended"


@dataclass(frozen=True)
class PreviewView:
    """Reported viewer visibility, separate from experiment participation."""

    key: str
    name: str
    visible: bool = False
    available: bool = False
    reason: str = "Viewer connection unavailable"
    pending: bool = False
    active: bool = False
    source_fps: float | None = None
    preview_fps: float | None = None
    rates_observed_ns: int = 0


@dataclass(frozen=True)
class DashboardView:
    phase: Phase = Phase.CONFIGURATION
    connected: bool = False
    has_control: bool = False
    sample: bool = False
    configuration_wired: bool = True
    cleanup_confirmed: bool = False
    cleanup_pending: bool = False
    trial_index: int = 0
    trial_count: int = 0
    elapsed_s: float | None = None
    remaining_s: float | None = None
    trial_duration_s: float | None = None
    total_elapsed_s: float | None = None
    total_duration_s: float | None = None
    outcome: str = "—"
    camera_status: str = "Unavailable"
    stimulus_status: str = "Unavailable"
    tracking_status: str = "Unavailable"
    output_status: str = "No controller evidence"
    output_directory: str = ""
    reservation_status: str = "Not started"
    previews: tuple[PreviewView, ...] = ()

    @property
    def can_edit(self) -> bool:
        return (
            (self.sample or self.connected)
            and not self.cleanup_pending
            and self.configuration_wired
            and self.has_control
            and (
                self.phase in {Phase.CONFIGURATION, Phase.READY}
                or self.phase == Phase.ENDED
                and self.cleanup_confirmed
            )
        )

    @property
    def can_edit_session(self) -> bool:
        """Completed-session edits are drafts for the next session."""
        return self.can_edit


def review_view(phase: Phase, *, observer: bool = False) -> DashboardView:
    running = phase in {Phase.RUNNING, Phase.STOPPING, Phase.FINALIZING, Phase.ENDED}
    prepared = phase not in {Phase.CONFIGURATION, Phase.SETTING_UP}
    return DashboardView(
        phase=phase,
        sample=True,
        has_control=not observer,
        cleanup_confirmed=phase == Phase.ENDED,
        previews=tuple(
            PreviewView(key, name, available=True, active=True, reason="")
            for key, name in (
                ("camera-1", "Behavior cam"),
                ("camera-2", "Tracking cam"),
                ("tracking", "Tracking"),
                ("stimulus", "Visual stimulus"),
            )
        ),
        trial_index=6 if phase == Phase.ENDED else 2 if running else 0,
        trial_count=6,
        elapsed_s=150 if phase == Phase.ENDED else 48 if running else None,
        remaining_s=0 if phase == Phase.ENDED else 102 if running else None,
        trial_duration_s=150,
        total_elapsed_s=900 if phase == Phase.ENDED else 198 if running else None,
        total_duration_s=900,
        outcome="Completed" if phase == Phase.ENDED else "—",
        camera_status="Ready" if prepared else "Not prepared",
        stimulus_status="Ready" if prepared else "Not prepared",
        tracking_status="Ready" if prepared else "Not prepared",
        output_directory="D:/CephVR/SP0001-120000" if prepared else "",
        output_status="Closed"
        if phase == Phase.ENDED
        else "Open"
        if running
        else "Not started",
    )
