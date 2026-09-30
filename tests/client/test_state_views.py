"""E03 stream-local configuration and generation invariants."""

from uuid import uuid4

import pytest

from cephvr.client.session import ClientError, HeadlessClient, StateViews
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal


def snapshot(revision: int, config: int = 1, *, values: bool = True) -> pb.Snapshot:
    view = pb.Snapshot(controller_generation="generation-one", state_revision=revision)
    view.configuration.revision = config
    if values:
        view.configuration_values.revision = config
        view.configuration_values.current.subject = "subject"
    return view


def test_stream_must_receive_matching_configuration() -> None:
    views = StateViews()
    with pytest.raises(ClientError):
        views.install(snapshot(1, values=False))
    views.install(snapshot(1))
    views.install(snapshot(4, values=False))
    assert views.current is not None
    assert views.current.configuration_values.current.subject == "subject"
    with pytest.raises(ClientError):
        views.install(snapshot(5, config=2, values=False))
    assert views.current.state_revision == 4


def test_older_view_cannot_roll_back_and_generation_change_requires_new_stream() -> (
    None
):
    views = StateViews()
    views.install(snapshot(5))
    views.install(snapshot(3, values=False))
    assert views.current is not None and views.current.state_revision == 5
    other = snapshot(6)
    other.controller_generation = "generation-two"
    with pytest.raises(ClientError):
        views.install(other)
    fresh = StateViews()
    with pytest.raises(ClientError):
        fresh.install(snapshot(7, values=False))


def test_views_do_not_alias_transport_messages() -> None:
    views = StateViews()
    incoming = snapshot(1)
    views.install(incoming)
    incoming.configuration_values.current.subject = "changed"
    assert views.current is not None
    assert views.current.configuration_values.current.subject == "subject"


async def test_confirmed_command_survives_subsequent_stream_failure() -> None:
    # A terminal view can arrive immediately before process shutdown. Its exact
    # retained result remains evidence even when the subsequent read fails.
    import grpc

    async with grpc.aio.insecure_channel("127.0.0.1:1") as channel:
        client = HeadlessClient(channel, Principal("cli", str(uuid4()), "test-token"))
        view = snapshot(1)
        command_id = str(uuid4())
        view.operations.add(
            context=pb.OperationContext(command_id=command_id),
            complete=True,
            succeeded=True,
        )
        client.views.install(view)
        client._failure = ClientError("connection ended")
        outcome = await client.wait_result(command_id)
        assert outcome.complete and outcome.succeeded
        with pytest.raises(ClientError, match="connection ended"):
            await client.wait_result(str(uuid4()))
