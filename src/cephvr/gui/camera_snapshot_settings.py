"""Collect restored camera drafts against accepted SDK-owned preset baselines."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from cephvr.acquisition.v1 import camera_pb2 as pb
from cephvr.control.v1 import types_pb2
from cephvr.gui.cameras import CamerasPanel


def collect_camera_snapshot(
    panel: CamerasPanel, settings: types_pb2.AcquisitionSettings
) -> None:
    if not panel.snapshot_draft:
        return
    baselines = {
        item.device.device_id: pb.CameraSessionSettings.FromString(
            item.SerializeToString()
        )
        for item in (settings.behavioral, settings.tracking)
        if item.device.device_id
    }
    for role, target, pulse in (
        ("Behavior cam", settings.behavioral, settings.pulses.behavioral),
        ("Tracking cam", settings.tracking, settings.pulses.tracking),
    ):
        draft = next((draft for draft in panel.drafts if draft.role == role), None)
        if draft is None:
            target.enabled = False
            target.device.device_id = ""
            continue
        if draft.serial in baselines:
            target.CopyFrom(baselines[draft.serial])
        else:
            target.device.ClearField("pfs_baseline")
            target.device.ClearField("pfs_source_filename")
        target.device.device_id, target.enabled = draft.serial, draft.enabled
        values = draft.values
        preset = values.get("preset", "").strip()
        if preset and (
            preset != target.device.pfs_source_filename
            or not target.device.HasField("pfs_baseline")
        ):
            raise ValueError(
                f"{role}: import the loaded PFS path through Cameras before submitting this GUI snapshot"
            )
        if not preset:
            target.device.ClearField("pfs_source_filename")
            target.device.ClearField("pfs_baseline")
        clock = values.get("trigger_clock", "")
        if clock == "External controller":
            source = values.get("trigger_source", "").strip()
            if not source and draft.enabled:
                raise ValueError(
                    f"{role}: select a PFS file with an explicit FrameStart line source"
                )
            target.device.frame_timing = pb.FRAME_TIMING_EXTERNAL_TRIGGER
            target.device.unaligned_free_running = False
            if source:
                target.device.settings.trigger_source = source
            else:
                target.device.settings.ClearField("trigger_source")
        elif clock == "Internal clock":
            target.device.frame_timing = pb.FRAME_TIMING_FREE_RUNNING
            target.device.unaligned_free_running = True
            target.device.settings.ClearField("trigger_source")
        elif draft.enabled:
            raise ValueError(
                f"{role}: select a camera trigger source before submitting"
            )
        else:
            target.device.ClearField("frame_timing")
        rate = values.get("trigger_frequency_hz", "").strip()
        if rate:
            try:
                frequency = Decimal(rate)
            except InvalidOperation as error:
                raise ValueError(f"{role}: trigger rate must be a number") from error
            if (
                not frequency.is_finite()
                or frequency <= 0
                or frequency % Decimal("0.1")
            ):
                raise ValueError(
                    f"{role}: trigger rate must use a positive 0.1 Hz grid"
                )
            pulse.requested_frequency_hz = float(frequency)
        else:
            pulse.ClearField("requested_frequency_hz")
