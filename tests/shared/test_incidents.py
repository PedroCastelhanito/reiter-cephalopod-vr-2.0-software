"""E06 proof never turns an unverified data fault into a Continue decision."""

from __future__ import annotations

import uuid

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.incident.registry import (
    IncidentCapacityError,
    IncidentRegistry,
    StaleIncidentChoice,
)
from cephvr.shared.incidents import (
    Classification,
    IncidentEvidenceError,
    IncidentTopology,
    IsolationProof,
    classify_incident,
    validate_registered_cleanup,
)


def _id() -> str:
    return str(uuid.uuid4())


def _registered() -> svc.RegisteredContext:
    controller = pb.ProcessIdentity(role="controller", generation=_id())
    supervisor = pb.ProcessIdentity(role="supervisor", generation=_id())
    vr = pb.BackendContext(backend_name="vr", backend_generation=_id())
    acquisition = pb.BackendContext(
        backend_name="acquisition", backend_generation=_id()
    )
    session = pb.SessionContext(
        controller_generation=controller.generation, session_id=_id()
    )
    context = svc.RegisteredContext(
        controller=controller,
        supervisor=supervisor,
        work=pb.WorkContext(session=session),
        required_participants=[vr, acquisition],
    )
    context.outputs.add(
        backend=acquisition,
        output_key="camera.mp4",
        output_tag="behavioral_cam",
        extension="mp4",
        trial=pb.TrialContext(session=session, trial_id=_id(), trial_number=1),
    )
    context.prepared_functions.add(
        resource_id="vr.presentation",
        owner=pb.ProcessIdentity(role="vr", generation=vr.backend_generation),
        affected_closure_resource_ids=["vr.presentation"],
        essential_to_stimulus_control=True,
        feedback_hold_required_on_loss=False,
        bounded_uncertainty_supported=False,
        lifecycle_sources=["renderer"],
    )
    context.prepared_functions.add(
        resource_id="camera.mp4",
        owner=pb.ProcessIdentity(
            role="acquisition", generation=acquisition.backend_generation
        ),
        affected_closure_resource_ids=["camera.mp4"],
        essential_to_stimulus_control=False,
        feedback_hold_required_on_loss=False,
        bounded_uncertainty_supported=False,
    )
    return context


def _error(context: svc.RegisteredContext) -> pb.ErrorReport:
    acquisition = next(
        item
        for item in context.required_participants
        if item.backend_name == "acquisition"
    )
    return pb.ErrorReport(
        error_id=_id(),
        source=pb.ProcessIdentity(
            role="acquisition", generation=acquisition.backend_generation
        ),
        work=context.work,
        occurred_monotonic_ns=100,
        failure=pb.Failure(code="ENCODER_FAILED", message="writer stopped"),
        isolation=pb.FaultIsolationEvidence(
            affected_resource_ids=["camera.mp4"],
            fenced_resource_ids=["camera.mp4"],
            leases_released_or_quarantined=True,
            verified_monotonic_ns=105,
        ),
    )


def _proof(context: svc.RegisteredContext, *, observed: int = 110) -> IsolationProof:
    vr = next(
        item for item in context.required_participants if item.backend_name == "vr"
    )
    identity = pb.ProcessIdentity(role="vr", generation=vr.backend_generation)
    heartbeat = pb.HeartbeatReport(
        source=identity,
        work=context.work,
        sent_monotonic_ns=observed,
        continuing_functions=[
            pb.ContinuingFunctionEvidence(
                resource_id="vr.presentation",
                functioning=True,
                schedule_valid=True,
                host_clock_valid=True,
                control_path_valid=True,
                observed_monotonic_ns=observed,
            )
        ],
    )
    return IsolationProof(
        {(identity.role, identity.generation): heartbeat},
        controller_authority_valid=True,
        supervisor_authority_valid=True,
        bounded_accounting=True,
    )


def _classify(
    error: pb.ErrorReport,
    topology: IncidentTopology,
    proof: IsolationProof | None,
    *,
    now: int = 120,
    deadline: int = 200,
) -> Classification:
    return classify_incident(
        error,
        topology,
        proof,
        now_ns=now,
        original_deadline_ns=deadline,
        max_evidence_age_ns=50,
    )


def test_exact_isolated_camera_fault_can_continue_with_current_vr_evidence() -> None:
    context = _registered()
    topology = IncidentTopology.from_registered(context)
    result = _classify(_error(context), topology, _proof(context))
    assert result.status == "continuable"
    assert result.affected_resources == ("camera.mp4",)


def test_lifecycle_scope_requires_exact_vr_and_camera_worker_ancestry() -> None:
    context = _registered()
    context.prepared_functions[0].ClearField("lifecycle_sources")
    with pytest.raises(IncidentEvidenceError, match="VR renderer"):
        IncidentTopology.from_registered(context)

    context.prepared_functions[0].lifecycle_sources.append("renderer")
    camera = context.prepared_functions[1]
    camera.lifecycle_sources.append("behavioral")
    worker = pb.ProcessIdentity(role="acquisition-camera", generation=_id())
    camera.owner.CopyFrom(worker)
    camera.authorized_reporters.add().CopyFrom(worker)
    workers = frozenset({(worker.role, worker.generation)})
    with pytest.raises(IncidentEvidenceError, match="ancestry"):
        IncidentTopology.from_registered(context, registered_workers=workers)
    topology = IncidentTopology.from_registered(
        context,
        registered_workers=workers,
        worker_backend={(worker.role, worker.generation): "acquisition"},
    )
    assert topology.functions["camera.mp4"].lifecycle_sources == ["behavioral"]
    camera.authorized_reporters[0].generation = _id()
    with pytest.raises(IncidentEvidenceError, match="reporter"):
        IncidentTopology.from_registered(
            context,
            registered_workers=workers,
            worker_backend={(worker.role, worker.generation): "acquisition"},
        )


def test_missing_or_stale_proof_never_extends_original_recovery_deadline() -> None:
    context = _registered()
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    assert _classify(error, topology, None).status == "pending"
    assert _classify(error, topology, None, now=201).status == "blocking"
    assert _classify(error, topology, _proof(context, observed=99)).status == "pending"
    assert (
        _classify(error, topology, _proof(context, observed=99), now=201).status
        == "blocking"
    )


def test_code_and_source_role_do_not_override_prepared_loss_closure() -> None:
    context = _registered()
    camera = next(
        item for item in context.prepared_functions if item.resource_id == "camera.mp4"
    )
    camera.affected_closure_resource_ids.append("vr.presentation")
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    assert _classify(error, topology, _proof(context)).status == "blocking"
    camera.affected_closure_resource_ids.pop()
    topology = IncidentTopology.from_registered(context)
    error.source.generation = _id()
    assert _classify(error, topology, _proof(context)).status == "blocking"


def test_unsafe_lease_or_missing_feedback_hold_does_not_continue() -> None:
    context = _registered()
    camera = next(
        item for item in context.prepared_functions if item.resource_id == "camera.mp4"
    )
    camera.feedback_hold_required_on_loss = True
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    assert _classify(error, topology, _proof(context)).status == "pending"
    error.isolation.feedback_hold_resource_ids.append("camera.mp4")
    error.isolation.feedback_hold_active = True
    error.isolation.leases_released_or_quarantined = False
    assert _classify(error, topology, _proof(context)).status == "blocking"


def test_downstream_feedback_is_discharged_by_exact_hold_scope() -> None:
    context = _registered()
    camera = next(
        item for item in context.prepared_functions if item.resource_id == "camera.mp4"
    )
    vr = next(
        item for item in context.required_participants if item.backend_name == "vr"
    )
    camera.affected_closure_resource_ids.append("vr.feedback")
    context.prepared_functions.add(
        resource_id="vr.feedback",
        owner=pb.ProcessIdentity(role="vr", generation=vr.backend_generation),
        affected_closure_resource_ids=["vr.feedback"],
        essential_to_stimulus_control=False,
        feedback_hold_required_on_loss=True,
        bounded_uncertainty_supported=False,
    )
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    assert _classify(error, topology, _proof(context)).status == "pending"
    error.isolation.feedback_hold_resource_ids.append("vr.feedback")
    error.isolation.feedback_hold_active = True
    assert _classify(error, topology, _proof(context)).status == "continuable"


def test_missing_output_function_declaration_rejects_topology() -> None:
    context = _registered()
    del context.prepared_functions[1]
    with pytest.raises(IncidentEvidenceError, match="reserved output"):
        IncidentTopology.from_registered(context)


def test_registered_native_cleanup_must_match_exact_ready_set() -> None:
    context = _registered()
    vr = next(
        item for item in context.required_participants if item.backend_name == "vr"
    )
    acquisition = next(
        item
        for item in context.required_participants
        if item.backend_name == "acquisition"
    )
    vr_obligation = pb.ResourceObligation(
        owner=pb.ProcessIdentity(role="vr", generation=vr.backend_generation),
        resource="display-window",
    )
    camera_obligation = pb.ResourceObligation(
        owner=pb.ProcessIdentity(
            role="acquisition", generation=acquisition.backend_generation
        ),
        resource="camera-handle",
        path="/dev/camera1",
    )
    context.cleanup_resources.extend([vr_obligation, camera_obligation])
    ready = {
        "vr": pb.ReadyReport(
            context=pb.ReportContext(backend=vr, work=context.work),
            required_checks_passed=True,
            cleanup_resources=[vr_obligation],
        ),
        "acquisition": pb.ReadyReport(
            context=pb.ReportContext(backend=acquisition, work=context.work),
            required_checks_passed=True,
            cleanup_resources=[camera_obligation],
        ),
    }
    validate_registered_cleanup(context, ready)
    context.cleanup_resources.pop()
    with pytest.raises(IncidentEvidenceError, match="differ from Ready"):
        validate_registered_cleanup(context, ready)
    context.cleanup_resources.append(camera_obligation)
    ready["vr"].cleanup_resources.clear()
    with pytest.raises(IncidentEvidenceError, match="empty cleanup"):
        validate_registered_cleanup(context, ready)


def test_unprepared_trial_and_absent_safety_fact_do_not_continue() -> None:
    context = _registered()
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    error.work.trial.CopyFrom(
        pb.TrialContext(session=context.work.session, trial_id=_id(), trial_number=1)
    )
    assert _classify(error, topology, _proof(context)).status == "blocking"
    error.work.CopyFrom(context.work)
    error.isolation.ClearField("leases_released_or_quarantined")
    assert _classify(error, topology, _proof(context)).status == "pending"


def test_registry_retains_active_scope_and_rejects_stale_continue() -> None:
    context = _registered()
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    classification = _classify(error, topology, _proof(context))
    registry = IncidentRegistry(
        context.work.session, max_incidents=1, max_error_ids=2, max_bytes=4096
    )
    episode = _id()
    first = registry.observe(
        error, classification, episode_id=episode, consequence="camera frames missing"
    )
    retry = registry.observe(
        error, classification, episode_id=episode, consequence="camera frames missing"
    )
    assert retry.incident_id == first.incident_id
    assert retry.revision == first.revision
    assert retry.occurrence_count == 1
    second_error = pb.ErrorReport.FromString(error.SerializeToString())
    second_error.error_id = _id()
    with pytest.raises(IncidentCapacityError):
        registry.observe(
            second_error,
            classification,
            episode_id=_id(),
            consequence="another active episode",
        )
    selected = registry.choose(
        first.incident_id, first.revision, "continue_session", session_active=True
    )
    assert selected.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_CONTINUE_SELECTED
    with pytest.raises(StaleIncidentChoice):
        registry.choose(
            first.incident_id, first.revision, "continue_session", session_active=True
        )
    error.error_id = _id()
    escalated = registry.observe(
        error,
        classification,
        episode_id=episode,
        consequence="camera and frame log unconfirmed",
    )
    assert escalated.incident_id == first.incident_id
    assert escalated.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_AWAITING_OPERATOR
    assert escalated.revision > selected.revision
    registry.end_session()
    terminal = registry.snapshot()[0]
    assert (
        terminal.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_SESSION_ENDED_UNANSWERED
    )
    with pytest.raises(StaleIncidentChoice):
        registry.choose(
            terminal.incident_id,
            terminal.revision,
            "continue_session",
            session_active=False,
        )


def test_blocking_incident_acknowledgement_never_reopens_continue() -> None:
    context = _registered()
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    error.incident_episode_id = _id()
    error.isolation.leases_released_or_quarantined = False
    registry = IncidentRegistry(
        context.work.session, max_incidents=1, max_error_ids=3, max_bytes=4096
    )
    blocking = _classify(error, topology, _proof(context))
    stopped = registry.observe(error, blocking, consequence="unsafe lease")
    assert stopped.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
    with pytest.raises(StaleIncidentChoice):
        registry.choose(
            stopped.incident_id,
            stopped.revision,
            "continue_session",
            session_active=True,
        )
    acknowledged = registry.choose(
        stopped.incident_id, stopped.revision, "acknowledge", session_active=False
    )
    assert acknowledged.acknowledged
    assert acknowledged.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
    error.error_id = _id()
    error.isolation.leases_released_or_quarantined = True
    later = registry.observe(
        error,
        _classify(error, topology, _proof(context)),
        consequence="later safe lease evidence",
    )
    assert later.incident_id == stopped.incident_id
    assert later.disposition == pb.RUNTIME_INCIDENT_DISPOSITION_AUTOMATIC_STOP
    assert not later.continuation_available
    error.error_id = _id()
    error.isolation.leases_released_or_quarantined = False
    reopened = registry.observe(
        error,
        _classify(error, topology, _proof(context)),
        consequence="new unsafe consequence",
    )
    assert not reopened.acknowledged


def test_registry_preserves_cumulative_scope_and_original_deadline() -> None:
    context = _registered()
    acquisition = next(
        item
        for item in context.required_participants
        if item.backend_name == "acquisition"
    )
    context.prepared_functions.add(
        resource_id="camera.frames",
        owner=pb.ProcessIdentity(
            role="acquisition", generation=acquisition.backend_generation
        ),
        affected_closure_resource_ids=["camera.frames"],
        essential_to_stimulus_control=False,
        feedback_hold_required_on_loss=False,
        bounded_uncertainty_supported=False,
    )
    topology = IncidentTopology.from_registered(context)
    first_error = _error(context)
    first_error.incident_episode_id = _id()
    registry = IncidentRegistry(
        context.work.session, max_incidents=2, max_error_ids=2, max_bytes=4096
    )
    first = registry.observe(
        first_error,
        _classify(first_error, topology, _proof(context)),
        consequence="video lost",
    )
    second_error = _error(context)
    second_error.incident_episode_id = first_error.incident_episode_id
    second_error.isolation.affected_resource_ids[:] = ["camera.frames"]
    second_error.isolation.fenced_resource_ids[:] = ["camera.frames"]
    second = registry.observe(
        second_error,
        _classify(second_error, topology, _proof(context)),
        consequence="video and frame log lost",
    )
    assert second.incident_id == first.incident_id
    assert set(second.affected_resources) == {"camera.mp4", "camera.frames"}
    third_error = _error(context)
    third_error.incident_episode_id = first_error.incident_episode_id
    with pytest.raises(IncidentEvidenceError, match="deadline changed"):
        registry.observe(
            third_error,
            _classify(third_error, topology, _proof(context), deadline=300),
            consequence="new consequence",
        )
    assert registry.snapshot()[0] == second


def test_registry_byte_capacity_fails_before_mutating_active_view() -> None:
    context = _registered()
    topology = IncidentTopology.from_registered(context)
    error = _error(context)
    classification = _classify(error, topology, _proof(context))
    registry = IncidentRegistry(
        context.work.session, max_incidents=2, max_error_ids=2, max_bytes=1
    )
    with pytest.raises(IncidentCapacityError, match="byte capacity"):
        registry.observe(error, classification, consequence="camera failed")
    assert registry.snapshot() == ()
    assert not registry._errors

    registry.max_bytes = 4096
    first = registry.observe(error, classification, consequence="camera failed")
    used = sum(len(item) for item in registry._errors.values()) + sum(
        len(item.SerializeToString(deterministic=True)) for item in registry.snapshot()
    )
    registry.max_bytes = used
    second_error = _error(context)
    second_error.incident_episode_id = error.error_id
    with pytest.raises(IncidentCapacityError, match="byte capacity"):
        registry.observe(
            second_error,
            _classify(second_error, topology, _proof(context)),
            consequence="camera failed",
        )
    assert registry.snapshot() == (first,)
