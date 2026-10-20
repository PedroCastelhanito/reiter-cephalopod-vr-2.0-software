"""Actual Start and durable writer with fake authority, SDK and lifecycle peers."""

import asyncio
import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cephvr.control.v1 import services_pb2 as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.planning import build_schema
from cephvr.controller.metadata.documents import projector_brightness_schema
from cephvr.tracking.recording_schema import get_writer_schemas
from tests.controller.support_components import _attempt, _runtime, drain_runtime_tasks

EVIDENCE = Path(__file__).resolve().parent
RUN = f"m-{uuid4().hex[:8]}"


class SimulatedSdk:
    cleanup_complete = True
    diagnostics = "SIMULATED SDK ONLY; no projector or USB operation"

    def __init__(self):
        self.result = None
        self.fail = False
        self.clamp = False
        self.partial = False

    def reset_cancel(self):
        pass

    def cancel(self):
        pass

    def adjust(self, current_ma, operation, *, deadline_ns):
        actual = 1023 if self.clamp else current_ma
        self.result = {
            "schema_version": 1, "requested_ma": current_ma,
            "discovered_interfaces": 1,
            "interfaces": [{"index": 0, "name": "SIMULATED SDK INTERFACE", "id": "fixture-only",
                            "readback_ma": {"red": actual, "green": actual, "blue": actual} if not self.fail else None,
                            "clamped": self.clamp if not self.fail else None,
                            "confirmed": not self.fail, "release_confirmed": True,
                            "error": "fixture partial SDK failure" if self.fail else ""}],
            "success": not self.fail,
        }
        if self.partial:
            self.result["interfaces"].append({"index": 1, "name": "SIMULATED FAILED INTERFACE", "id": "fixture-failed", "readback_ma": None, "clamped": None, "confirmed": False, "release_confirmed": True, "error": "fixture readback unavailable"})
            self.result["discovered_interfaces"] = 2
            self.result["success"] = False
            raise RuntimeError("fixture partial SDK failure")
        if self.fail:
            raise RuntimeError("fixture partial SDK failure")


class SimulatedSupervisor:
    async def register_context(self, request):
        return wire.RegistrationReceipt(
            admission=pb.CommandAdmission(result=pb.COMMAND_RESULT_ACCEPTED),
            registered=request.context,
        )


async def scenario(name):
    root = EVIDENCE / RUN / name
    root.mkdir(parents=True, exist_ok=False)
    backend = pb.BackendContext(backend_name="tracking", backend_generation=str(uuid4()))
    runtime = _runtime(root, backend)
    runtime.configuration_state.revision = 1
    runtime.lifecycle.session.phase = pb.SESSION_PHASE_CONFIGURATION
    sdk = SimulatedSdk()
    runtime.projector_brightness.native = sdk
    runtime.projector_brightness.hooks = replace(runtime.projector_brightness.hooks, authorized=lambda *_a, **_kw: "")
    admitted = []
    sdk.clamp = name == "clamped"
    sdk.partial = name == "partial"
    if name != "unknown":
        for failed in ([False, True] if name == "latest-failed" else [False]):
            sdk.fail = failed
            command_id = str(uuid4())
            request = wire.ProjectorBrightnessRequest(
                command=wire.OperatorCommand(operator=pb.OperatorContext(command_id=command_id)),
                expected_configuration_revision=1,
                current_ma=1500 if sdk.clamp else (250 if failed else 200),
            )
            receipt = await runtime.projector_brightness.execute(request)
            assert receipt.result == pb.COMMAND_RESULT_ACCEPTED
            admitted.append(command_id)
            await drain_runtime_tasks(runtime)
        prior = deepcopy(runtime.device_state.projector_brightness)
        rejected = await runtime.projector_brightness.execute(wire.ProjectorBrightnessRequest(
            command=wire.OperatorCommand(operator=pb.OperatorContext(command_id=str(uuid4()))),
            expected_configuration_revision=999, current_ma=500))
        assert rejected.result == pb.COMMAND_RESULT_REJECTED
        assert runtime.device_state.projector_brightness == prior
    snapshot = deepcopy(runtime.device_state.projector_brightness)
    attempt = _attempt(runtime, root, {})
    assert attempt.reservation.acquire() == []
    attempt.prepared.configuration.CopyFrom(pb.ExperimentConfiguration(
        experiment="NON_SCIENTIFIC_METADATA_FIXTURE", subject="FAKE_IDENTITY_NO_HARDWARE"))
    attempt.prepared.anchor_wall_time = datetime.now(UTC).isoformat()
    attempt.prepared.local_timezone = "UTC"
    trial = attempt.prepared.trials.add(context=pb.TrialContext(session=attempt.context, trial_id=str(uuid4()), trial_number=1))
    attempt.prepared.outputs.add(output_key=f"{trial.context.trial_id}:tracking:tracking", backend=backend,
                                 trial=trial.context, output_tag="tracking", extension="jsonl")
    runtime.lifecycle.attempt = attempt
    runtime.lifecycle.session.CopyFrom(pb.SessionState(context=attempt.context, phase=pb.SESSION_PHASE_STARTING))
    command_id = str(uuid4())
    runtime.control.operations[command_id] = pb.OperationState(context=pb.OperationContext(command_id=command_id), command="StartSession")
    runtime.start.schema_factory = lambda prepared: build_schema(prepared, get_writer_schemas())
    runtime.start.supervisor = SimulatedSupervisor()

    async def no_trials(_attempt):
        assert _attempt is attempt

    async def unexpected_interrupt(_attempt, reason):
        raise AssertionError(f"fixture Start failed: {reason}")

    runtime.start.trials = SimpleNamespace(run_trials=no_trials)
    runtime.start.interruption = SimpleNamespace(interrupt=unexpected_interrupt)
    persist = runtime.metadata.persist

    async def mutate_after_document_capture(owner_attempt, filename, action, document):
        if filename == "SESSION_CONFIG.json" and snapshot is not None:
            assert document["projector_brightness"] == snapshot
            runtime.device_state.projector_brightness["requested_ma"] = 999
            runtime.device_state.projector_brightness["sdk_result"]["interfaces"][0]["name"] = "MUTATED AFTER START SNAPSHOT"
            assert document["projector_brightness"] == snapshot
        return await persist(owner_attempt, filename, action, document)

    runtime.metadata.persist = mutate_after_document_capture
    try:
        await runtime.start.run_start(attempt, command_id)
        await drain_runtime_tasks(runtime)
        assert runtime.control.operations[command_id].succeeded
        assert attempt.activated
        attempt.trial_index = 0
        attempt.trial_log_name = "FAKE_SUBJECT_120000_LOG.json"
        await runtime.trial_logs.start_trial_log(attempt, trial)
        config_path = attempt.reservation.protocol_directory / "SESSION_CONFIG.json"
        schema_path = attempt.reservation.protocol_directory / "SCHEMA.json"
        config_bytes = config_path.read_bytes()
        document = json.loads(config_bytes)
        schema = json.loads(schema_path.read_bytes())
        evidence = document["projector_brightness"]
        if name == "unknown":
            assert evidence == {"schema_version": 1, "outcome": "unknown", "reason": "no adjustment observed in this controller lifetime"}
        else:
            assert evidence == snapshot
            assert evidence["controller_generation"] == runtime.generation
            assert evidence["command_id"] == admitted[-1]
            assert evidence["requested_ma"] == (1500 if name == "clamped" else (250 if name == "latest-failed" else 200))
            assert evidence["outcome"] == ("failed" if name in ("latest-failed", "partial") else "succeeded")
            assert evidence["native_cleanup_confirmed"] is True
            assert evidence["sdk_result"]["interfaces"][0]["name"] == "SIMULATED SDK INTERFACE"
        assert document["session_id"] == attempt.context.session_id
        assert document["configuration"]["subject"] == "FAKE_IDENTITY_NO_HARDWARE"
        expected_schema = build_schema(attempt.prepared, get_writer_schemas())
        expected_schema["controller_metadata"] = {"SESSION_CONFIG.json.projector_brightness": projector_brightness_schema()}
        assert schema == expected_schema
        trial_path = attempt.reservation.protocol_directory / attempt.trial_log_name
        trial_document = json.loads(trial_path.read_bytes())
        assert trial_document["session_config"] == "SESSION_CONFIG.json"
        assert trial_document["session_id"] == document["session_id"]
        assert (trial_path.parent / trial_document["session_config"]).resolve() == config_path.resolve()
        runtime.device_state.projector_brightness = {"outcome": "a later action cannot rewrite this session"}
        assert config_path.read_bytes() == config_bytes
        assert attempt.writer.seal(3)
        attempt.reservation.release()
        paths = [config_path, schema_path, trial_path, attempt.reservation.protocol_directory / "SESSION_LOG.jsonl"]
        return {"case": name, "passed": True, "fake_controller_generation": runtime.generation,
                "fake_session_id": attempt.context.session_id, "admitted_commands": admitted,
                "snapshot_independent_of_live_state": True,
                "files": [{"path": str(path.relative_to(EVIDENCE)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]}
    finally:
        if attempt.writer is not None:
            attempt.writer.seal(3)
        if attempt.reservation.held:
            attempt.reservation.release()


async def main():
    return {"scope": "actual brightness admission/Start/run_start/MetadataCoordinator/MetadataWriter and Windows durable file publication; fake authority, supervisor, SDK, backend identities and no trial execution",
            "cases": [await scenario(name) for name in ("unknown", "succeeded", "latest-failed", "clamped", "partial")]}


if __name__ == "__main__":
    document = asyncio.run(main())
    (EVIDENCE / "metadata-output-results.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document, indent=2))
