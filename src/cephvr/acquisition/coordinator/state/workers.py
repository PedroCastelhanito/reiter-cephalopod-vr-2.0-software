"""Worker, preview, command and worker-owned retention records."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from cephvr.acquisition.ports import WorkerPort
from cephvr.acquisition.v1 import camera_pb2
from cephvr.acquisition.v1 import messages_pb2 as acq
from cephvr.acquisition.v1 import microcontroller_pb2 as mcu
from cephvr.control.v1 import types_pb2 as control
from cephvr.shared.commands import CommandLedger

from .base import LaunchRecord


@dataclass
class WorkerPreview:
    run_id: str
    configuration_revision: int
    preparation: control.OperationContext | None = None
    start_operation: control.OperationContext | None = None
    stop_operation: control.OperationContext | None = None
    allocation_id: str | None = None
    preview_output_bit_depth: int = 8
    resolved_camera: camera_pb2.CameraResolvedState | None = None
    viewer: control.ProcessIdentity | None = None
    viewer_transfer_id: str | None = None
    attachment: acq.FrameBufferAttachment | None = None
    worker_attachment: acq.FrameBufferAttachment | None = None
    started: bool = False
    stopping: bool = False
    started_event: asyncio.Event = field(default_factory=asyncio.Event)
    stopped_event: asyncio.Event = field(default_factory=asyncio.Event)
    cleanup_event: asyncio.Event = field(default_factory=asyncio.Event)
    viewer_released_event: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True)
class PausedPreview:
    role: int
    resolved: camera_pb2.CameraResolvedState
    output_bits: int


@dataclass
class WorkerTrial:
    configuration_revision: int
    preparation: control.OperationContext | None = None
    schedule: control.OperationContext | None = None
    release: control.OperationContext | None = None
    stop: control.OperationContext | None = None
    released: bool = False
    start_monotonic_ns: int | None = None
    end_monotonic_ns: int | None = None
    pulse_on: mcu.PulseCommandEvidence | None = None
    pulse_off: mcu.PulseCommandEvidence | None = None


@dataclass
class ChildOperation:
    """One exact worker command retained under its acquisition parent operation."""

    command_id: str
    camera: int
    work: control.WorkContext
    parent_operation: control.OperationContext
    kind: str
    configuration_revision: int = 0
    requested_device_id: str | None = None
    deadline_ns: int | None = None
    report: control.OperationState | None = None
    report_ingress_ns: int | None = None
    report_revision: int = 0
    resolved_camera: camera_pb2.CameraResolvedState | None = None
    exported_pfs_path: str | None = None
    retention_key: str | None = None
    retained_size: int = 0
    updated: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class WorkerRecord:
    """Single authoritative registry entry for one exact camera worker generation."""

    context: acq.WorkerContext
    port: WorkerPort | None
    launch: LaunchRecord
    commands: CommandLedger | None = field(default=None, repr=False)
    setup_ready: acq.WorkerReadyEvidence | None = None
    setup_operation: control.OperationContext | None = None
    preview: WorkerPreview | None = None
    trial: WorkerTrial | None = None
    child_operations: dict[str, ChildOperation] = field(default_factory=dict)
    heartbeat: control.HeartbeatReport | None = None
    warning_views: dict[str, control.AcquisitionWarningView] = field(
        default_factory=dict
    )
    warning_payloads: dict[str, str] = field(default_factory=dict)
    lifecycle_evidence: dict[tuple[str, str, str], acq.WorkerLifecycleEvidence] = field(
        default_factory=dict
    )
    lifecycle_payloads: dict[tuple[str, str, str], str] = field(default_factory=dict)
    lifecycle_finalized_ns: dict[str, int] = field(default_factory=dict)
    alive: bool = False

    def prune_child_operations(self) -> int:
        """Drop only child metadata whose shared-ledger reservation expired."""
        if self.commands is None:
            return 0
        expired = [
            command_id
            for command_id, child in self.child_operations.items()
            if child.retention_key is not None
            and not self.commands.has_payload(child.retention_key)
        ]
        for command_id in expired:
            self.child_operations.pop(command_id, None)
        return len(expired)

    def retain_lifecycle(
        self,
        evidence: acq.WorkerLifecycleEvidence,
        *,
        commands: CommandLedger,
    ) -> bool:
        """Keep latest cumulative evidence per exact work/command/kind revision."""
        self.preflight_lifecycle(evidence, commands=commands)
        if not evidence.HasField("operation") or not evidence.HasField("source"):
            raise ValueError("worker lifecycle evidence requires source and operation")
        kind = evidence.WhichOneof("evidence")
        if kind is None or not evidence.HasField("state_revision"):
            raise ValueError("worker lifecycle evidence requires kind and revision")
        selected_work = evidence.source.work.WhichOneof("work")
        if selected_work == "session":
            work_key = evidence.source.work.session.session_id
        elif selected_work == "trial":
            work_key = evidence.source.work.trial.trial_id
        else:
            work_key = evidence.operation.command_id
        retention_scope = work_key
        if selected_work == "trial":
            retention_scope = evidence.source.work.trial.session.session_id
        key = (work_key, evidence.operation.command_id, kind)
        prior = self.lifecycle_evidence.get(key)
        if prior is not None:
            if prior.state_revision > evidence.state_revision:
                return False
            if prior.state_revision == evidence.state_revision:
                same = prior.SerializeToString(
                    deterministic=True
                ) == evidence.SerializeToString(deterministic=True)
                if not same:
                    raise ValueError(
                        "same worker lifecycle revision changed its evidence"
                    )
                return True
        saved = acq.WorkerLifecycleEvidence()
        saved.CopyFrom(evidence)
        safety = kind in {"stopped", "finished", "cleanup"}
        payload_key = (
            f"worker-lifecycle:{self.launch.worker.generation}:{retention_scope}:"
            f"{'safety' if safety else 'ordinary'}"
        )
        retained_bytes = saved.ByteSize() + sum(
            item.ByteSize()
            for item_key, item in self.lifecycle_evidence.items()
            if _lifecycle_retention_scope(item) == retention_scope
            and item_key != key
            and _lifecycle_safety(item) == safety
        )
        commands.reserve_payload(
            payload_key,
            max(1, retained_bytes),
            work_key=retention_scope,
            priority=safety,
        )
        self.lifecycle_evidence[key] = saved
        for item_key in self.lifecycle_evidence:
            item_scope = _lifecycle_retention_scope(self.lifecycle_evidence[item_key])
            if item_scope == retention_scope:
                self.lifecycle_payloads[item_key] = payload_key
        return True

    def preflight_lifecycle(
        self,
        evidence: acq.WorkerLifecycleEvidence,
        *,
        commands: CommandLedger,
    ) -> None:
        """Validate replay and reserve evidence capacity before ledger effects."""
        if not evidence.HasField("operation") or not evidence.HasField("source"):
            raise ValueError("worker lifecycle evidence requires source and operation")
        kind = evidence.WhichOneof("evidence")
        if kind is None or not evidence.HasField("state_revision"):
            raise ValueError("worker lifecycle evidence requires kind and revision")
        selected_work = evidence.source.work.WhichOneof("work")
        if selected_work == "session":
            work_key = evidence.source.work.session.session_id
        elif selected_work == "trial":
            work_key = evidence.source.work.trial.trial_id
        else:
            work_key = evidence.operation.command_id
        retention_scope = (
            evidence.source.work.trial.session.session_id
            if selected_work == "trial"
            else work_key
        )
        key = (work_key, evidence.operation.command_id, kind)
        prior = self.lifecycle_evidence.get(key)
        if prior is not None:
            if prior.state_revision > evidence.state_revision:
                return
            if prior.state_revision == evidence.state_revision:
                if prior.SerializeToString(
                    deterministic=True
                ) != evidence.SerializeToString(deterministic=True):
                    raise ValueError(
                        "same worker lifecycle revision changed its evidence"
                    )
                return
        safety = _lifecycle_safety(evidence)
        payload_key = (
            f"worker-lifecycle:{self.launch.worker.generation}:{retention_scope}:"
            f"{'safety' if safety else 'ordinary'}"
        )
        retained_bytes = evidence.ByteSize() + sum(
            item.ByteSize()
            for item_key, item in self.lifecycle_evidence.items()
            if _lifecycle_retention_scope(item) == retention_scope
            and item_key != key
            and _lifecycle_safety(item) == safety
        )
        commands.reserve_payload(
            payload_key,
            max(1, retained_bytes),
            work_key=retention_scope,
            priority=safety,
        )

    def finalize_lifecycle_work(self, work_key: str, finalized_ns: int) -> None:
        """Keep final evidence through E08 retention before bounded pruning."""
        prior = self.lifecycle_finalized_ns.setdefault(work_key, finalized_ns)
        if prior != finalized_ns:
            raise ValueError("worker work finalization timestamp changed")

    def retain_warning_view(
        self, view: control.AcquisitionWarningView, commands: CommandLedger
    ) -> bool:
        if (
            view.producer != self.launch.worker
            or view.camera != self.context.camera
            or not view.HasField("warning_revision")
            or view.warning_revision == 0
            or len(view.warnings) > 10
        ):
            raise ValueError("worker warning view differs from its registered scope")
        scope = _warning_scope(view)
        prior = self.warning_views.get(scope)
        if prior is not None:
            prior_revision = prior.warning_revision
            new_revision = view.warning_revision
            if prior_revision > new_revision:
                return False
            if prior_revision == new_revision:
                if prior != view:
                    raise ValueError("same warning revision changed its complete view")
                return True
        work_key = _context_work_key(view.work, view.producer.generation)
        payload_key = self.warning_payloads.get(scope)
        if payload_key is None:
            payload_key = f"worker-warning:{view.producer.generation}:{scope}"
        commands.reserve_payload(
            payload_key, max(1, view.ByteSize()), work_key=work_key
        )
        saved = control.AcquisitionWarningView()
        saved.CopyFrom(view)
        self.warning_views[scope] = saved
        self.warning_payloads[scope] = payload_key
        return True

    def prune_lifecycle(
        self, now_ns: int, retention_ns: int, commands: CommandLedger
    ) -> int:
        expired_work = {
            work_key
            for work_key, finalized_ns in self.lifecycle_finalized_ns.items()
            if now_ns > finalized_ns + retention_ns
        }
        if not expired_work:
            return 0
        expired = [
            key
            for key, evidence in self.lifecycle_evidence.items()
            if _lifecycle_retention_scope(evidence) in expired_work
        ]
        for key in expired:
            self.lifecycle_evidence.pop(key)
            payload_key = self.lifecycle_payloads.pop(key, None)
            if payload_key is not None:
                commands.release_payload(payload_key)
        expired_warning_scopes = [
            scope
            for scope, view in self.warning_views.items()
            if _context_work_key(view.work, view.producer.generation) in expired_work
        ]
        for scope in expired_warning_scopes:
            self.warning_views.pop(scope, None)
            payload_key = self.warning_payloads.pop(scope, None)
            if payload_key is not None:
                commands.release_payload(payload_key)
        for work_key in expired_work:
            self.lifecycle_finalized_ns.pop(work_key, None)
        return len(expired)


def _context_work_key(work: control.WorkContext, generation: str) -> str:
    kind = work.WhichOneof("work")
    if kind == "session":
        return work.session.session_id
    if kind == "trial":
        return work.trial.trial_id
    return generation


def _lifecycle_retention_scope(evidence: acq.WorkerLifecycleEvidence) -> str:
    kind = evidence.source.work.WhichOneof("work")
    if kind == "trial":
        return evidence.source.work.trial.session.session_id
    if kind == "session":
        return evidence.source.work.session.session_id
    return evidence.operation.command_id


def _lifecycle_safety(evidence: acq.WorkerLifecycleEvidence) -> bool:
    return evidence.WhichOneof("evidence") in {"stopped", "finished", "cleanup"}


def _warning_scope(view: control.AcquisitionWarningView) -> str:
    revision = (
        view.configuration_revision if view.HasField("configuration_revision") else "-"
    )
    preview = view.preview_run_id if view.HasField("preview_run_id") else "-"
    return (
        f"{_context_work_key(view.work, view.producer.generation)}:{revision}:{preview}"
    )
