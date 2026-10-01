"""Bounded audit probes; backend/device preparation is never started."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.platform.windows.jobs import WindowsJobs, WindowsLaunchError
from tests.controller.support_components import TaskCapture, _id, _runtime, _RetainedPeer
from tests.controller.test_setup import _settings

SCRATCH = ROOT / ".audit-tmp" / "probes"
SCRATCH.mkdir(exist_ok=True)


async def setup_retention():
    backend = pb.BackendContext(backend_name="visual_stimulus", backend_generation=_id())
    runtime = _runtime(SCRATCH, backend)
    runtime.setup_admission.backends = {"visual_stimulus": _RetainedPeer(backend, svc.RetainedResult())}
    config = runtime.configuration_state.current
    config.mode = pb.SESSION_MODE_OPEN_LOOP
    config.experiment = "experiment"
    config.subject = "subject"
    config.backends.add(backend_name="visual_stimulus", enabled=True)
    config.trials.add(trial_number=1)
    runtime.supervisor_state.processes["visual_stimulus"] = svc.ProcessHealthStatus(process=pb.ProcessIdentity(role="visual_stimulus", generation=backend.backend_generation), process_running=True, connected=True)
    runtime.setup_admission.validators = {"structural": lambda _: pb.ValidationResult(completed=True, valid=True)}
    runtime.setup_admission.file_policy_loader = lambda _: {}
    runtime.setup_admission.startup_settings = _settings(runtime.limits)
    runtime.setup_admission.settings_loader = lambda: _settings(runtime.limits)
    runtime.control_operations.authorized = lambda _: ""
    async def prepared(attempt, command_id, deadline):
        await runtime.setup_execution._publish_ready(attempt, command_id)
    runtime.setup_execution.run_setup = prepared
    tasks = TaskCapture(runtime.setup_admission.spawn)
    runtime.setup_admission.spawn = tasks.spawn
    command = svc.OperatorCommand()
    command.operator.command_id = _id()
    admission = await runtime.setup(command)
    await tasks.drain()
    print("Setup admission:", str(admission))
    assert admission.result == pb.COMMAND_RESULT_ACCEPTED
    operation = runtime.control.operations[command.operator.command_id]
    assert operation.complete and operation.succeeded
    runtime.lifecycle.attempt = None
    runtime.lifecycle.session.cleanup_confirmed = True
    runtime.configuration_state.policies.command_retention_after_finalization_ns = 1
    runtime.control_operations.clock = lambda: 10**18
    runtime.control_operations.prune_operations()
    assert command.operator.command_id in runtime.control.operations
    assert command.operator.command_id not in runtime.control.operation_finished_ns
    print("Setup public admission + actual Ready transition: terminal timestamp absent; finalized operation survives pruning beyond retention. Preparation and authorization stubbed; no backend dispatched.")


def interpreter_identity():
    native = WindowsJobs()
    job = "cephvr-audit-" + uuid4().hex
    output = SCRATCH / "child.json"
    script = SCRATCH / "child.py"
    script.write_text("import json,os,sys,time\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({'pid':os.getpid(),'executable':sys.executable,'base':sys._base_executable}))\ntime.sleep(10)\n", encoding="utf8")
    native.create_launch_job(job)
    launched = None
    try:
        launched = native.launch_suspended(sys.executable, [str(script), str(output)], [job])
        native.resume(launched)
        import time
        deadline = time.monotonic() + 5
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(.025)
        reported = json.loads(output.read_text())
        members = native.inspect_launch_job(job)
        print("Interpreter launch:", json.dumps({"launched_pid": launched.pid, "configured_image": sys.executable, "code_process": reported, "job_members": members}))
        code_process = next(row for row in members if row[0] == reported["pid"])
        try:
            native.retain_exact(code_process[0], code_process[1], sys.executable)
        except WindowsLaunchError as exc:
            print("Configured-image retention for actual code process rejected:", str(exc))
        else:
            print("Configured-image retention accepted.")
    finally:
        native.terminate_job(job)
        native.close_launch_job(job)
        if launched:
            native.release_process(launched.pid, launched.creation_time_100ns)


def schema_encoding():
    sys.path.insert(0, str(ROOT / "contracts" / "tracking"))
    import schema_check
    mismatches = []
    for name, model in {**schema_check.METHODS, **schema_check.RECORDS}.items():
        path = ROOT / "contracts" / "tracking" / (name + ".schema.json")
        expected = json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
        utf8_equal = path.read_text(encoding="utf8") == expected
        if path.read_text() != expected:
            mismatches.append({"schema": name, "default_encoding_differs": True, "utf8_exact": utf8_equal})
    print("Schema encoding comparison:", json.dumps(mismatches))


schema_encoding()
asyncio.run(setup_retention())
interpreter_identity()
