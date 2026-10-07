"""CLI error reporting and the Ctrl+C scope under E02, without a live controller."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cephvr.client import main as cli
from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.auth import Principal


def _client(timeout_s: float = 0.05) -> HeadlessClient:
    principal = Principal("cli", str(uuid4()), "token")
    return HeadlessClient(loopback_channel(1, 1000), principal, rpc_timeout_s=timeout_s)


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        (pb.SESSION_PHASE_SETTING_UP, "CancelSetup"),
        (pb.SESSION_PHASE_STARTING, "AbortNow"),
        (pb.SESSION_PHASE_RUNNING, "AbortNow"),
    ],
)
async def test_ctrl_c_cancels_only_the_phases_e02_names(
    monkeypatch: pytest.MonkeyPatch, phase: int, expected: str
) -> None:
    client = _client()
    calls: list[str] = []

    async def execute(method: str, *args: object, **kwargs: object) -> str:
        calls.append(method)
        return method

    monkeypatch.setattr(
        HeadlessClient,
        "snapshot",
        property(lambda self: SimpleNamespace(session=SimpleNamespace(phase=phase))),
    )
    monkeypatch.setattr(client, "execute", execute)
    assert await client.cancel_current_work() == expected
    assert calls == [expected]


@pytest.mark.parametrize(
    "phase",
    [
        pb.SESSION_PHASE_CONFIGURATION,
        pb.SESSION_PHASE_READY,
        pb.SESSION_PHASE_FINALIZING,
    ],
)
async def test_ctrl_c_does_nothing_outside_the_e02_phases(
    monkeypatch: pytest.MonkeyPatch, phase: int
) -> None:
    client = _client()

    async def execute(*args: object, **kwargs: object) -> None:
        raise AssertionError("no command may be issued in this phase")

    monkeypatch.setattr(
        HeadlessClient,
        "snapshot",
        property(lambda self: SimpleNamespace(session=SimpleNamespace(phase=phase))),
    )
    monkeypatch.setattr(client, "execute", execute)
    with pytest.raises(ClientError, match="no cancellable"):
        await client.cancel_current_work()


async def test_unsynchronized_watch_times_out_with_a_message() -> None:
    client = _client()

    class Watch:
        def __aiter__(self) -> Watch:
            return self

        async def __anext__(self) -> None:
            await asyncio.Event().wait()

        def cancel(self) -> None:
            pass

    client.stub = SimpleNamespace(WatchState=lambda request, metadata: Watch())
    with pytest.raises(ClientError, match="did not synchronize"):
        async with client.observe():
            pass


async def test_unconfirmed_claim_times_out_with_its_command_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()

    async def admitted(*args: object, **kwargs: object) -> None:
        return None

    async def never(*args: object, **kwargs: object) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(
        HeadlessClient,
        "snapshot",
        property(lambda self: pb.Snapshot(controller_generation=str(uuid4()))),
    )
    monkeypatch.setattr(client, "_admit", admitted)
    monkeypatch.setattr(client, "_wait", never)
    with pytest.raises(ClientError, match="not confirmed") as caught:
        await client.claim_control()
    assert caught.value.command_id


async def test_missing_rpc_table_is_a_client_error(tmp_path: Path) -> None:
    config = tmp_path / "config/backends"
    config.mkdir(parents=True)
    (config / "experiment_config.toml").write_text("format_version = 1\n")
    args = argparse.Namespace(software_root=tmp_path)
    with pytest.raises(ClientError, match=r"\[rpc\]"):
        await cli._run(args)


def test_a_client_error_prints_its_message_and_command_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def failing(args: argparse.Namespace) -> int:
        raise ClientError("claim unconfirmed", command_id="abc")

    monkeypatch.setattr(cli, "_run", failing)
    monkeypatch.setattr(
        "sys.argv",
        ["cephvr", "--controller-generation", str(uuid4()), "--json", "status"],
    )
    assert cli.main() == 1
    assert '"error": "claim unconfirmed"' in capsys.readouterr().out
