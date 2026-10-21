"""Standalone preview clock and painter checks without a Dashboard/device fixture."""

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from cephvr.gui import preview_timeline
from cephvr.gui.preview_motion_dial import dial_readout, rotation_text, vector_text
from cephvr.gui.preview_motion_plot import time_window
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.protocol_document import review_program
from cephvr.gui.theme import colors_for
from cephvr.visual_stimulus.config.models.program_model import (
    ArenaMotion,
    ArenaSettings,
    Constant,
    Feedback,
    Hold,
    Pose,
    Ramp,
    Rate,
    Trajectory,
)


def constant(value):
    return Constant(kind="constant", value=value)


def with_settings(*epochs):
    """Replace the review fixture's three epochs' settings, keeping their timing."""
    program = review_program()
    return program.model_copy(
        update={
            "sequence": tuple(
                epoch.model_copy(update={"settings": settings})
                for epoch, settings in zip(program.sequence, epochs, strict=True)
            )
        }
    )


def arena(x=-20.0, yaw=0.0, *, reset=False, feedback=()):
    return ArenaSettings(
        kind="arena",
        instance_id="world",
        asset_id="arena",
        world_frame_id="world",
        asset_to_world=((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)),
        initial=Pose(position_mm=(0, 0), yaw_deg=90),
        fixed_height_mm=10,
        fixed_pitch_deg=0,
        fixed_roll_deg=0,
        motion=ArenaMotion(
            x=Rate(kind="rate", function=constant(x)),
            y=Hold(kind="hold"),
            yaw=Rate(kind="rate", function=constant(yaw)),
        ),
        reset=reset,
        assignments=(),
        feedback=feedback,
    )


@pytest.fixture
def timeline():
    app = QApplication.instance() or QApplication([])
    widget = StimulusTimeline()
    widget.resize(1300, 420)
    widget.set_program(review_program(), "", "Trial")
    widget.show()
    app.processEvents()
    yield widget
    widget.timer.stop()
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_timeline_construction_does_not_show_a_detached_notice():
    app = QApplication.instance() or QApplication([])
    visible_before = {widget for widget in app.topLevelWidgets() if widget.isVisible()}
    timeline = StimulusTimeline()
    try:
        app.processEvents()
        assert {widget for widget in app.topLevelWidgets() if widget.isVisible()} == (
            visible_before
        )
        assert timeline.notice.parentWidget() is timeline.instrument_host
        assert not timeline.notice.isWindow()
        timeline.set_advanced(True)
        app.processEvents()
        assert not timeline.notice.isVisible()
        timeline.clear("")
        timeline.show()
        app.processEvents()
        assert timeline.notice.isVisible()
        assert timeline.notice.window() is timeline
        timeline.set_advanced(False)
        assert not timeline.notice.isVisible()
    finally:
        timeline.timer.stop()
        timeline.notice.hide()
        timeline.close()
        timeline.deleteLater()
        app.processEvents()


@pytest.mark.parametrize(
    "elapsed, expected",
    [
        (None, (0, 60)),
        (0, (0, 60)),
        (12, (0, 60)),
        (30, (0, 60)),
        (45, (15, 75)),
        (60.5, (30.5, 90.5)),
    ],
)
def test_time_window_pins_start_then_centers_current_time(elapsed, expected):
    assert time_window(elapsed) == expected


@pytest.mark.parametrize(
    "elapsed, label",
    [
        (0, "Epoch 1 / 3"),
        (12, "Epoch 2 / 3"),
        (60, "Epoch 3 / 3"),
        (None, "Epoch — / 3"),
    ],
)
def test_epoch_timeline_reports_current_epoch_progress(timeline, elapsed, label):
    timeline.set_elapsed(elapsed)
    assert timeline.epoch_label.text() == label
    assert timeline.epoch_label.mapTo(timeline, QPoint()).y() < (
        timeline.epoch_timeline.mapTo(timeline, QPoint()).y()
    )
    assert timeline.epoch_timeline.elapsed == timeline.size_lane.elapsed == elapsed


def test_clock_advances_at_five_hz_and_stops_with_reported_state(timeline, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(preview_timeline, "monotonic", lambda: now[0])
    assert timeline.timer.interval() == 200
    assert timeline.timer.timerType() == Qt.TimerType.PreciseTimer
    timeline.set_playback(12, running=True)
    now[0] += 0.2
    timeline.timer.timeout.emit()
    assert timeline.elapsed == pytest.approx(12.2)
    timeline.set_playback(13, running=True)
    now[0] += 0.2
    timeline.timer.timeout.emit()
    assert timeline.elapsed == pytest.approx(13.2)
    now[0] += 100
    timeline.timer.timeout.emit()
    assert timeline.elapsed == 60
    timeline.set_playback(14, running=False)
    now[0] += 1
    timeline.timer.timeout.emit()
    assert timeline.elapsed == 14
    timeline.set_playback(None, running=False)
    timeline.timer.timeout.emit()
    assert timeline.elapsed is None


def test_advanced_previews_default_hidden_and_toggle_instruments(timeline):
    app = QApplication.instance()
    assert not timeline.advanced
    assert timeline.dial_area.isHidden() and timeline.size_lane.isHidden()
    timeline.set_advanced(True)
    app.processEvents()
    assert timeline.dial_area.isVisible() and len(timeline.dials) == 1
    timeline.set_advanced(False)
    assert timeline.dial_area.isHidden()
    # The plan and legend stay intact while instruments are hidden.
    assert timeline.toggles and timeline.epochs


@pytest.mark.parametrize("stacked", [False, True])
def test_source_controls_belong_to_motion_plots_not_timeline(timeline, stacked):
    app = QApplication.instance()
    timeline.set_stacked(stacked)
    timeline.set_advanced(True)
    app.processEvents()
    toggle = next(iter(timeline.toggles.values()))
    assert timeline.motion_section.isAncestorOf(toggle)
    assert timeline.motion_section.isAncestorOf(timeline.dial_area)
    assert not timeline.motion_section.isAncestorOf(timeline.epoch_timeline)
    assert toggle.mapTo(timeline.motion_section, QPoint()).y() < timeline.dial_area.y()
    epochs = timeline.epochs
    toggle.setChecked(False)
    assert timeline.epochs == epochs
    assert not timeline.dial_samples
    assert timeline.epoch_timeline.isVisible()
    assert toggle.isVisible()
    toggle.setChecked(True)
    assert timeline.dial_samples
    timeline.set_advanced(False)
    assert not toggle.isVisible()
    assert timeline.epoch_timeline.isVisible()


def test_texture_dial_speed_is_arrow_length_at_fractional_endpoint(timeline):
    program = review_program()
    epoch = program.sequence[1]
    setting = epoch.settings[0].model_copy(
        update={
            "phase_x": Rate(
                kind="rate", function=Ramp(kind="ramp", initial=1, slope_per_s=2)
            )
        }
    )
    program = with_settings(program.sequence[0].settings, (setting,), ())
    timeline.set_program(program, "", "Ramp")
    timeline.set_advanced(True)
    timeline.set_elapsed(12.13)
    sample = timeline.dial_samples[0]
    assert sample.form == "texture" and sample.unit == "deg/s"
    assert sample.vector == pytest.approx((-(1 + 2 * 7.13) / 0.05, 0))
    # The ring scale covers the trial's fastest planned drift (end of the ramp).
    assert sample.scale == pytest.approx((1 + 2 * 20) / 0.05, rel=1e-6)
    assert vector_text(sample).endswith("deg/s · 180°")
    assert rotation_text(sample) == "0°/s"


@pytest.mark.parametrize(
    "elapsed,orientation,reset",
    [(2, 55, False), (12, 85, False), (1, 45, False), (12, 35, True)],
)
def test_stationary_dial_reports_current_orientation_with_continuity(
    timeline, elapsed, orientation, reset
):
    texture = review_program().sequence[1].settings[0]
    turning = texture.model_copy(
        update={
            "reset": reset,
            "phase_x": Hold(kind="hold"),
            "phase_y": Hold(kind="hold"),
            "initial": texture.initial.model_copy(update={"rotation_deg": 35}),
            "motion": texture.motion.model_copy(
                update={"rotation": Rate(kind="rate", function=constant(10))}
            ),
        }
    )
    stopped = turning.model_copy(
        update={
            "motion": turning.motion.model_copy(update={"rotation": Hold(kind="hold")})
        }
    )
    timeline.set_program(
        with_settings((turning,), (stopped,), (stopped,)), "", "Stationary"
    )
    timeline.set_advanced(True)
    timeline.set_elapsed(20)
    timeline.set_elapsed(elapsed)
    sample = timeline.dial_samples[0]
    assert sample.vector is None
    assert sample.orientation_deg == pytest.approx(orientation)
    assert vector_text(sample) == f"0 deg/s · {orientation}°"
    assert not timeline.dials[0].grab().isNull()


def test_dial_readouts_are_numeric_on_one_row_and_keep_missing_data(timeline):
    from dataclasses import replace

    timeline.set_advanced(True)
    timeline.set_elapsed(12)
    sample = timeline.dial_samples[0]
    assert (
        dial_readout(replace(sample, vector=None, angular_speed=0)) == "0 deg/s · 0°/s"
    )
    assert dial_readout(replace(sample, vector=(0, 30), angular_speed=-10)) == (
        "30 deg/s · 90° · -10°/s"
    )
    assert dial_readout(replace(sample, message="Waiting for tracking")) == (
        "Waiting for tracking"
    )
    assert "\n" not in dial_readout(sample)


def test_render_has_progress_cursor_and_hover_values(timeline):
    from PyQt6.QtGui import QColor

    timeline.set_advanced(True)
    timeline.set_elapsed(12)
    strip = timeline.epoch_timeline
    image = strip.grab().toImage()
    colors = colors_for(strip)
    bounds = strip.plot_bounds()
    middle = round(bounds.center().y()) - 6
    filled = image.pixel(round(strip.x_at(8)), middle)
    unfilled = image.pixel(round(strip.x_at(20)), middle)
    assert filled != unfilled
    assert QColor(unfilled).rgb() == QColor(colors.active).rgb()
    cursor = QColor(colors.label).rgb()
    x = round(strip.x_at(12))
    assert any(
        image.pixel(x + dx, 4 + y) == cursor for dx in (-1, 0, 1) for y in range(12)
    )
    assert strip.readout(12).splitlines() == [
        "00:00:12 · Flow",
        "Left + Right · texture: 30 deg/s · 180° · 0°/s",
    ]
    timeline.set_elapsed(0)
    QTest.mouseClick(
        strip,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(strip.x_at(30)), round(bounds.center().y())),
    )
    assert timeline.elapsed == pytest.approx(30, abs=0.1)


def test_arena_map_and_body_frame_dial_follow_planned_continuity(timeline):
    # Yaw 90° makes world -X the animal's forward direction (V24 body frame).
    program = with_settings((arena(),), (arena(),), (arena(reset=True),))
    timeline.set_program(program, "", "Arena")
    timeline.set_advanced(True)
    panel = timeline.panels[0]
    assert (panel.form, panel.arena, panel.driving) == ("tracking", True, False)
    assert len(timeline.maps) == 1 and len(timeline.dials) == 1
    timeline.set_elapsed(12)
    dial = timeline.dial_samples[0]
    assert dial.vector == pytest.approx((20, 0)) and dial.unit == "mm/s"
    assert vector_text(dial) == "20 · 0 mm/s"
    world = timeline.map_samples[0]
    # Continuing state carries the first epoch's displacement into the second.
    assert world.pose == pytest.approx((-240, 0, 90))
    assert world.path and world.path[0][-1][0] == pytest.approx(-240, abs=4)
    timeline.set_elapsed(27)
    # An authored reset restarts from the initial pose at the third epoch.
    assert timeline.map_samples[0].pose == pytest.approx((-40, 0, 90))
    timeline.toggles[panel.source.key].setChecked(False)
    assert not timeline.map_samples and not timeline.dial_samples
    assert timeline.maps[0].isHidden() and timeline.dials[0].isHidden()


def test_authored_trajectory_uses_tracking_form_and_size_lane(timeline):
    texture = review_program().sequence[1].settings[0]
    moving = texture.model_copy(
        update={
            "phase_x": Hold(kind="hold"),
            "phase_y": Hold(kind="hold"),
            "width": Ramp(kind="ramp", initial=5, slope_per_s=2),
            "motion": texture.motion.model_copy(
                update={
                    "x": Trajectory(
                        kind="trajectory",
                        function=Ramp(kind="ramp", initial=0, slope_per_s=3),
                    ),
                    "rotation": Rate(kind="rate", function=constant(10)),
                }
            ),
        }
    )
    timeline.set_program(with_settings((), (moving,), ()), "", "Trajectory")
    timeline.set_advanced(True)
    timeline.set_elapsed(5)
    sample = timeline.dial_samples[0]
    assert sample.form == "tracking" and sample.unit == "deg/s"
    # At rotation 0 the layer's +X is forward.
    assert sample.vector == pytest.approx((3, 0), abs=1e-6)
    assert sample.angular_speed == pytest.approx(10)
    assert rotation_text(sample) == "10°/s"
    timeline.set_elapsed(14)
    forward, left = timeline.dial_samples[0].vector
    # After 90° of rotation the +X trajectory is lateral to the layer heading.
    assert (forward, left) == pytest.approx((0, -3), abs=0.05)
    lane = timeline.size_lane
    assert lane.isVisible() and [t.name for t in lane.traces] == ["Left + Right"]
    assert lane.traces[0].unit == "deg"
    assert lane.traces[0].segments[-1][-1] == pytest.approx((14, 5 + 2 * 9))


def test_feedback_texture_pairs_waiting_texture_and_tracking_dials(timeline):
    texture = review_program().sequence[1].settings[0]
    driven = texture.model_copy(
        update={
            "feedback": (
                Feedback(
                    binding_id="drive",
                    source_channel="forward",
                    target="phase_x",
                    operation="movement_integration",
                    gain=constant(1),
                    offset=constant(0),
                ),
            )
        }
    )
    timeline.set_program(with_settings((), (texture,), (driven,)), "", "Feedback")
    timeline.set_advanced(True)
    assert timeline.panels[0].driving and len(timeline.dials) == 2
    timeline.set_elapsed(12)
    texture_dial, tracking_dial = timeline.dial_samples
    assert texture_dial.form == "texture" and texture_dial.vector is not None
    assert tracking_dial.form == "tracking" and tracking_dial.unit == "mm/s"
    assert tracking_dial.message == "No feedback"
    timeline.set_elapsed(40)
    assert [s.message for s in timeline.dial_samples] == [
        "Waiting for tracking",
        "Waiting for tracking",
    ]
    assert all(s.vector is None for s in timeline.dial_samples)


def test_feedback_arena_pose_waits_until_reset(timeline):
    driven = arena(
        feedback=(
            Feedback(
                binding_id="drive",
                source_channel="forward",
                target="x",
                operation="movement_integration",
                gain=constant(1),
                offset=constant(0),
            ),
        )
    )
    program = with_settings((arena(),), (driven,), (arena(),))
    timeline.set_program(program, "", "Arena feedback")
    timeline.set_advanced(True)
    timeline.set_elapsed(12)
    assert timeline.map_samples[0].message == "Waiting for tracking"
    assert timeline.dial_samples[0].message == "Waiting for tracking"
    # Continuing after an unplanned feedback epoch never guesses a pose.
    timeline.set_elapsed(40)
    assert timeline.map_samples[0].pose is None
    timeline.set_program(
        with_settings((arena(),), (driven,), (arena(reset=True),)), "", "Reset"
    )
    timeline.set_elapsed(27)
    assert timeline.map_samples[0].pose == pytest.approx((-40, 0, 90))
