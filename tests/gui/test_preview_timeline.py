"""Standalone preview clock and painter checks without a Dashboard/device fixture."""

import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox

from cephvr.gui import preview_timeline
from cephvr.gui.preview_motion_dial import (
    MotionDial,
    dial_readout,
    rotation_text,
    vector_text,
)
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


def test_monitor_keeps_all_epochs_and_session_duration_beyond_editor_prefix(app):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_status import session_timeline
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.trial_preview_plan import PreviewPlan
    from cephvr.visual_stimulus.config.models.program_model import Group

    program = blank_program()
    epoch = program.sequence[0]
    program = program.model_copy(
        update={
            "sequence": (
                Group(
                    kind="group",
                    group_id="repeated",
                    repetitions=125,
                    order="as_listed",
                    order_unit="child_blocks",
                    conditions=None,
                    body=(epoch,),
                ),
            )
        }
    )
    seconds = epoch.duration.duration.ns() / 1e9
    timeline = StimulusTimeline()
    timeline.set_program(program, "0", "Long trial")
    assert len(timeline.epochs) == 125
    assert timeline.epochs[-1].end == 125 * seconds
    timeline.set_elapsed(124 * seconds)
    assert timeline.epochs[124].start == 124 * seconds
    assert len(PreviewPlan(program).epochs) == 100
    state = pb.Snapshot()
    for number in (1, 2):
        trial = state.configuration_values.current.trials.add(trial_number=number)
        trial.stimulus.program.program_json = program.model_dump_json()
    state.configuration_values.current.gaps.add(
        after_trial_number=1, minimum_duration_ns=10_000_000_000
    )
    state.trial.context.trial_number = 2
    assert session_timeline(state, 120 * seconds, 0) == (
        245 * seconds + 10,
        250 * seconds + 10,
    )
    timeline.close()
    timeline.deleteLater()


@pytest.mark.parametrize("style", ["standard", "retro_console", "amber_phosphor"])
@pytest.mark.parametrize("scale", [0.75, 1, 2])
def test_instrument_font_matches_preview_info(app, monkeypatch, style, scale):
    from PyQt6.QtGui import QFont, QImage, QPainter
    from PyQt6.QtWidgets import QWidget

    from cephvr.gui import preview_motion_dial
    from cephvr.gui.preview_frame import PreviewFrame
    from cephvr.gui.preview_motion_dial import SharedMotionDial
    from cephvr.gui.theme import (
        RETRO_PALETTES,
        load_terminal_font,
        phosphor_stylesheet,
        retro_stylesheet,
    )

    load_terminal_font()
    host = QWidget()
    if style != "standard":
        host.setStyleSheet(
            retro_stylesheet(RETRO_PALETTES[style][0])
            + (phosphor_stylesheet() if style == "amber_phosphor" else "")
        )
    frame = PreviewFrame()
    frame.setParent(host)
    frame.metrics.ensurePolished()
    dial = SharedMotionDial()
    dial.setParent(host)
    dial.ensurePolished()
    size = dial.sizeHint()
    dial.resize(round(size.width() * scale), round(size.height() * scale))
    canvas = QImage(dial.size(), QImage.Format.Format_ARGB32_Premultiplied)

    class ImagePainter(QPainter):
        def __init__(self, widget):
            super().__init__(canvas)

    monkeypatch.setattr(preview_motion_dial, "QPainter", ImagePainter)
    painter = preview_motion_dial.instrument_painter(
        dial, size.height(), size.width(), centered=True
    )
    try:
        font, expected = painter.font(), frame.metrics.font()
        actual_scale = painter.transform().m11()
        assert font.family() == expected.family()
        assert font.weight() == expected.weight()
        assert (
            font.pointSizeF() * dial.logicalDpiY() / 72 * actual_scale
            == pytest.approx(expected.pixelSize() * min(1, actual_scale), abs=0.05)
        )
        if expected.letterSpacingType() == QFont.SpacingType.AbsoluteSpacing:
            assert font.letterSpacing() * actual_scale == pytest.approx(
                expected.letterSpacing() * min(1, actual_scale), abs=0.05
            )
    finally:
        painter.end()
        host.close()


@pytest.mark.parametrize("angular", [-10, 10])
@pytest.mark.parametrize("scale", [1, 2])
@pytest.mark.parametrize("style", [None, "retro_console", "amber_phosphor"])
def test_rotation_marker_arrowhead_and_device_width(app, angular, scale, style):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPen, QTransform

    from cephvr.gui.preview_motion_data import DialSample
    from cephvr.gui.theme import projector_marker_colors

    class Painter:
        def __init__(self):
            self.pens, self.paths, self.polygons = [], [], []

        def transform(self):
            return QTransform().scale(scale, scale)

        def setPen(self, pen):
            if isinstance(pen, QPen):
                self.pens.append(pen)

        def setBrush(self, brush):
            pass

        def drawPath(self, path):
            self.paths.append(path)

        def drawPolygon(self, polygon):
            self.polygons.append(polygon)

        def drawLine(self, start, end):
            pass

    painter = Painter()
    dial = MotionDial()
    dial.setProperty("retroConsole", style is not None)
    dial.setProperty("retroPalette", style)
    center = QPointF(100, 100)
    dial.draw_marker(
        painter,
        DialSample("Bottom", "accent", "texture", "mm/s", None, angular, 20, 20),
        center,
        50,
        40,
    )
    assert len(painter.paths) == len(painter.polygons) == 1
    tip, left, right = painter.polygons[0]
    assert tip == painter.paths[0].currentPosition()
    direction = tip - (left + right) / 2
    radial = tip - center
    assert (radial.x() * direction.y() - radial.y() * direction.x()) * angular < 0
    assert (direction.x() ** 2 + direction.y() ** 2) ** 0.5 * scale == pytest.approx(7)
    assert painter.pens[0].isCosmetic() and painter.pens[0].widthF() == 2
    assert painter.pens[0].color().name() == projector_marker_colors(dial)["Bottom"]
    painter = Painter()
    dial.draw_marker(
        painter,
        DialSample("Left", "accent", "texture", "mm/s", (10, 0), None, 20, 20),
        center,
        50,
        40,
    )
    assert len(painter.polygons) == 1
    assert painter.pens[0].isCosmetic() and painter.pens[0].widthF() == 2
    assert painter.pens[0].color().name() == projector_marker_colors(dial)["Left"]
    dial.close()


@pytest.mark.parametrize("style", ["standard", "retro_console", "amber_phosphor"])
@pytest.mark.parametrize("size", [(245, 130), (204, 220)])
def test_waiting_motion_dial_readout_does_not_overlap_bottom_axis(
    app, monkeypatch, style, size
):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QWidget

    from cephvr.gui import preview_motion_dial
    from cephvr.gui.preview_motion_data import DialSample
    from cephvr.gui.theme import (
        RETRO_PALETTES,
        load_terminal_font,
        phosphor_stylesheet,
        retro_stylesheet,
    )

    load_terminal_font()
    host = QWidget()
    if style != "standard":
        host.setStyleSheet(
            retro_stylesheet(RETRO_PALETTES[style][0])
            + (phosphor_stylesheet() if style == "amber_phosphor" else "")
        )
    canvas = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    text_bounds = {}

    class ImagePainter(QPainter):
        def __init__(self, _widget):
            super().__init__(canvas)

        def drawText(self, rect, *args):
            if isinstance(rect, QRectF):
                text_bounds[args[-1]] = self.transform().mapRect(rect)
            return super().drawText(rect, *args)

    monkeypatch.setattr(preview_motion_dial, "QPainter", ImagePainter)
    dial = MotionDial()
    dial.setParent(host)
    dial.ensurePolished()
    dial.resize(canvas.size())
    dial.set_sample(
        DialSample(
            "Bottom",
            "accent",
            "texture",
            "mm/s",
            None,
            None,
            20,
            20,
            message="Waiting for trial",
        )
    )
    dial.paintEvent(None)

    bottom_axis = text_bounds["Back\n−90°"]
    waiting = next(
        bounds for text, bounds in text_bounds.items() if text.startswith("Waiting")
    )
    assert not bottom_axis.intersects(waiting)
    assert waiting.bottom() <= canvas.height() - 1
    host.close()


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


@pytest.mark.parametrize(
    "elapsed,seconds,expected",
    [
        (None, 0, "00:00"),
        (12, 5, "00:05"),
        (3569, 3595, "59:55"),
        (3570, 3595, "00:59:55"),
        (3570, 3600, "01:00:00"),
        (7200, 7205, "02:00:05"),
    ],
)
def test_timeline_axis_clock_follows_visible_hour_boundary(
    timeline, elapsed, seconds, expected
):

    timeline.set_elapsed(elapsed)

    assert timeline.epoch_timeline.tick_label(seconds) == expected


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

    assert timeline.dial_area.isVisible() and len(timeline.dials) == 2

    timeline.set_advanced(False)

    assert timeline.dial_area.isHidden()

    # The plan and legend stay intact while instruments are hidden.

    assert timeline.panels and timeline.epochs


def test_hidden_instruments_prepare_once_and_rebuild_on_plan_changes(
    timeline, monkeypatch
):
    from cephvr.gui.preview_motion_samples import InstrumentPlan

    geometry, _ = linked_plan()
    program = review_program()
    prepared = []
    prepare = InstrumentPlan.prepare_panel

    def track_prepare(plan, panel):
        prepared.append(panel.source.key)
        prepare(plan, panel)

    monkeypatch.setattr(InstrumentPlan, "prepare_panel", track_prepare)
    timeline.clear("")
    timeline.set_program(program, "", "Lazy")

    assert not prepared and not timeline.dials
    assert timeline.projector_names() == ("Left", "Right")
    assert timeline.panels and timeline.dial_samples == []
    hover_before = timeline.readout_lines(2)
    timeline.set_projector_visible("Left", False)
    assert timeline.projector_names() == ("Left", "Right")

    timeline.set_advanced(True)
    first_count = len(timeline.all_panels)
    assert len(prepared) == first_count and timeline.dial_samples
    assert timeline.readout_lines(2) == hover_before
    assert not timeline.projector_cards["Left"].isVisible()

    timeline.set_advanced(False)
    timeline.set_advanced(True)
    assert len(prepared) == first_count

    timeline.set_advanced(False)
    timeline.set_program(program, "new-seed", "Lazy", geometry)
    assert len(prepared) == first_count
    timeline.set_advanced(True)
    assert len(prepared) == first_count * 2

    timeline.set_advanced(False)
    changed_geometry = geometry.model_copy(update={"observer_mm": (1, 0, 0)})
    timeline.set_program(program, "new-seed", "Lazy", changed_geometry)
    assert len(prepared) == first_count * 2
    timeline.set_advanced(True)
    assert len(prepared) == first_count * 3

    timeline.set_advanced(False)
    timeline.set_program(
        program.model_copy(deep=True), "new-seed", "Lazy", changed_geometry
    )
    assert len(prepared) == first_count * 3
    timeline.set_advanced(True)
    assert len(prepared) == first_count * 4


@pytest.mark.parametrize("stacked", [False, True])
def test_source_controls_belong_to_motion_plots_not_timeline(timeline, stacked):

    app = QApplication.instance()

    timeline.set_stacked(stacked)

    timeline.set_advanced(True)

    app.processEvents()

    card = timeline.dials[0].parentWidget().parentWidget()

    assert card.objectName() == "ProjectorCard"

    assert timeline.dial_area.isAncestorOf(card)

    assert not timeline.instrument_host.findChildren(QCheckBox)

    assert timeline.dial_samples

    assert timeline.epoch_timeline.isVisible()

    timeline.set_advanced(False)

    assert not card.isVisible()

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

    assert vector_text(sample).endswith("deg/s · 90°")

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
        "30 deg/s · 0° · -10°/s"
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
        "Left · texture: 30 deg/s · 90° · 0°/s",
        "Right · texture: 30 deg/s · -90° · 0°/s",
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

    assert timeline.map_samples[0].pose is None
    assert not timeline.map_samples[0].path
    assert timeline.map_samples[0].message == "Waiting for trial"

    timeline.set_elapsed(0)

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


def test_projector_card_instruments_wrap_to_the_column_width(timeline):

    app = QApplication.instance()

    program = with_settings((arena(),), (arena(),), (arena(reset=True),))

    timeline.set_program(program, "", "Arena")

    timeline.set_advanced(True)

    timeline.set_playback(0, running=False)

    for _ in range(3):
        app.processEvents()

    card = timeline.maps[0].parentWidget().parentWidget()

    grid = card.grid

    world, dial = timeline.maps[0], timeline.dials[0]

    # The map and dial share a row only when two fixed-size instruments fit.

    timeline.dial_area.setFixedWidth(MotionDial.SIZE + 60)

    for _ in range(3):
        app.processEvents()

    assert grid.columns == 1 and dial.y() > world.y()

    assert abs(dial.geometry().center().x() - grid.rect().center().x()) <= 1

    assert timeline.dial_area.horizontalScrollBar().maximum() == 0

    timeline.dial_area.setFixedWidth(2 * MotionDial.SIZE + 80)

    for _ in range(3):
        app.processEvents()

    assert grid.columns == 2 and dial.y() == world.y() and dial.x() > world.x()


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

    assert lane.isVisible() and [t.name for t in lane.traces] == ["Left", "Right"]

    assert lane.traces[0].unit == "deg"

    assert lane.traces[0].segments[-1][-1] == pytest.approx((14, 5 + 2 * 9))


def test_shared_polar_keeps_static_bottom_colours_and_toggle_identity(timeline):
    geometry, settings = linked_plan()
    source = settings[0]
    hold = Hold(kind="hold")
    settings[0] = source.model_copy(
        update={
            "phase_x": hold,
            "phase_y": hold,
            "motion": source.motion.model_copy(
                update={"x": hold, "y": hold, "rotation": hold}
            ),
        }
    )
    timeline.merge_directions = True
    timeline.set_program(
        with_settings(tuple(settings), tuple(settings), tuple(settings)),
        "",
        "Static",
        geometry,
    )
    timeline.set_advanced(True)
    pending = next(iter(timeline.shared_dials.values()))
    assert timeline.elapsed is None
    assert len(pending.samples) == 4
    assert all(
        s.vector is None and s.angular_speed is None and s.orientation_deg is None
        for s in pending.samples
    )
    assert all(s.message == "Waiting for trial" for s in pending.samples)
    timeline.set_elapsed(2)
    assert set(timeline.active_sources) == {"Left", "Front", "Right", "Bottom"}
    assert len(timeline.shared_dials) == 1
    dial = next(iter(timeline.shared_dials.values()))
    assert [s.name.split(" · ")[0] for s in dial.samples] == [
        "Left",
        "Front",
        "Right",
        "Bottom",
    ]
    assert len({s.color for s in dial.samples}) == 4
    bottom = dial.samples[-1]
    assert bottom.vector is None and bottom.angular_speed == 0 and not bottom.message
    assert dial.HEADERS == ("Projector", "Speed", "Direction", "Angular")
    rows = dial.parameter_rows()
    assert [row[0] for row in rows] == ["Left", "Front", "Right", "Bottom"]
    assert rows[-1][1:] == ("0 mm/s", f"{bottom.orientation_deg:.3g}°", "0°/s")
    assert all(row[1].endswith("mm/s") and row[3].endswith("°/s") for row in rows)
    assert not dial.grab().isNull()
    timeline.set_projector_visible("Bottom", False)
    assert len(dial.samples) == 3
    assert [row[0] for row in dial.parameter_rows()] == ["Left", "Front", "Right"]
    timeline.set_projector_visible("Bottom", True)
    assert len(dial.samples) == 4 and dial.samples[-1] == bottom
    timeline.combined = False
    timeline.rebuild_instruments()
    timeline.refresh()
    assert not timeline.shared_dials
    assert not timeline.projector_cards["Bottom"].findChild(MotionDial).isHidden()
    timeline.set_playback(None, running=False)
    assert all(
        s.vector is None and s.angular_speed is None for s in timeline.dial_samples
    )


def test_shared_polar_separates_incompatible_units(timeline):
    geometry, settings = linked_plan()
    angular = review_program().sequence[1].settings[0]
    settings = tuple(settings) + (angular,)
    timeline.merge_directions = True
    timeline.set_program(
        with_settings(settings, settings, settings), "", "Mixed units", geometry
    )
    assert not timeline.shared_dials
    timeline.set_advanced(True)
    timeline.set_elapsed(2)
    assert set(timeline.shared_dials) == {("texture", "mm/s"), ("texture", "deg/s")}
    for (_, unit), dial in timeline.shared_dials.items():
        assert dial.samples and {s.unit for s in dial.samples} == {unit}


def test_projector_card_retains_every_same_face_layer(timeline):
    app = QApplication.instance()
    texture = review_program().sequence[1].settings[0]
    second = texture.model_copy(
        update={
            "instance_id": "second_layer",
            "motion": texture.motion.model_copy(
                update={"rotation": Rate(kind="rate", function=constant(7))}
            ),
        }
    )
    timeline.set_program(with_settings((), (texture, second), ()), "", "Layers")
    timeline.set_advanced(True)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    timeline.set_playback(12, running=False)
    timeline.timer.timeout.emit()
    face = timeline.panels[0].source.key[0]
    layers = [panel for panel in timeline.panels if panel.source.key[0] == face]
    assert len(layers) == 2
    assert len(timeline.projector_cards[face].findChildren(MotionDial)) == 2
    assert [
        sample.angular_speed
        for panel, sample in zip(timeline.panels, timeline.dial_samples, strict=True)
        if panel.source.key[0] == face
    ] == [0, 7]
    timeline.set_projector_visible(face, False)
    assert timeline.projector_cards[face].isHidden()
    timeline.set_projector_visible(face, True)
    app.processEvents()
    assert all(
        dial.isVisible()
        for dial in timeline.projector_cards[face].findChildren(MotionDial)
    )
    timeline.refresh()


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

    assert timeline.panels[0].driving and len(timeline.dials) == 4

    timeline.set_elapsed(12)

    texture_dial, tracking_dial = timeline.dial_samples[:2]

    assert texture_dial.form == "texture" and texture_dial.vector is not None

    assert tracking_dial.form == "tracking" and tracking_dial.unit == "mm/s"

    assert tracking_dial.message == "No feedback"

    timeline.set_elapsed(40)

    assert [s.message for s in timeline.dial_samples] == [
        "Waiting for tracking",
        "Waiting for tracking",
    ] * 2

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


def linked_plan():

    import json

    from cephvr.visual_stimulus.config.models.display_profile import Geometry
    from cephvr.visual_stimulus.config.models.program_model import TextureSettings

    geometry = Geometry.model_validate_json(
        json.dumps(
            dict(
                frame_id="rig-mm",
                observer_mm=(0, 0, 0),
                near_mm=1,
                far_mm=1000,
                positional_tolerance_mm=0.01,
                orthogonality_tolerance=0.001,
                surfaces=[
                    dict(
                        surface_id=face,
                        bottom_left_mm=bl,
                        bottom_right_mm=br,
                        top_right_mm=tr,
                        top_left_mm=tl,
                    )
                    for face, bl, br, tr, tl in (
                        (
                            "bottom",
                            (-100, -100, -30),
                            (100, -100, -30),
                            (100, 100, -30),
                            (-100, 100, -30),
                        ),
                        (
                            "front",
                            (100, -100, -30),
                            (-100, -100, -30),
                            (-100, -100, 100),
                            (100, -100, 100),
                        ),
                        (
                            "left",
                            (-40, -100, -30),
                            (-40, 100, -30),
                            (-40, 100, 100),
                            (-40, -100, 100),
                        ),
                        (
                            "right",
                            (60, 100, -30),
                            (60, -100, -30),
                            (60, -100, 100),
                            (60, 100, 100),
                        ),
                    )
                ],
            )
        )
    )

    base = review_program().sequence[1].settings[0].model_dump(mode="json")

    settings = []

    for face, period in (("bottom", 100), ("front", 50), ("left", 80), ("right", 120)):
        data = dict(
            base,
            instance_id=face,
            linked_to=None if face == "bottom" else "bottom",
            pattern=dict(
                kind="image_tile",
                asset_id="tile",
                sampling="nearest",
                period_x=dict(kind="constant", value=period),
                period_y=dict(kind="constant", value=period),
            ),
            space=dict(
                kind="physical_surface",
                frame_id="rig-mm",
                mappings=[dict(surface_id=face, matrix=((1, 0, 0), (0, 1, 0)))],
            ),
            motion={key: dict(kind="hold") for key in ("x", "y", "rotation")},
            phase_x=dict(kind="hold"),
            phase_y=dict(kind="hold"),
            reset=False,
        )

        settings.append(TextureSettings.model_validate_json(json.dumps(data)))

    return geometry, settings


@pytest.mark.parametrize("spin", [0, -30, 30])
@pytest.mark.parametrize("shared", [False, True])
def test_linked_dials_match_renderer_rates_and_keep_independent_scales(
    timeline, spin, shared
):

    from math import hypot, radians

    from cephvr.gui.preview_motion_dial import screen_vector
    from cephvr.visual_stimulus.rendering.state import InstanceState
    from cephvr.visual_stimulus.rendering.texture_links import bind_texture_links

    geometry, settings = linked_plan()
    timeline.merge_directions = shared

    source = settings[0]

    source = source.model_copy(
        update={
            "phase_x": Hold(kind="hold")
            if spin
            else Rate(kind="rate", function=constant(-0.5)),
            "motion": source.motion.model_copy(
                update={"rotation": Rate(kind="rate", function=constant(spin))}
            ),
        }
    )

    settings[0] = source

    program = with_settings(tuple(settings), tuple(settings), tuple(settings))

    timeline.set_program(program, "", "Linked", geometry)

    timeline.set_advanced(True)

    timeline.set_elapsed(2)

    states = {
        s.instance_id: InstanceState.initialize(s, now_ns=0, epoch_start_ns=0)
        for s in settings
    }

    bind_texture_links(states, geometry, now_ns=0)

    samples = {s.name.split(" ")[0].lower(): s for s in timeline.dial_samples}

    assert len(samples) == 4 and all(not s.message for s in samples.values())

    for setting in settings[1:]:
        fields = states[setting.instance_id].values

        expected = tuple(
            -fields[key].function.value * period.value
            for key, period in (
                ("phase_x", setting.pattern.period_x),
                ("phase_y", setting.pattern.period_y),
            )
        )

        sample = samples[setting.instance_id]

        assert sample.vector == pytest.approx(expected)

        assert sample.angular_speed == fields["rotation"].function.value

        assert sample.scale >= hypot(*expected) - 1e-9

    assert hypot(*samples["left"].vector) == pytest.approx(
        abs(radians(spin) * 40) if spin else 50
    )

    assert hypot(*samples["right"].vector) == pytest.approx(
        abs(radians(spin) * 60) if spin else 50
    )

    if spin:
        assert samples["bottom"].vector is None
        assert samples["bottom"].angular_speed == spin
        # Leftward Bottom rotation produces each face's own arena translation.
        for face, direction in (
            ("front", (-1, 0)),
            ("right", (0, -1)),
            ("left", (0, 1)),
        ):
            sample = samples[face]
            dx, dy = screen_vector(sample)
            speed = hypot(dx, dy)
            sign = 1 if spin > 0 else -1
            assert (dx / speed, dy / speed) == pytest.approx(
                tuple(sign * component for component in direction), abs=1e-8
            )
            assert sample.angular_speed == 0


@pytest.mark.parametrize("reset", [False, True])
def test_linked_dials_retain_boundary_orientation_through_stop_and_relink(
    timeline, reset
):

    from cephvr.visual_stimulus.rendering.state import InstanceState
    from cephvr.visual_stimulus.rendering.texture_links import bind_texture_links

    geometry, settings = linked_plan()

    spin = settings[0].model_copy(
        update={
            "motion": settings[0].motion.model_copy(
                update={"rotation": Rate(kind="rate", function=constant(10))}
            )
        }
    )

    drift = settings[0].model_copy(
        update={"reset": reset, "phase_x": Rate(kind="rate", function=constant(-0.5))}
    )

    epochs = [(spin, *settings[1:]), tuple(settings), (drift, *settings[1:])]

    program = with_settings(*epochs)

    timeline.set_advanced(True)
    timeline.set_program(program, "", "Continuity", geometry)

    states = {}

    for index, epoch in enumerate(timeline.epochs):
        for setting in epoch.settings:
            if setting.instance_id not in states:
                states[setting.instance_id] = InstanceState.initialize(
                    setting, now_ns=epoch.start_ns, epoch_start_ns=epoch.start_ns
                )

            else:
                states[setting.instance_id].transition(
                    setting,
                    action="reset" if setting.reset else "continue",
                    now_ns=epoch.start_ns,
                    epoch_start_ns=epoch.start_ns,
                )

        bind_texture_links(states, geometry, now_ns=epoch.start_ns)

        timeline.set_elapsed(epoch.start + 1)

        samples = {s.name.split(" ")[0].lower(): s for s in timeline.dial_samples}
        for setting in epoch.settings:
            sample = samples[setting.instance_id]
            current = timeline.plan.values(index, setting.instance_id, 1_000_000_000)
            if sample.vector is None:
                assert sample.orientation_deg == pytest.approx(current["rotation"])

        for setting in epoch.settings:
            expected = {
                k: v.value for k, v in states[setting.instance_id].values.items()
            }

            assert timeline.plan.values(index, setting.instance_id, 0) == pytest.approx(
                expected
            )

        if index == 1:
            assert all(
                sample.vector is None and sample.angular_speed == 0
                for sample in timeline.dial_samples
            )

    assert timeline.plan.values(2, "bottom", 0)["rotation"] == pytest.approx(
        0 if reset else 50
    )

    assert all(not sample.message for sample in timeline.dial_samples)


def test_linked_dials_rebuild_for_geometry_and_isolate_unavailable_sources(timeline):

    geometry, settings = linked_plan()

    settings[0] = settings[0].model_copy(
        update={"phase_x": Rate(kind="rate", function=constant(-0.5))}
    )

    program = with_settings(tuple(settings), tuple(settings), tuple(settings))

    timeline.set_advanced(True)
    timeline.set_program(program, "", "Missing geometry")

    timeline.set_elapsed(2)

    assert not timeline.dial_samples[0].message

    assert all("geometry" in sample.message for sample in timeline.dial_samples[1:])

    timeline.set_program(program, "", "Calibrated", geometry)

    timeline.set_elapsed(2)

    assert all(not sample.message for sample in timeline.dial_samples)

    previous = timeline.plan

    timeline.set_program(program, "", "Same geometry", geometry.model_copy())

    assert timeline.plan is previous

    settings[1] = settings[1].model_copy(update={"linked_to": "missing"})

    timeline.set_program(
        with_settings(tuple(settings), tuple(settings), tuple(settings)),
        "",
        "Missing reference",
        geometry,
    )

    timeline.set_elapsed(2)

    samples = {sample.name.split(" ")[0]: sample for sample in timeline.dial_samples}

    assert "unavailable" in samples["Front"].message

    assert not samples["Left"].message and not samples["Right"].message


@pytest.mark.parametrize("style", [None, "amber_phosphor"])
@pytest.mark.parametrize("size", [(1440, 960), (1000, 700), (600, 480)])
@pytest.mark.parametrize("driving", [False, True])
def test_all_projector_plots_fit_visible_workspace_without_scroll(
    timeline, size, driving, style
):

    from PyQt6.QtWidgets import QLabel, QWidget

    from cephvr.gui.previews import PreviewWorkspace

    geometry, settings = linked_plan()
    settings[0] = settings[0].model_copy(
        update={"phase_x": Rate(kind="rate", function=constant(-0.5))}
    )

    if driving:
        settings = [
            setting.model_copy(
                update={
                    "linked_to": None,
                    "feedback": (
                        Feedback(
                            binding_id="drive",
                            source_channel="forward",
                            target="phase_x",
                            operation="movement_integration",
                            gain=constant(1),
                            offset=constant(0),
                        ),
                    ),
                }
            )
            for setting in settings
        ]

    host = QWidget()

    dialog = PreviewWorkspace(None)
    dialog.setProperty("retroPalette", style)
    dialog.setProperty("retroConsole", style is not None)
    dialog.stimulus_area.set_projectors(("Left", "Front", "Right", "Bottom"))

    try:
        plot = dialog.timeline

        plot.set_program(
            with_settings(tuple(settings), tuple(settings), tuple(settings)),
            "",
            "Fit",
            geometry,
        )

        dialog.advanced_toggle.setChecked(True)

        plot.set_playback(0, running=False)

        dialog.resize(*size)

        dialog.show()

        app = QApplication.instance()

        app.processEvents()

        # Reflow after dragging the divider, then returning it to its usual width.

        for width in (size[0] // 3, size[0] - 180, size[0] // 4):
            dialog.splitter.setSizes([size[0] - width, width])

            for _ in range(3):
                app.processEvents()

            viewport = plot.dial_area.viewport()

            assert plot.dial_area.verticalScrollBar().maximum() == 0

            assert plot.dial_area.horizontalScrollBar().maximum() == 0

            cards = plot.instrument_host.instruments

            assert len(cards) == (4 if driving else 1)
            if driving:
                assert [card.findChild(QLabel).name_text for card in cards] == [
                    "Left",
                    "Front",
                    "Right",
                    "Bottom",
                ]
            else:
                assert [s.name.split(" · ")[0] for s in cards[0].samples] == [
                    "Left",
                    "Front",
                    "Right",
                    "Bottom",
                ]

            assert plot.cards.spacing() == 16
            bounds = cards[0].geometry()
            for card in cards[1:]:
                bounds = bounds.united(card.geometry())
            assert (
                abs(bounds.center().y() - plot.instrument_host.rect().center().y()) <= 1
            )
            margins = plot.cards.contentsMargins()
            if plot.instrument_host.columns != len(cards):
                assert margins.top() == margins.bottom() == 0
            else:
                host = plot.instrument_host
                row_height = round(
                    (host.width() - 16 * (len(cards) - 1))
                    / len(cards)
                    / host.cell_size.width()
                    * host.cell_size.height()
                )
                if driving:
                    assert bounds.height() <= row_height + 1
                if driving and host.height() > row_height + 2:
                    assert margins.top() > 0

            for card in cards:
                assert card.isVisible()

                assert viewport.rect().contains(card.mapTo(viewport, QPoint()))

                assert viewport.rect().contains(
                    card.mapTo(viewport, card.rect().bottomRight())
                )

                for dial in card.grid.instruments if driving else ():
                    assert dial.isVisible() and dial.width() > 0 and dial.height() > 0

                    assert card.rect().contains(dial.mapTo(card, QPoint()))

                    assert card.rect().contains(
                        dial.mapTo(card, dial.rect().bottomRight())
                    )

            assert len(plot.dials) == (8 if driving else 4)

            assert not dialog.grab().isNull()

    finally:
        dialog.timeline.timer.stop()

        dialog.close()

        host.deleteLater()

        QApplication.instance().processEvents()


def test_retro_projector_headings_are_uppercase_and_glow(timeline):
    timeline.set_advanced(True)
    plain = [heading.text() for heading in timeline.headings]
    assert plain and all(
        heading.graphicsEffect() is None for heading in timeline.headings
    )
    timeline.setProperty("retroConsole", True)
    timeline.restyle(True)
    assert [heading.text() for heading in timeline.headings] == [
        text.upper() for text in plain
    ]
    assert all(heading.graphicsEffect() for heading in timeline.headings)
    # Cards rebuilt while Retro and glow are on keep both treatments.
    timeline.rebuild_instruments()
    assert timeline.headings and all(
        heading.text().isupper() and heading.graphicsEffect()
        for heading in timeline.headings
    )
    card = timeline.headings[0].parentWidget()
    assert card.objectName() == "ProjectorCard"
    card.resize(240, 260)
    assert not card.grab().isNull()
    timeline.restyle(False)
    assert all(heading.graphicsEffect() is None for heading in timeline.headings)
    assert all(heading.text().isupper() for heading in timeline.headings)
    timeline.setProperty("retroConsole", False)
    timeline.restyle(False)
    assert [heading.text() for heading in timeline.headings] == plain
    from cephvr.gui.theme import colors_for

    for style in ("amber_phosphor", "retro_console", None):
        timeline.setProperty("retroPalette", style)
        timeline.setProperty("retroConsole", style is not None)
        timeline.restyle()
        expected = f"color: {colors_for(timeline).coral};"
        assert {heading.styleSheet() for heading in timeline.headings} == {expected}
        timeline.rebuild_instruments()
        assert {heading.styleSheet() for heading in timeline.headings} == {expected}
    from cephvr.gui.theme import colors_for

    for style in ("amber_phosphor", "retro_console", None):
        timeline.setProperty("retroPalette", style)
        timeline.setProperty("retroConsole", style is not None)
        timeline.restyle()
        expected = f"color: {colors_for(timeline).coral};"
        assert {heading.styleSheet() for heading in timeline.headings} == {expected}
        timeline.rebuild_instruments()
        assert {heading.styleSheet() for heading in timeline.headings} == {expected}


def test_retro_preview_controls_and_headings_glow(app):
    from PyQt6.QtWidgets import QCheckBox, QPushButton, QWidget

    from cephvr.gui.previews import PreviewWorkspace
    from cephvr.gui.view import PreviewView

    host = QWidget()
    dialog = PreviewWorkspace(None)
    dialog.apply_views(
        (
            PreviewView(
                "behavior", "Behavior cam", visible=True, available=True, active=True
            ),
        ),
        allowed=True,
    )
    toggle, show = dialog.advanced_toggle, dialog.controls["behavior"]
    assert isinstance(toggle, QCheckBox) and isinstance(show, QPushButton)
    assert toggle.isCheckable() and show.isCheckable()
    host.setProperty("retroConsole", True)
    dialog.restyle(True)
    assert dialog.names["behavior"].graphicsEffect() is not None
    # Stream toggles are named by their stream (no "Show" wording).
    assert show.text() == "Behavior"
    assert show.accessibleName() == dialog.views["behavior"].name
    assert toggle.text() == "Advanced"
    toggle.setEnabled(False)
    toggle.setEnabled(True)
    dialog.apply_views((PreviewView("camera", "Camera", visible=False),), allowed=True)
    assert dialog.names["camera"].graphicsEffect() is not None
    dialog.restyle(False)
    assert all(name.graphicsEffect() is None for name in dialog.names.values())
    host.setProperty("retroConsole", False)
    dialog.timeline.timer.stop()
    host.deleteLater()


@pytest.mark.parametrize("vx,vy", [(30, 0), (-30, 0), (0, 30), (0, -30), (18, 24)])
@pytest.mark.parametrize("rotation", [0, 45])
def test_linked_subject_directions_align_across_projectors(timeline, vx, vy, rotation):
    from math import cos, radians, sin

    from cephvr.gui.preview_motion_dial import AXIS_LABELS, screen_vector

    geometry, settings = linked_plan()

    settings[0] = settings[0].model_copy(
        update={
            "initial": settings[0].initial.model_copy(
                update={"rotation_deg": rotation}
            ),
            "phase_x": Rate(kind="rate", function=constant(-vx / 100)),
            "phase_y": Rate(kind="rate", function=constant(-vy / 100)),
        }
    )

    timeline.set_program(
        with_settings(*(tuple(settings),) * 3), "", "Subject", geometry
    )

    timeline.set_advanced(True)
    timeline.set_elapsed(2)

    assert timeline.dial_samples
    for sample in timeline.dial_samples:
        assert not sample.message

        angle = radians(rotation)
        assert screen_vector(sample) == pytest.approx(
            (vx * cos(angle) - vy * sin(angle), vx * sin(angle) + vy * cos(angle)),
            abs=1e-8,
        )

    assert AXIS_LABELS["texture"] == (
        "Front\n90°",
        "Back\n−90°",
        "Right\n0°",
        "Left\n180°",
    )


@pytest.mark.parametrize("direction", [0, 90, 180, -90, 35])
@pytest.mark.parametrize("rotation", [0, 45])
@pytest.mark.parametrize("mapping_rotation", [0, 90])
def test_rig_authored_translation_stays_aligned_while_texture_rotates(
    timeline, direction, rotation, mapping_rotation
):
    import json
    from math import cos, radians, sin

    from cephvr.gui.preview_motion_dial import screen_vector
    from cephvr.gui.rig_parameter_edits import motion_numbers, patch_setting
    from cephvr.visual_stimulus.config.models.program_model import TextureSettings
    from cephvr.visual_stimulus.rendering.state import InstanceState

    geometry, settings = linked_plan()
    # Match G01's Bottom screen axes: image +X points toward the back of the tank.
    bottom = geometry.surfaces[0].model_copy(
        update={
            "bottom_left_mm": (100, -100, -30),
            "bottom_right_mm": (100, 100, -30),
            "top_right_mm": (-100, 100, -30),
            "top_left_mm": (-100, -100, -30),
        }
    )
    geometry = geometry.model_copy(
        update={"surfaces": (bottom, *geometry.surfaces[1:])}
    )
    authored = []
    for setting in settings:
        data = setting.model_dump(mode="json")
        data["linked_to"] = None
        if mapping_rotation:
            data["space"]["mappings"][0]["matrix"] = [[0, -1, 0], [1, 0, 0]]
        data["initial"]["rotation_deg"] = rotation
        patch_setting(
            data, {"Speed": "30", "Direction": str(direction), "Angular speed": "15"}
        )
        assert motion_numbers(data) == pytest.approx((30, direction, 15))
        assert data["phase_x"] == data["phase_y"] == {"kind": "hold"}
        authored.append(TextureSettings.model_validate_json(json.dumps(data)))
    timeline.set_program(with_settings(*(tuple(authored),) * 3), "", "Rig", geometry)
    timeline.set_advanced(True)
    expected = (30 * cos(radians(direction)), -30 * sin(radians(direction)))
    for time in (1, 7, 24):
        timeline.set_elapsed(time)
        assert timeline.dial_samples
        for sample in timeline.dial_samples:
            assert not sample.message
            assert screen_vector(sample) == pytest.approx(expected, abs=1e-8)
    for setting in authored:
        state = InstanceState.initialize(setting, now_ns=0, epoch_start_ns=0)
        first = dict(state.snapshot(now_ns=1_000_000_000, epoch_start_ns=0))
        later = dict(state.snapshot(now_ns=3_000_000_000, epoch_start_ns=0))
        assert later["rotation"] - first["rotation"] == pytest.approx(30)
        assert later["x"] - first["x"] == pytest.approx(
            2 * setting.motion.x.function.value
        )
        assert later["y"] - first["y"] == pytest.approx(
            2 * setting.motion.y.function.value
        )


def test_rig_authored_reference_drives_linked_projectors(timeline):
    import json

    from cephvr.gui.preview_motion_dial import screen_vector
    from cephvr.gui.rig_parameter_edits import patch_setting
    from cephvr.visual_stimulus.config.models.program_model import TextureSettings
    from cephvr.visual_stimulus.config.texture_links import validate_links

    geometry, settings = linked_plan()
    # Use Left as reference: its axes agree with the standard rig fixture.
    source = next(s for s in settings if s.instance_id == "left")
    data = source.model_dump(mode="json")
    data["linked_to"] = None
    patch_setting(data, {"Speed": "30", "Direction": "-90"})
    source = TextureSettings.model_validate_json(json.dumps(data))
    settings = [
        source
        if s.instance_id == "left"
        else s.model_copy(update={"linked_to": "left"})
        for s in settings
    ]
    validate_links(settings, resolved=True)
    timeline.set_program(
        with_settings(*(tuple(settings),) * 3), "", "Rig linked", geometry
    )
    timeline.set_advanced(True)
    timeline.set_elapsed(2)
    assert timeline.dial_samples
    for sample in timeline.dial_samples:
        assert not sample.message
        assert screen_vector(sample) == pytest.approx((0, 30), abs=1e-8)
