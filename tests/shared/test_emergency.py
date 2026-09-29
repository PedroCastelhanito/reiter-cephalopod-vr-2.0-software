"""E04 independent emergency evidence never guesses external stop state."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.emergency import write_emergency_report


@pytest.mark.asyncio
async def test_explicit_stop_uncertainty_and_byte_bound(tmp_path: Path) -> None:
    supervisor = pb.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    controller = pb.ProcessIdentity(role="controller", generation=str(uuid4()))
    path = await write_emergency_report(
        tmp_path,
        cause="CONTROLLER_LOST",
        supervisor=supervisor,
        controller=controller,
        work=None,
        errors=[],
        spikeglx_stop_unconfirmed=False,
    )
    document = json.loads(path.read_text())
    assert document["spikeglx_stop_unconfirmed"] is False
    assert document["cause"] == "CONTROLLER_LOST"
    with pytest.raises(ValueError, match="byte bound"):
        await write_emergency_report(
            tmp_path,
            cause="FAULT",
            supervisor=supervisor,
            controller=controller,
            work=None,
            errors=[],
            spikeglx_stop_unconfirmed=True,
            max_bytes=1,
        )


@pytest.mark.asyncio
async def test_slow_disk_does_not_hold_event_loop_or_default_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cephvr.shared.emergency as emergency

    supervisor = pb.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    controller = pb.ProcessIdentity(role="controller", generation=str(uuid4()))
    entered = threading.Event()
    release = threading.Event()
    original_fsync = emergency.os.fsync

    def blocked_fsync(fd: int) -> None:
        entered.set()
        assert release.wait(3)
        original_fsync(fd)

    monkeypatch.setattr(emergency.os, "fsync", blocked_fsync)
    try:
        with pytest.raises(TimeoutError):
            await write_emergency_report(
                tmp_path,
                cause="FAULT",
                supervisor=supervisor,
                controller=controller,
                work=None,
                errors=[],
                spikeglx_stop_unconfirmed=True,
                timeout_ns=50_000_000,
            )
        assert entered.wait(1)
        await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
    finally:
        release.set()
