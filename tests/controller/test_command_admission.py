"""Command scope, replay ownership and bounded RPC ingress."""

from __future__ import annotations

import asyncio
import time
import uuid
from types import SimpleNamespace
from typing import Literal, cast

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.operations import ControlOperations
from cephvr.controller.state import (
    Attempt,
    ConfigurationState,
    ControlState,
    LifecycleState,
    Watch,
)
from cephvr.controller.transport.admission import CommandAdmissionGate, CommandWorkView
from cephvr.controller.transport.ingress import BoundedReportIngress, ReportSink
from tests.controller.support_components import _id


class _Work:
    def __init__(self) -> None:
        self.generation = _id()
        self.now = 1_000
        self.key: str | None = _id()
        self.retired = False

    def clock(self) -> int:
        return self.now

    def current_work_key(self) -> str | None:
        return self.key

    def command_work_complete(self, key: str) -> bool:
        return False

    def clean_work_retired(self) -> bool:
        return self.retired


def _request(command_id: str) -> svc.OperatorCommand:
    command = svc.OperatorCommand()
    command.operator.command_id = command_id
    return command


def _gate(work: _Work, retention_ns: int = 100) -> CommandAdmissionGate:
    return CommandAdmissionGate(
        work,
        max_pending_events=16,
        max_pending_payload_bytes=1_000_000,
        command_retention_ns=retention_ns,
    )


def _action(reject: bool, command_id: str):
    async def run() -> pb.CommandAdmission:
        if reject:
            return pb.CommandAdmission(
                result=pb.COMMAND_RESULT_REJECTED,
                command_id=command_id,
                failure=pb.Failure(code="REJECTED", message="no"),
            )
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=command_id
        )

    return run


async def test_rejected_abort_then_accepted_abort_same_session() -> None:
    work = _Work()
    gate = _gate(work)
    try:
        first, second = _id(), _id()
        rejected = await gate.admit(
            "AbortNow", first, _request(first), _action(True, first)
        )
        assert rejected.result == pb.COMMAND_RESULT_REJECTED
        accepted = await gate.admit(
            "AbortNow", second, _request(second), _action(False, second)
        )
        assert accepted.result == pb.COMMAND_RESULT_ACCEPTED
    finally:
        await gate.aclose()


async def test_rejected_stop_after_trial_then_start_session_accepted() -> None:
    work = _Work()
    gate = _gate(work)
    try:
        stop, start = _id(), _id()
        rejected = await gate.admit(
            "StopAfterTrial", stop, _request(stop), _action(True, stop)
        )
        assert rejected.result == pb.COMMAND_RESULT_REJECTED
        accepted = await gate.admit(
            "StartSession", start, _request(start), _action(False, start)
        )
        assert accepted.result == pb.COMMAND_RESULT_ACCEPTED
    finally:
        await gate.aclose()


async def test_same_id_retry_returns_retained_rejection_and_prunes_later() -> None:
    work = _Work()
    gate = _gate(work)
    try:
        command_id = _id()
        request = _request(command_id)
        first = await gate.admit(
            "StopAfterTrial", command_id, request, _action(True, command_id)
        )
        calls = 0

        async def other() -> pb.CommandAdmission:
            nonlocal calls
            calls += 1
            return pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED)

        retry = await gate.admit("StopAfterTrial", command_id, request, other)
        assert retry == first
        assert calls == 0
        work.now += 101 + 1
        gate.retention_ledger.prune(work.now)
        assert gate.retention_ledger.get(command_id) is None
    finally:
        await gate.aclose()


async def test_failed_execution_does_not_finalize_session_scope() -> None:
    work = _Work()
    gate = _gate(work)
    try:
        boom, ok = _id(), _id()

        async def fail() -> pb.CommandAdmission:
            raise RuntimeError("boom")

        failed = await gate.admit("StartSession", boom, _request(boom), fail)
        assert failed.failure.code == "INTERNAL"
        accepted = await gate.admit(
            "StartSession", ok, _request(ok), _action(False, ok)
        )
        assert accepted.result == pb.COMMAND_RESULT_ACCEPTED
    finally:
        await gate.aclose()


def _ops() -> tuple[ControlOperations, pb.SessionContext, str]:
    generation, client, watch, lease = _id(), _id(), _id(), _id()
    session = pb.SessionContext(controller_generation=generation, session_id=_id())
    lifecycle = LifecycleState()
    lifecycle.attempt = Attempt.__new__(Attempt)
    lifecycle.attempt.context = session
    lifecycle.trial = pb.TrialState(
        phase=pb.TRIAL_PHASE_PENDING,
        context=pb.TrialContext(session=session, trial_id=_id(), trial_number=2),
    )
    control = ControlState()
    control.owner = (client, watch, lease)
    control.watches[(client, watch)] = Watch.__new__(Watch)
    ops = ControlOperations(
        lifecycle=lifecycle,
        configuration=ConfigurationState(
            pb.ExperimentConfiguration(), pb.ControlPolicies()
        ),
        control=control,
        generation=generation,
        max_operation_records=16,
        clock=lambda: 0,
    )
    return ops, session, client


def _command(ops: ControlOperations, client: str) -> svc.OperatorCommand:
    command = svc.OperatorCommand(controller_generation=ops.generation)
    command.operator.client_id = client
    command.operator.control_generation = ops.control.owner[2]  # type: ignore[index]
    return command


def _auth(
    ops: ControlOperations,
    command: svc.OperatorCommand,
    safety: Literal["ordinary", "abort", "shutdown"] = "ordinary",
    targets: bool = True,
) -> str:
    return ops.authorized(command, safety=safety, targets_work=targets)


def test_missing_expected_work_rejected_for_work_commands() -> None:
    ops, _, client = _ops()
    command = _command(ops, client)
    assert _auth(ops, command) == "expected work is required"
    assert _auth(ops, command, "abort") == "expected work is required"
    assert _auth(ops, command, "shutdown") == "expected work is required"
    assert _auth(ops, command, targets=False) == ""


def test_matching_session_and_trial_accepted() -> None:
    ops, session, client = _ops()
    command = _command(ops, client)
    command.expected_work.session.CopyFrom(session)
    assert _auth(ops, command) == ""
    command = _command(ops, client)
    command.expected_work.trial.CopyFrom(ops.lifecycle.trial.context)
    assert _auth(ops, command) == ""


def test_stale_trial_or_wrong_session_rejected_for_ordinary() -> None:
    ops, session, client = _ops()
    command = _command(ops, client)
    command.expected_work.trial.CopyFrom(ops.lifecycle.trial.context)
    command.expected_work.trial.trial_number = 1
    assert _auth(ops, command) == "work identity mismatch"
    command = _command(ops, client)
    command.expected_work.trial.CopyFrom(ops.lifecycle.trial.context)
    command.expected_work.trial.trial_id = _id()
    assert _auth(ops, command) == "work identity mismatch"
    command = _command(ops, client)
    command.expected_work.session.session_id = _id()
    assert _auth(ops, command) == "work identity mismatch"


def test_safety_commands_accept_stale_trial_of_same_session_only() -> None:
    ops, session, client = _ops()
    for safety in ("abort", "shutdown"):
        command = _command(ops, client)
        command.expected_work.trial.session.CopyFrom(session)
        command.expected_work.trial.trial_id = _id()
        command.expected_work.trial.trial_number = 1
        assert _auth(ops, command, safety) == ""  # type: ignore[arg-type]
        other = _command(ops, client)
        other.expected_work.trial.session.session_id = _id()
        other.expected_work.trial.trial_id = _id()
        assert _auth(ops, other, safety) == "work identity mismatch"  # type: ignore[arg-type]


def test_no_attempt_needs_no_expected_work() -> None:
    ops, _, client = _ops()
    ops.lifecycle.attempt = None
    assert _auth(ops, _command(ops, client)) == ""


async def test_cancelled_caller_does_not_cancel_owned_command_or_duplicate_it() -> None:
    command_id = str(uuid.uuid4())
    work = cast(
        CommandWorkView,
        SimpleNamespace(
            generation=str(uuid.uuid4()),
            clock=time.monotonic_ns,
            current_work_key=lambda: None,
            command_work_complete=lambda _key: False,
            clean_work_retired=lambda: True,
        ),
    )
    gate = CommandAdmissionGate(
        work,
        max_pending_events=8,
        max_pending_payload_bytes=8192,
        command_retention_ns=300_000_000_000,
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
            gate.admit("AcquireControl", command_id, request, action)
        )
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        duplicate = asyncio.create_task(
            gate.admit("AcquireControl", command_id, request, action)
        )
        release.set()
        result = await duplicate
        assert result.result == pb.COMMAND_RESULT_ACCEPTED
        assert calls == 1
        replay = await gate.admit("AcquireControl", command_id, request, action)
        assert replay == result
        assert calls == 1
    finally:
        await gate.aclose()


async def test_interruption_precedes_queued_report_and_keeps_observed_time() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    seen: list[tuple[str, int]] = []

    async def lifecycle(
        _report: pb.LifecycleReport, ingress_ns: int
    ) -> pb.ReportReceipt:
        seen.append(("lifecycle", ingress_ns))
        if len(seen) == 1:
            started.set()
            await release.wait()
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    async def interruption(_report: svc.InterruptionReport) -> pb.ReportReceipt:
        seen.append(("interruption", 0))
        return pb.ReportReceipt(result=pb.COMMAND_RESULT_ACCEPTED)

    sink = cast(
        ReportSink,
        SimpleNamespace(
            report_lifecycle=lifecycle,
            report_interruption=interruption,
            ingress_exhausted=lambda _reason: None,
        ),
    )
    ingress = BoundedReportIngress(
        sink,
        max_pending_events=4,
        max_pending_payload_bytes=8192,
        max_message_bytes=1024,
    )
    try:
        first = asyncio.create_task(
            ingress.enqueue("lifecycle", pb.LifecycleReport(), 101)
        )
        await started.wait()
        second = asyncio.create_task(
            ingress.enqueue("lifecycle", pb.LifecycleReport(), 102)
        )
        urgent = asyncio.create_task(
            ingress.enqueue("interruption", svc.InterruptionReport(), 103)
        )
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(first, second, urgent)
        assert all(result.result == pb.COMMAND_RESULT_ACCEPTED for result in results)
        assert seen == [("lifecycle", 101), ("interruption", 0), ("lifecycle", 102)]
    finally:
        await ingress.aclose()


async def test_safety_command_has_bounded_reserved_admission_when_ordinary_ledger_is_full() -> (
    None
):
    work = cast(
        CommandWorkView,
        SimpleNamespace(
            generation=str(uuid.uuid4()),
            clock=time.monotonic_ns,
            current_work_key=lambda: None,
            command_work_complete=lambda _key: False,
            clean_work_retired=lambda: True,
        ),
    )
    gate = CommandAdmissionGate(
        work,
        max_pending_events=2,
        max_pending_payload_bytes=16_384,
        command_retention_ns=300_000_000_000,
    )

    async def admit(command_id: str) -> pb.CommandAdmission:
        return pb.CommandAdmission(
            result=pb.COMMAND_RESULT_ACCEPTED, command_id=command_id
        )

    try:
        ordinary_id = str(uuid.uuid4())
        ordinary = svc.OperatorCommand()
        ordinary.operator.command_id = ordinary_id
        accepted = await gate.admit(
            "AcquireControl", ordinary_id, ordinary, lambda: admit(ordinary_id)
        )
        assert accepted.result == pb.COMMAND_RESULT_ACCEPTED

        second_id = str(uuid.uuid4())
        second = svc.OperatorCommand()
        second.operator.command_id = second_id
        assert (
            await gate.admit(
                "AcquireControl", second_id, second, lambda: admit(second_id)
            )
        ).result == pb.COMMAND_RESULT_ACCEPTED

        extra_id = str(uuid.uuid4())
        extra = svc.OperatorCommand()
        extra.operator.command_id = extra_id
        rejected = await gate.admit(
            "AcquireControl", extra_id, extra, lambda: admit(extra_id)
        )
        assert rejected.result == pb.COMMAND_RESULT_REJECTED

        abort_id = str(uuid.uuid4())
        abort = svc.OperatorCommand()
        abort.operator.command_id = abort_id
        safety = await gate.admit("AbortNow", abort_id, abort, lambda: admit(abort_id))
        assert safety.result == pb.COMMAND_RESULT_ACCEPTED
    finally:
        await gate.aclose()
