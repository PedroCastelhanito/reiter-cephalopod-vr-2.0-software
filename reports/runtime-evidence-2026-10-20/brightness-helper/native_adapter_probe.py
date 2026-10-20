"""Real owned Windows children; simulated supervisor and SDK JSON, no USB access."""

import json
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows import projector_brightness as brightness
from cephvr.platform.windows.file_sync import WindowsFileSyncOwner
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.platform.windows.python_runtime import resolve_python_executable
from cephvr.shared.auth import Principal
from cephvr.shared.native_helper_identity import PROJECTOR_BRIGHTNESS_ROLE
from cephvr.shared.supervised_encoder import SupervisedEncoderLauncher


class SimulatedSupervisor:
    def __init__(self, operation):
        self.native = WindowsJobs()
        self.operation = operation
        self.state = None
        self.events = []

    def PlanLaunch(self, request, **kwargs):
        assert request.child.role == PROJECTOR_BRIGHTNESS_ROLE
        assert request.parent_operation == self.operation
        assert request.work.WhichOneof("work") is None
        assert request.stop_method == "owner_job_terminate"
        assert not request.python_worker
        assert kwargs["timeout"] > 0
        job = f"cephvr-brightness-probe-{uuid4()}"
        self.native.create_launch_job(job)
        self.state = wire.LaunchState(
            plan=request,
            phase=wire.LAUNCH_PHASE_PLANNED,
            containment_job_name=job,
        )
        self.events.append({"phase": "planned", "job": job})
        return self.receipt(request.command_id)

    def ConfirmLaunch(self, request, **kwargs):
        assert request.owner == self.state.plan.owner
        assert request.child == self.state.plan.child
        assert request.launch_command_id == self.state.plan.command_id
        assert kwargs["timeout"] > 0
        if request.native_cleanup_complete:
            assert request.pid == self.state.pid
            assert request.creation_time_100ns == self.state.creation_time_100ns
            assert not self.native.process_running(request.pid, request.creation_time_100ns)
            assert not self.native.inspect_launch_job(self.state.containment_job_name)
            self.state.phase = wire.LAUNCH_PHASE_RELEASED
            self.events.append({"phase": "released", "process_absent": True, "job_empty": True})
        else:
            assert any(
                member[:2] == (request.pid, request.creation_time_100ns)
                for member in self.native.inspect_launch_job(self.state.containment_job_name)
            )
            if self.state.phase == wire.LAUNCH_PHASE_PLANNED:
                self.native.retain_exact(request.pid, request.creation_time_100ns, self.state.plan.executable)
                self.state.pid = request.pid
                self.state.creation_time_100ns = request.creation_time_100ns
                self.state.phase = wire.LAUNCH_PHASE_OS_CONFIRMED
                self.events.append({"phase": "os_confirmed", "pid": request.pid, "creation_time_100ns": request.creation_time_100ns})
            else:
                assert self.state.phase == wire.LAUNCH_PHASE_OS_CONFIRMED
                self.state.phase = wire.LAUNCH_PHASE_OPERATIONAL
                self.events.append({"phase": "operational"})
        return self.receipt(request.command_id)

    def GetLaunchState(self, request, **kwargs):
        assert request.requester == self.state.plan.owner
        assert request.launch_command_id == self.state.plan.command_id
        return self.state

    def receipt(self, command_id):
        return wire.LaunchReceipt(
            admission=pb.CommandAdmission(command_id=command_id, result=pb.COMMAND_RESULT_ACCEPTED),
            state=self.state,
        )

    def close(self):
        if self.state is None:
            return
        job = self.state.containment_job_name
        if self.native.inspect_launch_job(job):
            self.native.terminate_job(job)
        if self.state.HasField("pid"):
            assert self.native.wait_process_exit(self.state.pid, self.state.creation_time_100ns, 5000)
            self.native.release_process(self.state.pid, self.state.creation_time_100ns)
        assert not self.native.inspect_launch_job(job)
        self.native.close_launch_job(job)


class ObservedWindowsJobs(WindowsJobs):
    def launch_suspended(self, *args, **kwargs):
        assert kwargs["no_window"] is True
        return super().launch_suspended(*args, **kwargs)


def run_case(case):
    operation = pb.OperationContext(command_id=str(uuid4()))
    supervisor = SimulatedSupervisor(operation)
    owner = Principal("controller", str(uuid4()), "fake-validation-token")
    launcher = SupervisedEncoderLauncher(
        supervisor=supervisor,
        owner=owner,
        owner_identity=pb.ProcessIdentity(role=owner.role, generation=owner.generation),
        windows_jobs=ObservedWindowsJobs(),
        file_sync_owner=WindowsFileSyncOwner(),
        allowed_roles=frozenset((PROJECTOR_BRIGHTNESS_ROLE,)),
        probe_roles=frozenset((PROJECTOR_BRIGHTNESS_ROLE,)),
        stop_method="owner_job_terminate",
    )
    adapter = brightness.WindowsProjectorBrightness(launcher)
    result = {
        "schema_version": 1, "requested_ma": 200, "discovered_interfaces": 1,
        "interfaces": [{"index": 0, "name": "SIMULATED SDK INTERFACE", "id": "fixture-only",
                        "readback_ma": {"red": 200, "green": 200, "blue": 200},
                        "clamped": False, "confirmed": True, "release_confirmed": True, "error": ""}],
        "success": True,
    }
    executable = resolve_python_executable(Path(sys.executable))
    script = (
        "import json,os,sys; _dll_dir=os.add_dll_directory(os.path.join(sys.base_prefix,'Library','bin')); import ctypes; print('console_handle='+str(ctypes.windll.kernel32.GetConsoleWindow()), flush=True); print('benign helper: no SDK or USB access', flush=True); "
        + (f"print({brightness.RESULT_PREFIX!r}+{json.dumps(result)!r}, flush=True)" if case == "success" else "import time; time.sleep(30)")
    )
    original = brightness.brightness_command
    brightness.brightness_command = lambda current: [str(executable), "-c", script]
    timer = threading.Timer(0.35, adapter.cancel) if case == "cancel" else None
    duration = 3 if case == "timeout" else 10
    deadline = time.perf_counter_ns() + duration * 1_000_000_000
    started = time.perf_counter()
    error = None
    try:
        if timer is not None:
            timer.start()
        try:
            adapter.adjust(200, operation, deadline_ns=deadline)
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            print(json.dumps({"case": case, "observed_error": error, "diagnostics": adapter.diagnostics}), flush=True)
        assert adapter.cleanup_complete
        assert supervisor.state is not None, error
        assert supervisor.state.phase == wire.LAUNCH_PHASE_RELEASED
        assert "console_handle=0" in adapter.diagnostics
        assert time.perf_counter_ns() <= deadline
        if case == "success":
            assert error is None and adapter.result == result
        elif case == "cancel":
            assert error and error["type"] == "RuntimeError" and "cancelled" in error["message"]
            assert adapter.result is None
        else:
            assert error and error["type"] == "TimeoutError"
            assert adapter.result is None
        return {"case": case, "passed": True, "elapsed_s": time.perf_counter() - started,
                "original_budget_s": duration, "cleanup_complete": adapter.cleanup_complete,
                "create_no_window_requested": True, "child_console_handle": 0,
                "result": adapter.result, "diagnostics": adapter.diagnostics,
                "expected_error": error, "events": supervisor.events}
    finally:
        if timer is not None:
            timer.cancel()
            timer.join(1)
        brightness.brightness_command = original
        try:
            adapter.close(deadline_ns=deadline)
        finally:
            supervisor.close()


if __name__ == "__main__":
    output = Path(__file__).with_name("native-adapter-final-results.json")
    document = {"scope": "real Windows child/jobs/pipes and production brightness adapter; simulated supervisor receipts and SDK JSON; no hardware",
                "cases": [run_case(case) for case in ("success", "cancel", "timeout")]}
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document, indent=2))
