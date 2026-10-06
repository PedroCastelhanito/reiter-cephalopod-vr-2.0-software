"""Prepared transport admission, method binding and original deadline pinning."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import grpc
import pytest

from cephvr.acquisition.transport.admission import CommandAdmissionTransport
from cephvr.acquisition.transport.grpc_ports import GrpcSupervisorPort
from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.auth import Principal
from cephvr.shared.clock import host_time_ns
from cephvr.shared.commands import CommandLedger


def test_worker_plan_transmits_the_protected_child_credential(monkeypatch) -> None:
    from cephvr.acquisition.transport import grpc_ports

    stub = Mock()
    stub.PlanLaunch = AsyncMock(return_value=wire.LaunchReceipt())
    monkeypatch.setattr(grpc_ports.control_rpc, "SupervisorServiceStub", lambda _: stub)
    principal = Principal("acquisition", _id(), "owner-token")
    port = GrpcSupervisorPort(Mock(), principal)
    deadline = _deadline()
    asyncio.run(
        port.plan_launch(
            wire.PlanLaunchRequest(), deadline_ns=deadline, child_token="child-token"
        )
    )
    metadata = stub.PlanLaunch.call_args.kwargs["metadata"]
    assert ("x-cephvr-child-token", "child-token") in metadata
    assert all(item in metadata for item in principal.metadata())
    assert stub.PlanLaunch.call_args.kwargs["timeout"] > 0


def test_worker_plan_transport_rejection_reaches_the_command_owner(monkeypatch) -> None:
    from cephvr.acquisition.transport import grpc_ports

    stub = Mock()
    stub.PlanLaunch = AsyncMock(
        side_effect=grpc.aio.AioRpcError(
            grpc.StatusCode.FAILED_PRECONDITION, (), (), "work context differs", ""
        )
    )
    monkeypatch.setattr(grpc_ports.control_rpc, "SupervisorServiceStub", lambda _: stub)
    port = GrpcSupervisorPort(Mock(), Principal("acquisition", _id(), "owner-token"))
    with pytest.raises(RuntimeError, match="FAILED_PRECONDITION: work context differs"):
        asyncio.run(
            port.plan_launch(
                wire.PlanLaunchRequest(),
                deadline_ns=_deadline(),
                child_token="child-token",
            )
        )


def _id() -> str:
    return str(uuid4())


def _deadline(offset_ns: int = 10_000_000_000) -> int:
    return host_time_ns() + offset_ns


def _transport() -> CommandAdmissionTransport:
    return CommandAdmissionTransport(
        CommandLedger(
            _id(),
            300_000_000_000,
            max_records=16,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        )
    )


def test_retry_reuses_one_admission_and_original_deadline() -> None:
    async def run() -> None:
        transport = _transport()
        request = wire.BackendCommand(
            command_id=_id(),
            issuer=control.ProcessIdentity(role="controller", generation=_id()),
            target=control.BackendContext(
                backend_name="acquisition", backend_generation=_id()
            ),
        )
        calls: list[int] = []

        async def handler(*, deadline_ns: int) -> control.CommandAdmission:
            calls.append(deadline_ns)
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command_id,
            )

        deadline = _deadline()
        first = await transport.dispatch("Cleanup", request, request, deadline, handler)
        retry = await transport.dispatch(
            "Cleanup", request, request, deadline + 500, handler
        )
        assert first == retry
        await asyncio.sleep(0)
        assert calls == [deadline]

    asyncio.run(run())


def test_rpc_method_is_part_of_canonical_command_identity() -> None:
    async def run() -> None:
        transport = _transport()
        request = wire.BackendCommand(
            command_id=_id(),
            issuer=control.ProcessIdentity(role="controller", generation=_id()),
            target=control.BackendContext(
                backend_name="acquisition", backend_generation=_id()
            ),
        )

        async def handler(*, deadline_ns: int) -> control.CommandAdmission:
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command_id,
            )

        deadline = _deadline(1_000_000)
        accepted = await transport.dispatch(
            "Cleanup", request, request, deadline, handler
        )
        conflict = await transport.dispatch(
            "Shutdown", request, request, deadline, handler
        )
        assert accepted.result == control.COMMAND_RESULT_ACCEPTED
        assert conflict.result == control.COMMAND_RESULT_REJECTED
        assert conflict.failure.code == "COMMAND_ADMISSION"

    asyncio.run(run())


def test_concurrent_replay_gets_short_admission_for_one_owned_operation() -> None:
    async def run() -> None:
        transport = _transport()
        request = wire.BackendCommand(
            command_id=_id(),
            issuer=control.ProcessIdentity(role="controller", generation=_id()),
            target=control.BackendContext(
                backend_name="acquisition", backend_generation=_id()
            ),
        )
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def handler(*, deadline_ns: int) -> control.CommandAdmission:
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command_id,
            )

        first_task = asyncio.create_task(
            transport.dispatch("Cleanup", request, request, _deadline(), handler)
        )
        await started.wait()
        retry_task = asyncio.create_task(
            transport.dispatch("Cleanup", request, request, _deadline(), handler)
        )
        await asyncio.sleep(0)
        release.set()
        first, retry = await asyncio.gather(first_task, retry_task)
        assert first == retry
        assert calls == 1

    asyncio.run(run())


def test_late_executor_failure_preserves_admission_and_retains_terminal_operation() -> (
    None
):
    async def run() -> None:
        ledger = CommandLedger(
            _id(),
            300_000_000_000,
            max_records=16,
            max_bytes=1_000_000,
            result_reservation_bytes=4096,
        )
        terminal_reported = asyncio.Event()

        async def terminal_failure(*_args: object) -> None:
            terminal_reported.set()

        transport = CommandAdmissionTransport(ledger, terminal_failure=terminal_failure)
        request = wire.BackendCommand(
            command_id=_id(),
            issuer=control.ProcessIdentity(role="controller", generation=_id()),
            target=control.BackendContext(
                backend_name="acquisition", backend_generation=_id()
            ),
        )
        started = asyncio.Event()
        release = asyncio.Event()

        async def handler(*, deadline_ns: int) -> control.CommandAdmission:
            started.set()
            await release.wait()
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_REJECTED,
                command_id=request.command_id,
                failure=control.Failure(code="LATE_FAILURE", message="retained"),
            )

        deadline = _deadline()
        first = await transport.dispatch("Cleanup", request, request, deadline, handler)
        await started.wait()
        replay_while_running = await transport.dispatch(
            "Cleanup", request, request, deadline + 900, handler
        )
        assert replay_while_running == first
        release.set()
        await asyncio.wait_for(terminal_reported.wait(), 1)
        replay_after_failure = await transport.dispatch(
            "Cleanup", request, request, deadline + 2_000, handler
        )
        retained = ledger.get(request.command_id)
        assert replay_after_failure == first
        assert retained is not None and retained.executor_result is not None
        terminal = control.OperationState.FromString(retained.executor_result)
        assert terminal.complete and not terminal.succeeded
        assert terminal.failure.code == "LATE_FAILURE"
        await transport.close(host_time_ns() + 1_000_000_000)

    asyncio.run(run())


def test_expired_new_command_is_rejected_but_expired_retry_replays_receipt() -> None:
    async def run() -> None:
        transport = _transport()
        request = wire.BackendCommand(
            command_id=_id(),
            issuer=control.ProcessIdentity(role="controller", generation=_id()),
            target=control.BackendContext(
                backend_name="acquisition", backend_generation=_id()
            ),
        )
        calls = 0

        async def handler(*, deadline_ns: int) -> control.CommandAdmission:
            nonlocal calls
            calls += 1
            return control.CommandAdmission(
                result=control.COMMAND_RESULT_ACCEPTED,
                command_id=request.command_id,
            )

        expired = host_time_ns() - 1
        rejected = await transport.dispatch(
            "Cleanup", request, request, expired, handler
        )
        assert rejected.result == control.COMMAND_RESULT_REJECTED
        assert calls == 0
        retained_request = wire.BackendCommand(
            command_id=_id(),
            issuer=request.issuer,
            target=request.target,
        )
        deadline = _deadline()
        accepted = await transport.dispatch(
            "Cleanup", retained_request, retained_request, deadline, handler
        )
        await asyncio.sleep(0.002)
        replay = await transport.dispatch(
            "Cleanup", retained_request, retained_request, host_time_ns() - 1, handler
        )
        assert accepted == replay
        await asyncio.sleep(0)
        assert calls == 1

    asyncio.run(run())
