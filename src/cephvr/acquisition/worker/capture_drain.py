"""One terminal capture generation and fixed drain margin across control handoffs."""

from __future__ import annotations

import logging
from collections.abc import Callable

from cephvr.acquisition.camera.types import CameraAdapter, FrameTiming, PurgeEvidence
from cephvr.acquisition.worker.capture import CameraCaptureLoop


class TerminalCaptureDrain:
    def __init__(
        self,
        adapter: CameraAdapter,
        *,
        active: bool,
        admission_stop_ns: int,
        timing: FrameTiming | None,
        margin_ns: int,
        terminal_off_confirmed: bool,
        activity_stopped: Callable[[int], None] | None,
        clock: Callable[[], int],
    ) -> None:
        self.adapter = adapter
        self.timing = timing
        self.margin_ns = margin_ns
        self.terminal_off_confirmed = terminal_off_confirmed
        self.generation_stopped = adapter.begin_terminal_drain() if active else False
        if self.generation_stopped and terminal_off_confirmed and activity_stopped:
            activity_stopped(clock())
        margin_start = admission_stop_ns
        if timing == "external_trigger":
            if terminal_off_confirmed:
                margin_start = clock()
            else:
                self.generation_stopped = False
        self.margin_end_ns = margin_start + margin_ns
        self.active = active

    def advance(
        self,
        capture: CameraCaptureLoop | None,
        *,
        deadline_ns: int,
        handoff: Callable[[], bool],
        resumable: bool,
        clock: Callable[[], int],
    ) -> PurgeEvidence | None:
        complete = (
            self.active
            and self.generation_stopped
            and self.terminal_off_confirmed
            and self.margin_end_ns <= deadline_ns
        )
        interrupted = False

        def control() -> bool:
            nonlocal interrupted
            permitted = handoff()
            interrupted = not permitted
            return permitted

        if complete:
            while clock() < self.margin_end_ns:
                if capture is None:
                    complete = False
                    break
                capture.capture_once(control)
                if interrupted and resumable and clock() < deadline_ns:
                    return None
                if interrupted or clock() >= deadline_ns:
                    complete = False
                    break
            if complete and clock() >= self.margin_end_ns:
                self.adapter.confirm_drain_margin()
            else:
                complete = False
        if resumable:
            evidence = self.adapter.stop_capture(
                deadline_ns, should_continue_drain=handoff, resumable=True
            )
        else:
            evidence = self.adapter.stop_capture(
                deadline_ns, should_continue_drain=handoff
            )
        if evidence is not None and not evidence.accounting_complete:
            logging.getLogger(__name__).warning(
                "Camera terminal drain incomplete: timing=%s generation_stopped=%s "
                "terminal_off_confirmed=%s margin_ns=%s margin_completed=%s "
                "control_handoff_interrupted=%s original_deadline_ns=%s observed_ns=%s",
                self.timing,
                self.generation_stopped,
                self.terminal_off_confirmed,
                self.margin_ns,
                complete,
                interrupted,
                deadline_ns,
                clock(),
            )
        return evidence
