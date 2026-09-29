"""Controller process entry point for the supervisor's inherited-pipe bootstrap."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import grpc
from google.protobuf.message import Message

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.authority import (
    ManagedJob,
    handle_authority_loss,
    managed_jobs_from_bootstrap,
    notify_launcher,
    shutdown_owned_jobs,
)
from cephvr.controller.backend import BackendRegistration, GrpcBackendPort
from cephvr.controller.configuration import (
    BackendValidator,
    SupervisorStartup,
    controller_validators,
    load_controller_configuration,
)
from cephvr.controller.planning import (
    WriterSchema,
    WriterSchemaKey,
    build_schema,
    plan_outputs,
)
from cephvr.controller.recovery import StartupRecovery
from cephvr.controller.runtime import (
    Attempt,
    ControllerLimits,
    ControllerRuntime,
    SpikeGLXPort,
)
from cephvr.controller.service import (
    credential_store_authentication,
    start_controller_server,
)
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.clock import describe_host_clock
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.shared.identity import require_uuid4
from cephvr.shared.recovery import RecoveryStore, UnfinishedSessionPointer


class GrpcSupervisorPort:
    def __init__(self, stub: rpc.SupervisorServiceStub, principal: Principal) -> None:
        self.stub = stub
        self.principal = principal

    async def register_context(
        self, request: svc.RegisterContextRequest
    ) -> svc.RegistrationReceipt:
        return cast(
            svc.RegistrationReceipt,
            await self.stub.RegisterContext(
                request, metadata=self.principal.metadata()
            ),
        )

    async def request_shutdown(
        self, request: svc.ApplicationShutdownRequest
    ) -> pb.CommandAdmission:
        return cast(
            pb.CommandAdmission,
            await self.stub.RequestApplicationShutdown(
                request, metadata=self.principal.metadata()
            ),
        )

    async def report_preview_consumer_state(
        self, request: svc.PreviewConsumerReport
    ) -> pb.ReportReceipt:
        return cast(
            pb.ReportReceipt,
            await self.stub.ReportPreviewConsumerState(
                request, metadata=self.principal.metadata()
            ),
        )


def _bootstrap_value(bootstrap: Mapping[str, object], key: str, kind: type) -> object:
    value = bootstrap.get(key)
    if type(value) is not kind:
        raise ValueError(f"bootstrap {key} has invalid type")
    return value


def _backend_descriptors(bootstrap: Mapping[str, object]) -> list[BackendRegistration]:
    raw = bootstrap.get("backends", [])
    if not isinstance(raw, list):
        raise ValueError("bootstrap backend registry is not a list")
    result: list[BackendRegistration] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "backend_name",
            "backend_generation",
            "endpoint",
            "token",
            "launch_confirmed",
        }:
            raise ValueError("bootstrap backend registry entry differs from schema")
        if item["launch_confirmed"] is not False or any(
            not isinstance(item[key], str)
            for key in ("backend_name", "backend_generation", "endpoint", "token")
        ):
            raise ValueError("backend bootstrap cannot claim launch completion")
        registration = BackendRegistration(
            item["backend_name"],
            item["backend_generation"],
            item["endpoint"],
            item["token"],
        )
        if registration.backend_name in seen:
            raise ValueError("duplicate backend bootstrap role")
        seen.add(registration.backend_name)
        result.append(registration)
    return result


def _installed_validators() -> dict[str, BackendValidator]:
    providers: dict[str, BackendValidator] = {}
    for name in ("acquisition", "vr", "tracking", "synchronization"):
        module_name = f"cephvr.{name}.configuration"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        validator = getattr(module, "validate_configuration", None)
        if not callable(validator):
            raise RuntimeError(f"{module_name} has no pure validate_configuration")
        providers[name] = validator
    return providers


def _installed_file_policies(
    software_root: Path, active_names: frozenset[str]
) -> dict[str, Message]:
    policies: dict[str, Message] = {}
    for name in ("acquisition", "vr", "tracking"):
        if name not in active_names:
            continue
        module_name = f"cephvr.{name}.configuration"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        loader = getattr(module, "load_file_policies", None)
        if loader is None:
            continue
        policy = loader(software_root)
        if not isinstance(policy, Message):
            raise RuntimeError(
                f"{module_name}.load_file_policies returned no Protobuf policy"
            )
        policies[name] = policy
    return policies


def _writer_schema(prepared: pb.PreparedSession) -> dict[str, object]:
    """Load only owning writers' pure schema definitions for enabled outputs."""
    definitions: dict[WriterSchemaKey, WriterSchema] = {}
    for name in sorted({output.backend.backend_name for output in prepared.outputs}):
        if name not in {"acquisition", "vr", "tracking"}:
            raise RuntimeError("prepared output has an unsupported writer owner")
        module_name = f"cephvr.{name}.recording_schema"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            raise RuntimeError(
                f"writer definitions unavailable: {module_name}"
            ) from exc
        provider = getattr(module, "get_writer_schemas", None)
        if not callable(provider):
            raise RuntimeError(f"{module_name} has no pure get_writer_schemas provider")
        supplied = provider()
        if not isinstance(supplied, Mapping):
            raise RuntimeError("writer schema provider must return a mapping")
        for key, value in supplied.items():
            if (
                not isinstance(key, tuple)
                or len(key) != 3
                or any(not isinstance(part, str) for part in key)
                or key[0] != name
                or not isinstance(value, WriterSchema)
            ):
                raise RuntimeError(
                    "writer schema provider returned foreign or invalid definitions"
                )
            definitions[cast(WriterSchemaKey, key)] = value
    return build_schema(prepared, definitions)


def _installed_spikeglx(software_root: Path, generation: str) -> SpikeGLXPort | None:
    """Bind the later synchronization stage's controller-owned remote client."""
    module_name = "cephvr.synchronization.client"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise
    factory = getattr(module, "create_controller_client", None)
    if not callable(factory):
        raise RuntimeError("synchronization client factory unavailable")
    client = factory(software_root=software_root, controller_generation=generation)
    if any(
        not callable(getattr(client, method, None))
        for method in (
            "prepare",
            "verify_before_start",
            "start_and_verify_writing",
            "stop_expected_run",
        )
    ):
        raise RuntimeError(
            "synchronization client does not implement the controller port"
        )
    return cast(SpikeGLXPort, client)


def _installed_display_validator() -> Callable[[str], frozenset[str]] | None:
    module_name = "cephvr.vr.configuration"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise
    provider = getattr(module, "validate_display_profile", None)
    if not callable(provider):
        raise RuntimeError("VR configuration module has no pure display validator")

    def validate(profile_json: str) -> frozenset[str]:
        outputs = provider(profile_json)
        if (
            not isinstance(outputs, frozenset)
            or not outputs
            or any(not isinstance(value, str) or not value for value in outputs)
        ):
            raise ValueError("VR display validator returned no exact output set")
        return outputs

    return validate


async def run_controller(bootstrap: Mapping[str, object]) -> None:
    software_root = Path(str(_bootstrap_value(bootstrap, "software_root", str)))
    controller_generation = require_uuid4(
        str(_bootstrap_value(bootstrap, "controller_generation", str))
    )
    supervisor_generation = require_uuid4(
        str(_bootstrap_value(bootstrap, "supervisor_generation", str))
    )
    controller_token = str(_bootstrap_value(bootstrap, "controller_token", str))
    supervisor_token = str(_bootstrap_value(bootstrap, "supervisor_token", str))
    supervisor_port = cast(int, _bootstrap_value(bootstrap, "supervisor_port", int))
    controller_port = cast(int, _bootstrap_value(bootstrap, "controller_port", int))
    launch_command_id = require_uuid4(
        str(_bootstrap_value(bootstrap, "launch_command_id", str))
    )
    pid = cast(int, _bootstrap_value(bootstrap, "pid", int))
    creation_time = cast(int, _bootstrap_value(bootstrap, "creation_time_100ns", int))
    supervisor_pid = cast(int, _bootstrap_value(bootstrap, "supervisor_pid", int))
    supervisor_creation = cast(
        int, _bootstrap_value(bootstrap, "supervisor_creation_time_100ns", int)
    )
    if (
        not controller_token
        or not supervisor_token
        or pid <= 0
        or creation_time <= 0
        or supervisor_pid <= 0
        or supervisor_creation <= 0
    ):
        raise ValueError("bootstrap identity or credential missing")
    settings = load_controller_configuration(software_root)
    if (
        settings.controller_port != controller_port
        or settings.supervisor_startup.port != supervisor_port
    ):
        raise ValueError("bootstrap ports disagree with the versioned configuration")
    principal = Principal("controller", controller_generation, controller_token)
    descriptors = _backend_descriptors(bootstrap)
    managed_jobs = managed_jobs_from_bootstrap(bootstrap.get("managed_jobs"))
    managed_generations = {job.role: job.generation for job in managed_jobs}
    if any(
        managed_generations.get(entry.backend_name) != entry.backend_generation
        for entry in descriptors
    ):
        raise ValueError("backend credentials and managed job generations disagree")
    if {entry.backend_name for entry in descriptors} != {
        "acquisition",
        "vr",
        "tracking",
    }:
        raise ValueError("bootstrap omits a required top-level backend identity")
    launcher_handle = cast(
        int, _bootstrap_value(bootstrap, "launcher_control_handle", int)
    )
    if launcher_handle <= 0:
        raise ValueError("controller launcher channel is missing")
    if sys.platform != "win32":
        raise RuntimeError("controller managed bootstrap requires Windows")
    import msvcrt

    launcher_descriptor = msvcrt.open_osfhandle(launcher_handle, os.O_WRONLY)
    native = WindowsJobs()
    native.retain_exact(supervisor_pid, supervisor_creation, sys.executable)
    for job in managed_jobs:
        native.open_launch_job(job.job_name)
    backend_ports = {
        entry.backend_name: GrpcBackendPort(
            entry, principal, max_message_bytes=settings.max_message_bytes
        )
        for entry in descriptors
    }
    store = CredentialStore(default_runtime_root(), controller_generation)
    channel = grpc.aio.insecure_channel(
        f"127.0.0.1:{supervisor_port}",
        options=(
            ("grpc.max_receive_message_length", settings.max_message_bytes),
            ("grpc.max_send_message_length", settings.max_message_bytes),
        ),
    )
    stub = rpc.SupervisorServiceStub(channel)  # type: ignore[no-untyped-call]
    recovery_store = await run_pipe_io_daemon(
        lambda: RecoveryStore(default_runtime_root()),
        timeout_s=settings.limits_kwargs["metadata_ns"] / 1e9,
    )
    startup_recovery = StartupRecovery(
        recovery_store,
        current_generation=controller_generation,
        timeout_ns=settings.limits_kwargs["metadata_ns"],
        max_operations=settings.limits_kwargs["max_metadata_operations"],
        max_bytes=settings.limits_kwargs["max_metadata_bytes"],
    )

    def pointer_for(attempt: Attempt) -> UnfinishedSessionPointer:
        return UnfinishedSessionPointer(
            session_directory=str(attempt.reservation.session_directory),
            session_id=attempt.context.session_id,
            controller_generation=controller_generation,
            supervisor_generation=supervisor_generation,
        )

    async def reservation_started(attempt: Attempt) -> None:
        await run_pipe_io_daemon(
            lambda: recovery_store.write_pointer(pointer_for(attempt)),
            timeout_s=settings.limits_kwargs["metadata_ns"] / 1e9,
        )

    async def reservation_released(attempt: Attempt) -> None:
        expected = pointer_for(attempt)

        def clear() -> None:
            # Cancellation before acquisition creates no recovery pointer.
            if recovery_store.read_pointer() is not None:
                recovery_store.clear_pointer(expected)

        await run_pipe_io_daemon(
            clear, timeout_s=settings.limits_kwargs["metadata_ns"] / 1e9
        )

    runtime = ControllerRuntime(
        generation=controller_generation,
        configuration=settings.configuration,
        policies=settings.policies,
        recording_root=Path(settings.configuration.recording_root)
        if settings.configuration.recording_root
        else software_root / ".unset-recording-root",
        configuration_history_path=software_root / "config/last_configuration.json",
        history_warning=settings.history_warning,
        limits=ControllerLimits(**settings.limits_kwargs),
        validators=controller_validators(_installed_validators()),
        display_validator=_installed_display_validator(),
        settings_loader=lambda: load_controller_configuration(software_root),
        startup_settings=settings,
        backends=backend_ports,
        supervisor=GrpcSupervisorPort(stub, principal),
        supervisor_generation=supervisor_generation,
        spikeglx=_installed_spikeglx(software_root, controller_generation),
        output_planner=plan_outputs,
        schema_factory=_writer_schema,
        file_policy_loader=lambda names: _installed_file_policies(software_root, names),
        max_preparation_bytes=settings.max_message_bytes,
        max_incident_bytes=min(
            settings.max_message_bytes // 4, settings.max_pending_payload_bytes // 4
        ),
        health_silence_ns=settings.supervisor_startup.silence_timeout_ns,
        max_operation_records=settings.max_pending_events,
        initial_startup_blocker="Checking the prior application's unfinished session",
        reservation_started=reservation_started,
        reservation_released=reservation_released,
    )
    server = await start_controller_server(
        runtime,
        port=controller_port,
        max_message_bytes=settings.max_message_bytes,
        client_authentication=credential_store_authentication(store),
        peer_tokens={"supervisor": (supervisor_generation, supervisor_token)}
        | {
            entry.backend_name: (entry.backend_generation, entry.token)
            for entry in descriptors
        },
        max_pending_events=settings.max_pending_events,
        max_pending_payload_bytes=settings.max_pending_payload_bytes,
        command_retention_ns=settings.policies.command_retention_after_finalization_ns,
    )
    try:
        clock = describe_host_clock()
        confirmation = svc.ConfirmLaunchRequest(
            command_id=str(uuid.uuid4()),
            launch_command_id=launch_command_id,
            owner=pb.ProcessIdentity(
                role="supervisor", generation=supervisor_generation
            ),
            child=pb.ProcessIdentity(
                role="controller", generation=controller_generation
            ),
            pid=pid,
            creation_time_100ns=creation_time,
            endpoint=f"127.0.0.1:{controller_port}",
            host_clock=pb.HostClockDescriptor(
                clock_id=clock.clock_id,
                implementation=clock.implementation,
                monotonic=clock.monotonic,
                adjustable=clock.adjustable,
                resolution_s=clock.resolution_s,
            ),
        )
        receipt = await asyncio.wait_for(
            stub.ConfirmLaunch(confirmation, metadata=principal.metadata()),
            settings.supervisor_startup.silence_timeout_ns / 1e9,
        )
        if (
            receipt.admission.result != pb.COMMAND_RESULT_ACCEPTED
            or receipt.state.phase != svc.LAUNCH_PHASE_OPERATIONAL
        ):
            raise RuntimeError("supervisor did not confirm operational endpoint")
        display = asyncio.create_task(runtime.initialize_display())

        async def prepare_recovery() -> None:
            async def query(prior_generation: str) -> svc.RecoverySnapshot:
                result = cast(
                    svc.RecoverySnapshot,
                    await stub.GetRecoveryState(
                        svc.RecoveryQuery(
                            expected_supervisor=pb.ProcessIdentity(
                                role="supervisor", generation=supervisor_generation
                            ),
                            prior_controller_generation=prior_generation,
                        ),
                        metadata=principal.metadata(),
                    ),
                )
                if result.supervisor != pb.ProcessIdentity(
                    role="supervisor", generation=supervisor_generation
                ):
                    raise RuntimeError(
                        "startup recovery response has a foreign supervisor"
                    )
                return result

            try:
                prompt = await startup_recovery.prepare(query)
            except Exception as exc:
                await runtime.install_startup_recovery(
                    prompt=None,
                    handler=None,
                    blocker=f"Startup recovery remains blocked: {exc}",
                )
            else:
                inspection = startup_recovery.inspection
                completion_warning = None
                if inspection is not None and inspection.spikeglx_stop_unconfirmed:
                    endpoint = (
                        f"{inspection.spikeglx_endpoint[0]}:{inspection.spikeglx_endpoint[1]}"
                        if inspection.spikeglx_endpoint is not None
                        else "unknown endpoint"
                    )
                    completion_warning = (
                        "Recovery preserved an unconfirmed SpikeGLX stop: "
                        f"{endpoint}, run {inspection.spikeglx_run or 'unknown'}. "
                        "Inspect the remote run before another paired session; local "
                        "recovery does not establish remote stopping or scientific file closure."
                    )
                await runtime.install_startup_recovery(
                    prompt=prompt,
                    handler=startup_recovery.recover if prompt is not None else None,
                    blocker=prompt.explanation if prompt is not None else None,
                    completion_warning=completion_warning,
                )

        recovery_task = asyncio.create_task(prepare_recovery())
        try:
            await _authority_loop(
                runtime,
                stub,
                principal,
                supervisor_pid,
                supervisor_creation,
                settings.supervisor_startup,
                native,
                managed_jobs,
                backend_ports,
                launcher_descriptor,
                software_root,
            )
        finally:
            display.cancel()
            recovery_task.cancel()
            await asyncio.gather(display, recovery_task, return_exceptions=True)
    finally:
        await server.stop(grace=0)
        # The original graceful deadline has ended. Prevent new work before
        # relinquishing recovery locks or the native shutdown authority.
        pending = tuple(runtime._tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        try:
            startup_recovery.close()
        except OSError as exc:
            print(f"Recovery lock release unconfirmed: {exc}", file=sys.stderr)
        await channel.close()
        for backend in backend_ports.values():
            await backend.close()
        os.close(launcher_descriptor)
        for job in managed_jobs:
            native.close_launch_job(job.job_name)
        for exact_pid, exact_creation in tuple(native.processes):
            native.release_process(exact_pid, exact_creation)


async def _authority_loop(
    runtime: ControllerRuntime,
    stub: rpc.SupervisorServiceStub,
    principal: Principal,
    supervisor_pid: int,
    supervisor_creation: int,
    startup: SupervisorStartup,
    native: WindowsJobs,
    managed_jobs: tuple[ManagedJob, ...],
    backends: Mapping[str, GrpcBackendPort],
    launcher_descriptor: int,
    software_root: Path,
) -> None:

    async def send_heartbeats() -> None:
        while True:
            await asyncio.sleep(startup.heartbeat_interval_ns / 1e9)
            heartbeat = pb.HeartbeatReport(
                source=pb.ProcessIdentity(
                    role="controller", generation=runtime.generation
                ),
                sent_monotonic_ns=runtime.clock(),
                session_phase=runtime.session.phase,
                health_summary="responsive",
            )
            if runtime.attempt is not None:
                heartbeat.work.session.CopyFrom(runtime.attempt.context)
            try:
                await asyncio.wait_for(
                    stub.ReportHeartbeat(heartbeat, metadata=principal.metadata()),
                    startup.heartbeat_interval_ns / 1e9,
                )
            except (TimeoutError, grpc.RpcError):
                pass

    sender = asyncio.create_task(send_heartbeats())
    launcher_attempted = False
    launcher_notified = False

    async def enforce_owned_exit(deadline: int) -> None:
        failures = await shutdown_owned_jobs(
            native,
            managed_jobs,
            absolute_deadline_ns=deadline,
            graceful_exit_ns=startup.graceful_exit_ns,
            terminate_exit_ns=startup.terminate_exit_ns,
        )
        for failure in failures:
            print(f"Shutdown remains unconfirmed: {failure}", file=sys.stderr)
        try:
            native.terminate_exact(supervisor_pid, supervisor_creation)
        except Exception as exc:
            print(f"Supervisor exit unconfirmed: {exc}", file=sys.stderr)

    try:
        while True:
            await asyncio.sleep(0.1)
            now = runtime.clock()
            if runtime._shutdown_intent_ns and not launcher_attempted:
                launcher_attempted = True
                deadline = runtime._shutdown_intent_ns + startup.application_backstop_ns
                try:
                    await notify_launcher(
                        launcher_descriptor,
                        supervisor_generation=runtime.supervisor_generation,
                        controller_generation=runtime.generation,
                        deadline_ns=deadline,
                        cause="OPERATOR_SHUTDOWN",
                        timeout_s=max(
                            0, min(startup.emergency_timeout_ns, deadline - now) / 1e9
                        ),
                    )
                    launcher_notified = True
                except Exception as exc:
                    async with runtime._lock:
                        runtime._warnings.append(
                            pb.Warning(
                                warning_id=str(uuid.uuid4()),
                                component="shutdown",
                                message=f"launcher handoff unconfirmed: {exc}",
                            )
                        )
                        runtime._publish()
                now = runtime.clock()
            try:
                alive = native.process_running(supervisor_pid, supervisor_creation)
                cause = "SUPERVISOR_LOST" if not alive else "SUPERVISOR_SILENT"
            except Exception:
                alive = False
                cause = "SUPERVISOR_IDENTITY_UNCONFIRMED"
            if (
                sender.done()
                or not alive
                or now - runtime._supervisor_last_seen_ns > startup.silence_timeout_ns
            ):
                await handle_authority_loss(
                    runtime,
                    cause=cause,
                    issued_ns=now,
                    startup=startup,
                    native=native,
                    jobs=managed_jobs,
                    backends=backends,
                    launcher_descriptor=launcher_descriptor,
                    software_root=str(software_root),
                    notify_backstop=not launcher_attempted,
                )
                if launcher_attempted and not launcher_notified:
                    deadline = (
                        runtime._shutdown_intent_ns + startup.application_backstop_ns
                    )
                    while runtime.clock() < deadline:
                        await asyncio.sleep(
                            max(0, min(0.1, (deadline - runtime.clock()) / 1e9))
                        )
                    await enforce_owned_exit(deadline)
                return
            if runtime._shutdown_intent_ns:
                deadline = runtime._shutdown_intent_ns + startup.application_backstop_ns
                handoff_complete = all(
                    op.complete
                    for op in runtime._operations.values()
                    if op.command == "ShutdownApplication"
                )
                if (
                    launcher_notified
                    and handoff_complete
                    and runtime.session.phase
                    in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_ENDED)
                    and runtime.session.cleanup_confirmed
                ):
                    return
                if now >= deadline:
                    if not launcher_notified:
                        # No fresh grace period follows an uncertain pipe handoff.
                        # The original bound has expired; use only retained owned
                        # jobs and the exact retained supervisor process handle.
                        await enforce_owned_exit(deadline)
                    return
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CephVR controller supervised process")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("supervised controller bootstrap requires Windows")
    from cephvr.platform.windows.bootstrap import read_bootstrap
    from cephvr.platform.windows.guard import SingleInstanceGuard

    with SingleInstanceGuard("controller"):
        bootstrap = read_bootstrap(args.bootstrap_handle)
        asyncio.run(run_controller(bootstrap))
    return 0
