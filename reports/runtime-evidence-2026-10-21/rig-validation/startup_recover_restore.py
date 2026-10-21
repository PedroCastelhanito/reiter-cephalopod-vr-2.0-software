"""Read-only live runtime inventory; no control claim or device commands."""
import asyncio
import json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

async def main():
    root = default_runtime_root()
    endpoint = _existing_endpoint(root)
    store = CredentialStore(root, endpoint.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            from cephvr.control.v1 import types_pb2 as pb, services_pb2 as rpc
            from google.protobuf.json_format import ParseDict
            original = ParseDict(json.loads((Path(__file__).parent / "full-texture/runtime-before.json").read_text())["configuration_values"]["current"], pb.ExperimentConfiguration())
            async with client.control(takeover=True):
                prompt = next(p for p in client.snapshot.prompts if "recover" in p.permitted_choices)
                assert prompt.setup.session_id == "3679c1f4-ab58-45b4-b752-66de400435c0"
                recovered = await client.execute("RespondToPrompt", rpc.PromptResponse(command=client.operator_command(), prompt_id=prompt.prompt_id, setup=prompt.setup, setup_operation=prompt.operation, choice="recover"))
                assert recovered.succeeded, recovered
                assert not client.snapshot.prompts
                print("Supported recovery preserved failed session; original unknown closure retained")
                await asyncio.wait_for(client._wait(lambda s: s.session.phase == pb.SESSION_PHASE_CONFIGURATION), 30)
                result = await client.execute("UpdateConfiguration", rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=original))
                assert result.succeeded, result
                assert client.snapshot.configuration_values.current == original
                saved = (Path(__file__).parent / "full-texture/saved-history-before.json").read_bytes()
                history = Path.cwd() / "config/last_configuration.json"
                before_history = history.read_bytes()
                expected_saved = (Path(__file__).parent / "full-texture/saved-history-before.json").read_bytes()
                assert before_history == expected_saved, "Concurrent saved configuration edit: preserve it"
                history.write_bytes(saved)
                assert history.read_bytes() == saved
                print("Original runtime configuration and saved history restored exactly")

    finally:
        store.remove_client(principal)

asyncio.run(main())
