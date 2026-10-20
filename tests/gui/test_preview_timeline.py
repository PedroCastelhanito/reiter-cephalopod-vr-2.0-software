"""Standalone preview clock and painter checks without a Dashboard/device fixture."""

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from cephvr.gui import preview_timeline
from cephvr.gui.preview_motion_plot import time_window
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.protocol_document import review_program
from cephvr.gui.theme import colors_for


@pytest.fixture
def timeline():
    app = QApplication.instance() or QApplication([])
    widget = StimulusTimeline()
    widget.resize(1100, 400)
    widget.set_program(review_program(), "", "Trial")
    widget.show()
    app.processEvents()
    yield widget
    widget.timer.stop()
    widget.close()
    widget.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("elapsed", [None, 0, 12, 30, 45, 60.5])
def test_time_window_keeps_current_time_centered(elapsed):
    start, end = time_window(elapsed)
    assert end - start == 30
    assert (start + end) / 2 == (elapsed or 0)


@pytest.mark.parametrize("elapsed", [0, 4.2, 5, 12.13, 25, 45.5, 60])
def test_speed_history_stops_at_center_and_preserves_epoch_steps(timeline, elapsed):
    timeline.set_elapsed(elapsed)
    points = [p for s in timeline.plot.traces[0].segments for p in s]
    assert all(max(0, elapsed - 15) <= t <= elapsed for t, _ in points)
    assert points[-1][0] == elapsed
    assert points[-1][1] == (30 if 5 <= elapsed < 25 else 0)
    assert timeline.epoch_strip.elapsed == elapsed


def test_clock_advances_at_five_hz_and_stops_with_reported_state(timeline, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(preview_timeline, "monotonic", lambda: now[0])
    assert timeline.timer.interval() == 200
    assert timeline.timer.timerType() == Qt.TimerType.PreciseTimer
    timeline.set_playback(12, running=True)
    now[0] += 0.2
    timeline.timer.timeout.emit()
    assert timeline.plot.elapsed == pytest.approx(12.2)
    timeline.set_playback(13, running=True)
    now[0] += 0.2
    timeline.timer.timeout.emit()
    assert timeline.plot.elapsed == pytest.approx(13.2)
    now[0] += 100
    timeline.timer.timeout.emit()
    assert timeline.plot.elapsed == 60
    timeline.set_playback(14, running=False)
    now[0] += 1
    timeline.timer.timeout.emit()
    assert timeline.plot.elapsed == 14
    timeline.set_playback(None, running=False)
    timeline.timer.timeout.emit()
    assert timeline.plot.elapsed is None


def test_current_velocity_is_evaluated_at_fractional_endpoint(timeline):
    from cephvr.visual_stimulus.config.models.program_model import Ramp, Rate

    program = review_program()
    epoch = program.sequence[1]
    setting = epoch.settings[0].model_copy(
        update={
            "phase_x": Rate(
                kind="rate", function=Ramp(kind="ramp", initial=1, slope_per_s=2)
            )
        }
    )
    program = program.model_copy(
        update={
            "sequence": (
                program.sequence[0],
                epoch.model_copy(update={"settings": (setting,)}),
                program.sequence[2],
            )
        }
    )
    timeline.set_program(program, "", "Ramp")
    timeline.set_elapsed(12.13)
    assert timeline.plot.traces[0].segments[-1][-1] == pytest.approx(
        (12.13, (1 + 2 * 7.13) / 0.05)
    )


def test_render_has_centered_speed_endpoint_without_time_bar(timeline):
    from PyQt6.QtGui import QColor

    timeline.set_elapsed(12)
    plot = timeline.plot
    image = plot.grab().toImage()
    bounds = plot.plot_bounds()
    middle = round(bounds.center().x())
    colors = colors_for(plot)
    trace_color = QColor(colors.accent).rgb()
    coral = QColor(colors.coral).rgb()
    step_x = round(bounds.left() + (5 - (12 - 15)) / 30 * bounds.width())
    assert image.pixel(step_x, round(bounds.center().y())) == trace_color
    assert any(
        image.pixel(middle, y) == trace_color for y in range(25, int(bounds.bottom()))
    )
    assert not any(
        image.pixel(middle, y) == coral for y in range(25, int(bounds.bottom()))
    )
    assert not any(
        image.pixel(middle + 10, y) == trace_color
        for y in range(25, int(bounds.bottom()))
    )
    timeline.set_elapsed(0)
    QTest.mouseClick(
        plot,
        Qt.MouseButton.LeftButton,
        pos=QPoint(int(bounds.left() + 2), int(bounds.center().y())),
    )
    assert plot.elapsed == 0
