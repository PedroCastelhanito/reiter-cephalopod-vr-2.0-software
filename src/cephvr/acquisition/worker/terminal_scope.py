"""Command-local E08 retention for terminal commands on finalized work."""

from __future__ import annotations

from google.protobuf.message import DecodeError

from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.shared.commands import CommandRecord

TERMINAL_COMMANDS = frozenset({"Cleanup", "Shutdown"})


def command_work_key(method: str, command_id: str, work_key: str) -> str:
    """Keep terminal receipts under their own command, never reopen old work."""
    return command_id if method in TERMINAL_COMMANDS else work_key


def terminal_target_matches(
    record: CommandRecord,
    command_id: str,
    target: acq.WorkerContext,
) -> bool:
    """Validate the exact original target hidden by terminal command-local scope."""
    request = _terminal_request(record)
    return bool(
        request is not None
        and record.command_id == command_id
        and record.work_key == command_id
        and request.command_id == command_id
        and request.target == target
    )


def terminal_evidence_scope(
    record: CommandRecord, source: acq.WorkerContext
) -> str | None:
    """Return command-local scope only for evidence from the exact terminal target."""
    request = _terminal_request(record)
    if request is None or record.work_key != record.command_id:
        return None
    if request.command_id != record.command_id or request.target != source:
        raise ValueError("terminal lifecycle evidence differs from retained target")
    return record.command_id


def terminal_target(record: CommandRecord) -> acq.WorkerContext | None:
    """Read an exact retained target only when this record is terminal-scoped."""
    request = _terminal_request(record)
    if request is None or record.work_key != record.command_id:
        return None
    target = acq.WorkerContext()
    target.CopyFrom(request.target)
    return target


def _terminal_request(record: CommandRecord) -> acq.WorkerCommand | None:
    name, separator, payload = record.canonical_request.partition(b"\0")
    if not separator or name.decode("ascii", errors="ignore") not in TERMINAL_COMMANDS:
        return None
    request = acq.WorkerCommand()
    try:
        request.ParseFromString(payload)
    except (DecodeError, ValueError):
        return None
    return request
