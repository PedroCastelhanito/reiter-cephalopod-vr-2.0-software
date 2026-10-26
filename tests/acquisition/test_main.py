"""Acquisition process teardown preserves exact controller release evidence."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import grpc
import pytest

from cephvr.acquisition.main import _close
from cephvr.acquisition.microcontroller_client import ControllerMicrocontrollerClient
from cephvr.shared.auth import Principal


class _Server:
    async def close(self, *, deadline_ns: int) -> None:
        assert deadline_ns == 500


class _Channel:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _Native:
    def __init__(self, running: bool) -> None:
        self.running = running
        self.checked: tuple[int, int] | None = None

    def process_running(self, pid: int, creation_time_100ns: int) -> bool:
        self.checked = pid, creation_time_100ns
        return self.running


class _UninspectableNative(_Native):
    def process_running(self, pid: int, creation_time_100ns: int) -> bool:
        self.checked = pid, creation_time_100ns
        raise OSError("process state unavailable")


class _Serial:
    def __init__(self, status: grpc.StatusCode = grpc.StatusCode.UNAVAILABLE) -> None:
        self.claim_id = "claim-1"
        self.status = status

    async def close(self, *, deadline_ns: int) -> None:
        assert deadline_ns == 500
        raise grpc.aio.AioRpcError(self.status, details="controller RPC failed")


async def _close_with_controller_state(
    running: bool,
) -> tuple[_Native, _Serial, _Channel, _Channel]:
    native = _Native(running)
    controller_channel = _Channel()
    supervisor_channel = _Channel()
    serial = _Serial()
    runtime = SimpleNamespace(
        serial=serial,
        state=SimpleNamespace(resources={}),
        resource_ledger=SimpleNamespace(),
    )
    await _close(
        _Server(),
        runtime,
        SimpleNamespace(),
        native,
        123,
        456,
        controller_channel,
        supervisor_channel,
        500,
    )
    return native, serial, controller_channel, supervisor_channel


@pytest.mark.asyncio
async def test_unavailable_close_after_exact_controller_exit_keeps_claim_unconfirmed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    (
        native,
        serial,
        controller_channel,
        supervisor_channel,
    ) = await _close_with_controller_state(running=False)

    assert native.checked == (123, 456)
    assert serial.claim_id == "claim-1"
    assert "release remains unconfirmed" in capsys.readouterr().err
    assert controller_channel.closed
    assert supervisor_channel.closed


@pytest.mark.asyncio
async def test_unavailable_close_with_controller_still_running_propagates() -> None:
    native = _Native(running=True)
    controller_channel = _Channel()
    supervisor_channel = _Channel()
    runtime = SimpleNamespace(
        serial=_Serial(),
        state=SimpleNamespace(resources={}),
        resource_ledger=SimpleNamespace(),
    )

    with pytest.raises(grpc.aio.AioRpcError):
        await _close(
            _Server(),
            runtime,
            SimpleNamespace(),
            native,
            123,
            456,
            controller_channel,
            supervisor_channel,
            500,
        )

    assert native.checked == (123, 456)
    assert controller_channel.closed
    assert supervisor_channel.closed


@pytest.mark.asyncio
async def test_non_unavailable_close_error_propagates_and_closes_channels() -> None:
    native = _Native(running=False)
    controller_channel = _Channel()
    supervisor_channel = _Channel()
    runtime = SimpleNamespace(
        serial=_Serial(grpc.StatusCode.INTERNAL),
        state=SimpleNamespace(resources={}),
        resource_ledger=SimpleNamespace(),
    )

    with pytest.raises(grpc.aio.AioRpcError) as caught:
        await _close(
            _Server(),
            runtime,
            SimpleNamespace(),
            native,
            123,
            456,
            controller_channel,
            supervisor_channel,
            500,
        )

    assert caught.value.code() == grpc.StatusCode.INTERNAL
    assert native.checked is None
    assert controller_channel.closed
    assert supervisor_channel.closed


@pytest.mark.asyncio
async def test_unavailable_close_with_uninspectable_controller_propagates() -> None:
    native = _UninspectableNative(running=False)
    controller_channel = _Channel()
    supervisor_channel = _Channel()
    runtime = SimpleNamespace(
        serial=_Serial(),
        state=SimpleNamespace(resources={}),
        resource_ledger=SimpleNamespace(),
    )

    with pytest.raises(OSError, match="process state unavailable"):
        await _close(
            _Server(),
            runtime,
            SimpleNamespace(),
            native,
            123,
            456,
            controller_channel,
            supervisor_channel,
            500,
        )

    assert native.checked == (123, 456)
    assert controller_channel.closed
    assert supervisor_channel.closed


@pytest.mark.asyncio
async def test_controller_client_keeps_claim_when_close_rpc_is_unavailable() -> None:
    class _UnavailableStub:
        async def ExecuteMicrocontrollerIo(self, *_args, **_kwargs):
            raise grpc.aio.AioRpcError(
                grpc.StatusCode.UNAVAILABLE, details="controller exited"
            )

    client = ControllerMicrocontrollerClient(
        _UnavailableStub(),  # type: ignore[arg-type]
        Principal("acquisition", str(uuid4()), "token"),
        "controller-1",
        requested=lambda: None,  # type: ignore[arg-type]
        clock=lambda: 0,
    )
    client.claim_id = "claim-1"

    with pytest.raises(grpc.aio.AioRpcError):
        await client.close(deadline_ns=100)

    assert client.claim_id == "claim-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [False, True])
async def test_teardown_does_not_release_an_absent_or_acknowledged_claim(
    claimed, capsys
):
    from cephvr.control.v1 import services_pb2 as wire

    class Stub:
        calls = 0

        async def ExecuteMicrocontrollerIo(self, request, **kwargs):
            self.calls += 1
            assert self.calls == 1
            assert request.claim_id == "claim-1"
            assert request.kind == wire.MICROCONTROLLER_IO_KIND_CLOSE
            return wire.MicrocontrollerIoResult(
                command_id=request.command_id, succeeded=True
            )

    stub = Stub()
    client = ControllerMicrocontrollerClient(
        stub,
        Principal("acquisition", str(uuid4()), "token"),
        "controller-1",
        requested=lambda: None,
        clock=lambda: 0,
    )
    if claimed:
        client.claim_id = "claim-1"
        await client.close(deadline_ns=500)
    assert not client.claim_id
    native = _Native(running=False)
    channels = _Channel(), _Channel()
    await _close(
        _Server(),
        SimpleNamespace(
            serial=client,
            state=SimpleNamespace(resources={}),
            resource_ledger=SimpleNamespace(),
        ),
        SimpleNamespace(),
        native,
        123,
        456,
        *channels,
        500,
    )
    assert stub.calls == int(claimed)
    assert native.checked is None
    assert all(channel.closed for channel in channels)
    assert not capsys.readouterr().err
