"""TI SDK subprocess boundary without loading the SDK or touching USB devices."""

import asyncio
from pathlib import Path

import pytest

from cephvr.platform.windows import projector_brightness as brightness


@pytest.mark.parametrize("result", [0, 1, None])
async def test_projector_sdk_readback_failure_and_timeout(
    monkeypatch: pytest.MonkeyPatch, result: int | None
) -> None:
    class Process:
        returncode = None
        killed = False

        async def communicate(self):
            if result is None and not self.killed:
                await asyncio.Event().wait()
            self.returncode = result if not self.killed else -1
            return b"Interface 0: readback R=101 G=101 B=101", None

        def kill(self):
            self.killed = True

    process = Process()
    calls = []

    async def start(*args, **kwargs):
        calls.append((args, kwargs))
        return process

    monkeypatch.setenv("WINDIR", "C:/Windows")
    monkeypatch.setattr(
        brightness.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )
    monkeypatch.setattr(brightness.sys, "platform", "win32")
    monkeypatch.setattr(brightness.asyncio, "create_subprocess_exec", start)
    if result is None:
        with pytest.raises(TimeoutError):
            await brightness.adjust_brightness(101, 0.01)
        assert process.killed and process.returncode == -1
    elif result:
        with pytest.raises(RuntimeError, match="readback"):
            await brightness.adjust_brightness(101, 1)
    else:
        assert "readback R=101" in await brightness.adjust_brightness(101, 1)
    args, kwargs = calls[0]
    assert "SysWOW64" in args[0]
    assert args[-2:] == ("-Current", "101")
    assert Path(args[args.index("-File") + 1]).is_file()
    assert kwargs["creationflags"]


@pytest.mark.parametrize("current", [100, 2501])
async def test_projector_sdk_rejects_invalid_current(current: int) -> None:
    with pytest.raises(ValueError, match="101 and 2500"):
        await brightness.adjust_brightness(current, 1)
