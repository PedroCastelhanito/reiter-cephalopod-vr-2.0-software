"""Asynchronous protected display preparation and GL-owner completion."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass

from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.rendering.types import DisplayInitialization
from cephvr.visual_stimulus.resources.calibration import PreparedCalibration
from cephvr.visual_stimulus.v1 import messages_pb2 as visual_stimulus
from cephvr.visual_stimulus.worker.ports import PreparationPort


@dataclass(slots=True)
class DisplayPreparationJob:
    request: visual_stimulus.InitializeDisplay
    display: DisplayProfile
    result: Future[tuple[DisplayProfile, PreparedCalibration]]
    completion: Future[None]
    deadline_ns: int
    thread: threading.Thread | None = None
    resource_key: str = "display:preparation"


def begin_display_preparation(
    request: visual_stimulus.InitializeDisplay,
    display: DisplayProfile,
    preparation: PreparationPort,
    announce: Callable[[str, str | None], None],
    deadline_ns: int,
) -> DisplayPreparationJob:
    result: Future[tuple[DisplayProfile, PreparedCalibration]] = Future()
    completion: Future[None] = Future()

    def prepare() -> None:
        try:
            result.set_result(
                preparation.prepare_display(request, announce, deadline_ns)
            )
        except BaseException as exc:
            result.set_exception(exc)

    job = DisplayPreparationJob(request, display, result, completion, deadline_ns)
    announce(job.resource_key, None)
    job.thread = threading.Thread(
        target=prepare, name="cephvr-visual-stimulus-display-preparation", daemon=True
    )
    job.thread.start()
    return job


def complete_display_preparation(
    job: DisplayPreparationJob,
    preparation: PreparationPort,
    *,
    now_ns: int,
    report: Callable[[DisplayProfile, DisplayInitialization], None],
) -> bool:
    """Finish CPU validation and issue Idle only from the calling GL owner."""
    if not job.result.done() or (job.thread is not None and job.thread.is_alive()):
        return False
    try:
        if now_ns >= job.deadline_ns:
            raise TimeoutError("display preparation missed its retained deadline")
        prepared_display, calibration = job.result.result()
        if prepared_display != job.display:
            raise ValueError("prepared display changed during protected loading")
        observation = preparation.initialize_display(job.display, calibration)
        report(job.display, observation)
        job.completion.set_result(None)
    except BaseException as exc:
        job.completion.set_exception(exc)
        raise
    return True
