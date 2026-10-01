"""Expected trial participants, activity sources and exact producer ownership."""

from __future__ import annotations

from cephvr.acquisition.v1 import camera_pb2 as camera_pb
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.ports import BackendPort
from cephvr.controller.state import Attempt


def _camera_source(role: int) -> str:
    return "behavioral" if role == camera_pb.CAMERA_ROLE_BEHAVIORAL else "tracking"


def activity_requirements(
    attempt: Attempt, name: str
) -> tuple[
    frozenset[int],
    frozenset[int],
    frozenset[str],
    frozenset[str],
    frozenset[tuple[str, str]],
]:
    ready = attempt.ready.get(name)
    if ready is None:
        raise RuntimeError("required backend lacks frozen Setup Ready evidence")
    affected = attempt.unavailable_resources()
    declared = {
        source for item in ready.prepared_functions for source in item.lifecycle_sources
    }
    active = {
        source
        for item in ready.prepared_functions
        if item.resource_id not in affected
        for source in item.lifecycle_sources
    }
    producers = {
        (reporter.role, reporter.generation)
        for item in ready.prepared_functions
        if item.resource_id not in affected and item.lifecycle_sources
        for reporter in item.authorized_reporters
    }
    if name == "acquisition":
        settings = next(
            (
                item.acquisition
                for item in attempt.prepared.configuration.backends
                if item.backend_name == name and item.enabled
            ),
            None,
        )
        if settings is None:
            raise RuntimeError("acquisition resolved settings missing")
        selected = {
            camera_pb.CAMERA_ROLE_BEHAVIORAL: settings.behavioral,
            camera_pb.CAMERA_ROLE_TRACKING: settings.tracking,
        }
        configured = {
            _camera_source(role)
            for role, camera in selected.items()
            if camera.HasField("enabled") and camera.enabled
        }
        if declared != configured:
            raise RuntimeError(
                "acquisition lifecycle source declaration differs from enabled cameras"
            )
        roles = frozenset(
            role
            for role, camera in selected.items()
            if camera.HasField("enabled")
            and camera.enabled
            and _camera_source(role) in active
        )
        external = frozenset(
            role
            for role in roles
            if selected[role].device.frame_timing
            == camera_pb.FRAME_TIMING_EXTERNAL_TRIGGER
        )
        sources = frozenset(_camera_source(role) for role in roles)
        return roles, external, frozenset(), sources, frozenset(producers)
    if name == "visual_stimulus":
        if declared != {"renderer"} or "renderer" not in active:
            raise RuntimeError(
                "essential Visual Stimulus renderer lifecycle source unavailable"
            )
        return (
            frozenset(),
            frozenset(),
            attempt.visual_stimulus_output_ids,
            frozenset(active),
            frozenset(producers),
        )
    if name == "tracking":
        if declared != {"tracking"}:
            raise RuntimeError("tracking lifecycle source declaration missing")
        return (
            frozenset(),
            frozenset(),
            frozenset(),
            frozenset(active),
            frozenset(producers),
        )
    raise RuntimeError("backend has no declared activity evidence semantics")


def activity_backends(attempt: Attempt) -> frozenset[str]:
    return frozenset(
        name
        for name in attempt.trial_participants
        if activity_requirements(attempt, name)[3]
    )


def source_producers(attempt: Attempt, name: str) -> dict[str, tuple[str, str]]:
    ready = attempt.ready[name]
    affected = attempt.unavailable_resources()
    sources: dict[str, tuple[str, str]] = {}
    for function in ready.prepared_functions:
        if function.resource_id in affected:
            continue
        for source in function.lifecycle_sources:
            if (
                source in sources
                or len(function.authorized_reporters) > 1
                or name == "acquisition"
                and len(function.authorized_reporters) != 1
            ):
                raise RuntimeError(
                    "lifecycle source lacks one exact registered producer"
                )
            reporter = (
                function.authorized_reporters[0]
                if function.authorized_reporters
                else function.owner
            )
            sources[source] = (reporter.role, reporter.generation)
    return sources


def select_trial_participants(
    attempt: Attempt, plan: pb.TrialPlan
) -> dict[str, BackendPort]:
    affected = attempt.unavailable_resources()
    participants: dict[str, BackendPort] = {}
    for name, backend in attempt.required.items():
        declared = {item.resource_id for item in attempt.ready[name].prepared_functions}
        expected_outputs = {
            item.output_key
            for item in attempt.prepared.outputs
            if item.trial == plan.context and item.backend.backend_name == name
        }
        if not declared or declared - affected:
            participants[name] = backend
            continue
        if name == "visual_stimulus" or not expected_outputs <= affected:
            raise RuntimeError(
                f"{name} has unavailable functions without a safe trial omission"
            )
    return participants
