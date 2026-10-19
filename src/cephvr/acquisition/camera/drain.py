"""Resumable SDK result purge under one original terminal deadline (A10)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cephvr.acquisition.camera.types import GrabResult, PurgeEvidence


@dataclass(slots=True)
class PurgeProgress:
    count: int = 0
    last_counter: int | None = None


def drain_and_stop(
    camera: Any,
    *,
    deadline_ns: int,
    should_continue: Callable[[], bool],
    retrieve: Callable[[int], GrabResult | None],
    generation_stopped: bool,
    margin_confirmed: bool,
    clock: Callable[[], int],
    progress: PurgeProgress | None = None,
) -> PurgeEvidence | None:
    """None yields to control without flushing uncounted SDK buffers."""
    counts = progress if progress is not None else PurgeProgress()
    drained = False
    if generation_stopped:
        while clock() < deadline_ns:
            if not should_continue():
                if progress is not None:
                    return None
                break
            if int(camera.NumReadyBuffers.GetValue()) == 0:
                drained = True
                break
            result = retrieve(0)
            if result is None:
                break
            if result.camera_frame_counter is not None:
                counts.last_counter = result.camera_frame_counter
            result.release()
            counts.count += 1
    camera.StopGrabbing()
    stopped_in_time = clock() <= deadline_ns
    empty_after_stop = (
        not generation_stopped or int(camera.NumReadyBuffers.GetValue()) == 0
    )
    complete = (
        generation_stopped
        and margin_confirmed
        and drained
        and stopped_in_time
        and empty_after_stop
    )
    if complete:
        return PurgeEvidence(counts.count, counts.last_counter, True)
    logging.getLogger(__name__).warning(
        "Camera SDK purge incomplete: generation_stopped=%s margin_confirmed=%s "
        "queue_drained=%s stopped_in_time=%s retrieved_count=%s "
        "original_deadline_ns=%s observed_ns=%s",
        generation_stopped,
        margin_confirmed,
        drained,
        stopped_in_time,
        counts.count,
        deadline_ns,
        clock(),
    )
    return PurgeEvidence(None, counts.last_counter, False)
