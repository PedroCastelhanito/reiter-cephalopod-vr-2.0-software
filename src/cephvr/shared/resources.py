"""E08 generation-scoped, append-only native cleanup obligation catalogue.

The owning process must await an accepted ReportHeartbeat receipt before creating
each newly declared resource. This local registry validates evidence; it does not
send that heartbeat, create a resource, or authorize work on its own.
"""

from __future__ import annotations

from collections.abc import Iterable

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4


class ResourceCatalogueError(ValueError):
    """A catalogue revision or cleanup claim is incomplete or inconsistent."""


def validate_cleanup_fence_update(
    previous: svc.RegisteredContext | None,
    current: svc.RegisteredContext,
    *,
    max_fences: int,
    max_bytes: int,
) -> None:
    """Validate append-only controller cleanup admissions on the existing context RPC."""
    if max_fences <= 0 or max_bytes <= 0:
        raise ValueError("positive cleanup fence bounds required")
    if not current.HasField("paired_spikeglx"):
        raise ResourceCatalogueError("paired SpikeGLX Setup fact is unknown")
    fences = current.cleanup_commands
    if (
        len(fences) > max_fences
        or sum(len(item.SerializeToString(deterministic=True)) for item in fences)
        > max_bytes
    ):
        raise ResourceCatalogueError("cleanup command fence capacity exceeded")
    allowed = {
        (item.backend_name, item.backend_generation)
        for item in current.required_participants
    }
    seen: set[str] = set()
    for fence in fences:
        try:
            require_uuid4(fence.operation.command_id)
        except ValueError as exc:
            raise ResourceCatalogueError("cleanup fence command ID is invalid") from exc
        if (
            (fence.target.role, fence.target.generation) not in allowed
            or not _matches_work(current.work, fence.work)
            or fence.operation.command_id in seen
        ):
            raise ResourceCatalogueError(
                "cleanup fence target/work is invalid or repeated"
            )
        seen.add(fence.operation.command_id)
    if previous is None:
        return
    if previous.work != current.work:
        return  # A new session has a new fence list and separate cleanup gate.
    old = tuple(previous.cleanup_commands)
    if tuple(fences[: len(old)]) != old:
        raise ResourceCatalogueError("cleanup command fences changed or shrank")
    if previous.required_participants != current.required_participants:
        raise ResourceCatalogueError("cleanup fence update changed participants")
    if (
        previous.HasField("paired_spikeglx")
        and previous.paired_spikeglx != current.paired_spikeglx
    ):
        raise ResourceCatalogueError("paired SpikeGLX Setup fact changed")
    if previous.prepared_functions and (
        previous.outputs != current.outputs
        or previous.cleanup_resources != current.cleanup_resources
        or previous.prepared_functions != current.prepared_functions
    ):
        raise ResourceCatalogueError("cleanup fence update changed frozen topology")


def cleanup_command_fenced(
    report: pb.CleanupReport,
    context: svc.RegisteredContext,
    *,
    supervisor_command: svc.BackendCommand | None = None,
) -> bool:
    """Match a Cleanup report to an accepted controller or issued supervisor command."""
    if any(
        fence.target == report.source
        and fence.work == report.work
        and fence.operation == report.operation
        for fence in context.cleanup_commands
    ):
        return True
    return (
        supervisor_command is not None
        and supervisor_command.issuer == context.supervisor
        and supervisor_command.target.backend_name == report.source.role
        and supervisor_command.target.backend_generation == report.source.generation
        and supervisor_command.work == report.work
        and supervisor_command.command_id == report.operation.command_id
    )


def _clone(item: pb.ResourceObligation) -> pb.ResourceObligation:
    return pb.ResourceObligation.FromString(item.SerializeToString(deterministic=True))


def _matches_work(expected: pb.WorkContext, actual: pb.WorkContext) -> bool:
    if expected.WhichOneof("work") == "session":
        if actual.WhichOneof("work") == "session":
            return actual.session == expected.session
        return (
            actual.WhichOneof("work") == "trial"
            and actual.trial.session == expected.session
            and actual.trial.trial_number > 0
            and _valid_uuid4(actual.trial.trial_id)
        )
    return actual == expected


def _valid_uuid4(value: str) -> bool:
    try:
        require_uuid4(value)
    except ValueError:
        return False
    return True


def _validate_items(
    items: Iterable[pb.ResourceObligation],
    allowed_owners: frozenset[tuple[str, str]],
) -> tuple[pb.ResourceObligation, ...]:
    seen: set[str] = set()
    result: list[pb.ResourceObligation] = []
    for item in items:
        owner = (item.owner.role, item.owner.generation)
        if owner not in allowed_owners or not item.resource or item.resource in seen:
            raise ResourceCatalogueError(
                "resource owner/key is unregistered or repeated"
            )
        if item.HasField("path") and not item.path:
            raise ResourceCatalogueError("cleanup resource path is empty")
        seen.add(item.resource)
        result.append(_clone(item))
    return tuple(result)


class ResourceObligationRegistry:
    """Receiver-side current catalogue for one backend generation and work context.

    ``accept_heartbeat`` must run before returning an accepted heartbeat receipt.
    Missing revision before initialization leaves catalogue state unknown; after
    initialization every heartbeat repeats the full catalogue so exact status
    forwarding can expose it. Revision zero with an empty list establishes
    known-zero obligations. Any later addition uses exactly the
    next revision and a full prefix-preserving catalogue. A duplicate revision is
    an idempotent retry only if its entire catalogue is byte-identical.
    """

    def __init__(
        self,
        source: pb.ProcessIdentity,
        work: pb.WorkContext,
        *,
        allowed_owners: frozenset[tuple[str, str]],
        max_resources: int,
        max_bytes: int,
    ) -> None:
        require_uuid4(source.generation)
        if not source.role or (source.role, source.generation) not in allowed_owners:
            raise ValueError("catalogue source is not an allowed owner")
        work_kind = work.WhichOneof("work")
        if work_kind is None or max_resources <= 0 or max_bytes <= 0:
            raise ValueError("catalogue work and positive bounds are required")
        session = work.session if work_kind == "session" else work.trial.session
        require_uuid4(session.controller_generation)
        require_uuid4(session.session_id)
        if work_kind == "trial":
            require_uuid4(work.trial.trial_id)
            if work.trial.trial_number <= 0:
                raise ValueError("trial catalogue work requires positive trial number")
        self.source = pb.ProcessIdentity.FromString(source.SerializeToString())
        self.work = pb.WorkContext.FromString(work.SerializeToString())
        self.allowed_owners = allowed_owners
        self.max_resources = max_resources
        self.max_bytes = max_bytes
        self._revision: int | None = None
        self._items: tuple[pb.ResourceObligation, ...] = ()
        self._sealed = False

    @property
    def revision(self) -> int | None:
        return self._revision

    @property
    def obligations(self) -> tuple[pb.ResourceObligation, ...]:
        return tuple(_clone(item) for item in self._items)

    def accept_heartbeat(self, report: pb.HeartbeatReport) -> int | None:
        if report.source != self.source or not _matches_work(self.work, report.work):
            raise ResourceCatalogueError("heartbeat source/work differs from catalogue")
        if not report.HasField("cleanup_resources_revision"):
            if report.cleanup_resources:
                raise ResourceCatalogueError("cleanup resources have no revision")
            if self._revision is not None:
                raise ResourceCatalogueError("initialized heartbeat omitted catalogue")
            return None
        revision = report.cleanup_resources_revision
        candidate = _validate_items(report.cleanup_resources, self.allowed_owners)
        if (
            len(candidate) > self.max_resources
            or sum(
                len(item.SerializeToString(deterministic=True)) for item in candidate
            )
            > self.max_bytes
        ):
            raise ResourceCatalogueError("cleanup catalogue capacity exceeded")
        if self._revision is None:
            if revision != 0 or candidate:
                raise ResourceCatalogueError(
                    "first catalogue must be revision-zero empty"
                )
        elif revision == self._revision:
            if candidate != self._items:
                raise ResourceCatalogueError("same revision changed cleanup catalogue")
            return self._revision
        elif self._sealed:
            raise ResourceCatalogueError("finalized cleanup catalogue cannot grow")
        elif revision != self._revision + 1:
            raise ResourceCatalogueError(
                "cleanup catalogue revision skipped or regressed"
            )
        elif candidate[: len(self._items)] != self._items or len(candidate) <= len(
            self._items
        ):
            raise ResourceCatalogueError(
                "cleanup catalogue shrank or changed an obligation"
            )
        self._items = candidate
        self._revision = revision
        return revision

    def verify_final(self, items: Iterable[pb.ResourceObligation]) -> None:
        """Check Ready/final RegisteredContext against the last acknowledged set."""
        if self._revision is None:
            raise ResourceCatalogueError(
                "cleanup catalogue was never explicitly registered"
            )
        candidate = _validate_items(items, self.allowed_owners)
        if candidate != self._items:
            raise ResourceCatalogueError(
                "final cleanup obligations differ from catalogue"
            )

    def seal_final(self, items: Iterable[pb.ResourceObligation]) -> None:
        """Check final registration, then forbid new resource obligations."""
        self.verify_final(items)
        self._sealed = True

    def verify_cleanup(
        self,
        report: pb.CleanupReport,
        *,
        cleanup_command_fenced: bool,
    ) -> None:
        """Require exact revision, releases and stopped admissions, including known zero."""
        try:
            require_uuid4(report.operation.command_id)
        except ValueError as exc:
            raise ResourceCatalogueError("cleanup command ID is invalid") from exc
        if (
            self._revision is None
            or report.source != self.source
            or not _matches_work(self.work, report.work)
            or not report.HasField("cleanup_resources_revision")
            or report.cleanup_resources_revision != self._revision
            or not report.trial_activity_stopped
            or report.verified_monotonic_ns <= 0
            or not cleanup_command_fenced
        ):
            raise ResourceCatalogueError(
                "cleanup revision, identity or fence is unverified"
            )
        observed = {item.resource: item for item in report.resources}
        if len(observed) != len(report.resources) or set(observed) != {
            item.resource for item in self._items
        }:
            raise ResourceCatalogueError("cleanup release set differs from catalogue")
        for obligation in self._items:
            release = observed[obligation.resource]
            if (
                not release.released
                or release.failure.code
                or release.failure.message
                or release.HasField("path") != obligation.HasField("path")
                or obligation.HasField("path")
                and release.path != obligation.path
            ):
                raise ResourceCatalogueError("cleanup release is unverified")
