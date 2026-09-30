"""Controller application assembly and owned resource lifetime."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import grpc

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import services_pb2_grpc as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.authority import (
    AuthorityControl,
    managed_jobs_from_bootstrap,
)
from cephvr.controller.backend import (
    GrpcBackendPort,
    GrpcSupervisorPort,
)
from cephvr.controller.configuration import (
    controller_validators,
    load_controller_configuration,
)
from cephvr.controller.planning import (
    plan_outputs,
)
from cephvr.controller.recovery import StartupRecovery
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.service import (
    start_controller_server,
)
from cephvr.controller.startup.bootstrap import _backend_descriptors, _bootstrap_value
from cephvr.controller.startup.monitor import authority_loop
from cephvr.controller.startup.providers import (
    _installed_display_validator,
    _installed_file_policies,
    _installed_spikeglx,
    _installed_validators,
    _writer_schema,
)
from cephvr.controller.startup.recovery import prepare_recovery
from cephvr.controller.state import Attempt, ControllerLimits
from cephvr.controller.transport.auth import credential_store_authentication
from cephvr.platform.windows.bootstrap import run_pipe_io_daemon
from cephvr.platform.windows.jobs import WindowsJobs
from cephvr.shared.auth import Principal
from cephvr.shared.clock import describe_host_clock
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.shared.identity import require_uuid4
from cephvr.shared.recovery import RecoveryStore, UnfinishedSessionPointer


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

        recovery_task = asyncio.create_task(
            prepare_recovery(
                startup_recovery,
                stub,
                principal,
                supervisor_generation,
                runtime.install_startup_recovery,
            )
        )
        try:
            await authority_loop(
                AuthorityControl(
                    generation=runtime.generation,
                    supervisor_generation=runtime.supervisor_generation,
                    status=runtime.authority_status,
                    lose=runtime.authority_loss,
                    warn=runtime.record_warning,
                    clock=runtime.clock,
                    limits=runtime.limit_state,
                ),
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
        await runtime.cancel_background_tasks()
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
