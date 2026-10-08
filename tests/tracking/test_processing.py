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


def test_preprocessing_keeps_native_precision_and_inverts_pixel_centres():
    import numpy as np

    from cephvr.tracking.processing.preprocessing import resolve_transform

    transform = resolve_transform(
        5, 3, crop_enabled=True, crop=(1, 0, 3, 3), scale_percent=50
    )
    assert (transform.output_width, transform.output_height) == (2, 2)
    assert transform.source_to_output((2.0, 1.0)) == (0.5, 0.5)
    assert transform.output_to_source((0.5, 0.5)) == (2.0, 1.0)
    source = np.arange(15, dtype=np.uint16).reshape(3, 5) * 256
    original = source.copy()
    output = np.empty((2, 2), dtype=np.uint16)
    transform.apply(source, output)
    assert output.dtype == source.dtype
    assert np.array_equal(source, original)
    assert np.all(output <= source.max())
    with pytest.raises(ValueError, match="exceeds the acquired image"):
        resolve_transform(5, 3, crop_enabled=True, crop=(4, 0, 3, 3))


def test_downscaled_flow_grid_rejects_insufficient_setup_neighbours():
    from types import SimpleNamespace

    from cephvr.tracking.processing.session import _validate_flow_grid

    flow = SimpleNamespace(output_grid_px=4)
    estimator = SimpleNamespace(quality=SimpleNamespace(minimum_neighbors=4))
    with pytest.raises(ValueError, match="too small for the selected flow grid"):
        _validate_flow_grid(
            ImageLayout(8, 8, 8, "gray", "uint8", 8, "lsb", 0, 255, "small"),
            flow,
            estimator,
        )


def test_automatic_reference_dimensions_match_acquired_source_before_transform():
    from cephvr.tracking.processing.session import _validate_source_reference
    from cephvr.tracking.v1 import pose_pb2

    source_layout = ImageLayout(
        200, 200, 200, "gray", "uint8", 8, "lsb", 0, 255, "acquired"
    )
    reference = pose_pb2.SubjectReferenceSettings(
        image_width_px=100,
        image_height_px=100,
        anterior=pose_pb2.ImagePoint(x_px=90, y_px=50),
        posterior=pose_pb2.ImagePoint(x_px=10, y_px=50),
        medial_left=pose_pb2.ImagePoint(x_px=50, y_px=30),
        medial_right=pose_pb2.ImagePoint(x_px=50, y_px=70),
    )
    with pytest.raises(ValueError, match="differ from the acquired source"):
        _validate_source_reference(reference, source_layout)


def test_ring_source_publishes_transformed_private_frame_without_source_mutation():
    from types import SimpleNamespace
    from uuid import UUID, uuid4

    import cv2
    import numpy as np

    from cephvr.tracking.processing.preprocessing import resolve_transform
    from cephvr.tracking.processing.source import RingSource

    source_pixels = (np.arange(15, dtype="<u2").reshape(3, 5) * 256).copy()
    transform = resolve_transform(
        5, 3, crop_enabled=True, crop=(1, 0, 3, 3), scale_percent=50
    )
    processed_layout = ImageLayout(
        2, 2, 4, "gray", "uint16", 12, "msb", 0, 4095, "transformed"
    )
    source_layout = ImageLayout(
        5, 3, 10, "gray", "uint16", 12, "msb", 0, 4095, "source"
    )
    work = WorkContext()
    work.trial.trial_id = str(uuid4())

    class FakeRing:
        def read_into(self, sequence, target, *, expected_run_id):
            assert sequence == 0 and expected_run_id == UUID(work.trial.trial_id)
            target[:] = source_pixels.tobytes()
            return SimpleNamespace(
                status="frame",
                sequence=0,
                record=SimpleNamespace(frame_id=12, acquisition_time_ns=90),
                discontinuity_epoch=0,
            )

    class FakeConverter:
        def prepare_source_depth_into(self, source, destination):
            destination[:] = source

    source = object.__new__(RingSource)
    source.pool = FramePool(processed_layout, 1, 8, transform)
    source.ring = FakeRing()
    source.converter = FakeConverter()
    source.sequence = source.epoch = 0
    source.scratch = bytearray(source_pixels.nbytes)
    source.native_scratch = bytearray(source_pixels.nbytes)
    source.source_layout = source_layout
    source.layout = processed_layout
    source.transform = transform

    frame, gap = source.read(work, "generation")

    assert not gap and frame is not None
    assert frame.source.frame_id == 12 and frame.transform is transform
    actual = np.frombuffer(frame.pixels, dtype="<u2").reshape(2, 2)
    expected = cv2.resize(source_pixels[:, 1:4], (2, 2), interpolation=cv2.INTER_AREA)
    assert np.array_equal(actual, expected)
    assert np.array_equal(source_pixels, np.arange(15, dtype="<u2").reshape(3, 5) * 256)
    source.pool.release(frame)


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
        pixels_per_mm=2,
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
            pixels_per_mm=2,
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


@pytest.mark.parametrize("pixels_per_mm", [0.0, -1.0, float("nan"), float("inf")])
def test_physical_output_rejects_unusable_camera_scale(pixels_per_mm):
    from cephvr.tracking.config.models.records import DriveTriplet
    from cephvr.tracking.processing.physical_units import physical_drive

    with pytest.raises(ValueError, match="camera pixels_per_mm"):
        physical_drive(
            DriveTriplet(forward_drive=1.0, sideways_drive=2.0, turn_drive=3.0),
            pixels_per_mm,
        )


def test_movement_records_and_publishes_calibrated_units_preserving_pixel_evidence():
    import json
    import math
    from types import SimpleNamespace

    from cephvr.control.v1.types_pb2 import ProcessIdentity
    from cephvr.tracking.config.models.records import FlowProxyEvidence
    from cephvr.tracking.processing.movement import Movement, MovementPorts

    records, published = [], []
    gate = TrialGate(lambda record: records.append(record) or True)
    work = WorkContext()
    gate.begin(work, "prepared", "attached", 1, 200, 1)
    pool = FramePool(ImageLayout(2, 2, 2, "gray", "uint8", 8, "lsb", 0, 255, "x"), 1, 4)
    slot, pixels = pool.acquire()
    pixels.release()
    frame = pool.publish(slot, SourceFrame(frame_id=2, host_receipt_ns=90), work, "1")
    ports = MovementPorts(
        source=SimpleNamespace(pool=pool),
        flow=None,
        estimator=None,
        gate=gate,
        history=PoseHistory(1),
        pose=None,
        manual_geometry=None,
        feedback=SimpleNamespace(
            before_result=lambda _: None, publish=published.append
        ),
        identity=ProcessIdentity(),
        stream_id="water_flow",
        maximum_frame_age_ns=50,
        maximum_pose_age_ns=50,
        movement_timeout_ns=20,
        first_evaluation=lambda *_: None,
        pixels_per_mm=2.0,
    )
    movement = Movement(ports, clock=lambda: 100)
    movement.baseline = SimpleNamespace(
        source=SourceFrame(frame_id=1, host_receipt_ns=80)
    )
    controls = dict(forward_drive=-100.0, sideways_drive=20.0, turn_drive=-math.pi / 2)
    evidence = FlowProxyEvidence.model_validate_json(
        json.dumps(
            dict(
                schema_version=1,
                pipeline_id="water_flow",
                validity="valid",
                reason=None,
                sections=[
                    dict(
                        section_index=0,
                        intended_area_px2=1.0,
                        visible_area_px2=1.0,
                        accepted_area_px2=1.0,
                    )
                ],
                counts=dict(
                    selected=1,
                    unavailable=0,
                    nonfinite=0,
                    cost_rejected=0,
                    neighbor_unevaluable=0,
                    median_rejected=0,
                    accepted=1,
                ),
                centroid_body_px=[0.0, 0.0],
                mean_velocity_body_px_per_s=[100.0, -20.0],
                centred_moment_px2_per_s=math.pi / 2,
                centred_second_moment_px2=1.0,
                raw=controls,
                filtered_average=controls,
                filter_end=controls,
                filter_disposition="seeded",
            )
        )
    )
    use, _ = movement._pose(frame)
    movement._commit(frame, evidence, "valid", use)
    saved = records[-1].model_dump(mode="json")["record"]
    assert {v.channel_id: v.value for v in published[0].values} == pytest.approx(
        dict(forward_drive=-50.0, sideways_drive=10.0, turn_drive=-90.0)
    )
    assert {
        v["channelId"]: v["value"] for v in saved["feedback_result"]["values"]
    } == pytest.approx(dict(forward_drive=-50.0, sideways_drive=10.0, turn_drive=-90.0))
    assert saved["stage_evidence"][-1]["payload"]["filtered_average"] == controls
    assert published[0].interval_start_ns == 80 and published[0].interval_end_ns == 90
    pool.release(frame)
    assert pool.idle()
