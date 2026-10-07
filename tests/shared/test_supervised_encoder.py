"""Contained launch, partial-attempt retention and exact cleanup of supervised helpers.

Fakes stand in for the supervisor, Windows jobs and pipes; this checks the ownership
state machine only, never native behaviour (E15).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as types
from cephvr.platform.windows.byte_stream_factory import PipeConstructionOwner
from cephvr.platform.windows.jobs import SuspendedProcess
from cephvr.shared import supervised_encoder
from cephvr.shared.auth import Principal
from cephvr.shared.encoder_errors import EncoderLaunchError
from cephvr.shared.supervised_encoder import (
    FFMPEG_PROBE_ROLE,
    SupervisedEncoderLauncher,
)

DEADLINE = 10**15
CHILD = SuspendedProcess(
    pid=7, creation_time_100ns=70, executable="x", process_handle=1, thread_handle=2
)


class FakeEndpoint:
    def __init__(self, journal: list[str], name: str) -> None:
        self.journal = journal
        self.name = name
        self.child_handle = 5
        self.parent = SimpleNamespace(handle=9)

    def close_child_copy(self) -> None:
        self.child_handle = 0
        self.journal.append(f"close_child:{self.name}")

    def close_parent(self) -> None:
        self.journal.append(f"close_parent:{self.name}")


class FakePipes:
    """Stands in for OverlappedPipe; fails on the Nth endpoint when asked."""

    def __init__(self, journal: list[str], fail_at: int | None = None) -> None:
        self.journal = journal
        self.fail_at = fail_at
        self.created = 0

    def create_child_endpoint(self, **_: Any) -> FakeEndpoint:
        self.created += 1
        if self.created == self.fail_at:
            raise OSError("pipe creation failed")
        return FakeEndpoint(self.journal, f"pipe{self.created}")


class FakeJobs:
    def __init__(self, journal: list[str]) -> None:
        self.journal = journal
        self.create_error: Exception | None = None
        self.job_members: list[tuple[int, int, str]] = []

    def open_launch_job(self, name: str) -> None:
        self.journal.append(f"open_job:{name}")

    def launch_suspended(self, *args: Any, **kwargs: Any) -> SuspendedProcess:
        if self.create_error is not None:
            raise self.create_error
        self.journal.append("launch_suspended")
        return CHILD

    def resume(self, process: SuspendedProcess) -> None:
        self.journal.append("resume")

    def terminate_exact(self, pid: int, created: int) -> None:
        self.journal.append("terminate_exact")

    def inspect_launch_job(self, name: str) -> list[tuple[int, int, str]]:
        return list(self.job_members)

    def release_process(self, pid: int, created: int) -> None:
        self.journal.append("release_process")

    def close_launch_job(self, name: str) -> None:
        self.journal.append(f"close_job:{name}")


class FakeSupervisor:
    JOB = "job-1"

    def __init__(self) -> None:
        self.plans: dict[str, wire.PlanLaunchRequest] = {}
        self.confirm_phases: list[int | None] = []  # None = rejected/raise
        self.confirm_no_child_ok = True

    def PlanLaunch(
        self, request: wire.PlanLaunchRequest, **_: Any
    ) -> wire.LaunchReceipt:
        self.plans[request.command_id] = request
        return wire.LaunchReceipt(
            admission=types.CommandAdmission(
                command_id=request.command_id, result=types.COMMAND_RESULT_ACCEPTED
            ),
            state=wire.LaunchState(
                plan=request,
                phase=wire.LAUNCH_PHASE_PLANNED,
                containment_job_name=self.JOB,
            ),
        )

    def ConfirmLaunch(
        self, request: wire.ConfirmLaunchRequest, **_: Any
    ) -> wire.LaunchReceipt:
        if request.creation_failed_without_child:
            if not self.confirm_no_child_ok:
                raise OSError("supervisor unreachable")
            return wire.LaunchReceipt(
                admission=types.CommandAdmission(
                    command_id=request.command_id,
                    result=types.COMMAND_RESULT_ACCEPTED,
                )
            )
        phase = self.confirm_phases.pop(0)
        if phase is None:
            raise OSError("supervisor unreachable")
        return wire.LaunchReceipt(
            admission=types.CommandAdmission(
                command_id=request.command_id, result=types.COMMAND_RESULT_ACCEPTED
            ),
            state=wire.LaunchState(
                phase=phase,
                pid=CHILD.pid,
                creation_time_100ns=CHILD.creation_time_100ns,
            ),
        )

    def GetLaunchState(self, query: wire.LaunchQuery, **_: Any) -> wire.LaunchState:
        return wire.LaunchState(
            plan=self.plans[query.launch_command_id],
            phase=wire.LAUNCH_PHASE_PLANNED,
            containment_job_name=self.JOB,
        )


class Harness:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.journal: list[str] = []
        self.supervisor = FakeSupervisor()
        self.jobs = FakeJobs(self.journal)
        self.pipes = FakePipes(self.journal)
        self.executable = str(tmp_path / "ffmpeg")
        monkeypatch.setattr(supervised_encoder, "OverlappedPipe", self.pipes_adapter())
        monkeypatch.setattr(
            PipeConstructionOwner, "retry_cleanup", lambda self, *, deadline_ns: None
        )
        monkeypatch.setattr(
            supervised_encoder,
            "_wait_process",
            lambda *args: self.journal.append("wait"),
        )
        owner = Principal("acquisition", str(uuid4()), "token")
        self.launcher = SupervisedEncoderLauncher(
            supervisor=self.supervisor,  # type: ignore[arg-type]
            owner=owner,
            owner_identity=types.ProcessIdentity(
                role=owner.role, generation=owner.generation
            ),
            windows_jobs=self.jobs,  # type: ignore[arg-type]
            file_sync_owner=SimpleNamespace(),  # type: ignore[arg-type]
            process_factory=lambda **kwargs: SimpleNamespace(
                start_readers=lambda: self.journal.append("start_readers")
            ),  # type: ignore[arg-type,return-value]
            clock_ns=lambda: 0,
        )
        self.launcher.bind_operation(
            types.WorkContext(), types.OperationContext(command_id=str(uuid4()))
        )

    def pipes_adapter(self) -> Any:
        pipes = self.pipes
        return SimpleNamespace(create_child_endpoint=pipes.create_child_endpoint)

    def launch(self) -> Any:
        return self.launcher.launch(
            [self.executable, "-version"],
            deadline_ns=DEADLINE,
            role=FFMPEG_PROBE_ROLE,
        )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


def test_successful_launch_resumes_only_after_both_confirmations(
    harness: Harness,
) -> None:
    harness.supervisor.confirm_phases = [
        wire.LAUNCH_PHASE_OS_CONFIRMED,
        wire.LAUNCH_PHASE_OPERATIONAL,
    ]
    harness.launch()
    journal = harness.journal
    assert journal.index("launch_suspended") < journal.index("resume")
    assert journal.index("resume") < journal.index("start_readers")
    assert not harness.launcher.pending_plans
    assert harness.supervisor.confirm_phases == []


def test_pipe_creation_failing_midway_closes_what_was_created(
    harness: Harness,
) -> None:
    harness.pipes.fail_at = 2
    with pytest.raises(OSError, match="pipe creation failed"):
        harness.launch()
    assert "close_parent:pipe1" in harness.journal
    assert "launch_suspended" not in harness.journal
    assert not harness.launcher.pending_plans


def test_creation_failure_with_confirmed_no_child_releases_the_attempt(
    harness: Harness,
) -> None:
    harness.jobs.create_error = OSError("CreateProcess failed")
    with pytest.raises(EncoderLaunchError, match="creation failed"):
        harness.launch()
    assert f"close_job:{FakeSupervisor.JOB}" in harness.journal
    assert not harness.launcher._partial
    assert not harness.launcher.pending_plans


def test_creation_failure_without_supervisor_confirmation_keeps_the_obligation(
    harness: Harness,
) -> None:
    harness.jobs.create_error = OSError("CreateProcess failed")
    harness.supervisor.confirm_no_child_ok = False
    with pytest.raises(EncoderLaunchError):
        harness.launch()
    assert len(harness.launcher.pending_plans) == 1
    assert f"close_job:{FakeSupervisor.JOB}" not in harness.journal
    # Once the supervisor is reachable, bounded cleanup confirms no child and releases.
    harness.supervisor.confirm_no_child_ok = True
    harness.launcher.terminate_unconfirmed(deadline_ns=DEADLINE)
    assert not harness.launcher._partial
    assert f"close_job:{FakeSupervisor.JOB}" in harness.journal


def test_unconfirmed_os_identity_retains_the_child_and_never_resumes(
    harness: Harness,
) -> None:
    harness.supervisor.confirm_phases = [None]
    with pytest.raises(EncoderLaunchError, match="OS confirmation"):
        harness.launch()
    assert "resume" not in harness.journal
    assert len(harness.launcher._partial) == 1


def test_terminate_unconfirmed_ends_the_exact_child_and_releases_everything(
    harness: Harness,
) -> None:
    harness.supervisor.confirm_phases = [None]
    with pytest.raises(EncoderLaunchError):
        harness.launch()
    harness.launcher.terminate_unconfirmed(deadline_ns=DEADLINE)
    journal = harness.journal
    assert journal.index("terminate_exact") < journal.index("release_process")
    assert journal.index("release_process") < journal.index(
        f"close_job:{FakeSupervisor.JOB}"
    )
    assert not harness.launcher._partial


def test_descendants_left_in_the_job_keep_the_attempt_as_a_blocker(
    harness: Harness,
) -> None:
    harness.supervisor.confirm_phases = [None]
    with pytest.raises(EncoderLaunchError):
        harness.launch()
    harness.jobs.job_members = [(99, 990, "descendant")]
    with pytest.raises(EncoderLaunchError, match="descendants remain"):
        harness.launcher.terminate_unconfirmed(deadline_ns=DEADLINE)
    assert len(harness.launcher._partial) == 1
    assert "release_process" not in harness.journal
    assert f"close_job:{FakeSupervisor.JOB}" not in harness.journal
