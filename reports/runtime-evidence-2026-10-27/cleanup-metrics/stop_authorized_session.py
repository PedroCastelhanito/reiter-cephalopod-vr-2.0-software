"""Owner-authorized graceful stop of one exact active session, then normal shutdown."""

import asyncio, json, tomllib
from dataclasses import asdict
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.shared.credentials import CredentialStore, default_runtime_root
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.control.v1 import types_pb2 as pb

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent / "authorized-session-stop"
GEN = "d960f94d-61de-4172-9d5e-38de0de2bd6b"
SESSION = "fceadce2-bf45-480b-9c14-b22ea726b382"


async def main():
    assert not OUT.exists()
    OUT.mkdir()
    e = _existing_endpoint(default_runtime_root())
    assert e and e.controller_generation == GEN
    settings = tomllib.loads(
        (ROOT / "config/backends/experiment_config.toml").read_text()
    )
    store = CredentialStore(default_runtime_root(), GEN)
    p = store.provision_client("cli")
    try:
        async with loopback_channel(
            settings["rpc"]["port"], settings["rpc"]["max_message_bytes"]
        ) as ch:
            c = HeadlessClient(ch, p)
            async with c.observe():

                def save(name):
                    (OUT / name).write_text(
                        json.dumps(
                            MessageToDict(c.snapshot, preserving_proto_field_name=True),
                            indent=2,
                        )
                        + "\n"
                    )

                s = c.snapshot
                assert (
                    s.controller_generation == GEN
                    and s.session.context.session_id == SESSION
                )
                assert s.session.phase == pb.SESSION_PHASE_RUNNING and not s.prompts
                save("before.json")
                await c.claim_control(takeover=True)
                lease = c.snapshot.control.control_generation

                async def command(method):
                    s = c.snapshot
                    assert (
                        s.controller_generation == GEN
                        and s.control.holder_client_id == p.generation
                        and s.control.control_generation == lease
                    )
                    result = await asyncio.wait_for(c.execute(method), 90)
                    (OUT / (method + ".json")).write_text(
                        json.dumps(asdict(result), indent=2) + "\n"
                    )
                    assert result.succeeded and not result.needs_input
                    print(method, "succeeded", flush=True)

                await command("AbortNow")
                await asyncio.wait_for(
                    c._wait(
                        lambda s: (
                            s.controller_generation == GEN
                            and s.session.cleanup_confirmed
                            and not s.session.cleanup_blockers
                            and s.session.phase
                            in (pb.SESSION_PHASE_ENDED, pb.SESSION_PHASE_CONFIGURATION)
                        )
                    ),
                    90,
                )
                save("cleanup-confirmed.json")
                if c.snapshot.session.phase == pb.SESSION_PHASE_ENDED:
                    await command("NewSession")
                assert (
                    c.snapshot.session.phase == pb.SESSION_PHASE_CONFIGURATION
                    and not c.snapshot.prompts
                )
                await command("ShutdownApplication")
    finally:
        store.remove_client(p)


asyncio.run(main())
