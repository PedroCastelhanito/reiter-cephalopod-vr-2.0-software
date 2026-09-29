"""Protected E08 acquisition/tracking/VR Setup dependency state.

This holds descriptors, never frames. Its contents must not enter public snapshots,
configuration history or logs. The controller dispatches its existing RPCs from
these exact retained messages under the original Setup deadline.
"""

from __future__ import annotations

from collections.abc import Mapping

from cephvr.acquisition.v1 import messages_pb2 as acquisition
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.shared.identity import require_uuid4
from cephvr.tracking.v1 import preparation_pb2 as tracking_wire


class PreparationError(ValueError):
    """Descriptor evidence conflicts with the exact live Setup attempt."""


class PreparationHandoff:
    def __init__(
        self,
        session: pb.SessionContext,
        revision: int,
        peers: Mapping[str, pb.BackendContext],
        setup_commands: Mapping[str, str],
        *,
        camera: int,
        closed_loop: bool,
        max_payload_bytes: int,
    ) -> None:
        self.session = pb.SessionContext.FromString(session.SerializeToString())
        self.revision = revision
        self.peers = dict(peers)
        self.setup_commands = dict(setup_commands)
        self.camera = camera
        self.closed_loop = closed_loop
        self.max_payload_bytes = max_payload_bytes
        self.reports: dict[str, rpc.DataPreparationReport] = {}
        self.retired = False
        self.input_binding_command: str | None = None
        self.input_confirmation_command: str | None = None

    def retire(self) -> None:
        # Keep existing descriptors as cleanup obligations; prevent new dispatch.
        self.retired = True

    @property
    def frames(self) -> acquisition.FrameBufferAttachment | None:
        report = self.reports.get("acquisition")
        if report is None:
            return None
        return acquisition.FrameBufferAttachment.FromString(
            report.tracking_input.SerializeToString()
        )

    @property
    def tracking(self) -> tracking_wire.TrackingPreparationState | None:
        report = self.reports.get("tracking")
        if report is None:
            return None
        return tracking_wire.TrackingPreparationState.FromString(
            report.tracking.SerializeToString()
        )

    @property
    def can_bind_input(self) -> bool:
        return (
            not self.retired
            and self.frames is not None
            and self.tracking is not None
            and self.input_binding_command is None
        )

    @property
    def can_confirm_input(self) -> bool:
        state = self.tracking
        return (
            not self.retired
            and self.frames is not None
            and state is not None
            and state.data_attached
            and self.input_confirmation_command is None
        )

    @property
    def can_prepare_vr(self) -> bool:
        if self.retired:
            return False
        state = self.tracking
        return not self.closed_loop or (
            state is not None and state.HasField("feedback")
        )

    def accept(self, report: rpc.DataPreparationReport) -> bool:
        """Install a newer complete view; return false for an identical/stale view."""
        name = report.source.backend.backend_name
        if self.retired:
            raise PreparationError("Setup handoff is retired; cleanup remains required")
        if (
            name not in {"acquisition", "tracking"}
            or report.source.backend != self.peers.get(name)
            or report.source.work.WhichOneof("work") != "session"
            or report.source.work.session != self.session
            or report.source.operation.command_id != self.setup_commands.get(name)
            or report.configuration_revision != self.revision
            or report.report_revision == 0
        ):
            raise PreparationError("preparation source, operation or revision differs")
        expected_payload = "tracking_input" if name == "acquisition" else "tracking"
        if report.WhichOneof("payload") != expected_payload:
            raise PreparationError("preparation payload does not belong to this source")
        previous = self.reports.get(name)
        if previous is not None:
            if report.report_revision < previous.report_revision:
                return False
            if report.report_revision == previous.report_revision:
                if report != previous:
                    raise PreparationError("preparation revision changed payload")
                return False
        if name == "acquisition":
            self._validate_frames(report.tracking_input)
            if previous and previous.tracking_input != report.tracking_input:
                raise PreparationError("camera allocation changed within Setup")
        else:
            self._validate_tracking(report.tracking)
            if previous:
                old, new = previous.tracking, report.tracking
                if old.preparation_generation != new.preparation_generation:
                    raise PreparationError("tracking preparation generation changed")
                if old.data_attached and (
                    not new.data_attached or old.attached_input != new.attached_input
                ):
                    raise PreparationError("tracking attachment regressed or changed")
                for field in ("methods", "feedback"):
                    if old.HasField(field) and getattr(old, field) != getattr(
                        new, field
                    ):
                        raise PreparationError(f"prepared tracking {field} changed")
        retained_bytes = report.ByteSize() + sum(
            value.ByteSize() for key, value in self.reports.items() if key != name
        )
        if retained_bytes > self.max_payload_bytes:
            raise PreparationError("preparation descriptor budget exhausted")
        self.reports[name] = rpc.DataPreparationReport.FromString(
            report.SerializeToString()
        )
        return True

    def _validate_frames(self, attachment: acquisition.FrameBufferAttachment) -> None:
        frames, sync = attachment.buffer, attachment.sync
        require_uuid4(frames.allocation_id)
        require_uuid4(sync.transfer_id)
        require_uuid4(frames.producer.generation)
        expected = self.peers.get("tracking")
        if expected is None:
            raise PreparationError("tracking has no registered consumer")
        consumer = pb.ProcessIdentity(
            role="tracking", generation=expected.backend_generation
        )
        owner = self.peers["acquisition"]
        if (
            frames.owner.role != "acquisition"
            or frames.owner.generation != owner.backend_generation
            or not frames.producer.role
            or frames.consumer != consumer
            or sync.target != consumer
            or frames.kind != acquisition.FRAME_BUFFER_KIND_TRACKING
            or frames.camera != self.camera
            or frames.WhichOneof("scope") != "session"
            or frames.session != self.session
            or not frames.HasField("configuration_revision")
            or frames.configuration_revision != self.revision
            or not frames.shared_memory_name
            or not sync.event_name
            or not frames.HasField("layout_version")
            or frames.layout_version == 0
            or not frames.HasField("capacity_frames")
            or frames.capacity_frames == 0
            or not frames.HasField("allocation_bytes")
            or frames.allocation_bytes == 0
            or not frames.HasField("image")
        ):
            raise PreparationError("camera attachment identity/layout is incomplete")

    def _validate_tracking(self, state: tracking_wire.TrackingPreparationState) -> None:
        require_uuid4(state.preparation_generation)
        if state.configuration_revision != self.revision:
            raise PreparationError("tracking nested configuration revision differs")
        if state.data_attached != state.HasField("attached_input"):
            raise PreparationError("tracking attachment evidence/presence differs")
        if state.data_attached:
            frames = self.frames
            if frames is None or (
                state.attached_input.resource_id != frames.buffer.allocation_id
                or state.attached_input.transfer_id != frames.sync.transfer_id
            ):
                raise PreparationError("tracking acknowledged another input transfer")
        if state.HasField("feedback"):
            feedback = state.feedback
            require_uuid4(feedback.attachment_generation)
            if (
                not self.closed_loop
                or feedback.source_process_instance_id
                != self.peers["tracking"].backend_generation
                or not feedback.result_pipe
                or not feedback.credit_pipe
                or not feedback.startup_nonce
                or not feedback.stream_ids
                or len(set(feedback.stream_ids)) != len(feedback.stream_ids)
                or not all(feedback.stream_ids)
                or feedback.queue_capacity == 0
                or feedback.maximum_message_bytes == 0
            ):
                raise PreparationError("feedback descriptor identity/bounds differ")
