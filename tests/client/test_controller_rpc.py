"""Real loopback controller RPC checks; no simulated scientific backends."""

from __future__ import annotations

import asyncio
import json
import shutil
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from uuid import uuid4

import grpc
import pytest
import pytest_asyncio

from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import services_pb2_grpc as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import (
    _load_saved_configuration,
    load_controller_configuration,
)
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.service import ExperimentControllerService
from cephvr.controller.state import ControllerLimits
from cephvr.shared.auth import (
    AuthenticationError,
    Principal,
    require_authenticated_peer,
)
from cephvr.shared.credentials import CredentialStore
from cephvr.synchronization.diagnostic import SpikeGLXDiagnostic
from cephvr.synchronization.v1 import spikeglx_pb2 as sync_pb


@pytest_asyncio.fixture
async def controller(
    tmp_path: Path,
) -> AsyncIterator[tuple[int, CredentialStore, ControllerRuntime]]:
    generation = str(uuid4())
    store = CredentialStore(tmp_path / "credentials", generation)
    settings = load_controller_configuration(Path(__file__).resolve().parents[2])
    repository = Path(__file__).resolve().parents[2]
    (tmp_path / "config/backends").mkdir(parents=True)
    (tmp_path / "contracts").mkdir()
    shutil.copyfile(
        repository / "config/backends/synchronization_config.toml",
        tmp_path / "config/backends/synchronization_config.toml",
    )
    shutil.copyfile(
        repository / "contracts/spikeglx_mapping_reference.json",
        tmp_path / "contracts/spikeglx_mapping_reference.json",
    )
    runtime = ControllerRuntime(
        generation=generation,
        configuration=pb.ExperimentConfiguration(
            subject="subject",
            experiment="experiment",
            recording_root=str(tmp_path),
            mode=pb.SESSION_MODE_OPEN_LOOP,
            trials=[pb.TrialDefinition(trial_number=1)],
            backends=[pb.BackendSettings(backend_name="visual_stimulus", enabled=True)],
        ),
        limits=ControllerLimits(**settings.limits_kwargs),
        validators={},
        backends={},
        configuration_history_path=tmp_path / "last_configuration.json",
        software_root=tmp_path,
    )

    async def authenticate(
        client_id: str, controller_generation: str, peer: str, metadata: object
    ) -> None:
        if controller_generation != generation:
            raise AuthenticationError("wrong controller generation")
        principal = await asyncio.to_thread(store.lookup, client_id)
        if principal is None:
            raise AuthenticationError("client not provisioned")
        require_authenticated_peer(
            peer,
            cast(list[tuple[str, str]], metadata),
            expected_role=principal.role,
            expected_generation=principal.generation,
            expected_token=principal.token,
        )

    server = grpc.aio.server()

    class Diagnostic:
        async def check(self) -> rpc.SpikeGLXConnectionResult:
            return rpc.SpikeGLXConnectionResult(
                connected=True,
                address="169.254.240.108",
                port=4142,
                version="SpikeGLX test",
                running=False,
                saving=False,
            )

    service = ExperimentControllerService(
        runtime,
        client_authentication=authenticate,
        peer_tokens={"acquisition": (generation, "camera-trigger-token")},
        spikeglx_diagnostic=cast(SpikeGLXDiagnostic, Diagnostic()),
    )
    wire.add_ExperimentControllerServiceServicer_to_server(service, server)
    port = server.add_insecure_port("127.0.0.1:0")
    assert port > 0
    await server.start()
    try:
        yield port, store, runtime
    finally:
        await server.stop(0)
        await service.aclose()


async def test_forged_credentials_are_rejected(
    controller: tuple[int, CredentialStore, ControllerRuntime],
) -> None:
    port, store, _runtime = controller
    principal = store.provision_client("cli")
    forged = Principal("cli", principal.generation, "incorrect-token")
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(channel, forged)
        with pytest.raises(grpc.aio.AioRpcError) as caught:
            await client.get_snapshot()
        assert caught.value.code() == grpc.StatusCode.UNAUTHENTICATED
    store.remove_client(principal)


async def test_spikeglx_diagnostic_requires_authenticated_client(
    controller: tuple[int, CredentialStore, ControllerRuntime],
) -> None:
    port, store, _runtime = controller
    principal = store.provision_client("gui")
    async with loopback_channel(port, 16_777_216) as channel:
        stub = wire.ExperimentControllerServiceStub(channel)
        query = rpc.SpikeGLXConnectionQuery(client_id=principal.generation)
        result = await stub.CheckSpikeGLXConnection(
            query, metadata=principal.metadata(), timeout=5
        )
        assert result.connected
        assert result.version == "SpikeGLX test"
        with pytest.raises(grpc.aio.AioRpcError) as caught:
            await stub.CheckSpikeGLXConnection(query, timeout=5)
        assert caught.value.code() == grpc.StatusCode.UNAUTHENTICATED
    store.remove_client(principal)


async def test_spikeglx_inventory_rpc_auth_lease_revision_and_digest_guards(
    controller: tuple[int, CredentialStore, ControllerRuntime],
) -> None:
    port, store, _runtime = controller
    principal = store.provision_client("gui")
    async with loopback_channel(port, 16_777_216) as channel:
        stub = wire.ExperimentControllerServiceStub(channel)
        request = rpc.SpikeGLXInventoryRequest(expected_configuration_revision=1)
        with pytest.raises(grpc.aio.AioRpcError) as unauthenticated:
            await stub.GetSpikeGLXInventory(request, timeout=5)
        assert unauthenticated.value.code() == grpc.StatusCode.UNAUTHENTICATED
        client = HeadlessClient(channel, principal)
        async with client.control():
            request.command.CopyFrom(client.operator_command())
            snapshot = await stub.GetSpikeGLXInventory(
                request, metadata=principal.metadata(), timeout=5
            )
            assert snapshot.configuration_revision == 1
            assert len(snapshot.file_sha256) == 64
            channel_mapping = sync_pb.PulseChannel(
                role=sync_pb.PULSE_ROLE_CUSTOM,
                family=sync_pb.STREAM_FAMILY_NI,
                stream_index=0,
                channel_index=0,
                source_id="loopback-input",
            )
            update = rpc.SpikeGLXInventoryUpdateRequest(
                command=client.operator_command(),
                expected_configuration_revision=1,
                expected_file_sha256=snapshot.file_sha256,
                pulse_channels=[channel_mapping],
            )
            accepted = await stub.UpdateSpikeGLXInventory(
                update, metadata=principal.metadata(), timeout=5
            )
            assert accepted.result == pb.COMMAND_RESULT_ACCEPTED
            current = await stub.GetSpikeGLXInventory(
                request, metadata=principal.metadata(), timeout=5
            )
            assert current.file_sha256 != snapshot.file_sha256
            assert current.pulse_channels[0].source_id == "loopback-input"
            update.command.CopyFrom(client.operator_command())
            stale = await stub.UpdateSpikeGLXInventory(
                update, metadata=principal.metadata(), timeout=5
            )
            assert stale.result == pb.COMMAND_RESULT_REJECTED
            assert "changed since inventory was read" in stale.failure.message
            wrong_revision = rpc.SpikeGLXInventoryRequest(
                command=client.operator_command(), expected_configuration_revision=2
            )
            with pytest.raises(grpc.aio.AioRpcError) as stale_revision:
                await stub.GetSpikeGLXInventory(
                    wrong_revision, metadata=principal.metadata(), timeout=5
                )
            assert stale_revision.value.code() == grpc.StatusCode.FAILED_PRECONDITION
    store.remove_client(principal)


async def test_spikeglx_timeout_does_not_start_a_second_native_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()

    def blocked(_root: Path) -> rpc.SpikeGLXConnectionResult:
        entered.set()
        release.wait(1)
        return rpc.SpikeGLXConnectionResult(connected=True)

    monkeypatch.setattr("cephvr.synchronization.diagnostic._read_once", blocked)
    diagnostic = SpikeGLXDiagnostic(Path.cwd(), timeout_s=0.01)
    try:
        first = await diagnostic.check()
        assert entered.is_set()
        assert "timed out" in first.error
        second = await diagnostic.check()
        assert "previous" in second.error
    finally:
        release.set()


async def test_gui_observes_before_explicit_control_claim(
    controller: tuple[int, CredentialStore, ControllerRuntime],
) -> None:
    port, store, _runtime = controller
    principal = store.provision_client(
        "gui", generation=str(uuid4()), token="gui-token"
    )
    received: list[int] = []
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(
            channel,
            principal,
            on_snapshot=lambda view: received.append(view.state_revision),
        )
        async with client.observe():
            assert received
            assert client.snapshot.control.holder_client_id != principal.generation
            await client.claim_control()
            assert client.snapshot.control.holder_client_id == principal.generation
        assert (
            await client.get_snapshot()
        ).control.holder_client_id != principal.generation
    store.remove_client(principal)


async def test_gui_can_save_current_configuration_history_on_close(
    controller: tuple[int, CredentialStore, ControllerRuntime], tmp_path: Path
) -> None:
    port, store, _runtime = controller
    principal = store.provision_client("gui")
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(channel, principal)
        async with client.observe():
            await client.claim_control()
            outcome = await client.execute("SaveConfigurationHistory")
            assert outcome.succeeded
    document = json.loads((tmp_path / "last_configuration.json").read_text())
    assert document["format_version"] == 1
    assert document["configuration"]["subject"] == "subject"
    assert document["configuration"]["experiment"] == "experiment"
    restored = _load_saved_configuration(
        tmp_path / "last_configuration.json", max_message_bytes=16_777_216
    )
    assert restored.subject == "subject"
    assert restored.experiment == "experiment"
    store.remove_client(principal)


async def test_control_takeover_and_real_missing_backend_rejection(
    controller: tuple[int, CredentialStore, ControllerRuntime],
) -> None:
    port, store, _runtime = controller
    first = store.provision_client("cli")
    second = store.provision_client("cli")
    async with loopback_channel(port, 16_777_216) as channel:
        a, b = HeadlessClient(channel, first), HeadlessClient(channel, second)
        async with a.control():
            old = a.operator_command()
            with pytest.raises(ClientError, match="held"):
                async with b.control():
                    pytest.fail("control was acquired without explicit takeover")
            async with b.control(takeover=True):
                stale = await a.stub.Setup(old, metadata=first.metadata(), timeout=2)
                assert stale.result == pb.COMMAND_RESULT_REJECTED
                with pytest.raises(
                    ClientError, match="registered|unavailable|validator"
                ) as rejected:
                    await b.execute("Setup")
                assert rejected.value.command_id
                assert not rejected.value.admission_uncertain
                snapshot = await b.get_snapshot()
                assert snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                assert not snapshot.session.activated
                assert snapshot.control.holder_client_id == second.generation
                # Closing the displaced holder's exact stream must not revoke
                # the replacement holder or disturb the controller's lifecycle.
                a._watch.cancel()
                assert a._reader is not None
                with pytest.raises(asyncio.CancelledError):
                    await a._reader
                still_owned = await b.get_snapshot()
                assert still_owned.control.holder_client_id == second.generation
        result = await b.get_snapshot()
        assert not result.control.HasField("holder_client_id")
    store.remove_client(first)
    store.remove_client(second)


async def test_pending_setup_cancel_and_prompt_response_are_independent_loopback_commands(
    controller: tuple[int, CredentialStore, ControllerRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.controller.support_components import _RetainedPeer

    from cephvr.controller.ports import BackendPort

    port, store, runtime = controller
    principal = store.provision_client("gui")
    backend_context = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=str(uuid4())
    )
    runtime.setup_admission.backends = {
        "visual_stimulus": cast(
            BackendPort, _RetainedPeer(backend_context, rpc.RetainedResult())
        )
    }
    runtime.supervisor_state.processes["visual_stimulus"] = rpc.ProcessHealthStatus(
        process=pb.ProcessIdentity(
            role="visual_stimulus", generation=backend_context.backend_generation
        ),
        process_running=True,
        connected=True,
    )
    runtime.setup_admission.validators = {
        "structural": lambda _: pb.ValidationResult(completed=True, valid=True)
    }
    runtime.setup_admission.file_policy_loader = lambda _active: {}
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending_setup(*_args: object) -> None:
        entered.set()
        await release.wait()

    monkeypatch.setattr(runtime.setup_execution, "run_setup", pending_setup)
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(channel, principal, rpc_timeout_s=3)
        async with client.observe():
            await client.claim_control()
            from cephvr.gui.controller_bridge import ControllerBridge

            bridge = ControllerBridge(principal, port, 16_777_216, (0,))
            bridge._loop = asyncio.get_running_loop()
            bridge._queue = asyncio.PriorityQueue(maxsize=33)
            bridge._connected = True
            bridge._connection_epoch = 1
            bridge._controller_generation = runtime.generation
            admissions: list[tuple[str, str]] = []
            completions: list[tuple[str, str, str, str]] = []
            admission_event, completion_event = asyncio.Event(), asyncio.Event()

            def on_admitted(action: str, command_id: str) -> None:
                admissions.append((action, command_id))
                admission_event.set()

            def on_finished(
                action: str, command_id: str, status: str, message: str
            ) -> None:
                completions.append((action, command_id, status, message))
                completion_event.set()

            bridge.command_admitted.connect(on_admitted)
            bridge.operation_finished.connect(on_finished)
            command_task = asyncio.create_task(bridge._commands(client))
            accepted_configuration = client.snapshot.configuration_values.current
            assert bridge.request(
                "Setup",
                expected_revision=client.snapshot.configuration_values.revision,
                expected_configuration=accepted_configuration.SerializeToString(
                    deterministic=True
                ),
            )
            await asyncio.wait_for(entered.wait(), 2)
            while not any(action == "Setup" for action, _ in admissions):
                admission_event.clear()
                await asyncio.wait_for(admission_event.wait(), 2)
            setup_id = next(
                command_id for action, command_id in admissions if action == "Setup"
            )
            current = next(
                item
                for item in client.snapshot.operations
                if item.context.command_id == setup_id
            )
            assert not current.complete

            assert bridge.request("Cancel Setup")
            while not any(action == "Cancel Setup" for action, _ in admissions):
                admission_event.clear()
                await asyncio.wait_for(admission_event.wait(), 2)
            cancel_id = next(
                command_id
                for action, command_id in admissions
                if action == "Cancel Setup"
            )
            assert cancel_id != setup_id
            # The Setup coroutine is still blocked behind this gate. Its
            # operation may already be failed by the independently admitted
            # cancellation cleanup, which is the expected safety response.
            assert not release.is_set()
            release.set()
            while not {
                ("Cancel Setup", cancel_id),
                ("Setup", setup_id),
            } <= {(action, command_id) for action, command_id, _, _ in completions}:
                completion_event.clear()
                await asyncio.wait_for(completion_event.wait(), 3)
            assert (
                next(
                    status
                    for action, command_id, status, _ in completions
                    if action == "Setup" and command_id == setup_id
                )
                == "failed"
            )
            assert (
                next(
                    status
                    for action, command_id, status, _ in completions
                    if action == "Cancel Setup" and command_id == cancel_id
                )
                == "failed"
            )

            prompt = pb.Prompt(
                prompt_id=str(uuid4()),
                setup=pb.SessionContext(
                    controller_generation=runtime.generation, session_id=str(uuid4())
                ),
                operation=pb.OperationContext(command_id=str(uuid4())),
                explanation="A recovery choice is required.",
                permitted_choices=["continue", "cancel"],
            )
            recovery_gate = asyncio.Event()

            async def wait_for_recovery_choice() -> None:
                await recovery_gate.wait()

            await runtime.install_startup_recovery(
                prompt,
                wait_for_recovery_choice,
                "pending recovery choice",
            )
            await asyncio.wait_for(
                client._wait(
                    lambda state: any(
                        item.prompt_id == prompt.prompt_id for item in state.prompts
                    )
                ),
                2,
            )
            assert bridge.request(
                "respond_prompt",
                prompt=prompt.SerializeToString(),
                choice="cancel",
            )
            while not any(
                action == "respond_prompt" and status == "completed"
                for action, _, status, _ in completions
            ):
                completion_event.clear()
                await asyncio.wait_for(completion_event.wait(), 2)
            recovery_gate.set()
            assert bridge.request("quit")
            await asyncio.wait_for(command_task, 2)
    store.remove_client(principal)


def _install_microcontroller(runtime: ControllerRuntime, *, uploader=None):
    from unittest.mock import AsyncMock

    from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
    from cephvr.acquisition.v1 import runtime_pb2 as acquisition
    from cephvr.controller.microcontroller.device import MicrocontrollerDevice
    from cephvr.controller.microcontroller.lifecycle import MicrocontrollerLifecycle

    settings = pb.AcquisitionSettings()
    settings.pulses.port = "COM8"
    settings.pulses.trial_state_enabled = True
    settings.pulses.trial_state_pin = "D9"
    runtime.configuration_state.current.backends.add(
        backend_name="acquisition", enabled=False, acquisition=settings
    )
    serial = AsyncMock()
    observation = mcu.MicrocontrollerObservation(
        port="COM8", connection_id="connection"
    )
    observation.state.behavioral.running = False
    observation.state.tracking.running = False
    serial.connect.return_value = observation
    serial.configure.return_value = observation
    serial.status.return_value = observation
    serial.diagnostic_start.return_value = (True, "trial_state", "D9", 1)
    serial.diagnostic_stop.return_value = (False, "trial_state", "D9", 1)
    serial.off.return_value = mcu.PulseCommandEvidence(
        outcome=mcu.PULSE_COMMAND_OUTCOME_APPLIED, resulting_state=observation.state
    )
    owner = MicrocontrollerDevice(
        serial, settings, acquisition.AcquisitionFilePolicies(), runtime.clock, uploader
    )
    runtime.microcontroller_device = owner
    runtime.microcontroller.owner = owner
    runtime.publisher.microcontroller_view = owner.snapshot_view
    owner.changed = runtime.publisher.publish
    runtime.microcontroller_lifecycle = MicrocontrollerLifecycle(
        owner,
        generation=runtime.generation,
        lifecycle=runtime.lifecycle,
        configuration=runtime.configuration_state,
        device=runtime.device_state,
        limits=runtime.limit_state,
        clock=runtime.clock,
        publish=runtime.publisher.publish,
        warning=runtime.record_warning,
        spawn=runtime._spawn,
        interrupt=lambda attempt, reason, issued: runtime.interruption.interrupt(
            attempt, reason, issued_ns=issued
        ),
    )
    return owner, serial


async def test_camera_trigger_rpc_authenticates_exact_peer_and_original_deadline(
    controller,
):
    from cephvr.acquisition.microcontroller_client import (
        ControllerMicrocontrollerClient,
    )
    from cephvr.shared.transport_deadlines import deadline_metadata

    port, _store, runtime = controller
    owner, serial = _install_microcontroller(runtime)
    principal = Principal("acquisition", runtime.generation, "camera-trigger-token")
    deadline = runtime.clock() + 5_000_000_000
    request = rpc.MicrocontrollerIoRequest(
        command_id=str(uuid4()),
        requester=pb.ProcessIdentity(role="acquisition", generation=runtime.generation),
        controller_generation=runtime.generation,
        deadline_monotonic_ns=deadline,
        kind=rpc.MICROCONTROLLER_IO_KIND_CONNECT,
        requested=owner.settings.pulses,
    )
    request.claim_id = request.command_id
    async with loopback_channel(port, 16_777_216) as channel:
        stub = wire.ExperimentControllerServiceStub(channel)
        for credential in [
            Principal("acquisition", runtime.generation, "forged"),
            Principal("acquisition", str(uuid4()), principal.token),
        ]:
            with pytest.raises(grpc.aio.AioRpcError) as caught:
                await stub.ExecuteMicrocontrollerIo(
                    request,
                    metadata=(*credential.metadata(), deadline_metadata(deadline)),
                    timeout=2,
                )
            assert caught.value.code() == grpc.StatusCode.UNAUTHENTICATED
        with pytest.raises(grpc.aio.AioRpcError) as mismatch:
            await stub.ExecuteMicrocontrollerIo(
                request,
                metadata=(*principal.metadata(), deadline_metadata(deadline - 1)),
                timeout=2,
            )
        assert mismatch.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert serial.connect.await_count == 0
        result = await stub.ExecuteMicrocontrollerIo(
            request,
            metadata=(*principal.metadata(), deadline_metadata(deadline)),
            timeout=2,
        )
        assert result.succeeded and result.observation.port == "COM8"
        replay = await stub.ExecuteMicrocontrollerIo(
            request,
            metadata=(*principal.metadata(), deadline_metadata(deadline)),
            timeout=2,
        )
        assert replay == result and serial.connect.await_count == 1
        client = ControllerMicrocontrollerClient(
            stub, principal, runtime.generation, lambda: owner.settings.pulses
        )
        client.claim_id = request.claim_id
        boundary, issued = runtime.clock() + 1_000_000, runtime.clock()
        await client.off(
            ("behavioral",),
            scheduled_boundary_ns=boundary,
            stop_issued_ns=issued,
            deadline_ns=deadline,
        )
        call = serial.off.await_args
        assert call.args == ((1,),)
        assert call.kwargs == {
            "scheduled_boundary_ns": boundary,
            "stop_issued_ns": issued,
            "deadline_ns": deadline,
        }
        bad = rpc.MicrocontrollerIoRequest.FromString(request.SerializeToString())
        bad.command_id = str(uuid4())
        bad.kind = rpc.MICROCONTROLLER_IO_KIND_STATUS
        bad.claim_id = str(uuid4())
        rejected = await stub.ExecuteMicrocontrollerIo(
            bad,
            metadata=(*principal.metadata(), deadline_metadata(deadline)),
            timeout=2,
        )
        assert not rejected.succeeded and "claim" in rejected.failure
        await client.close(deadline_ns=deadline)
        assert not owner.acquisition_claimed and owner.cleanup_complete


@pytest.mark.parametrize("source_kind", ["hex", "ino"])
async def test_general_microcontroller_commands_and_upload_work_without_acquisition_backend(
    controller, tmp_path, source_kind
):
    from cephvr.controller.microcontroller.firmware import read_uno_image
    from cephvr.controller.microcontroller.firmware_source import read_firmware

    port, store, runtime = controller
    events = []
    image_path = tmp_path / "compiled.hex"
    image_path.write_bytes(b":0400000001020304F2\n:00000001FF\n")
    image = read_uno_image(str(image_path))
    path = tmp_path / f"source.{source_kind}"
    path.write_bytes(
        b"void setup() {}\nvoid loop() {}\n" if source_kind == "ino" else image.payload
    )

    class Uploader:
        cleanup_complete = True

        def reset_cancel(self):
            pass

        def compile(self, selected, operation, *, deadline_ns):
            events.append(("compile", operation.command_id, deadline_ns))
            return image

        def prepare(self, selected):
            assert selected.payload == image.payload

        def upload(self, port, operation, *, deadline_ns):
            assert port == "COM8"
            events.append(("upload", operation.command_id, deadline_ns))

        def close(self, *, deadline_ns):
            self.cleanup_complete = True

        def cancel(self):
            pass

    owner, serial = _install_microcontroller(runtime, uploader=Uploader())
    assert runtime.microcontroller.device_views() is None
    assert not runtime.configuration_state.current.backends[-1].enabled
    principal = store.provision_client("gui")
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(channel, principal)
        stub = wire.ExperimentControllerServiceStub(channel)
        async with client.observe():
            await client.claim_control()
            for kind in [
                rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT,
                rpc.MICROCONTROLLER_COMMAND_KIND_START,
                rpc.MICROCONTROLLER_COMMAND_KIND_STOP,
                rpc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE,
            ]:
                request = rpc.MicrocontrollerCommandRequest(
                    command=client.operator_command(),
                    expected_configuration_revision=runtime.configuration_state.revision,
                    kind=kind,
                )
                if kind == rpc.MICROCONTROLLER_COMMAND_KIND_START:
                    request.signal = pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE
                if kind == rpc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE:
                    request.firmware_path = str(path)
                    request.firmware_sha256 = read_firmware(str(path)).digest
                admission = await stub.ExecuteMicrocontrollerCommand(
                    request, metadata=principal.metadata(), timeout=2
                )
                assert admission.result == pb.COMMAND_RESULT_ACCEPTED
                for _ in range(200):
                    operation = runtime.control.operations[
                        request.command.operator.command_id
                    ]
                    if operation.complete:
                        break
                    await asyncio.sleep(0.005)
                assert operation.complete and operation.succeeded, operation.failure
                snapshot = await client.get_snapshot()
                assert snapshot.microcontroller.observation.port == "COM8"
                assert snapshot.microcontroller.diagnostic.active == (
                    kind == rpc.MICROCONTROLLER_COMMAND_KIND_START
                )
            assert [phase for phase, _, _ in events] == (
                ["compile", "upload"] if source_kind == "ino" else ["upload"]
            )
            assert (
                len({(operation, deadline) for _, operation, deadline in events}) == 1
            )
            assert serial.close.await_count == 1
            assert not runtime.authority_status().cleanup_confirmed
            deadline = runtime.clock() + 1_000_000_000
            await owner.close(deadline_ns=deadline, permanent=False)
            assert (
                owner.cleanup_complete
                and not (await client.get_snapshot()).microcontroller.cleanup_pending
            )
    store.remove_client(principal)


async def test_normal_shutdown_releases_controller_owned_microcontroller(controller):
    port, store, runtime = controller
    owner, serial = _install_microcontroller(runtime)
    owner.port_owned = True
    owner.view.observation.CopyFrom(serial.connect.return_value)
    runtime.lifecycle.session.cleanup_confirmed = True
    principal = store.provision_client("gui")
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(channel, principal)
        async with client.observe():
            await client.claim_control()
            request = client.operator_command()
            admission = await runtime.shutdown_application(request)
            assert admission.result == pb.COMMAND_RESULT_ACCEPTED
            for _ in range(100):
                if owner.cleanup_complete:
                    break
                await asyncio.sleep(0.005)
            assert owner.cleanup_complete
            assert runtime.authority_status().cleanup_confirmed
            assert (
                owner.shutdown_deadline_ns
                == runtime.lifecycle.shutdown_intent_ns
                + runtime.limits.setup_cancel_ns
                + runtime.limits.recovery_ns
            )
            assert (
                serial.close.await_args.kwargs["deadline_ns"]
                == owner.shutdown_deadline_ns
            )
    await runtime.cancel_background_tasks()
    store.remove_client(principal)


async def test_old_camera_projection_cannot_replace_controller_microcontroller_state(
    controller,
):
    _port, _store, runtime = controller
    owner, serial = _install_microcontroller(runtime)
    owner.view.observation.CopyFrom(serial.connect.return_value)
    owner.view.diagnostic.active = True
    stale = pb.AcquisitionDeviceViews()
    stale.pulses.port = "COM9"
    stale.diagnostic.active = False
    runtime.projections.devices = stale
    snapshot = runtime.publisher.build_snapshot()
    assert snapshot.microcontroller.observation.port == "COM8"
    assert snapshot.microcontroller.diagnostic.active
    assert snapshot.acquisition_devices.pulses.port == "COM9"


@pytest.mark.parametrize("cause", ["control_loss", "shutdown"])
async def test_controller_cleanup_waits_for_camera_off_and_claim_release(
    controller, cause
):
    from cephvr.acquisition.microcontroller_client import (
        ControllerMicrocontrollerClient,
    )

    port, store, runtime = controller
    owner, serial = _install_microcontroller(runtime)
    principal = store.provision_client("gui")
    peer = Principal("acquisition", runtime.generation, "camera-trigger-token")
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(channel, principal)
        camera = ControllerMicrocontrollerClient(
            wire.ExperimentControllerServiceStub(channel),
            peer,
            runtime.generation,
            lambda: owner.settings.pulses,
        )
        async with client.observe():
            await client.claim_control()
            deadline = runtime.clock() + 5_000_000_000
            await camera.connect(deadline_ns=deadline)
            if cause == "control_loss":
                await runtime.microcontroller_lifecycle.owner_lost()
                assert owner.snapshot_view().cleanup_pending
            else:
                admission = await runtime.shutdown_application(
                    client.operator_command()
                )
                assert admission.result == pb.COMMAND_RESULT_ACCEPTED
            await asyncio.sleep(0)
            serial.close.assert_not_awaited()
            await camera.off(
                ("behavioral",),
                scheduled_boundary_ns=None,
                stop_issued_ns=runtime.clock(),
                deadline_ns=deadline,
            )
            await camera.close(deadline_ns=deadline)
            for _ in range(100):
                if owner.cleanup_complete:
                    break
                await asyncio.sleep(0.005)
            assert owner.cleanup_complete
            assert serial.off.await_count == 1
    await runtime.cancel_background_tasks()
    store.remove_client(principal)
