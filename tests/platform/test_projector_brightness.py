"""Brightness SDK result and registered helper ownership without USB access."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows import projector_brightness as brightness
from cephvr.shared.auth import Principal

DEADLINE = 10_000_000_000


def result(current=101, *, failed=False, clamped=False):
    rgb = 1023 if clamped else current
    return {
        "schema_version": 1,
        "requested_ma": current,
        "discovered_interfaces": 1,
        "interfaces": [
            {
                "index": 0,
                "name": "TI",
                "id": "usb0",
                "readback_ma": dict.fromkeys(("red", "green", "blue"), rgb)
                if not failed
                else None,
                "clamped": clamped if not failed else None,
                "confirmed": not failed,
                "release_confirmed": True,
                "error": "readback failed" if failed else "",
            }
        ],
        "success": not failed,
    }


def encoded(value):
    return "readback diagnostic\n" + brightness.RESULT_PREFIX + json.dumps(value)


@pytest.mark.parametrize("current", [100, 2501])
def test_projector_sdk_rejects_invalid_current(current):
    with pytest.raises(ValueError, match="101 and 2500"):
        brightness.brightness_command(current)


@pytest.mark.parametrize(
    "failure", [None, "partial", "malformed", "timeout", "launch", "release"]
)
def test_projector_registered_helper_preserves_scope_deadline_and_cleanup(
    monkeypatch, failure
):
    journal = []
    operation = pb.OperationContext(command_id=str(uuid4()))
    owner = pb.ProcessIdentity(role="controller", generation=str(uuid4()))
    plan = wire.PlanLaunchRequest(
        command_id=str(uuid4()),
        owner=owner,
        child=pb.ProcessIdentity(
            role="controller_projector_brightness", generation=str(uuid4())
        ),
        executable="C:/Windows/benign.exe",
        parent_operation=operation,
        stop_method="owner_job_terminate",
    )
    output = (
        encoded(result(failed=failure == "partial"))
        if failure != "malformed"
        else "missing JSON"
    )

    class Process:
        launch_id = plan.command_id
        child = SimpleNamespace(pid=42, creation_time_100ns=142)
        job_name = "exact-job"
        cleanup_complete = False
        stdout_text = output
        diagnostic_tail = ()

        def close_stdin(self, *, deadline_ns):
            assert deadline_ns == DEADLINE
            journal.append("stdin")

        def wait(self, *, deadline_ns):
            assert deadline_ns == DEADLINE
            self.cleanup_complete = True
            journal.append("wait")
            return 1 if failure == "partial" else 0

    process = Process()
    state = wire.LaunchState(plan=plan, phase=wire.LAUNCH_PHASE_OPERATIONAL)
    if failure != "launch":
        state.pid, state.creation_time_100ns = 42, 142

    def get_state(request, **kwargs):
        assert request.launch_command_id == plan.command_id
        assert kwargs["timeout"] <= 10
        assert sum(k == "x-cephvr-deadline-ns" for k, _ in kwargs["metadata"]) == 1
        journal.append("query")
        return state

    def confirm(request, **kwargs):
        assert request.native_cleanup_complete
        assert request.owner == owner and request.child == plan.child
        assert (
            request.pid == state.pid
            and request.creation_time_100ns == state.creation_time_100ns
        )
        assert kwargs["timeout"] <= 10
        if failure == "release":
            raise RuntimeError("supervisor release unknown")
        journal.append("release")
        return wire.LaunchReceipt(
            admission=pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED),
            state=wire.LaunchState(plan=plan, phase=wire.LAUNCH_PHASE_RELEASED),
        )

    launcher = SimpleNamespace(
        owner_identity=owner,
        owner=Principal(owner.role, owner.generation, "test-token"),
        supervisor=SimpleNamespace(GetLaunchState=get_state, ConfirmLaunch=confirm),
        pending_plans=(),
        clock_ns=lambda: 0,
        bind_operation=lambda work, parent: journal.append(
            (work.WhichOneof("work"), parent.command_id)
        ),
        windows_jobs=SimpleNamespace(
            process_running=lambda *args: failure == "timeout",
            terminate_job=lambda name: journal.append(("terminate", name)),
        ),
        terminate_unconfirmed=lambda **kw: journal.append("partial cleanup"),
    )

    def launch(argv, *, deadline_ns, role, capture_stdout):
        assert deadline_ns == DEADLINE and role == plan.child.role and capture_stdout
        launcher.registered_plan(plan)
        if failure == "launch":
            launcher.pending_plans = (plan,)
            raise RuntimeError("creation unconfirmed")
        if failure == "timeout":
            launcher.clock_ns = lambda: DEADLINE - 1_000_000_000
        return process

    launcher.launch = launch
    monkeypatch.setattr(
        brightness, "brightness_command", lambda current: [plan.executable]
    )
    native = brightness.WindowsProjectorBrightness(launcher)
    if failure:
        with pytest.raises((RuntimeError, ValueError, TimeoutError)):
            native.adjust(101, operation, deadline_ns=DEADLINE)
    else:
        native.adjust(101, operation, deadline_ns=DEADLINE)
    assert journal[0] == (None, operation.command_id)
    if failure in {"release", "launch"}:
        assert not native.cleanup_complete
    else:
        assert native.cleanup_complete
    if failure == "partial":
        assert native.result == result(failed=True)
    if failure == "timeout":
        assert ("terminate", "exact-job") in journal
    if failure == "release":
        with pytest.raises(RuntimeError, match="Previous"):
            native.adjust(101, operation, deadline_ns=DEADLINE)


def test_new_admission_cancellation_cannot_reuse_previous_readbacks():
    launcher = SimpleNamespace(pending_plans=())
    native = brightness.WindowsProjectorBrightness(launcher)
    native.result = result()
    native.diagnostics = "old success"
    native.reset_cancel()
    native.cancel()
    with pytest.raises(RuntimeError, match="cancelled before"):
        native.adjust(
            101, pb.OperationContext(command_id=str(uuid4())), deadline_ns=DEADLINE
        )
    assert native.result is None and native.diagnostics == ""
    assert native.cleanup_complete


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "count",
        "clamp",
        "contradiction",
        "rgb",
        "schema_bool",
        "request_float",
        "index_bool",
    ],
)
def test_projector_rejects_incomplete_or_contradictory_structured_readbacks(mutation):
    value = result(1500, clamped=True)
    output = encoded(value)
    if mutation == "missing":
        output = "SDK output without result"
    elif mutation == "duplicate":
        output += "\n" + encoded(value)
    else:
        if mutation == "count":
            value["discovered_interfaces"] = 2
        elif mutation == "clamp":
            value["interfaces"][0]["clamped"] = False
        elif mutation == "contradiction":
            value["success"] = False
        elif mutation == "rgb":
            value["interfaces"][0]["readback_ma"]["red"] = 1500
        elif mutation == "schema_bool":
            value["schema_version"] = True
        elif mutation == "request_float":
            value["requested_ma"] = 1500.0
        elif mutation == "index_bool":
            value["interfaces"][0]["index"] = False
        output = encoded(value)
    with pytest.raises(ValueError):
        brightness.brightness_result(output, 1500)


def test_projector_requested_current_differs_from_confirmed_clamp():
    value = result(1500, clamped=True)
    assert brightness.brightness_result(encoded(value), 1500) == value
