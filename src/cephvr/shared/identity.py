"""Canonical E08 identities and exact registered context matching."""

from __future__ import annotations

import uuid
from typing import Protocol


class ProcessIdentityLike(Protocol):
    role: str
    generation: str


class SessionContextLike(Protocol):
    controller_generation: str
    session_id: str


class TrialContextLike(Protocol):
    session: SessionContextLike
    trial_id: str
    trial_number: int


class WorkContextLike(Protocol):
    session: SessionContextLike
    trial: TrialContextLike

    def WhichOneof(self, name: str) -> str | None: ...


def require_uuid4(value: str) -> str:
    """Require the exact lowercase, hyphenated UUIDv4 wire spelling."""
    if not isinstance(value, str):
        raise ValueError("identity must be a string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("invalid UUID") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("identity must be a canonical lowercase UUIDv4")
    return value


def require_registered_process(
    identity: ProcessIdentityLike, *, expected_role: str, expected_generation: str
) -> None:
    """Check claimed identity against a trusted registration, not just its syntax."""
    require_uuid4(identity.generation)
    require_uuid4(expected_generation)
    if not expected_role or identity.role != expected_role:
        raise ValueError("process role does not match registration")
    if identity.generation != expected_generation:
        raise ValueError("process generation does not match registration")


def require_session_context(
    context: SessionContextLike, *, controller_generation: str, session_id: str
) -> None:
    require_uuid4(context.controller_generation)
    require_uuid4(context.session_id)
    if context.controller_generation != require_uuid4(
        controller_generation
    ) or context.session_id != require_uuid4(session_id):
        raise ValueError("session context does not match registered work")


def require_trial_context(
    context: TrialContextLike,
    *,
    controller_generation: str,
    session_id: str,
    trial_id: str,
    trial_number: int,
) -> None:
    require_session_context(
        context.session,
        controller_generation=controller_generation,
        session_id=session_id,
    )
    require_uuid4(context.trial_id)
    if (
        context.trial_id != require_uuid4(trial_id)
        or context.trial_number != trial_number
    ):
        raise ValueError("trial context does not match registered work")
    if trial_number <= 0:
        raise ValueError("trial number must be positive")


def require_work_context(
    context: WorkContextLike,
    *,
    controller_generation: str,
    session_id: str | None = None,
    trial_id: str | None = None,
    trial_number: int | None = None,
) -> None:
    """Check Protobuf oneof presence and the exact registered work identity."""
    kind = context.WhichOneof("work")
    if session_id is None:
        if kind is not None or trial_id is not None or trial_number is not None:
            raise ValueError("work context was not expected")
        return
    if trial_id is None:
        if kind != "session" or trial_number is not None:
            raise ValueError("required session context is missing")
        require_session_context(
            context.session,
            controller_generation=controller_generation,
            session_id=session_id,
        )
        return
    if kind != "trial" or trial_number is None:
        raise ValueError("required trial context is missing")
    require_trial_context(
        context.trial,
        controller_generation=controller_generation,
        session_id=session_id,
        trial_id=trial_id,
        trial_number=trial_number,
    )
