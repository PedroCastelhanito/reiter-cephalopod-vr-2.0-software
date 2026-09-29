"""E04 independent, bounded emergency report for an authority survivor."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Sequence
from concurrent.futures import Future
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import host_time_ns


async def write_emergency_report(
    software_root: Path,
    *,
    cause: str,
    supervisor: pb.ProcessIdentity,
    controller: pb.ProcessIdentity,
    work: pb.WorkContext | None,
    errors: Sequence[pb.ErrorReport],
    spikeglx_stop_unconfirmed: bool,
    timeout_ns: int = 5_000_000_000,
    max_bytes: int = 1_048_576,
) -> Path:
    """Submit one bounded report without occupying the loop's shared executor.

    Timeout means the result is unconfirmed: the daemon may finish its already
    started OS write later. The caller never treats timeout as durable completion.
    """
    if timeout_ns <= 0 or max_bytes <= 0 or not cause:
        raise ValueError("emergency report requires positive bounds and cause")
    estimate = len(cause) + len(supervisor.generation) + len(controller.generation)
    if work is not None:
        estimate += 2 * work.ByteSize()
    for error in errors:
        estimate += 80 + sum(
            len(value)
            for value in (
                error.error_id,
                error.source.role,
                error.failure.code,
                error.failure.message,
            )
        )
        if estimate > max_bytes:
            raise ValueError("emergency report byte bound exceeded")
    started_ns = host_time_ns()
    deadline_ns = started_ns + timeout_ns
    report_dir = Path(software_root) / "reports"
    report_path = report_dir / f"emergency-{started_ns}-{uuid4()}.json"
    document = {
        "schema_version": 1,
        "cause": cause,
        "supervisor_generation": supervisor.generation,
        "controller_generation": controller.generation,
        "work": work.SerializeToString().hex() if work is not None else None,
        "errors": [
            {
                "id": error.error_id,
                "component": error.source.role,
                "code": error.failure.code,
                "message": error.failure.message,
            }
            for error in errors
        ],
        "spikeglx_stop_unconfirmed": spikeglx_stop_unconfirmed,
    }
    payload = (
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(payload) > max_bytes:
        raise ValueError("emergency report byte bound exceeded")
    completion: Future[Path] = Future()

    def write() -> None:
        try:
            report_dir.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(report_path, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            completion.set_result(report_path)
        except BaseException as exc:
            completion.set_exception(exc)

    threading.Thread(target=write, name="cephvr-emergency", daemon=True).start()
    remaining_s = max(0.0, (deadline_ns - host_time_ns()) / 1e9)
    return await asyncio.wait_for(
        asyncio.shield(asyncio.wrap_future(completion)), timeout=remaining_s
    )
