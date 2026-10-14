"""Read-only diagnostic through the existing controller; never take a lease."""
import asyncio
import json
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import services_pb2_grpc as transport
from cephvr.shared.credentials import CredentialStore, default_runtime_root


async def main():
    root = Path.cwd()
    runtime = default_runtime_root()
    generation = json.loads((runtime / "launcher.json").read_text())["controller_generation"]
    settings = tomllib.loads((root / "config/backends/experiment_config.toml").read_text())["rpc"]
    endpoint = tomllib.loads((root / "config/backends/synchronization_config.toml").read_text())["spikeglx"]
    store = CredentialStore(runtime, generation)
    principal = store.provision_client("cli")
    evidence = {
        "date_jst": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree": "dirty; existing concurrent changes preserved",
        "controller_generation": generation,
        "endpoint": endpoint,
        "method": "authenticated controller CheckSpikeGLXConnection RPC; no control lease or mutation",
        "limits": "connection/status only; no recording, pulse, wiring or synchronization acceptance",
        "initial_sandbox_tcp_probe": "WSAEACCES 10013; no remote connection result",
    }
    try:
        async with loopback_channel(settings["port"], settings["max_message_bytes"]) as channel:
            stub = transport.ExperimentControllerServiceStub(channel)
            result = await stub.CheckSpikeGLXConnection(
                rpc.SpikeGLXConnectionQuery(client_id=principal.generation),
                metadata=principal.metadata(), timeout=8,
            )
            evidence["result"] = MessageToDict(result, preserving_proto_field_name=True, always_print_fields_with_no_presence=True)
    except Exception as exc:
        evidence["error"] = str(exc)
    finally:
        store.remove_client(principal)
    Path(__file__).with_name("result.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


asyncio.run(main())
