"""Real loopback controller RPC checks; no simulated scientific backends."""

from __future__ import annotations

import asyncio
import json
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


@pytest_asyncio.fixture
async def controller(tmp_path: Path) -> AsyncIterator[tuple[int, CredentialStore]]:
    generation = str(uuid4())
    store = CredentialStore(tmp_path / "credentials", generation)
    settings = load_controller_configuration(Path(__file__).resolve().parents[2])
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
        peer_tokens={},
        spikeglx_diagnostic=cast(SpikeGLXDiagnostic, Diagnostic()),
    )
    wire.add_ExperimentControllerServiceServicer_to_server(service, server)  # type: ignore[no-untyped-call]
    port = server.add_insecure_port("127.0.0.1:0")
    assert port > 0
    await server.start()
    try:
        yield port, store
    finally:
        await server.stop(0)
        await service.aclose()


async def test_forged_credentials_are_rejected(
    controller: tuple[int, CredentialStore],
) -> None:
    port, store = controller
    principal = store.provision_client("cli")
    forged = Principal("cli", principal.generation, "incorrect-token")
    async with loopback_channel(port, 16_777_216) as channel:
        client = HeadlessClient(channel, forged)
        with pytest.raises(grpc.aio.AioRpcError) as caught:
            await client.get_snapshot()
        assert caught.value.code() == grpc.StatusCode.UNAUTHENTICATED
    store.remove_client(principal)


async def test_spikeglx_diagnostic_requires_authenticated_client(
    controller: tuple[int, CredentialStore],
) -> None:
    port, store = controller
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
    controller: tuple[int, CredentialStore],
) -> None:
    port, store = controller
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
    controller: tuple[int, CredentialStore], tmp_path: Path
) -> None:
    port, store = controller
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
    controller: tuple[int, CredentialStore],
) -> None:
    port, store = controller
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
                ):
                    await b.execute("Setup")
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
