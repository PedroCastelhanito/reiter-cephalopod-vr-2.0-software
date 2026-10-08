"""Attempt the requested real dummy workflow using managed GUI transport."""
import argparse
import asyncio
import dataclasses
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.managed_configuration_transport import submit_configuration
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--unpaired", action="store_true")
parser.add_argument("--start", action="store_true")
parser.add_argument("--label", default="paired-setup")
args = parser.parse_args()
result = {"pairing": not args.unpaired, "events": []}

def keep(name, value):
    result[name] = value
    (OUT / f"{args.label}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(name, json.dumps(value), flush=True)

async def main():
    endpoint = _existing_endpoint(default_runtime_root())
    store = CredentialStore(default_runtime_root(), endpoint.controller_generation)
    principal = store.provision_client("cli")
    keep("controller_generation", endpoint.controller_generation)
    try:
        async with loopback_channel(50051, 16_777_216) as channel:
            client = HeadlessClient(channel, principal)
            async with client.control(takeover=True):
                state = await client.get_snapshot()
                if state.session.phase != pb.SESSION_PHASE_CONFIGURATION:
                    raise RuntimeError("Configuration phase required")
                original = pb.Snapshot.FromString((OUT / "pre-restart-snapshot.pb").read_bytes())
                keep("configuration_restored_on_restart", state.configuration_values.current == original.configuration_values.current)
                candidate = pb.ExperimentConfiguration.FromString((OUT / "dummy-candidate.pb").read_bytes())
                sync = next((b for b in candidate.backends if b.backend_name == "synchronization"), None)
                if sync is None:
                    sync = candidate.backends.add(backend_name="synchronization")
                sync.enabled = not args.unpaired
                def event(*values):
                    result["events"].append(list(values))
                    keep("events", result["events"])
                accepted = await submit_configuration(
                    client, {"base_revision": state.configuration.revision, "proposal": candidate.SerializeToString()},
                    endpoint.controller_generation, admitted=lambda v: event("admitted", v),
                    accepted=lambda v: event("accepted", v), finished=event,
                )
                keep("configuration_accepted", accepted)
                if not accepted:
                    return
                outcome = await asyncio.wait_for(client.execute("Setup"), 180)
                keep("setup", dataclasses.asdict(outcome))
                state = client.snapshot
                (OUT / f"{args.label}-setup-snapshot.pb").write_bytes(state.SerializeToString())
                keep("setup_state", {name: MessageToDict(getattr(state, name), preserving_proto_field_name=True)
                                      for name in ("session", "configuration", "trial")})
                keep("prompts", [MessageToDict(p, preserving_proto_field_name=True) for p in state.prompts])
                keep("warnings", [MessageToDict(w, preserving_proto_field_name=True) for w in state.warnings])
                if not outcome.succeeded:
                    if state.session.phase == pb.SESSION_PHASE_SETTING_UP:
                        keep("cancel_setup", dataclasses.asdict(await client.execute("CancelSetup")))
                    return
                if not args.start:
                    return
                started = await asyncio.wait_for(client.execute("StartSession"), 60)
                keep("start", dataclasses.asdict(started))
                if not started.succeeded:
                    return
                for _ in range(130):
                    await asyncio.sleep(1)
                    state = client.snapshot
                    if state.session.phase == pb.SESSION_PHASE_ENDED or state.session.shutdown_requested:
                        break
                else:
                    keep("abort_timeout", dataclasses.asdict(await client.execute("AbortNow")))
                state = client.snapshot
                (OUT / f"{args.label}-final-snapshot.pb").write_bytes(state.SerializeToString())
                keep("final_session", MessageToDict(state.session, preserving_proto_field_name=True))
                keep("final_trial", MessageToDict(state.trial, preserving_proto_field_name=True))
                keep("final_metadata", [MessageToDict(o, preserving_proto_field_name=True) for o in state.metadata])
                keep("final_reservation", MessageToDict(state.reservation, preserving_proto_field_name=True))
    except Exception as exc:
        keep("error", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        store.remove_client(principal)

asyncio.run(main())
