"""E08 command admission remains owned after an RPC caller disconnects."""

from __future__ import annotations

import asyncio
import time
import uuid
from types import SimpleNamespace
from typing import cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.service import ExperimentControllerService


@pytest.mark.asyncio
async def test_cancelled_caller_does_not_cancel_owned_command_or_duplicate_it() -> None:
    command_id = str(uuid.uuid4())
    runtime = cast(
        ControllerRuntime,
        SimpleNamespace(
            generation=str(uuid.uuid4()),
            clock=time.monotonic_ns,
            attempt=None,
            session=pb.SessionState(
                phase=pb.SESSION_PHASE_CONFIGURATION, cleanup_confirmed=True
            ),
            _operations={},
        ),
    )
    service = ExperimentControllerService(
        runtime,
        client_authentication=lambda *_: asyncio.sleep(0),
        peer_tokens={},
        max_pending_events=8,
        max_pending_payload_bytes=8192,
        max_message_bytes=1024,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def action() -> pb.CommandAdmission:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=command_id
        )

    request = svc.OperatorCommand()
    request.operator.command_id = command_id
    try:
        first = asyncio.create_task(
            service._command("AcquireControl", command_id, request, action)
        )
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        duplicate = asyncio.create_task(
            service._command("AcquireControl", command_id, request, action)
        )
        release.set()
        result = await duplicate
        assert result.result == pb.COMMAND_RESULT_ACCEPTED
        assert calls == 1
        replay = await service._command("AcquireControl", command_id, request, action)
        assert replay == result
        assert calls == 1
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_safety_command_has_bounded_reserved_admission_when_ordinary_ledger_is_full() -> (
    None
):
    runtime = cast(
        ControllerRuntime,
        SimpleNamespace(
            generation=str(uuid.uuid4()),
            clock=time.monotonic_ns,
            attempt=None,
            session=pb.SessionState(
                phase=pb.SESSION_PHASE_CONFIGURATION, cleanup_confirmed=True
            ),
            _operations={},
        ),
    )
    service = ExperimentControllerService(
        runtime,
        client_authentication=lambda *_: asyncio.sleep(0),
        peer_tokens={},
        max_pending_events=2,
        max_pending_payload_bytes=16_384,
        max_message_bytes=1024,
    )

    async def admit(command_id: str) -> pb.CommandAdmission:
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=command_id
        )

    try:
        ordinary_id = str(uuid.uuid4())
        ordinary = svc.OperatorCommand()
        ordinary.operator.command_id = ordinary_id
        accepted = await service._command(
            "AcquireControl", ordinary_id, ordinary, lambda: admit(ordinary_id)
        )
        assert accepted.result == pb.COMMAND_RESULT_ACCEPTED

        second_id = str(uuid.uuid4())
        second = svc.OperatorCommand()
        second.operator.command_id = second_id
        assert (
            await service._command(
                "AcquireControl", second_id, second, lambda: admit(second_id)
            )
        ).result == pb.COMMAND_RESULT_ACCEPTED

        extra_id = str(uuid.uuid4())
        extra = svc.OperatorCommand()
        extra.operator.command_id = extra_id
        rejected = await service._command(
            "AcquireControl", extra_id, extra, lambda: admit(extra_id)
        )
        assert rejected.result == pb.COMMAND_RESULT_REJECTED

        abort_id = str(uuid.uuid4())
        abort = svc.OperatorCommand()
        abort.operator.command_id = abort_id
        safety = await service._command(
            "AbortNow", abort_id, abort, lambda: admit(abort_id)
        )
        assert safety.result == pb.COMMAND_RESULT_ACCEPTED
    finally:
        await service.aclose()
