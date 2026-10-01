"""Finite ownership, completed pose selection and feedback reset contracts."""

from uuid import uuid4

import pytest

from cephvr.control.v1.types_pb2 import WorkContext
from cephvr.tracking.config.models.records import PoseObservation, SourceFrame
from cephvr.tracking.feedback.delivery import FeedbackDelivery
from cephvr.tracking.processing.frames import FramePool
from cephvr.tracking.processing.gate import TrialGate
from cephvr.tracking.processing.history import PoseHistory
from cephvr.tracking.types import ImageLayout, PoseGeometryObservation
from cephvr.visual_stimulus.v1 import data_pb2 as wire


def test_private_frame_is_not_reused_while_pose_holds_it():
    pool = FramePool(ImageLayout(2, 2, 2, "gray", "uint8", 8, "lsb", 0, 255, "x"), 1, 4)
    slot, writable = pool.acquire()
    writable[:] = b"1234"
    writable.release()
    frame = pool.publish(
        slot, SourceFrame(frame_id=0, host_receipt_ns=1), WorkContext(), "1"
    )
    pool.retain(frame)
    pool.release(frame)
    assert pool.acquire() is None and frame.pixels.readonly
    pool.release(frame)
    assert pool.acquire() is not None
    with pytest.raises(ValueError, match="retired"):
        pool.release(frame)
    pool.cancel(slot)
    assert pool.idle()


def observation(work, frame, timestamp):
    return PoseGeometryObservation(
        work,
        "prepared",
        "attached",
        PoseObservation(
            kind="pose",
            observation_id=str(uuid4()),
            reset_generation="1",
            source=SourceFrame(frame_id=frame, host_receipt_ns=timestamp),
            completion_host_ns=timestamp + 1,
            method="threshold_contour",
            validity="invalid",
            reason="no_candidate",
            landmarks=None,
            eligible_candidate_count=0,
            selected_score=None,
            top_score_tie=False,
            disposition="published",
        ),
        None,
    )


def test_history_keeps_invalid_selection_age_boundary_and_borrowed_retirement():
    work = WorkContext()
    work.trial.trial_id = str(uuid4())
    history = PoseHistory(1)
    first = observation(work, 1, 100)
    history.publish(first)
    use, held = history.select(work, "prepared", "attached", 1, 110, 10)
    assert use.disposition == "invalid" and held is first
    history.publish(observation(work, 2, 120))
    assert not history.take_retired()
    history.release(first)
    assert history.take_retired() == (first,)
    use, held = history.select(work, "prepared", "attached", 1, 140, 10)
    assert use.disposition == "missing" and held is None  # No future pose.
    use, held = history.select(work, "prepared", "attached", 2, 131, 10)
    assert use.disposition == "stale"
    history.release(held)
    history.clear()
    assert len(history.take_retired()) == 1


def test_credit_overflow_changes_delivery_only_and_preserves_inflight_owner():
    records = []
    gate = TrialGate(lambda record: records.append(record) is None)
    gate.begin(WorkContext(), "prepared", "attached", 1, 100, 1)
    delivery = FeedbackDelivery("attached", "water_flow", 1, 4096, gate)
    delivery.publish(wire.FeedbackResult(reset_generation="1", result_id="one"))
    active = delivery.take(0)
    delivery.before_result(2)
    assert gate.delivery_generation == 2 and gate.processing_generation == "1"
    assert delivery.inflight is active
    delivery.publish(wire.FeedbackResult(reset_generation="2", result_id="two"))
    assert not delivery.credit(
        wire.FeedbackCredit(
            attachment_generation="attached",
            stream_id="water_flow",
            reset_generation="1",
            entry_sequence=1,
        )
    )
    delivery.written(active)
    second = delivery.take(0)
    assert second.result.result_id == "two"
    assert delivery.credit(
        wire.FeedbackCredit(
            attachment_generation="attached",
            stream_id="water_flow",
            reset_generation="2",
            entry_sequence=2,
        )
    )
    delivery.written(second)
    delivery.seal(3)
    assert records[-1].record.kind == "reset"


def test_history_clear_waits_for_every_borrow_and_rejects_double_return():
    work = WorkContext()
    history = PoseHistory(2)
    value = observation(work, 1, 100)
    history.publish(value)
    for _ in range(2):
        assert history.select(work, "prepared", "attached", 1, 101, 10)[1] is value
    history.clear()
    assert history.select(work, "prepared", "attached", 1, 101, 10)[1] is None
    assert history.take_retired() == ()
    history.release(value)
    assert history.take_retired() == ()
    history.release(value)
    assert history.take_retired() == (value,)
    assert history.take_retired() == ()
    with pytest.raises(ValueError, match="unknown or already returned"):
        history.release(value)


@pytest.mark.parametrize("fail_compute", [False, True])
def test_pose_retirement_and_close_stay_on_owner_thread_after_failure(fail_compute):
    import threading
    from dataclasses import replace

    from cephvr.tracking.processing.pose import PoseOperations, PoseWorker

    work = WorkContext()
    gate = TrialGate(lambda record: True)
    gate.begin(work, "prepared", "attached", 1, 100, 1)
    pool = FramePool(ImageLayout(2, 2, 2, "gray", "uint8", 8, "lsb", 0, 255, "x"), 1, 4)
    history = PoseHistory(1)
    geometries = (object(), object())
    for index, geometry in enumerate(geometries):
        history.publish(replace(observation(work, index, index + 1), geometry=geometry))
    events = []
    computed = threading.Event()

    def compute(frame):
        computed.set()
        raise RuntimeError("pose computation failed")

    def close(deadline):
        events.append(("close", deadline, threading.get_ident()))
        return True

    worker = PoseWorker(
        lambda: PoseOperations(
            compute,
            lambda landmarks: None,
            lambda geometry: events.append(
                ("release", geometry, threading.get_ident())
            ),
            close,
            "threshold_contour",
        ),
        pool,
        history,
        gate,
        failure_close=lambda deadline: False,
        clock=lambda: 10,
    )
    try:
        worker.ready.result(timeout=1)
        if fail_compute:
            slot, pixels = pool.acquire()
            pixels.release()
            frame = pool.publish(
                slot, SourceFrame(frame_id=2, host_receipt_ns=5), work, "1"
            )
            worker.offer(frame)
            pool.release(frame)
            assert computed.wait(1)
    finally:
        assert worker.close(1_000_000_010)
    assert [(kind, value) for kind, value, _ in events] == [
        ("release", geometries[0]),
        ("release", geometries[1]),
        ("close", 1_000_000_010),
    ]
    assert all(owner == worker.thread.ident for _, _, owner in events)
    assert bool(worker.failure) == fail_compute
    assert pool.idle()


@pytest.mark.parametrize(
    "cause,has_frame",
    [
        ("input_overflow", False),
        ("input_overflow", True),
        ("input_age", True),
        ("camera_gap", True),
    ],
)
def test_movement_input_reset_preserves_evidence_order_and_pose_history(
    cause, has_frame
):
    from types import SimpleNamespace

    from cephvr.control.v1.types_pb2 import ProcessIdentity
    from cephvr.tracking.processing.movement import Movement, MovementPorts

    events = []
    records = []

    def admit(record):
        records.append(record.record)
        events.append(record.record.kind)
        return True

    gate = TrialGate(admit)
    work = WorkContext()
    gate.begin(work, "prepared", "attached", 1, 200, 1)
    pool = FramePool(ImageLayout(2, 2, 2, "gray", "uint8", 8, "lsb", 0, 255, "x"), 2, 8)

    def frame(frame_id, receipt):
        slot, pixels = pool.acquire()
        pixels.release()
        return pool.publish(
            slot, SourceFrame(frame_id=frame_id, host_receipt_ns=receipt), work, "1"
        )

    baseline = frame(1, 80)
    incoming = frame(3, 10 if cause == "input_age" else 90) if has_frame else None
    history = PoseHistory(1)
    pose = observation(work, 1, 80)
    history.publish(pose)
    delivery = FeedbackDelivery("attached", "water_flow", 2, 4096, gate)
    delivery.publish(wire.FeedbackResult(reset_generation="1", result_id="pending"))

    def reset_flow(generation):
        assert generation == "2"
        assert not pool.idle()  # The prior baseline still owns its slot here.
        if incoming is not None:
            with pytest.raises(ValueError, match="retired"):
                pool.retain(incoming)
        events.append("flow_reset")

    def latest():
        assert pool.idle()
        events.append("latest")
        gate.seal(100)

    ports = MovementPorts(
        source=SimpleNamespace(
            pool=pool,
            begin=lambda: None,
            read=lambda *_: (incoming, cause == "input_overflow"),
            latest=latest,
        ),
        flow=SimpleNamespace(reset=reset_flow),
        estimator=SimpleNamespace(
            reset=lambda generation: events.append(("estimator_reset", generation))
        ),
        gate=gate,
        history=history,
        pose=None,
        manual_geometry=None,
        feedback=delivery,
        identity=ProcessIdentity(),
        stream_id="water_flow",
        maximum_frame_age_ns=50,
        maximum_pose_age_ns=50,
        movement_timeout_ns=20,
        first_evaluation=lambda *_: pytest.fail(
            "discarded input cannot start activity"
        ),
    )
    movement = Movement(ports, clock=lambda: 100)
    movement.baseline = baseline
    records.clear()
    events.clear()
    movement.run()
    assert events == (["discard"] if has_frame else []) + [
        "discard",
        "reset",
        "flow_reset",
        ("estimator_reset", "2"),
        "latest",
    ]
    assert records[-1].causes == (cause,)
    assert records[-1].reset_generation == "2"
    assert all(record.observed_host_ns == 100 for record in records)
    assert records[-2].target == "result" and records[-2].ids == ("pending",)
    if has_frame:
        assert records[0].target == "source_frame" and records[0].ids == ("3",)
    assert all(
        record.reset_generation == "1" and record.reason == cause
        for record in records[:-1]
    )
    assert gate.processing_generation == "2" and gate.end == 200
    assert movement.baseline is None and pool.idle()
    assert history.select(work, "prepared", "attached", 3, 100, 50)[1] is pose
    history.release(pose)


@pytest.mark.parametrize(
    "outcome", ["accepted", "record_failure", "stale_generation", "cutoff"]
)
def test_movement_commit_records_before_feedback_and_first_activity(outcome):
    from types import SimpleNamespace

    from cephvr.control.v1.types_pb2 import ProcessIdentity
    from cephvr.tracking.processing.movement import Movement, MovementPorts

    events = []

    def admit(record):
        events.append(record.record.kind)
        return outcome != "record_failure" or record.record.kind != "result"

    gate = TrialGate(admit)
    work = WorkContext()
    gate.begin(work, "prepared", "attached", 1, 200, 1)
    pool = FramePool(ImageLayout(2, 2, 2, "gray", "uint8", 8, "lsb", 0, 255, "x"), 1, 4)
    slot, pixels = pool.acquire()
    pixels.release()
    frame = pool.publish(slot, SourceFrame(frame_id=1, host_receipt_ns=90), work, "1")
    movement = Movement(
        MovementPorts(
            source=SimpleNamespace(pool=pool),
            flow=None,
            estimator=None,
            gate=gate,
            history=PoseHistory(1),
            pose=None,
            manual_geometry=None,
            feedback=SimpleNamespace(
                before_result=lambda now: events.append("before"),
                publish=lambda result: events.append("publish"),
            ),
            identity=ProcessIdentity(),
            stream_id="water_flow",
            maximum_frame_age_ns=50,
            maximum_pose_age_ns=50,
            movement_timeout_ns=20,
            first_evaluation=lambda *_: events.append("first"),
        ),
        clock=lambda: 100,
    )
    if outcome == "stale_generation":
        gate.reset(("camera_gap",), 99)
    elif outcome == "cutoff":
        gate.seal(99)
    use, _ = movement._pose(frame)
    events.clear()
    try:
        if outcome == "record_failure":
            with pytest.raises(RuntimeError, match="evidence admission failed"):
                movement._commit(frame, None, "baseline_only", use)
            assert events == ["before", "result"] and not movement.first
        elif outcome == "accepted":
            movement._commit(frame, None, "baseline_only", use)
            assert events == ["before", "result", "publish", "first"]
            events.clear()
            movement._commit(frame, None, "baseline_only", use)
            assert events == ["before", "result", "publish"]
            assert movement.result_sequence == 2
        else:
            movement._commit(frame, None, "baseline_only", use)
            assert events == ["discard"] and movement.result_sequence == 0
            assert not movement.first
    finally:
        pool.release(frame)
    assert pool.idle()
