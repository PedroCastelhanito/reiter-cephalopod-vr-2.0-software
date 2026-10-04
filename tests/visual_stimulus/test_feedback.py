from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from tests.visual_stimulus.support import make_program

from cephvr.control.v1 import native_transport_pb2
from cephvr.visual_stimulus.config.models.program_model import (
    Constant,
    Feedback,
    InputChannel,
)
from cephvr.visual_stimulus.feedback.arena import (
    inset_convex_polygon,
    slide_displacement,
)
from cephvr.visual_stimulus.feedback.batch import FeedbackBatchConsumer
from cephvr.visual_stimulus.feedback.consumer import FeedbackConsumer, FeedbackResult
from cephvr.visual_stimulus.feedback.credits import FeedbackCredits
from cephvr.visual_stimulus.feedback.mapping import FeedbackMappingApplier
from cephvr.visual_stimulus.feedback.pipe_consumer import (
    FeedbackPipeConstructionError,
    FeedbackPipeConsumer,
)
from cephvr.visual_stimulus.feedback.wire import decode_entry
from cephvr.visual_stimulus.v1 import data_pb2 as data
from cephvr.visual_stimulus.v1 import runtime_pb2


class Target:
    def __init__(self) -> None:
        self.applied = []

    def apply(self, result, values, now_ns) -> None:
        self.applied.append((result.result_id, values, now_ns))


def test_feedback_generation_freshness_and_hold() -> None:
    clock = iter((1_100, 1_500)).__next__
    target = Target()
    consumer = FeedbackConsumer(max_result_age_ns=200, clock_ns=clock, target=target)
    consumer.begin_trial("trial")

    def result(sequence: int, receipt: int) -> FeedbackResult:
        return FeedbackResult(
            "trial",
            "stream",
            1,
            sequence,
            receipt,
            10,
            20,
            "valid",
            (("forward", 1.0),),
            str(sequence),
        )

    dispositions = consumer.consume((result(1, 1_000), result(2, 1_000)))
    assert [item.disposition for item in dispositions] == ["applied", "stale"]
    assert len(target.applied) == 1


def test_boundary_sweep_slides_and_does_not_cross_wall() -> None:
    walls = inset_convex_polygon(
        ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)), 0.0
    )
    position, applied, constrained = slide_displacement(
        (5.0, 5.0), (10.0, 3.0), walls, tolerance=1e-9
    )
    assert constrained
    assert position[0] == pytest.approx(10.0)
    assert position[1] == pytest.approx(8.0)
    assert applied == pytest.approx((5.0, 3.0))


def test_boundary_rejects_invalid_polygon_and_nonfinite_motion() -> None:
    with pytest.raises(ValueError, match="counterclockwise"):
        inset_convex_polygon(((0, 0), (0, 1), (1, 0)), 0)
    walls = inset_convex_polygon(((0, 0), (2, 0), (2, 2), (0, 2)), 0)
    with pytest.raises(ValueError, match="finite"):
        slide_displacement((1, 1), (float("nan"), 0), walls, tolerance=1e-6)


def test_batch_consumer_returns_immutable_render_group_evidence():
    consumer = FeedbackBatchConsumer(
        make_program(),
        arena_boundaries=SimpleNamespace(bindings=()),
        max_result_age_ns=100,
        clock_ns=lambda: 150,
        attachment_generation="attachment",
        stream_ids=frozenset({"stream"}),
        source_generation="tracking-generation",
    )
    consumer.begin_trial("trial")
    result = FeedbackResult(
        trial_id="trial",
        stream_id="stream",
        reset_generation="1",
        result_sequence=1,
        source_host_receipt_ns=100,
        source_interval_start_ns=None,
        source_interval_end_ns=None,
        validity="valid",
        values=(),
        result_id="feedback-1",
        attachment_generation="attachment",
        source_role="tracking",
        source_generation="tracking-generation",
        source_frame_ids=("camera-frame-1",),
    )
    evidence = consumer.consume(
        (result,),
        SimpleNamespace(instances={}),
        SimpleNamespace(settings=()),
        150,
        0,
        9,
    )
    assert len(evidence) == 1
    assert evidence[0].disposition == "absent"
    assert evidence[0].group_id == 9
    assert evidence[0].source_frame_ids == ("camera-frame-1",)


def test_wire_result_requires_exact_trial_source_and_canonical_generation() -> None:
    entry = data.FeedbackEntry(entry_sequence=2)
    entry.result.source.role = "tracking"
    entry.result.source.generation = "tracking-generation"
    entry.result.work.trial.session.controller_generation = "controller"
    entry.result.work.trial.session.session_id = "session"
    entry.result.work.trial.trial_id = "trial"
    entry.result.stream_id = "stream"
    entry.result.reset_generation = "2"
    entry.result.result_id = "result"
    entry.result.result_sequence = 3
    entry.result.newest_source_frame_id = "frame-1"
    entry.result.source_frame_ids.append("frame-1")
    entry.result.source_host_receipt_ns = 10
    entry.result.validity = data.FEEDBACK_VALIDITY_VALID
    entry.result.values.add(channel_id="forward", value=1)
    decoded = decode_entry(entry, attachment_generation="attachment")
    assert decoded.trial_id == "trial"
    assert decoded.reset_generation == "2"
    assert decoded.source_generation == "tracking-generation"
    entry.result.reset_generation = "02"
    with pytest.raises(ValueError, match="canonical"):
        decode_entry(entry, attachment_generation="attachment")


def test_feedback_credit_is_exact_bounded_and_reset_fenced() -> None:
    credits = FeedbackCredits(
        attachment_generation="attachment", stream_id="stream", capacity=2
    )
    first = credits.capture(reset_generation="1", entry_sequence=1)
    assert credits.available == 1
    assert credits.return_credit(first)
    assert not credits.return_credit(first)
    second = credits.capture(reset_generation="1", entry_sequence=2)
    third = credits.capture(reset_generation="2", entry_sequence=3)
    assert second.reset_generation == "1"
    assert third.reset_generation == "2"
    assert credits.available == 1
    assert not credits.return_credit(second)
    assert credits.return_credit(third)
    assert credits.available == 2
    with pytest.raises(ValueError, match="unknown"):
        credits.return_credit(
            data.FeedbackCredit(
                attachment_generation="attachment",
                stream_id="stream",
                reset_generation="2",
                entry_sequence=44,
            )
        )


class MutableState:
    def __init__(self) -> None:
        self.values = {"phase_x": SimpleNamespace(value=2.0)}
        self.active = True
        self.applied = []

    def apply_feedback(self, target, operation, value, *, now_ns):
        self.applied.append((target, operation, value, now_ns))
        self.values[target].value += value


def test_prepared_mapping_integrates_only_declared_source_interval() -> None:
    mapping = Feedback(
        binding_id="binding",
        source_channel="phase_rate",
        target="phase_x",
        operation="movement_integration",
        gain=Constant(kind="constant", value=2),
        offset=Constant(kind="constant", value=0.5),
    )
    program = SimpleNamespace(
        input_channels=(
            InputChannel(
                channel_id="phase_rate",
                stream_id="stream",
                value_kind="interval_average_rate",
                unit="cycle/s",
                frame_id="world",
            ),
        ),
    )
    target = MutableState()
    trial = SimpleNamespace(instances={"texture": target})
    epoch = SimpleNamespace(
        settings=(SimpleNamespace(instance_id="texture", feedback=(mapping,)),)
    )
    result = FeedbackResult(
        "trial",
        "stream",
        1,
        1,
        1_000,
        1_000,
        1_001_000,
        "valid",
        (("phase_rate", 3.0),),
        "result",
    )
    applier = FeedbackMappingApplier(
        program, arena_boundaries=SimpleNamespace(bindings=())
    )
    applier((result,), trial, epoch, 10_000, 0)
    assert target.applied[0][:2] == ("phase_x", "movement_integration")
    assert target.applied[0][2] == pytest.approx(0.0065)
    assert target.applied[0][3] == 10_000
    assert target.values["phase_x"].value == pytest.approx(2.0065)


class _HandshakePipe:
    def __init__(self, challenge, accepted):
        self.received = [challenge.SerializeToString(), accepted.SerializeToString()]
        self.sent = []

    def send_bytes(self, payload, *, deadline_ns):
        self.sent.append(payload)

    def recv_bytes(self, *, deadline_ns):
        return self.received.pop(0)


class _FakePipeAPI:
    def CreateFileW(self, *args):
        return 123

    def SetNamedPipeHandleState(self, *args):
        return True

    def CloseHandle(self, handle):
        return True


def test_named_pipe_client_authenticates_nonce_and_process_instance():
    from cephvr.platform.windows.message_pipe import open_message_pipe

    nonce = b"descriptor-startup-nonce"
    challenge = native_transport_pb2.PipeHandshake(
        protocol_version=1, process_instance_id="tracking-id", startup_nonce=nonce
    )
    accepted = native_transport_pb2.PipeHandshake(
        protocol_version=1,
        process_instance_id="tracking-id",
        startup_nonce=nonce,
        accepted=True,
    )
    pipe = _HandshakePipe(challenge, accepted)
    opened = open_message_pipe(
        SimpleNamespace(owner_process_instance_id="visual-stimulus-id"),
        name=r"\\.\pipe\cephvr-feedback",
        role="client",
        expected_peer_instance_id="tracking-id",
        startup_nonce=nonce,
        maximum_message_bytes=1024,
        deadline_ns=10**30,
        _api=_FakePipeAPI(),
        _pipe_factory=lambda *args, **kwargs: pipe,
    )
    assert opened is pipe
    hello = native_transport_pb2.PipeHandshake.FromString(pipe.sent[0])
    assert hello.process_instance_id == "visual-stimulus-id"
    assert hello.startup_nonce == nonce
    assert not hello.accepted

    bad = _HandshakePipe(
        native_transport_pb2.PipeHandshake(
            protocol_version=1, process_instance_id="other", startup_nonce=nonce
        ),
        accepted,
    )
    with pytest.raises(RuntimeError, match="identity or startup nonce"):
        open_message_pipe(
            SimpleNamespace(owner_process_instance_id="visual-stimulus-id"),
            name=r"\\.\pipe\cephvr-feedback",
            role="client",
            expected_peer_instance_id="tracking-id",
            startup_nonce=nonce,
            maximum_message_bytes=1024,
            deadline_ns=10**30,
            _api=_FakePipeAPI(),
            _pipe_factory=lambda *args, **kwargs: bad,
        )


class _ResultPipe:
    def __init__(self, payload):
        self.payload = payload
        self.cancelled = threading.Event()

    def recv_bytes(self, *, deadline_ns):
        if self.payload is not None:
            payload, self.payload = self.payload, None
            return payload
        self.cancelled.wait(0.01)
        raise TimeoutError

    def request_cancel(self):
        self.cancelled.set()

    def close_after_io(self, *, deadline_ns):
        return None


class _CreditPipe:
    def __init__(self):
        self.sent = []

    def send_bytes(self, payload, *, deadline_ns):
        self.sent.append(payload)

    def request_cancel(self):
        return None

    def close_after_io(self, *, deadline_ns):
        return None


class _RetryClosePipe(_ResultPipe):
    def __init__(self):
        super().__init__(None)
        self.close_attempts = 0

    def close_after_io(self, *, deadline_ns):
        self.close_attempts += 1
        if self.close_attempts == 1:
            raise OSError("injected close failure")


def test_pipe_consumer_captures_finite_batch_then_returns_exact_credit():
    entry = data.FeedbackEntry(entry_sequence=1)
    entry.result.source.role = "tracking"
    entry.result.source.generation = "tracking-generation"
    entry.result.work.trial.session.controller_generation = "controller"
    entry.result.work.trial.session.session_id = "session"
    entry.result.work.trial.trial_id = "trial"
    entry.result.stream_id = "stream"
    entry.result.reset_generation = "1"
    entry.result.result_id = "result"
    entry.result.result_sequence = 1
    entry.result.source_host_receipt_ns = 10
    entry.result.validity = data.FEEDBACK_VALIDITY_VALID
    entry.result.source_frame_ids.append("frame-1")
    result_pipe = _ResultPipe(entry.SerializeToString())
    credit_pipe = _CreditPipe()
    opened = []
    announced = []

    def opener(key, **kwargs):
        opened.append((key, kwargs))
        return result_pipe if kwargs["name"].endswith("results") else credit_pipe

    attachment = runtime_pb2.FeedbackAttachment(
        attachment_generation="attachment",
        result_pipe=r"\\.\pipe\cephvr-results",
        credit_pipe=r"\\.\pipe\cephvr-credits",
        startup_nonce=b"nonce",
        source_process_instance_id="tracking-generation",
        stream_ids=["stream"],
        queue_capacity=2,
        maximum_message_bytes=4096,
    )
    consumer = FeedbackPipeConsumer(
        attachment,
        local_process_instance_id="visual-stimulus-generation",
        resource_key_factory=lambda kind, owner: (kind, owner),
        open_pipe=opener,
        announce=announced.append,
        selected_stream_ids=("stream",),
        deadline_ns=10**30,
        clock_ns=lambda: 1,
    )
    try:
        for _ in range(100):
            if consumer._results.qsize():
                break
            threading.Event().wait(0.001)
        batch = consumer.capture_batch()
        assert len(batch) == 1
        assert batch[0].entry_sequence == 1
        for _ in range(100):
            if credit_pipe.sent:
                break
            threading.Event().wait(0.001)
        assert len(credit_pipe.sent) == 1
        returned = data.FeedbackCredit.FromString(credit_pipe.sent[0])
        assert returned.attachment_generation == "attachment"
        assert returned.stream_id == "stream"
        assert returned.reset_generation == "1"
        assert returned.entry_sequence == 1
        assert announced == ["feedback-result-pipe", "feedback-credit-pipe"]
        assert len(opened) == 2
    finally:
        consumer.close(deadline_ns=2_000_000_000)


def test_partial_pipe_open_retains_owner_when_cleanup_fails():
    result_pipe = _RetryClosePipe()
    attachment = runtime_pb2.FeedbackAttachment(
        attachment_generation="attachment",
        result_pipe="results",
        credit_pipe="credits",
        startup_nonce=b"nonce",
        source_process_instance_id="tracking-generation",
        stream_ids=["stream"],
        queue_capacity=2,
        maximum_message_bytes=4096,
    )

    def opener(key, **kwargs):
        if kwargs["name"] == "credits":
            raise OSError("injected credit open failure")
        return result_pipe

    with pytest.raises(FeedbackPipeConstructionError) as raised:
        FeedbackPipeConsumer(
            attachment,
            local_process_instance_id="visual-stimulus-generation",
            resource_key_factory=lambda kind, owner: (kind, owner),
            open_pipe=opener,
            announce=lambda resource: None,
            selected_stream_ids=("stream",),
            deadline_ns=10**30,
            clock_ns=lambda: 1,
        )
    owner = raised.value.consumer
    assert not owner.closed
    owner.close(deadline_ns=10**30)
    assert owner.closed
    assert result_pipe.close_attempts == 2


@pytest.mark.parametrize("yaw", (0.0, 90.0))
@pytest.mark.parametrize(
    "forward_gain,sideways_gain", ((2, 3), (0, 3), (2, 0), (2, None), (2, -3))
)
def test_planar_mapping_independent_gains_and_legacy_fallback(
    yaw, forward_gain, sideways_gain
):
    import math

    from cephvr.visual_stimulus.config.models.program_model import (
        ArenaSettings,
        PlanarFeedback,
    )

    mapping = PlanarFeedback(
        binding_id="walk",
        operation="heading_relative_planar_integration",
        forward_channel="forward",
        sideways_channel="sideways",
        gain=Constant(kind="constant", value=forward_gain),
        sideways_gain=None
        if sideways_gain is None
        else Constant(kind="constant", value=sideways_gain),
    )
    program = SimpleNamespace(
        input_channels=tuple(
            InputChannel(
                channel_id=name,
                stream_id="stream",
                value_kind="interval_average_rate",
                unit="px/s",
                frame_id="anatomical_body",
            )
            for name in ("forward", "sideways")
        )
    )
    target = MutableState()
    target.values = {
        key: SimpleNamespace(value=value)
        for key, value in (("x", 0.0), ("y", 0.0), ("yaw", yaw))
    }
    target.advance = lambda now_ns: None
    trial = SimpleNamespace(instances={"arena": target})
    region = SimpleNamespace(
        kind="convex_polygon_xy",
        vertices_mm=(
            (-100.0, -100.0),
            (100.0, -100.0),
            (100.0, 100.0),
            (-100.0, 100.0),
        ),
        margin_mm=0.0,
    )
    applier = FeedbackMappingApplier(
        program,
        arena_boundaries=SimpleNamespace(
            bindings=(SimpleNamespace(instance_id="arena", region=region),)
        ),
    )
    epoch = SimpleNamespace(
        settings=(
            ArenaSettings.model_construct(
                instance_id="arena", world_frame_id="world", feedback=(mapping,)
            ),
        )
    )
    result = FeedbackResult(
        "trial",
        "stream",
        1,
        1,
        1,
        0,
        500_000_000,
        "valid",
        (("forward", 4.0), ("sideways", 6.0)),
        "result",
    )
    evidence = applier((result,), trial, epoch, 500_000_000, 0)
    f = 4 * forward_gain * 0.5
    lateral = 6 * (forward_gain if sideways_gain is None else sideways_gain) * 0.5
    angle = math.radians(yaw)
    expected = (
        -math.sin(angle) * f - math.cos(angle) * lateral,
        math.cos(angle) * f - math.sin(angle) * lateral,
    )
    assert evidence[0].requested_increment == pytest.approx(expected)
    assert evidence[0].applied_increment == pytest.approx(expected)
    assert (target.values["x"].value, target.values["y"].value) == pytest.approx(
        expected
    )
