"""Controller-owned bounded incident retention and operator choices (E06).

Classification remains in shared.incidents; this owner commits current views only
once their original deadlines and serialized capacity have been checked.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.clock import require_int64_ns
from cephvr.shared.identity import require_uuid4
from cephvr.shared.incidents import Classification, IncidentEvidenceError, _same_session

_TERMINAL = {
    pb.RUNTIME_INCIDENT_DISPOSITION_RESOLVED,
    pb.RUNTIME_INCIDENT_DISPOSITION_SESSION_ENDED_UNANSWERED,
}


class IncidentCapacityError(RuntimeError):
    """A required incident/error cannot be retained without evicting active work."""


class StaleIncidentChoice(ValueError):
    """A prompt choice no longer matches its session, revision or allowed action."""


class IncidentRegistry:
    """Bounded controller-local current incidents; active scopes are never evicted."""

    def __init__(
        self,
        session: pb.SessionContext,
        *,
        max_incidents: int,
        max_error_ids: int,
        max_bytes: int,
    ) -> None:
        require_uuid4(session.controller_generation)
        require_uuid4(session.session_id)
        if max_incidents <= 0 or max_error_ids <= 0 or max_bytes <= 0:
            raise ValueError("incident bounds must be positive")
        self.session = pb.SessionContext.FromString(session.SerializeToString())
        self.max_incidents = max_incidents
        self.max_error_ids = max_error_ids
        self.max_bytes = max_bytes
        self._records: dict[str, pb.RuntimeIncident] = {}
        self._episodes: dict[tuple[str, str, str], str] = {}
        self._errors: dict[str, bytes] = {}
        self._deadlines: dict[tuple[str, str, str], int] = {}
        self._finalized = False
        self.retained_truncated = False

    def observe(
        self,
        error: pb.ErrorReport,
        classification: Classification,
        *,
        episode_id: str | None = None,
        consequence: str,
    ) -> pb.RuntimeIncident:
        """Coalesce matching incidents without evicting active work or weakening severity."""
        if self._finalized:
            raise IncidentEvidenceError(
                "finalized session cannot gain incident evidence"
            )
        episode_id = (
            episode_id
            if episode_id is not None
            else (
                error.incident_episode_id
                if error.HasField("incident_episode_id")
                else error.error_id
            )
        )
        require_uuid4(episode_id)
        require_uuid4(error.error_id)
        require_int64_ns(classification.original_deadline_ns)
        if not _same_session(error.work, self.session) or not consequence:
            raise IncidentEvidenceError("incident work or consequence is missing")
        encoded = error.SerializeToString(deterministic=True)
        previous = self._errors.get(error.error_id)
        if previous is not None and previous != encoded:
            raise IncidentEvidenceError("error ID was reused with changed evidence")
        episode = (error.source.role, error.source.generation, episode_id)
        old_deadline = self._deadlines.get(episode)
        if (
            old_deadline is not None
            and old_deadline != classification.original_deadline_ns
        ):
            raise IncidentEvidenceError("incident recovery deadline changed")
        records = dict(self._records)
        episodes = dict(self._episodes)
        errors = dict(self._errors)
        deadlines = dict(self._deadlines)
        truncated = self.retained_truncated
        incident_id = episodes.get(episode)
        if incident_id is None:
            if previous is not None:
                raise IncidentEvidenceError("error ID was moved to a new episode")
            if len(records) >= self.max_incidents:
                evict = next(
                    (
                        key
                        for key, value in records.items()
                        if value.disposition in _TERMINAL
                    ),
                    None,
                )
                if evict is None:
                    raise IncidentCapacityError("active incident capacity exhausted")
                removed = records.pop(evict)
                for old_error in removed.error_ids:
                    errors.pop(old_error, None)
                episodes = {
                    key: value for key, value in episodes.items() if value != evict
                }
                deadlines = {
                    key: value for key, value in deadlines.items() if key in episodes
                }
                truncated = True
            incident_id = str(uuid4())
            episodes[episode] = incident_id
            deadlines[episode] = classification.original_deadline_ns
            record = pb.RuntimeIncident(
                incident_id=incident_id,
                revision=1,
                work=error.work,
                error_ids=[error.error_id],
                affected_resources=classification.affected_resources,
                consequence=consequence,
                disposition=(
                    pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
                    if classification.status == "blocking"
                    else pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR
                ),
                first_observed_monotonic_ns=error.occurred_monotonic_ns,
                last_observed_monotonic_ns=error.occurred_monotonic_ns,
                occurrence_count=1,
                continuation_available=classification.continuation_available,
            )
            records[incident_id] = record
        else:
            record = pb.RuntimeIncident.FromString(
                records[incident_id].SerializeToString()
            )
            cumulative_scope = tuple(
                dict.fromkeys(
                    (*record.affected_resources, *classification.affected_resources)
                )
            )
            material = (
                tuple(record.affected_resources) != cumulative_scope
                or record.consequence != consequence
                or record.continuation_available
                != classification.continuation_available
                or classification.status == "blocking"
                and record.disposition != pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
            )
            if previous is None:
                if len(record.error_ids) >= self.max_error_ids:
                    raise IncidentCapacityError("incident error ID capacity exhausted")
                record.error_ids.append(error.error_id)
                record.occurrence_count += 1
                record.last_observed_monotonic_ns = max(
                    record.last_observed_monotonic_ns, error.occurred_monotonic_ns
                )
                record.revision += 1
            if material:
                record.affected_resources[:] = cumulative_scope
                record.consequence = consequence
                # Acknowledgement only covers the previous informational view.
                # Material new blocking evidence must be shown again.
                if classification.status == "blocking":
                    record.acknowledged = False
                if record.disposition in (
                    pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP,
                    pb.RUNTIME_INCIDENT_DISPOSITION_ABORT_SELECTED,
                ):
                    # New facts cannot undo a committed stop or Abort decision.
                    record.continuation_available = False
                else:
                    record.continuation_available = (
                        classification.continuation_available
                    )
                    record.disposition = (
                        pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
                        if classification.status == "blocking"
                        else pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR
                    )
                if previous is not None:
                    record.revision += 1
            records[incident_id] = record
        errors[error.error_id] = encoded
        used_bytes = sum(len(item) for item in errors.values()) + sum(
            len(item.SerializeToString(deterministic=True)) for item in records.values()
        )
        if used_bytes > self.max_bytes:
            raise IncidentCapacityError("incident serialized byte capacity exhausted")
        self._records = records
        self._episodes = episodes
        self._errors = errors
        self._deadlines = deadlines
        self.retained_truncated = truncated
        return pb.RuntimeIncident.FromString(record.SerializeToString())

    def choose(
        self,
        incident_id: str,
        expected_revision: int,
        choice: Literal["continue_session", "abort_session", "acknowledge"],
        *,
        session_active: bool,
    ) -> pb.RuntimeIncident:
        require_uuid4(incident_id)
        existing = self._records.get(incident_id)
        if (
            existing is None
            or not session_active
            and choice != "acknowledge"
            or existing.revision != expected_revision
            or choice not in ("continue_session", "abort_session", "acknowledge")
            or choice == "acknowledge"
            and existing.disposition != pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
            or choice == "acknowledge"
            and existing.acknowledged
            or choice != "acknowledge"
            and existing.disposition
            != pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR
            or choice == "continue_session"
            and not existing.continuation_available
        ):
            raise StaleIncidentChoice("incident choice is stale or unavailable")
        record = pb.RuntimeIncident.FromString(existing.SerializeToString())
        if choice == "acknowledge":
            record.acknowledged = True
        else:
            record.disposition = (
                pb.RUNTIME_INCIDENT_DISPOSITION_CONTINUE_SELECTED
                if choice == "continue_session"
                else pb.RUNTIME_INCIDENT_DISPOSITION_ABORT_SELECTED
            )
        record.revision += 1
        current_bytes = sum(len(item) for item in self._errors.values()) + sum(
            len(item.SerializeToString(deterministic=True))
            for key, item in self._records.items()
            if key != incident_id
        )
        if (
            current_bytes + len(record.SerializeToString(deterministic=True))
            > self.max_bytes
        ):
            raise IncidentCapacityError(
                "incident choice exceeds serialized byte capacity"
            )
        self._records[incident_id] = record
        return pb.RuntimeIncident.FromString(record.SerializeToString())

    def end_session(self) -> None:
        records = {
            key: pb.RuntimeIncident.FromString(value.SerializeToString())
            for key, value in self._records.items()
        }
        for record in records.values():
            if record.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR:
                record.disposition = (
                    pb.RUNTIME_INCIDENT_DISPOSITION_SESSION_ENDED_UNANSWERED
                )
                record.continuation_available = False
                record.revision += 1
        used_bytes = sum(len(item) for item in self._errors.values()) + sum(
            len(item.SerializeToString(deterministic=True)) for item in records.values()
        )
        if used_bytes > self.max_bytes:
            raise IncidentCapacityError(
                "terminal incident view exceeds serialized byte capacity"
            )
        self._records = records
        self._finalized = True

    def resolve_after_recovery(
        self,
        incident_id: str,
        expected_revision: int,
        *,
        session_active: bool,
        recovered_monotonic_ns: int,
    ) -> pb.RuntimeIncident:
        """Resolve a recovered incident without undoing an Abort or automatic stop."""
        require_uuid4(incident_id)
        require_int64_ns(recovered_monotonic_ns)
        existing = self._records.get(incident_id)
        if (
            self._finalized
            or not session_active
            or existing is None
            or existing.revision != expected_revision
            or existing.disposition
            not in (
                pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR,
                pb.RUNTIME_INCIDENT_DISPOSITION_CONTINUE_SELECTED,
            )
        ):
            raise StaleIncidentChoice(
                "incident recovery evidence is stale or unavailable"
            )
        record = pb.RuntimeIncident.FromString(existing.SerializeToString())
        record.disposition = pb.RUNTIME_INCIDENT_DISPOSITION_RESOLVED
        record.continuation_available = False
        record.last_observed_monotonic_ns = max(
            record.last_observed_monotonic_ns, recovered_monotonic_ns
        )
        record.revision += 1
        current_bytes = sum(len(item) for item in self._errors.values()) + sum(
            len(item.SerializeToString(deterministic=True))
            for key, item in self._records.items()
            if key != incident_id
        )
        if (
            current_bytes + len(record.SerializeToString(deterministic=True))
            > self.max_bytes
        ):
            raise IncidentCapacityError(
                "incident recovery exceeds serialized byte capacity"
            )
        self._records[incident_id] = record
        return pb.RuntimeIncident.FromString(record.SerializeToString())

    def snapshot(self) -> tuple[pb.RuntimeIncident, ...]:
        return tuple(
            pb.RuntimeIncident.FromString(record.SerializeToString())
            for record in self._records.values()
        )
