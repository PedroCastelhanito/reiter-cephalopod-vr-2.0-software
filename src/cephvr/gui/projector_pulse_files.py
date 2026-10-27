"""Shared per-screen pulse files, retaining the original draft extension keys."""

import copy
from contextlib import ExitStack

from PyQt6.QtCore import QSignalBlocker

from cephvr.gui.projector_files import ProjectorFiles
from cephvr.gui.projector_pulses import (
    ProjectorPulses,
    profile_pulse_drafts,
    validate_drafts,
)


class ProjectorPulseFiles(ProjectorFiles):
    def snapshot(self) -> dict[str, object]:
        result = super().snapshot()
        assert isinstance(self.timing, ProjectorPulses)
        result["photodiode_mode"] = self.timing.pulse_mode
        result["review_pulse_screens"] = copy.deepcopy(self.timing.drafts)
        return result

    def validate(self, payload: object) -> dict[str, object]:
        if isinstance(payload, dict) and "photodiode_mode" in payload:
            if payload["photodiode_mode"] not in ("landmarks", "every_frame"):
                raise ValueError("Unsupported photodiode mode")
            payload = {k: v for k, v in payload.items() if k != "photodiode_mode"}
        if isinstance(payload, dict) and "review_pulse_screens" in payload:
            validate_drafts(payload["review_pulse_screens"])
            payload = {k: v for k, v in payload.items() if k != "review_pulse_screens"}
        return super().validate(payload)

    def apply_snapshot(self, payload: object) -> None:
        mode = (
            payload.get("photodiode_mode", "landmarks")
            if isinstance(payload, dict)
            else "landmarks"
        )
        if mode not in ("landmarks", "every_frame"):
            raise ValueError("Unsupported photodiode mode")
        if isinstance(payload, dict) and "settings" in payload:
            payload = {k: v for k, v in payload.items() if k != "photodiode_mode"}
        drafts = None
        if isinstance(payload, dict) and "outputs" in payload and "mappings" in payload:
            drafts = profile_pulse_drafts(
                payload,
                {m["output_id"]: m["surface_id"].title() for m in payload["mappings"]},
            )
        else:
            self.validate(payload)
        if isinstance(payload, dict) and "review_pulse_screens" in payload:
            drafts = payload["review_pulse_screens"]
            payload = {k: v for k, v in payload.items() if k != "review_pulse_screens"}
        assert isinstance(self.timing, ProjectorPulses)
        with ExitStack() as stack:
            for widget in (
                self.timing.target,
                *self.timing.fields.values(),
                *self.timing.pulse_fields.values(),
            ):
                stack.enter_context(QSignalBlocker(widget))
            super().apply_snapshot(payload)
            self.timing.set_pulse_mode(str(mode))
        if drafts is None and isinstance(payload, dict) and "settings" not in payload:
            return
        self.timing.face = self.timing.panel.pulse_face()
        if drafts is not None:
            self.timing.restore_drafts(drafts)
        else:
            self.timing.drafts.clear()
            self.timing.edited()
