"""Bounded controller views and private preview attachment ownership (E03/E08)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cephvr.acquisition.v1 import messages_pb2 as acquisition
from cephvr.control.v1 import services_pb2 as rpc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device_projection import merge_devices, merge_preview_visibility
from cephvr.shared.identity import require_uuid4


class ProjectionError(ValueError):
    """A report cannot update the current authoritative projection."""


WARNING_CODES = frozenset(
    {
        "INVALID_IMAGE",
        "NATIVE_COUNTER_GAP",
        "NATIVE_COUNTER_DISCONTINUITY",
        "NATIVE_TIMESTAMP_UNAVAILABLE",
        "NATIVE_COUNTER_UNAVAILABLE",
        "TRANSPORT_COUNTERS_UNAVAILABLE",
        "NO_VIDEO_FRAMES",
    }
)


@dataclass
class PreviewTransfer:
    operation: str
    consumer: pb.ProcessIdentity
    run_id: str
    camera: int
    kind: int = acquisition.FRAME_BUFFER_KIND_PREVIEW
    attachment: acquisition.FrameBufferAttachment | None = None
    retired: bool = False
    result: rpc.PreviewConsumerReport | None = None


class ProjectionStore:
    """Called only on the controller state loop after per-hop authentication."""

    def __init__(
        self,
        controller_generation: str,
        peers: Mapping[str, pb.BackendContext],
        *,
        max_entries: int,
        max_payload_bytes: int,
    ) -> None:
        require_uuid4(controller_generation)
        if min(max_entries, max_payload_bytes) <= 0:
            raise ValueError("positive projection budgets required")
        self.generation = controller_generation
        self.peers = dict(peers)
        self.max_entries = max_entries
        self.max_payload_bytes = max_payload_bytes
        self.devices: pb.AcquisitionDeviceViews | None = None
        self.display: pb.VisualStimulusDisplayView | None = None
        self.warnings: dict[tuple[str, int, bytes], pb.AcquisitionWarningView] = {}
        self.transfers: dict[str, PreviewTransfer] = {}
        self.expected_display: tuple[str, int] | None = None
        self.work = pb.WorkContext()
        self.previous_trial: pb.TrialContext | None = None
        self.configuration_revision = 0

    def set_scope(self, work: pb.WorkContext, configuration_revision: int) -> None:
        old_session = self._session(self.work)
        new_session = self._session(work)
        if old_session != new_session:
            self.warnings.clear()
            self.previous_trial = None
        elif self.work.WhichOneof("work") == "trial" and self.work != work:
            self.previous_trial = pb.TrialContext.FromString(
                self.work.trial.SerializeToString()
            )
        self.work.CopyFrom(work)
        self.configuration_revision = configuration_revision
        self.warnings = {
            key: view
            for key, view in self.warnings.items()
            if self._scope_current(view)
        }

    @staticmethod
    def _session(work: pb.WorkContext) -> pb.SessionContext | None:
        kind = work.WhichOneof("work")
        return (
            work.session
            if kind == "session"
            else (work.trial.session if kind == "trial" else None)
        )

    def _source(self, source: pb.BackendContext, expected: str) -> None:
        if source.backend_name != expected or source != self.peers.get(expected):
            raise ProjectionError("report backend generation is not registered")

    def _scope_current(self, view: pb.AcquisitionWarningView) -> bool:
        if not view.work.WhichOneof("work"):
            return (
                not self.work.WhichOneof("work")
                and view.HasField("configuration_revision")
                and view.configuration_revision == self.configuration_revision
            )
        return view.work == self.work or (
            view.work.WhichOneof("work") == "trial"
            and self.previous_trial is not None
            and view.work.trial == self.previous_trial
        )

    def _budget(self, delta: int) -> None:
        used = sum(view.ByteSize() for view in self.warnings.values())
        used += self.devices.ByteSize() if self.devices else 0
        used += self.display.ByteSize() if self.display else 0
        used += sum(
            transfer.attachment.ByteSize()
            for transfer in self.transfers.values()
            if transfer.attachment is not None
        )
        if used + delta > self.max_payload_bytes:
            raise ProjectionError("retained projection byte budget exhausted")

    def validate_devices(self, report: rpc.AcquisitionDeviceStatusReport) -> None:
        """Validate source, scope, revision/time, and device-view consistency."""
        view = report.views
        self._source(view.source, "acquisition")
        if (
            not view.HasField("state_revision")
            or view.state_revision == 0
            or not view.HasField("observed_monotonic_ns")
            or view.observed_monotonic_ns <= 0
            or report.work != self.work
        ):
            raise ProjectionError("device status revision/time/work differs")
        for device in (view.behavioral, view.tracking):
            # An explicit empty ID confirms a released run; active runs need a UUID.
            if (
                device.preview_run_id
                or device.preview_running
                or device.preview_prepared
            ):
                require_uuid4(device.preview_run_id)
            if device.preview_running and not device.device_open:
                raise ProjectionError("running preview has no open device")

    def accept_devices(self, report: rpc.AcquisitionDeviceStatusReport) -> bool:
        self.validate_devices(report)
        view = report.views
        if self.devices:
            if view.state_revision < self.devices.state_revision:
                return False
            if view.state_revision == self.devices.state_revision:
                if view != self.devices:
                    raise ProjectionError("device status revision changed payload")
                return False
        adopted = merge_devices(view, self.devices)
        self._budget(
            adopted.ByteSize() - (self.devices.ByteSize() if self.devices else 0)
        )
        self.devices = adopted
        return True

    def accept_preview_visibility(
        self, report: rpc.AcquisitionDeviceStatusReport
    ) -> bool:
        self._source(report.views.source, "acquisition")
        try:
            adopted = merge_preview_visibility(report, self.devices)
        except ValueError as exc:
            raise ProjectionError(str(exc)) from exc
        if adopted is None:
            return False
        self._budget(
            adopted.ByteSize() - (self.devices.ByteSize() if self.devices else 0)
        )
        self.devices = adopted
        return True

    def accept_newer_devices(self, report: rpc.AcquisitionDeviceStatusReport) -> bool:
        """Adopt late terminal evidence only over an older current view."""
        self.validate_devices(report)
        if self.devices and report.views.state_revision <= self.devices.state_revision:
            return False
        return self.accept_devices(report)

    def expect_display(self, command_id: str, revision: int) -> None:
        require_uuid4(command_id)
        self.expected_display = command_id, revision

    def accept_display(self, view: pb.VisualStimulusDisplayView) -> bool:
        self._source(view.backend, "visual_stimulus")
        if (
            view.source.role != "visual_stimulus"
            or view.source.generation != view.backend.backend_generation
            or view.controller.role != "controller"
            or view.controller.generation != self.generation
            or (view.command_id, view.requested_revision) != self.expected_display
            or view.observed_monotonic_ns <= 0
            or not view.HasField("complete")
        ):
            raise ProjectionError("display result is not the expected operation")
        if view.HasField("applied_revision") and (
            view.applied_revision != view.requested_revision or not view.complete
        ):
            raise ProjectionError("display applied revision is not confirmed")
        if self.display and self.display.command_id == view.command_id:
            if view.observed_monotonic_ns < self.display.observed_monotonic_ns:
                return False
            if view.observed_monotonic_ns == self.display.observed_monotonic_ns:
                if view != self.display:
                    raise ProjectionError("display observation changed payload")
                return False
            if self.display.complete and view != self.display:
                raise ProjectionError("completed display operation changed result")
        self._budget(view.ByteSize() - (self.display.ByteSize() if self.display else 0))
        self.display = pb.VisualStimulusDisplayView.FromString(view.SerializeToString())
        return True

    def accept_warnings(self, report: rpc.AcquisitionWarningReport) -> bool:
        self._source(report.source, "acquisition")
        view = report.view
        require_uuid4(view.producer.generation)
        if (
            not view.producer.role
            or view.camera not in (1, 2)
            or not view.HasField("warning_revision")
            or view.warning_revision == 0
            or not self._scope_current(view)
            or len(view.warnings) > len(WARNING_CODES)
        ):
            raise ProjectionError("warning producer/scope/revision differs")
        scope = view.work.SerializeToString(deterministic=True)
        if not view.work.WhichOneof("work"):
            scope = f"{view.configuration_revision}:{view.preview_run_id}".encode()
        key = view.producer.generation, view.camera, scope
        old = self.warnings.get(key)
        if old:
            if view.warning_revision < old.warning_revision:
                return False
            if view.warning_revision == old.warning_revision:
                if view != old:
                    raise ProjectionError("warning revision changed payload")
                return False
        elif len(self.warnings) >= self.max_entries:
            raise ProjectionError("warning view capacity exhausted")
        previous = {item.warning_id: item for item in old.warnings} if old else {}
        codes: set[str] = set()
        identities: set[str] = set()
        for warning in view.warnings:
            require_uuid4(warning.warning_id)
            occurrence = warning.acquisition_occurrence
            if (
                occurrence.code not in WARNING_CODES
                or occurrence.code in codes
                or warning.warning_id in identities
                or occurrence.source != view.producer
                or occurrence.camera != view.camera
                or occurrence.work != view.work
                or occurrence.configuration_revision != view.configuration_revision
                or occurrence.preview_run_id != view.preview_run_id
                or not occurrence.HasField("count")
                or occurrence.count == 0
                or not occurrence.HasField("first_observed_monotonic_ns")
                or not occurrence.HasField("last_observed_monotonic_ns")
                or not 0
                < occurrence.first_observed_monotonic_ns
                <= occurrence.last_observed_monotonic_ns
                or len(occurrence.latest_sdk_code.encode()) > 64
                or len(occurrence.latest_details.encode()) > 1024
                or len(warning.message.encode()) > 1024
            ):
                raise ProjectionError("warning occurrence identity/count is invalid")
            codes.add(occurrence.code)
            identities.add(warning.warning_id)
            prior = previous.get(warning.warning_id)
            if prior:
                evidence = prior.acquisition_occurrence
                if (
                    occurrence.code != evidence.code
                    or occurrence.count < evidence.count
                    or occurrence.first_observed_monotonic_ns
                    != evidence.first_observed_monotonic_ns
                    or occurrence.last_observed_monotonic_ns
                    < evidence.last_observed_monotonic_ns
                ):
                    raise ProjectionError("warning occurrence regressed")
        if previous and not previous.keys() <= identities:
            raise ProjectionError("same-scope cumulative warning disappeared")
        self._budget(view.ByteSize() - (old.ByteSize() if old else 0))
        self.warnings[key] = pb.AcquisitionWarningView.FromString(
            view.SerializeToString()
        )
        return True

    def expect_preview(
        self,
        operation: str,
        consumer: pb.ProcessIdentity,
        run_id: str,
        camera: int,
        *,
        kind: int = acquisition.FRAME_BUFFER_KIND_PREVIEW,
    ) -> None:
        for identity in (operation, consumer.generation, run_id):
            require_uuid4(identity)
        roles = (
            {"tracking"}
            if kind == acquisition.FRAME_BUFFER_KIND_TRACKING
            else {"gui", "cli"}
        )
        if consumer.role not in roles or camera not in (1, 2):
            raise ProjectionError("preview target/camera is invalid")
        old = self.transfers.get(operation)
        if old is not None:
            if (old.consumer, old.run_id, old.camera, old.kind) != (
                consumer,
                run_id,
                camera,
                kind,
            ):
                raise ProjectionError("preview operation identity changed")
            return
        for transfer in self.transfers.values():
            released = (
                transfer.result is not None
                and transfer.result.result == rpc.PREVIEW_CONSUMER_RESULT_RELEASED
            )
            if transfer.run_id == run_id and transfer.kind == kind and not released:
                raise ProjectionError(
                    "preview already has an outstanding viewer transfer"
                )
        if len(self.transfers) >= self.max_entries:
            completed = next(
                (
                    key
                    for key, transfer in self.transfers.items()
                    if transfer.result is not None
                    and transfer.result.result == rpc.PREVIEW_CONSUMER_RESULT_RELEASED
                ),
                None,
            )
            if completed is not None:
                del self.transfers[completed]
        if len(self.transfers) >= self.max_entries:
            raise ProjectionError("preview transfer capacity exhausted")
        self.transfers[operation] = PreviewTransfer(
            operation,
            pb.ProcessIdentity.FromString(consumer.SerializeToString()),
            run_id,
            camera,
            kind,
        )

    def retire_preview(self, run_id: str) -> None:
        for transfer in self.transfers.values():
            if transfer.run_id == run_id:
                transfer.retired = True

    def cancel_preview_expectation(self, operation: str) -> None:
        """Forget a transfer that failed admission before any report was sent."""
        transfer = self.transfers.get(operation)
        if (
            transfer is not None
            and transfer.attachment is None
            and transfer.result is None
        ):
            self.transfers.pop(operation, None)

    def accept_preview(self, report: rpc.PreviewAttachmentReport) -> bool:
        self._source(report.source, "acquisition")
        transfer = self.transfers.get(report.operation.command_id)
        attachment = report.attachment
        buffer, sync = attachment.buffer, attachment.sync
        require_uuid4(buffer.allocation_id)
        require_uuid4(sync.transfer_id)
        if transfer is None or (
            sync.target != transfer.consumer
            or buffer.kind != transfer.kind
            or buffer.camera != transfer.camera
            or buffer.owner.role != "acquisition"
            or buffer.owner.generation != report.source.backend_generation
            or (
                transfer.kind == acquisition.FRAME_BUFFER_KIND_PREVIEW
                and buffer.HasField("consumer")
            )
            or (
                transfer.kind == acquisition.FRAME_BUFFER_KIND_TRACKING
                and (
                    not buffer.HasField("consumer")
                    or buffer.consumer != transfer.consumer
                )
            )
            or not buffer.shared_memory_name
            or not sync.event_name
        ):
            raise ProjectionError("preview transfer was not authorized")
        if buffer.WhichOneof("scope") == "preview":
            if (
                buffer.preview.controller.role != "controller"
                or buffer.preview.controller.generation != self.generation
                or buffer.preview.acquisition_run_id != transfer.run_id
            ):
                raise ProjectionError("preview run identity differs")
        elif buffer.WhichOneof("scope") == "session":
            if buffer.session != self._session(self.work):
                raise ProjectionError("session preview identity differs")
        else:
            raise ProjectionError("preview scope is missing")
        if transfer.attachment is not None:
            if transfer.attachment != attachment:
                raise ProjectionError("preview attachment changed within transfer")
            return False
        self._budget(attachment.ByteSize())
        transfer.attachment = acquisition.FrameBufferAttachment.FromString(
            attachment.SerializeToString()
        )
        return True

    def preview(self, query: rpc.PreviewAttachmentQuery) -> rpc.PreviewAttachmentResult:
        if (
            query.controller_generation != self.generation
            or query.client_id != query.consumer.generation
        ):
            raise ProjectionError("preview requester identity differs")
        matches = [
            transfer
            for transfer in self.transfers.values()
            if transfer.consumer == query.consumer
            and transfer.run_id == query.preview_run_id
            and transfer.attachment is not None
            and (
                transfer.result is None
                or transfer.result.result != rpc.PREVIEW_CONSUMER_RESULT_RELEASED
            )
        ]
        if len(matches) != 1:
            return rpc.PreviewAttachmentResult(
                available=False,
                failure=pb.Failure(
                    code="UNAVAILABLE",
                    message="exact preview attachment is unavailable",
                ),
            )
        transfer = matches[0]
        return rpc.PreviewAttachmentResult(
            available=True,
            attachment=transfer.attachment,
            release_only=transfer.retired,
        )

    def preview_result(self, report: rpc.PreviewConsumerReport) -> bool:
        if (
            report.controller_generation != self.generation
            or report.client_id != report.consumer.generation
            or report.result
            not in {
                rpc.PREVIEW_CONSUMER_RESULT_ATTACHED,
                rpc.PREVIEW_CONSUMER_RESULT_RELEASED,
                rpc.PREVIEW_CONSUMER_RESULT_FAILED,
            }
        ):
            raise ProjectionError("preview consumer result identity differs")
        matches = [
            transfer
            for transfer in self.transfers.values()
            if transfer.consumer == report.consumer
            and transfer.run_id == report.preview_run_id
            and transfer.attachment is not None
            and transfer.attachment.buffer.allocation_id == report.allocation_id
            and transfer.attachment.sync.transfer_id == report.transfer_id
        ]
        if len(matches) != 1:
            raise ProjectionError("preview result targets an unknown transfer")
        transfer = matches[0]
        if transfer.result == report:
            return False
        if (
            transfer.result
            and transfer.result.result == rpc.PREVIEW_CONSUMER_RESULT_RELEASED
        ):
            raise ProjectionError("released preview cannot be reattached")
        if transfer.retired and report.result == rpc.PREVIEW_CONSUMER_RESULT_ATTACHED:
            raise ProjectionError("retired preview accepts release evidence only")
        transfer.result = rpc.PreviewConsumerReport.FromString(
            report.SerializeToString()
        )
        if report.result == rpc.PREVIEW_CONSUMER_RESULT_FAILED:
            transfer.retired = True
        return True

    def install_public(self, snapshot: pb.Snapshot) -> None:
        if self.devices is not None:
            snapshot.acquisition_devices.CopyFrom(self.devices)
        if self.display is not None:
            snapshot.visual_stimulus_display.CopyFrom(self.display)
        snapshot.warnings.extend(
            warning for view in self.warnings.values() for warning in view.warnings
        )
