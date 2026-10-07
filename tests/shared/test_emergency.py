"""Bounded emergency reports preserve failure evidence and ownership."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from cephvr.control.v1 import types_pb2 as types
from cephvr.shared.emergency import write_emergency_report


async def test_explicit_stop_uncertainty_and_byte_bound(tmp_path: Path) -> None:
    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    controller = types.ProcessIdentity(role="controller", generation=str(uuid4()))
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


async def test_slow_disk_does_not_hold_event_loop_or_default_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cephvr.shared.emergency as emergency

    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    controller = types.ProcessIdentity(role="controller", generation=str(uuid4()))
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


async def test_huge_failure_message_is_truncated_not_dropped(tmp_path: Path) -> None:
    supervisor = types.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    controller = types.ProcessIdentity(role="controller", generation=str(uuid4()))
    errors = [
        types.ErrorReport(
            error_id=str(uuid4()),
            source=types.ProcessIdentity(
                role="visual_stimulus", generation=str(uuid4())
            ),
            failure=types.Failure(code=f"CODE_{index}", message="x" * 2_000_000),
        )
        for index in range(3)
    ]
    path = await write_emergency_report(
        tmp_path,
        cause="CONTROLLER_LOST",
        supervisor=supervisor,
        controller=controller,
        work=types.WorkContext(session=types.SessionContext(session_id=str(uuid4()))),
        errors=errors,
        spikeglx_stop_unconfirmed=False,
    )
    assert path.stat().st_size <= 1_048_576
    document = json.loads(path.read_text())
    assert [item["code"] for item in document["errors"]] == [
        "CODE_0",
        "CODE_1",
        "CODE_2",
    ]
    assert all("[truncated " in item["message"] for item in document["errors"])
    assert document["work"]
