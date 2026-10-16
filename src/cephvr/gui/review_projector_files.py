"""Review-only file extension; runtime rejects unreviewed multi-pulse documents."""

import copy
from contextlib import ExitStack

from PyQt6.QtCore import QSignalBlocker

from cephvr.gui.projector_files import ProjectorFiles
from cephvr.gui.review_timing import ReviewProjectorTiming, validate_drafts


class ReviewProjectorFiles(ProjectorFiles):
    def snapshot(self) -> dict[str, object]:
        result = super().snapshot()
        assert isinstance(self.timing, ReviewProjectorTiming)
        result["review_pulse_screens"] = copy.deepcopy(self.timing.drafts)
        return result

    def validate(self, payload: object) -> dict[str, object]:
        if isinstance(payload, dict) and "review_pulse_screens" in payload:
            validate_drafts(payload["review_pulse_screens"])
            payload = {k: v for k, v in payload.items() if k != "review_pulse_screens"}
        return super().validate(payload)

    def apply_snapshot(self, payload: object) -> None:
        self.validate(payload)
        drafts = None
        if isinstance(payload, dict) and "review_pulse_screens" in payload:
            drafts = payload["review_pulse_screens"]
            payload = {k: v for k, v in payload.items() if k != "review_pulse_screens"}
        assert isinstance(self.timing, ReviewProjectorTiming)
        with ExitStack() as stack:
            for widget in (
                self.timing.target,
                *self.timing.fields.values(),
                *self.timing.pulse_fields.values(),
            ):
                stack.enter_context(QSignalBlocker(widget))
            super().apply_snapshot(payload)
        self.timing.face = self.timing.panel.pulse_face()
        if drafts is not None:
            self.timing.restore_drafts(drafts)
        else:
            self.timing.drafts.clear()
            self.timing.edited()
