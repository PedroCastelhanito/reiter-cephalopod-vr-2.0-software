"""Real loopback controller RPC checks; no simulated scientific backends."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from uuid import uuid4

import grpc
import pytest
import pytest_asyncio

from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2_grpc as wire
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import load_controller_configuration
from cephvr.controller.runtime import ControllerRuntime
from cephvr.controller.service import ExperimentControllerService
from cephvr.controller.state import ControllerLimits
from cephvr.shared.auth import (
    AuthenticationError,
    Principal,
    require_authenticated_peer,
)
from cephvr.shared.credentials import CredentialStore


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
            backends=[pb.BackendSettings(backend_name="vr", enabled=True)],
        ),
        limits=ControllerLimits(**settings.limits_kwargs),
        validators={},
        backends={},
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
    service = ExperimentControllerService(
        runtime, client_authentication=authenticate, peer_tokens={}
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
