"""One-shot atomic proposal transport for the managed GUI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from cephvr.client.session import ClientError, HeadlessClient
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb


def configuration_update_plan(
    proposal: pb.ExperimentConfiguration,
    current: pb.ExperimentConfiguration,
    phase: int,
    action: str,
) -> str:
    """Choose direct, submit, or preserve behavior without rebasing a draft."""
    if proposal.SerializeToString(deterministic=True) == current.SerializeToString(
        deterministic=True
    ):
        return "direct"
    if action == "New session":
        return "direct_preserve"
    if phase in (pb.SESSION_PHASE_CONFIGURATION, pb.SESSION_PHASE_READY):
        return "submit"
    return "preserve"


async def submit_configuration(
    client: HeadlessClient,
    options: dict[str, Any],
    controller_generation: str,
    *,
    admitted: Callable[[str], None],
    accepted: Callable[[int], None],
    finished: Callable[[str, str, str, str], None],
) -> bool:
    """Admit once, await exact completion, then require the exact new version."""
    base_revision = int(options["base_revision"])
    if (
        client.snapshot.configuration.revision != base_revision
        or client.snapshot.controller_generation != controller_generation
    ):
        raise ClientError(
            "Configuration base changed; the draft was not rebased or submitted."
        )
    proposal = pb.ExperimentConfiguration.FromString(options["proposal"])
    request = rpc.UpdateConfigurationRequest(
        command=client.operator_command(),
        expected_revision=base_revision,
        proposed=proposal,
    )
    command_id = request.command.operator.command_id
    try:
        admission = await client._admit("UpdateConfiguration", request)
    except asyncio.CancelledError:
        finished(
            "submit_configuration",
            command_id,
            "unconfirmed",
            "Connection ended during configuration admission; this proposal will not be replayed.",
        )
        raise
    except ClientError as exc:
        finished(
            "submit_configuration",
            exc.command_id or command_id,
            "unconfirmed" if exc.admission_uncertain else "rejected",
            str(exc),
        )
        return False
    admitted(admission.command_id)
    try:
        result = await client.wait_result(admission.command_id)
    except asyncio.CancelledError:
        finished(
            "submit_configuration",
            admission.command_id,
            "unconfirmed",
            "Connection ended before configuration completion was confirmed; this proposal will not be replayed.",
        )
        raise
    except ClientError as exc:
        finished("submit_configuration", admission.command_id, "unconfirmed", str(exc))
        return False
    if result.needs_input:
        finished(
            "submit_configuration",
            admission.command_id,
            "needs_input",
            "Controller requires operator input.",
        )
        return False
    if not result.complete or result.succeeded is not True:
        finished(
            "submit_configuration",
            admission.command_id,
            "failed" if result.succeeded is False else "unconfirmed",
            result.failure or "Configuration acceptance was not confirmed.",
        )
        return False

    encoded_proposal = proposal.SerializeToString(deterministic=True)

    def exact_version(snapshot: pb.Snapshot) -> bool:
        if (
            snapshot.controller_generation != controller_generation
            or not snapshot.HasField("configuration_values")
            or snapshot.configuration_values.revision != snapshot.configuration.revision
            or snapshot.configuration.revision not in (base_revision, base_revision + 1)
        ):
            return False
        return (
            snapshot.configuration_values.current.SerializeToString(deterministic=True)
            == encoded_proposal
        )

    try:
        state = await asyncio.wait_for(
            client._wait(exact_version),
            client.rpc_timeout_s,
        )
    except asyncio.CancelledError:
        finished(
            "submit_configuration",
            admission.command_id,
            "unconfirmed",
            "Connection ended before the accepted configuration version was synchronized; this proposal will not be replayed.",
        )
        raise
    except (TimeoutError, ClientError) as exc:
        finished(
            "submit_configuration",
            admission.command_id,
            "unconfirmed",
            f"Update completed but the accepted configuration version was not synchronized: {exc}",
        )
        return False
    accepted_revision = state.configuration.revision
    accepted(accepted_revision)
    finished(
        "submit_configuration",
        admission.command_id,
        "completed",
        "Accepted authoritative configuration version.",
    )
    return True
