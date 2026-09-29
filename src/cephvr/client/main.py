"""Command-line access to the authoritative controller under E02."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path

import grpc
from google.protobuf.json_format import MessageToDict, Parse, ParseError

from cephvr.client.session import ClientError, HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.credentials import (
    CredentialError,
    CredentialStore,
    default_runtime_root,
)

COMMANDS = {
    "setup": "Setup",
    "cancel-setup": "CancelSetup",
    "start": "StartSession",
    "stop": "StopAfterTrial",
    "cancel-stop": "CancelStopAfterTrial",
    "abort": "AbortNow",
    "new-session": "NewSession",
    "shutdown": "ShutdownApplication",
    "save": "SaveConfigurationHistory",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--controller-generation",
        required=True,
        help="Exact running controller generation reported by the launcher.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--takeover", action="store_true")
    parser.add_argument("--no-wait", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    result = commands.add_parser("result")
    result.add_argument("command_id")
    config = commands.add_parser("configuration")
    config.add_argument(
        "--file", type=Path, help="Submit a complete JSON configuration."
    )
    for name in COMMANDS:
        commands.add_parser(name)
    response = commands.add_parser("respond")
    response.add_argument("prompt_id")
    response.add_argument("choice")
    return parser


def _print(value: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if "session" in value:
        session = value["session"]
        assert isinstance(session, dict)
        print(f"Controller: {value.get('controller_generation', 'unknown')}")
        print(f"Session: {session.get('phase', 'unknown')}")
        if value.get("prompts"):
            print("Operator input required:")
            print(json.dumps(value["prompts"], ensure_ascii=False, indent=2))
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


async def _run(args: argparse.Namespace) -> int:
    config_path = args.software_root / "config/backends/experiment_config.toml"
    with config_path.open("rb") as stream:
        settings = tomllib.load(stream)
    port = settings["rpc"]["port"]
    limit = settings["rpc"]["max_message_bytes"]
    if type(port) is not int or type(limit) is not int:
        raise ClientError("Controller RPC port and message limit must be integers.")
    store = CredentialStore(default_runtime_root(), args.controller_generation)
    principal = store.provision_client("cli")
    try:
        async with loopback_channel(port, limit) as channel:
            client = HeadlessClient(channel, principal)
            readonly = args.command in {"status", "result"} or (
                args.command == "configuration" and args.file is None
            )
            if readonly:
                state = await client.get_snapshot()
                if args.command == "status":
                    result = MessageToDict(state, preserving_proto_field_name=True)
                elif args.command == "configuration":
                    result = MessageToDict(
                        state.configuration_values, preserving_proto_field_name=True
                    )
                else:
                    operation = next(
                        (
                            op
                            for op in state.operations
                            if op.context.command_id == args.command_id
                        ),
                        None,
                    )
                    if operation is None:
                        raise ClientError("Command is not retained in this generation.")
                    result = MessageToDict(operation, preserving_proto_field_name=True)
                _print(result, as_json=args.json_output)
                return 0
            async with client.control(takeover=args.takeover):
                request: object | None = None
                if args.command == "configuration":
                    with args.file.open("rb") as stream:
                        raw = stream.read(limit + 1)
                    if len(raw) > limit:
                        raise ClientError("Configuration file exceeds RPC size limit.")
                    proposed = Parse(raw.decode("utf-8"), pb.ExperimentConfiguration())
                    method = "UpdateConfiguration"
                    request = rpc.UpdateConfigurationRequest(
                        command=client.operator_command(),
                        expected_revision=client.snapshot.configuration.revision,
                        proposed=proposed,
                    )
                elif args.command == "respond":
                    prompt = next(
                        (
                            p
                            for p in client.snapshot.prompts
                            if p.prompt_id == args.prompt_id
                        ),
                        None,
                    )
                    if prompt is None or args.choice not in prompt.permitted_choices:
                        raise ClientError(
                            "Prompt or permitted choice is no longer current."
                        )
                    method = "RespondToPrompt"
                    response = rpc.PromptResponse(
                        command=client.operator_command(),
                        prompt_id=prompt.prompt_id,
                        setup=prompt.setup,
                        setup_operation=prompt.operation,
                        choice=args.choice,
                    )
                    if prompt.HasField("runtime_incident"):
                        response.expected_incident_revision = (
                            prompt.runtime_incident.revision
                        )
                    request = response
                else:
                    method = COMMANDS[args.command]
                try:
                    outcome = await client.execute(
                        method, request, wait=not args.no_wait
                    )
                except asyncio.CancelledError:
                    # asyncio.run maps the first Ctrl+C to task cancellation. Keep the
                    # lease/stream while asking for bounded cleanup, as E02 requires.
                    outcome = await client.cancel_current_work()
                    _print(asdict(outcome), as_json=args.json_output)
                    return 130
                output = asdict(outcome)
                if outcome.needs_input:
                    output["prompts"] = [
                        MessageToDict(prompt, preserving_proto_field_name=True)
                        for prompt in client.snapshot.prompts
                    ]
                _print(output, as_json=args.json_output)
                if outcome.needs_input:
                    return 3
                if outcome.complete and outcome.succeeded is None:
                    raise ClientError(
                        "Completed command has no confirmed success/failure result.",
                        command_id=outcome.command_id,
                    )
                return 1 if outcome.succeeded is False else 0
    finally:
        store.remove_client(principal)


def main() -> int:
    args = _parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Cancellation completion unconfirmed.", file=sys.stderr)
        return 130
    except (
        ClientError,
        CredentialError,
        ValueError,
        OSError,
        ParseError,
        grpc.RpcError,
    ) as exc:
        error: dict[str, object] = {"error": str(exc)}
        if isinstance(exc, ClientError) and exc.command_id is not None:
            error["command_id"] = exc.command_id
        _print(error, as_json=args.json_output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
