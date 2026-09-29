"""E08 partial-Setup catalogue and cleanup evidence invariants."""

from __future__ import annotations

from uuid import uuid4

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.resources import (
    ResourceCatalogueError,
    ResourceObligationRegistry,
    cleanup_command_fenced,
    validate_cleanup_fence_update,
)


def _fixture(
    *, max_resources: int = 2
) -> tuple[ResourceObligationRegistry, pb.ProcessIdentity, pb.WorkContext]:
    source = pb.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    work = pb.WorkContext(
        session=pb.SessionContext(
            controller_generation=str(uuid4()), session_id=str(uuid4())
        )
    )
    registry = ResourceObligationRegistry(
        source,
        work,
        allowed_owners=frozenset({(source.role, source.generation)}),
        max_resources=max_resources,
        max_bytes=1024,
    )
    return registry, source, work


def _heartbeat(
    source: pb.ProcessIdentity,
    work: pb.WorkContext,
    revision: int | None,
    resources: tuple[pb.ResourceObligation, ...] = (),
) -> pb.HeartbeatReport:
    report = pb.HeartbeatReport(source=source, work=work, cleanup_resources=resources)
    if revision is not None:
        report.cleanup_resources_revision = revision
    return report


def _obligation(source: pb.ProcessIdentity, name: str) -> pb.ResourceObligation:
    return pb.ResourceObligation(owner=source, resource=name, path=f"/tmp/{name}")


def _cleanup(
    source: pb.ProcessIdentity,
    work: pb.WorkContext,
    revision: int | None,
    resources: tuple[pb.ResourceRelease, ...] = (),
) -> pb.CleanupReport:
    report = pb.CleanupReport(
        source=source,
        work=work,
        operation=pb.OperationContext(command_id=str(uuid4())),
        verified_monotonic_ns=100,
        trial_activity_stopped=True,
        resources=resources,
    )
    if revision is not None:
        report.cleanup_resources_revision = revision
    return report


def test_unknown_empty_cannot_clear_but_explicit_zero_with_fence_can() -> None:
    registry, source, work = _fixture()
    unknown = _cleanup(source, work, None)
    with pytest.raises(ResourceCatalogueError):
        registry.verify_cleanup(unknown, cleanup_command_fenced=True)
    registry.accept_heartbeat(_heartbeat(source, work, None))
    with pytest.raises(ResourceCatalogueError):
        registry.verify_final(())
    registry.accept_heartbeat(_heartbeat(source, work, 0))
    with pytest.raises(ResourceCatalogueError, match="omitted"):
        registry.accept_heartbeat(_heartbeat(source, work, None))
    with pytest.raises(ResourceCatalogueError):
        registry.verify_cleanup(_cleanup(source, work, 0), cleanup_command_fenced=False)
    registry.verify_final(())
    registry.verify_cleanup(_cleanup(source, work, 0), cleanup_command_fenced=True)


def test_append_only_revisions_and_exact_final_catalogue() -> None:
    registry, source, work = _fixture(max_resources=3)
    camera = _obligation(source, "camera")
    writer = _obligation(source, "writer")
    with pytest.raises(ResourceCatalogueError):
        registry.accept_heartbeat(_heartbeat(source, work, 1, (camera,)))
    registry.accept_heartbeat(_heartbeat(source, work, 0))
    registry.accept_heartbeat(_heartbeat(source, work, 1, (camera,)))
    registry.accept_heartbeat(_heartbeat(source, work, 1, (camera,)))
    with pytest.raises(ResourceCatalogueError):
        registry.accept_heartbeat(_heartbeat(source, work, 1, (writer,)))
    with pytest.raises(ResourceCatalogueError):
        registry.accept_heartbeat(_heartbeat(source, work, 2))
    with pytest.raises(ResourceCatalogueError):
        registry.accept_heartbeat(_heartbeat(source, work, 3, (camera, writer)))
    assert registry.revision == 1
    registry.accept_heartbeat(_heartbeat(source, work, 2, (camera, writer)))
    registry.verify_final((camera, writer))
    with pytest.raises(ResourceCatalogueError):
        registry.verify_final((camera,))
    registry.seal_final((camera, writer))
    registry.accept_heartbeat(_heartbeat(source, work, 2, (camera, writer)))
    with pytest.raises(ResourceCatalogueError, match="finalized"):
        registry.accept_heartbeat(
            _heartbeat(source, work, 3, (camera, writer, _obligation(source, "third")))
        )


def test_cleanup_must_match_last_revision_and_exact_releases() -> None:
    registry, source, work = _fixture()
    item = _obligation(source, "camera")
    registry.accept_heartbeat(_heartbeat(source, work, 0))
    registry.accept_heartbeat(_heartbeat(source, work, 1, (item,)))
    release = pb.ResourceRelease(resource="camera", path="/tmp/camera", released=True)
    with pytest.raises(ResourceCatalogueError):
        registry.verify_cleanup(
            _cleanup(source, work, 0, (release,)), cleanup_command_fenced=True
        )
    with pytest.raises(ResourceCatalogueError):
        registry.verify_cleanup(_cleanup(source, work, 1), cleanup_command_fenced=True)
    wrong = pb.ResourceRelease(resource="camera", path="/tmp/other", released=True)
    with pytest.raises(ResourceCatalogueError):
        registry.verify_cleanup(
            _cleanup(source, work, 1, (wrong,)), cleanup_command_fenced=True
        )
    registry.verify_cleanup(
        _cleanup(source, work, 1, (release,)), cleanup_command_fenced=True
    )


def test_capacity_and_wrong_owner_fail_without_mutating_revision() -> None:
    registry, source, work = _fixture()
    registry.accept_heartbeat(_heartbeat(source, work, 0))
    other = pb.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    with pytest.raises(ResourceCatalogueError):
        registry.accept_heartbeat(
            _heartbeat(source, work, 1, (_obligation(other, "camera"),))
        )
    with pytest.raises(ResourceCatalogueError):
        registry.accept_heartbeat(
            _heartbeat(
                source,
                work,
                1,
                tuple(_obligation(source, str(index)) for index in range(3)),
            )
        )
    assert registry.revision == 0


def test_cleanup_fences_are_exact_append_only_registered_commands() -> None:
    _registry, source, work = _fixture()
    supervisor = pb.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    first = svc.RegisteredContext(
        supervisor=supervisor,
        work=work,
        paired_spikeglx=False,
        required_participants=[
            pb.BackendContext(
                backend_name=source.role, backend_generation=source.generation
            )
        ],
    )
    command_id = str(uuid4())
    updated = svc.RegisteredContext.FromString(first.SerializeToString())
    updated.cleanup_commands.add(
        target=source, work=work, operation=pb.OperationContext(command_id=command_id)
    )
    validate_cleanup_fence_update(first, updated, max_fences=2, max_bytes=1024)
    report = _cleanup(source, work, 0)
    report.operation.command_id = command_id
    assert cleanup_command_fenced(report, updated)
    assert not cleanup_command_fenced(report, first)
    with pytest.raises(ResourceCatalogueError, match="changed or shrank"):
        validate_cleanup_fence_update(updated, first, max_fences=2, max_bytes=1024)
    changed = svc.RegisteredContext.FromString(updated.SerializeToString())
    changed.cleanup_commands[0].operation.command_id = str(uuid4())
    with pytest.raises(ResourceCatalogueError, match="changed or shrank"):
        validate_cleanup_fence_update(updated, changed, max_fences=2, max_bytes=1024)
    changed = svc.RegisteredContext.FromString(updated.SerializeToString())
    changed.paired_spikeglx = True
    with pytest.raises(
        ResourceCatalogueError, match="paired SpikeGLX Setup fact changed"
    ):
        validate_cleanup_fence_update(updated, changed, max_fences=2, max_bytes=1024)
    finalized = svc.RegisteredContext.FromString(updated.SerializeToString())
    finalized.prepared_functions.add(resource_id="camera")
    illegal = svc.RegisteredContext.FromString(finalized.SerializeToString())
    illegal.outputs.add(output_key="unexpected")
    with pytest.raises(ResourceCatalogueError, match="frozen topology"):
        validate_cleanup_fence_update(finalized, illegal, max_fences=2, max_bytes=1024)
    other = pb.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    report.source.CopyFrom(other)
    assert not cleanup_command_fenced(report, updated)


def test_supervisor_issued_cleanup_fence_requires_exact_command() -> None:
    _registry, source, work = _fixture()
    supervisor = pb.ProcessIdentity(role="supervisor", generation=str(uuid4()))
    context = svc.RegisteredContext(supervisor=supervisor, work=work)
    report = _cleanup(source, work, 0)
    command = svc.BackendCommand(
        command_id=report.operation.command_id,
        issuer=supervisor,
        target=pb.BackendContext(
            backend_name=source.role, backend_generation=source.generation
        ),
        work=work,
    )
    assert cleanup_command_fenced(report, context, supervisor_command=command)
    command.command_id = str(uuid4())
    assert not cleanup_command_fenced(report, context, supervisor_command=command)
