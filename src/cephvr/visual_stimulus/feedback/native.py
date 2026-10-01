"""Native Setup binding for feedback pipe ownership and batch mapping (A06/E08)."""

from __future__ import annotations

from collections.abc import Callable

from cephvr.platform.windows.message_pipe import open_message_pipe
from cephvr.platform.windows.resource_ledger import ResourceKey
from cephvr.shared.clock import host_time_ns
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.feedback.batch import FeedbackBatchConsumer
from cephvr.visual_stimulus.feedback.consumer import FeedbackResult
from cephvr.visual_stimulus.feedback.pipe_consumer import (
    FeedbackPipeConstructionError,
    FeedbackPipeConsumer,
)
from cephvr.visual_stimulus.rendering.types import ResourceReleaseReport
from cephvr.visual_stimulus.v1 import runtime_pb2 as vp


class NativeFeedback:
    """Bind the retained descriptor once, then expose finite trial-local batches."""

    def __init__(
        self,
        *,
        local_process_instance_id: str,
        clock_ns: Callable[[], int] = host_time_ns,
    ) -> None:
        self.local_process_instance_id = local_process_instance_id
        self.max_result_age_ns = 0
        self.clock_ns = clock_ns
        self._transport: FeedbackPipeConsumer | None = None
        self._source_generation = ""
        self._attachment_generation = ""
        self._active_consumer: FeedbackBatchConsumer | None = None

    def configure(
        self,
        attachment: vp.FeedbackAttachment,
        artifacts: tuple[PreparedTrial, ...],
        announce: Callable[[str], None],
        deadline_ns: int,
        max_result_age_ns: int,
    ) -> None:
        if self._transport is not None:
            raise RuntimeError("feedback transport is already attached")
        if max_result_age_ns <= 0:
            raise ValueError(
                "closed-loop feedback requires a positive locked freshness limit"
            )
        self.max_result_age_ns = max_result_age_ns
        streams = {
            channel.stream_id
            for artifact in artifacts
            for channel in artifact.source.input_channels
        }
        if not streams or not streams <= set(attachment.stream_ids):
            raise ValueError(
                "closed-loop feedback streams lack an exact Setup attachment"
            )
        self._source_generation = attachment.source_process_instance_id
        self._attachment_generation = attachment.attachment_generation

        def resource_key(kind: str, owner_id: str) -> ResourceKey:
            return ResourceKey("visual-stimulus-feedback-" + kind, owner_id)

        try:
            self._transport = FeedbackPipeConsumer(
                attachment,
                local_process_instance_id=self.local_process_instance_id,
                resource_key_factory=resource_key,
                open_pipe=open_message_pipe,
                announce=announce,
                selected_stream_ids=tuple(sorted(streams)),
                deadline_ns=deadline_ns,
                clock_ns=self.clock_ns,
            )
        except FeedbackPipeConstructionError as exc:
            self._transport = exc.consumer
            raise

    def prepare_trial(self, artifact: PreparedTrial) -> Callable[..., object]:
        if self._transport is None:
            raise RuntimeError(
                "feedback trial prepared without an authenticated attachment"
            )
        streams = {channel.stream_id for channel in artifact.source.input_channels}
        if not streams <= set(self._transport.selected_stream_ids):
            raise ValueError(
                "prepared trial uses a feedback stream outside its attachment"
            )
        self._active_consumer = FeedbackBatchConsumer(
            artifact.source,
            arena_boundaries=artifact.arena_boundaries,
            max_result_age_ns=self.max_result_age_ns,
            clock_ns=self.clock_ns,
            attachment_generation=self._attachment_generation,
            stream_ids=frozenset(streams),
            source_generation=self._source_generation,
        )
        return self._active_consumer.consume

    def begin_trial(self, trial_id: str) -> None:
        if self._transport is None:
            return
        if self._active_consumer is None:
            raise RuntimeError("feedback consumer was not prepared for this trial")
        self._active_consumer.begin_trial(trial_id)

    def capture_batch(self) -> tuple[FeedbackResult, ...]:
        if self._transport is None:
            return ()
        return self._transport.capture_batch()

    def discard_pending(self) -> None:
        if self._transport is None:
            return
        self._transport.capture_batch()

    def close(self, deadline_ns: int) -> ResourceReleaseReport:
        transport = self._transport
        if transport is not None:
            try:
                transport.close(deadline_ns=deadline_ns)
            except BaseException:
                if transport.closed:
                    self._transport = None
                    self._active_consumer = None
                raise
            self._transport = None
        self._active_consumer = None
        if transport is None:
            return ResourceReleaseReport((), ())
        return ResourceReleaseReport(
            ("feedback-result-pipe", "feedback-credit-pipe"), ()
        )
