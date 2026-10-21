"""Native frontend behavior and ownership; no controller or rig execution."""

from collections.abc import Iterator
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QRect, QSettings, QSize, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QWidget,
)

from cephvr.gui.layouts import tool_window_position
from cephvr.gui.log_format import STAMP_WIDTH
from cephvr.gui.managed_status import (
    dashboard_view,
    has_retained_history,
    has_retained_review,
    retained_ack_required_for,
    retained_details,
    retained_summary,
)
from cephvr.gui.review import ReviewControls
from cephvr.gui.view import DashboardView, Phase, PreviewView, review_view
from cephvr.gui.window import DashboardWindow


def show_previews(target: DashboardWindow) -> None:
    """Enter the runtime layout that hosts previews (Start swaps it in; G02)."""
    target.apply_view(replace(target.dashboard.view, phase=Phase.RUNNING))
    QApplication.processEvents()


def log_rows(console: QPlainTextEdit) -> list[str]:
    """Log rows without their wall-clock stamp."""
    return [row[STAMP_WIDTH:] for row in console.toPlainText().splitlines()]


@pytest.mark.parametrize(
    "anchor,area,scale,expected",
    [
        (QRect(100, 100, 500, 600), QRect(0, 0, 1920, 1080), 1.0, (600, 100, 640)),
        (QRect(1000, 100, 800, 600), QRect(0, 0, 1920, 1080), 1.0, (344, 100, 640)),
        (QRect(0, 0, 1456, 979), QRect(0, 0, 1920, 1032), 1.0, (1456, 0, 448)),
        (QRect(100, 800, 500, 200), QRect(0, 0, 1920, 1080), 1.0, (600, 800, 216)),
        (
            QRect(-1800, 200, 500, 600),
            QRect(-1920, 0, 1920, 1080),
            1.0,
            (-1300, 200, 640),
        ),
        (QRect(100, 100, 500, 600), QRect(0, 0, 3840, 2160), 2.0, (600, 100, 1280)),
    ],
)
def test_square_preview_initial_edge_placement(
    anchor: QRect, area: QRect, scale: float, expected: tuple[int, int, int]
) -> None:
    from cephvr.gui.preview_placement import square_preview_placement

    result = square_preview_placement(anchor, area, scale)
    assert (result.x, result.y, result.side) == expected


def test_review_blank_preview_connect_close_and_disconnect(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    import cephvr.gui.review_preview as previews

    visible: set[str] = set()
    shown: list[str] = []
    cv = SimpleNamespace(
        WINDOW_NORMAL=0,
        WND_PROP_VISIBLE=1,
        error=RuntimeError,
        namedWindow=lambda title, _: visible.add(title),
        imshow=lambda title, _: shown.append(title),
        waitKey=lambda _: None,
        moveWindow=lambda *_: None,
        resizeWindow=lambda *_: None,
        setWindowTitle=lambda *_: None,
        destroyWindow=lambda title: visible.discard(title),
        getWindowProperty=lambda title, _: int(title in visible),
    )
    monkeypatch.setitem(sys.modules, "cv2", cv)
    monkeypatch.setattr(previews, "position_preview_frame", lambda *_, **_kw: None)
    monkeypatch.setattr(previews, "preview_window_handle", lambda _title: 99)
    monkeypatch.setattr(previews, "blank_preview_caption", lambda _handle: None)
    monkeypatch.setattr(
        previews,
        "StagedPreviewWindow",
        lambda _: nullcontext(SimpleNamespace(show=lambda _: None)),
    )
    owner_state = {"minimized": False}
    monkeypatch.setattr(
        previews,
        "bind_preview_owner",
        lambda *_: SimpleNamespace(
            sync=lambda _minimized=None: owner_state["minimized"],
            close=lambda: None,
            geometry=lambda: (0, 0, 300, 330),
            placement_revision=lambda: None,
            retarget=lambda _handle: None,
        ),
    )
    target = DashboardWindow(sample=True)
    controls = ReviewControls(target, fake_previews=True)
    viewers = controls.preview_windows
    assert viewers is not None
    cameras = target.devices.cameras
    try:
        monkeypatch.setattr(
            target.screen(), "availableGeometry", lambda: QRect(0, 0, 1920, 1080)
        )
        target.resize(1440, 940)
        target.show()
        for _ in range(4):
            app.processEvents()
        target.select_page(2)
        target.devices.tabs.setCurrentIndex(0)
        app.processEvents()
        # The Cameras grid shows only while a camera viewer is open or pending.
        assert not target.preview_slot.isVisible()
        cameras.table.selectRow(0)
        camera = cameras.selected
        assert camera is not None
        cameras.toggle_connection()
        assert camera.connected and camera.capture_running
        assert camera.key in viewers.windows and len(visible) == 1
        app.processEvents()
        assert target.preview_slot.isVisible()
        frame = viewers.windows[camera.key][1]
        assert not frame.any()
        viewers.poll_windows()
        assert len(shown) == 1
        assert not frame.any()
        owner_state["minimized"] = True
        visible.clear()
        viewers.poll_windows()
        assert camera.key in viewers.windows
        assert target.dashboard.view.previews[0].visible
        owner_state["minimized"] = False
        visible.add(viewers.windows[camera.key][0])
        viewers.poll_windows()
        assert len(shown) == 1
        # Native X clears Show without disconnecting the fixture or recreating it.
        controls.observer.setChecked(True)
        visible.clear()
        viewers.poll_windows()
        assert not viewers.windows and not viewers.timer.isActive()
        assert camera.connected and camera.capture_running
        app.processEvents()
        assert not target.preview_slot.isVisible()
        assert not next(
            p for p in target.dashboard.view.previews if p.key == camera.key
        ).visible
        controls.observer.setChecked(False)
        controls.preview_visibility(camera.key, True)
        assert len(visible) == 1
        cameras.toggle_connection()
        assert not camera.connected and not viewers.windows and not visible
        app.processEvents()
        assert not target.preview_slot.isVisible()
        assert not visible and not viewers.timer.isActive()
    finally:
        viewers.close()
        target.close()
        target.deleteLater()
        app.processEvents()


def test_review_stimulus_viewer_lives_in_runtime_layout(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    import cephvr.gui.review_preview as previews

    visible: set[str] = set()
    shown: list[str] = []
    cv = SimpleNamespace(
        WINDOW_NORMAL=0,
        WND_PROP_VISIBLE=1,
        error=RuntimeError,
        namedWindow=lambda title, _: visible.add(title),
        imshow=lambda title, _: shown.append(title),
        waitKey=lambda _: None,
        moveWindow=lambda *_: None,
        resizeWindow=lambda *_: None,
        setWindowTitle=lambda *_: None,
        destroyWindow=lambda title: visible.discard(title),
        getWindowProperty=lambda title, _: int(title in visible),
    )
    monkeypatch.setitem(sys.modules, "cv2", cv)
    monkeypatch.setattr(previews, "position_preview_frame", lambda *_, **_kw: None)
    monkeypatch.setattr(previews, "preview_window_handle", lambda _title: 99)
    monkeypatch.setattr(previews, "blank_preview_caption", lambda _handle: None)
    monkeypatch.setattr(
        previews,
        "StagedPreviewWindow",
        lambda _: nullcontext(SimpleNamespace(show=lambda _: None)),
    )
    owner_state = {"minimized": False}
    monkeypatch.setattr(
        previews,
        "bind_preview_owner",
        lambda *_: SimpleNamespace(
            sync=lambda _minimized=None: owner_state["minimized"],
            close=lambda: None,
            geometry=lambda: (0, 0, 300, 330),
            placement_revision=lambda: None,
            retarget=lambda _handle: None,
        ),
    )
    target = DashboardWindow(sample=True)
    controls = ReviewControls(target, fake_previews=True)
    viewers = controls.preview_windows
    assert viewers is not None
    try:
        monkeypatch.setattr(
            target.screen(), "availableGeometry", lambda: QRect(0, 0, 1920, 1080)
        )
        target.resize(1440, 940)
        target.show()
        app.processEvents()
        # Before Start the Dashboard has no preview footprints.
        assert not target.preview_slot.isVisible()
        show_previews(target)
        app.processEvents()
        assert target.preview_slot.isVisible()
        controls.preview_visibility("stimulus", True)
        assert "stimulus" in viewers.windows
        assert not viewers.windows["stimulus"][1].any()
        controls.preview_visibility("stimulus", False)
        app.processEvents()
        # Active footprints stay reserved for the whole run.
        assert target.preview_slot.isVisible()
        # Leaving the runtime layout hides them again.
        target.apply_view(replace(target.dashboard.view, phase=Phase.ENDED))
        app.processEvents()
        assert not target.dashboard.runtime_layout
        assert not target.preview_slot.isVisible()
        assert not visible and not viewers.timer.isActive()
    finally:
        viewers.close()
        target.close()
        target.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("page", [0, 2])
@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_multiple_review_previews_have_independent_source_frames(
    app: QApplication, monkeypatch: pytest.MonkeyPatch, page: int, style: str
) -> None:
    import sys

    import cephvr.gui.review_preview as previews
    from cephvr.platform.windows.window_coordinates import preview_frame_extra

    visible: set[str] = set()
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            WINDOW_NORMAL=0,
            WND_PROP_VISIBLE=1,
            error=RuntimeError,
            namedWindow=lambda title, _: visible.add(title),
            imshow=lambda *_: None,
            waitKey=lambda _: None,
            moveWindow=lambda *_: None,
            resizeWindow=lambda *_: None,
            setWindowTitle=lambda *_: None,
            destroyWindow=lambda title: visible.discard(title),
            getWindowProperty=lambda title, _: int(title in visible),
        ),
    )
    monkeypatch.setattr(previews, "position_preview_frame", lambda *_, **_kw: None)
    monkeypatch.setattr(previews, "preview_window_handle", lambda _title: 99)
    monkeypatch.setattr(previews, "blank_preview_caption", lambda _handle: None)
    monkeypatch.setattr(
        previews,
        "StagedPreviewWindow",
        lambda _: nullcontext(SimpleNamespace(show=lambda _: None)),
    )
    monkeypatch.setattr(
        previews,
        "bind_preview_owner",
        lambda *_: SimpleNamespace(
            sync=lambda *_: False,
            close=lambda: None,
            geometry=lambda: (0, 0, 300, 330),
            placement_revision=lambda: None,
            retarget=lambda _handle: None,
        ),
    )
    target = DashboardWindow(sample=True)
    controls = ReviewControls(target, fake_previews=True)
    viewers = controls.preview_windows
    assert viewers is not None
    try:
        target.appearance.select(style, persist=False)
        monkeypatch.setattr(
            target.screen(), "availableGeometry", lambda: QRect(0, 0, 2200, 1500)
        )
        target.resize(1600, 1100)
        target.show()
        target.select_page(page)
        if page == 0:
            show_previews(target)
        for _ in range(4):
            app.processEvents()
        status = (
            target.dashboard.status_column
            if page == 0
            else target.devices.cameras.status_column
        )
        original_log_height = status.console.height()
        initial_placement = viewers.placement
        positions = {}

        def placement(key):
            hint = initial_placement(key)
            width, height = preview_frame_extra()
            positions[key] = QRect(
                hint.x, hint.y, hint.side + width, hint.side + height
            )
            return hint

        viewers.placement = placement
        enabled = {
            camera.key for camera in target.devices.cameras.drafts if camera.enabled
        }
        keys = [
            p.key
            for p in target.dashboard.view.previews
            if p.active and (page == 0 or p.key in enabled)
        ][:3]
        assert len(keys) == (3 if page == 0 else 2)
        assert target.preview_slot.isHidden() is (page != 0)
        for key in keys:
            controls.preview_visibility(key, True)
            app.processEvents()
            viewers.poll_windows()
        assert set(viewers.windows) == set(keys)
        assert len(visible) == len(keys)
        for key, frame in positions.items():
            slot = target.preview_slot.target_for(key)
            assert QRect(slot.mapToGlobal(QPoint()), slot.size()).contains(frame)
        frames = list(positions.values())
        assert all(
            not a.intersects(b) for i, a in enumerate(frames) for b in frames[i + 1 :]
        )
        if page == 0:
            # Embedded in the Dashboard window; its form log is not resized.
            assert target.preview_slot.window() is target
            assert target.dashboard.preview_workspace.isAncestorOf(target.preview_slot)
        else:
            assert status.hud_card.y() == 0
            assert target.preview_slot.y() > status.log_card.geometry().bottom()
            assert status.console.height() < original_log_height
        controls.preview_visibility(keys[0], False)
        app.processEvents()
        assert set(viewers.windows) == set(keys[1:])
        viewers.poll_windows()
        # Hiding a stream frees its frame on every page (G01 Monitor view).
        assert set(target.preview_slot.frames) == set(keys[1:])
        # An external X closes just its own source, preserving the other stream.
        visible.remove(viewers.windows[keys[1]][0])
        viewers.poll_windows()
        assert set(viewers.windows) == set(keys[2:])
        for key in keys[2:]:
            controls.preview_visibility(key, False)
        app.processEvents()
        assert target.preview_slot.isHidden() is (page != 0)
        assert status.console.height() == original_log_height
    finally:
        viewers.close()
        target.close()
        target.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_camera_preview_slots_only_include_enabled_cameras(
    window: DashboardWindow, app: QApplication, style: str
) -> None:
    window.appearance.select(style, persist=False)
    cameras = window.devices.cameras
    assert len(cameras.drafts) >= 2
    enabled_camera, disabled_camera = cameras.drafts[:2]
    enabled_camera.enabled = True
    disabled_camera.enabled = False
    disabled_camera.connected = True
    sources = window.dashboard.view.previews
    assert "stimulus" in {source.key for source in sources}
    view = replace(
        window.dashboard.view,
        previews=tuple(replace(source, visible=True) for source in sources),
    )
    window.apply_view(view)
    app.processEvents()
    assert set(window.preview_slot.frames) == {source.key for source in sources}
    window.select_page(2)
    app.processEvents()
    assert set(window.preview_slot.frames) == {enabled_camera.key}
    from cephvr.gui.preview_placement import preview_window_placement

    # Diagnostic Connect remains independent of experiment enablement (A10).
    assert preview_window_placement(window, disabled_camera.key).side >= 128
    assert window.preview_slot.isVisible()
    window.apply_view(
        replace(
            view,
            previews=tuple(
                replace(source, visible=source.key == "stimulus") for source in sources
            ),
        )
    )
    app.processEvents()
    assert window.preview_slot.isHidden()
    assert (
        cameras.status_column.console.minimumHeight()
        == cameras.status_column.log_minimum_height
    )
    disabled_camera.enabled = True
    window.apply_view(view)
    app.processEvents()
    assert set(window.preview_slot.frames) == {enabled_camera.key, disabled_camera.key}
    disabled_camera.enabled = False
    window.apply_view(view)
    app.processEvents()
    assert set(window.preview_slot.frames) == {enabled_camera.key}
    enabled_camera.enabled = False
    window.apply_view(view)
    app.processEvents()
    assert window.preview_slot.isHidden()
    assert (
        cameras.status_column.console.minimumHeight()
        == cameras.status_column.log_minimum_height
    )
    window.select_page(0)
    show_previews(window)
    app.processEvents()
    assert set(window.preview_slot.frames) == {source.key for source in sources}
    assert window.preview_slot.isVisible()


def test_startup_maximize_survives_first_layout_and_allows_later_restore(
    app: QApplication,
) -> None:
    from cephvr.gui.layouts import show_maximized

    target = QWidget()
    try:
        show_maximized(target)
        assert target.isMaximized()
        target.showNormal()
        app.processEvents()
        assert target.isMaximized()
        target.showNormal()
        app.processEvents()
        assert not target.isMaximized()
    finally:
        target.close()


def test_square_preview_placement_fits_small_work_area() -> None:
    from cephvr.gui.preview_placement import square_preview_placement

    area = QRect(-800, -600, 800, 600)
    result = square_preview_placement(QRect(-100, -10, 800, 600), area)
    assert result.side == 536
    assert area.left() <= result.x <= area.right() - result.side
    assert result.y == area.top()


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_preview_slot_fits_native_frame(scale: float) -> None:
    from cephvr.gui.preview_placement import slot_preview_placement
    from cephvr.platform.windows.window_coordinates import preview_frame_extra

    slot = QRect(-900, 100, round(400 * scale), round(500 * scale))
    result = slot_preview_placement(slot, QRect(-1920, 0, 3840, 2160), scale)
    width, height = preview_frame_extra(scale)
    assert result.side + width == slot.width()
    assert result.side + height <= slot.height()
    assert result.x == slot.x()
    assert result.y == slot.y() + (slot.height() - result.side - height) // 2


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_preview_slot_centers_frame_in_visible_card(scale: float) -> None:
    from cephvr.gui.preview_placement import slot_preview_placement
    from cephvr.platform.windows.window_coordinates import preview_frame_extra

    slot = QRect(-1100, -100, round(900 * scale), round(500 * scale))
    area = QRect(-1000, 0, 3000, 1600)
    bounds = slot.intersected(area)
    result = slot_preview_placement(slot, area, scale)
    width, height = preview_frame_extra(scale)
    frame = QRect(result.x, result.y, result.side + width, result.side + height)
    assert bounds.contains(frame)
    assert abs(frame.center().x() - bounds.center().x()) <= 1
    assert abs(frame.center().y() - bounds.center().y()) <= 1
    assert result.side == min(2048, bounds.width() - width, bounds.height() - height)


@pytest.mark.parametrize("slot", [QRect(0, 0, 100, 100), QRect(3000, 0, 500, 500)])
def test_preview_slot_rejects_insufficient_visible_space(slot: QRect) -> None:
    from cephvr.gui.preview_placement import slot_preview_placement

    with pytest.raises(ValueError, match="insufficient visible space"):
        slot_preview_placement(slot, QRect(0, 0, 1920, 1080))


def test_cocoa_preview_position_converts_work_height_origin() -> None:
    from cephvr.gui.preview_placement import cocoa_preview_position

    assert cocoa_preview_position(900, 650, 982, 923) == (900, 591)
    assert cocoa_preview_position(-1200, -500, 982, 1440) == (-1200, -42)


def test_preview_slot_centers_resizable_native_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cephvr.gui.preview_placement as placement

    monkeypatch.setattr(placement, "preview_frame_extra", lambda _scale: (2, 32))
    result = placement.slot_preview_placement(
        QRect(0, 0, 400, 200), QRect(0, 0, 1920, 1080)
    )
    assert result.side == 168
    assert result.x == 115
    narrow = placement.slot_preview_placement(
        QRect(0, 0, 190, 200), QRect(0, 0, 1920, 1080)
    )
    assert narrow.side == 168 and narrow.x == 10
    with pytest.raises(ValueError, match="insufficient visible space"):
        placement.slot_preview_placement(QRect(0, 0, 100, 200), QRect(0, 0, 1920, 1080))


def test_preview_placement_failure_restores_hidden_card_and_expanded_log(
    window: DashboardWindow, app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cephvr.gui.preview_placement as placement

    for _ in range(4):
        app.processEvents()
    height = window.dashboard.log_console.height()

    def unavailable(*_args: object) -> object:
        raise ValueError("Preview placement unavailable")

    monkeypatch.setattr(placement, "slot_preview_placement", unavailable)
    with pytest.raises(ValueError, match="Preview placement unavailable"):
        placement.preview_window_placement(window)
    assert not window.preview_slot.isVisible()
    assert window.dashboard.log_console.height() == height


def test_preview_cards_name_their_source_and_draw_retro_frame(
    app: QApplication,
) -> None:
    from PyQt6.QtGui import QColor

    from cephvr.gui.preview_placement import PreviewSlot
    from cephvr.gui.retro_instruments import blink
    from cephvr.gui.theme import RETRO_COLORS

    slot = PreviewSlot()
    slot.setProperty("retroConsole", True)
    slot.resize(500, 560)
    slot.show()
    app.processEvents()
    frame = slot.frames[""]
    assert frame.empty and slot.caption.text() == "[ PREVIEW ]"
    blink().on = True
    placeholder = frame.grab().toImage()
    frame.empty = False
    quiet = frame.grab().toImage()
    # NO SIGNAL appears only inside the empty footprint.
    assert placeholder != quiet
    middle = frame.target.geometry().center().y()
    left = frame.target.geometry().left()
    assert QColor(quiet.pixelColor(left - 2, middle)) == QColor(RETRO_COLORS.accent)
    assert QColor(quiet.pixelColor(left - 5, middle)) == QColor(RETRO_COLORS.border)

    slot.set_sources((PreviewView("behavior", "Behavior cam", visible=True),))
    named = slot.frames["behavior"]
    assert not named.empty and named.caption.text() == "[ BEHAVIOR CAM ]"
    slot.set_sources(())
    assert slot.caption.text() == "[ PREVIEW ]" and slot.frames[""].empty
    slot.deleteLater()


def test_preview_slot_tracks_relevant_tabs(
    window: DashboardWindow, app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui.preview_placement import preview_window_placement

    camera_key = window.devices.cameras.drafts[0].key
    window.devices.cameras.drafts[0].enabled = True
    window.showMaximized()
    for _ in range(4):
        app.processEvents()
    assert window.isMaximized()
    window.showNormal()
    monkeypatch.setattr(
        window.screen(), "availableGeometry", lambda: QRect(0, 0, 1920, 1080)
    )
    window.resize(1440, 940)
    for _ in range(4):
        app.processEvents()
    assert not window.preview_slot.isVisible()  # Dashboard hosts it only after Start.
    show_previews(window)
    app.processEvents()
    expanded_log_height = window.dashboard.log_console.height()
    window.apply_view(
        replace(window.dashboard.view, previews=(PreviewView(camera_key, "Camera"),))
    )
    app.processEvents()
    opening = preview_window_placement(window, camera_key)
    assert window.preview_slot.isHidden()
    assert window.dashboard.log_console.height() == expanded_log_height
    window.apply_view(
        replace(
            window.dashboard.view,
            previews=(PreviewView(camera_key, "Camera", visible=True),),
        )
    )
    app.processEvents()
    assert preview_window_placement(window) == opening
    for page, device, visible in (
        (0, 0, True),
        (1, 0, False),
        (2, 0, True),
        (2, 1, False),
        (2, 2, False),
        (3, 2, True),
    ):
        window.devices.tabs.setCurrentIndex(device)
        window.select_page(page)
        app.processEvents()
        assert window.preview_slot.isVisible() is visible
        if visible:
            slot = window.preview_slot
            frame_widget = next(iter(slot.frames.values()))
            target = frame_widget.target
            region = window.dashboard.preview_workspace if page == 0 else window.stack
            assert slot.height() < region.height()
            assert target.geometry().top() > frame_widget.header.geometry().bottom()
            assert (
                abs(target.geometry().center().x() - frame_widget.rect().center().x())
                <= 1
            )
            assert slot.property("role") != "card"
            assert slot.caption.text() == "[ CAMERA ]"
            assert target.geometry().bottom() + 9 <= frame_widget.height()
            panel = window.stack.currentWidget()
            if panel is window.devices:
                panel = window.devices.cameras
            if page == 0:
                assert slot.window() is window
                assert window.dashboard.preview_workspace.isAncestorOf(slot)
                continue
            status = panel.columns[1]
            assert slot.parentWidget() is status
            assert slot.y() > status.log_card.geometry().bottom()
            assert status.hud_card.y() == 0
            if panel.mode == "wide":
                assert (
                    status.mapTo(window, QPoint()).x()
                    > panel.columns[0].mapTo(window, QPoint()).x()
                )
            assert (
                status.hud_card.geometry().left() == status.log_card.geometry().left()
            )
            if page != 0:
                assert slot.geometry().left() == status.log_card.geometry().left()
                assert slot.geometry().bottom() < status.height()
            if QApplication.platformName() != "windows":
                hint = preview_window_placement(window)
                origin = target.mapToGlobal(QPoint())
                from cephvr.platform.windows.window_coordinates import (
                    preview_frame_extra,
                )

                width, height = preview_frame_extra()
                frame = QRect(hint.x, hint.y, hint.side + width, hint.side + height)
                assert QRect(origin, target.size()).contains(frame)


@pytest.fixture
def window(app: QApplication) -> Iterator[DashboardWindow]:
    result = DashboardWindow(sample=True)
    ReviewControls(result)
    from cephvr.gui.protocol_document import review_program

    result.protocol.editor.set_program(review_program())
    result.show()
    app.processEvents()
    yield result
    result.close()
    result.deleteLater()
    app.processEvents()


def _move_mouse_and_wait_for_native_event(
    widget: QWidget, position: QPoint, app: QApplication, *, timeout_ms: int = 1000
) -> None:
    """Wait for the platform-delivered hover event after moving the real cursor."""
    from PyQt6.QtCore import QObject

    target_global = widget.mapToGlobal(position)
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    matched = False

    class TargetMouseMove(QObject):
        def eventFilter(self, receiver, event):
            nonlocal matched
            if (
                receiver is widget
                and event.type() == QEvent.Type.MouseMove
                and event.globalPosition().toPoint() == target_global
            ):
                matched = True
                QTimer.singleShot(0, loop.quit)
            return False

    probe = TargetMouseMove(widget)
    widget.installEventFilter(probe)
    timer.start(timeout_ms)
    try:
        QTest.mouseMove(widget, position)
        if not matched:
            loop.exec()
    finally:
        timer.stop()
        widget.removeEventFilter(probe)
    assert matched, (
        f"native MouseMove was not delivered to {type(widget).__name__} at "
        f"{target_global} within {timeout_ms} ms; visible={widget.isVisible()}, "
        f"global geometry={widget.mapToGlobal(widget.rect().topLeft())} "
        f"{widget.size()}"
    )
    app.processEvents()


class ParameterDocument:
    """Document sink for parameter-widget tests, independent of planner navigation."""

    def __init__(self, window):
        from cephvr.gui.protocol_document import blank_program
        from cephvr.gui.stimulus_parameters import StimulusParameters

        self.parameters = StimulusParameters()
        self.parameters.setParent(window)
        self.parameters.committed.connect(self.accept)
        window.protocol.session_mode.currentTextChanged.connect(
            lambda value: self.parameters.set_closed_loop(value == "Closed-loop")
        )
        self.parameters.set_closed_loop(
            window.protocol.session_mode.currentText() == "Closed-loop"
        )
        self.set_program(blank_program())

    def accept(self, program):
        self.program = program
        self.parameters.program = program

    def set_program(self, program):
        self.program = program
        self.parameters.bind(program, (0,), 0 if program.sequence[0].settings else -1)

    def add_stimulus(self, preset):
        from cephvr.gui.stimulus_presets import add_stimulus

        program = add_stimulus(self.program, (0,), preset, ("Left", "Right"))
        self.program = program
        self.parameters.bind(program, (0,), len(program.sequence[0].settings) - 1)

    def remove_stimulus(self):
        from cephvr.gui.stimulus_presets import remove_stimulus

        self.set_program(
            remove_stimulus(self.program, (0,), self.parameters.layer_index)
        )


def open_protocol_group(editor, *, generate=False):
    """Put UI-control tests in the supported group editing scope."""
    from cephvr.gui.protocol_batches import grouped_program

    editor.set_program(grouped_program(editor.program))
    editor.enter_group()


def test_unpatched_modal_is_recorded_instead_of_blocking(
    window: DashboardWindow, unexpected_modals: list[str], monkeypatch
) -> None:
    from PyQt6.QtWidgets import QMessageBox

    import cephvr.gui.window as window_module

    def broken(*args, **kwargs):
        raise ValueError("asset folder missing")

    monkeypatch.setattr(window_module, "TrialPreview", broken)
    window.open_trial_preview()
    assert window.trial_preview is None
    assert unexpected_modals == ["information: Trial preview: asset folder missing"]
    assert QMessageBox.question(window, "Q", "?") == QMessageBox.StandardButton.NoButton
    unexpected_modals.clear()  # Recorded as expected; do not fail at teardown.


def test_offline_frontend_cannot_request_commands(app: QApplication) -> None:
    window = DashboardWindow()
    requests: list[str] = []
    window.dashboard.action_requested.connect(requests.append)
    window.dashboard.request_action("Setup")
    assert requests == []
    assert not any(
        control.isEnabled() for control in window.dashboard.command_buttons.values()
    )
    assert not window.dashboard.subject_id.isEnabled()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_protocol_config_round_trip_retains_complete_schedule(
    window: DashboardWindow, tmp_path: Path
) -> None:
    import json

    from cephvr.gui.protocol_document import TrialDraft, blank_program
    from cephvr.gui.protocol_snapshot import (
        capture_protocol,
        restore_protocol,
        validate_protocol,
    )

    page = window.protocol
    data = capture_protocol(page)
    data["mode"], data["asset_root"] = "Closed-loop", "C:/实验/assets"
    trial = data["trials"][0]
    trial.update(
        name="First",
        path="logical/first.json",
        stimulus_seed_decimal="12",
        gap_after_seconds="0.125",
        arena_boundaries_json='{"format_version":1,"bindings":[]}',
    )
    data["trials"] = [
        trial,
        dict(trial, name="Second", stimulus_seed_decimal="99", gap_after_seconds=""),
    ]
    data["selected_trial"] = 1
    restore_protocol(page, validate_protocol(data))
    path = tmp_path / "protocol.json"
    assert page.config_files.save_path(str(path))
    restore_protocol(
        page,
        validate_protocol(
            dict(data, mode="Open-loop", selected_trial=0, trials=[data["trials"][0]])
        ),
    )
    assert page.config_files.load_path(str(path))
    assert capture_protocol(page) == data
    saved = json.loads(path.read_text())
    saved["trials"][0]["stimulus_seed_decimal"] = "0"
    saved["trials"][1]["stimulus_seed_decimal"] = "42"
    path.write_text(json.dumps(saved), encoding="utf-8")
    assert page.config_files.load_path(str(path))
    for index in (0, 1):
        page.editor.trials.setCurrentRow(index)
    assert page.config_files.save_path(str(path))
    assert [
        trial["stimulus_seed_decimal"]
        for trial in json.loads(path.read_text())["trials"]
    ] == ["0", "42"]
    # Existing canonical single-trial documents remain accepted by the toolbar.
    path.write_text(blank_program().model_dump_json(), encoding="utf-8")
    assert page.config_files.load_path(str(path))
    assert len(page.editor.drafts) == 2
    assert isinstance(page.editor.drafts[1], TrialDraft)
    assert page.editor.drafts[1].path == str(path)


def test_microcontroller_config_load_is_local_and_collects_for_normal_submission(
    window: DashboardWindow, tmp_path: Path
) -> None:
    panel = window.devices.microcontroller
    data = panel.snapshots.capture()
    data.update(port="COM91", firmware_path="C:/实验/firmware.ino")
    data["trial_state"] = {"pin": "D8", "enabled": False}
    data["projector_flip"] = {"pin": "D2", "enabled": True}
    data["camera_pins"] = {
        key: f"D{9 + index}" for index, key in enumerate(data["camera_pins"])
    }
    from cephvr.gui.configuration_files import write_snapshot

    path = tmp_path / "mcu.json"
    write_snapshot(str(path), data)
    requests: list[tuple[object, ...]] = []
    panel.save_requested.connect(lambda *args: requests.append(args))
    panel.firmware_requested.connect(lambda *args: requests.append(args))
    panel.connection_requested.connect(lambda *args: requests.append(args))
    panel.managed = True
    assert panel.config_files.load_path(str(path))
    data["projector_flip"]["enabled"] = False
    data["review_outputs"]["selected"] = sorted(["trial-state", *data["camera_pins"]])
    assert panel.snapshots.capture() == data
    assert requests == []
    assert "Apply pin settings" not in [
        b.text() for b in panel.findChildren(QPushButton)
    ]
    from cephvr.control.v1 import types_pb2 as pb

    settings = pb.AcquisitionSettings()
    panel.snapshots.collect(settings)
    assert settings.pulses.port == "COM91"
    assert settings.pulses.trial_state_pin == "D8"
    assert not settings.pulses.trial_state_enabled
    assert requests == []


def test_spikeglx_config_replaces_custom_rows_preserves_host_and_file_identity(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from PyQt6.QtWidgets import QLineEdit

    from cephvr.gui.configuration_files import write_snapshot

    panel = window.devices.spikeglx
    assert not hasattr(panel, "save_inventory")
    panel.add_custom()
    key = panel.row_keys[-1]
    signal, stream, index, channel, bit = panel.rows[key]
    assert isinstance(signal, QLineEdit)
    signal.setText("stimulus-sync")
    data = panel.snapshots.capture()
    data["rows"][-1].update(stream="NI", index="2", channel="7", bit="3", enabled=False)
    data["host_reference"].update(
        address="other-server", command_port="4142", pairing=True
    )
    path = tmp_path / "spike.json"
    write_snapshot(str(path), data)
    host = panel.snapshots.host()
    panel.inventory_file_sha256 = "current-controller-digest"
    requests: list[object] = []
    panel.inventory_update_requested.connect(requests.append)
    panel.add_custom()
    assert panel.config_files.load_path(str(path))
    actual = panel.snapshots.capture()
    assert actual["rows"] == data["rows"]
    assert actual["host_reference"] == host
    assert panel.inventory_file_sha256 == "current-controller-digest"
    assert requests == []
    assert [
        panel.table.horizontalHeaderItem(i).text()
        for i in range(panel.table.columnCount())
        if not panel.table.isColumnHidden(i)
    ] == ["Use", "Signal", "Channel index", ""]
    panel.add_custom()
    assert len(set(panel.row_keys)) == len(panel.row_keys)


def test_camera_config_round_trip_is_local_and_requires_matching_stopped_inventory(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.configuration_files import write_snapshot

    panel = window.devices.cameras
    data = panel.snapshots.capture()
    data["cameras"][0]["values"] = {
        "trigger_clock": "External controller",
        "trigger_source": "Line3",
        "trigger_frequency_hz": "30",
    }
    data["cameras"][1]["enabled"] = False
    path = tmp_path / "cameras.json"
    write_snapshot(str(path), data)
    requests = []
    for signal in (
        panel.enable_requested,
        panel.role_requested,
        panel.settings_requested,
    ):
        signal.connect(lambda *args: requests.append(args))
    panel.managed = True
    assert panel.config_files.load_path(str(path))
    assert panel.snapshots.capture() == data
    assert requests == []
    panel.table.selectRow(1)
    tests = []
    panel.connection_requested.connect(lambda *args: tests.append(args))
    panel.connect_button.click()
    assert tests == [(panel.drafts[1].key, True)]
    assert not panel.drafts[1].enabled
    saved = tmp_path / "saved-cameras.json"
    assert panel.config_files.save_path(str(saved))
    assert panel.config_files.load_path(str(saved))
    invalid = panel.snapshots.capture()
    invalid["cameras"][0]["serial"] = "wrong-camera"
    with pytest.raises(ValueError, match="serials differ"):
        panel.snapshots.validate(invalid)
    assert panel.snapshots.capture() == data
    panel.drafts[0].capture_running = True
    panel.refresh_controls()
    assert not panel.config_files.load_button.isEnabled()
    assert not panel.snapshots.available()
    panel.drafts[0].capture_running = False
    panel.operation_pending = True
    panel.refresh_controls()
    assert not panel.snapshots.available()
    panel.operation_pending = False
    window.apply_view(review_view(Phase.RUNNING))
    assert not panel.config_files.save_button.isEnabled()


@pytest.mark.parametrize(
    "owner",
    [
        "protocol",
        "cameras",
        "microcontroller",
        "projectors",
        "spikeglx",
        "tracking",
        "gui",
    ],
)
def test_tab_config_buttons_roundtrip_into_fresh_gui(
    window: DashboardWindow,
    app: QApplication,
    tmp_path: Path,
    owner: str,
) -> None:
    from cephvr.gui.camera_inventory import CameraDraft

    fresh = DashboardWindow(sample=True)
    for target in (window, fresh):
        cameras = target.devices.cameras
        cameras.drafts.append(
            CameraDraft(
                "camera-3",
                "Eye tracking",
                "REVIEW-003",
                "Basler · sample",
                values={
                    "trigger_clock": "External controller",
                    "trigger_source": "Line3",
                    "trigger_frequency_hz": "45",
                },
            )
        )
        cameras.populate_inventory()
        cameras.drafts_changed.emit()
        target.apply_view(review_view(Phase.CONFIGURATION))
        cameras.managed = target.devices.microcontroller.managed = True
    window.devices.microcontroller.set_saved_pins("COM88", "D12", True, "D2", True)
    for key, pin in (("behavioral", "10"), ("tracking", "11"), ("eye_tracking", "8")):
        window.devices.microcontroller.pin_editors[key].setText(pin)
    window.dashboard.subject_id.setText("saved-subject")
    window.tracking.forms.fields["threshold"].setText("123")
    commands = []
    for target in (window, fresh):
        for signal in (
            target.devices.cameras.enable_requested,
            target.devices.cameras.role_requested,
            target.devices.cameras.settings_requested,
            target.devices.microcontroller.save_requested,
            target.devices.microcontroller.connection_requested,
            target.devices.microcontroller.firmware_requested,
        ):
            signal.connect(lambda *args: commands.append(args))

    def files(target):
        if owner == "gui":
            return target.config_files
        panel = getattr(
            target if owner in ("protocol", "tracking") else target.devices, owner
        )
        return panel.calibration_files if owner == "projectors" else panel.config_files

    def capture(target):
        selected = files(target)
        return selected.snapshot() if owner == "projectors" else selected.capture()

    try:
        original = capture(window)
        path = tmp_path / f"{owner}-实验.json"
        writer = files(window)
        assert writer.save_button.isEnabled()
        writer.save_button.click()
        assert writer.dialog is not None
        writer.dialog.selectFile(str(path))
        writer.dialog.accept()
        app.processEvents()
        assert path.is_file()
        reader = files(fresh)
        assert reader.load_button.isEnabled()
        reader.load_button.click()
        assert reader.dialog is not None
        reader.dialog.selectFile(str(path))
        reader.dialog.accept()
        app.processEvents()
        assert capture(fresh) == original
        assert commands == []
        if owner in ("microcontroller", "gui"):
            assert (
                fresh.devices.microcontroller.pin_editors["eye_tracking"].text() == "8"
            )
            assert fresh.devices.microcontroller.flip_pin.text() == "2"
            assert not fresh.devices.microcontroller.enable_controls[
                "projector-flip"
            ].isChecked()
    finally:
        fresh.close()
        fresh.deleteLater()
        app.processEvents()


def test_full_gui_config_round_trip_restores_all_sections_without_commands(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.configuration_files import write_snapshot

    data = window.snapshots.capture()
    data["experiment"]["dashboard"].update(
        subject_id="octopus-7",
        experiment="experimenter-A",
        condition="drift",
        output_root="C:/experiments/A",
    )
    data["experiment"]["cameras"][0]["values"] = {
        "trigger_clock": "External controller",
        "trigger_source": "Line2",
        "trigger_frequency_hz": "18",
        "preset": "C:/presets/A.pfs",
    }
    data["experiment"]["recordings"]["stimulus"] = False
    data["protocol"]["mode"] = "Closed-loop"
    data["protocol"]["asset_root"] = "C:/experiment-assets"
    data["microcontroller"]["port"] = "COM92"
    data["tracking"]["distance_mm"] = "25"
    data["projectors"]["configuration"]["settings"]["photodiode_enabled"] = False
    path = tmp_path / "experiment.json"
    write_snapshot(str(path), data)
    requests: list[object] = []
    for signal in (
        window.dashboard.action_requested,
        window.devices.cameras.settings_requested,
        window.devices.cameras.role_requested,
        window.devices.cameras.enable_requested,
        window.devices.microcontroller.save_requested,
        window.devices.spikeglx.inventory_update_requested,
    ):
        signal.connect(lambda *args: requests.append(args))
    assert window.config_files.load_path(str(path))
    assert window.snapshots.capture() == data
    assert requests == []
    assert window.devices.cameras.snapshot_draft
    assert window.devices.microcontroller.snapshots.draft_loaded
    assert window.recordings.touched == {
        "stimulus",
        "velocities",
        "camera-1",
        "camera-2",
    }
    saved = tmp_path / "saved.json"
    assert window.config_files.save_path(str(saved))
    assert window.config_files.load_path(str(saved))
    assert window.snapshots.capture() == data


@pytest.mark.parametrize(
    "section",
    ["experiment", "protocol", "microcontroller", "projectors", "spikeglx", "tracking"],
)
def test_invalid_full_gui_config_changes_no_section(
    window: DashboardWindow, tmp_path: Path, section: str
) -> None:
    from cephvr.gui.configuration_files import write_snapshot

    before = window.snapshots.capture()
    malformed = window.snapshots.capture()
    malformed["experiment"]["dashboard"]["subject_id"] = "must-not-be-restored"
    malformed[section] = {"unexpected": True}
    path = tmp_path / "invalid.json"
    write_snapshot(str(path), malformed)
    assert not window.config_files.load_path(str(path))
    assert window.snapshots.capture() == before


@pytest.mark.parametrize(
    "payload", ['{"format": "a", "format": "b"}', '{"n": NaN}', "[1,2]", '{"invalid":']
)
def test_gui_snapshot_rejects_invalid_json_before_editing(
    window: DashboardWindow, tmp_path: Path, payload: str
) -> None:
    before = window.snapshots.capture()
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    assert not window.config_files.load_path(str(path))
    assert window.snapshots.capture() == before


def test_snapshot_limits_and_failed_save_preserve_existing_file(
    window: DashboardWindow, tmp_path: Path
) -> None:
    path = tmp_path / "gui.json"
    assert window.config_files.save_path(str(path))
    original = path.read_bytes()
    window.config_files.limit = 8
    assert not window.config_files.load_path(str(path))
    assert not window.config_files.save_path(str(path))
    assert path.read_bytes() == original


@pytest.mark.parametrize("save", [False, True])
@pytest.mark.parametrize("process_events", [False, True])
def test_native_file_picker_immediate_cancel_and_parent_cleanup(
    app: QApplication, save: bool, process_events: bool
) -> None:
    from PyQt6.QtCore import QTimer

    from cephvr.gui.file_dialogs import file_dialog, open_file_dialog

    for _ in range(10):
        parent = QWidget()
        parent.show()
        app.processEvents()
        dialog = file_dialog(parent, "Select file")
        assert not dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.setAcceptMode(
            QFileDialog.AcceptMode.AcceptSave
            if save
            else QFileDialog.AcceptMode.AcceptOpen
        )
        finished: list[int] = []
        dialog.finished.connect(finished.append)
        open_file_dialog(dialog)
        if process_events:
            native: list[bool] = []

            def cancel_visible(
                selected: QFileDialog = dialog, seen: list[bool] = native
            ) -> None:
                seen.append(
                    selected.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
                )
                selected.reject()

            cancel = QTimer(dialog)
            cancel.setSingleShot(True)
            cancel.timeout.connect(cancel_visible)
            cancel.start(50)
            app.processEvents()
            if app.platformName() == "windows":
                assert native == [True], "Windows picker fell back to Qt widgets"
        else:
            dialog.reject()
        # Native rejection can also report the shell's closing result.
        assert finished and set(finished) == {0}
        dialog.deleteLater()
        parent.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("save", [False, True])
def test_started_config_chooser_closes_on_authority_loss(
    app: QApplication, save: bool
) -> None:
    from PyQt6.QtCore import QTimer

    from cephvr.gui.configuration_files import ConfigurationFiles

    parent = QWidget()
    parent.show()
    app.processEvents()
    allowed = True
    files = ConfigurationFiles(
        parent,
        "Native authority probe",
        "probe.json",
        capture=lambda: {},
        validate=lambda value: value,
        apply=lambda value: pytest.fail("Canceled chooser applied configuration"),
        available=lambda: allowed,
    )
    files.choose(save=save)
    dialog = files.dialog
    assert dialog is not None
    observed: list[bool] = []

    def lose_authority() -> None:
        nonlocal allowed
        observed.append(dialog.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))
        allowed = False
        files.set_enabled(False)

    cancel = QTimer(parent)
    cancel.setSingleShot(True)
    cancel.timeout.connect(lose_authority)
    cancel.start(50)
    app.processEvents()
    assert files.dialog is None
    if app.platformName() == "windows":
        assert observed == [True]
    parent.deleteLater()
    app.processEvents()


@pytest.mark.parametrize(
    "owner", ["protocol", "tracking", "cameras", "microcontroller", "spikeglx", "gui"]
)
@pytest.mark.parametrize("save", [False, True], ids=["load", "save"])
def test_config_chooser_closes_on_authority_loss_and_rechecks_load(
    window: DashboardWindow, tmp_path: Path, owner: str, save: bool
) -> None:
    files = (
        window.config_files
        if owner == "gui"
        else getattr(
            window if owner in ("protocol", "tracking") else window.devices, owner
        ).config_files
    )
    path = tmp_path / f"{owner}.json"
    assert files.save_path(str(path))
    saved_bytes = path.read_bytes()
    files.choose(save=save)
    assert files.dialog is not None
    original_dialog = files.dialog
    window.apply_view(review_view(Phase.CONFIGURATION, observer=True))
    assert files.dialog is None
    assert not files.load_button.isEnabled()
    assert not files.load_path(str(path))
    window.apply_view(review_view(Phase.CONFIGURATION))
    window.dashboard.subject_id.setText("newer draft")
    window.protocol.assets.folders["root"].editor.setText("newer-assets")
    window.tracking.forms.distance_calibration.distance.setText("24")
    window.devices.microcontroller.trial_pin.setText("D12")
    from PyQt6.QtWidgets import QLineEdit

    channel = next(iter(window.devices.spikeglx.rows.values()))[3]
    assert isinstance(channel, QLineEdit)
    channel.setText("999")
    before = window.snapshots.capture()
    original_dialog.fileSelected.emit(str(path))
    assert window.snapshots.capture() == before
    assert path.read_bytes() == saved_bytes


def test_full_gui_loaded_drafts_join_one_proposal_and_survive_polling(
    window: DashboardWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.configuration_files import write_snapshot
    from cephvr.gui.managed_cameras import ManagedCameras
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )
    from cephvr.gui.managed_mcu import ManagedMcu

    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.configuration.revision = state.configuration_values.revision = 5
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    base = state.configuration_values.current
    base.mode = pb.SESSION_MODE_OPEN_LOOP
    acquisition = base.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    for draft, selected in zip(
        window.devices.cameras.drafts,
        (acquisition.behavioral, acquisition.tracking),
        strict=True,
    ):
        selected.device.device_id = draft.serial
        selected.enabled = False
    desired = window.snapshots.capture()
    desired["protocol"]["mode"] = "Open-loop"
    for camera in desired["experiment"]["cameras"]:
        camera["enabled"] = False
        camera["values"] = {
            "trigger_clock": "Internal clock",
            "trigger_frequency_hz": "18",
        }
    desired["microcontroller"]["port"] = "COM93"
    desired["microcontroller"]["trial_state"]["pin"] = "D7"
    desired["microcontroller"]["review_outputs"]["selected"] = ["trial-state"]
    desired["tracking"]["distance_mm"] = (
        ""  # Dormant, uncalibrated Tracking is a valid saved draft.
    )
    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
            window.devices.microcontroller,
        )
    )
    assert manager.install(state)
    camera_owner = ManagedCameras(
        window.devices.cameras,
        SimpleNamespace(request=lambda *_a, **_kw: False),
        lambda *_: False,
    )
    mcu_owner = ManagedMcu(
        window.devices.microcontroller,
        SimpleNamespace(request=lambda *_a, **_kw: False),
        lambda: state,
    )
    camera_owner.install(state)
    mcu_owner.install(state, True)
    path = tmp_path / "full.json"
    write_snapshot(str(path), desired)
    assert window.config_files.load_path(str(path))
    camera_owner.install(state)
    mcu_owner.install(state, True)
    assert window.snapshots.capture() == desired
    assert manager.dirty and manager.tracking_dirty
    monkeypatch.setattr(
        window.devices.projectors, "configuration_for_submit", lambda current: current
    )
    proposal = manager.collect(base)
    updated = next(
        entry.acquisition
        for entry in proposal.backends
        if entry.backend_name == "acquisition"
    )
    assert updated.pulses.port == "COM93"
    assert updated.pulses.trial_state_pin == "D7"
    assert updated.pulses.behavioral.requested_frequency_hz == 18
    assert not next(
        entry for entry in proposal.backends if entry.backend_name == "tracking"
    ).enabled
    state.configuration_values.current.CopyFrom(proposal)
    state.configuration.revision = state.configuration_values.revision = 6
    manager.note_installed_revision(state, submitted_edit_serial=manager.edit_serial)
    assert not window.devices.cameras.snapshot_draft
    assert not window.devices.microcontroller.snapshots.draft_loaded
    assert window.tracking.snapshot_draft
    # Enabling Tracking must validate the retained loaded settings, never submit an old baseline.
    window.recordings.velocities.setChecked(True)
    with pytest.raises(ValueError):
        manager.collect(proposal)
    # Explicit device reload restores accepted roles/pins before dependent Tracking installs.
    window.devices.cameras.drafts[0].role = "Tracking cam"
    window.devices.cameras.drafts[1].role = "Behavior cam"
    window.devices.cameras.snapshot_draft = True
    window.devices.microcontroller.trial_pin.setText("D12")
    window.devices.microcontroller.snapshots.draft_loaded = True
    camera_owner.discard_snapshot_draft(state)
    mcu_owner.discard_snapshot_draft(state, True)
    assert window.devices.cameras.drafts[0].role == "Behavior cam"
    assert window.tracking.source_serial == window.devices.cameras.drafts[1].serial
    assert window.devices.microcontroller.trial_pin.text() == "7"


def test_loaded_camera_presets_cannot_claim_sdk_import_provenance(
    window: DashboardWindow,
) -> None:
    from cephvr.acquisition.v1 import camera_pb2 as camera_pb
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.camera_snapshot_settings import collect_camera_snapshot

    panel = window.devices.cameras
    panel.snapshot_draft = True
    first, second = panel.drafts
    first.enabled = second.enabled = False
    first.values = {
        "preset": "changed.pfs",
        "pfs_imported": "yes",
        "trigger_clock": "Internal clock",
    }
    settings = pb.AcquisitionSettings()
    settings.behavioral.device.device_id = first.serial
    settings.behavioral.device.pfs_source_filename = "accepted.pfs"
    settings.behavioral.device.pfs_baseline.text = "sdk-baseline"
    settings.tracking.device.device_id = second.serial
    with pytest.raises(ValueError, match="import the loaded PFS"):
        collect_camera_snapshot(panel, settings)
    # Changing GUI roles retains the accepted baseline with the serial, rather than borrowing another camera's preset.
    first.role, second.role = "Tracking cam", "Behavior cam"
    first.values["preset"] = "accepted.pfs"
    collect_camera_snapshot(panel, settings)
    assert settings.tracking.device.device_id == first.serial
    assert settings.tracking.device.pfs_baseline.text == "sdk-baseline"
    assert settings.tracking.device.frame_timing == camera_pb.FRAME_TIMING_FREE_RUNNING


@pytest.mark.parametrize("clock", ["Internal clock", "External controller"])
def test_loaded_camera_timing_keeps_only_applicable_activation(
    window: DashboardWindow, clock: str
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.camera_snapshot_settings import collect_camera_snapshot

    panel = window.devices.cameras
    panel.snapshot_draft = True
    first, second = panel.drafts
    first.enabled = second.enabled = False
    first.values = {"trigger_clock": clock, "trigger_source": "Line3"}
    settings = pb.AcquisitionSettings()
    settings.behavioral.device.device_id = first.serial
    settings.behavioral.device.settings.trigger_activation = "falling_edge"
    collect_camera_snapshot(panel, settings)
    actual = settings.behavioral.device.settings
    assert actual.HasField("trigger_activation") == (clock == "External controller")
    if clock == "External controller":
        assert actual.trigger_activation == "falling_edge"


@pytest.mark.asyncio
@pytest.mark.parametrize("clock", ["Internal clock", "External controller"])
async def test_camera_settings_timing_keeps_only_applicable_activation(
    clock: str,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_device_commands import _save_camera_settings

    state = pb.Snapshot()
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    settings.eye_tracking.device.device_id = "eye"
    settings.eye_tracking.device.settings.trigger_activation = "falling_edge"
    requests = []

    async def execute(method, request):
        requests.append(request)
        return SimpleNamespace(succeeded=True)

    await _save_camera_settings(
        SimpleNamespace(snapshot=state, execute=execute, operator_command=lambda: None),
        {"serial": "eye", "clock": clock, "source": "Line3", "preset": "", "rate": ""},
    )
    actual = requests[0].proposed.backends[0].acquisition.eye_tracking.device.settings
    assert actual.HasField("trigger_activation") == (clock == "External controller")
    if clock == "External controller":
        assert actual.trigger_activation == "falling_edge"


def test_cross_camera_snapshot_error_focuses_tracking_field_and_keeps_proposal_atomic(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    panel = window.devices.cameras
    behavior, tracking = panel.drafts
    behavior.enabled = True
    behavior.values = {"trigger_clock": "Internal clock"}
    tracking.enabled = True
    tracking.values = {"trigger_clock": "External controller"}
    panel.snapshot_draft = True
    panel.table.setFocus()
    window.protocol.session_mode.setCurrentText("Open-loop")
    window.devices.projectors.configuration_for_submit = lambda display: display

    base = pb.ExperimentConfiguration()
    acquisition = base.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    acquisition.behavioral.device.device_id = behavior.serial
    acquisition.tracking.device.device_id = tracking.serial
    before = base.SerializeToString(deterministic=True)
    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            panel,
            window.devices.projectors,
            window.tracking,
        )
    )

    with pytest.raises(ValueError, match="Tracking cam · Parameter file"):
        manager.collect(base)
    assert base.SerializeToString(deterministic=True) == before
    assert panel.table.currentRow() == 1
    assert panel.focusWidget() is panel.preset

    tracking.values["trigger_source"] = "Line2"
    proposal = manager.collect(base)
    assert (
        proposal.backends[0].acquisition.tracking.device.settings.trigger_source
        == "Line2"
    )
    assert base.SerializeToString(deterministic=True) == before


def test_camera_save_validation_error_routes_to_other_camera_row(
    window: DashboardWindow,
) -> None:
    from cephvr.acquisition.config.validation import validate_configuration
    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_cameras import ManagedCameras

    panel = window.devices.cameras
    panel.drafts[0].role = "Behavior cam"
    panel.drafts[1].role = "Tracking cam"
    behavior, tracking = panel.drafts
    behavior_before = behavior.values.copy()
    candidate = pb.ExperimentConfiguration()
    acquisition = candidate.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    acquisition.behavioral.enabled = True
    acquisition.behavioral.device.device_id = behavior.serial
    acquisition.behavioral.device.frame_timing = camera_pb2.FRAME_TIMING_FREE_RUNNING
    acquisition.behavioral.device.unaligned_free_running = True
    acquisition.tracking.enabled = True
    acquisition.tracking.device.device_id = tracking.serial
    validation = validate_configuration(candidate)
    issue = next(item for item in validation.issues if "tracking." in item.field_path)
    message = (
        f"configuration validation failed: {issue.field_path}: {issue.failure.message}"
    )
    cameras = ManagedCameras(panel, SimpleNamespace(), lambda *_: False)
    cameras.pending = "save_camera_settings"
    cameras.finished("save_camera_settings", False, message)

    assert panel.table.currentRow() == 1
    assert panel.focusWidget() is panel.trigger_source
    assert behavior.values == behavior_before

    panel.drafts[1].values["trigger_clock"] = "Internal clock"
    acquisition.tracking.device.frame_timing = camera_pb2.FRAME_TIMING_FREE_RUNNING
    acquisition.tracking.device.unaligned_free_running = True
    corrected = validate_configuration(candidate)
    assert corrected.valid
    cameras.pending = "save_camera_settings"
    cameras.finished("save_camera_settings", True, "Completed")
    assert message in panel.console.toPlainText()
    assert "save_camera_settings: Completed" not in panel.console.toPlainText()


def test_authoritative_camera_projection_invalidates_spatial_draft_without_user_edit(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_cameras import ManagedCameras
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.configuration.revision = state.configuration_values.revision = 1
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    settings.behavioral.device.device_id = window.devices.cameras.drafts[1].serial
    settings.tracking.device.device_id = window.devices.cameras.drafts[0].serial
    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
        )
    )
    window.tracking.forms.distance_calibration.distance.setText("24")
    assert manager.install(state)
    camera_owner = ManagedCameras(
        window.devices.cameras,
        SimpleNamespace(request=lambda *_a, **_kw: False),
        lambda *_: False,
    )
    with manager.installing_projection():
        camera_owner.install(state)
    assert window.tracking.source_serial == settings.tracking.device.device_id
    assert window.tracking.forms.distance_calibration.distance.text() == ""
    assert not manager.dirty and not manager.tracking_dirty
    window.tracking.forms.distance_calibration.distance.setText("25")
    assert manager.dirty and manager.tracking_dirty


@pytest.mark.parametrize(
    "lock", ["camera", "camera_pending", "mcu", "tracking", "projector"]
)
def test_full_gui_snapshot_cannot_load_during_device_work(
    window: DashboardWindow, tmp_path: Path, lock: str
) -> None:
    path = tmp_path / "full.json"
    assert window.config_files.save_path(str(path))
    if lock == "camera":
        window.devices.cameras.drafts[0].connected = True
    elif lock == "camera_pending":
        window.devices.cameras.operation_pending = True
    elif lock == "mcu":
        window.devices.microcontroller.upload_pending = True
    elif lock == "tracking":
        window.tracking._diagnostic_locked = True
    else:
        window.devices.projectors.calibration.presentation_active = True
    assert not window.config_files.load_path(str(path))


def test_managed_subject_metadata_preserves_absence_and_numeric_zero(
    app: QApplication,
) -> None:
    from cephvr.gui.managed_config import subject_metadata_from_fields

    dashboard = DashboardWindow().dashboard
    dashboard.subject_id.setText("S-1")
    dashboard.age.setText("0")
    dashboard.subject_size.setText("12.5")
    draft = subject_metadata_from_fields(dashboard)
    assert draft.HasField("age_dph") and draft.age_dph == 0
    assert draft.HasField("size_mm") and draft.size_mm == 12.5
    assert not draft.HasField("sex")
    assert not draft.HasField("species")
    dashboard.window().close()
    dashboard.window().deleteLater()
    app.processEvents()


def test_managed_subject_metadata_preserves_unknown_sex_value(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb
    from cephvr.gui.managed_config import install_subject_metadata

    dashboard = DashboardWindow(sample=False).dashboard
    config = control_pb.ExperimentConfiguration()
    config.subject_metadata.sex = "Intersex"
    install_subject_metadata(dashboard, config)
    assert dashboard.sex.currentText() == "Intersex"
    assert "Intersex" in [
        dashboard.sex.itemText(index) for index in range(dashboard.sex.count())
    ]
    assert dashboard.sex.currentText()
    dashboard.window().close()
    dashboard.window().deleteLater()
    app.processEvents()


def test_managed_runtime_editors_are_enabled_without_review_samples(
    app: QApplication,
) -> None:
    from cephvr.gui.managed_window import ManagedDashboardWindow

    managed = ManagedDashboardWindow(sample=False)
    view = DashboardView(
        phase=Phase.CONFIGURATION,
        connected=True,
        has_control=True,
        configuration_wired=True,
    )
    assert view.can_edit
    managed.apply_view(view)
    assert managed.protocol.can_edit
    assert managed.protocol.editor.isEnabled()
    assert managed.recordings.velocities.isEnabled()
    assert managed.tracking.can_edit
    assert managed.tracking.pipeline.isEnabled()
    assert managed.protocol.assets.folders["root"].isEnabled()
    assert managed.devices.projectors.can_review
    assert managed.devices.projectors.calibration.isEnabled()
    assert managed.devices.spikeglx.can_review
    assert managed.devices.spikeglx.pairing.isEnabled()
    assert managed.devices.spikeglx.address.isReadOnly()
    assert managed.devices.spikeglx.command_port.isReadOnly()
    managed.close()
    managed.deleteLater()
    app.processEvents()


def test_dashboard_control_status_matches_connection_and_authority(
    app: QApplication,
) -> None:
    dashboard = DashboardWindow(sample=False).dashboard
    cases = (
        (DashboardView(connected=True, has_control=True), True),
        (DashboardView(connected=True, has_control=False), False),
        (DashboardView(connected=False, has_control=False), False),
        (DashboardView(sample=True, has_control=True), True),
        (DashboardView(sample=True, has_control=False), False),
    )
    for view, expected in cases:
        dashboard.apply_view(view)
        assert "Configuration" in dashboard.runtime_console.toPlainText()
        assert "CONTROL" not in dashboard.runtime_console.toPlainText()
        assert dashboard.command_buttons["Start"].isEnabled() == expected
        assert dashboard.subject_id.isEnabled() == expected
    dashboard.window().close()
    dashboard.window().deleteLater()
    app.processEvents()


def test_shared_theme_styles_menu_bar_and_menu_states(app: QApplication) -> None:
    from cephvr.gui.theme import COLORS, stylesheet

    current = stylesheet()
    assert f"QMenuBar {{ background: {COLORS.sidebar}; color: {COLORS.text};" in current
    assert "QMenuBar::item:selected" in current
    assert "QMenuBar::item:disabled" in current
    assert f"QMenu {{ background: {COLORS.card}; color: {COLORS.text};" in current
    assert "QMenu::item:selected" in current
    assert "QMenu::item:disabled" in current


def test_managed_configuration_creates_first_run_backends_and_installs_partial_tracking(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb
    from cephvr.gui.camera_inventory import CameraDraft
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )
    from cephvr.gui.managed_window import ManagedDashboardWindow

    managed = ManagedDashboardWindow(sample=False)
    managed.apply_view(
        DashboardView(
            phase=Phase.CONFIGURATION,
            connected=True,
            has_control=True,
            configuration_wired=True,
        )
    )
    camera = CameraDraft("tracking-1", "Tracking cam", "SERIAL-1", "Basler")
    managed.devices.cameras.drafts = [camera]
    managed.devices.cameras.populate_inventory()
    managed.devices.cameras.drafts_changed.emit()
    generation = str(uuid4())
    state = control_pb.Snapshot(controller_generation=generation)
    state.session.phase = control_pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 1
    state.configuration_values.revision = 1
    state.configuration_values.current.mode = control_pb.SESSION_MODE_CLOSED_LOOP
    backend = state.configuration_values.current.backends.add(backend_name="tracking")
    backend.tracking.SetInParent()
    manager = ManagedConfiguration(
        ConfigurationPages(
            managed.dashboard,
            managed.protocol,
            managed.recordings,
            managed.devices.cameras,
            managed.devices.projectors,
            managed.tracking,
        )
    )
    assert manager.install(state)
    assert manager.revision == 1
    assert managed.tracking.source_serial == "SERIAL-1"
    assert managed.protocol.editor.subgroup.composer.closed_loop
    managed.tracking.forms.preprocessing.scale.setValue(95)
    assert manager.dirty and manager.tracking_dirty
    manager.dirty = False
    manager.tracking_dirty = False
    managed.tracking.annotation.changed.emit()
    assert manager.dirty and manager.tracking_dirty
    manager.dirty = False
    manager.tracking_dirty = False
    managed.protocol.editor.add_button.click()
    from tests.visual_stimulus.support import valid_display_json

    with pytest.raises(ValueError, match="Load a projector configuration"):
        manager.collect(state.configuration_values.current)
    complete_base = control_pb.ExperimentConfiguration()
    complete_base.CopyFrom(state.configuration_values.current)
    visual_backend = complete_base.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    visual_backend.visual_stimulus.display.profile_json = valid_display_json()
    managed.devices.projectors.timing.mode.setCurrentText("VSync on pulse display")
    candidate = manager.collect(complete_base)
    by_name = {item.backend_name: item for item in candidate.backends}
    assert by_name["visual_stimulus"].enabled
    assert by_name["visual_stimulus"].HasField("visual_stimulus")
    assert by_name["tracking"].enabled
    assert by_name["tracking"].HasField("tracking")
    from cephvr.acquisition.v1 import camera_pb2

    assert (
        by_name["tracking"].tracking.input_camera_role
        == camera_pb2.CAMERA_ROLE_TRACKING
    )
    import json

    assert (
        json.loads(by_name["visual_stimulus"].visual_stimulus.display.profile_json)[
            "presentation_mode"
        ]
        == "photodiode_only_vsync"
    )
    managed.protocol.session_mode.setCurrentText("Open-loop")
    open_loop = manager.collect(complete_base)
    open_tracking = next(
        item for item in open_loop.backends if item.backend_name == "tracking"
    )
    assert not open_tracking.enabled
    assert not open_tracking.tracking.HasField("input_camera_role")
    assert not open_tracking.tracking.stages
    managed.recordings.velocities.click()
    recording_candidate = manager.collect(complete_base)
    recording_tracking = next(
        item for item in recording_candidate.backends if item.backend_name == "tracking"
    )
    assert recording_tracking.enabled
    assert recording_tracking.tracking.save_tracking_data
    managed.close()
    managed.deleteLater()
    app.processEvents()


def test_managed_status_uses_readiness_and_output_closure_evidence() -> None:
    from cephvr.control.v1 import types_pb2 as pb

    state = pb.Snapshot()
    state.configuration.revision = 7
    state.session.phase = pb.SESSION_PHASE_READY
    participant = state.participants.add()
    participant.process.role = "tracking"
    participant.connected = True
    participant.health = "Connected"
    participant.ready.configuration_revision = 6
    participant.ready.required_checks_passed = True
    participant.outputs.add(closure=pb.OUTPUT_CLOSURE_CLOSED)
    state.reservation.ready_for_outputs = True
    view = dashboard_view(state, "gui-1", ())
    assert view.tracking_status == "Connected"
    assert view.output_status == "Last reported outputs closed"
    assert view.reservation_status == "Reserved"
    participant.process_running = True
    participant.ready.configuration_revision = 7
    assert dashboard_view(state, "gui-1", ()).tracking_status == "Ready"

    assert view.trial_duration_s is None
    assert view.total_elapsed_s is None and view.total_duration_s is None
    state.trial.start_monotonic_ns = 10_000_000_000
    state.trial.scheduled_end_monotonic_ns = 160_000_000_000
    state.trial.actual_end_monotonic_ns = 58_000_000_000
    timed = dashboard_view(state, "gui-1", ())
    assert timed.elapsed_s == 48
    assert timed.trial_duration_s == 150
    assert timed.total_elapsed_s is None and timed.total_duration_s is None


def test_managed_total_time_tracks_trials_gaps_and_stops(window) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_status import session_timeline
    from cephvr.gui.protocol_document import blank_program

    state = pb.Snapshot()
    config = state.configuration_values.current
    for number in (1, 2):
        trial = config.trials.add(trial_number=number)
        trial.stimulus.program.program_json = blank_program().model_dump_json()
    config.gaps.add(after_trial_number=1, minimum_duration_ns=10_000_000_000)
    _, total = session_timeline(state, None, 0)
    assert total is not None
    trial_duration = (total - 10) / 2
    assert session_timeline(state, None, 0) == (0, total)
    state.trial.context.trial_number = 1
    assert session_timeline(state, 12, 0) == (12, total)
    state.trial.gap_earliest_end_monotonic_ns = 110_000_000_000
    assert session_timeline(state, trial_duration, 104_000_000_000) == (
        trial_duration + 4,
        total,
    )
    state.session.phase = pb.SESSION_PHASE_ENDED
    assert session_timeline(state, trial_duration, 200_000_000_000) == (None, total)
    state.trial.interruption_issued_monotonic_ns = 104_000_000_000
    assert session_timeline(state, trial_duration, 200_000_000_000) == (
        trial_duration + 4,
        total,
    )
    state.trial.ClearField("interruption_issued_monotonic_ns")
    state.trial.ClearField("gap_earliest_end_monotonic_ns")
    state.trial.context.trial_number = 2
    state.trial.start_monotonic_ns = 200_000_000_000
    state.trial.actual_end_monotonic_ns = 212_000_000_000
    state.session.phase = pb.SESSION_PHASE_ENDED
    view = dashboard_view(state, "", ())
    assert view.total_elapsed_s == trial_duration + 10 + 12
    assert view.total_duration_s == total
    window.apply_view(view)
    preview_text = window.dashboard.preview_workspace.hud.toPlainText()
    # The preview HUD repeats every Dashboard row except OUTPUT, in aligned columns.
    for row in window.dashboard.status_column.rows:
        if row is not None and row[0] != "OUTPUT DIR":
            assert row[0] in preview_text and row[1] in preview_text
    lines = preview_text.splitlines()
    assert len(lines) == 2
    assert lines[0].index("TRIAL ") == lines[1].index("TOTAL TIME")
    config.trials[0].stimulus.program.program_json = "{}"
    assert session_timeline(state, 12, 0) == (None, None)


def test_retained_summary_keeps_incidents_ahead_of_completed_operation_history() -> (
    None
):
    from cephvr.control.v1 import types_pb2 as pb

    state = pb.Snapshot()
    for index in range(45):
        operation = state.operations.add(command="Setup", complete=True, succeeded=True)
        operation.context.command_id = f"id-{index}"
    state.errors.add(
        error_id="retained-error",
        failure=pb.Failure(message="camera cleanup failed"),
    )
    state.warnings.add(message="output recovery needs review")
    rendered = retained_summary(state)
    assert "retained-error" not in rendered
    assert "camera cleanup failed" in rendered
    assert "output recovery needs review" in rendered
    assert "Completed operations: 45" in rendered
    assert "id-0" not in rendered
    assert "retained-error" in retained_details(state)
    assert has_retained_review(state)
    assert retained_ack_required_for(state, (3, "controller-1"), None)
    assert not retained_ack_required_for(
        state, (3, "controller-1"), (3, "controller-1")
    )


def test_auto_retained_review_filters_only_exact_routine_warnings() -> None:
    from cephvr.control.v1 import types_pb2 as pb

    state = pb.Snapshot()
    state.configuration.revision = 8
    validation = state.configuration.edit_validation.add(
        configuration_revision=8,
        completed=True,
        valid=True,
        component="visual_stimulus",
    )
    validation.issues.add(
        component="visual_stimulus",
        field_path="stimulus.program",
        failure=pb.Failure(message="Optional preview unavailable"),
    )
    routine = state.warnings.add(
        warning_id="configuration:8:visual_stimulus:nonfatal",
        component="visual_stimulus",
        message="Configuration has nonfatal preparation warnings",
    )
    routine.issues.extend(validation.issues)
    assert not has_retained_review(state)
    assert has_retained_history(state)

    # A warning has no severity field; unknown evidence stays important.
    state.warnings.add(message="Optional preview unavailable")
    assert has_retained_review(state)

    state.ClearField("warnings")
    stale = state.warnings.add(
        warning_id="configuration:7:visual_stimulus:nonfatal",
        component="visual_stimulus",
        message="Configuration has nonfatal preparation warnings",
    )
    stale.issues.extend(validation.issues)
    assert has_retained_review(state)

    # Any differing field or issue prevents suppression of a familiar warning.
    for mutation in ("message", "issues", "reverted_fields", "acquisition_occurrence"):
        candidate = pb.Snapshot()
        candidate.configuration.CopyFrom(state.configuration)
        item = candidate.warnings.add()
        item.CopyFrom(routine)
        if mutation == "message":
            item.message = "Configuration may need review"
        elif mutation == "issues":
            item.issues[0].failure.message = "Different issue"
        elif mutation == "reverted_fields":
            item.reverted_fields.append("camera.exposure")
        else:
            item.acquisition_occurrence.SetInParent()
        assert has_retained_review(candidate)

    for completed, valid in ((False, True), (True, False)):
        candidate = pb.Snapshot()
        candidate.configuration.revision = 8
        validation = candidate.configuration.edit_validation.add(
            configuration_revision=8,
            completed=completed,
            valid=valid,
            component="visual_stimulus",
        )
        validation.issues.add().CopyFrom(
            state.configuration.edit_validation[0].issues[0]
        )
        item = candidate.warnings.add()
        item.CopyFrom(routine)
        assert has_retained_review(candidate)


def test_auto_retained_review_operation_and_recovery_truth_table() -> None:
    from cephvr.control.v1 import types_pb2 as pb

    pending = pb.Snapshot()
    pending.operations.add(command="Setup", complete=False, progress="Preparing")
    assert not has_retained_review(pending)
    assert has_retained_history(pending)

    unknown_operation = pb.Snapshot()
    unknown_operation.operations.add(command="Setup", complete=True)
    assert has_retained_review(unknown_operation)

    failed_operation = pb.Snapshot()
    failed_operation.operations.add(command="Setup", complete=True, succeeded=False)
    assert has_retained_review(failed_operation)

    successful_recovery = pb.Snapshot()
    successful_recovery.recoveries.add(
        attempt_id="done",
        outcome=pb.RECOVERY_OUTCOME_COMPLETED,
        completion_monotonic_ns=123,
    )
    assert not has_retained_review(successful_recovery)

    missing_completion = pb.Snapshot()
    missing_completion.recoveries.add(
        attempt_id="missing-completion",
        outcome=pb.RECOVERY_OUTCOME_COMPLETED,
    )
    assert has_retained_review(missing_completion)

    for outcome, failure in (
        (pb.RECOVERY_OUTCOME_UNSPECIFIED, False),
        (pb.RECOVERY_OUTCOME_FAILED, True),
        (pb.RECOVERY_OUTCOME_COMPLETED, True),
    ):
        state = pb.Snapshot()
        recovery = state.recoveries.add(
            attempt_id="needs-review",
            outcome=outcome,
            completion_monotonic_ns=123,
        )
        if failure:
            recovery.failure.message = "Cleanup status is inconsistent"
        assert has_retained_review(state)


def test_retained_ack_guard_reassesses_fresh_snapshot_but_preserves_same_identity() -> (
    None
):
    from cephvr.control.v1 import types_pb2 as pb

    important = pb.Snapshot()
    important.errors.add(error_id="startup-cleanup")
    identity = (1, "controller-1")
    assert retained_ack_required_for(important, identity, None)
    assert not retained_ack_required_for(pb.Snapshot(), (2, "controller-1"), None)
    assert not retained_ack_required_for(important, identity, identity)


def test_manual_history_review_opens_without_ack_guard(app: QApplication) -> None:
    from PyQt6.QtWidgets import QWidget

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    state = pb.Snapshot(controller_generation="controller-1")
    state.operations.add(command="Setup", complete=True, succeeded=True)
    manager = SimpleNamespace(
        state=state,
        _retained_ack_required=False,
        _retained_ack_identity=None,
        _connection_identity=(7, "controller-1"),
        _acknowledged_identity=None,
    )
    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, _choice: False,
        acknowledged=lambda epoch, generation: ManagedGui.retained_state_acknowledged(
            manager, epoch, generation
        ),
        log=lambda _message: None,
    )
    prompts.update(
        state,
        require_acknowledgement=False,
        can_respond=False,
        connection_epoch=7,
    )
    manager.prompts = prompts
    ManagedGui.review_retained_state(manager)
    app.processEvents()
    dialog = prompts.retained_dialog
    assert dialog is not None and dialog.isVisible()

    latest = pb.Snapshot(controller_generation="controller-1")
    operation = latest.operations.add(command="Setup", complete=True, succeeded=True)
    operation.context.command_id = "latest-command"
    manager.state = latest
    prompts.update(
        latest,
        require_acknowledgement=False,
        can_respond=False,
        connection_epoch=7,
    )
    assert prompts.retained_dialog is dialog
    dialog.copy_button.click()
    assert "latest-command" in QApplication.clipboard().text()
    dialog.continue_button.click()
    app.processEvents()
    assert not manager._retained_ack_required
    assert manager._acknowledged_identity is None
    parent.close()
    parent.deleteLater()


def test_mandatory_review_can_be_reopened_after_same_identity_history_empties(
    app: QApplication,
) -> None:
    from PyQt6.QtWidgets import QWidget

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    state = pb.Snapshot(controller_generation="controller-1")
    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, _choice: False,
        acknowledged=lambda _epoch, _generation: None,
        log=lambda _message: None,
    )
    prompts.update(
        state,
        require_acknowledgement=True,
        can_respond=False,
        connection_epoch=2,
    )
    assert prompts.retained_dialog is not None
    prompts.retained_dialog.reject()
    manager = SimpleNamespace(
        state=state,
        _retained_ack_required=True,
        prompts=prompts,
    )
    ManagedGui.review_retained_state(manager)
    app.processEvents()
    assert prompts.retained_dialog is not None
    assert prompts.retained_dialog.isVisible()
    prompts.retained_dialog.reject()
    parent.close()
    parent.deleteLater()


def test_managed_prompt_window_is_single_and_responds_with_displayed_snapshot(
    app: QApplication,
) -> None:
    from PyQt6.QtWidgets import QPushButton

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    responses: list[tuple[bytes, str]] = []

    def queue_response(encoded: bytes, choice: str) -> bool:
        responses.append((encoded, choice))
        return True

    prompts = ManagedPrompts(
        parent,
        queue_response=queue_response,
        acknowledged=lambda _epoch, _generation: None,
        log=lambda _message: None,
    )
    state = pb.Snapshot()
    prompt = state.prompts.add(
        prompt_id="prompt-1",
        explanation="Choose a response",
        permitted_choices=["continue_session", "abort_session"],
    )
    prompts.update(state, require_acknowledgement=False, can_respond=False)
    app.processEvents()
    dialog = prompts.prompt_dialog
    assert dialog is not None and dialog.isVisible()
    choices = dialog.findChildren(QPushButton)
    assert all(not item.isEnabled() for item in choices if item.text() != "Close")

    prompts.update(state, require_acknowledgement=False, can_respond=True)
    app.processEvents()
    assert prompts.prompt_dialog is dialog
    button = next(
        item
        for item in dialog.findChildren(QPushButton)
        if item.text() == "continue_session" and item.isVisible()
    )
    button.click()
    assert responses == [(prompt.SerializeToString(), "continue_session")]

    prompts.operation_finished("respond_prompt")
    prompt.runtime_incident.revision = 4
    prompts.update(state, require_acknowledgement=False, can_respond=True)
    app.processEvents()
    button = next(
        item
        for item in dialog.findChildren(QPushButton)
        if item.text() == "abort_session" and item.isVisible()
    )
    button.click()
    assert responses[-1] == (prompt.SerializeToString(), "abort_session")
    parent.close()
    parent.deleteLater()
    app.processEvents()


def test_prompt_completion_preserves_current_lease_authority(app: QApplication) -> None:
    from PyQt6.QtWidgets import QPushButton

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, _choice: True,
        acknowledged=lambda _epoch, _generation: None,
        log=lambda _message: None,
    )
    state = pb.Snapshot(controller_generation="controller-1")
    state.prompts.add(prompt_id="p1", permitted_choices=["continue"])
    prompts.update(state, require_acknowledgement=False, can_respond=True)
    prompts.update(state, require_acknowledgement=False, can_respond=False)
    prompts.queued_prompt_id = "p1"
    prompts.pending_prompt_ids.add("p1")
    prompts.operation_finished("respond_prompt")
    app.processEvents()
    assert prompts.prompt_dialog is not None
    choices = [
        item
        for item in prompts.prompt_dialog.findChildren(QPushButton)
        if item.text() == "continue" and item.isVisible()
    ]
    assert choices and all(not item.isEnabled() for item in choices)
    prompts.hide_prompt()
    prompts.operation_finished("respond_prompt")
    assert not prompts.prompt_dialog.isVisible()
    parent.close()
    parent.deleteLater()
    app.processEvents()


def test_managed_retained_summary_uses_one_acknowledgement_window(
    app: QApplication,
) -> None:
    from PyQt6.QtWidgets import QPushButton

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_prompts import ManagedPrompts
    from cephvr.gui.retained_review import RetainedReviewDialog

    parent = QWidget()
    acknowledgements: list[tuple[int, str]] = []

    def acknowledge(epoch: int, generation: str) -> None:
        acknowledgements.append((epoch, generation))

    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, _choice: False,
        acknowledged=acknowledge,
        log=lambda _message: None,
    )
    state = pb.Snapshot(retained_truncated=True, controller_generation="controller-1")
    state.errors.add(
        error_id="renderer-error",
        failure=pb.Failure(message="<unknown> cleanup <b>failed</b> & confirm"),
    )
    for index in range(45):
        item = state.operations.add(command="Setup", complete=True, succeeded=True)
        item.context.command_id = f"routine-{index}"
    prompts.update(
        state,
        require_acknowledgement=True,
        can_respond=False,
        connection_epoch=1,
    )
    app.processEvents()
    dialog = prompts.retained_dialog
    assert isinstance(dialog, RetainedReviewDialog) and dialog.isVisible()
    assert dialog.windowTitle() == "Controller events to review"
    assert "Retained errors:" in dialog.summary.text()
    assert (
        "&lt;unknown&gt; cleanup &lt;b&gt;failed&lt;/b&gt; &amp; confirm"
        in dialog.summary.text()
    )
    assert [button.text() for button in dialog.findChildren(QPushButton)] == [
        "Copy details",
        "Continue",
    ]
    latest = pb.Snapshot(controller_generation="controller-1")
    latest.errors.add(
        error_id="new-error",
        failure=pb.Failure(message="multiline\n<unknown> latest & <b>failure</b>"),
    )
    for index in range(45):
        item = latest.operations.add(command="Setup", complete=True, succeeded=True)
        item.context.command_id = f"routine-{index}"
    prompts.update(
        latest,
        require_acknowledgement=True,
        can_respond=False,
        connection_epoch=1,
    )
    assert prompts.retained_dialog is dialog
    assert "latest &amp; &lt;b&gt;failure&lt;/b&gt;" in dialog.summary.text()
    assert "cleanup failed" not in dialog.summary.text()
    dialog.copy_button.click()
    copied = QApplication.clipboard().text()
    assert "new-error" in copied
    assert "multiline\n<unknown> latest & <b>failure</b>" in copied
    assert "routine-44" in copied
    assert "cleanup failed" not in copied
    assert acknowledgements == []
    dialog.continue_button.click()
    app.processEvents()
    assert acknowledgements == [(1, "controller-1")]
    parent.close()
    parent.deleteLater()
    app.processEvents()


def test_old_retained_dialog_cannot_acknowledge_a_new_connection(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    acknowledgements: list[tuple[int, str]] = []
    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, _choice: False,
        acknowledged=lambda epoch, generation: acknowledgements.append(
            (epoch, generation)
        ),
        log=lambda _message: None,
    )
    first = pb.Snapshot(retained_truncated=True, controller_generation="controller-1")
    prompts.update(
        first,
        require_acknowledgement=True,
        can_respond=False,
        connection_epoch=4,
    )
    app.processEvents()
    old_dialog = prompts.retained_dialog
    assert old_dialog is not None
    prompts.invalidate_retained_summary()
    second = pb.Snapshot(retained_truncated=True, controller_generation="controller-1")
    prompts.update(
        second,
        require_acknowledgement=True,
        can_respond=False,
        connection_epoch=5,
    )
    app.processEvents()
    new_dialog = prompts.retained_dialog
    assert new_dialog is not None and new_dialog is not old_dialog
    old_dialog.continue_button.click()
    app.processEvents()
    assert acknowledgements == []
    new_dialog.continue_button.click()
    app.processEvents()
    assert acknowledgements == [(5, "controller-1")]
    parent.close()
    parent.deleteLater()
    app.processEvents()


def test_startup_recovery_buttons_are_explicit_and_close_is_not_a_choice(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    choices: list[str] = []
    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, choice: choices.append(choice) or True,
        acknowledged=lambda _epoch, _generation: None,
        log=lambda _message: None,
    )
    state = pb.Snapshot(controller_generation="controller-1")
    state.prompts.add(
        prompt_id="startup-recovery",
        explanation="Unfinished session: chosen path",
        permitted_choices=["recover", "delete"],
    )
    prompts.update(state, require_acknowledgement=False, can_respond=True)
    assert [button.text() for button in prompts.prompt_buttons] == [
        "Start recovery",
        "Cancel and delete files",
    ]
    assert all(not button.autoDefault() for button in prompts.prompt_buttons)
    assert prompts.prompt_dialog is not None
    prompts.prompt_dialog.reject()
    assert choices == []
    prompts.review_prompt(can_respond=True)
    prompts.prompt_buttons[1].click()
    assert choices == ["delete"]
    parent.close()
    parent.deleteLater()


def test_closing_retained_review_does_not_acknowledge(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    acknowledgements: list[tuple[int, str]] = []
    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, _choice: False,
        acknowledged=lambda epoch, generation: acknowledgements.append(
            (epoch, generation)
        ),
        log=lambda _message: None,
    )
    prompts.update(
        pb.Snapshot(controller_generation="controller-1"),
        require_acknowledgement=True,
        can_respond=False,
        connection_epoch=9,
    )
    app.processEvents()
    assert prompts.retained_dialog is not None
    prompts.retained_dialog.reject()
    app.processEvents()
    assert acknowledgements == []
    parent.close()
    parent.deleteLater()


def test_long_retained_review_scrolls_without_hiding_actions(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_prompts import ManagedPrompts

    parent = QWidget()
    prompts = ManagedPrompts(
        parent,
        queue_response=lambda _encoded, _choice: False,
        acknowledged=lambda _epoch, _generation: None,
        log=lambda _message: None,
    )
    state = pb.Snapshot(controller_generation="controller-1")
    for index in range(55):
        state.warnings.add(
            warning_id=f"warning-{index}",
            message=f"Warning {index}: " + "operator review required " * 4,
        )
    prompts.update(
        state,
        require_acknowledgement=True,
        can_respond=False,
        connection_epoch=10,
    )
    app.processEvents()
    dialog = prompts.retained_dialog
    assert dialog is not None
    assert dialog.width() <= 540
    assert dialog.height() <= 400
    scrollbar = dialog.summary_scroll.verticalScrollBar()
    assert scrollbar is not None and scrollbar.maximum() > 0
    assert dialog.copy_button.isVisible()
    assert dialog.continue_button.isVisible()
    dialog.reject()
    parent.close()
    parent.deleteLater()


def test_retained_summary_keeps_ids_in_details_and_all_actionable_operations_visible() -> (
    None
):
    from cephvr.control.v1 import types_pb2 as pb

    state = pb.Snapshot()
    operation = state.operations.add(command="Setup")
    operation.context.command_id = "cmd-123"
    operation.progress = "waiting for device readiness"
    for index in range(45):
        failed = state.operations.add(command="Setup", complete=True, succeeded=False)
        failed.context.command_id = f"failed-{index}"
        failed.failure.message = "<unknown> renderer cleanup failed"
    prompt = state.prompts.add(prompt_id="prompt-456", explanation="Continue?")
    prompt.permitted_choices.append("cancel")
    rendered = retained_summary(state)
    assert "cmd-123" not in rendered
    assert "waiting for device readiness" in rendered
    assert "prompt-456" not in rendered
    assert "failed-44" not in rendered
    assert "failed-44" in retained_details(state)
    assert "<unknown> renderer cleanup failed" in retained_summary(state)
    assert "<unknown> renderer cleanup failed" in retained_details(state)


def test_managed_bridge_reserves_safety_queue_capacity_and_drops_stale_epoch() -> None:
    import asyncio

    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    bridge = ControllerBridge(Principal("gui", "gui-1", "token"), 50051, 1024, (0,))
    bridge._queue = asyncio.PriorityQueue(maxsize=33)
    bridge._connection_epoch = 4
    bridge._controller_generation = "controller-1"
    bridge._pending_count = 2
    bridge._queue_request("ordinary", {}, 1, False, 4, "controller-1")
    bridge._queue_request("Abort now", {}, 2, True, 4, "controller-1")
    assert bridge._queue.get_nowait()[4] == "Abort now"
    assert ControllerBridge._is_safety_request("close_tracking_diagnostic", {})

    bridge._pending_count = 1
    bridge._queue_request("Start", {}, 3, False, 3, "controller-0")
    assert bridge._queue.qsize() == 1
    assert bridge._pending_count == 0

    class ImmediateLoop:
        @staticmethod
        def call_soon_threadsafe(callback: object, *args: object) -> None:
            callback(*args)  # type: ignore[operator]

    bridge._loop = ImmediateLoop()  # type: ignore[assignment]
    bridge._connected = True
    bridge._pending_count = bridge._ORDINARY_PENDING
    assert not bridge.request("Start")
    assert bridge.request("Abort now")
    for _ in range(bridge._MAX_PENDING - bridge._ORDINARY_PENDING - 1):
        assert bridge.request("Cancel Setup")
    assert bridge._pending_count == bridge._MAX_PENDING
    assert not bridge.request("respond_prompt", prompt=b"", choice="cancel")


@pytest.mark.asyncio
async def test_prompt_completion_wait_failure_retains_admitted_id_as_unconfirmed() -> (
    None
):
    from cephvr.client.session import ClientError
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    principal = Principal("gui", "gui-1", "token")
    bridge = ControllerBridge(principal, 50051, 1024, (0,))
    outcomes: list[tuple[str, str, str, str]] = []
    bridge.operation_finished.connect(
        lambda action, command_id, status, message: outcomes.append(
            (action, command_id, status, message)
        )
    )
    state = pb.Snapshot(controller_generation="controller-1")
    state.control.holder_client_id = principal.generation
    state.prompts.add(
        prompt_id="prompt-1",
        permitted_choices=["continue"],
    )
    command = rpc.OperatorCommand(
        operator=pb.OperatorContext(
            client_id=principal.generation,
            control_generation=state.control.control_generation,
            command_id="admitted-command",
        ),
        controller_generation=state.controller_generation,
    )

    class Client:
        snapshot = state

        @staticmethod
        def operator_command() -> rpc.OperatorCommand:
            return command

        @staticmethod
        async def _admit(
            _method: str, _request: rpc.PromptResponse
        ) -> pb.CommandAdmission:
            return pb.CommandAdmission(
                command_id="admitted-command",
                result=pb.COMMAND_RESULT_ACCEPTED,
            )

        @staticmethod
        async def wait_result(_command_id: str) -> object:
            raise ClientError("retained completion state is unavailable")

    client = Client()
    await bridge._dispatch(
        client,  # type: ignore[arg-type]
        "respond_prompt",
        {
            "prompt": state.prompts[0].SerializeToString(),
            "choice": "continue",
        },
    )
    assert outcomes == [
        (
            "respond_prompt",
            "admitted-command",
            "unconfirmed",
            "retained completion state is unavailable",
        )
    ]


@pytest.mark.parametrize("has_control", [False, True])
def test_managed_spikeglx_connection_emits_read_only_intent(
    app: QApplication, has_control: bool
) -> None:
    from cephvr.gui.spikeglx import SpikeGLXPanel

    panel = SpikeGLXPanel()
    requested: list[bool] = []
    panel.connection_requested.connect(lambda: requested.append(True))
    panel.apply_view(DashboardView(connected=True, has_control=has_control))
    assert panel.action_buttons[0].isEnabled()
    assert panel.address.isReadOnly()
    assert panel.command_port.isReadOnly()
    panel.action_buttons[0].click()
    assert requested == [True]
    assert "no hardware command sent" not in panel.console.toPlainText()
    for view in (DashboardView(), DashboardView(sample=True, has_control=True)):
        panel.apply_view(view)
        assert not panel.action_buttons[0].isEnabled()
        panel.request("Test connection")
        assert requested == [True]
    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_spikeglx_inventory_draft_roundtrips_supplemental_and_optional_bits(
    app: QApplication,
) -> None:
    from cephvr.gui.spikeglx import SpikeGLXPanel
    from cephvr.synchronization.v1 import spikeglx_pb2 as sync_pb

    panel = SpikeGLXPanel()
    panel.can_review = True
    panel.set_sources(
        (
            ("behavior-camera", "Behavioral camera", True),
            ("tracking-camera", "Tracking camera", True),
            ("eye-camera", "Eye tracking", True),
            ("photodiode", "Photodiode", True),
        ),
        frozenset({"behavior-camera", "tracking-camera", "eye-camera"}),
    )
    saved = (
        sync_pb.PulseChannel(
            role=sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA,
            family=sync_pb.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=1,
            bit=0,
        ),
        sync_pb.PulseChannel(
            role=sync_pb.PULSE_ROLE_TRACKING_CAMERA,
            family=sync_pb.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=2,
        ),
        sync_pb.PulseChannel(
            role=sync_pb.PULSE_ROLE_PHOTODIODE,
            family=sync_pb.STREAM_FAMILY_NI,
            stream_index=0,
            channel_index=3,
        ),
        sync_pb.PulseChannel(
            role=sync_pb.PULSE_ROLE_TRIAL_STATE,
            family=sync_pb.STREAM_FAMILY_NI,
            stream_index=0,
            channel_index=4,
        ),
        sync_pb.PulseChannel(
            role=sync_pb.PULSE_ROLE_CUSTOM,
            family=sync_pb.STREAM_FAMILY_NI,
            stream_index=0,
            channel_index=5,
            source_id="sync-input",
        ),
    )
    saved += (
        sync_pb.PulseChannel(
            role=sync_pb.PULSE_ROLE_EYE_TRACKING_CAMERA,
            family=sync_pb.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=1,
            bit=1,
        ),
    )
    panel.install_inventory(
        saved,
        "f" * 64,
        required_roles=frozenset(
            {
                sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA,
                sync_pb.PULSE_ROLE_TRACKING_CAMERA,
                sync_pb.PULSE_ROLE_EYE_TRACKING_CAMERA,
            }
        ),
    )
    assert not panel.enable_controls[
        panel.inventory_rows[sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA]
    ].isEnabled()
    collected = {item.role: item for item in panel.inventory_for_submit()}
    assert collected[sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA].HasField("bit")
    assert collected[sync_pb.PULSE_ROLE_BEHAVIORAL_CAMERA].bit == 0
    assert not collected[sync_pb.PULSE_ROLE_TRACKING_CAMERA].HasField("bit")
    assert collected[sync_pb.PULSE_ROLE_TRIAL_STATE].channel_index == 4
    assert collected[sync_pb.PULSE_ROLE_CUSTOM].source_id == "sync-input"
    assert collected[sync_pb.PULSE_ROLE_EYE_TRACKING_CAMERA].bit == 1
    assert panel.inventory_rows[sync_pb.PULSE_ROLE_EYE_TRACKING_CAMERA] == "eye-camera"
    assert panel.inventory_rows[sync_pb.PULSE_ROLE_TRACKING_CAMERA] == "tracking-camera"
    from cephvr.gui.spikeglx_snapshot import SpikeGLXSnapshot

    snapshot = SpikeGLXSnapshot(panel)
    snapshot.restore(snapshot.validate(snapshot.capture()))
    assert panel.inventory_rows[sync_pb.PULSE_ROLE_EYE_TRACKING_CAMERA] == "eye-camera"
    assert {item.role: item for item in panel.inventory_for_submit()} == collected
    panel.close()
    panel.deleteLater()
    app.processEvents()


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [True, False])
async def test_preview_window_waits_for_backend_completion(succeeded: bool) -> None:
    import asyncio

    from cephvr.client.session import ClientError, CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_device_commands import _camera

    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.acquisition_devices.behavioral.preview_run_id = str(uuid4())
    state.configuration.revision = 3
    submitted = asyncio.Event()
    confirmed = asyncio.Event()
    placement = rpc.PreviewWindowPlacement(x=-640, y=80, side=640)

    async def execute(method: str, request: rpc.CameraCommandRequest) -> CommandOutcome:
        assert method == "ExecuteCameraCommand"
        assert request.kind == rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
        assert (
            request.preview_run_id
            == state.acquisition_devices.behavioral.preview_run_id
        )
        assert request.expected_configuration_revision == 3
        assert not request.HasField("preview_consumer")
        assert request.preview_placement == placement
        submitted.set()
        await confirmed.wait()
        return CommandOutcome("command", True, succeeded, failure="window failed")

    client = SimpleNamespace(
        snapshot=state, operator_command=lambda: rpc.OperatorCommand(), execute=execute
    )
    task = asyncio.create_task(
        _camera(
            client,
            {
                "role": 1,
                "kind": rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW,
                "placement": placement.SerializeToString(),
            },
        )
    )
    try:
        await asyncio.wait_for(submitted.wait(), 1)
        assert not task.done()
        confirmed.set()
        if succeeded:
            await task
        else:
            with pytest.raises(ClientError, match="window failed"):
                await task
    finally:
        confirmed.set()
        await asyncio.gather(task, return_exceptions=True)


def test_managed_camera_controls_emit_intent_without_changing_local_device_state(
    app: QApplication,
) -> None:
    from cephvr.gui.cameras import CameraDraft, CamerasPanel

    panel = CamerasPanel()
    panel.managed = True
    panel.drafts = [CameraDraft("camera-1", "Behavior cam", "123", "Basler")]
    panel.populate_inventory()
    panel.table.selectRow(0)
    panel.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            previews=(
                PreviewView("camera-1", "Behavior cam", active=True, available=True),
            ),
        )
    )
    intents: list[tuple[str, bool]] = []
    panel.connection_requested.connect(lambda key, start: intents.append((key, start)))
    panel.connect_button.click()
    assert intents == [("camera-1", True)]
    assert not panel.drafts[0].connected
    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_devices_draft_icons_local_edits_and_command_gates(
    window: DashboardWindow, app: QApplication
) -> None:
    window.page_buttons[2].click()
    devices = window.devices
    assert window.stack.currentWidget() is devices
    assert [devices.tab_bar.tabText(i) for i in range(4)] == [
        "Cameras",
        "Microcontroller",
        "Projectors",
        "SpikeGLX",
    ]
    assert all(not devices.tab_bar.tabIcon(i).isNull() for i in range(4))
    camera = devices.cameras
    camera.fields["trigger_frequency_hz"].setText("1234")
    camera.edit("trigger_frequency_hz", "1234")
    for index, panel in enumerate(devices.panels[1:], start=1):
        devices.tabs.setCurrentIndex(index)
        app.processEvents()
        if panel is devices.spikeglx:
            assert not panel.action_buttons[0].isEnabled()
            continue
        if panel is devices.projectors:
            panel.refresh_button.click()
        else:
            panel.scan_button.click()
        assert "no hardware command sent" in panel.console.toPlainText()
    devices.tabs.setCurrentIndex(0)
    assert camera.fields["trigger_frequency_hz"].text() == "1234"
    for state in (
        review_view(Phase.RUNNING),
        review_view(Phase.CONFIGURATION, observer=True),
        DashboardView(),
    ):
        window.apply_view(state)
        for panel in devices.panels[1:]:
            before = panel.console.toPlainText()
            assert not any(control.isEnabled() for control in panel.action_buttons)
            if panel is devices.projectors:
                assert not panel.refresh_button.isEnabled()
            elif panel is devices.microcontroller:
                assert not panel.scan_button.isEnabled()
            panel.request("Test connection")
            assert panel.console.toPlainText() == before


@pytest.mark.parametrize("width", [720, 1175])
def test_devices_draft_reflows_without_horizontal_clipping(
    window: DashboardWindow, app: QApplication, width: int
) -> None:
    window.page_buttons[2].click()
    form = window.devices.cameras.trigger_form
    fields = form.fields
    for current_width in (width, 1920, width):
        window.resize(current_width, 883)
        for index in range(4):
            window.devices.tabs.setCurrentIndex(index)
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 1000)
            scroll = window.devices.panels[index].scrollers[0]
            assert scroll.horizontalScrollBar().maximum() == 0
            if index == 0:
                assert form.grid.count() == 3 and form.fields == fields
                assert all(form.rect().contains(item.geometry()) for item in fields)
                assert all(item.width() > 0 for item in fields)


def test_camera_trigger_form_reflows_and_destroys_owned_editors(app):
    from cephvr.gui.cameras import CamerasPanel

    destroyed = []
    for cycle in range(3):
        panel = CamerasPanel(sample=True)
        panel.destroyed.connect(lambda: destroyed.append(True))
        panel.apply_view(review_view(Phase.CONFIGURATION))
        panel.show()
        app.processEvents()
        form = panel.trigger_form
        fields = form.fields
        source, rate, pin = form.controls
        source.setFocus()
        QTest.keyClick(source, Qt.Key.Key_End)
        rate.setText("60")
        pin.setText("9")
        minimums = sorted(
            control.minimumSizeHint().width() for control in form.controls
        )
        narrow = (
            sum(minimums[-2:])
            + 2 * form.grid.horizontalSpacing()
            + panel.width()
            - form.width()
        )
        for width, stacked in (
            (narrow, True),
            (max(572, narrow * 2), False),
            (narrow, True),
        ):
            panel.resize(width, 883)
            app.processEvents()
            assert form.grid.count() == 3 and form.fields == fields
            assert all(form.rect().contains(item.geometry()) for item in fields)
            assert all(
                item.rect().contains(control.geometry())
                for item, control in zip(fields, form.controls, strict=True)
            )
            assert all(control.width() > 0 for control in form.controls)
            assert source.currentText() == source.toolTip() == "External controller"
            assert (
                source.fontMetrics().horizontalAdvance(source.currentText())
                < source.width()
            )
            assert rate.text() == "60" and pin.text() == "9"
            assert form.stacked is stacked
        panel.close()
        panel.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        assert len(destroyed) == cycle + 1


def test_folder_picker_selection_cancellation_and_phase_lock(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(QFileDialog, "open", lambda self: None)
    field = window.dashboard.output_field
    field.editor.setText(str(tmp_path))
    field.browse.click()
    dialog = field.dialog
    assert dialog is not None
    assert Path(dialog.directory().absolutePath()) == tmp_path
    dialog.reject()
    assert field.editor.text() == str(tmp_path)
    field.browse.click()
    assert field.dialog is not None
    field.dialog.fileSelected.emit(str(tmp_path / "chosen"))
    assert field.editor.text() == str(tmp_path / "chosen")
    window.apply_view(review_view(Phase.RUNNING))
    assert not field.browse.isEnabled()
    field.dialog.fileSelected.emit(str(tmp_path / "late"))
    assert field.editor.text() == str(tmp_path / "chosen")
    field.dialog.reject()


def test_compact_path_keeps_full_text_tooltip_and_editing(
    window: DashboardWindow,
) -> None:
    editor = window.dashboard.output_root
    path = r"D:\experiments\long project name\subjects\CEPH-007\sessions\2026-10-01"
    editor.setText(path)
    window.dashboard.session_controls.command_buttons["Start"].setFocus()
    assert editor.text() == path and editor.toolTip() == path
    assert not editor.grab().isNull()
    editor.setFocus()
    editor.selectAll()
    assert editor.selectedText() == path
    editor.insert(r"D:\new folder")
    assert editor.toolTip() == r"D:\new folder"


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_log_overflow_has_visible_working_scrollbar(
    window: DashboardWindow, app: QApplication, style: str
) -> None:
    window.appearance.select(style, persist=False)
    console = window.dashboard.log_console
    console.setPlainText("\n".join(f"Message {i}" for i in range(100)))
    app.processEvents()
    scroll = console.verticalScrollBar()
    assert scroll is not None
    assert scroll.maximum() > 0 and scroll.isVisible() and scroll.width() > 0
    scroll.setValue(scroll.maximum())
    bottom = scroll.value()
    QTest.mouseClick(
        scroll, Qt.MouseButton.LeftButton, pos=QPoint(scroll.width() // 2, 5)
    )
    app.processEvents()
    assert scroll.value() < bottom
    before = console.firstVisibleBlock().text()
    console.appendPlainText("Newest message")
    app.processEvents()
    assert console.firstVisibleBlock().text() == before
    console.setPlainText("Short log")
    app.processEvents()
    assert scroll.maximum() == 0 and not scroll.isVisible()


def test_log_rows_use_terminal_columns_and_skip_exact_repeats(
    window: DashboardWindow,
) -> None:
    from datetime import datetime

    from cephvr.gui.log_format import terminal_body, terminal_row

    now = datetime(2026, 10, 21, 14, 12, 3)
    assert terminal_row(terminal_body("Setup · Waiting for backends…"), now) == (
        "14:12:03  [SETUP]     Waiting for backends…"
    )
    assert terminal_body("Visual stimulus · Preparing…") == "[STIMULUS]  Preparing…"
    assert terminal_row("Setup selected; no command sent", now) == (
        "14:12:03  Setup selected; no command sent"
    )
    console = window.dashboard.log_console
    console.setPlainText("")
    for message in ("Session · Preparing to start…",) * 2 + ("Session · Ready",):
        console.appendPlainText(message)
    console.append_entry("Session · Ready", "details", error=True)
    rows = console.toPlainText().splitlines()
    assert [row[STAMP_WIDTH:] for row in rows] == [
        "[SESSION]   Preparing to start…",
        "[SESSION]   Ready",
        "[SESSION]   Ready",
    ]


@pytest.mark.parametrize("result", ["Done", "Failed", "Cancelled", "Unconfirmed"])
def test_action_result_updates_original_row_without_touching_other_actions(
    window, result
):
    console = window.dashboard.log_console
    console.clear()
    console.action_entry(("first",), "Setup · Preparing…")
    original = console.toPlainText()
    console.action_entry(("second",), "Setup · Preparing…")
    console.appendPlainText("Unrelated observation")
    console.action_entry(("first",), "", result, "original diagnostics")
    rows = console.toPlainText().splitlines()
    assert rows[0] == original + f" [{result}]"
    assert rows[1].endswith("Preparing…")
    assert rows[2].endswith("Unrelated observation")
    assert console.document().firstBlock().userData().details == "original diagnostics"
    console.action_entry(("first",), "", result)
    assert console.toPlainText().splitlines() == rows
    console.clear()
    console.action_entry(("second",), "", result)
    assert console.toPlainText() == ""


def test_action_results_do_not_reuse_evicted_blocks(window):
    console = window.dashboard.log_console
    console.clear()
    console.setMaximumBlockCount(2)
    console.action_entry(("old",), "Setup · Preparing…")
    console.appendPlainText("Newer")
    console.appendPlainText("Newest")
    console.action_entry(("old",), "", "Done")
    assert [row[STAMP_WIDTH:] for row in console.toPlainText().splitlines()] == [
        "[GUI]       Newer",
        "[GUI]       Newest",
    ]
    console.action_entry(("old",), "Setup · Preparing…", "Failed", "failure evidence")
    assert console.document().lastBlock().userData().details == "failure evidence"
    assert console.toPlainText().endswith("[Failed]")


def test_action_results_follow_operation_and_participant_evidence(window):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_progress import ActionProgress

    console = window.dashboard.log_console
    console.clear()
    log = ActionProgress(
        lambda *_: None, lambda _target, *args: console.action_entry(*args)
    )
    log.requested("Setup", "Setup · Validating configuration…")
    state = pb.Snapshot(controller_generation="controller")
    state.session.phase = pb.SESSION_PHASE_SETTING_UP
    operation = state.operations.add(
        command="Setup", progress="Reserving output folder…"
    )
    operation.context.command_id = "setup-1"
    participant = state.participants.add()
    participant.process.role = "visual_stimulus"
    participant.process.generation = "worker-1"
    log.install(1, state)
    operation.progress = "Registering outputs…"
    log.install(1, state)
    operation.complete = True
    operation.succeeded = True
    state.session.phase = pb.SESSION_PHASE_READY
    participant.ready.required_checks_passed = True
    log.install(1, state)
    assert log.finished("Setup", "completed", "Setup confirmed")
    rows = console.toPlainText().splitlines()
    assert sum(row.endswith("[Done]") for row in rows) == 4
    assert "Reserving output folder" in console.toPlainText()
    log.install(1, state)
    assert console.toPlainText().splitlines() == rows
    console.clear()
    log.install(2, state)
    assert "[Done]" not in console.toPlainText()


def test_action_results_keep_unknown_and_failed_completion_truthful(window):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_progress import ActionProgress

    console = window.dashboard.log_console
    console.clear()
    log = ActionProgress(
        lambda *_: None, lambda _target, *args: console.action_entry(*args)
    )
    state = pb.Snapshot(controller_generation="controller")
    operation = state.operations.add(command="Setup", progress="Preparing…")
    operation.context.command_id = "setup"
    recovery = state.recoveries.add(attempt_id="recovery", progress="Releasing…")
    state.session.phase = pb.SESSION_PHASE_RUNNING
    state.trial.context.trial_id = "trial"
    state.trial.phase = pb.TRIAL_PHASE_FINALIZING
    log.install(1, state)
    operation.complete = True
    operation.succeeded = False
    recovery.completion_monotonic_ns = 1
    state.trial.phase = pb.TRIAL_PHASE_ENDED
    state.trial.outcome = pb.TRIAL_OUTCOME_INTERRUPTED
    log.install(1, state)
    text = console.toPlainText()
    assert "Preparing… [Failed]" in text
    assert "Releasing… [Unconfirmed]" in text
    assert "Finalizing files… [Interrupted]" in text
    assert "[Done]" not in text


@pytest.mark.parametrize("matches", [True, False])
def test_finalization_result_survives_coalesced_configuration_reset(window, matches):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_progress import ActionProgress

    console = window.dashboard.log_console
    console.clear()
    log = ActionProgress(
        lambda *_: None, lambda _target, *args: console.action_entry(*args)
    )
    state = pb.Snapshot(controller_generation="controller")
    state.session.phase = pb.SESSION_PHASE_FINALIZING
    state.session.context.session_id = "session"
    state.session.context.controller_generation = "controller"
    state.trial.context.session.CopyFrom(state.session.context)
    state.trial.context.trial_id = "trial"
    state.trial.phase = pb.TRIAL_PHASE_FINALIZING
    log.install(1, state)
    state.last_finalization.session.CopyFrom(state.session)
    state.last_finalization.session.phase = pb.SESSION_PHASE_ENDED
    state.last_finalization.session.cleanup_confirmed = True
    state.last_finalization.trial.CopyFrom(state.trial)
    state.last_finalization.trial.outcome = pb.TRIAL_OUTCOME_INTERRUPTED
    if not matches:
        state.last_finalization.session.context.session_id = "other-session"
    state.ClearField("session")
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.session.cleanup_confirmed = True
    state.ClearField("trial")
    log.install(1, state)
    rows = console.toPlainText().splitlines()
    assert sum(row.endswith("[Done]") for row in rows) == (2 if matches else 0)
    log.install(1, state)
    assert console.toPlainText().splitlines() == rows
    console.clear()
    log.install(2, state)
    assert console.toPlainText() == ""


def test_log_keeps_reading_position_during_append_and_retention(
    window: DashboardWindow, app: QApplication
) -> None:
    console = window.dashboard.log_console
    console.setPlainText("\n".join(f"Message {i}" for i in range(256)))
    app.processEvents()
    scroll = console.verticalScrollBar()
    assert scroll is not None
    scroll.setValue(80)
    before = console.firstVisibleBlock().text()
    console.appendPlainText("\n".join(f"New {i}" for i in range(20)))
    app.processEvents()
    assert console.firstVisibleBlock().text() == before
    scroll.setValue(scroll.maximum())
    console.appendPlainText("Latest")
    assert scroll.value() == scroll.maximum()
    console.clear()
    console.appendPlainText("Latest")
    assert log_rows(console) == ["[GUI]       Latest"]


@pytest.mark.parametrize(
    "text,error,expected",
    [
        ("Camera failed: timeout", None, True),
        ("Transport error: lost connection", None, True),
        ("Cannot open camera", None, True),
        ("Setup rejected", None, True),
        ("No error reported", None, False),
        ("Completed without error", None, False),
        ("0 errors", None, False),
        ("Controller connected", None, False),
        ("Calibration file is missing", True, True),
        ("Previous failed operation recovered", False, False),
    ],
)
def test_log_error_color_preserves_text_details_and_style_switch(
    app: QApplication, text: str, error: bool | None, expected: bool
) -> None:
    from cephvr.gui.components import LogConsole
    from cephvr.gui.log_colors import log_block_is_error
    from cephvr.gui.theme import COLORS, RETRO_COLORS

    console = LogConsole()
    try:
        console.setProperty("retroConsole", True)
        console.append_entry(text, "exact command details", error=error)
        console.appendPlainText("Next normal entry")
        app.processEvents()
        block = console.document().begin()
        assert log_block_is_error(block) is expected
        formats = block.layout().formats()
        assert bool(formats) is expected
        if expected:
            assert formats[0].format.foreground().color().name() == RETRO_COLORS.error
        assert not block.next().layout().formats()
        console.setProperty("retroConsole", False)
        console.set_entry_prompts(False)
        if expected:
            assert (
                block.layout().formats()[0].format.foreground().color().name()
                == COLORS.error
            )
        assert log_rows(console) == [
            f"[GUI]       {text}",
            "[GUI]       Next normal entry",
        ]
        assert block.userData().details == "exact command details"
    finally:
        console.deleteLater()


def test_log_entry_details_follow_their_own_bounded_document_block(
    app: QApplication,
) -> None:
    from cephvr.gui.consoles import LogConsole, _LogDetails

    console = LogConsole(lines=3)
    console.setMaximumBlockCount(2)
    console.append_entry("First accepted", "command_id=first")
    console.append_entry("Second\nfailed", "command_id=second\n<unknown>")
    app.processEvents()
    document = console.document()
    assert document is not None
    first, second = document.begin(), document.begin().next()
    assert first.text()[STAMP_WIDTH:] == "[GUI]       First accepted"
    assert isinstance(first.userData(), _LogDetails)
    assert first.userData().details == "command_id=first"
    assert second.text()[STAMP_WIDTH:] == "[GUI]       Second · failed"
    assert isinstance(second.userData(), _LogDetails)
    assert second.userData().details == "command_id=second\n<unknown>"
    console.appendPlainText("Third")
    app.processEvents()
    assert document.blockCount() == 2
    assert document.begin().text()[STAMP_WIDTH:] == "[GUI]       Second · failed"
    assert document.begin().userData().details == "command_id=second\n<unknown>"
    console.deleteLater()


def test_managed_operation_log_suppresses_success_and_preserves_failure(
    app: QApplication,
) -> None:
    from cephvr.gui.components import LogConsole
    from cephvr.gui.main import ManagedGui

    console = LogConsole()
    manager = SimpleNamespace(
        window=SimpleNamespace(dashboard=SimpleNamespace(log_console=console)),
        prompts=SimpleNamespace(operation_finished=lambda _action: None),
        action_progress=SimpleNamespace(finished=lambda *_: False),
    )
    ManagedGui.operation_finished(
        manager, "Setup", "command-1", "completed", "Completed."
    )
    ManagedGui.operation_finished(
        manager, "Setup", "command-2", "failed", "<unknown> renderer failure"
    )
    assert log_rows(console) == [
        "[SETUP]     failed — <unknown> renderer failure",
    ]
    document = console.document()
    assert document is not None
    details = []
    block = document.begin()
    while block.isValid():
        user_data = block.userData()
        if user_data is not None:
            details.append(user_data.details)
        block = block.next()
    assert "Command ID: command-2" in details[0]
    assert "<unknown> renderer failure" in details[-1]
    assert document.lastBlock().userData().error is True
    assert document.begin().userData().error is True
    console.deleteLater()


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", ["recover", "delete", "continue"])
@pytest.mark.parametrize("outcome", ["success", "failed", "unconfirmed", "needs_input"])
async def test_recovery_result_feedback_waits_for_confirmed_prompt_completion(
    choice, outcome
):
    import asyncio

    from cephvr.client.session import ClientError
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    progress, completions = [], []
    bridge.action_progress.connect(
        lambda action, message: progress.append((action, message))
    )
    bridge.operation_finished.connect(lambda *args: completions.append(args))
    state = pb.Snapshot()
    prompt = state.prompts.add(
        prompt_id="prompt",
        permitted_choices=["continue", "cancel"]
        if choice == "continue"
        else ["recover", "delete"],
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def admit(_method, request):
        assert request.choice == choice
        return pb.CommandAdmission(
            command_id="command", result=pb.COMMAND_RESULT_ACCEPTED
        )

    async def wait_result(_command_id):
        entered.set()
        await release.wait()
        if outcome == "unconfirmed":
            raise ClientError("Connection lost before completion")
        return SimpleNamespace(
            needs_input=outcome == "needs_input",
            complete=outcome != "needs_input",
            succeeded=outcome == "success",
            failure="Deletion failed" if outcome == "failed" else "",
        )

    client = SimpleNamespace(
        snapshot=state,
        operator_command=lambda: rpc.OperatorCommand(),
        _admit=admit,
        wait_result=wait_result,
    )
    task = asyncio.create_task(
        bridge._dispatch(
            client,
            "respond_prompt",
            {"prompt": prompt.SerializeToString(), "choice": choice},
        )
    )
    await asyncio.wait_for(entered.wait(), 1)
    assert progress == []
    release.set()
    await task
    if outcome == "success" and choice != "continue":
        assert progress == [
            (
                "respond_prompt",
                "Recovery · Unfinished session files deleted."
                if choice == "delete"
                else "Recovery · Recovery completed; existing files preserved.",
            )
        ]
    else:
        assert progress == []
    assert (
        completions[-1][2]
        == {
            "success": "completed",
            "failed": "failed",
            "unconfirmed": "unconfirmed",
            "needs_input": "needs_input",
        }[outcome]
    )


@pytest.mark.parametrize(
    "action,options,expected",
    [
        ("camera", {"role": 1, "kind": 5}, ""),
        ("Setup", {}, "Setup · Validating configuration…"),
        ("spikeglx_connection", {}, "SpikeGLX · Connecting…"),
        ("begin_tracking_diagnostic", {}, "Tracking · Preparing pipeline…"),
        ("Abort now", {}, "Session · Stopping…"),
        ("save_configuration_history", {}, "Shutdown · Saving configuration…"),
        ("tracking_diagnostic_frame", {}, ""),
        ("get_spikeglx_inventory", {}, ""),
    ],
)
def test_dispatched_action_log_uses_actions_without_poll_results(
    action, options, expected
):
    from cephvr.gui.action_progress import requested_action

    # Viewer Show/Hide and background frame polls add no capture-status claims.
    if action == "camera":
        from cephvr.control.v1 import services_pb2 as rpc

        options["kind"] = rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
    assert requested_action(action, options) == expected


def test_action_log_tracks_evidence_once_without_success_results():
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_progress import ActionProgress, requested_action

    rows = []
    log = ActionProgress(lambda target, message: rows.append((target, message)))
    log.requested(
        "camera",
        requested_action(
            "camera", {"role": 1, "kind": rpc.CAMERA_COMMAND_KIND_START_PREVIEW}
        ),
    )
    state = pb.Snapshot(controller_generation="controller")
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    operation = state.operations.add(
        command="ExecuteCameraCommand", progress="acquisition command pending"
    )
    operation.context.command_id = "connect"
    log.install(1, state)
    assert rows == [("cameras", "Behavior camera · Connecting…")]
    for action in (
        "Applying camera settings…",
        "Arming capture…",
        "Starting external triggers…",
        "Waiting for frames…",
    ):
        operation.progress = f"Behavior camera · {action}"
        log.install(1, state)
        log.install(1, state)
    assert len(rows) == 5
    assert not any("Live" in message for _, message in rows)
    operation.complete, operation.succeeded = True, True
    operation.progress = "camera command confirmed"
    device = state.acquisition_devices.behavioral
    device.device_open, device.preview_prepared = True, True
    device.preview_run_id = "run-1"
    log.install(1, state)
    assert len(rows) == 5  # Open/armed is not first-frame evidence.
    device.preview_running = True
    log.install(1, state)
    assert rows[-1] == ("cameras", "Behavior camera · Live")
    for count in range(5):
        state.captured_monotonic_ns = count
        poll = state.operations.add(
            command="ExecuteMicrocontrollerCommand",
            complete=True,
            succeeded=True,
            progress="Microcontroller command completed",
        )
        poll.context.command_id = str(count)
        log.install(1, state)
    assert len(rows) == 6
    log.install(2, state)
    assert rows[-1] == ("cameras", "Behavior camera · Live")
    assert len(rows) == 7  # Reconnect shows current state, not old completions.


def test_action_log_covers_session_backends_recording_recovery_and_shutdown():
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_progress import ActionProgress

    rows = []
    log = ActionProgress(lambda target, message: rows.append((target, message)))
    state = pb.Snapshot(controller_generation="controller")
    state.session.context.session_id = "session"
    state.session.phase = pb.SESSION_PHASE_SETTING_UP
    for name in ("visual_stimulus", "tracking"):
        state.participants.add().process.role = name
    log.install(1, state)
    assert ("projectors", "Visual stimulus · Preparing session resources…") in rows
    assert ("tracking", "Tracking · Preparing session resources…") in rows
    state.participants[0].preparation_progress = "Decoding textures: 120/500"
    log.install(1, state)
    assert rows[-1] == ("projectors", "Visual stimulus · Decoding textures: 120/500")
    count = len(rows)
    log.install(1, state)
    assert len(rows) == count
    state.session.phase = pb.SESSION_PHASE_READY
    log.install(1, state)
    assert rows[-1] == ("", "Session · Setup complete; waiting for Start")
    state.session.phase = pb.SESSION_PHASE_RUNNING
    state.trial.context.trial_id = "trial"
    state.trial.context.trial_number = 2
    for phase, action in (
        (pb.TRIAL_PHASE_PREPARING, "Preparing recording…"),
        (pb.TRIAL_PHASE_RUNNING, "Recording"),
        (pb.TRIAL_PHASE_FINALIZING, "Finalizing files…"),
    ):
        state.trial.phase = phase
        log.install(1, state)
        assert rows[-1] == ("", f"Trial 2 · {action}")
    state.session.phase = pb.SESSION_PHASE_FINALIZING
    state.trial.phase = pb.TRIAL_PHASE_ENDED
    log.install(1, state)
    assert rows[-1] == ("", "Session · Finalizing session…")
    state.session.phase = pb.SESSION_PHASE_ENDED
    log.install(1, state)
    assert not any(message.endswith("Idle") for _, message in rows)
    state.session.cleanup_confirmed = True
    log.install(1, state)
    assert rows[-1] == ("", "Session · Idle")
    recovery = state.recoveries.add(attempt_id="recovery", progress="Releasing camera…")
    log.install(1, state)
    assert rows[-1] == ("", "Recovery · Releasing camera…")
    recovery.completion_monotonic_ns = 1
    recovery.progress = "Completed"
    count = len(rows)
    log.install(1, state)
    assert len(rows) == count
    state.session.shutdown_requested = True
    log.install(1, state)
    assert rows[-1] == ("", "Shutdown · Releasing devices…")


def test_successful_tracking_frame_poll_does_not_add_routine_log_row(
    app: QApplication,
) -> None:
    from cephvr.gui.components import LogConsole
    from cephvr.gui.main import ManagedGui

    console = LogConsole()
    manager = SimpleNamespace(
        window=SimpleNamespace(dashboard=SimpleNamespace(log_console=console)),
        cameras=SimpleNamespace(finished=lambda *_: None),
        action_progress=SimpleNamespace(finished=lambda *_: False),
    )
    ManagedGui.command_finished(
        manager, "tracking_diagnostic_frame", True, "Frame ready"
    )
    assert console.toPlainText() == ""
    ManagedGui.command_finished(
        manager, "tracking_diagnostic_frame", False, "Frame failed"
    )
    assert log_rows(console) == [
        "[GUI]       Tracking diagnostic frame failed: Frame failed"
    ]
    console.deleteLater()


def test_review_setup_click_logs_simulated_intent(window: DashboardWindow) -> None:
    dashboard = window.dashboard
    QTest.mouseClick(dashboard.command_buttons["Start"], Qt.MouseButton.LeftButton)
    assert "Setup selected; simulated session" in dashboard.log_console.toPlainText()


def test_runtime_preview_controls_request_visibility_without_a_window(
    window: DashboardWindow, app: QApplication
) -> None:
    dashboard = window.dashboard
    assert dashboard.pages.currentWidget() is dashboard.form
    show_previews(window)
    dialog = dashboard.preview_workspace
    assert dashboard.pages.currentWidget() is dialog
    assert window.preview_slot.window() is window
    assert all(
        control.width() >= control.sizeHint().width()
        for control in dialog.controls.values()
    )
    dialog.controls["camera-1"].click()
    assert dialog.controls["camera-1"].isChecked()
    dialog.controls["camera-1"].click()
    assert not any(item.visible for item in dashboard.view.previews)
    assert "no viewer command sent" in dashboard.log_console.toPlainText()


@pytest.mark.parametrize(
    ("anchor", "area", "expected"),
    [
        (QRect(100, 80, 900, 700), QRect(0, 0, 1920, 1080), QPoint(1012, 80)),
        (QRect(-1800, 80, 900, 700), QRect(-1920, 0, 1920, 1080), QPoint(-888, 80)),
        (QRect(30, 40, 1150, 700), QRect(0, 0, 1200, 900), QPoint(740, 40)),
    ],
)
def test_preview_snap_gap_and_available_screen_bounds(
    anchor: QRect, area: QRect, expected: QPoint
) -> None:
    assert tool_window_position(anchor, QSize(460, 350), area) == expected


def test_preview_waits_for_report_and_handles_failure_closure_and_control_loss(
    app: QApplication,
) -> None:
    window = DashboardWindow()
    dashboard = window.dashboard
    item = PreviewView("camera", "Camera", available=True, active=True, reason="")
    state = DashboardView(connected=True, has_control=True, previews=(item,))
    dashboard.apply_view(state)
    requests: list[tuple[str, bool]] = []
    dashboard.preview_requested.connect(lambda key, show: requests.append((key, show)))
    dialog = dashboard.preview_workspace
    dialog.controls["camera"].click()
    assert requests == [("camera", True)]
    assert not dialog.controls["camera"].isChecked()
    assert not dialog.controls["camera"].isEnabled()
    dialog.request("camera", True)
    assert len(requests) == 1
    dashboard.apply_view(
        replace(state, previews=(replace(item, reason="Open failed"),))
    )
    assert dialog.statuses["camera"] == "Open failed"
    assert dialog.controls["camera"].isEnabled()
    dashboard.apply_view(replace(state, previews=(replace(item, visible=True),)))
    assert dialog.controls["camera"].isChecked()
    dashboard.apply_view(state)  # Owner reports external-window closure.
    assert not dialog.controls["camera"].isChecked()
    for changed in (replace(state, has_control=False), replace(state, connected=False)):
        dashboard.apply_view(changed)
        dialog.request("camera", True)
        assert not dialog.controls["camera"].isEnabled()
    assert len(requests) == 1
    dashboard.apply_view(replace(state, previews=()))
    assert not dialog.controls
    window.close()
    window.deleteLater()
    app.processEvents()


def test_unavailable_preview_retains_reported_state_without_commands(
    window: DashboardWindow,
) -> None:
    dashboard = window.dashboard
    dashboard.apply_view(
        replace(
            dashboard.view,
            previews=(PreviewView("camera", "Camera", visible=True, reason="Offline"),),
        )
    )
    dialog = dashboard.preview_workspace
    assert dialog.controls["camera"].isChecked()
    assert not dialog.controls["camera"].isEnabled()
    assert dialog.statuses["camera"] == "Offline"


@pytest.mark.parametrize(
    ("phase", "actions", "editable"),
    [
        (Phase.CONFIGURATION, {"Start"}, True),
        (Phase.SETTING_UP, {"Stop"}, False),
        (Phase.READY, {"Start", "Stop"}, True),
        (Phase.STARTING, {"Stop"}, False),
        (Phase.RUNNING, {"Stop"}, False),
        (Phase.STOPPING, {"Stop"}, False),
        (Phase.FINALIZING, {"Stop"}, False),
        (Phase.ENDED, {"Start"}, True),
    ],
)
def test_review_phase_locks_and_actions(
    window: DashboardWindow, phase: Phase, actions: set[str], editable: bool
) -> None:
    window.apply_view(review_view(phase))
    dashboard = window.dashboard
    assert {
        name
        for name, control in dashboard.command_buttons.items()
        if control.isEnabled()
    } == actions
    assert dashboard.subject_id.isEnabled() is editable
    assert "Synced" not in dashboard.runtime_console.toPlainText() or phase in {
        Phase.RUNNING,
        Phase.STOPPING,
        Phase.FINALIZING,
        Phase.ENDED,
    }


def test_observer_locks_preserve_local_draft(window: DashboardWindow) -> None:
    dashboard = window.dashboard
    dashboard.subject_id.setText("REVIEW-EDIT")
    window.apply_view(review_view(Phase.RUNNING))
    window.apply_view(review_view(Phase.CONFIGURATION, observer=True))
    assert dashboard.subject_id.text() == "REVIEW-EDIT"
    assert not dashboard.subject_id.isEnabled()
    assert not any(
        control.isEnabled() for control in dashboard.command_buttons.values()
    )
    window.apply_view(review_view(Phase.CONFIGURATION))
    assert dashboard.subject_id.isEnabled()


def test_responsive_navigation_preserves_widget_identity(
    app: QApplication, window: DashboardWindow
) -> None:
    subject = window.dashboard.subject_id
    subject.setText("PERSISTENT")
    modes = set()
    for width in (1920, 1440, 1100, 720, 1920):
        window.resize(width, 940)
        app.processEvents()
        modes.add(window.dashboard.mode)
        for index in range(4):
            window.page_buttons[index].click()
            app.processEvents()
            assert window.stack.currentIndex() == index
        window.page_buttons[0].click()
        app.processEvents()
        assert window.dashboard.subject_id is subject
        assert subject.text() == "PERSISTENT"
        assert subject.parentWidget() is not None
        assert window.dashboard_scroll.horizontalScrollBar().maximum() == 0
    assert modes == {"wide", "stacked"}


def test_review_selector_renders_completion_and_observer_lock(
    window: DashboardWindow,
) -> None:
    controls = window.findChild(ReviewControls)
    assert controls is not None
    controls.set_phase(Phase.ENDED)
    assert "Completed" in window.dashboard.runtime_console.toPlainText()
    assert window.dashboard.view.output_status == "Closed"
    assert "TOTAL TIME" in window.dashboard.runtime_console.toPlainText()
    assert "D:/CephVR/SP0001-120000" in window.dashboard.runtime_console.toPlainText()
    assert "OUTPUT" not in window.dashboard.preview_workspace.hud.toPlainText()
    controls.observer.setChecked(True)
    assert not window.dashboard.command_buttons["Start"].isEnabled()


@pytest.mark.parametrize("dimensions", [(1440, 940), (1175, 883)])
def test_wide_layout_keeps_status_and_logs_visible(
    app: QApplication, window: DashboardWindow, dimensions: tuple[int, int]
) -> None:
    window.resize(*dimensions)
    app.processEvents()
    viewport = window.dashboard
    assert viewport is not None
    for panel in (
        window.dashboard.runtime_console,
        window.dashboard.log_console,
    ):
        top = panel.mapTo(viewport, panel.rect().topLeft())
        bottom = panel.mapTo(viewport, panel.rect().bottomRight())
        assert viewport.rect().contains(top)
        assert viewport.rect().contains(bottom)


def test_dashboard_has_only_requested_cards(window: DashboardWindow) -> None:
    from cephvr.gui.components import Card

    titles = {
        card.header.itemAt(0).widget().text()
        for card in window.dashboard.findChildren(Card)
        if not window.dashboard.preview_workspace.isAncestorOf(card)
    }
    assert titles == {
        "System controls",
        "Session config",
        "Saving options",
        "HUD",
        "Log",
    }
    assert not any(
        item.property("role") == "pill" for item in window.findChildren(QLabel)
    )
    assert window.dashboard.age.placeholderText() == "Age (dph)"
    assert any(
        item.text() == "AGE (dph)"
        for item in window.dashboard.subject_card.findChildren(QLabel)
    )
    labels = [item.text().lower() for item in window.findChildren(QLabel)]
    assert not any(
        "design review" in text or "local frontend" in text for text in labels
    )
    assert not any(
        child.property("role") == "banner" for child in window.findChildren(QWidget)
    )


@pytest.mark.parametrize("preview_open", [False, True])
def test_hud_fits_content_and_log_fills_available_height(
    app: QApplication, window: DashboardWindow, preview_open: bool
) -> None:
    dashboard = window.dashboard
    window.apply_view(
        replace(
            dashboard.view,
            previews=(PreviewView("camera", "Camera", visible=preview_open),),
        )
    )
    panel_heights = []
    log_heights = []
    preview_heights = []
    for height in (883, 1100):
        window.resize(1920, height)
        app.processEvents()
        assert dashboard.mode == "wide"
        right = dashboard.columns[1]
        assert dashboard.hud_card.y() == 0
        # Previews are hosted only in the runtime layout, never beside the form.
        assert window.preview_slot.isHidden()
        assert dashboard.log_card.geometry().bottom() == right.height() - 1
        assert dashboard.runtime_console.verticalScrollBar().maximum() == 0
        assert dashboard.log_console.height() > dashboard.log_console.minimumHeight()
        log_heights.append(dashboard.log_console.height())
        preview_heights.append(0)
        panel_heights.append(dashboard.runtime_console.height())
    assert panel_heights[1] == panel_heights[0]
    assert log_heights[1] > log_heights[0]
    assert (
        log_heights[1] - log_heights[0] + preview_heights[1] - preview_heights[0]
        == 1100 - 883
    )
    original = dashboard.runtime_console.toPlainText()
    dashboard.runtime_console.setPlainText(
        original + "\nEXTRA  additional runtime evidence"
    )
    app.processEvents()
    assert dashboard.runtime_console.height() > panel_heights[0]
    dashboard.runtime_console.setPlainText(original)
    app.processEvents()
    assert dashboard.runtime_console.height() == panel_heights[0]
    start, stop = (dashboard.command_buttons[name] for name in ("Start", "Stop"))
    assert start.y() == stop.y()
    assert abs(start.width() - stop.width()) <= 1


def test_setup_serves_as_new_session_after_completion(window: DashboardWindow) -> None:
    dashboard = window.dashboard
    requests: list[str] = []
    dashboard.action_requested.connect(requests.append)
    assert list(dashboard.command_buttons) == ["Start", "Stop"]
    dashboard.command_buttons["Start"].click()
    window.apply_view(review_view(Phase.ENDED))
    dashboard.command_buttons["Start"].click()
    assert requests == ["Setup", "New session"]
    assert dashboard.view.phase == Phase.ENDED
    assert "New session selected" in dashboard.log_console.toPlainText()


@pytest.mark.parametrize(
    ("phase", "cleanup", "control", "wired", "editable"),
    [
        (Phase.ENDED, True, True, True, True),
        (Phase.ENDED, False, True, True, False),
        (Phase.ENDED, True, False, True, False),
        (Phase.ENDED, True, True, False, False),
        (Phase.RUNNING, True, True, True, False),
        (Phase.FINALIZING, True, True, True, False),
    ],
)
def test_post_stop_session_draft_editing_requires_cleanup_and_authority(
    window: DashboardWindow,
    phase: Phase,
    cleanup: bool,
    control: bool,
    wired: bool,
    editable: bool,
) -> None:
    view = DashboardView(
        phase=phase,
        connected=True,
        has_control=control,
        configuration_wired=wired,
        cleanup_confirmed=cleanup,
    )
    window.apply_view(view)
    assert all(
        editor.isEnabled() is editable for editor in window.dashboard.subject_editors
    )
    assert view.can_edit is editable
    assert window.protocol.editor.isEnabled() is editable
    assert window.tracking.configuration.isEnabled() is editable
    window.apply_view(replace(view, connected=False))
    assert not window.dashboard.subject_id.isEnabled()


@pytest.mark.parametrize(
    "phase,cleanup,pending",
    [
        (Phase.FINALIZING, False, False),
        (Phase.ENDED, False, False),
        (Phase.CONFIGURATION, False, True),
    ],
)
def test_finalization_locks_setup_and_protocol_controls(
    window, phase, cleanup, pending
):
    view = replace(
        review_view(phase), cleanup_confirmed=cleanup, cleanup_pending=pending
    )
    window.apply_view(view)
    assert not window.dashboard.command_buttons["Start"].isEnabled()
    assert not window.dashboard.command_buttons["Start"].isEnabled()
    assert not window.protocol.editor.isEnabled()
    assert not window.dashboard.subject_id.isEnabled()
    assert not window.dashboard.can_request("Setup")
    assert not window.dashboard.can_request("New session")
    window.apply_view(
        replace(
            view,
            phase=Phase.CONFIGURATION,
            cleanup_confirmed=True,
            cleanup_pending=False,
        )
    )
    assert window.dashboard.command_buttons["Start"].isEnabled()
    assert window.protocol.editor.isEnabled()


def test_configuration_cleanup_blockers_lock_protocol_projection(window):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_status import dashboard_view

    state = pb.Snapshot()
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.control.holder_client_id = "gui"
    state.session.cleanup_blockers.add(resource="recording files")
    view = dashboard_view(state, "gui", (), configuration_wired=True)
    window.apply_view(view)
    assert view.cleanup_pending
    assert not window.dashboard.command_buttons["Start"].isEnabled()
    assert not window.protocol.editor.isEnabled()
    state.session.ClearField("cleanup_blockers")
    state.session.cleanup_confirmed = True
    view = dashboard_view(state, "gui", (), configuration_wired=True)
    window.apply_view(view)
    assert window.dashboard.command_buttons["Start"].isEnabled()
    assert window.protocol.editor.isEnabled()


def test_post_stop_subject_draft_survives_new_session_snapshot(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.configuration.revision = state.configuration_values.revision = 1
    state.configuration_values.current.subject = "0001"
    state.session.phase = pb.SESSION_PHASE_ENDED
    state.session.cleanup_confirmed = True
    state.control.holder_client_id = "operator"
    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
        )
    )
    assert manager.install(state)
    window.apply_view(dashboard_view(state, "operator", (), configuration_wired=True))
    assert window.dashboard.subject_id.isEnabled()
    window.dashboard.subject_id.setText("0002")
    window.dashboard.subject_id.textEdited.emit("0002")
    assert manager.dirty
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    assert manager.install(state)
    window.apply_view(dashboard_view(state, "operator", (), configuration_wired=True))
    assert window.dashboard.subject_id.text() == "0002"
    assert manager.dirty and not manager.stale
    assert state.configuration_values.current.subject == "0001"


@pytest.mark.parametrize("phase", [Phase.SETTING_UP, Phase.READY])
def test_stop_cancels_setup_without_a_dialog(
    window: DashboardWindow, phase: Phase
) -> None:
    dashboard = window.dashboard
    requests: list[str] = []
    dashboard.action_requested.connect(requests.append)
    window.apply_view(review_view(phase))
    dashboard.command_buttons["Stop"].click()
    assert requests == ["Cancel Setup"]
    assert dashboard.stop_dialog is None
    assert dashboard.view.phase == phase


@pytest.mark.parametrize(
    "choice, expected",
    [
        ("Abort now", ["Abort now"]),
        ("Stop after trial", ["Stop after trial"]),
        ("Cancel", []),
        ("Escape", []),
        ("Close", []),
    ],
)
def test_stop_requires_a_choice_during_session(
    app: QApplication, window: DashboardWindow, choice: str, expected: list[str]
) -> None:
    dashboard = window.dashboard
    requests: list[str] = []
    dashboard.action_requested.connect(requests.append)
    window.apply_view(review_view(Phase.RUNNING))
    dashboard.command_buttons["Stop"].click()
    app.processEvents()
    dialog = dashboard.stop_dialog
    assert dialog is not None and dialog.isVisible()
    assert requests == []
    assert [control.text() for control in dialog.choice_buttons.values()] == [
        "Stop now",
        "Stop after trial",
    ]
    assert dialog.cancel.isDefault()
    dashboard.stop()
    assert dashboard.stop_dialog is dialog
    if choice == "Cancel":
        dialog.cancel.click()
    elif choice == "Escape":
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
    elif choice == "Close":
        dialog.close()
    else:
        dialog.choice_buttons[choice].click()
    assert requests == expected
    assert dashboard.stop_dialog is None
    assert dashboard.view.phase == Phase.RUNNING


def test_stop_dialog_updates_choices_and_closes_on_control_loss(
    window: DashboardWindow,
) -> None:
    dashboard = window.dashboard
    requests: list[str] = []
    dashboard.action_requested.connect(requests.append)
    window.apply_view(review_view(Phase.RUNNING))
    dashboard.stop()
    dialog = dashboard.stop_dialog
    assert dialog is not None
    window.apply_view(review_view(Phase.STOPPING))
    assert not dialog.choice_buttons["Stop after trial"].isEnabled()
    dialog.select("Stop after trial")
    assert requests == []
    assert dialog.choice_buttons["Abort now"].isEnabled()
    window.apply_view(review_view(Phase.STOPPING, observer=True))
    assert dashboard.stop_dialog is None
    assert not dialog.isVisible()
    dashboard.request_action("Abort now")
    assert requests == []


def test_system_controls_show_backend_status_only_on_dashboard(window):
    from PyQt6.QtWidgets import QRadioButton

    dashboard = window.dashboard
    assert dashboard.session_controls.findChildren(QRadioButton) == list(
        dashboard.backend_indicators.values()
    )
    assert list(dashboard.backend_indicators) == [
        "Cameras",
        "Visual stimulus",
        "Tracking",
    ]
    assert (
        dashboard.session_controls.body.itemAt(0).layout()
        is dashboard.session_controls.header
    )
    window.protocol.session_mode.setCurrentText("Open-loop")
    window.recordings.velocities.setChecked(False)
    assert dashboard.backend_indicators["Tracking"].isHidden()
    window.recordings.velocities.setChecked(True)
    assert not dashboard.backend_indicators["Tracking"].isHidden()
    window.recordings.velocities.setChecked(False)
    window.protocol.session_mode.setCurrentText("Closed-loop")
    assert not dashboard.backend_indicators["Tracking"].isHidden()
    for enabled in (False, True):
        for camera in window.devices.cameras.drafts:
            camera.enabled = enabled
        window.devices.cameras.drafts_changed.emit()
        assert dashboard.backend_indicators["Cameras"].isHidden() != enabled
    assert not dashboard.backend_indicators["Visual stimulus"].isHidden()
    for phase in (Phase.READY, Phase.CONFIGURATION):
        window.apply_view(review_view(phase))
        for indicator in dashboard.backend_indicators.values():
            assert indicator.isChecked() == (phase == Phase.READY)
            indicator.click()
            assert indicator.isChecked() == (phase == Phase.READY)
            assert indicator.status in indicator.toolTip()
    assert list(dashboard.session_controls.command_buttons) == ["Start", "Stop"]
    # The same card, indicators included, moves into the runtime layout.
    show_previews(window)
    cell = dashboard.preview_workspace.top.itemAtPosition(0, 0)
    assert cell is not None and cell.widget() is dashboard.session_controls
    assert dashboard.session_controls.findChildren(QRadioButton) == list(
        dashboard.backend_indicators.values()
    )


def test_preview_participation_gates_and_camera_draft_selection(
    window: DashboardWindow,
) -> None:
    cameras = window.devices.cameras
    dashboard = window.dashboard
    dialog = dashboard.preview_workspace
    assert [item.name for item in dashboard.view.previews] == [
        "Behavior cam",
        "Tracking cam",
        "Tracking",
        "Visual stimulus",
    ]
    cameras.connect_button.click()
    assert cameras.selected.connected
    cameras.fields["trigger_frequency_hz"].setText("1200")
    cameras.edit("trigger_frequency_hz", "1200")
    cameras.table.selectRow(1)
    assert cameras.fields["trigger_frequency_hz"].text() == ""
    cameras.edit("trigger_frequency_hz", "2400")
    cameras.table.selectRow(0)
    assert cameras.fields["trigger_frequency_hz"].text() == "1200"
    assert not hasattr(cameras, "preview_button")
    assert dialog.controls["camera-1"].isChecked()
    cameras.enable_controls[0].click()
    assert not dialog.controls["camera-1"].isEnabled()
    assert not dialog.names["camera-1"].isEnabled()
    requests = []
    dashboard.preview_requested.connect(lambda *args: requests.append(args))
    dialog.request("camera-1", True)
    assert requests == []
    assert not dialog.controls["camera-1"].isChecked()
    controls = window.findChild(ReviewControls)
    controls.backend_actions["tracking"].setChecked(False)
    assert not dialog.controls["tracking"].isEnabled()
    assert dialog.controls["camera-2"].isEnabled()
    controls.backend_actions["stimulus"].setChecked(False)
    assert not dialog.controls["stimulus"].isEnabled()
    controls.set_phase(Phase.RUNNING)
    assert not cameras.connect_button.isEnabled()
    assert not cameras.preset_field.browse.isEnabled()
    assert not cameras.role.isEnabled()
    assert not any(c.isEnabled() for c in cameras.enable_controls)
    cameras.drafts[0].enabled = True
    cameras.populate_inventory()
    cameras.toggle_connection()
    cameras.edit("trigger_frequency_hz", "9999")
    assert cameras.drafts[0].enabled
    assert cameras.drafts[0].values["trigger_frequency_hz"] == "1200"


def test_camera_role_uniqueness_and_extra_preview_rows(window: DashboardWindow) -> None:
    cameras = window.devices.cameras
    cameras.role.setCurrentText("Tracking cam")
    assert cameras.selected.role == "Behavior cam"
    cameras.role.setCurrentText("Unassigned")
    assert "camera-1" not in window.dashboard.preview_workspace.controls
    cameras.table.selectRow(1)
    cameras.role.setCurrentText("Behavior cam")
    assert cameras.selected.role == "Behavior cam"
    extra = PreviewView("extra", "Side cam", active=False, available=True, reason="")
    window.apply_view(
        replace(
            window.dashboard.view, previews=(*window.dashboard.view.previews, extra)
        )
    )
    dialog = window.dashboard.preview_workspace
    assert "extra" in dialog.controls
    assert not dialog.controls["extra"].isEnabled()
    assert not dialog.names["extra"].isEnabled()


def test_camera_pfs_picker_preserves_camera_identity_and_editing_gate(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(QFileDialog, "open", lambda self: None)
    cameras = window.devices.cameras
    picker = cameras.preset_field
    preset = tmp_path / "behavior.pfs"
    preset.write_text("external Pylon preset; GUI must not interpret it")
    picker.browse.click()
    dialog = picker.dialog
    assert dialog is not None
    assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
    assert "*.pfs" in dialog.nameFilters()[0]
    dialog.fileSelected.emit(str(preset))
    assert cameras.drafts[0].values["preset"] == str(preset)
    cameras.table.selectRow(1)
    assert picker.dialog is None
    dialog.fileSelected.emit(str(preset))
    assert cameras.preset.text() == ""
    assert "preset" not in cameras.drafts[1].values
    picker.browse.click()
    dialog = picker.dialog
    assert dialog is not None
    window.apply_view(review_view(Phase.RUNNING))
    dialog.fileSelected.emit(str(preset))
    assert cameras.preset.text() == ""
    dialog.reject()
    window.apply_view(review_view(Phase.CONFIGURATION))
    cameras.table.selectRow(0)
    assert cameras.preset.text() == str(preset)
    picker.browse.click()
    picker.dialog.reject()
    assert cameras.preset.text() == str(preset)
    assert set(cameras.fields) == {"trigger_frequency_hz"}


def test_all_pages_share_fitted_hud_and_expanding_log(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.components import StatusColumn

    targets = [(0, None), *((2, i) for i in range(4)), (3, None)]
    top_positions = []
    for page, subtab in targets:
        window.page_buttons[page].click()
        if subtab is not None:
            window.devices.tabs.setCurrentIndex(subtab)
            panel = window.devices.panels[subtab]
        else:
            panel = window.stack.widget(page)
        status = panel.columns[1]
        if panel is window.devices.projectors:
            assert not status.hud_card.isVisible()
            assert panel.layout_card.isVisible() and panel.tank_card.isVisible()
            continue
        assert isinstance(status, StatusColumn)
        sizes = []
        for height in (940, 1040):
            window.resize(1920, height)
            app.processEvents()
            assert panel.mode == "wide"
            sizes.append((status.hud.height(), status.console.height()))
            if height == 940:
                first_card = panel.columns[0].layout().itemAt(0).widget()
                top_positions.append(
                    (
                        first_card.mapTo(window, QPoint()).y(),
                        status.hud_card.mapTo(window, QPoint()).y(),
                    )
                )
            assert status.hud_card.y() < status.log_card.y()
            assert status.hud.verticalScrollBar().maximum() == 0
        assert sizes[0][0] == sizes[1][0]
        assert sizes[1][1] > sizes[0][1]

    assert len(set(top_positions)) == 1


def test_device_tabs_sit_above_controls_without_moving_hud(
    window: DashboardWindow, app: QApplication
) -> None:
    assert window.tracking.load_button.text() == "Load…"
    assert window.tracking.save_button.text() == "Save as…"
    window.resize(1920, 940)
    app.processEvents()
    assert window.dashboard.mode == "wide"
    hud_top = window.dashboard.hud_card.mapTo(window, QPoint()).y()
    window.page_buttons[2].click()
    from cephvr.gui.theme import SIZES

    bar = window.devices.tab_bar

    def visible_tab(index):
        arrows = [
            control for control in bar.findChildren(QToolButton) if control.isVisible()
        ]
        visible = bar.rect()
        for control in arrows:
            visible.setRight(min(visible.right(), control.x() - 1))
        for _ in range(bar.count()):
            center = bar.tabRect(index).center()
            if visible.contains(center):
                return center
            direction = (
                Qt.ArrowType.LeftArrow
                if center.x() < visible.left()
                else Qt.ArrowType.RightArrow
            )
            arrow = next(
                control for control in arrows if control.arrowType() == direction
            )
            assert arrow.isEnabled()
            QTest.mouseClick(arrow, Qt.MouseButton.LeftButton)
            app.processEvents()
        pytest.fail("Device tab was not reachable through its scroll arrows")

    for width in (1920, 720, 1920):
        window.resize(width, 940)
        for index in (2, 0, 3, 1):
            app.processEvents()
            QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=visible_tab(index))
            app.processEvents()
            assert window.devices.tabs.currentIndex() == index
            panel = window.devices.panels[index]
            left = panel.columns[0]
            assert window.devices.navigation.parentWidget() is left
            assert bar.isVisible()
            assert bar.width() == left.width()
            arrows = [
                control
                for control in bar.findChildren(QToolButton)
                if control.isVisible()
            ]
            if not arrows:
                assert bar.tabRect(3).right() == bar.width() - 1
            else:
                assert all(
                    bar.rect().contains(control.geometry()) for control in arrows
                )
            if width == 1920:
                assert panel.mode == "wide"
                hud = panel.layout_card if index == 2 else panel.columns[1].hud_card
                border_top = (
                    hud.mapTo(window, QPoint()).y()
                    + hud.caption.geometry().center().y()
                )
                assert abs(bar.mapTo(window, QPoint()).y() - border_top) <= 1
            card = left.layout().itemAt(1).widget()
            assert card is window.devices.config_cards[index]
            assert card.caption.text() == "Configuration file"
            files = panel.calibration_files if index == 2 else panel.config_files
            assert card.isAncestorOf(files.load_button)
            assert card.isAncestorOf(files.save_button)
            assert files.load_button.text() == "Load…"
            assert files.save_button.text() == "Save as…"
            assert abs(files.load_button.width() - files.save_button.width()) <= 1
            assert files.load_button.height() == files.save_button.height()
            load_pos = files.load_button.mapTo(card, QPoint())
            save_pos = files.save_button.mapTo(card, QPoint())
            assert load_pos.y() == save_pos.y()
            assert save_pos.x() - load_pos.x() - files.load_button.width() == (
                SIZES.field_x_gap
            )
            if index in (0, 2):
                if index == 2:
                    measurements = panel.measurements
                    assert measurements.caption.text() == "Pixel-to-mm calibration"
                    widths = [measurements.table.columnWidth(i) for i in range(3)]
                    assert widths[1] > widths[0]
                    assert widths[1] > widths[2]
                header = panel.table.horizontalHeader()
                refresh = panel.refresh_button
                assert refresh.parentWidget() is header.viewport()
                assert refresh.text() == "" and not refresh.icon().isNull()
                assert refresh.size() == QSize(26, 26)
                assert refresh.iconSize() == QSize(16, 16)
                assert header.viewport().rect().contains(refresh.geometry())
                assert panel.table.horizontalHeaderItem(0).text() == "Use"
            if index == 1:
                assert panel.scan_button.parentWidget() is panel.port.parentWidget()
                assert panel.scan_button.size() == QSize(26, 26)
            if index == 1:
                assert not panel.io.isHidden()
                assert panel.output_table.isVisible()
                assert panel.triggers.rect().contains(panel.output_table.geometry())
                assert set(panel.pin_editors) == {
                    "behavioral",
                    "tracking",
                    "eye_tracking",
                }
                assert all(
                    pin.parentWidget()
                    is panel.output_table.cellWidget(panel.role_rows[key], 2)
                    for key, pin in panel.pin_editors.items()
                )
            assert card.y() >= window.devices.navigation.height() + SIZES.card_gap
            assert (
                window.devices.panels[index]
                .scrollers[0]
                .horizontalScrollBar()
                .maximum()
                == 0
            )
            if width == 1920:
                assert (
                    panel.layout_card if index == 2 else panel.columns[1].hud_card
                ).mapTo(window, QPoint()).y() == hud_top
    window.page_buttons[0].click()
    app.processEvents()
    assert window.dashboard.hud_card.mapTo(window, QPoint()).y() == hud_top


def test_camera_batch_check_preserves_selection_and_connections(
    window: DashboardWindow,
) -> None:
    cameras = window.devices.cameras
    cameras.enable_controls[1].setChecked(False)
    cameras.table.selectRow(1)
    cameras.test_enabled()
    log = cameras.console.toPlainText()
    assert "requested for Behavior cam (REVIEW-001)" in log
    assert "requested for Tracking cam" not in log
    assert "not tested" in log
    assert cameras.selected is cameras.drafts[1]
    assert not any(draft.connected for draft in cameras.drafts)
    cameras.connect_button.click()
    assert cameras.connect_button.text() == "Disconnect selected"
    assert cameras.selected.capture_running
    cameras.connect_button.click()
    assert cameras.connect_button.text() == "Connect selected"
    assert not cameras.selected.capture_running
    assert "Disconnect; no hardware command sent" in cameras.console.toPlainText()
    cameras.enable_controls[0].setChecked(False)
    assert not cameras.connect_all_button.isEnabled()
    assert cameras.connect_button.isEnabled()
    assert "Test enabled" not in [b.text() for b in cameras.findChildren(QPushButton)]
    cameras.enable_controls[0].setChecked(True)
    window.apply_view(review_view(Phase.RUNNING))
    before = cameras.console.toPlainText()
    cameras.test_enabled()
    assert cameras.console.toPlainText() == before
    assert not cameras.connect_all_button.isEnabled()


def test_pfs_trigger_hint_and_per_camera_drafts(
    window: DashboardWindow, tmp_path: Path
) -> None:
    camera = window.devices.cameras
    preset = tmp_path / "external.pfs"
    preset.write_text(
        "# GenApi persistence file (version 3.5.0)\nTriggerMode\t{TriggerSelector=FrameBurstStart}\tOff\nTriggerMode\t{TriggerSelector=FrameStart}\tOn\nTriggerSource\t{TriggerSelector=FrameStart}\tLine3\n"
    )
    camera.preset_field.select_path(str(preset))
    assert camera.trigger_source.currentText() == "External controller"
    assert camera.selected.values["trigger_source"] == "Line3"
    camera.table.selectRow(1)
    assert camera.trigger_source.currentIndex() == -1
    camera.table.selectRow(0)
    assert camera.trigger_source.currentText() == "External controller"
    preset.write_text(
        "# GenApi persistence file\nTriggerSelector\tFrameStart\nTriggerMode\tOff\n"
    )
    camera.preset_field.select_path(str(preset))
    assert camera.trigger_source.currentText() == "Internal clock"
    preset.write_text(
        "# GenApi persistence file\nTriggerSelector\tFrameStart\nTriggerMode\tOn\nTriggerSource\tSoftware\n"
    )
    camera.preset_field.select_path(str(preset))
    assert camera.trigger_source.currentIndex() == -1
    assert "unsupported" in camera.console.toPlainText()


def test_real_camera_inventory_preserves_roles_and_tests_open_close(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import cameras

    class Info:
        def __init__(self, serial: str, model: str) -> None:
            self.serial = serial
            self.model = model

        def GetSerialNumber(self) -> str:
            return self.serial

        def GetModelName(self) -> str:
            return self.model

    found = [Info("40065509", "Basler A"), Info("40747103", "Basler B")]

    class Factory:
        def EnumerateDevices(self):
            return found

    class Adapter:
        events: list[str] = []

        def _sdk(self):
            return SimpleNamespace(
                TlFactory=SimpleNamespace(GetInstance=lambda: Factory())
            )

        def open(self, serial: str) -> None:
            self.events.append(f"open {serial}")
            self.serial = serial

        def read_device_identity(self):
            return SimpleNamespace(physical_id=self.serial, model="Basler A")

        def close(self) -> None:
            self.events.append("close")

    monkeypatch.setattr(cameras, "BaslerCameraAdapter", Adapter)
    panel = window.devices.cameras
    recording_keys = []
    panel.participation_changed.connect(
        lambda: recording_keys.append(set(window.recordings.record))
    )
    panel.real_devices = True
    panel.refresh_inventory()
    assert [draft.serial for draft in panel.drafts] == ["40065509", "40747103"]
    assert [draft.role for draft in panel.drafts] == ["Behavior cam", "Tracking cam"]
    assert {draft.key for draft in panel.drafts} <= recording_keys[-1]
    Adapter.events.clear()
    panel.drafts[1].enabled = False
    panel.test_enabled()
    assert Adapter.events == ["open 40065509", "close"]
    panel.assign_role("Unassigned")
    panel.refresh_inventory()
    assert panel.drafts[0].role == "Unassigned"
    found.clear()
    panel.refresh_inventory()
    assert not panel.drafts
    assert window.devices.microcontroller.camera_rows == ()


def test_microcontroller_camera_rows_and_discovery(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import microcontroller

    class Port:
        def __init__(self, name="COM7"):
            self.name = name

        def portName(self):
            return self.name

        def systemLocation(self):
            return "COM7"

        def description(self):
            return "Test board"

    monkeypatch.setattr(
        microcontroller.QSerialPortInfo,
        "availablePorts",
        lambda: [Port(), Port("ttyUSB0"), Port("cu.Bluetooth"), Port()],
    )
    panel = window.devices.microcontroller
    panel.request("Scan ports")
    assert panel.port.count() == 1
    assert panel.port.itemText(0) == "COM7 — Test board"
    assert panel.port.itemData(0) == "COM7"
    panel.can_review = False
    panel.scan_ports()  # Managed startup inventories before control is acquired.
    assert panel.port.itemData(0) == "COM7"
    panel.can_review = True
    panel.port.setCurrentIndex(0)
    camera = window.devices.cameras
    camera.trigger_source.setCurrentText("External controller")
    camera.fields["trigger_frequency_hz"].setText("120")
    panel.pin_editors["behavioral"].setText("5")
    camera.enable_controls[1].setChecked(False)
    assert list(panel.pin_editors) == ["behavioral", "tracking", "eye_tracking"]
    assert not camera.enable_controls[1].isChecked()
    assert panel.pin_editors["tracking"].isEnabled()
    assert panel.pins["behavioral"] == "5"
    panel.test_pin("behavioral")
    assert (
        "pin 5, requested 120 Hz output test; not tested" in panel.console.toPlainText()
    )
    panel.test_pin("behavioral")  # Stop the review before changing wiring.
    console_before = panel.console.toPlainText()
    assert not panel.enable_controls["projector-flip"].isChecked()
    panel.test_pin("projector-flip")
    assert panel.console.toPlainText() == console_before
    panel.request("Scan ports")
    assert panel.port.currentData() == "COM7"
    monkeypatch.setattr(microcontroller.QSerialPortInfo, "availablePorts", lambda: [])
    panel.request("Scan ports")
    assert panel.port.currentIndex() == -1
    window.apply_view(review_view(Phase.RUNNING))
    assert not panel.flip_pin.isEnabled()
    assert not any(control.isEnabled() for control in panel.test_buttons.values())


def test_wrapped_log_preserves_whole_words_and_reading_anchor(
    window: DashboardWindow, app: QApplication
) -> None:
    console = window.dashboard.log_console
    window.resize(1175, 940)
    text = "Camera frame received with timestamp 123456789012345678901234567890 and exposure 1500.0"
    console.setPlainText("\n".join(f"{i} {text}" for i in range(256)))
    app.processEvents()
    block = console.document().begin()
    layout = block.layout()
    assert layout.lineCount() > 1
    for index in range(1, layout.lineCount()):
        start = layout.lineAt(index).textStart()
        assert block.text()[start - 1].isspace()
    console.verticalScrollBar().setValue(160)
    before = console.firstVisibleBlock().text()
    console.appendPlainText("\n".join(text for _ in range(20)))
    app.processEvents()
    assert console.firstVisibleBlock().text() == before


def test_projector_refresh_preserves_assignment(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import projectors

    monkeypatch.setattr(projectors.QGuiApplication, "primaryScreen", lambda: None)
    panel = window.devices.projectors
    panel.request("Refresh displays")
    assert panel.table.rowCount() >= 1
    key = panel.keys[0]
    panel.projectors[key].setCurrentText("Front")
    panel.request("Refresh displays")
    assert panel.keys[panel.table.currentRow()] == key
    assert panel.projectors[key].currentText() == "Front"
    before = list(panel.diagram.outputs)
    panel.enable_controls[key].click()
    assert panel.participation[key] is False
    assert panel.diagram.outputs == before
    panel.request("Refresh displays")
    assert not panel.enable_controls[key].isChecked()
    assert panel.projectors[key].currentText() == "Front"
    window.apply_view(review_view(Phase.RUNNING))
    assert not panel.enable_controls[key].isEnabled()
    panel.discover_displays()  # Runtime startup inventories while edits are locked.
    assert panel.keys and not panel.enable_controls[key].isEnabled()
    assert "×" in panel.table.item(0, 3).text()
    assert panel.diagram.outputs


@pytest.mark.parametrize("unassigned", [False, True])
def test_projector_assignments_survive_restart_and_changed_inventory(
    app: QApplication, tmp_path: Path, unassigned: bool
) -> None:
    from PyQt6.QtCore import QRect, QSettings

    from cephvr.gui.projectors import DisplayInfo

    path = tmp_path / "frontend.ini"
    displays = (
        DisplayInfo("edid:one", "First", "1", QRect(0, 0, 100, 100)),
        DisplayInfo("edid:two", "Second", "2", QRect(100, 0, 100, 100)),
    )
    windows = []

    def open_window(inventory):
        window = DashboardWindow(
            settings=QSettings(str(path), QSettings.Format.IniFormat)
        )
        windows.append(window)
        panel = window.devices.projectors
        panel.review_displays = inventory
        panel.discover_displays()
        panel.apply_view(review_view(Phase.CONFIGURATION))
        return panel

    first = open_window(displays)
    first.projectors["edid:one"].setCurrentText("Front")
    first.projectors["edid:two"].setCurrentText("Left")
    if unassigned:
        first.projectors["edid:one"].setCurrentText("Unassigned")
    expected = dict(first.assignments)
    assert path.exists()  # Retention does not depend on a successful close/Setup.
    retained = path.read_bytes()
    second = open_window(tuple(reversed(displays)))
    assert second.assignments == expected
    assert second.projectors["edid:one"].currentText() == expected["edid:one"]
    assert second.projectors["edid:two"].currentText() == "Left"
    second.review_displays = (displays[1],)
    second.discover_displays()
    assert second.assignments == expected
    if not unassigned:
        assert "Assigned displays unavailable: Front" in second.console.toPlainText()
    second.review_displays = displays
    second.discover_displays()
    assert second.projectors["edid:one"].currentText() == expected["edid:one"]
    assert path.read_bytes() == retained  # Discovery/loading are silent.
    for window in windows:
        window.close()
        window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("editable", [False, True])
@pytest.mark.parametrize("has_profile", [False, True])
def test_saved_projector_assignments_restore_as_managed_drafts(
    app: QApplication, tmp_path: Path, editable: bool, has_profile: bool
) -> None:
    from PyQt6.QtCore import QRect, QSettings
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.control.v1 import types_pb2 as control_pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )
    from cephvr.gui.projectors import DisplayInfo

    path = tmp_path / "frontend.ini"
    first = DashboardWindow(settings=QSettings(str(path), QSettings.Format.IniFormat))
    panel = first.devices.projectors
    panel.review_displays = (
        DisplayInfo("edid:one", "First", "1", QRect(0, 0, 100, 100)),
    )
    panel.discover_displays()
    panel.apply_view(review_view(Phase.CONFIGURATION))
    panel.projectors["edid:one"].setCurrentText("Left")
    second = DashboardWindow(settings=QSettings(str(path), QSettings.Format.IniFormat))
    panel = second.devices.projectors
    panel.review_displays = first.devices.projectors.review_displays
    panel.discover_displays()
    manager = ManagedConfiguration(
        ConfigurationPages(
            second.dashboard,
            second.protocol,
            second.recordings,
            second.devices.cameras,
            panel,
            second.tracking,
        )
    )
    state = control_pb.Snapshot(controller_generation="controller")
    state.session.phase = (
        control_pb.SESSION_PHASE_CONFIGURATION
        if editable
        else control_pb.SESSION_PHASE_RUNNING
    )
    state.configuration.revision = state.configuration_values.revision = 1
    if has_profile:
        state.configuration_values.current.backends.add(
            backend_name="visual_stimulus"
        ).visual_stimulus.display.profile_json = valid_display_json()
    preserved = state.SerializeToString(deterministic=True)
    assert manager.install(state)
    baseline = "Front" if has_profile else "Unassigned"
    expected = "Left" if editable else baseline
    assert panel.assignments.get("edid:one", "Unassigned") == expected
    assert panel.projectors["edid:one"].currentText() == expected
    assert manager.dirty is editable
    assert state.SerializeToString(deterministic=True) == preserved
    assert manager._installed_base == state.configuration_values.current
    assert manager.install(state, force=True)
    assert panel.assignments.get("edid:one", "Unassigned") == baseline
    assert not manager.dirty
    for window in (first, second):
        window.close()
        window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize(
    "raw",
    [
        "broken",
        '{"version":1,"assignments":{"one":"Front","two":"Front"}}',
        '{"version":1,"assignments":{"one":"Front","one":"Left"}}',
        '{"version":2,"assignments":{"one":"Front"}}',
    ],
)
def test_invalid_saved_projector_assignments_are_preserved_and_reported(
    app: QApplication, tmp_path: Path, raw: str
) -> None:
    from PyQt6.QtCore import QSettings

    settings = QSettings(str(tmp_path / "frontend.ini"), QSettings.Format.IniFormat)
    settings.setValue("projectors/assignments", raw)
    settings.sync()
    window = DashboardWindow(settings=settings)
    panel = window.devices.projectors
    assert panel.assignments == {}
    assert "Saved display assignments were not restored" in panel.console.toPlainText()
    assert settings.value("projectors/assignments") == raw
    window.close()
    window.deleteLater()
    app.processEvents()


def test_projector_assignment_save_failure_keeps_draft_and_warns(
    app: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtCore import QRect, QSettings

    from cephvr.gui.projectors import DisplayInfo

    path = tmp_path / "frontend.ini"
    path.mkdir()
    window = DashboardWindow(settings=QSettings(str(path), QSettings.Format.IniFormat))
    panel = window.devices.projectors
    panel.review_displays = (
        DisplayInfo("edid:one", "First", "1", QRect(0, 0, 100, 100)),
    )
    panel.discover_displays()
    panel.apply_view(review_view(Phase.CONFIGURATION))
    panel.projectors["edid:one"].setCurrentText("Front")
    assert panel.assignments["edid:one"] == "Front"
    assert "Display assignments were not saved" in panel.console.toPlainText()
    assert path.is_dir()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_gui_display_number_is_local_and_shared_with_layout(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import projectors

    monkeypatch.setattr(projectors.QGuiApplication, "primaryScreen", lambda: None)
    panel = window.devices.projectors
    panel.request("Refresh displays")
    assert panel.table.item(0, 1).text() == "1"
    assert panel.diagram.outputs[0][0] == "1"
    assert "numbers are independent" in panel.console.toPlainText()
    assert panel.table.horizontalHeaderItem(1).text() == "Display ID"


def test_microcontroller_fixed_signal_tests_and_layout(window: DashboardWindow) -> None:
    panel = window.devices.microcontroller
    panel.port.addItem("COM7", "COM7")
    panel.port.setCurrentIndex(0)
    panel.trial_pin.setText("D3")
    assert panel.trial_pin.text() == "3"
    assert panel.trial_pin.placeholderText() == "2–13"
    assert panel.flip_pin.placeholderText() == "2 or 3"
    panel.flip_pin.setText("4")
    panel.test_buttons["trial-state"].click()
    assert "pin 3, active-high output test; not tested" in panel.console.toPlainText()
    before = panel.console.toPlainText()
    panel.test_buttons["projector-flip"].click()
    assert panel.console.toPlainText() == before
    assert not panel.io.isHidden()
    assert not panel.test_buttons["projector-flip"].isEnabled()
    panel.test_pin("trial-state")
    assert not panel.review_tests
    before = panel.console.toPlainText()
    panel.test_pin("projector-flip")
    assert panel.console.toPlainText() == before


def test_microcontroller_role_outputs_clear_without_changing_camera_use(
    window: DashboardWindow,
) -> None:
    panel = window.devices.microcontroller
    cameras = window.devices.cameras
    cameras.enable_controls[0].setChecked(False)
    panel.can_review = True
    panel.set_role_pin("behavioral", "8")
    assert panel.pin_editors["behavioral"].text() == "8"
    assert not cameras.drafts[0].enabled
    panel.signals.remove("behavioral")
    assert panel.pin_editors["behavioral"].text() == ""
    assert not cameras.drafts[0].enabled
    assert set(panel.pin_editors) == {"behavioral", "tracking", "eye_tracking"}
    assert panel.output_table.isRowHidden(panel.role_rows["behavioral"])
    original = [
        (camera.role, camera.enabled, dict(camera.values)) for camera in cameras.drafts
    ]
    for key in panel.signals.editors:
        panel.signals.remove(key)
    assert panel.input_table.horizontalHeader().isHidden()
    assert panel.output_table.horizontalHeader().isHidden()
    assert not panel.enable_controls["trial-state"].isChecked()
    assert not panel.enable_controls["projector-flip"].isChecked()
    data = panel.snapshots.capture()
    panel.snapshots.restore(data)
    assert panel.input_table.horizontalHeader().isHidden()
    assert panel.output_table.horizontalHeader().isHidden()
    panel.signals.add("behavioral")
    assert not panel.output_table.isRowHidden(panel.role_rows["behavioral"])
    assert not panel.output_table.horizontalHeader().isHidden()
    assert panel.pin_editors["behavioral"].text() == ""
    panel.pin_editors["behavioral"].setText("8")
    panel.signals.add("projector-flip")
    assert not panel.enable_controls["projector-flip"].isChecked()
    assert panel.input_table.horizontalHeader().isHidden()
    assert not panel.io.isHidden()
    assert "projector-flip" not in panel.signals.editors
    assert original == [
        (camera.role, camera.enabled, dict(camera.values)) for camera in cameras.drafts
    ]
    panel.managed_test_key = "behavioral"
    panel.refresh_tests()
    panel.signals.remove("behavioral")
    panel.signals.add("trial-state")
    assert panel.pin_editors["behavioral"].text() == "8"
    assert not panel.trial_pin.text()


def test_microcontroller_file_restores_camera_output_rows_without_commands(
    window, tmp_path
):
    from cephvr.gui.configuration_files import write_snapshot

    panel = window.devices.microcontroller
    cameras = window.devices.cameras
    panel.can_review = True
    cameras.set_participation(0, False)
    panel.set_role_pin("behavioral", "8")
    data = panel.snapshots.capture()
    assert data["version"] == 3
    assert "camera_enabled" not in data
    assert data["camera_pins"]["behavioral"] == "D8"
    path = tmp_path / "signals.json"
    write_snapshot(str(path), data)
    requests = []
    cameras.managed = panel.managed = True
    cameras.enable_requested.connect(lambda *args: requests.append(args))
    panel.save_requested.connect(lambda *args: requests.append(args))
    cameras.drafts[0].enabled = True
    cameras.populate_inventory()
    assert panel.config_files.load_path(str(path))
    assert cameras.drafts[0].enabled
    assert panel.pin_editors["behavioral"].text() == "8"
    assert requests == []
    assert panel.snapshots.capture() == data
    legacy = dict(data, version=2)
    legacy["camera_pins"] = {"camera-1": "D7", "camera-2": ""}
    legacy["camera_enabled"] = {"camera-1": False, "camera-2": True}
    migrated = panel.snapshots.validate(legacy)
    assert migrated["camera_pins"] == {
        "behavioral": "D7",
        "tracking": "",
        "eye_tracking": "",
    }
    assert panel.snapshots.validate(legacy) == migrated
    assert legacy["version"] == 2 and legacy["camera_enabled"]["camera-1"] is False
    panel.snapshots.restore(migrated)
    assert cameras.drafts[0].enabled
    assert panel.pin_editors["behavioral"].text() == "7"
    assert requests == []
    unknown = dict(legacy)
    unknown["camera_pins"] = {"missing-camera": "D4"}
    with pytest.raises(ValueError, match="invalid field inventory"):
        panel.snapshots.validate(unknown)
    full = window.snapshots.capture()
    full["microcontroller"]["version"] = 2
    full["microcontroller"]["camera_pins"] = {"camera-1": "D4", "camera-2": ""}
    full["microcontroller"]["camera_enabled"] = {
        "camera-1": not cameras.drafts[0].enabled,
        "camera-2": not cameras.drafts[1].enabled,
    }
    full["experiment"]["cameras"][0]["role"] = "Eye tracking"
    full["experiment"]["cameras"][1]["role"] = "Behavior cam"
    normalized = window.snapshots.validate(full)
    assert normalized["microcontroller"]["camera_pins"]["eye_tracking"] == "D4"
    assert normalized["microcontroller"]["camera_pins"]["behavioral"] == ""
    assert cameras.drafts[0].enabled


def test_local_review_microcontroller_does_not_open_serial(window, monkeypatch):
    from unittest.mock import Mock

    from cephvr.controller.microcontroller import serial_port

    physical_port = Mock(side_effect=AssertionError("Review must not open serial"))
    monkeypatch.setattr(serial_port, "PySerialPort", physical_port)
    monkeypatch.setattr(window.devices.cameras, "refresh_inventory", lambda: None)
    monkeypatch.setattr(window.devices.projectors, "request", lambda _: None)
    monkeypatch.setattr(window.devices.microcontroller, "scan_ports", lambda: None)
    ReviewControls(window, real_devices=True)
    panel = window.devices.microcontroller
    panel.port.addItem("COM8", "COM8")
    panel.port.setCurrentIndex(0)
    panel.trial_pin.setText("9")
    connections, tests = [], []
    panel.connection_requested.connect(lambda: connections.append(True))
    panel.pin_test_requested.connect(lambda key, start: tests.append((key, start)))
    panel.test_connection_button.click()
    panel.test_buttons["trial-state"].click()
    assert connections == tests == []
    physical_port.assert_not_called()
    assert "no command sent" in panel.console.toPlainText()


def test_simulated_review_inventory_does_not_enumerate_com_ports(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import microcontroller

    def unexpected_inventory():
        raise AssertionError("review mode must not enumerate physical COM ports")

    monkeypatch.setattr(
        microcontroller.QSerialPortInfo, "availablePorts", unexpected_inventory
    )
    reviewed = DashboardWindow(sample=True)
    ReviewControls(reviewed, simulate_projectors=True)
    panel = reviewed.devices.microcontroller
    assert panel.simulated_inventory
    assert panel.port.currentData() == "SIM-UNO"
    assert len(reviewed.devices.projectors.review_displays or ()) == 4
    assert {camera.serial for camera in reviewed.devices.cameras.drafts} == {
        "REVIEW-001",
        "REVIEW-002",
    }
    panel.request("Scan ports")
    assert panel.port.count() == 1
    reviewed.close()
    reviewed.deleteLater()
    app.processEvents()


def test_managed_microcontroller_emits_controller_intents(
    window: DashboardWindow,
) -> None:
    panel = window.devices.microcontroller
    panel.managed = True
    connections: list[bool] = []
    saves: list[
        tuple[str, str, bool, str, bool, str | None, str | None, str | None]
    ] = []
    pin_tests: list[tuple[str, bool]] = []
    panel.connection_requested.connect(lambda: connections.append(True))
    panel.save_requested.connect(lambda *values: saves.append(values))
    panel.pin_test_requested.connect(lambda key, start: pin_tests.append((key, start)))
    window.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            configuration_wired=False,
            phase=Phase.CONFIGURATION,
        )
    )
    panel.set_saved_pins("COM8", "D9", True, "D2", True)
    assert panel.port.isEnabled()
    assert panel.scan_button.isEnabled()
    panel.pin_editors["behavioral"].setText("D10")
    panel.pin_editors["tracking"].setText("D11")
    assert saves == []  # Controller snapshots and unfinished drafts stay silent.
    panel.pin_editors["tracking"].editingFinished.emit()
    panel.test_connection_button.click()
    panel.test_buttons["trial-state"].click()
    panel.set_diagnostic("trial-state", True, 1)
    assert not panel.port.isEnabled()
    assert not panel.scan_button.isEnabled()
    panel.test_buttons["trial-state"].click()

    assert saves == []  # Incomplete/local edits are adopted by the next action.
    assert connections == [True]
    assert pin_tests == [("trial-state", True), ("trial-state", False)]
    assert "no command sent" not in panel.console.toPlainText().splitlines()[-1]
    assert "Save pins" not in [b.text() for b in panel.findChildren(QPushButton)]
    assert not panel.enable_controls["projector-flip"].isEnabled()
    panel.set_diagnostic("trial-state", False, 1)
    assert panel.port.isEnabled()
    assert panel.scan_button.isEnabled()
    assert (
        "output LOW, 1 rising transitions generated by MCU"
        in panel.status_column.hud.toPlainText()
    )
    assert "rising transitions generated by MCU" not in panel.console.toPlainText()
    panel.set_diagnostic("behavioral", False, 59)
    assert (
        "59 rising transitions generated by MCU"
        in panel.status_column.hud.toPlainText()
    )
    assert "rising edges reported" not in panel.console.toPlainText()
    panel.enable_controls["projector-flip"].setChecked(False)
    assert saves == []
    panel.port.addItem("COM9", "COM9")
    panel.port.setCurrentIndex(panel.port.findData("COM9"))
    assert saves == []
    saved_count = len(saves)
    panel.set_saved_pins("COM9", "D9", True, "D2", False)
    assert len(saves) == saved_count
    panel.simulated_inventory = True
    panel.scan_ports()
    assert len(saves) == saved_count
    panel.apply_view(DashboardView(connected=True, has_control=False))
    panel.trial_pin.editingFinished.emit()
    assert len(saves) == saved_count


@pytest.mark.parametrize("row", (0, 1))
def test_managed_camera_enable_waits_for_controller_confirmation(
    window: DashboardWindow,
    row: int,
) -> None:
    panel = window.devices.cameras
    panel.managed = True
    requests: list[tuple[str, bool]] = []
    panel.enable_requested.connect(
        lambda serial, enabled: requests.append((serial, enabled))
    )
    settings_requests = []
    panel.settings_requested.connect(lambda *values: settings_requests.append(values))
    for index, draft in enumerate(panel.drafts):
        draft.values.update(
            trigger_clock="Internal clock",
            trigger_frequency_hz=str(30 * (index + 1)),
            preset=f"camera-{index}.pfs",
        )
    selected = panel.drafts[row]
    selected.enabled = False
    panel.table.selectRow(1 - row)
    panel.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            configuration_wired=False,
            phase=Phase.CONFIGURATION,
        )
    )
    assert panel.enable_controls[row].isEnabled()
    panel.enable_controls[row].click()
    assert panel.selected is selected
    assert panel.role.currentText() == selected.role
    assert panel.preset.text() == selected.values["preset"]
    assert panel.fields["trigger_frequency_hz"].text() == str(30 * (row + 1))
    assert requests == [(selected.serial, True)]
    assert not settings_requests
    assert not selected.enabled
    assert panel.enable_controls[row].isChecked()
    assert not panel.enable_controls[row].isEnabled()
    panel.pending_enable.clear()
    panel.refresh_controls()
    assert not panel.enable_controls[row].isChecked()


def test_managed_camera_enable_accepts_missing_external_input(
    window: DashboardWindow,
) -> None:
    panel = window.devices.cameras
    panel.managed = True
    panel.drafts[0].enabled = False
    panel.drafts[0].values["trigger_clock"] = "External controller"
    requests: list[tuple[str, bool]] = []
    panel.enable_requested.connect(
        lambda serial, enabled: requests.append((serial, enabled))
    )
    panel.apply_view(
        DashboardView(connected=True, has_control=True, configuration_wired=False)
    )
    panel.enable_controls[0].click()
    assert requests == [(panel.drafts[0].serial, True)]
    assert panel.enable_controls[0].isChecked()
    assert not panel.drafts[0].enabled
    assert "awaiting controller confirmation" in panel.console.toPlainText()


def test_managed_camera_settings_submit_pfs_source_and_rate(
    window: DashboardWindow,
    tmp_path: Path,
) -> None:
    panel = window.devices.cameras
    panel.managed = True
    submissions: list[tuple[str, str, str, str, str]] = []
    panel.settings_requested.connect(lambda *values: submissions.append(values))
    panel.preset_import_requested.connect(lambda *values: submissions.append(values))
    panel.apply_view(
        DashboardView(connected=True, has_control=True, configuration_wired=False)
    )
    assert panel.preset_field.isEnabled()
    assert panel.trigger_source.isEnabled()
    assert panel.role.isEnabled()
    panel.selected.values.update(
        {
            "trigger_clock": "External controller",
            "trigger_source": "Line1",
            "preset": "C:/camera/behavior.pfs",
            "trigger_frequency_hz": "30.0",
        }
    )
    panel.load_selected()
    assert submissions == []
    panel.fields["trigger_frequency_hz"].editingFinished.emit()
    assert submissions == [
        (
            "REVIEW-001",
            "External controller",
            "Line1",
            "C:/camera/behavior.pfs",
            "30.0",
        )
    ]
    assert "Save camera settings" not in [
        b.text() for b in panel.findChildren(QPushButton)
    ]
    submitted_count = len(submissions)
    panel.trigger_source.setCurrentText("Internal clock")
    assert panel.snapshot_draft
    assert len(submissions) == submitted_count
    preset = tmp_path / "external.pfs"
    preset.write_text(
        "# GenApi persistence file\nTriggerSelector\tFrameStart\n"
        "TriggerMode\tOn\nTriggerSource\tLine3\n"
    )
    submitted_count = len(submissions)
    panel.preset_field.select_path(str(preset))
    assert panel.snapshot_draft
    assert len(submissions) == submitted_count
    submitted_count = len(submissions)
    panel.fields["trigger_frequency_hz"].setText("0.01")
    panel.fields["trigger_frequency_hz"].editingFinished.emit()
    assert len(submissions) == submitted_count
    submitted_count = len(submissions)
    panel.apply_view(DashboardView(connected=True, has_control=False))
    panel.fields["trigger_frequency_hz"].editingFinished.emit()
    assert len(submissions) == submitted_count


@pytest.mark.asyncio
async def test_bridge_submits_configuration_and_waits_for_exact_version() -> None:
    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    current = pb.Snapshot(controller_generation=generation)
    current.configuration.revision = 8
    current.configuration_values.revision = 8
    current.configuration_values.current.subject = "subject"
    accepted = pb.Snapshot(controller_generation=generation)
    accepted.configuration.revision = 9
    accepted.configuration_values.revision = 9
    accepted.configuration_values.current.subject = "updated subject"
    proposal = pb.ExperimentConfiguration()
    proposal.CopyFrom(accepted.configuration_values.current)
    requests: list[tuple[str, object]] = []
    command_id = str(uuid4())

    class Client:
        snapshot = current
        rpc_timeout_s = 1

        def operator_command(self) -> rpc.OperatorCommand:
            return rpc.OperatorCommand(
                operator=pb.OperatorContext(command_id=command_id),
                controller_generation=generation,
            )

        async def _admit(self, method: str, request: object) -> pb.CommandAdmission:
            requests.append((method, request))
            return pb.CommandAdmission(
                command_id=command_id, result=pb.COMMAND_RESULT_ACCEPTED
            )

        async def wait_result(self, _command_id: str) -> CommandOutcome:
            return CommandOutcome(command_id, True, True)

        async def _wait(self, _predicate: object) -> pb.Snapshot:
            return accepted

    bridge = ControllerBridge(Principal("gui", generation, "token"), 50051, 1024, (0,))
    bridge._controller_generation = generation
    accepted_versions: list[int] = []
    finished: list[tuple[str, str, str, str]] = []
    bridge.configuration_accepted.connect(
        lambda revision, _edit_serial: accepted_versions.append(revision)
    )
    bridge.operation_finished.connect(lambda *args: finished.append(args))
    assert await bridge._submit_configuration(
        Client(),
        {
            "base_revision": 8,
            "proposal": proposal.SerializeToString(deterministic=True),
        },
    )
    assert len(requests) == 1
    method, request = requests[0]
    assert method == "UpdateConfiguration"
    assert request.expected_revision == 8
    assert request.proposed.subject == "updated subject"
    assert accepted_versions == [9]
    assert finished[-1][2] == "completed"


@pytest.mark.asyncio
async def test_bridge_accepts_unchanged_configuration_at_same_revision() -> None:
    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 8
    state.configuration_values.revision = 8
    state.configuration_values.current.subject = "unchanged"
    proposal = pb.ExperimentConfiguration()
    proposal.CopyFrom(state.configuration_values.current)
    command_id = str(uuid4())

    class Client:
        snapshot = state
        rpc_timeout_s = 1

        def operator_command(self) -> rpc.OperatorCommand:
            return rpc.OperatorCommand(
                operator=pb.OperatorContext(command_id=command_id),
                controller_generation=generation,
            )

        async def _admit(self, method: str, _request: object) -> pb.CommandAdmission:
            assert method == "UpdateConfiguration"
            return pb.CommandAdmission(
                command_id=command_id, result=pb.COMMAND_RESULT_ACCEPTED
            )

        async def wait_result(self, _command_id: str) -> CommandOutcome:
            return CommandOutcome(command_id, True, True)

        async def _wait(self, predicate: object) -> pb.Snapshot:
            assert callable(predicate) and predicate(state)
            return state

    bridge = ControllerBridge(Principal("gui", generation, "token"), 50051, 1024, (0,))
    bridge._controller_generation = generation
    accepted: list[int] = []
    finished: list[tuple[str, str, str, str]] = []
    bridge.configuration_accepted.connect(
        lambda revision, _edit_serial: accepted.append(revision)
    )
    bridge.operation_finished.connect(lambda *args: finished.append(args))
    assert await bridge._submit_configuration(
        Client(),
        {"base_revision": 8, "proposal": proposal.SerializeToString()},
    )
    assert accepted == [8]
    assert finished[-1][2] == "completed"


def test_managed_configuration_action_plan_preserves_edits_outside_editable_phases() -> (
    None
):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_configuration_transport import configuration_update_plan

    current = pb.ExperimentConfiguration(subject="accepted")
    unchanged = pb.ExperimentConfiguration(subject="accepted")
    changed = pb.ExperimentConfiguration(subject="local draft")
    assert (
        configuration_update_plan(unchanged, current, pb.SESSION_PHASE_ENDED, "Setup")
        == "direct"
    )
    assert (
        configuration_update_plan(
            changed, current, pb.SESSION_PHASE_ENDED, "New session"
        )
        == "direct_preserve"
    )
    assert (
        configuration_update_plan(
            changed, current, pb.SESSION_PHASE_RUNNING, "save_configuration_history"
        )
        == "preserve"
    )
    assert (
        configuration_update_plan(changed, current, pb.SESSION_PHASE_READY, "Setup")
        == "submit"
    )


@pytest.mark.asyncio
async def test_managed_gui_setup_captures_exact_accepted_configuration_for_bridge(
    window: DashboardWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from PyQt6.QtCore import QObject

    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.main import ManagedGui
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 2
    state.configuration_values.revision = 2
    state.configuration_values.current.subject = "accepted"
    client_id = str(uuid4())
    manager = SimpleNamespace(
        stale=False,
        revision=2,
        edit_serial=11,
        collect=lambda base: pb.ExperimentConfiguration.FromString(
            base.SerializeToString()
        ),
    )
    gui = ManagedGui.__new__(ManagedGui)
    QObject.__init__(gui)
    gui.state = state
    gui.configuration = manager
    gui._connection_epoch = 3
    bridge = ControllerBridge(Principal("gui", client_id, "token"), 50051, 1024, (0,))
    bridge._loop = asyncio.get_running_loop()
    bridge._queue = asyncio.PriorityQueue(maxsize=bridge._MAX_PENDING + 1)
    bridge._connected = True
    bridge._connection_epoch = 3
    bridge._controller_generation = generation
    bridge._configuration_lock = asyncio.Lock()
    gui.bridge = bridge
    gui.window = window
    gui.confirm_discard_local_draft = lambda: True

    window.devices.projectors.keys = ["identified-projector"]
    monkeypatch.setattr(window.devices.projectors, "discover_displays", lambda: None)

    gui.request_dashboard_action("Setup")
    await asyncio.sleep(0)
    _, _, epoch, queued_generation, action, options = bridge._queue.get_nowait()
    assert action == "Setup"
    assert epoch == 3 and queued_generation == generation
    assert options["expected_revision"] == 2
    assert options[
        "expected_configuration"
    ] == state.configuration_values.current.SerializeToString(deterministic=True)

    command_id = str(uuid4())
    calls: list[str] = []

    class Client:
        snapshot = state

        def operator_command(self):
            from cephvr.control.v1 import services_pb2 as rpc

            return rpc.OperatorCommand(
                operator=pb.OperatorContext(command_id=command_id),
                controller_generation=generation,
            )

        async def execute(self, method, *_args, **_kwargs):
            calls.append(method)
            return CommandOutcome(command_id, True, True)

        async def wait_result(self, _command):
            return CommandOutcome(command_id, True, True)

    await bridge._dispatch_guarded(Client(), action, options, epoch, queued_generation)
    assert calls == ["Setup"]


def test_managed_gui_immutable_phase_actions_bypass_invalid_collection(
    window: DashboardWindow,
) -> None:
    from unittest.mock import Mock

    from PyQt6.QtCore import QObject

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui

    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.session.phase = pb.SESSION_PHASE_ENDED
    state.configuration.revision = 7
    state.configuration_values.revision = 7
    state.configuration_values.current.subject = "accepted"
    requests: list[str] = []
    collect = Mock(side_effect=ValueError("unfinished epoch duration"))
    manager = SimpleNamespace(
        stale=True,
        dirty=True,
        revision=6,
        collect=collect,
    )
    gui = ManagedGui.__new__(ManagedGui)
    QObject.__init__(gui)
    gui.state = state
    gui.configuration = manager
    gui.close_pending = False
    gui.history = SimpleNamespace(save=lambda: None)
    gui.bridge = SimpleNamespace(
        request=lambda action, **_kwargs: requests.append(action) or True
    )
    gui.window = window
    gui.confirm_discard_local_draft = lambda: True

    gui.request_dashboard_action("New session")
    assert requests == ["New session"]
    assert collect.call_count == 0
    gui.request_close()
    assert requests == ["New session", "save_configuration_history"]
    assert gui.close_pending
    assert collect.call_count == 0


@pytest.mark.asyncio
async def test_controller_bridge_setup_validates_captured_version_under_dispatch_lock() -> (
    None
):
    import asyncio

    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 4
    state.configuration_values.revision = 4
    state.configuration_values.current.subject = "accepted"
    command_id = str(uuid4())
    requests: list[str] = []

    class Client:
        snapshot = state

        def operator_command(self) -> rpc.OperatorCommand:
            return rpc.OperatorCommand(
                operator=pb.OperatorContext(command_id=command_id),
                controller_generation=generation,
            )

        async def execute(
            self, method: str, *_args: object, **_kwargs: object
        ) -> CommandOutcome:
            requests.append(method)
            return CommandOutcome(command_id, True, True)

        async def wait_result(self, _command_id: str) -> CommandOutcome:
            return CommandOutcome(command_id, True, True)

    bridge = ControllerBridge(Principal("gui", generation, "token"), 50051, 1024, (0,))
    bridge._connection_epoch = 1
    bridge._controller_generation = generation
    bridge._configuration_lock = asyncio.Lock()
    failures: list[tuple[str, bool, str]] = []
    bridge.command_finished.connect(lambda *args: failures.append(args))
    await bridge._dispatch_guarded(
        Client(),
        "Setup",
        {
            "expected_revision": 3,
            "expected_configuration": state.configuration_values.current.SerializeToString(
                deterministic=True
            ),
        },
        1,
        generation,
    )
    assert requests == []
    assert failures and "captured configuration version changed" in failures[-1][2]
    await bridge._dispatch_guarded(
        Client(),
        "Setup",
        {
            "expected_revision": 4,
            "expected_configuration": state.configuration_values.current.SerializeToString(
                deterministic=True
            ),
        },
        1,
        generation,
    )
    assert requests == ["Setup"]


@pytest.mark.asyncio
async def test_controller_bridge_submits_then_setup_uses_exact_accepted_version() -> (
    None
):
    import asyncio

    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    before = pb.Snapshot(controller_generation=generation)
    before.configuration.revision = 4
    before.configuration_values.revision = 4
    before.configuration_values.current.subject = "before"
    after = pb.Snapshot(controller_generation=generation)
    after.configuration.revision = 5
    after.configuration_values.revision = 5
    after.configuration_values.current.subject = "accepted proposal"
    command_id = str(uuid4())
    calls: list[str] = []

    class Client:
        snapshot = before
        rpc_timeout_s = 1

        def operator_command(self) -> rpc.OperatorCommand:
            return rpc.OperatorCommand(
                operator=pb.OperatorContext(command_id=command_id),
                controller_generation=generation,
            )

        async def _admit(self, method: str, _request: object) -> pb.CommandAdmission:
            calls.append(method)
            return pb.CommandAdmission(
                command_id=command_id, result=pb.COMMAND_RESULT_ACCEPTED
            )

        async def wait_result(self, _command_id: str) -> CommandOutcome:
            return CommandOutcome(command_id, True, True)

        async def _wait(self, predicate: object) -> pb.Snapshot:
            assert callable(predicate) and predicate(after)
            self.snapshot = after
            return after

        async def execute(
            self, method: str, *_args: object, **_kwargs: object
        ) -> CommandOutcome:
            calls.append(method)
            return CommandOutcome(str(uuid4()), True, True)

    proposal = pb.ExperimentConfiguration(subject="accepted proposal")
    client = Client()
    bridge = ControllerBridge(Principal("gui", generation, "token"), 50051, 1024, (0,))
    bridge._connection_epoch = 1
    bridge._controller_generation = generation
    bridge._configuration_lock = asyncio.Lock()
    accepted: list[tuple[int, int]] = []
    bridge.configuration_accepted.connect(lambda *args: accepted.append(args))
    await bridge._dispatch_guarded(
        client,
        "submit_configuration",
        {
            "base_revision": 4,
            "proposal": proposal.SerializeToString(deterministic=True),
            "edit_serial": 19,
            "after_action": "Setup",
        },
        1,
        generation,
    )
    assert calls == ["UpdateConfiguration", "Setup"]
    assert accepted == [(5, 19)]


def test_managed_display_calibration_requests_use_repository_relative_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_display_operations import (
        capture_display_calibration_intent,
        close_display_calibration_request,
        open_display_calibration_request,
    )

    generation = str(uuid4())
    client_id = str(uuid4())
    root = tmp_path / "repository-assets"
    monkeypatch.setattr(
        "cephvr.gui.managed_display_operations.calibration_asset_root", lambda: root
    )
    runtime = tmp_path / "runtime-data"
    monkeypatch.setattr(
        "cephvr.gui.managed_display_operations.calibration_runtime_root",
        lambda _view: runtime,
    )
    (runtime / "calibration").mkdir(parents=True)
    calibration = root / "calibration"
    calibration.mkdir(parents=True)
    profile = runtime / "calibration" / "diagnostic_display_profile.json"
    arena = calibration / "frame_grid.glb"
    profile.write_text("{}", encoding="utf-8")
    arena.write_bytes(b"glb")
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 9
    state.configuration_values.revision = 9
    state.configuration_values.current.asset_root = str(tmp_path / "external-media")
    state.control.holder_client_id = client_id
    state.control.control_generation = "lease-1"

    class Client:
        snapshot = state

        def operator_command(self) -> rpc.OperatorCommand:
            return rpc.OperatorCommand(
                operator=pb.OperatorContext(
                    client_id=client_id,
                    control_generation="lease-1",
                    command_id=str(uuid4()),
                ),
                controller_generation=generation,
            )

    intent = capture_display_calibration_intent(state, arena_path=str(arena))
    request = open_display_calibration_request(Client(), **intent)
    assert request.expected_configuration_revision == 9
    assert (
        request.profile_asset_reference == "calibration/diagnostic_display_profile.json"
    )
    assert request.arena_asset_reference == "calibration/frame_grid.glb"
    assert request.command.controller_generation == generation
    assert request.expected_profile_sha256
    assert request.expected_arena_sha256

    state.configuration_values.current.ClearField("asset_root")
    assert open_display_calibration_request(
        Client(), **intent
    ).arena_asset_reference == ("calibration/frame_grid.glb")
    profile.write_text('{"changed":true}', encoding="utf-8")
    from cephvr.client.session import ClientError

    with pytest.raises(ClientError, match="changed before command admission"):
        open_display_calibration_request(Client(), **intent)
    profile.write_text("{}", encoding="utf-8")

    state.visual_stimulus_display.calibration.diagnostic_id = "diag-1"
    state.visual_stimulus_display.calibration.controller_generation = generation
    state.visual_stimulus_display.calibration.configuration_revision = 9
    close = close_display_calibration_request(
        Client(), expected_revision=9, diagnostic_id="diag-1"
    )
    assert close.expected_configuration_revision == 9
    assert close.diagnostic_id == "diag-1"

    outside = tmp_path / "outside.glb"
    outside.write_bytes(b"outside")
    with pytest.raises(
        ValueError, match="outside the repository calibration asset root"
    ):
        capture_display_calibration_intent(state, arena_path=str(outside))


def test_projector_first_run_profile_import_is_reachable_and_collectable(
    window: DashboardWindow, tmp_path: Path
) -> None:
    import json

    from cephvr.gui.projector_codec import display_document
    from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_pb

    panel = window.devices.projectors
    panel.can_review = True
    path = tmp_path / "display-profile.json"
    path.write_text(
        json.dumps(
            {
                "outputs": [
                    {
                        "output_id": "front-output",
                        "device_identity": "monitor-front",
                        "width_px": 1920,
                        "height_px": 1080,
                        "refresh_numerator": 60,
                        "refresh_denominator": 1,
                        "rgb_bits_per_channel": 8,
                    }
                ],
                "mappings": [{"surface_id": "front", "output_id": "front-output"}],
                "presentation_mode": "all_outputs_vsync",
                "photodiode_enabled": False,
            }
        ),
        encoding="utf-8",
    )

    # The file's physical monitor ID must not replace this rig's selection.
    panel.assignments["current-front"] = "Front"
    panel._profile_outputs = [
        {
            "output_id": "current-output",
            "device_identity": "current-front",
            "width_px": 1920,
            "height_px": 1080,
            "refresh_numerator": 60,
            "refresh_denominator": 1,
            "rgb_bits_per_channel": 8,
        }
    ]
    panel.calibration_files.load_path(str(path))
    submitted = panel.configuration_for_submit(visual_pb.DisplayConfiguration())
    document = display_document(submitted)
    assert document["outputs"][0]["device_identity"] == "current-front"
    assert document["mappings"][0]["output_id"] == "current-output"
    assert document["mappings"][0]["surface_id"] == "front"
    assert document["photodiode_enabled"] is False
    assert panel.calibration_files.profile is not None
    assert "outputs" not in panel.calibration_files.snapshot()["screen_profile"]


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [True, False])
async def test_managed_bridge_reads_and_updates_spikeglx_inventory_exactly(
    succeeded: bool,
) -> None:
    import asyncio

    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal
    from cephvr.synchronization.v1 import spikeglx_pb2

    generation = str(uuid4())
    client_id = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 6
    state.configuration_values.revision = 6
    state.control.holder_client_id = client_id
    state.control.control_generation = "lease-1"
    command_id = str(uuid4())
    get_requests: list[rpc.SpikeGLXInventoryRequest] = []
    update_requests: list[rpc.SpikeGLXInventoryUpdateRequest] = []

    class Stub:
        async def GetSpikeGLXInventory(self, request: object, **_kwargs: object):
            assert isinstance(request, rpc.SpikeGLXInventoryRequest)
            get_requests.append(request)
            return rpc.SpikeGLXInventorySnapshot(
                configuration_revision=6,
                file_sha256="digest",
                backend_enabled=True,
                address="127.0.0.1",
                command_port=4142,
            )

    class Client:
        snapshot = state
        stub = Stub()
        principal = Principal("gui", client_id, "token")
        rpc_timeout_s = 1

        def operator_command(self) -> rpc.OperatorCommand:
            return rpc.OperatorCommand(
                operator=pb.OperatorContext(
                    client_id=client_id,
                    control_generation="lease-1",
                    command_id=command_id,
                ),
                controller_generation=generation,
            )

        async def execute(
            self, method: str, request: object, *, wait: bool
        ) -> CommandOutcome:
            assert method == "UpdateSpikeGLXInventory" and not wait
            assert isinstance(request, rpc.SpikeGLXInventoryUpdateRequest)
            update_requests.append(request)
            return CommandOutcome(command_id, False, None)

        async def wait_result(self, _command_id: str) -> CommandOutcome:
            return CommandOutcome(
                command_id,
                True,
                succeeded,
                failure="<unknown> write failed" if not succeeded else "",
            )

    bridge = ControllerBridge(Client.principal, 50051, 1024, (0,))
    bridge._connection_epoch = 3
    bridge._controller_generation = generation
    bridge._configuration_lock = asyncio.Lock()
    received: list[tuple[int, str, bytes]] = []
    bridge.spikeglx_inventory_received.connect(lambda *args: received.append(args))
    await bridge._dispatch(
        Client(),
        "get_spikeglx_inventory",
        {"expected_revision": 6, "dispatch_identity": (3, generation)},
    )
    assert len(get_requests) == 1
    assert get_requests[0].expected_configuration_revision == 6
    assert received[0][:2] == (3, generation)
    assert (
        rpc.SpikeGLXInventorySnapshot.FromString(received[0][2]).file_sha256 == "digest"
    )

    from cephvr.client.session import ClientError

    state.session.phase = pb.SESSION_PHASE_SETTING_UP
    with pytest.raises(ClientError, match="deferred until Configuration or Ready"):
        await bridge._dispatch(
            Client(),
            "get_spikeglx_inventory",
            {"expected_revision": 6, "dispatch_identity": (3, generation)},
        )
    assert len(get_requests) == 1
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION

    channel = spikeglx_pb2.PulseChannel(role=spikeglx_pb2.PULSE_ROLE_CUSTOM)
    channel.source_id = "custom-trigger"
    admitted: list[tuple[str, str]] = []
    finished: list[tuple[str, str, str, str]] = []
    generic_finished: list[tuple[str, bool, str]] = []
    bridge.command_admitted.connect(lambda *args: admitted.append(args))
    bridge.operation_finished.connect(lambda *args: finished.append(args))
    bridge.command_finished.connect(lambda *args: generic_finished.append(args))
    await bridge._dispatch(
        Client(),
        "spikeglx_inventory_update",
        {
            "expected_revision": 6,
            "expected_file_sha256": "digest",
            "pulse_channels": (channel.SerializeToString(deterministic=True),),
        },
    )
    assert len(update_requests) == 1
    assert update_requests[0].expected_configuration_revision == 6
    assert update_requests[0].pulse_channels[0].source_id == "custom-trigger"
    assert admitted == [("spikeglx_inventory_update", command_id)]
    assert finished[-1][2] == ("completed" if succeeded else "failed")
    if not succeeded:
        assert "<unknown> write failed" in finished[-1][3]
    assert generic_finished == []


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeded", [True, False])
async def test_managed_spikeglx_pairing_updates_only_session_flag(
    succeeded: bool,
) -> None:
    from cephvr.client.session import ClientError, CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_device_commands import dispatch_device_action
    from cephvr.shared.auth import Principal

    state = pb.Snapshot()
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 7
    state.configuration_values.current.backends.add(
        backend_name="synchronization", enabled=False
    )
    state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    original = state.configuration_values.current.SerializeToString()
    requests = []

    class Client:
        snapshot = state

        def operator_command(self):
            return rpc.OperatorCommand()

        async def execute(self, method, request):
            assert method == "UpdateConfiguration"
            requests.append(request)
            return CommandOutcome("pairing", True, succeeded, failure="rejected")

    principal = Principal("gui", str(uuid4()), "token")
    options = {"expected_revision": 7, "enabled": True}
    if succeeded:
        result = await dispatch_device_action(
            Client(), "set_spikeglx_enabled", options, principal
        )
        assert result == (True, "Pairing enabled")
    else:
        with pytest.raises(ClientError, match="rejected"):
            await dispatch_device_action(
                Client(), "set_spikeglx_enabled", options, principal
            )
    assert len(requests) == 1
    expected = pb.ExperimentConfiguration.FromString(original)
    expected.backends[0].enabled = True
    assert requests[0].proposed == expected
    assert requests[0].expected_revision == 7
    assert state.configuration_values.current.SerializeToString() == original
    for revision, phase, error in (
        (8, pb.SESSION_PHASE_CONFIGURATION, "revision changed"),
        (7, pb.SESSION_PHASE_RUNNING, "only change in Configuration"),
    ):
        state.configuration.revision = revision
        state.session.phase = phase
        with pytest.raises(ClientError, match=error):
            await dispatch_device_action(
                Client(), "set_spikeglx_enabled", options, principal
            )
        assert len(requests) == 1


@pytest.mark.asyncio
async def test_spikeglx_pairing_bridge_publishes_accepted_device_revision() -> None:
    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = state.configuration_values.revision = 7
    state.configuration_values.current.backends.add(
        backend_name="synchronization", enabled=False
    )

    class Client:
        snapshot = state

        def operator_command(self):
            return rpc.OperatorCommand()

        async def execute(self, method, request):
            assert method == "UpdateConfiguration"
            state.configuration_values.current.CopyFrom(request.proposed)
            state.configuration.revision = state.configuration_values.revision = 8
            return CommandOutcome("pairing", True, True)

    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
    )
    accepted = []
    finished = []
    bridge.device_configuration_accepted.connect(
        lambda revision, raw: accepted.append((revision, pb.Snapshot.FromString(raw)))
    )
    bridge.command_finished.connect(lambda *result: finished.append(result))
    await bridge._dispatch(
        Client(), "set_spikeglx_enabled", {"enabled": True, "expected_revision": 7}
    )
    assert len(accepted) == 1
    assert accepted[0][0] == 7
    assert accepted[0][1].configuration.revision == 8
    assert accepted[0][1].configuration_values.current.backends[0].enabled
    assert finished == [("set_spikeglx_enabled", True, "Pairing enabled")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,options",
    [
        ("set_camera_enabled", {"serial": "eye", "enabled": True}),
        ("assign_camera_role", {"serial": "eye", "role": "Eye tracking"}),
        (
            "save_camera_settings",
            {
                "serial": "eye",
                "clock": "External controller",
                "source": "Line1",
                "preset": "",
                "rate": "60",
            },
        ),
        (
            "save_mcu_pins",
            {
                "port": "COM8",
                "trial_pin": "12",
                "trial_enabled": True,
                "flip_pin": "",
                "flip_enabled": False,
                "behavioral_pin": "11",
                "tracking_pin": "10",
                "eye_tracking_pin": "9",
            },
        ),
        ("add_mcu_output", {"role": "eye_tracking", "pin": "9"}),
    ],
)
@pytest.mark.parametrize("rejected", [False, True])
async def test_device_settings_acknowledgement_keeps_camera_connect_current(
    window: DashboardWindow, action, options, rejected
) -> None:
    from cephvr.client.session import ClientError, CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = state.configuration_values.revision = 7
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    settings.eye_tracking.device.device_id = "eye"
    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
            window.devices.microcontroller,
        )
    )
    assert manager.install(state)
    window.dashboard.subject_id.setText("unsent subject")
    manager.dirty = True
    gui = SimpleNamespace(state=state, configuration=manager, window=window)
    acknowledgements = []

    def accepted(base_revision, payload):
        acknowledged = pb.Snapshot.FromString(payload)
        acknowledgements.append(acknowledged)
        assert manager.note_device_revision(acknowledged, base_revision)

    class Client:
        snapshot = state

        def operator_command(self):
            return rpc.OperatorCommand()

        async def execute(self, method, request):
            assert method == "UpdateConfiguration"
            assert request.expected_revision == 7
            if not rejected:
                state.configuration_values.current.CopyFrom(request.proposed)
            state.configuration.revision = state.configuration_values.revision = 8
            # A streamed snapshot may arrive before the operation's acknowledgement.
            assert not manager.install(state)
            return CommandOutcome("device", True, not rejected, failure="rejected")

    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
    )
    bridge.device_configuration_accepted.connect(accepted)
    if rejected:
        with pytest.raises(ClientError, match="rejected"):
            await bridge._dispatch(Client(), action, options)
        assert not acknowledgements and manager.stale and manager.revision == 7
        with pytest.raises(ValueError, match="configuration changed"):
            ManagedGui.camera_submission_options(gui, "eye")
    else:
        await bridge._dispatch(Client(), action, options)
        assert len(acknowledgements) == 1
        assert manager.revision == 8 and not manager.stale
        assert ManagedGui.camera_submission_options(gui, "eye")["base_revision"] == 8
    assert manager.dirty and window.dashboard.subject_id.text() == "unsent subject"


@pytest.mark.parametrize("queued", [True, False])
def test_managed_spikeglx_pairing_waits_for_confirmation(
    window: DashboardWindow, queued: bool
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_display import ManagedDisplayOperations
    from cephvr.gui.view import DashboardView, Phase

    state = pb.Snapshot()
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 7
    backend = state.configuration_values.current.backends.add(
        backend_name="synchronization", enabled=False
    )
    sent = []

    def send(action, **options):
        sent.append((action, options))
        return queued

    panel = window.devices.spikeglx
    save_spikeglx = window.recordings.spikeglx
    assert save_spikeglx is panel.pairing
    assert window.recordings.isAncestorOf(save_spikeglx)
    assert not panel.isAncestorOf(save_spikeglx)
    assert window.recordings.spikeglx_label.text() == "Save spikeglx"
    assert save_spikeglx.accessibleName() == "Save spikeglx"
    ops = ManagedDisplayOperations(
        window.devices.projectors,
        panel,
        snapshot=lambda: state,
        connection_identity=lambda: None,
        send=send,
    )
    panel.pairing_requested.connect(ops.submit_pairing)
    view = DashboardView(connected=True, has_control=True)
    panel.apply_view(view)
    ops.install_pairing()
    save_spikeglx.click()
    assert sent == [("set_spikeglx_enabled", {"enabled": True, "expected_revision": 7})]
    assert not panel.pairing.isChecked()
    assert panel.pairing_pending == queued
    assert panel.pairing.isEnabled() != queued
    panel.apply_view(view)
    assert panel.pairing.isEnabled() != queued
    backend.enabled = True
    ops.install_pairing()
    assert panel.pairing.isChecked()
    assert len(sent) == 1
    ops.pairing_finished()
    assert panel.pairing.isEnabled()
    save_spikeglx.click()
    assert sent[-1] == (
        "set_spikeglx_enabled",
        {"enabled": False, "expected_revision": 7},
    )
    assert save_spikeglx.isChecked()
    backend.enabled = False
    ops.install_pairing()
    ops.pairing_finished()
    assert not save_spikeglx.isChecked()
    for locked in (
        DashboardView(),
        DashboardView(connected=True),
        DashboardView(connected=True, has_control=True, phase=Phase.READY),
    ):
        panel.apply_view(locked)
        assert not panel.pairing.isEnabled()


def test_managed_spikeglx_inventory_installs_read_only_host_settings(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_display import ManagedDisplayOperations
    from cephvr.gui.view import DashboardView, Phase, review_view

    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 3
    state.configuration_values.revision = 3
    state.configuration_values.current.backends.add(
        backend_name="synchronization", enabled=True
    )
    current = SimpleNamespace(state=state, identity=(9, generation))
    operations = ManagedDisplayOperations(
        window.devices.projectors,
        window.devices.spikeglx,
        snapshot=lambda: current.state,
        connection_identity=lambda: current.identity,
        send=lambda *_args, **_kwargs: True,
    )

    response = rpc.SpikeGLXInventorySnapshot(
        configuration_revision=3,
        file_sha256="saved-inventory-digest",
        backend_enabled=True,
        address="169.254.240.108",
        command_port=4142,
    )
    operations.install_inventory(9, generation, response.SerializeToString())

    panel = window.devices.spikeglx
    panel.apply_view(DashboardView(connected=True, has_control=True))
    assert panel.pairing.isChecked()
    assert panel.pairing.isEnabled()
    assert panel.address.text() == "169.254.240.108"
    assert panel.address.isReadOnly()
    assert panel.command_port.text() == "4142"
    assert panel.command_port.isReadOnly()
    assert "synchronization_config.toml" in panel.pairing.toolTip()
    previous_digest = panel.inventory_file_sha256
    current.state.configuration.revision = 4
    operations.install_inventory(9, generation, response.SerializeToString())
    assert panel.inventory_file_sha256 == previous_digest
    assert "does not match" in panel.console.toPlainText()
    panel.apply_view(review_view(Phase.CONFIGURATION))
    assert panel.pairing.isEnabled()


@pytest.mark.asyncio
async def test_queued_calibration_rejects_revision_and_asset_drift() -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 9
    state.configuration_values.revision = 9
    state.configuration_values.current.asset_root = "/unused"

    class Client:
        snapshot = state

    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
    )
    bridge._connection_epoch = 4
    bridge._controller_generation = generation
    finished: list[tuple[str, bool, str]] = []
    bridge.command_finished.connect(
        lambda action, ok, message: finished.append((action, ok, message))
    )

    await bridge._dispatch_guarded(
        Client(),
        "open_display_calibration",
        {
            "arena_path": "/outside/arena.glb",
            "expected_revision": 8,
            "expected_profile_sha256": "profile-digest",
            "expected_arena_sha256": "arena-digest",
        },
        4,
        generation,
    )
    assert finished and finished[-1][0] == "open_display_calibration"
    assert not finished[-1][1]
    assert "older configuration" in finished[-1][2]


@pytest.mark.asyncio
async def test_queued_calibration_close_rejects_changed_diagnostic_identity() -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 9
    state.configuration_values.revision = 9
    evidence = state.visual_stimulus_display.calibration
    evidence.controller_generation = generation
    evidence.configuration_revision = 9
    evidence.diagnostic_id = "current-diagnostic"

    class Client:
        snapshot = state

    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
    )
    bridge._connection_epoch = 4
    bridge._controller_generation = generation
    finished: list[tuple[str, bool, str]] = []
    bridge.command_finished.connect(
        lambda action, ok, message: finished.append((action, ok, message))
    )

    await bridge._dispatch_guarded(
        Client(),
        "close_display_calibration",
        {"expected_revision": 9, "diagnostic_id": "clicked-diagnostic"},
        4,
        generation,
    )
    assert finished and finished[-1][0] == "close_display_calibration"
    assert not finished[-1][1]
    assert "stale" in finished[-1][2]


def test_inventory_required_roles_follow_the_accepted_active_configuration() -> None:
    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_display_operations import required_inventory_roles
    from cephvr.synchronization.v1 import spikeglx_pb2

    configuration = pb.ExperimentConfiguration()
    acquisition = configuration.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    acquisition.behavioral.enabled = True
    acquisition.behavioral.device.frame_timing = (
        camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    )
    acquisition.tracking.enabled = True
    acquisition.tracking.device.frame_timing = camera_pb2.FRAME_TIMING_FREE_RUNNING
    acquisition.eye_tracking.enabled = True
    acquisition.eye_tracking.device.frame_timing = (
        camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    )
    vs = configuration.backends.add(
        backend_name="visual_stimulus", enabled=True
    ).visual_stimulus
    vs.display.profile_json = '{"photodiode_enabled":true}'

    assert required_inventory_roles(configuration) == frozenset(
        {
            spikeglx_pb2.PULSE_ROLE_BEHAVIORAL_CAMERA,
            spikeglx_pb2.PULSE_ROLE_PHOTODIODE,
            spikeglx_pb2.PULSE_ROLE_EYE_TRACKING_CAMERA,
        }
    )


@pytest.mark.asyncio
async def test_tracking_diagnostic_requests_keep_preview_and_draft_identity() -> None:
    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    generation = str(uuid4())
    client_id = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 11
    state.configuration_values.revision = 11
    state.acquisition_devices.tracking.preview_running = True
    state.acquisition_devices.tracking.preview_run_id = "preview-11"
    state.acquisition_devices.tracking.applied_configuration_revision = 11
    requests: list[tuple[str, object]] = []
    command_id = str(uuid4())

    class Client:
        snapshot = state
        principal = Principal("gui", client_id, "token")

        def operator_command(self) -> rpc.OperatorCommand:
            return rpc.OperatorCommand(
                operator=pb.OperatorContext(
                    client_id=client_id,
                    control_generation="lease-1",
                    command_id=command_id,
                ),
                controller_generation=generation,
            )

        async def execute(self, method: str, request: object, *, wait: bool):
            assert not wait
            requests.append((method, request))
            return CommandOutcome(command_id, False, None)

        async def wait_result(self, _command_id: str):
            return CommandOutcome(command_id, True, True)

    bridge = ControllerBridge(Client.principal, 50051, 1024, (0,))
    bridge._controller_generation = generation
    bridge._connection_epoch = 6
    finished: list[tuple[str, str, str, str]] = []
    bridge.operation_finished.connect(lambda *args: finished.append(args))
    settings = pb.TrackingSettings(input_camera_role=2)
    await bridge._dispatch(
        Client(),
        "begin_tracking_diagnostic",
        {
            "expected_revision": 11,
            "preview_run_id": "preview-11",
            "selected_stages": (1, 3),
            "diagnostic_settings": settings.SerializeToString(deterministic=True),
        },
    )
    assert requests[0][0] == "BeginTrackingDiagnostic"
    begin = requests[0][1]
    assert isinstance(begin, rpc.BeginTrackingDiagnosticRequest)
    assert begin.expected_configuration_revision == 11
    assert begin.preview_run_id == "preview-11"
    assert tuple(begin.selected_stages) == (1, 3)
    assert begin.diagnostic_settings.input_camera_role == 2
    assert finished[-1][2] == "completed"

    await bridge._dispatch(
        Client(),
        "close_tracking_diagnostic",
        {
            "expected_revision": 11,
            "diagnostic_id": "diagnostic-1",
            "preview_run_id": "preview-11",
        },
    )
    assert requests[1][0] == "CloseTrackingDiagnostic"
    close = requests[1][1]
    assert isinstance(close, rpc.CloseTrackingDiagnosticRequest)
    assert close.diagnostic_id == "diagnostic-1"
    assert close.preview_run_id == "preview-11"


@pytest.mark.asyncio
async def test_tracking_viewer_rpc_uses_frozen_authorized_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui import tracking_frame_transport as transport_module
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal
    from cephvr.tracking.v1 import services_pb2 as tracking_rpc

    generation = str(uuid4())
    viewer_id = str(uuid4())
    backend_generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 12
    diagnostic = state.tracking_diagnostic
    diagnostic.diagnostic_id = "diagnostic-active"
    diagnostic.configuration_revision = 12
    diagnostic.preview_run_id = "preview-active"
    diagnostic.active = True
    diagnostic.tracking_endpoint = "127.0.0.1:51234"
    diagnostic.tracking_process.role = "tracking"
    diagnostic.tracking_process.generation = backend_generation
    gui_principal = Principal("gui", viewer_id, "gui-token")

    class Client:
        snapshot = state
        principal = gui_principal
        rpc_timeout_s = 3.0

    frame = tracking_rpc.TrackingDiagnosticFrame(
        diagnostic_id="diagnostic-active",
        configuration_revision=12,
        preview_run_id="preview-active",
        available=False,
        unavailable_reason="No frame yet",
    )
    calls: list[tuple[object, object, object]] = []

    class Channel:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class Stub:
        async def GetLatestDiagnosticFrame(self, request, *, metadata, timeout):
            calls.append((request, metadata, timeout))
            return frame

    monkeypatch.setattr(
        transport_module.grpc.aio, "insecure_channel", lambda *_a, **_k: Channel()
    )
    monkeypatch.setattr(
        transport_module.tracking_transport,
        "TrackingDiagnosticServiceStub",
        lambda _channel: Stub(),
    )
    bridge = ControllerBridge(gui_principal, 50051, 1_000_000, (0,))
    bridge._connection_epoch = 8
    bridge._controller_generation = generation
    received: list[tuple[int, str, bytes]] = []
    bridge.tracking_frame_received.connect(lambda *args: received.append(args))

    await bridge._dispatch(
        Client(),
        "tracking_diagnostic_frame",
        {
            "expected_revision": 12,
            "diagnostic_id": "diagnostic-active",
            "preview_run_id": "preview-active",
            "tracking_endpoint": "127.0.0.1:51234",
            "tracking_generation": backend_generation,
        },
    )
    query, metadata, timeout = calls[0]
    from cephvr.control.v1 import services_pb2 as rpc

    assert isinstance(query, rpc.TrackingDiagnosticQuery)
    assert query.viewer.role == "gui" and query.viewer.generation == viewer_id
    assert query.controller_generation == generation
    assert query.configuration_revision == 12
    assert query.diagnostic_id == "diagnostic-active"
    assert query.preview_run_id == "preview-active"
    assert metadata == gui_principal.metadata()
    assert timeout == 2.0
    assert received[0][:2] == (8, generation)
    assert tracking_rpc.TrackingDiagnosticFrame.FromString(received[0][2]) == frame


def test_tracking_viewer_detach_stays_detached_until_explicit_reopen(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.cameras import CamerasPanel
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.managed_tracking_diagnostics import ManagedTrackingDiagnostics
    from cephvr.gui.tracking import TrackingPage
    from cephvr.gui.view import DashboardView
    from cephvr.shared.auth import Principal

    page = TrackingPage(CamerasPanel(sample=False))
    page.apply_view(DashboardView(connected=True, has_control=True))
    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 4
    diagnostic = state.tracking_diagnostic
    diagnostic.diagnostic_id = "diag-viewer"
    diagnostic.configuration_revision = 4
    diagnostic.preview_run_id = "preview-viewer"
    diagnostic.source_camera_serial = "SERIAL-1"
    diagnostic.active = True
    diagnostic.tracking_endpoint = "127.0.0.1:59999"
    diagnostic.tracking_process.role = "tracking"
    diagnostic.tracking_process.generation = str(uuid4())
    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
    )
    owner = ManagedTrackingDiagnostics(
        page, bridge, page, lambda: state, lambda: "", lambda: True
    )

    owner.install_snapshot(state)
    assert owner.viewer is not None and owner.viewer.isVisible()
    owner.viewer.close()
    app.processEvents()
    assert not owner._viewer_open
    assert owner.viewer is not None and not owner.viewer.isVisible()

    owner.install_snapshot(state)
    assert owner.viewer is not None and not owner.viewer.isVisible()
    assert page.diagnostic_viewer_button.isEnabled()
    assert page.diagnostic_button.isEnabled()
    page.diagnostic_viewer_button.click()
    app.processEvents()
    assert owner.viewer is not None and owner.viewer.isVisible()
    assert page.diagnostic_button.text() == "Stop diagnostic"
    owner.timer.stop()
    owner.viewer.close()
    page.close()


def test_tracking_viewer_frame_freezes_only_on_explicit_exact_source_action(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PyQt6.QtGui import QImage

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui import managed_tracking_diagnostics as diagnostics_module
    from cephvr.gui.camera_inventory import CameraDraft
    from cephvr.gui.cameras import CamerasPanel
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.managed_tracking_diagnostics import ManagedTrackingDiagnostics
    from cephvr.gui.tracking import TrackingPage
    from cephvr.gui.tracking_live import TrackingDiagnosticPresentation
    from cephvr.gui.view import DashboardView
    from cephvr.shared.auth import Principal
    from cephvr.tracking.v1 import services_pb2 as tracking_rpc

    page = TrackingPage(CamerasPanel(sample=False))
    page.apply_view(DashboardView(connected=True, has_control=True))
    page.cameras.drafts = [
        CameraDraft("tracking-1", "Tracking cam", "SERIAL-1", "Basler")
    ]
    page.cameras.populate_inventory()
    page.cameras.drafts_changed.emit()
    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 9
    diagnostic = state.tracking_diagnostic
    diagnostic.diagnostic_id = str(uuid4())
    diagnostic.configuration_revision = 9
    diagnostic.preview_run_id = str(uuid4())
    diagnostic.source_camera_serial = "SERIAL-1"
    diagnostic.active = True
    diagnostic.tracking_endpoint = "127.0.0.1:59999"
    diagnostic.tracking_process.role = "tracking"
    diagnostic.tracking_process.generation = str(uuid4())
    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
    )
    managed_requests: list[tuple[str, dict[str, object]]] = []
    bridge.request = lambda action, **options: (
        managed_requests.append((action, options)) or True
    )
    owner = ManagedTrackingDiagnostics(
        page, bridge, page, lambda: state, lambda: "", lambda: True
    )
    image = QImage(2, 1, QImage.Format.Format_Grayscale8)
    image.fill(100)
    presentation = TrackingDiagnosticPresentation(
        image=image.copy(),
        diagnostic_id=diagnostic.diagnostic_id,
        configuration_revision=9,
        preview_run_id=diagnostic.preview_run_id,
        source_frame_id=0,
        source_host_receipt_ns=123,
        produced_monotonic_ns=456,
        points=(),
        rectangles=(),
        vectors=(),
        labels=(),
        overlays_truncated=False,
    )
    monkeypatch.setattr(
        diagnostics_module,
        "tracking_diagnostic_presentation",
        lambda *_args, **_kwargs: presentation,
    )
    owner.install_snapshot(state)
    frame = tracking_rpc.TrackingDiagnosticFrame(available=True)
    owner.install_frame(
        bridge.connection_epoch,
        generation,
        frame.SerializeToString(),
    )
    assert page.annotation.canvas.image.isNull()
    assert owner.viewer is not None and owner.viewer.use_frame.isEnabled()

    state.configuration.revision = 10
    owner.viewer.use_frame.click()
    assert page.annotation.canvas.image.isNull()
    state.configuration.revision = 9
    original_run_id = diagnostic.preview_run_id
    diagnostic.preview_run_id = str(uuid4())
    owner.viewer.use_frame.click()
    assert page.annotation.canvas.image.isNull()
    diagnostic.preview_run_id = original_run_id
    diagnostic.source_camera_serial = "OTHER-SERIAL"
    owner.viewer.use_frame.click()
    assert page.annotation.canvas.image.isNull()
    diagnostic.source_camera_serial = "SERIAL-1"
    bridge._connection_epoch += 1
    owner.viewer.use_frame.click()
    assert page.annotation.canvas.image.isNull()
    bridge._connection_epoch -= 1
    owner.viewer.use_frame.click()
    assert not page.annotation.canvas.image.isNull()
    assert page.annotation.canvas.image.size() == image.size()
    assert page.annotation.source_lineage == {
        "camera_serial": "SERIAL-1",
        "configuration_revision": 9,
        "preview_run_id": diagnostic.preview_run_id,
        "source_frame_id": 0,
        "source_host_receipt_ns": 123,
    }
    assert page.snapshot()["annotation_source"] == page.annotation.source_lineage
    assert managed_requests == []

    diagnostic.active = False
    diagnostic.closed = True
    owner.install_snapshot(state)
    assert not page.annotation.canvas.image.isNull()
    assert page.annotation.isEnabled()
    owner.timer.stop()
    if owner.viewer is not None:
        owner.viewer.close()
    page.close()


def test_tracking_diagnostic_close_waits_for_closed_evidence(
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.cameras import CamerasPanel
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.managed_tracking_diagnostics import ManagedTrackingDiagnostics
    from cephvr.gui.tracking import TrackingPage
    from cephvr.gui.view import DashboardView
    from cephvr.shared.auth import Principal

    page = TrackingPage(CamerasPanel(sample=False))
    page.apply_view(DashboardView(connected=True, has_control=True))
    generation = str(uuid4())
    state = pb.Snapshot(controller_generation=generation)
    state.configuration.revision = 4
    diagnostic = state.tracking_diagnostic
    diagnostic.diagnostic_id = "diag-closing"
    diagnostic.configuration_revision = 4
    diagnostic.preview_run_id = "preview-closing"
    diagnostic.source_camera_serial = "SERIAL-1"
    diagnostic.active = True
    diagnostic.tracking_endpoint = "127.0.0.1:59999"
    diagnostic.tracking_process.role = "tracking"
    diagnostic.tracking_process.generation = str(uuid4())
    state.control.holder_client_id = "gui-current"
    bridge = ControllerBridge(
        Principal("gui", "gui-current", "token"), 50051, 1024, (0,)
    )
    owner = ManagedTrackingDiagnostics(
        page, bridge, page, lambda: state, lambda: "", lambda: True
    )
    owner.install_snapshot(state)
    assert page.diagnostic_button.isEnabled()

    owner._close_requested = ("diag-closing", 4, "preview-closing")
    owner.install_snapshot(state)
    assert page.diagnostic_button.text() == "Stopping diagnostic…"
    assert not page.diagnostic_button.isEnabled()
    assert page.diagnostic_viewer_button.isEnabled()

    diagnostic.active = False
    diagnostic.closed = True
    owner.install_snapshot(state)
    assert page.diagnostic_button.isEnabled()
    assert page.diagnostic_button.text() == "Live diagnostic"
    owner.timer.stop()
    if owner.viewer is not None:
        owner.viewer.close()
    page.close()


def test_managed_snapshot_keeps_diagnostic_close_pending_and_status_visible(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_window import ManagedDashboardWindow
    from cephvr.shared.auth import Principal
    from cephvr.tracking.v1 import services_pb2 as tracking_rpc

    client_id = str(uuid4())
    generation = str(uuid4())
    bridge = ControllerBridge(Principal("gui", client_id, "token"), 50051, 1024, (0,))
    bridge.start = lambda: None
    bridge.stop = lambda: None
    requests: list[tuple[str, dict[str, object]]] = []
    bridge.request = lambda action, **options: (
        requests.append((action, options)) or True
    )

    window = ManagedDashboardWindow(sample=False)
    window.devices.cameras.refresh_inventory = lambda: None
    window.devices.microcontroller.scan_ports = lambda: None
    window.devices.projectors.discover_displays = lambda: None
    manager = ManagedGui(window, bridge, gui_history_path=tmp_path / "runtime_gui.json")
    manager.configuration = SimpleNamespace(
        install=lambda _state: True, stale=False, installing_projection=nullcontext
    )
    manager.cameras = SimpleNamespace(install=lambda _state: [])
    manager.mcu = SimpleNamespace(install=lambda *_args: None)
    manager._inventory_identity = (generation, 4)
    manager.control_ready = True
    manager.auto_control_attempted = True
    manager._retained_ack_required = False

    state = pb.Snapshot(controller_generation=generation)
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 4
    state.configuration_values.revision = 4
    state.control.holder_client_id = client_id
    diagnostic = state.tracking_diagnostic
    diagnostic.diagnostic_id = str(uuid4())
    diagnostic.configuration_revision = 4
    diagnostic.preview_run_id = str(uuid4())
    diagnostic.active = True
    diagnostic.tracking_endpoint = "127.0.0.1:59999"
    diagnostic.tracking_process.role = "tracking"
    diagnostic.tracking_process.generation = str(uuid4())
    diagnostic.last_duration_ns = 12_000_000
    diagnostic.maximum_duration_ns = 20_000_000
    stage = diagnostic.stages.add(
        stage=tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_POSE,
        state=tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_STATE_RUNNING,
    )
    stage.reason = "current source"
    manager.install_snapshot(1, generation, state.SerializeToString())
    page = window.tracking
    assert page.diagnostic_button.text() == "Stop diagnostic"
    page.diagnostic_button.click()
    assert requests[-1][0] == "close_tracking_diagnostic"
    manager.install_snapshot(1, generation, state.SerializeToString())
    assert page.diagnostic_button.text() == "Stopping diagnostic…"
    assert not page.diagnostic_button.isEnabled()
    assert page._diagnostic_locked
    assert "pose: running (current source)" in page.status.hud.toPlainText()
    assert ("LAST", "12.00 ms") in page.status.rows
    assert ("MAX", "20.00 ms") in page.status.rows
    page.diagnostic_button.click()
    assert not any(action == "begin_tracking_diagnostic" for action, _ in requests)

    diagnostic.failure = "close outcome unknown"
    diagnostic.active = False
    diagnostic.closed = False
    manager.install_snapshot(1, generation, state.SerializeToString())
    assert not page.diagnostic_button.isEnabled()
    assert page._diagnostic_locked
    assert "close outcome unknown" in page.status.hud.toPlainText()
    assert not any(action == "begin_tracking_diagnostic" for action, _ in requests)

    manager.tracking_diagnostics.timer.stop()
    if manager.tracking_diagnostics.viewer is not None:
        manager.tracking_diagnostics.viewer.close()
    manager.bridge.stop()
    window._close_after_save = True
    window.close()
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize(
    ("selection", "expected"),
    ((None, None), ("Retry", "retry"), ("Close without saving", "discard")),
)
def test_save_failure_dismissal_never_discards_draft(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    selection: str | None,
    expected: str | None,
) -> None:

    from PyQt6.QtWidgets import QMessageBox

    from cephvr.gui.managed_close import save_failure_choice

    monkeypatch.setattr(QMessageBox, "exec", lambda _self: 0)
    monkeypatch.setattr(
        QMessageBox,
        "clickedButton",
        lambda self: next(
            (button for button in self.buttons() if button.text() == selection), None
        ),
    )
    parent = QWidget()
    choice = save_failure_choice(parent, "GUI save failed")
    assert choice == expected
    parent.close()


def test_tracking_empty_diagnostic_mask_does_not_require_experiment_settings(
    app: QApplication,
) -> None:
    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.cameras import CamerasPanel
    from cephvr.gui.tracking import TrackingPage

    page = TrackingPage(CamerasPanel(sample=False))
    for stage in page.forms.stages.values():
        stage.setChecked(False)
    current = pb.TrackingSettings()
    settings, selected = page.diagnostic_configuration(current)
    assert selected == ()
    assert settings.input_camera_role == camera_pb2.CAMERA_ROLE_TRACKING
    assert settings.preprocessing.scale_percent == 100
    assert not settings.HasField("subject_reference")
    assert not settings.HasField("pose_search_region")
    assert not settings.stages
    page.close()


def test_tracking_flow_diagnostic_ignores_dormant_pose_and_estimator_drafts(
    app: QApplication,
) -> None:
    import json

    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.cameras import CamerasPanel
    from cephvr.gui.tracking import TrackingPage
    from cephvr.tracking.v1 import services_pb2 as tracking_rpc

    page = TrackingPage(CamerasPanel(sample=False))
    for stage in page.forms.stages.values():
        stage.setChecked(False)
    page.forms.stages["optical_flow"].setChecked(True)
    base = pb.TrackingSettings(
        input_camera_role=camera_pb2.CAMERA_ROLE_TRACKING,
        pipeline_id="water_flow",
    )
    base.stages.add(
        stage_id="image_flow",
        implementation_id="nvidia_optical_flow",
        settings_schema_id="tracking.flow-settings.v1",
        settings_json=json.dumps(
            {
                "schema_version": 1,
                "adapter": "nvof_cuda_v1",
                "device_ordinal": 0,
                "output_grid_px": 4,
                "preset": "slow",
                "temporal_hints": False,
                "output_cost": False,
                "input_mapping": "declared_full_range_gray8_v1",
            }
        ),
    )

    settings, selected = page.diagnostic_configuration(base)
    assert selected == (tracking_rpc.TRACKING_DIAGNOSTIC_STAGE_OPTICAL_FLOW,)
    assert len(settings.stages) == 1
    document = json.loads(settings.stages[0].settings_json)
    assert document["adapter"] == "nvof_cuda_v1"
    assert document["input_mapping"] == "declared_full_range_gray8_v1"
    assert document["output_grid_px"] == 4
    page.close()


@pytest.mark.asyncio
async def test_bridge_rejects_stale_configuration_base_without_admission() -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.configuration.revision = 3
    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
    )
    bridge._controller_generation = state.controller_generation

    class Client:
        snapshot = state

    from cephvr.client.session import ClientError

    with pytest.raises(ClientError, match="base changed"):
        await bridge._submit_configuration(
            Client(),
            {
                "base_revision": 2,
                "proposal": pb.ExperimentConfiguration().SerializeToString(),
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["behavioral", "tracking", "eye_tracking"])
async def test_managed_camera_enable_updates_only_assigned_camera(role: str) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot()
    state.configuration.revision = 4
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=False
    )
    acquisition.acquisition.behavioral.device.device_id = "40065509"
    acquisition.acquisition.tracking.device.device_id = "40747103"
    acquisition.acquisition.tracking.enabled = False
    acquisition.acquisition.eye_tracking.device.device_id = "eye-serial"
    serial = getattr(acquisition.acquisition, role).device.device_id
    requests = []

    async def execute(method: str, request: object) -> SimpleNamespace:
        requests.append((method, request))
        return SimpleNamespace(succeeded=True)

    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    client = SimpleNamespace(
        snapshot=state,
        operator_command=lambda: rpc.OperatorCommand(),
        execute=execute,
    )
    await bridge._dispatch(
        client, "set_camera_enabled", {"serial": serial, "enabled": True}
    )
    assert len(requests) == 1
    method, request = requests[0]
    assert method == "UpdateConfiguration"
    assert request.expected_revision == 4
    updated = request.proposed.backends[0]
    assert updated.enabled
    for name in ("behavioral", "tracking", "eye_tracking"):
        assert getattr(updated.acquisition, name).enabled is (name == role)
    assert not state.configuration_values.current.backends[0].enabled


@pytest.mark.asyncio
async def test_disconnect_after_failed_connect_uses_device_cleanup() -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_device_commands import _camera

    state = pb.Snapshot()
    state.configuration.revision = 4
    state.acquisition_devices.behavioral.cleanup_pending = True
    requests = []

    async def execute(method, request):
        requests.append(request)
        return SimpleNamespace(succeeded=True)

    client = SimpleNamespace(
        snapshot=state, operator_command=rpc.OperatorCommand, execute=execute
    )
    await _camera(client, {"role": 1, "kind": rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW})
    assert requests[0].kind == rpc.CAMERA_COMMAND_KIND_FINISH_EDITING
    assert not requests[0].HasField("preview_run_id")


def test_eye_role_projects_and_tests_selected_without_capture(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_cameras import ManagedCameras

    panel = window.devices.cameras
    panel.managed = True
    assert panel.role.findText("Eye tracking") >= 0
    state = pb.Snapshot()
    state.configuration.revision = 4
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    settings.eye_tracking.device.device_id = panel.drafts[0].serial
    settings.eye_tracking.enabled = False
    calls = []
    binding = ManagedCameras(
        panel,
        SimpleNamespace(
            request=lambda action, **kw: calls.append((action, kw)) or True
        ),
        lambda *_: False,
    )
    binding.install(state)
    assert panel.drafts[0].role == "Eye tracking"
    binding.queue("camera", role=3, kind=rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION)
    assert calls == [
        (
            "camera",
            {
                "role": 3,
                "kind": rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
            },
        )
    ]


@pytest.mark.asyncio
async def test_eye_assignment_preserves_existing_camera_roles() -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.device_requests import assign_camera_role

    state = pb.Snapshot()
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    settings.behavioral.device.device_id = "behavior"
    settings.tracking.device.device_id = "tracking"
    requests = []

    async def execute(method, request):
        requests.append(request)
        return SimpleNamespace(succeeded=True)

    await assign_camera_role(
        SimpleNamespace(
            snapshot=state, operator_command=rpc.OperatorCommand, execute=execute
        ),
        {"serial": "third", "role": "Eye tracking"},
    )
    changed = requests[0].proposed.backends[0].acquisition
    assert changed.behavioral.device.device_id == "behavior"
    assert changed.tracking.device.device_id == "tracking"
    assert changed.eye_tracking.device.device_id == "third"
    assert not changed.eye_tracking.enabled


@pytest.mark.parametrize("connect", [False, True])
def test_loaded_camera_action_queues_parameters_without_setup(
    window: DashboardWindow, connect: bool
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.gui.managed_cameras import ManagedCameras

    panel = window.devices.cameras
    panel.managed = panel.snapshot_draft = True
    panel.selected.values.update(
        trigger_clock="Internal clock", preset="new.pfs", pfs_imported="no"
    )
    window.apply_view(
        DashboardView(connected=True, has_control=True, phase=Phase.CONFIGURATION)
    )
    calls = []
    binding = ManagedCameras(
        panel,
        SimpleNamespace(
            request=lambda action, **kw: calls.append((action, kw)) or True
        ),
        lambda *_: False,
        submission_options=lambda _key: {"base_revision": 4, "pin": "12"},
    )
    panel.connect_button.click() if connect else binding.prepare_action(
        panel.selected.key, rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION
    )
    assert len(calls) == 1 and calls[0][0] == "prepare_camera"
    assert calls[0][1]["preset"] == "new.pfs"
    assert calls[0][1]["clock"] == "Internal clock"
    assert calls[0][1]["kind"] == (
        rpc.CAMERA_COMMAND_KIND_START_PREVIEW
        if connect
        else rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION
    )
    assert binding.pending == "prepare_camera" and panel.operation_pending


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "base", "settings", "import"])
@pytest.mark.parametrize("connect", [False, True])
async def test_camera_action_submits_before_test_and_stops_on_failure(
    failure: str,
    connect: bool,
) -> None:
    from cephvr.acquisition.v1 import camera_pb2 as camera_pb
    from cephvr.client.session import ClientError
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation="generation")
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = state.configuration_values.revision = 4
    state.configuration_values.current.subject = "Preserved"
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    settings.behavioral.device.device_id = "behavior"
    settings.eye_tracking.device.settings.trigger_activation = "rising_edge"
    calls = []

    async def execute(method, request):
        calls.append((method, request))
        if method == "UpdateConfiguration":
            candidate = request.proposed.backends[0].acquisition.eye_tracking.device
            if (
                candidate.frame_timing == camera_pb.FRAME_TIMING_FREE_RUNNING
                and candidate.settings.HasField("trigger_activation")
            ):
                raise ClientError(
                    "value 'rising_edge' is not an advertised TriggerActivation choice"
                )
            if failure == "settings" and len(calls) == 2:
                return SimpleNamespace(succeeded=False, failure="invalid settings")
            state.configuration_values.current.CopyFrom(request.proposed)
            state.configuration.revision += 1
            state.configuration_values.revision = state.configuration.revision
        if (
            method == "ExecuteCameraCommand"
            and request.kind == rpc.CAMERA_COMMAND_KIND_IMPORT_PFS
        ):
            if failure == "import":
                return SimpleNamespace(succeeded=False, failure="invalid PFS")
            current = state.configuration_values.current.backends[0].acquisition
            current.eye_tracking.device.pfs_baseline.SetInParent()
            state.configuration.revision += 1
            state.configuration_values.revision = state.configuration.revision
        if (
            method == "ExecuteCameraCommand"
            and request.kind == rpc.CAMERA_COMMAND_KIND_START_PREVIEW
        ):
            state.acquisition_devices.eye_tracking.preview_running = True
            state.acquisition_devices.eye_tracking.preview_run_id = "preview"
            state.configuration.revision += 1
            state.configuration_values.revision = state.configuration.revision
        return SimpleNamespace(succeeded=True)

    bridge = ControllerBridge(Principal("gui", "gui", "token"), 50051, 1024, (0,))
    accepted = []
    bridge.device_configuration_accepted.connect(
        lambda revision, payload: accepted.append(
            (revision, pb.Snapshot.FromString(payload))
        )
    )
    options = {
        "generation": "generation",
        "base_revision": 3 if failure == "base" else 4,
        "base_configuration": state.configuration_values.current.SerializeToString(
            deterministic=True
        ),
        "camera_role": 3,
        "role": "Eye tracking",
        "serial": "eye",
        "clock": "Internal clock",
        "source": "",
        "preset": "new.pfs",
        "rate": "60",
        "enabled": True,
        "pin": "8",
        "port": "COM8",
        "kind": (
            rpc.CAMERA_COMMAND_KIND_START_PREVIEW
            if connect
            else rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION
        ),
        "show_preview": connect,
    }
    client = SimpleNamespace(
        snapshot=state, execute=execute, operator_command=rpc.OperatorCommand
    )
    if failure == "none" or (not connect and failure in {"settings", "import"}):
        await bridge._dispatch(client, "prepare_camera", options)
        assert calls[-1][0] == "ExecuteCameraCommand"
        assert calls[-1][1].kind == (
            rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
            if connect
            else rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION
        )
        assert calls[-1][1].expected_configuration_revision == (8 if connect else 5)
        changed = state.configuration_values.current.backends[0].acquisition
        assert changed.eye_tracking.device.device_id == "eye"
        assert not changed.eye_tracking.enabled
        assert changed.behavioral.device.device_id == "behavior"
        assert state.configuration_values.current.subject == "Preserved"
        if connect:
            assert changed.pulses.eye_tracking.pin == "D8"
            assert not changed.eye_tracking.device.settings.HasField(
                "trigger_activation"
            )
            assert [base for base, _ in accepted] == [4, 5, 6, 7]
        else:
            assert (
                changed.eye_tracking.device.settings.trigger_activation == "rising_edge"
            )
            assert not changed.pulses.HasField("eye_tracking")
            assert [method for method, _ in calls] == [
                "UpdateConfiguration",
                "ExecuteCameraCommand",
            ]
            assert [base for base, _ in accepted] == [4]
    else:
        with pytest.raises(ClientError):
            await bridge._dispatch(client, "prepare_camera", options)
        assert not any(
            method == "ExecuteCameraCommand"
            and request.kind
            in (
                rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION,
                rpc.CAMERA_COMMAND_KIND_START_PREVIEW,
            )
            for method, request in calls
        )
        if failure == "base":
            assert calls == [] and accepted == []
        if failure == "import":
            assert calls[-1][1].kind == rpc.CAMERA_COMMAND_KIND_FINISH_EDITING


@pytest.mark.asyncio
async def test_repeated_camera_connect_skips_noop_configuration_update() -> None:
    """A no-op camera preparation must not validate unrelated incomplete drafts."""
    from cephvr.acquisition.v1 import camera_pb2 as camera_pb
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation="generation")
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = state.configuration_values.revision = 4
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    selected = acquisition.eye_tracking.device
    selected.device_id = "eye"
    selected.frame_timing = camera_pb.FRAME_TIMING_FREE_RUNNING
    selected.unaligned_free_running = True
    acquisition.pulses.eye_tracking.pin = "D8"
    acquisition.pulses.eye_tracking.requested_frequency_hz = 30.0
    calls = []

    async def execute(method, request):
        calls.append(method)
        if method == "UpdateConfiguration":
            if state.configuration.revision > 4:
                assert request.proposed == state.configuration_values.current, (
                    f"proposed={request.proposed!s}\ncurrent="
                    f"{state.configuration_values.current!s}"
                )
            state.configuration_values.current.CopyFrom(request.proposed)
            state.configuration.revision += 1
            state.configuration_values.revision = state.configuration.revision
        if method == "ExecuteCameraCommand":
            state.acquisition_devices.eye_tracking.preview_running = True
            state.acquisition_devices.eye_tracking.preview_run_id = "preview"
        return SimpleNamespace(succeeded=True)

    bridge = ControllerBridge(Principal("gui", "gui", "token"), 50051, 1024, (0,))
    client = SimpleNamespace(
        snapshot=state, execute=execute, operator_command=rpc.OperatorCommand
    )

    def options(kind):
        return {
            "generation": "generation",
            "base_revision": state.configuration.revision,
            "base_configuration": state.configuration_values.current.SerializeToString(
                deterministic=True
            ),
            "camera_role": 3,
            "role": "Eye tracking",
            "serial": "eye",
            "enabled": False,
            "pin": "8",
            "port": "",
            "clock": "Internal clock",
            "source": "",
            "preset": "",
            "rate": "30",
            "kind": kind,
            "show_preview": True,
        }

    await bridge._dispatch(
        client, "prepare_camera", options(rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION)
    )
    state.configuration_values.current.backends[0].acquisition.behavioral.enabled = True
    await bridge._dispatch(
        client, "prepare_camera", options(rpc.CAMERA_COMMAND_KIND_START_PREVIEW)
    )
    assert calls.count("UpdateConfiguration") == 1
    assert calls[-1] == "ExecuteCameraCommand"
    assert state.acquisition_devices.eye_tracking.preview_running


def test_camera_acceptance_preserves_other_local_configuration_drafts(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
            window.devices.microcontroller,
        )
    )
    state = pb.Snapshot(controller_generation="generation")
    state.configuration.revision = state.configuration_values.revision = 4
    assert manager.install(state)
    window.devices.cameras.snapshot_draft = True
    window.devices.microcontroller.snapshots.draft_loaded = True
    window.dashboard.subject_id.setText("Local subject")
    manager.dirty = manager.tracking_dirty = manager.stale = True
    state.configuration.revision = state.configuration_values.revision = 5
    assert manager.note_device_revision(state, 4)
    assert manager.revision == 5 and not manager.stale
    assert manager.dirty and manager.tracking_dirty
    assert window.dashboard.subject_id.text() == "Local subject"
    assert window.devices.cameras.snapshot_draft
    assert window.devices.microcontroller.snapshots.draft_loaded
    state.controller_generation = "other"
    assert not manager.note_device_revision(state, 5)
    assert manager.revision == 5


@pytest.mark.asyncio
async def test_managed_camera_settings_supply_missing_trigger_source() -> None:
    from cephvr.acquisition.v1 import camera_pb2 as camera
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot()
    state.configuration.revision = 6
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=False
    ).acquisition
    acquisition.behavioral.device.device_id = "40065509"
    acquisition.tracking.device.device_id = "40747103"
    requests = []

    async def execute(method: str, request: object) -> SimpleNamespace:
        requests.append((method, request))
        return SimpleNamespace(succeeded=True)

    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    client = SimpleNamespace(
        snapshot=state,
        operator_command=lambda: rpc.OperatorCommand(),
        execute=execute,
    )
    await bridge._dispatch(
        client,
        "save_camera_settings",
        {
            "serial": "40065509",
            "clock": "External controller",
            "source": "Line1",
            "preset": "C:/camera/behavior.pfs",
            "rate": "30.0",
        },
    )
    assert [method for method, _ in requests] == [
        "UpdateConfiguration",
        "ExecuteCameraCommand",
        "ExecuteCameraCommand",
    ]
    assert requests[1][1].kind == rpc.CAMERA_COMMAND_KIND_IMPORT_PFS
    assert requests[2][1].kind == rpc.CAMERA_COMMAND_KIND_FINISH_EDITING
    assert not requests[0][1].proposed.backends[0].acquisition.behavioral.enabled
    method, request = requests[0]
    assert method == "UpdateConfiguration"
    assert request.expected_revision == 6
    changed = request.proposed.backends[0].acquisition
    assert (
        changed.behavioral.device.frame_timing == camera.FRAME_TIMING_EXTERNAL_TRIGGER
    )
    assert changed.behavioral.device.settings.trigger_source == "Line1"
    assert changed.behavioral.device.pfs_source_filename == "C:/camera/behavior.pfs"
    assert changed.pulses.behavioral.requested_frequency_hz == 30.0
    assert (
        state.configuration_values.current.backends[
            0
        ].acquisition.behavioral.device.settings.trigger_source
        == ""
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["D", ""])
async def test_managed_mcu_save_includes_camera_output_pins(prefix: str) -> None:
    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot()
    state.configuration.revision = 3
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    acquisition.pulses.tracking.pin = "D11"
    requests = []

    async def execute(method: str, request: object) -> SimpleNamespace:
        requests.append((method, request))
        return SimpleNamespace(succeeded=True)

    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    client = SimpleNamespace(
        snapshot=state,
        operator_command=lambda: rpc.OperatorCommand(),
        execute=execute,
    )
    await bridge._dispatch(
        client,
        "save_mcu_pins",
        {
            "port": "COM8",
            "trial_pin": f"{prefix}9",
            "trial_enabled": True,
            "flip_pin": f"{prefix}2",
            "flip_enabled": True,
            "behavioral_pin": f"{prefix}10",
            "tracking_pin": None,
            "eye_tracking_pin": f"{prefix}8",
        },
    )
    method, request = requests[0]
    assert method == "UpdateConfiguration"
    pulses = request.proposed.backends[0].acquisition.pulses
    assert pulses.behavioral.pin == "D10"
    assert pulses.tracking.pin == "D11"
    assert pulses.eye_tracking.pin == "D8"
    assert (
        state.configuration_values.current.backends[0].acquisition.pulses.behavioral.pin
        == ""
    )
    acquisition.eye_tracking.device.device_id = "eye-serial"
    acquisition.eye_tracking.device.frame_timing = (
        camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    )
    await bridge._dispatch(
        client, "add_mcu_output", {"role": "eye_tracking", "pin": "8"}
    )
    added = requests[-1][1].proposed.backends[0].acquisition
    assert not added.eye_tracking.enabled and added.pulses.eye_tracking.pin == "D8"
    assert (
        requests[-1][1].proposed.backends[0].enabled
        == state.configuration_values.current.backends[0].enabled
    )
    assert not acquisition.eye_tracking.enabled


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["", "rejected", "stale", "unconfirmed", "changed_after_acceptance"]
)
async def test_managed_mcu_draft_test_requires_exact_acceptance(failure: str) -> None:
    from cephvr.client.session import ClientError
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation="generation")
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = state.configuration_values.revision = 7
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition
    acquisition.pulses.port = "COM8"
    acquisition.pulses.behavioral.pin = "D10"
    acquisition.pulses.trial_state_pin = "D12"
    acquisition.pulses.eye_tracking.pin = "D8"
    acquisition.pulses.eye_tracking.requested_frequency_hz = 30
    acquisition.eye_tracking.device.device_id = "eye-camera"
    acquisition.eye_tracking.enabled = True
    acquisition.eye_tracking.save_video = True
    options = {
        "generation": "generation",
        "base_revision": 7,
        "base_configuration": state.configuration_values.current.SerializeToString(
            deterministic=True
        ),
        "port": "COM8",
        "pin": "9",
        "frequency": "60",
        "kind": rpc.MICROCONTROLLER_COMMAND_KIND_START,
        "signal": pb.MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING,
    }
    calls = []

    async def execute(method: str, request: object) -> SimpleNamespace:
        calls.append((method, request))
        if method == "UpdateConfiguration" and failure != "rejected":
            state.configuration_values.current.CopyFrom(request.proposed)
            state.configuration.revision = state.configuration_values.revision = 8
            if failure == "unconfirmed":
                state.configuration_values.current.backends[
                    0
                ].acquisition.pulses.eye_tracking.pin = "D7"
        succeeded = failure != "rejected"
        if method == "ExecuteMicrocontrollerCommand":
            succeeded = (
                request.expected_configuration_revision == state.configuration.revision
            )
        return SimpleNamespace(succeeded=succeeded, failure="pin rejected")

    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    client = SimpleNamespace(
        snapshot=state,
        operator_command=lambda: rpc.OperatorCommand(),
        execute=execute,
    )
    accepted = []

    def note_accepted(*args: object) -> None:
        accepted.append(args)
        if failure == "changed_after_acceptance":
            state.configuration.revision = state.configuration_values.revision = 9

    bridge.device_configuration_accepted.connect(note_accepted)
    if failure == "stale":
        state.configuration.revision = 8
    if failure:
        with pytest.raises(ClientError):
            await bridge._dispatch(client, "prepare_mcu_test", options)
        if failure == "changed_after_acceptance":
            assert accepted
            assert calls[-1][1].expected_configuration_revision == 8
        else:
            assert not accepted
            assert all(method != "ExecuteMicrocontrollerCommand" for method, _ in calls)
    else:
        await bridge._dispatch(client, "prepare_mcu_test", options)
        assert [method for method, _ in calls] == [
            "UpdateConfiguration",
            "ExecuteMicrocontrollerCommand",
        ]
        changed = calls[0][1].proposed.backends[0].acquisition
        assert changed.pulses.eye_tracking.pin == "D9"
        assert changed.pulses.eye_tracking.requested_frequency_hz == 60
        assert changed.pulses.behavioral.pin == "D10"
        assert changed.pulses.trial_state_pin == "D12"
        assert changed.eye_tracking == acquisition.eye_tracking
        assert calls[1][1].expected_configuration_revision == 8
        assert calls[1][1].signal == pb.MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING
        assert accepted[0][0] == 7


def test_managed_microcontroller_submits_edited_pin_before_test(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui import managed_mcu

    panel = window.devices.microcontroller
    panel.managed = True
    panel.set_saved_pins("COM8", "D12", True, "D2", True)
    window.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            configuration_wired=False,
            phase=Phase.CONFIGURATION,
        )
    )
    snapshot = pb.Snapshot()
    acquisition = snapshot.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    acquisition.pulses.port = "COM8"
    acquisition.pulses.trial_state_pin = "D12"
    acquisition.pulses.projector_flip_pin = "D2"
    requests: list[tuple[str, dict[str, object]]] = []
    bridge = SimpleNamespace(
        request=lambda action, **options: requests.append((action, options)) or True
    )
    monkeypatch.setattr(managed_mcu.QTimer, "singleShot", lambda *_: None)
    binding = managed_mcu.ManagedMcu(panel, bridge, lambda: snapshot)

    panel.test_connection_button.click()
    binding.finished("mcu", True, "Completed")
    assert panel.trial_pin.text() == "12"
    assert panel.test_buttons["trial-state"].isEnabled()
    panel.test_buttons["trial-state"].click()
    binding.finished("mcu", True, "Completed")
    panel.trial_pin.setText("D8")
    binding.test_pin("trial-state", True)

    from cephvr.gui.action_cancellation import Cancellation

    assert all(
        isinstance(options["cancellation"], Cancellation) for _, options in requests[:2]
    )
    assert [
        (
            action,
            {key: value for key, value in options.items() if key != "cancellation"},
        )
        for action, options in requests[:2]
    ] == [
        ("mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT}),
        (
            "mcu",
            {
                "kind": rpc.MICROCONTROLLER_COMMAND_KIND_START,
                "signal": pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
            },
        ),
    ]
    assert requests[2][0] == "prepare_mcu_test"
    assert requests[2][1]["pin"] == "8"
    assert "Requested" not in panel.console.toPlainText()


def test_managed_camera_pin_test_uses_saved_role_signal(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui import managed_mcu
    from cephvr.gui.microcontroller import CameraTrigger

    panel = window.devices.microcontroller
    panel.managed = True
    panel.set_cameras(
        (CameraTrigger("camera-1", "Behavior cam", "Internal clock", "30", False),)
    )
    panel.pin_editors["behavioral"].setText("D10")
    state = pb.Snapshot()
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    acquisition.pulses.behavioral.pin = "D10"
    acquisition.pulses.behavioral.requested_frequency_hz = 30
    acquisition.pulses.port = "COM8"
    panel.set_saved_pins("COM8", "D9", True, "D2", True)
    requests: list[tuple[str, dict[str, object]]] = []
    bridge = SimpleNamespace(
        request=lambda action, **options: requests.append((action, options)) or True
    )
    monkeypatch.setattr(managed_mcu.QTimer, "singleShot", lambda *_: None)
    binding = managed_mcu.ManagedMcu(panel, bridge, lambda: state)
    binding.test_pin("behavioral", True)
    assert requests[0][1].pop("cancellation") is panel.pending_action.token
    assert requests == [
        (
            "mcu",
            {
                "kind": rpc.MICROCONTROLLER_COMMAND_KIND_START,
                "signal": pb.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL,
            },
        )
    ]
    panel.pin_editors["behavioral"].setText("D12")
    binding.finished("mcu", True, "Completed")
    binding.test_pin("behavioral", True)
    assert len(requests) == 2
    assert requests[1][0] == "prepare_mcu_test"
    assert requests[1][1]["pin"] == "12"
    assert requests[1][1]["frequency"] == "30"


@pytest.mark.parametrize("role", ["Eye tracking", "Unassigned"])
def test_managed_mcu_preserves_camera_role_identity(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui import managed_mcu
    from cephvr.gui.microcontroller import CameraTrigger

    panel = window.devices.microcontroller
    panel.managed = True
    panel.set_cameras((CameraTrigger("third", role, "External controller", "60"),))
    state = pb.Snapshot()
    state.configuration.revision = 1
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    acquisition.pulses.port = "COM8"
    acquisition.pulses.tracking.pin = "D11"
    acquisition.pulses.eye_tracking.pin = "D8"
    acquisition.pulses.eye_tracking.requested_frequency_hz = 60
    requests: list[object] = []
    bridge = SimpleNamespace(
        request=lambda action, **options: requests.append((action, options)) or True
    )
    monkeypatch.setattr(managed_mcu.QTimer, "singleShot", lambda *_: None)
    binding = managed_mcu.ManagedMcu(panel, bridge, lambda: state)
    window.apply_view(
        DashboardView(connected=True, has_control=True, phase=Phase.CONFIGURATION)
    )
    binding.install(state, True)
    if role == "Eye tracking":
        assert panel.pin_editors["eye_tracking"].text() == "8"
        assert panel.pin_editors["eye_tracking"].isEnabled()
        assert panel.test_buttons["eye_tracking"].isEnabled()
        panel.test_buttons["eye_tracking"].click()
        assert requests[0][0] == "mcu"
        assert requests[0][1]["signal"] == pb.MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING
    else:
        assert panel.pin_editors["eye_tracking"].text() == "8"
        assert panel.pin_editors["eye_tracking"].isEnabled()
        assert not panel.test_buttons["eye_tracking"].isEnabled()
        binding.test_pin("eye_tracking", True)
        assert requests[0][1]["signal"] == pb.MICROCONTROLLER_SIGNAL_KIND_EYE_TRACKING


def test_managed_role_wiring_is_local_before_camera_discovery(
    window: DashboardWindow,
) -> None:
    panel = window.devices.microcontroller
    cameras = window.devices.cameras
    panel.managed = True
    panel.can_review = True
    cameras.enable_controls[0].setChecked(False)
    requests = []
    panel.save_requested.connect(lambda *args: requests.append(args))
    assert set(panel.pin_editors) == {"behavioral", "tracking", "eye_tracking"}
    panel.pin_editors["eye_tracking"].setText("D8")
    assert panel.snapshots.draft_loaded
    assert panel.pin_editors["eye_tracking"].text() == "8"
    assert not cameras.drafts[0].enabled
    assert requests == []


def test_contextual_wiring_editors_update_only_the_shared_draft(
    window: DashboardWindow, app: QApplication
) -> None:
    from PyQt6.QtCore import QTimer

    devices = window.devices
    mcu = devices.microcontroller
    cameras = devices.cameras
    window.apply_view(review_view(Phase.CONFIGURATION))
    mcu.port.addItem("COM8", "COM8")
    mcu.port.setCurrentIndex(mcu.port.findData("COM8"))
    mcu.pin_editors["tracking"].setText("11")
    mcu.flip_pin.setText("2")
    cameras.drafts[0].enabled = False
    cameras.populate_inventory()
    saved: list[tuple[object, ...]] = []
    mcu.save_requested.connect(lambda *values: saved.append(values))

    def camera_save() -> None:
        editor = devices.wiring_dialog
        assert editor is not None
        editor.port.setEditText("COM9")
        editor.pin.setText("7")
        editor.accept()

    QTimer.singleShot(0, camera_save)
    cameras.wiring_button.click()
    app.processEvents()
    assert mcu.port.currentData() == "COM9"
    assert mcu.pin_editors["behavioral"].text() == "7"
    assert mcu.pin_editors["tracking"].text() == "11"
    assert mcu.flip_pin.text() == "2"
    assert not cameras.drafts[0].enabled
    assert mcu.snapshots.draft_loaded and saved == []


@pytest.mark.parametrize("change", ["role", "authority", "pending"])
def test_contextual_wiring_save_is_discarded_after_identity_or_authority_change(
    window: DashboardWindow, app: QApplication, change: str
) -> None:
    from PyQt6.QtCore import QTimer

    devices = window.devices
    window.apply_view(review_view(Phase.CONFIGURATION))
    panel = devices.microcontroller
    panel.set_role_pin("behavioral", "5")

    def stale_save() -> None:
        editor = devices.wiring_dialog
        assert editor is not None
        if change == "role":
            devices.cameras.drafts[0].role = "Tracking cam"
        elif change == "authority":
            panel.can_review = False
        else:
            panel.pending_test_key = "behavioral"
        editor.pin.setText("9")
        editor.accept()

    QTimer.singleShot(0, stale_save)
    devices.edit_camera_wiring()
    app.processEvents()
    assert panel.pin_editors["behavioral"].text() == "5"
    assert panel.pin_editors["tracking"].text() == ""


@pytest.mark.parametrize(
    "mode", ["free_run", "photodiode_only_vsync", "all_outputs_vsync"]
)
def test_projector_sync_modes_without_mcu_preserve_saved_drafts(window, mode):
    panel = window.devices.projectors
    timing = panel.timing
    window.devices.microcontroller.flip_pin.clear()
    assert not hasattr(timing, "wiring_button")
    assert [timing.mode.itemText(i) for i in range(timing.mode.count())] == [
        "Free run (no VSync)",
        "VSync on pulse displays",
        "VSync on all displays",
    ]
    timing.set_presentation_mode(mode)
    assert timing.mode.isEnabled()
    snapshot = panel.calibration_files.snapshot()
    timing.set_presentation_mode("photodiode_only_vsync")
    panel.calibration_files.apply_snapshot(snapshot)
    assert timing.presentation_mode == mode
    assert window.devices.microcontroller.flip_pin.text() == ""
    snapshot["settings"]["vsync_mode"] = "All displays VSync"
    panel.calibration_files.apply_snapshot(snapshot)
    assert timing.presentation_mode == "all_outputs_vsync"


def test_restored_managed_draft_assigns_eye_and_adds_output_locally(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.camera_inventory import CameraDraft
    from cephvr.gui.camera_snapshot import capture_cameras, restore_cameras
    from cephvr.gui.managed_cameras import ManagedCameras
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )
    from cephvr.gui.managed_mcu import ManagedMcu

    cameras = window.devices.cameras
    panel = window.devices.microcontroller
    cameras.managed = panel.managed = True
    cameras.drafts.append(CameraDraft("eye", "Unassigned", "third", "Test", False))
    cameras.populate_inventory()
    restore_cameras(cameras, capture_cameras(cameras))
    configuration = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            cameras,
            window.devices.projectors,
            window.tracking,
            panel,
        )
    )
    window.apply_view(
        DashboardView(connected=True, has_control=True, phase=Phase.CONFIGURATION)
    )
    calls = []
    bridge = SimpleNamespace(
        request=lambda action, **options: calls.append((action, options)) or True
    )
    camera_binding = ManagedCameras(cameras, bridge, lambda *_: False)
    state = pb.Snapshot()
    state.configuration.revision = 1
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    settings.behavioral.device.device_id = cameras.drafts[0].serial
    settings.tracking.device.device_id = cameras.drafts[1].serial
    binding = ManagedMcu(panel, bridge, lambda: state)
    cameras.table.selectRow(2)
    cameras.role.setCurrentText("Eye tracking")
    assert cameras.selected.role == "Eye tracking"
    assert configuration.dirty and configuration.edit_serial > 0
    assert not configuration.stale
    assert configuration._tracking_serial() == cameras.drafts[1].serial
    assert cameras.table.item(2, 2).text() == "Eye tracking"
    assert panel.snapshots.draft_loaded
    panel.pin_editors["eye_tracking"].setText("8")
    assert not cameras.selected.enabled
    assert panel.pin_editors["eye_tracking"].text() == "8"
    camera_binding.install(state)
    assert cameras.selected.role == "Eye tracking"
    assert cameras.drafts[0].role == "Behavior cam"
    assert cameras.drafts[1].role == "Tracking cam"
    assert cameras.config_files.save_button.isEnabled()
    assert panel.config_files.save_button.isEnabled()
    assert calls == []
    binding.settle.stop()


def test_managed_window_waits_for_history_save_before_closing(
    app: QApplication,
) -> None:
    from cephvr.gui.managed_window import ManagedDashboardWindow

    managed = ManagedDashboardWindow(sample=True)
    requests: list[bool] = []
    managed.close_requested.connect(lambda: requests.append(True))
    managed.show()
    app.processEvents()

    managed.close()
    assert requests == [True]
    assert managed.isVisible()

    managed.finish_close()
    assert not managed.isVisible()
    managed.deleteLater()
    app.processEvents()


def test_managed_close_finishes_only_after_controller_save_result(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui

    requests: list[str] = []
    closed: list[bool] = []
    manager = SimpleNamespace(
        close_pending=False,
        history=SimpleNamespace(save=lambda: None),
        confirm_discard_local_draft=lambda: False,
        state=pb.Snapshot(),
        configuration=SimpleNamespace(
            stale=False,
            dirty=False,
            revision=0,
            collect=lambda _base: pb.ExperimentConfiguration(),
        ),
        bridge=SimpleNamespace(
            request=lambda action, **_kwargs: requests.append(action) or True
        ),
        window=SimpleNamespace(
            dashboard=window.dashboard,
            devices=window.devices,
            finish_close=lambda: closed.append(True),
        ),
    )

    manager.cameras = SimpleNamespace(finished=lambda *_: None)
    manager.action_progress = SimpleNamespace(finished=lambda *_: False)
    manager.prompts = SimpleNamespace(operation_finished=lambda _action: None)
    ManagedGui.request_close(manager)
    assert manager.close_pending and not closed
    assert requests == ["save_configuration_history"]

    ManagedGui.command_finished(manager, "save_configuration_history", True, "Saved")
    assert not manager.close_pending
    assert closed == [True]


@pytest.mark.parametrize("connected", [False, True])
def test_runtime_gui_close_reopen_preserves_full_draft(
    app: QApplication, tmp_path: Path, connected: bool
) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_window import ManagedDashboardWindow
    from cephvr.shared.auth import Principal

    path = tmp_path / "runtime_gui.json"
    requests = []

    def create():
        window = ManagedDashboardWindow(sample=True)
        window.devices.cameras.refresh_inventory = lambda: None
        window.devices.microcontroller.scan_ports = lambda: None
        window.devices.projectors.discover_displays = lambda: None
        bridge = ControllerBridge(
            Principal("gui", str(uuid4()), "token"), 50051, 1024, (0,)
        )
        bridge.start = lambda: None
        bridge.request = lambda action, **kwargs: (
            requests.append((action, kwargs)) or True
        )
        manager = ManagedGui(window, bridge, gui_history_path=path)
        state = pb.Snapshot(controller_generation=str(uuid4()))
        state.session.phase = pb.SESSION_PHASE_CONFIGURATION
        state.configuration.revision = state.configuration_values.revision = 1
        state.configuration_values.current.subject = "controller accepted value"
        state.control.holder_client_id = bridge.principal.generation
        manager.connection_changed(True, "", 1, state.controller_generation)
        return window, manager, state

    first, manager, state = create()
    seed = first.snapshots.capture()
    manager.install_snapshot(1, state.controller_generation, state.SerializeToString())
    first.snapshots.restore(seed)
    first.dashboard.subject_id.setText("last GUI subject")
    first.dashboard.age.setText("unfinished age")
    first.protocol.assets.folders["root"].editor.setText(str(tmp_path / "assets"))
    first.devices.microcontroller.set_saved_pins("COM8", "D9", True, "D2", False)
    first.devices.spikeglx.rows["trial-state"][3].setText("12")
    expected = first.snapshots.validate(first.snapshots.capture())
    if not connected:
        manager.state = None
    first.show()
    first.close()
    assert path.exists()
    if connected:
        assert first.isVisible() and manager.close_pending
        manager.command_finished("save_configuration_history", False, "Control changed")
    assert not first.isVisible()
    assert state.configuration_values.current.subject == "controller accepted value"
    assert not any(action == "submit_configuration" for action, _ in requests)

    second, reopened, fresh = create()
    reopened.install_snapshot(1, fresh.controller_generation, fresh.SerializeToString())
    assert second.snapshots.capture() == expected
    assert reopened.configuration.dirty and reopened.configuration.tracking_dirty
    assert fresh.configuration_values.current.subject == "controller accepted value"
    reopened.install_snapshot(1, fresh.controller_generation, fresh.SerializeToString())
    assert second.snapshots.capture() == expected
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.synchronization.v1 import spikeglx_pb2 as sync_pb

    inventory = rpc.SpikeGLXInventorySnapshot(
        configuration_revision=1,
        file_sha256="current-file-digest",
        backend_enabled=False,
        address="startup-host",
        command_port=4142,
    )
    inventory.pulse_channels.add(
        role=sync_pb.PULSE_ROLE_TRIAL_STATE,
        family=sync_pb.STREAM_FAMILY_ONEBOX,
        stream_index=0,
        channel_index=99,
    )
    reopened.display_operations.install_inventory(
        1, fresh.controller_generation, inventory.SerializeToString()
    )
    assert second.devices.spikeglx.rows["trial-state"][3].text() == "12"
    assert second.devices.spikeglx.inventory_file_sha256 == "current-file-digest"
    reopened.state = None
    second.close()
    for window, owner in ((first, manager), (second, reopened)):
        owner.tracking_diagnostics.timer.stop()
        window.deleteLater()
    app.processEvents()


def test_disconnected_projector_draft_restores_and_saves(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.gui_history import GuiHistory
    from cephvr.gui.projector_prerequisites import NO_PROJECTORS_MESSAGE

    panel = window.devices.projectors
    panel.assignments = {"saved-front": "Front", "saved-left": "Left"}
    panel.participation = {"saved-front": True, "saved-left": False}
    panel.update_participation()
    saved = window.snapshots.capture()
    panel.review_displays = ()
    panel.discover_displays()
    window.snapshots.restore(window.snapshots.validate(saved))
    assert panel.keys == []
    assert panel.assignments == saved["projectors"]["assignments"]
    assert panel.participation == saved["projectors"]["participation"]
    assert panel.enabled_screens == ("Front",)
    assert NO_PROJECTORS_MESSAGE in panel.console.toPlainText()
    assert NO_PROJECTORS_MESSAGE in panel.status_column.hud.toPlainText()
    field = panel.calibration_files.fields["screens.Front.valid_width_px"]
    field.setText("12")
    history = GuiHistory(window.snapshots, tmp_path / "runtime_gui.json")
    history.restore()
    history.save()
    field.setText("20")
    assert GuiHistory(window.snapshots, history.path).restore()
    assert float(field.text()) == 12


def test_setup_without_projectors_logs_and_submits_nothing(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.main import ManagedGui

    panel = window.devices.projectors
    panel.review_displays = ()
    requests = []
    gui = SimpleNamespace(
        window=window,
        bridge=SimpleNamespace(request=lambda *args, **kw: requests.append(args)),
    )
    # Refresh on click must replace even a stale inventory from before power-off.
    panel.keys = ["previously-connected"]
    window.dashboard.action_requested.disconnect()
    window.dashboard.action_requested.connect(
        lambda action: ManagedGui.request_dashboard_action(gui, action)
    )
    window.dashboard.apply_view(DashboardView(connected=True, has_control=True))
    setup = window.dashboard.command_buttons["Start"]
    assert setup.isEnabled()
    setup.click()
    assert requests == []
    assert panel.keys == []
    message = window.dashboard.log_console.toPlainText()
    assert "Setup not submitted" in message
    assert "No available projectors have been identified" in message
    assert "turn on" in message


def test_runtime_gui_save_failure_keeps_window_open_and_previous_file(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import main
    from cephvr.gui.gui_history import GuiHistory
    from cephvr.gui.managed_window import ManagedDashboardWindow

    window = ManagedDashboardWindow(sample=True)
    path = tmp_path / "runtime_gui.json"
    history = GuiHistory(window.snapshots, path)
    history.save()
    old = path.read_bytes()
    history.restore_attempted = True
    window.dashboard.subject_id.setText("changed")
    manager = SimpleNamespace(
        window=window,
        history=history,
        close_pending=False,
        state=None,
        bridge=SimpleNamespace(
            request=lambda *_: pytest.fail("No controller request on save failure")
        ),
    )

    def fail_write(*_args):
        raise OSError("disk write failed")

    monkeypatch.setattr("cephvr.gui.gui_history.write_snapshot", fail_write)
    monkeypatch.setattr(main, "save_failure_choice", lambda *_args, **_kwargs: None)
    window.close_requested.connect(lambda: main.ManagedGui.request_close(manager))
    window.show()
    window.close()
    assert window.isVisible() and path.read_bytes() == old
    window.finish_close()
    window.deleteLater()
    app.processEvents()


def test_runtime_gui_unrestored_file_is_preserved(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.gui_history import GuiHistory

    path = tmp_path / "runtime_gui.json"
    path.write_bytes(b"unreadable previous GUI configuration")
    history = GuiHistory(window.snapshots, path)
    with pytest.raises(ValueError, match="preserved"):
        history.save()
    with pytest.raises(ValueError):
        history.restore()
    with pytest.raises(ValueError, match="preserved"):
        history.save()
    assert path.read_bytes() == b"unreadable previous GUI configuration"


@pytest.mark.asyncio
async def test_managed_bridge_claims_free_control_for_history_save() -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    calls: list[str] = []
    state = pb.Snapshot()

    async def claim_control() -> None:
        calls.append("claim")
        state.control.holder_client_id = "gui-generation"

    async def execute(method: str) -> SimpleNamespace:
        calls.append(method)
        return SimpleNamespace(succeeded=True)

    client = SimpleNamespace(
        snapshot=state, claim_control=claim_control, execute=execute
    )
    await bridge._dispatch(client, "save_configuration_history", {})

    assert calls == ["claim", "SaveConfigurationHistory"]


@pytest.mark.parametrize("legacy_crop", [False, True])
def test_review_draft_restores_local_configuration(
    app: QApplication, tmp_path: Path, legacy_crop: bool
) -> None:
    from cephvr.gui.review_draft import load_review_draft, save_review_draft

    path = tmp_path / "review_draft.json"
    first = DashboardWindow(sample=True)
    ReviewControls(first)
    first.dashboard.subject_id.setText("LAST-SUBJECT")
    first.recordings.spikeglx.setChecked(legacy_crop)
    first.dashboard.set_species(
        "Sepia Latimanus" if legacy_crop else "Sepioteuthis lessoniana"
    )
    first.devices.cameras.drafts[0].values["trigger_frequency_hz"] = "30"
    first.devices.microcontroller.set_saved_pins("COM8", "D9", True, "D2", True)
    first.devices.microcontroller.pin_editors["behavioral"].setText("D10")
    first.devices.microcontroller.pin_editors["eye_tracking"].setText("D12")
    first.protocol.editor.drafts[0].name = "Last trial"
    first.devices.projectors.rig_editor.fields["width"].setText("250")
    first.devices.projectors.calibration.controls["Front", "offset_x_px"].setText("15")
    first.devices.spikeglx.editors[0].setText("10.0.0.2")  # type: ignore[attr-defined]
    first.devices.spikeglx.rows[first.devices.cameras.drafts[0].key][4].setText("0")
    first.devices.spikeglx.add_input.click()
    save_review_draft(first, path)
    if legacy_crop:
        import json

        saved = json.loads(path.read_text())
        saved["tracking"]["preprocessing"].pop("region")
        saved["tracking"].pop("annotation_source")
        path.write_text(json.dumps(saved))
    preserved = path.read_bytes()

    second = DashboardWindow(sample=True)
    ReviewControls(second)
    assert load_review_draft(second, path)
    assert load_review_draft(second, path)  # Opening again must not repeat the warning.
    assert path.read_bytes() == preserved
    assert second.tracking.snapshot() == first.tracking.snapshot()
    assert second.dashboard.subject_id.text() == "LAST-SUBJECT"
    assert second.recordings.spikeglx.isChecked() == legacy_crop
    assert (
        second.dashboard.species.currentText() == first.dashboard.species.currentText()
    )
    assert second.devices.cameras.drafts[0].values["trigger_frequency_hz"] == "30"
    assert second.devices.microcontroller.trial_pin.text() == "9"
    assert second.devices.microcontroller.flip_pin.text() == "2"
    assert second.devices.microcontroller.pin_editors["behavioral"].text() == "10"
    assert second.devices.microcontroller.pin_editors["eye_tracking"].text() == "12"
    assert second.protocol.editor.drafts[0].name == "Last trial"
    assert second.devices.projectors.rig_editor.fields["width"].text() == "250"
    assert (
        second.devices.projectors.calibration.controls["Front", "offset_x_px"].text()
        == "15"
    )
    assert second.devices.spikeglx.editors[0].text() == "10.0.0.2"  # type: ignore[attr-defined]
    assert (
        second.devices.spikeglx.rows[second.devices.cameras.drafts[0].key][4].text()
        == "0"
    )
    assert second.devices.spikeglx.rows["custom:custom-1"][4].text() == ""
    second.devices.spikeglx.add_input.click()
    assert "custom:custom-2" in second.devices.spikeglx.rows
    for item in (first, second):
        item.close()
        item.deleteLater()
    app.processEvents()


def test_legacy_review_draft_camera_pin_migrates_to_logical_role(
    app: QApplication, tmp_path: Path
) -> None:
    import json

    from cephvr.gui.review_draft import load_review_draft, save_review_draft

    path = tmp_path / "legacy-review.json"
    first = DashboardWindow(sample=True)
    ReviewControls(first)
    save_review_draft(first, path)
    legacy = json.loads(path.read_text())
    legacy["format_version"] = 1
    legacy["microcontroller"].pop("camera_pins")
    legacy["cameras"][0]["pin"] = "D8"
    legacy["cameras"][0]["role"] = "Eye tracking"
    legacy["projectors"]["screens"]["Bottom"] = {"width": "94", "height": "126"}
    path.write_text(json.dumps(legacy))
    second = DashboardWindow(sample=True)
    ReviewControls(second)
    assert load_review_draft(second, path)
    assert second.devices.microcontroller.pin_editors["eye_tracking"].text() == "8"
    assert second.devices.microcontroller.pin_editors["behavioral"].text() == ""
    assert (
        second.devices.projectors.screen_editor.fields["Bottom", "width"].text()
        == "126"
    )
    assert (
        second.devices.projectors.screen_editor.fields["Bottom", "height"].text()
        == "94"
    )
    first.close()
    second.close()
    app.processEvents()


def test_review_window_saves_draft_on_close(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import review
    from cephvr.gui.review_draft import load_review_draft

    path = tmp_path / "review_draft.json"
    monkeypatch.setattr(review, "draft_path", lambda: path)
    first = review.ReviewDashboardWindow(sample=True)
    review.ReviewControls(first)
    first.dashboard.subject_id.setText("CLOSE-SUBJECT")
    first.show()
    app.processEvents()
    first.close()

    second = DashboardWindow(sample=True)
    review.ReviewControls(second)
    assert load_review_draft(second, path)
    assert second.dashboard.subject_id.text() == "CLOSE-SUBJECT"
    for item in (first, second):
        item.close()
        item.deleteLater()
    app.processEvents()


def test_invalid_review_draft_is_not_replaced_during_load(
    app: QApplication, tmp_path: Path
) -> None:
    from cephvr.gui.review_draft import load_review_draft

    path = tmp_path / "review_draft.json"
    path.write_bytes(b"{bad json")
    window = DashboardWindow(sample=True)
    ReviewControls(window)
    with pytest.raises(ValueError):
        load_review_draft(window, path)
    assert path.read_bytes() == b"{bad json"
    window.close()
    window.deleteLater()
    app.processEvents()


def test_pin_test_stop_toggle_and_invalidation(
    window: DashboardWindow, app: QApplication
) -> None:
    panel = window.devices.microcontroller
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(1)
    panel.port.addItem("COM7", "COM7")
    panel.port.setCurrentIndex(0)
    panel.trial_pin.setText("3")
    control = panel.test_buttons["trial-state"]
    app.processEvents()
    original_size = control.size()
    control.click()
    app.processEvents()
    assert control.text() == "Stop"
    assert control.size() == original_size
    assert not panel.trial_pin.isEnabled() and not panel.port.isEnabled()
    control.click()
    assert control.text() == "Test"
    assert panel.trial_pin.isEnabled() and panel.port.isEnabled()
    control.click()
    window.apply_view(review_view(Phase.RUNNING))
    assert control.text() == "Test"
    assert not panel.review_tests
    window.apply_view(review_view(Phase.CONFIGURATION))
    control.click()
    panel.port.clear()
    assert control.text() == "Test"
    assert not panel.review_tests


def test_microcontroller_enablement_preserves_pins_and_syncs_cameras(
    window: DashboardWindow,
) -> None:
    panel = window.devices.microcontroller
    cameras = window.devices.cameras
    panel.port.addItem("COM7", "COM7")
    panel.port.setCurrentIndex(0)
    panel.trial_pin.setText("3")
    panel.flip_pin.setText("3")
    panel.enable_controls["projector-flip"].click()
    assert not panel.flip_pin.isEnabled()
    panel.test_pin("trial-state")
    assert "trial-state" in panel.review_tests  # Disabled input causes no conflict.
    panel.enable_controls["trial-state"].click()
    assert not panel.review_tests
    assert panel.test_buttons["trial-state"].text() == "Test"
    assert not panel.test_buttons["trial-state"].isEnabled()
    panel.test_pin("trial-state")
    panel.test_pin("projector-flip")
    assert not panel.review_tests
    panel.enable_controls["trial-state"].click()
    assert panel.trial_pin.text() == "3" and panel.trial_pin.isEnabled()

    cameras.trigger_source.setCurrentText("External controller")
    cameras.fields["trigger_frequency_hz"].setText("120")
    panel.pin_editors["behavioral"].setText("5")
    panel.test_pin("behavioral")
    assert "behavioral" in panel.review_tests
    cameras.enable_controls[0].click()
    assert not cameras.drafts[0].enabled
    assert not cameras.enable_controls[0].isChecked()
    assert not panel.review_tests
    assert panel.pin_editors["behavioral"].isEnabled()
    panel.test_pin("behavioral")
    assert "behavioral" in panel.review_tests
    panel.test_pin("behavioral")
    panel.signals.remove("behavioral")
    assert not cameras.drafts[0].enabled
    assert panel.pin_editors["behavioral"].text() == ""
    assert not panel.review_tests
    window.apply_view(review_view(Phase.RUNNING))
    assert not any(c.isEnabled() for c in panel.enable_controls.values())


def test_projectors_number_secondary_screens_by_position(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PyQt6.QtCore import QRect

    from cephvr.gui import projectors

    class Screen:
        def __init__(self, name, x):
            self.identity = name
            self.x = x

        def name(self):
            return self.identity

        def manufacturer(self):
            return ""

        def model(self):
            return ""

        def serialNumber(self):
            return ""

        def geometry(self):
            return QRect(self.x, 0, 1920, 1080)

        def devicePixelRatio(self):
            return 1

    main, left, right = Screen("main", 0), Screen("left", -3840), Screen("right", -1280)
    monkeypatch.setattr(
        projectors.QGuiApplication, "screens", lambda: [right, main, left]
    )
    monkeypatch.setattr(projectors.QGuiApplication, "primaryScreen", lambda: main)
    panel = window.devices.projectors
    panel.request("Refresh displays")
    assert panel.table.rowCount() == 2
    assert panel.keys == ["left|||", "right|||"]
    assert [panel.table.item(row, 1).text() for row in range(2)] == ["1", "2"]
    assert [index for index, _ in panel.diagram.outputs] == ["1", "2"]
    panel.projectors[panel.keys[0]].setCurrentText("Front")
    monkeypatch.setattr(
        projectors.QGuiApplication, "screens", lambda: [left, right, main]
    )
    panel.request("Refresh displays")
    assert panel.table.item(0, 1).text() == "1"
    assert panel.projectors[panel.keys[0]].currentText() == "Front"
    left.x, right.x = -1000, -3840
    panel.request("Refresh displays")
    assert panel.keys == ["right|||", "left|||"]
    assert panel.projectors["left|||"].currentText() == "Front"
    assert panel.table.item(1, 1).text() == "2"
    monkeypatch.setattr(projectors.QGuiApplication, "screens", lambda: [main])
    panel.request("Refresh displays")
    assert panel.table.rowCount() == 0
    assert panel.diagram.outputs == [] and panel.diagram.refreshed


def test_microcontroller_row_heights_match(
    window: DashboardWindow, app: QApplication
) -> None:
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(1)
    app.processEvents()
    panel = window.devices.microcontroller
    assert panel.trial_pin.height() == panel.test_buttons["trial-state"].height()
    assert panel.flip_pin.height() == panel.test_buttons["projector-flip"].height()
    for key, pin in panel.pin_editors.items():
        assert pin.height() == panel.test_buttons[key].height()
        for control in (pin, panel.test_buttons[key]):
            assert control.parentWidget().rect().contains(control.geometry())
            assert control.height() >= control.sizeHint().height()


def test_projector_geometry_and_pulse_drafts_are_independent(window: DashboardWindow):
    panel = window.devices.projectors
    timing = panel.timing
    timing.set_displays([("on", "Display 2", True), ("off", "Display 4", False)])
    timing.target.setCurrentIndex(timing.target.findData("off"))
    timing.pulse.click()
    timing.fields["Width"].setText("40")
    timing.pulse.click()
    assert timing.target.currentData() == "off"
    assert timing.fields["Width"].text() == "40"
    assert not timing.target.isEnabled() and timing.mode.isEnabled()
    rig = panel.rig_editor
    for key, value in zip(rig.fields, (200, 300, 150, 100, 100, 75), strict=True):
        rig.fields[key].setText(str(value))
    assert panel.tank.rig is not None and panel.tank.rig.subject == (100, 100, 75)
    import json
    from types import SimpleNamespace

    from cephvr.visual_stimulus.config.models.display_profile import Geometry
    from cephvr.visual_stimulus.rendering.arena import off_axis_view_projection

    assert not hasattr(rig, "projection_fields")
    draft = {
        face: {"width": "200", "height": "150", "subject_distance": "200"}
        for face in ("Front", "Left", "Right", "Bottom")
    }
    geometry = Geometry.model_validate_json(json.dumps(rig.geometry_payload(draft)))
    assert len(geometry.surfaces) == 4
    for surface in geometry.surfaces:
        assert off_axis_view_projection(SimpleNamespace(geometry=geometry), surface)
    screen = panel.screen_editor
    screen.fields["Front", "distance"].setText("600")
    screen.fields["Front", "throw"].setText("1.2")
    assert screen.drafts["Front"]["distance"] == "600"
    screen.fields["Bottom", "width"].setText("200")
    assert screen.fields["Front", "distance"].text() == "600"
    window.apply_view(review_view(Phase.RUNNING))
    assert not rig.isEnabled() and not timing.mode.isEnabled()


def test_configuration_scroll_keeps_projector_status_fixed(
    window: DashboardWindow, app: QApplication
):
    window.resize(1175, 800)
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(2)
    panel = window.devices.projectors
    assert [panel.setup_tabs.tabText(i) for i in range(3)] == [
        "Screen calibration",
        "Rig geometry",
        "Synchronization",
    ]
    panel.setup_tabs.setCurrentIndex(1)
    app.processEvents()
    top = panel.layout_card.mapTo(window, QPoint())
    log = panel.status_column.log_card.mapTo(window, QPoint())
    scroll = panel.config_scroll.verticalScrollBar()
    assert scroll.maximum() > 0
    scroll.setValue(scroll.maximum())
    app.processEvents()
    assert panel.layout_card.mapTo(window, QPoint()) == top
    assert panel.status_column.log_card.mapTo(window, QPoint()) == log
    assert panel.config_scroll.horizontalScrollBar().maximum() == 0


def test_calibration_and_screen_dimensions_retain_separate_drafts(
    window: DashboardWindow,
):
    panel = window.devices.projectors
    panel.calibration.controls["Front", "valid_width_px"].setText("1.2")
    panel.calibration.controls["Front", "flip_x"].setChecked(True)
    panel.screen_editor.fields["Front", "width"].setText("200")
    assert panel.screen_editor.drafts["Front"]["valid_width_px"] == "1.2"
    assert panel.screen_editor.drafts["Front"]["flip_x"] == "True"
    assert panel.screen_editor.fields["Front", "width"].text() == "200"


def test_spikeglx_sources_preserve_maps_and_follow_enablement(window: DashboardWindow):
    devices = window.devices
    panel = devices.spikeglx
    panel.set_sources((), frozenset())
    assert panel.table.horizontalHeader().isHidden()
    assert panel.table.height() == 2 * panel.table.frameWidth()
    devices.sync_inputs()
    assert not panel.table.horizontalHeader().isHidden()
    camera = devices.cameras.drafts[0]
    panel.rows[camera.key][3].setText("3")
    camera.enabled = False
    devices.cameras.drafts_changed.emit()
    assert not panel.rows[camera.key][3].isEnabled()
    camera.enabled = True
    devices.cameras.drafts_changed.emit()
    assert panel.rows[camera.key][3].text() == "3"
    assert panel.rows[camera.key][3].isEnabled()
    devices.projectors.timing.pulse.setChecked(True)
    panel.rows["photodiode"][3].setText("7")
    devices.projectors.timing.pulse.setChecked(False)
    assert panel.rows["photodiode"][3].isHidden()
    devices.projectors.timing.pulse.setChecked(True)
    assert panel.rows["photodiode"][3].text() == "7"
    panel.add_input.click()
    assert "custom:custom-1" in panel.rows
    window.apply_view(review_view(Phase.RUNNING))
    assert not panel.rows["custom:custom-1"][3].isEnabled()
    assert not panel.add_input.isEnabled()


def test_projector_config_tabs_keep_column_width_and_table_drafts(
    window: DashboardWindow, app: QApplication
):
    window.resize(1175, 800)
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(2)
    panel = window.devices.projectors
    widths = []
    for index in (0, 1, 2, 0):
        panel.setup_tabs.setCurrentIndex(index)
        app.processEvents()
        widths.append(
            (
                panel.config_scroll.viewport().width(),
                panel.configuration.width(),
                panel.columns[1].x(),
            )
        )
    assert len(set(widths)) == 1
    assert not hasattr(panel.timing, "pacing")
    for face, value in (
        ("Front", "200"),
        ("Left", "300"),
        ("Right", "310"),
        ("Bottom", "400"),
    ):
        panel.screen_editor.fields[face, "width"].setText(value)
        assert panel.screen_editor.drafts[face]["width"] == value
    assert panel.screen_editor.fields["Front", "width"].text() == "200"


def test_screen_distance_moves_planes_independently_of_tank():
    from cephvr.gui.projector_geometry import RigDimensions, screen_corners

    rig = RigDimensions(200, 300, 150, (80, 100, 75))
    distances = {
        "Front": (1, -50),
        "Left": (0, -70),
        "Right": (0, 230),
        "Bottom": (2, -75),
    }
    values = {"width": "200", "height": "150", "subject_distance": "150"}
    for face, (axis, coordinate) in distances.items():
        corners = screen_corners(
            rig, face, values, front_distance="150", bottom_distance="150"
        )
        assert all(p[axis] == coordinate for p in corners)
    assert rig.subject == (80, 100, 75)
    for distance in ("", "0", "-1", "nan", "inf"):
        with pytest.raises(ValueError):
            screen_corners(rig, "Front", dict(values, subject_distance=distance))


def test_hidden_scrollbar_preserves_wheel_scrolling(
    window: DashboardWindow, app: QApplication
):
    from PyQt6.QtGui import QWheelEvent

    window.resize(1175, 800)
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(2)
    panel = window.devices.projectors
    panel.setup_tabs.setCurrentIndex(2)
    app.processEvents()
    scroll = panel.config_scroll
    assert scroll.verticalScrollBar().sizeHint().width() == 0
    assert scroll.horizontalScrollBar().sizeHint().height() == 0
    event = QWheelEvent(
        QPoint(20, 20).toPointF(),
        QPoint(20, 20).toPointF(),
        QPoint(),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(scroll.viewport(), event)
    assert scroll.verticalScrollBar().value() > 0
    assert all(len(row) == 5 for row in window.devices.spikeglx.rows.values())


def test_all_screen_calibration_json_roundtrip_and_rejection(
    window: DashboardWindow, tmp_path: Path
):
    import json

    panel = window.devices.projectors
    files = panel.calibration_files
    panel.rig_editor.fields["width"].setText("200")
    panel.rig_editor.screen_distances["Left"].setText("150")
    panel.calibration.controls["Bottom", "valid_width_px"].setText("125")
    panel.calibration.controls["Right", "flip_x"].setChecked(True)
    path = tmp_path / "calibration.json"
    panel.assignments["local-display"] = "Front"
    panel.participation["local-display"] = False
    expected = files.snapshot()
    assert not any(key.startswith("projection.") for key in expected["values"])
    assert not any(
        "display" in key or "assignment" in key or "participation" in key
        for key in expected["values"]
    )
    files.save_path(str(path))
    assert json.loads(path.read_text()) == expected
    panel.rig_editor.fields["width"].setText("300")
    panel.calibration.controls["Right", "flip_x"].setChecked(False)
    files.load_path(str(path))
    assert files.snapshot() == expected
    assert panel.assignments == {"local-display": "Front"}
    assert panel.participation == {"local-display": False}
    assert panel.rig_editor.screen_distances["Left"].text() == "150.0"
    assert ("Left", "subject_distance") not in panel.screen_editor.fields
    assert panel.screen_editor.drafts["Bottom"]["valid_width_px"] == "125"
    assert panel.screen_editor.drafts["Right"]["flip_x"] == "True"
    legacy = json.loads(json.dumps(expected))
    legacy["values"].update(
        {
            "projection.near_mm": 20,
            "projection.far_mm": 2000,
            "projection.positional_tolerance_mm": 0.1,
            "projection.orthogonality_tolerance": 0.01,
        }
    )
    files.apply_snapshot(legacy)
    assert files.snapshot() == expected
    old = json.loads(json.dumps(expected))
    old["version"] = 9
    old["values"] = {
        k: v
        for k, v in old["values"].items()
        if not k.endswith(("offset_x_px", "offset_y_px"))
    }
    for face in ("Front", "Left", "Right", "Bottom"):
        old["values"][f"screens.{face}.offset_x"] = 12.5
        old["values"][f"screens.{face}.offset_y"] = -20.2
    old["values"]["screens.Bottom.valid_width_px"] = 125.2
    files.apply_snapshot(old)
    assert files.snapshot() == expected
    for key, value in (("offset_x_px", "12"), ("offset_y_px", "-7")):
        panel.calibration.controls["Bottom", key].setText(value)
    translated = files.snapshot()
    files.apply_snapshot(expected)
    files.apply_snapshot(translated)
    assert files.snapshot() == translated
    assert panel.calibration.controls["Bottom", "offset_y_px"].text() == "-7"
    files.apply_snapshot(expected)
    invalid_size = files.snapshot()
    invalid_size["values"]["screens.Bottom.valid_width_px"] = 125.2
    with pytest.raises(ValueError, match="whole pixel"):
        files.apply_snapshot(invalid_size)
    assert files.snapshot() == expected
    invalid = files.snapshot()
    invalid["values"]["screens.Left.subject_distance"] = -10
    path.write_text(json.dumps(invalid))
    files.load_path(str(path))
    assert files.snapshot() == expected
    assert "load failed" in panel.console.toPlainText()
    window.apply_view(review_view(Phase.RUNNING))
    files.save_path(str(tmp_path / "blocked.json"))
    assert not (tmp_path / "blocked.json").exists()


def test_calibration_dialog_closes_on_authority_loss(window: DashboardWindow):
    files = window.devices.projectors.calibration_files
    files.choose(save=False)
    dialog = files.dialog
    assert dialog is not None
    window.apply_view(review_view(Phase.RUNNING))
    assert files.dialog is None
    assert not dialog.isVisible()


@pytest.mark.parametrize("focused", [False, True])
def test_wheel_never_changes_input_values(
    window: DashboardWindow, app: QApplication, focused: bool
):
    from PyQt6.QtGui import QWheelEvent

    from cephvr.gui.components import combo, decimal_field

    panel = window.devices.projectors
    window.resize(1175, 800)
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(2)
    panel.setup_tabs.setCurrentIndex(2)
    for editor in (combo(("One", "Two")), decimal_field(5)):
        panel.screen_editor.body.addWidget(editor)
        app.processEvents()
        if focused:
            editor.setFocus()
        panel.config_scroll.verticalScrollBar().setValue(0)
        event = QWheelEvent(
            QPoint(10, 10).toPointF(),
            QPoint(10, 10).toPointF(),
            QPoint(),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(editor, event)
        assert (
            editor.currentIndex() == 0
            if hasattr(editor, "currentIndex")
            else editor.value() == 5
        )
        assert panel.config_scroll.verticalScrollBar().value() > 0


def test_epoch_clock_duration_retains_fractional_precision() -> None:
    from cephvr.gui.formatting import clock_duration, parse_clock_duration

    assert parse_clock_duration("01:02:03.000000001") == "3723.000000001"
    assert clock_duration("3723.000000001") == "01:02:03.000000001"
    for invalid in ("62", "1:02:03", "00:60:00", "00:00:60", "00:00:00.1234567890"):
        with pytest.raises(ValueError):
            parse_clock_duration(invalid)


def test_batch_variation_sweep_is_bounded(app: QApplication) -> None:
    from cephvr.gui.batch_variation import BatchVariationRow

    row = BatchVariationRow([("Left · Texture", (0,), 0, "texture")])
    row.method.setCurrentIndex(1)
    row.values.setText("0, 1, 0.25")
    assert tuple(float(v) for v in row.read_rules()[0].values) == (
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    )
    row.values.setText("0, 1000, 0.1")
    with pytest.raises(ValueError, match="512"):
        row.read_rules()
    row.deleteLater()


def test_epoch_reference_updates_do_not_show_detached_windows(
    app: QApplication,
) -> None:
    from PyQt6.QtCore import QEvent, QObject

    from cephvr.gui.epoch_composer import EpochComposer
    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.stimulus_presets import add_stimulus

    class DetachedWindowTrace(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.shown: list[QWidget] = []

        def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
            if (
                isinstance(watched, QWidget)
                and watched.isWindow()
                and event is not None
                and event.type() == QEvent.Type.Show
            ):
                self.shown.append(watched)
            return False

    trace = DetachedWindowTrace()
    app.installEventFilter(trace)
    try:
        composer = EpochComposer()
        composer.set_screens(("Front", "Left", "Right", "Bottom"))
        composer.program = add_stimulus(composer.program, 0, "Sine grating", ("Left",))
        composer.refresh_rows()
        motion = next(
            form
            for form in composer.rows["Left"].parameters.forms
            if isinstance(form, EpochMotion)
        )
        motion.speed.setText("12")
        motion.speed.textEdited.emit("12")
        assert composer.rows["Left"].parameters.apply()
        composer.change_type("Left", "Texture")
        composer.refresh_rows()
        composer.duration.setText("00:00:03")
        composer.update_duration()
        assert not trace.shown
        composer.deleteLater()
    finally:
        app.removeEventFilter(trace)


def test_spikeglx_disable_restore_and_remove_custom(window: DashboardWindow):
    panel = window.devices.spikeglx
    key = window.devices.cameras.drafts[0].key
    panel.rows[key][3].setText("4")
    panel.enable_controls[key].click()
    assert not panel.rows[key][3].isEnabled()
    panel.enable_controls[key].click()
    assert panel.rows[key][3].isEnabled() and panel.rows[key][3].text() == "4"
    assert key not in panel.remove_buttons
    panel.add_input.click()
    panel.remove_buttons["custom:custom-1"].click()
    assert "custom:custom-1" not in panel.rows
    panel.add_input.click()
    window.apply_view(review_view(Phase.RUNNING))
    panel.remove_custom("custom:custom-2")
    assert "custom:custom-2" in panel.rows


def test_right_screen_is_derived_and_legacy_asymmetry_rejected(
    window: DashboardWindow, tmp_path: Path
):
    import json

    from cephvr.gui.projector_geometry import screen_corners

    panel = window.devices.projectors
    rig = panel.rig_editor
    assert set(rig.screen_distances) == {"Left", "Front", "Bottom"}
    for key, value in zip(rig.fields, (200, 300, 150, 80, 100, 75), strict=True):
        rig.fields[key].setText(str(value))
    rig.screen_distances["Left"].setText("130")
    panel.screen_editor.fields["Right", "width"].setText("200")
    panel.screen_editor.fields["Right", "height"].setText("150")
    assert panel.tank.screens["Right"]["subject_distance"] == "170.0"
    corners = screen_corners(
        rig.dimensions(),
        "Right",
        panel.tank.screens["Right"],
        front_distance="150",
        bottom_distance="95",
    )
    assert all(p[0] == 250 for p in corners)
    payload = panel.calibration_files.snapshot()
    assert "screens.Right.subject_distance" not in payload["values"]
    legacy = dict(
        format=payload["format"],
        version=1,
        values=dict(payload["values"], **{"screens.Right.subject_distance": 170}),
    )
    for face in ("Front", "Left", "Right", "Bottom"):
        for old, new in (("scale_u", "valid_width_px"), ("scale_v", "valid_height_px")):
            legacy["values"].pop(f"screens.{face}.{new}")
            legacy["values"][f"screens.{face}.{old}"] = None
    legacy["values"] = {
        k: v for k, v in legacy["values"].items() if "reference_" not in k
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy))
    panel.calibration_files.load_path(str(path))
    assert panel.calibration_files.snapshot() == payload
    legacy["values"]["screens.Right.subject_distance"] = 100
    legacy["values"]["rig.width"] = 500
    path.write_text(json.dumps(legacy))
    panel.calibration_files.load_path(str(path))
    assert panel.calibration_files.snapshot() == payload
    assert "unequal" in panel.console.toPlainText()
    rig.fields["subject_x"].setText("90")
    assert panel.tank.screens["Right"]["subject_distance"] == "150.0"
    rig.screen_distances["Left"].clear()
    assert panel.tank.screens["Right"]["subject_distance"] == ""


def test_managed_protocol_roundtrips_ordered_trials_seed_and_gap(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb
    from cephvr.gui.protocol_document import blank_program

    config = control_pb.ExperimentConfiguration(
        mode=control_pb.SESSION_MODE_CLOSED_LOOP, asset_root="/assets"
    )
    for number, label_text in enumerate(("first", "second"), start=1):
        trial = config.trials.add(trial_number=number)
        trial.stimulus.program.program_json = blank_program().model_dump_json()
        trial.stimulus.program.logical_source_reference = f"programs/{label_text}.json"
    config.trials[0].stimulus.stimulus_seed_decimal = "0"
    config.trials[
        0
    ].stimulus.arena_boundaries.boundaries_json = '{"format_version":1,"bindings":[]}'
    config.gaps.add(after_trial_number=1, minimum_duration_ns=1_250_000_000)

    page = window.protocol
    # Flat controller sources use the same grouped controls as new Review trials.
    from cephvr.gui.protocol_batches import grouped_program

    page.editor.set_program(grouped_program(blank_program()))
    assert page.editor.scope
    page.install_configuration(config)
    assert page.session_mode.currentText() == "Closed-loop"
    assert page.assets.folders["root"].editor.text() == "/assets"
    assert page.editor.drafts[0].stimulus_seed_decimal == "0"
    assert page.editor.drafts[0].gap_after_seconds == "1.25"
    assert page.editor.drafts[1].path == "programs/second.json"
    assert page.editor.scope == (0,)
    assert page.editor.path == (0, 0)
    assert not page.editor.subgroup.isHidden()
    assert page.editor.timeline.block_actions.enabled
    page.install_configuration(config)
    assert page.editor.scope == (0,)

    roundtrip = control_pb.ExperimentConfiguration()
    page.apply_schedule(roundtrip)
    assert [item.trial_number for item in roundtrip.trials] == [1, 2]
    assert [
        item.stimulus.program.logical_source_reference for item in roundtrip.trials
    ] == [
        "programs/first.json",
        "programs/second.json",
    ]
    assert roundtrip.trials[0].stimulus.stimulus_seed_decimal == "0"
    assert roundtrip.trials[0].stimulus.arena_boundaries == (
        config.trials[0].stimulus.arena_boundaries
    )
    assert roundtrip.trials[1].stimulus.arena_boundaries.boundaries_json == (
        '{"format_version":1,"bindings":[]}'
    )
    assert roundtrip.gaps[0].after_trial_number == 1
    assert roundtrip.gaps[0].minimum_duration_ns == 1_250_000_000
    assert [t.stimulus.program.program_json for t in roundtrip.trials] == [
        t.stimulus.program.program_json for t in config.trials
    ]

    from cephvr.gui.protocol_snapshot import capture_protocol, restore_protocol

    saved = capture_protocol(page)
    restore_protocol(page, saved)
    assert page.editor.scope == (0,)
    assert not page.editor.subgroup.isHidden()
    assert capture_protocol(page) == saved

    page.editor.subgroup.composer.duration.setText("00:01:01")
    page.editor.subgroup.apply()
    page.apply_schedule(roundtrip)
    assert roundtrip.trials[0].stimulus.program.program_json != (
        config.trials[0].stimulus.program.program_json
    )
    assert page.editor.program.sequence[0].body[0].duration.duration.seconds == "61"
    page.editor.undo()
    page.apply_schedule(roundtrip)
    assert roundtrip.trials[0].stimulus.program.program_json == (
        config.trials[0].stimulus.program.program_json
    )
    page.editor.add_subgroup()
    assert len(page.editor.program.sequence[0].body) == 2
    page.editor.add_group()
    assert len(page.editor.program.sequence) == 2
    page.apply_schedule(roundtrip)
    grouped_source = roundtrip.trials[0].stimulus.program.program_json
    page.install_configuration(roundtrip)
    assert len(page.editor.program.sequence) == 2
    page.apply_schedule(roundtrip)
    assert roundtrip.trials[0].stimulus.program.program_json == grouped_source


def test_managed_protocol_rejects_partial_restore_without_mutating_pages(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb

    page = window.protocol
    old_program = page.editor.program.model_dump_json()
    old_root = page.assets.folders["root"].editor.text()
    old_mode = page.session_mode.currentText()
    config = control_pb.ExperimentConfiguration(
        mode=control_pb.SESSION_MODE_CLOSED_LOOP, asset_root="/new-root"
    )
    valid = config.trials.add(trial_number=1)
    valid.stimulus.program.program_json = page.editor.program.model_dump_json()
    invalid = config.trials.add(trial_number=2)
    invalid.stimulus.program.program_json = "not a valid program"
    with pytest.raises(ValueError):
        page.install_configuration(config)
    assert page.editor.program.model_dump_json() == old_program
    assert page.assets.folders["root"].editor.text() == old_root
    assert page.session_mode.currentText() == old_mode


def test_empty_managed_schedule_is_not_replaced_by_review_trial(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb

    page = window.protocol
    page.install_configuration(
        control_pb.ExperimentConfiguration(mode=control_pb.SESSION_MODE_OPEN_LOOP)
    )
    candidate = control_pb.ExperimentConfiguration()
    with pytest.raises(ValueError, match="Add a managed trial"):
        page.apply_schedule(candidate)
    assert not candidate.trials


def test_managed_configuration_preserves_incomplete_draft_on_new_revision(
    window: DashboardWindow,
    app: QApplication,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    generation = str(uuid4())

    def snapshot(revision: int) -> control_pb.Snapshot:
        state = control_pb.Snapshot(
            controller_generation=generation, state_revision=revision
        )
        state.configuration.revision = revision
        state.configuration_values.revision = revision
        state.configuration_values.current.subject = "authoritative"
        return state

    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
        )
    )
    assert manager.install(snapshot(1))
    window.dashboard.subject_id.setFocus()
    QTest.keyClick(
        window.dashboard.subject_id, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
    )
    QTest.keyClicks(window.dashboard.subject_id, "local draft")
    assert manager.dirty
    original_program = window.protocol.editor.program.model_dump_json()

    assert not manager.install(snapshot(2))
    assert manager.stale
    assert window.dashboard.subject_id.text() == "local draft"
    assert window.protocol.editor.program.model_dump_json() == original_program


def test_empty_schedule_first_add_becomes_the_first_trial(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb

    page = window.protocol
    page.install_configuration(
        control_pb.ExperimentConfiguration(mode=control_pb.SESSION_MODE_OPEN_LOOP)
    )
    page.editor.add_button.click()
    assert len(page.editor.drafts) == 1
    assert page.editor.drafts[0].name == "Trial 1"
    proposal = control_pb.ExperimentConfiguration()
    page.apply_schedule(proposal)
    assert len(proposal.trials) == 1


def test_managed_configuration_keeps_post_submit_edits_on_ack(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    window.apply_view(review_view(Phase.CONFIGURATION))
    generation = str(uuid4())
    initial = control_pb.Snapshot(controller_generation=generation)
    initial.configuration.revision = 4
    initial.configuration_values.revision = 4
    initial.configuration_values.current.mode = control_pb.SESSION_MODE_OPEN_LOOP
    from tests.visual_stimulus.support import valid_display_json

    visual = initial.configuration_values.current.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    visual.visual_stimulus.display.profile_json = valid_display_json()
    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
        )
    )
    assert manager.install(initial)
    window.protocol.editor.add_button.click()
    submitted = manager.collect(initial.configuration_values.current)
    submitted_edit_serial = manager.edit_serial
    acknowledged = control_pb.Snapshot(controller_generation=generation)
    acknowledged.configuration.revision = 5
    acknowledged.configuration_values.revision = 5
    acknowledged.configuration_values.current.CopyFrom(submitted)

    editor = window.dashboard.subject_id
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, "1234")
    assert manager.edit_serial > submitted_edit_serial
    manager.note_installed_revision(
        acknowledged, submitted_edit_serial=submitted_edit_serial
    )
    assert manager.stale
    assert "newer local edits" in manager.last_error
    assert editor.text() == "1234"

    from PyQt6.QtGui import QAction

    from cephvr.gui.main import ManagedGui

    reload_action = QAction(window)
    gui = SimpleNamespace(
        state=acknowledged,
        configuration=manager,
        reload_configuration=reload_action,
        window=window,
        _connection_epoch=1,
        install_snapshot=lambda *_args: None,
    )
    ManagedGui.configuration_accepted(gui, 5, submitted_edit_serial)
    assert manager.stale and manager.dirty
    assert "newer local edits" in manager.last_error
    assert reload_action.isEnabled()


def test_managed_configuration_keeps_invalid_newer_epoch_draft_after_ack(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import types_pb2 as control_pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    generation = str(uuid4())
    initial = control_pb.Snapshot(controller_generation=generation)
    initial.configuration.revision = 4
    initial.configuration_values.revision = 4
    initial.configuration_values.current.mode = control_pb.SESSION_MODE_OPEN_LOOP
    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
        )
    )
    assert manager.install(initial)
    window.protocol.editor.enter_group()
    submitted_serial = manager.edit_serial
    duration = window.protocol.editor.subgroup.composer.duration
    duration.setFocus()
    QTest.keyClick(duration, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(duration, "not a duration")
    assert manager.dirty and manager.edit_serial > submitted_serial

    acknowledged = control_pb.Snapshot(controller_generation=generation)
    acknowledged.configuration.revision = 5
    acknowledged.configuration_values.revision = 5
    acknowledged.configuration_values.current.CopyFrom(
        initial.configuration_values.current
    )
    manager.note_installed_revision(
        acknowledged, submitted_edit_serial=submitted_serial
    )
    assert manager.dirty and manager.stale
    assert duration.text() == "not a duration"

    newer = control_pb.Snapshot(controller_generation=generation)
    newer.configuration.revision = 6
    newer.configuration_values.revision = 6
    newer.configuration_values.current.subject = "new controller value"
    assert not manager.install(newer)
    assert duration.text() == "not a duration"


def test_protocol_participation_and_asset_pages(window: DashboardWindow) -> None:
    from cephvr.gui.window import PAGES

    assert PAGES == ("Dashboard", "Protocol", "Devices", "Tracking")
    panel = window.protocol
    assert panel.assets.parent() is panel.config_scroll.widget()
    assert panel.program_card.isAncestorOf(panel.session_mode)
    window.page_buttons[1].click()
    assert window.stack.currentWidget() is panel
    assert set(window.recordings.record) == {"stimulus", "camera-1", "camera-2"}
    window.recordings.record["camera-1"].click()
    assert window.devices.cameras.drafts[0].enabled
    assert not window.recordings.record["camera-1"].isChecked()
    window.devices.cameras.set_participation(0, False)
    assert not window.devices.cameras.drafts[0].enabled
    assert not window.recordings.record["camera-1"].isEnabled()
    assert not window.recordings.record["camera-1"].isChecked()
    window.devices.cameras.set_participation(0, True)
    assert window.recordings.record["camera-1"].isEnabled()
    assert not panel.tracking_active
    assert not next(
        p for p in window.dashboard.view.previews if p.key == "tracking"
    ).active
    panel.session_mode.setCurrentText("Closed-loop")
    assert panel.tracking_active
    assert not window.recordings.velocities.isChecked()
    panel.session_mode.setCurrentText("Open-loop")
    assert not panel.tracking_active
    window.recordings.velocities.click()
    assert panel.tracking_active
    panel.session_mode.setCurrentText("Closed-loop")
    assert panel.tracking_active
    window.recordings.record["stimulus"].click()
    assert panel.tracking_active
    assert next(p for p in window.dashboard.view.previews if p.key == "stimulus").active
    assets = window.protocol.assets
    assets.folders["root"].editor.setText("/example/assets")
    window.apply_view(review_view(Phase.RUNNING))
    assert not panel.session_mode.isEnabled()
    assert not panel.editor.isEnabled()
    assert not any(c.isEnabled() for c in window.recordings.record.values())
    assert not window.recordings.velocities.isEnabled()
    assert not window.devices.spikeglx.pairing.isEnabled()
    assert not assets.folders["root"].isEnabled()
    window.apply_view(review_view(Phase.CONFIGURATION))
    assert assets.folders["root"].editor.text() == "/example/assets"


def test_protocol_program_validation_and_atomic_save(
    window: DashboardWindow, tmp_path: Path
) -> None:
    import json

    source = {
        "format_version": 2,
        "assets": [],
        "instances": [],
        "input_channels": [],
        "scenes": [
            {
                "scene_id": "blank",
                "background_linear_rgb": [0.0, 0.0, 0.0],
                "arena_instance_id": None,
                "layer_instance_ids": [],
            }
        ],
        "duration": {"kind": "explicit_epochs"},
        "sequence": [
            {
                "kind": "epoch",
                "epoch_id": "first",
                "scene_id": "blank",
                "duration": {"kind": "fixed", "duration": {"seconds": "60"}},
                "settings": [],
            }
        ],
    }
    panel = window.protocol
    path = tmp_path / "program.json"
    path.write_text(json.dumps(source))
    panel.load_program(str(path))
    assert not panel.message.isVisible()
    path = tmp_path / "program.json"
    panel.save_program(str(path))
    source["sequence"][0]["batch_label"] = ""
    source["sequence"][0]["batch_id"] = None
    source["sequence"][0]["subgroup_draft"] = None
    source["sequence"][0]["repetition_settings"] = []
    source["sequence"][0]["repetition_rules"] = []
    assert json.loads(path.read_text()) == source
    # Legacy root epochs are preserved; authoring is confined to groups.
    assert panel.editor.subgroup.isHidden()
    assert not panel.message.isVisible()
    panel.save_program(str(path))
    assert json.loads(path.read_text()) == source
    panel.load_program(str(path))
    assert json.loads(panel.editor.program.model_dump_json()) == source
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}")
    panel.load_program(str(invalid))
    assert json.loads(panel.editor.program.model_dump_json()) == source
    window.apply_view(review_view(Phase.RUNNING))
    blocked = tmp_path / "blocked.json"
    panel.save_program(str(blocked))
    assert not blocked.exists()


def test_protocol_timeline_edits_preserve_trials_and_imported_groups(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    from cephvr.visual_stimulus.config.models.program_model import (
        Group,
        parse_program_json,
    )

    window.page_buttons[1].click()
    panel = window.protocol
    editor = panel.editor
    open_protocol_group(editor)
    original = editor.program
    parse_program_json(original.model_dump_json(), max_bytes=1_048_576)
    editor.hierarchy.contents.setFocus()
    QTest.keyClick(editor.hierarchy.contents, Qt.Key.Key_Right)
    assert editor.path == (0, 1)
    editor.subgroup.composer.duration.setText("00:00:21.000000001")
    editor.subgroup.apply()
    edited = editor.program
    assert edited.sequence[0].body[1].duration.duration.seconds == "21.000000001"
    assert edited.sequence[0].body[1].settings == original.sequence[0].body[1].settings
    editor.subgroup.composer.duration.setText("not a duration")
    editor.subgroup.apply()
    assert editor.program == edited
    assert editor.subgroup.notice.isHidden()
    assert editor.subgroup.notice.dialog is not None
    editor.subgroup.notice.dialog.accept()
    editor.subgroup.discard()
    editor.add_button.click()
    assert editor.index == 1
    assert not any(
        control.text() in {"↑", "↓"}
        for control in editor.trial_card.findChildren(QPushButton)
    )
    app.processEvents()
    row_rect = editor.trials.visualItemRect(editor.trials.item(0))
    QTest.mouseClick(
        editor.trials.viewport(), Qt.MouseButton.LeftButton, pos=row_rect.center()
    )
    assert editor.index == 0
    assert editor.program == edited
    group = Group(
        kind="group",
        group_id="repeat",
        repetitions=2,
        order="shuffle_each_repetition",
        order_unit="child_blocks",
        conditions=None,
        body=edited.sequence[0].body,
    )
    grouped = edited.model_copy(update={"sequence": (group,)})
    editor.set_program(grouped)
    assert editor.path == (0, 0) and not editor.subgroup.isHidden()
    path = tmp_path / "group.json"
    panel.save_program(str(path))
    assert parse_program_json(path.read_text(), max_bytes=1_048_576) == grouped
    editor.add_button.click()
    panel.load_program(str(path))
    assert editor.program == grouped
    window.apply_view(review_view(Phase.RUNNING))
    count = len(editor.drafts)
    editor.add_trial()
    assert len(editor.drafts) == count
    app.processEvents()


def test_protocol_cards_reflow_and_keep_properties_reachable(
    window: DashboardWindow, app: QApplication
) -> None:
    from PyQt6.QtWidgets import QPlainTextEdit, QTableWidget

    from cephvr.gui.components import StatusColumn

    panel = window.protocol
    window.page_buttons[1].click()
    assert not panel.findChildren(StatusColumn)
    assert not panel.findChildren(QPlainTextEdit)
    assert panel.findChildren(QTableWidget) == [panel.editor.subgroup.variation_table]
    open_protocol_group(panel.editor)
    for width in (1175, 720, 1175):
        window.resize(width, 883)
        for _ in range(3):
            app.processEvents()
        editor = panel.editor
        for action in (editor.output_preview_button,):
            assert action.width() >= action.minimumSizeHint().width()
            assert action.width() <= action.sizeHint().width()
        assert editor.settings_card.width() == editor.width()
        assert editor.trial_card.y() == editor.timeline_card.y()
        assert editor.trial_card.geometry().right() < editor.timeline_card.x()
        assert editor.timeline_card.geometry().right() == editor.width() - 1
        assert editor.timeline_card.height() == editor.trial_card.height()
        assert not hasattr(panel, "selected_trial_section")
        assert not any(
            caption.text() in {"Selected trial", "Random seed", "Gap after trial (s)"}
            for caption in editor.trial_card.findChildren(QLabel)
        )
        assert editor.sequence_summary.alignment() == Qt.AlignmentFlag.AlignLeft
        assert editor.settings_card.y() > editor.timeline_card.geometry().bottom()
        viewport = panel.config_scroll.viewport()
        assert panel.config_scroll.widget().width() <= viewport.width()
        assert set(panel.assets.folders) == {"root"}
        assert not hasattr(panel.assets, "more")
        if width == 1175:
            assert panel.assets.y() == panel.program_card.y()
            assert panel.program_card.x() < panel.assets.x()
        app.processEvents()
        panel.config_scroll.ensureWidgetVisible(panel.editor.subgroup.composer.duration)
        app.processEvents()
        point = panel.editor.subgroup.composer.duration.mapTo(viewport, QPoint())
        assert 0 <= point.x() < viewport.width()
        assert 0 <= point.y() < viewport.height()

    editor = panel.editor
    original = editor.program
    editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
    for _ in range(3):
        app.processEvents()
    from PyQt6.QtWidgets import QScrollArea

    height = editor.timeline_card.height()
    position = editor.settings_card.y()
    assert not editor.timeline_card.findChildren(QScrollArea)
    assert editor.timeline.height() == 126
    assert not editor.timeline.show_details
    for index in range(len(editor.timeline.nodes)):
        editor.timeline.choose(index, Qt.KeyboardModifier.NoModifier)
        app.processEvents()
        assert editor.timeline_card.height() == height
        assert editor.settings_card.y() == position
        assert editor.timeline.height() == 126
    assert editor.program == original


def test_protocol_controls_and_enabled_screen_lanes(window: DashboardWindow) -> None:
    from PyQt6.QtWidgets import QLineEdit

    panel = window.protocol
    assert window.recordings.velocities.text() == ""
    assert window.recordings.velocity_label.text() == "Save tracking velocities"
    assert not panel.program_card.findChildren(QLineEdit)
    assert not hasattr(panel, "validate_button")
    assert panel.message.isHidden()
    projectors = window.devices.projectors
    projectors.keys = ["left", "bottom"]
    projectors.assignments = {"left": "Left", "bottom": "Bottom"}
    projectors.diagram.outputs = [
        ("2", QRect(0, 0, 100, 100)),
        ("3", QRect(100, 0, 100, 100)),
    ]
    before = panel.editor.program
    projectors.update_participation()
    assert panel.editor.timeline.screens == ("Left", "Bottom")
    projectors.set_participation("left", False)
    assert panel.editor.timeline.screens == ("Bottom",)
    projectors.assignments["bottom"] = "Front"
    projectors.update_participation()
    assert panel.editor.timeline.screens == ("Front",)
    projectors.keys.clear()
    projectors.assignments.clear()
    projectors.diagram.outputs.clear()
    projectors.update_participation()
    assert panel.editor.timeline.screens == ()
    assert panel.editor.program == before
    panel.choose_load()
    assert panel.load_dialog is not None
    window.apply_view(review_view(Phase.RUNNING))
    assert panel.load_dialog is None


@pytest.mark.parametrize(
    "preset",
    [
        "Sine grating",
        "Square grating",
        "Checkerboard",
        "Image tile",
        "Image",
        "Looming image",
        "Video",
        "3D arena",
    ],
)
def test_stimulus_parameter_forms_round_trip_every_family(
    window: DashboardWindow, preset: str, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus(preset)
    program = editor.program
    assert len(program.sequence[0].settings) == 1
    assert editor.parameters.apply()
    assert editor.program == program
    path = tmp_path / "program.json"
    path.write_text(program.model_dump_json())
    assert parse_program_json(path.read_text(), max_bytes=1_048_576) == program
    if preset in ("Image", "Video", "3D arena", "Looming image", "Image tile"):
        assert editor.parameters.asset_forms
    if preset == "Looming image":
        assert program.sequence[0].settings[0].width.kind == "keyframes"


def test_stimulus_parameter_edit_invalid_guard_and_media_root(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import review_program

    data = review_program().model_dump(mode="json")
    data["sequence"] = [data["sequence"][1]]
    data["sequence"][0]["duration"]["duration"]["seconds"] = "60"
    editor.set_program(validate(data))
    parameters = editor.parameters
    value = parameters.fades.fade_in
    value.setText("0.4")
    parameters.fades.mark_changed()
    parameters.mark_changed()
    assert parameters.apply()
    assert editor.program.sequence[0].settings[0].opacity.kind == "keyframes"
    value.setText("-1")
    parameters.mark_changed()
    before = editor.program
    assert not parameters.apply()
    assert editor.program == before
    assert parameters.dirty
    value.setText("0.9")
    parameters.fades.mark_changed()
    assert parameters.apply()
    editor.set_program(blank_program())
    editor.add_stimulus("Video")
    identity = editor.program.sequence[0].settings[0].asset_id
    parameters.asset_root = str(tmp_path)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"authoring-path-fixture")
    before = editor.program
    parameters.choose_media(identity)
    assert parameters.file_dialog is not None
    parameters.file_dialog.reject()
    assert parameters.file_dialog is None
    assert editor.program == before
    parameters.set_media_path(identity, str(media))
    assert parameters.apply()
    assert editor.program.assets[0].logical_path == "clip.mp4"
    before = editor.program
    identity = editor.program.sequence[0].settings[0].asset_id
    parameters.set_media_path(identity, str(tmp_path.parent / "outside.mp4"))
    assert "Cannot select" in parameters.message.text()
    assert editor.program == before


def test_stimulus_animation_variants_reset_and_remove(window: DashboardWindow) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Image")
    parameters = editor.parameters
    parameters.fades.fade_in.setText("2")
    parameters.fades.fade_out.setText("3")
    parameters.fades.mark_changed()
    assert parameters.apply()
    setting = editor.program.sequence[0].settings[0]
    assert setting.opacity.kind == "keyframes"
    parameters.fades.fade_in.setText("bad")
    parameters.fades.mark_changed()
    assert not parameters.apply()
    parameters.reset()
    assert not parameters.dirty
    assert parameters.apply()
    assert editor.program.sequence[0].settings[0] == setting
    editor.remove_stimulus()
    assert editor.program.sequence[0].settings == ()
    assert parameters.isHidden()


def test_prepared_texture_bundle_and_epoch_motion(
    window: DashboardWindow, tmp_path: Path
) -> None:
    import json

    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.parameters.asset_root = str(tmp_path)
    editor.add_stimulus("Texture")
    parameters = editor.parameters
    assert not hasattr(parameters, "tabs")
    assert all(
        "pattern" not in getattr(form, "children_by_key", {})
        for form in parameters.forms
    )
    png = tmp_path / "pattern.png"
    png.write_bytes(b"file-selection-fixture-not-decoded")
    design = tmp_path / "pattern.texture.json"
    design.write_text(
        json.dumps(
            {
                "cephvr_asset_type": "texture_design",
                "kind": "texture",
                "pattern": "dots_grid",
                "params": {"tile_width_mm": 104},
                "preview_file": "pattern.png",
            }
        )
    )
    identity = editor.program.sequence[0].settings[0].pattern.asset_id
    parameters.set_media_path(identity, str(design))
    assert editor.program.assets[0].logical_path == "pattern.texture.json"
    assert editor.program.assets[0].profile == "cephvr1_texture_json_v1"
    assert not parameters.message.text()
    assert editor.program.sequence[0].settings[0].pattern.period_x.value == 104
    assert parameters.file_rows
    assert parameters.advanced.isHidden()
    parameters.more.setChecked(True)
    assert not parameters.advanced.isHidden()
    parameters.more.setChecked(False)
    parameters.bind(editor.program, (0,), 0, "Left")
    motion = parameters.forms[0]
    assert isinstance(motion, EpochMotion)
    motion.speed.setText("52")
    motion.direction.setText("90")
    motion.angular.setText("5")
    motion.changed.emit()
    assert parameters.apply()
    setting = editor.program.sequence[0].settings[parameters.layer_index]
    assert setting.phase_x.kind == setting.phase_y.kind == "hold"
    assert setting.motion.y.function.value == pytest.approx(0, abs=1e-12)
    assert setting.motion.x.function.value == pytest.approx(-52)
    assert setting.motion.rotation.function.value == 5
    before = editor.program
    design.write_text(
        json.dumps(
            {
                "cephvr_asset_type": "texture_design",
                "kind": "arena",
                "params": {"tile_width_mm": 104},
            }
        )
    )
    identity = setting.pattern.asset_id
    parameters.set_media_path(identity, str(design))
    assert editor.program == before
    assert "texture" in parameters.message.toolTip().lower()


def test_prepared_file_change_is_epoch_local(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Image")
    first = editor.program.sequence[0]
    second = first.model_copy(update={"epoch_id": "second"})
    editor.set_program(editor.program.model_copy(update={"sequence": (first, second)}))
    old_id = first.settings[0].asset_id
    image_path = tmp_path / "replacement.png"
    image_path.write_bytes(b"path-only-fixture")
    editor.parameters.asset_root = str(tmp_path)
    editor.parameters.set_media_path(old_id, str(image_path))
    assert editor.parameters.apply()
    assert editor.program.sequence[1].settings[0].asset_id == old_id
    assert editor.program.sequence[0].settings[0].asset_id != old_id
    assert (
        next(
            asset for asset in editor.program.assets if asset.asset_id == old_id
        ).logical_path
        == "image.png"
    )


def test_protocol_epoch_structure_actions(window: DashboardWindow) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    from cephvr.gui.protocol_batches import grouped_program

    editor.set_program(grouped_program(blank_program()))
    editor.enter_group()
    editor.hierarchy.contents.block_actions.add.click()
    assert len(editor.program.sequence[0].body) == 2
    assert editor.node_index == 1
    added = editor.program.sequence[0].body[1].epoch_id
    editor.edit_epoch("earlier")
    assert editor.program.sequence[0].body[0].epoch_id == added
    editor.edit_epoch("duplicate")
    assert len(editor.program.sequence[0].body) == 3
    assert len({node.epoch_id for node in editor.program.sequence[0].body}) == 3
    editor.edit_epoch("remove")
    assert len(editor.program.sequence[0].body) == 2
    editor.edit_epoch("remove")
    before = editor.program
    editor.edit_epoch("remove")
    assert editor.program == before


def test_add_prepared_file_picker_does_not_create_placeholder_on_cancel(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    open_protocol_group(editor)
    composer = editor.subgroup.composer
    editor.timeline.set_screens(("Left",))
    composer.set_asset_root(str(tmp_path))
    before = editor.program
    composer.choose("Image", "Left")
    assert composer.picker.dialog is not None
    composer.picker.dialog.reject()
    assert editor.program == before
    path = tmp_path / "image.png"
    path.write_bytes(b"authoring-only-file-fixture")
    composer.add_file("Image", str(path), "Left")
    editor.subgroup.apply()
    assert len(editor.program.sequence[0].body[0].settings) == 1
    assert editor.program.assets[0].logical_path == "image.png"
    before = editor.program
    composer.add_file("Video", str(path), "Left")
    assert editor.program == before
    composer.choose("Image", "Left")
    window.apply_view(review_view(Phase.RUNNING))
    assert composer.picker.dialog is None


def test_file_first_epoch_insertion_and_history(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    from cephvr.gui.protocol_batches import grouped_program

    editor.set_program(grouped_program(blank_program()))
    editor.enter_group()
    composer = editor.subgroup.composer
    editor.timeline.set_screens(("Left",))
    composer.set_asset_root(str(tmp_path))
    original = editor.program
    composer.choose("Texture", "Left")
    assert composer.picker.dialog is not None
    composer.picker.dialog.reject()
    assert editor.program == original
    image = tmp_path / "tile.png"
    image.write_bytes(b"authoring-only fixture")
    editor.add_subgroup()
    blank_added = editor.program
    composer.add_file("Texture", str(image), "Left")
    editor.subgroup.apply()
    assert len(editor.program.sequence[0].body) == 2
    assert editor.node_index == 1
    added = editor.program
    assert added.sequence[0].body[1].settings[0].pattern.kind == "image_tile"
    editor.undo()
    assert editor.program == blank_added
    editor.undo()
    assert editor.program == original
    editor.undo(True)
    editor.undo(True)
    assert editor.program == added
    composer.add_file("Video", str(image), "Left")
    assert editor.program == added
    assert len(editor.histories[0].past) == 2


def test_screen_overrides_and_layers_preserve_other_epochs(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_scope import change_scope, move_layer, split_screens

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.timeline.set_screens(("Left", "Right"))
    editor.add_stimulus("Texture")
    from cephvr.gui.protocol_nodes import edit_epoch as edit_source_epoch

    editor.set_program(edit_source_epoch(editor.program, editor.path, "duplicate")[0])
    original = editor.program
    split = split_screens(original, 1, 0)
    assert split.sequence[0] == original.sequence[0]
    assert len(split.sequence[1].settings) == 2
    assert (
        split.sequence[1].settings[0].instance_id
        != split.sequence[1].settings[1].instance_id
    )
    assert (
        split.sequence[1].settings[0].pattern.asset_id
        == split.sequence[1].settings[1].pattern.asset_id
    )
    changed = change_scope(split, 1, 0, ["left", "bottom"])
    assert changed.sequence[1].settings[1] == split.sequence[1].settings[1]
    assert changed.sequence[0] == original.sequence[0]
    moved, index = move_layer(changed, 1, 0, 1)
    assert index == 1
    assert moved.sequence[1].settings[1] == changed.sequence[1].settings[0]
    editor.set_program(split)
    editor.timeline.set_screens(("Left",))
    assert editor.program == split


def test_repeat_variation_uses_canonical_expansion_and_preserves_choreography(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import Variation, make_group
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.timeline.set_screens(("Left",))
    editor.add_stimulus("Texture")
    from cephvr.gui.protocol_nodes import edit_epoch as edit_source_epoch

    editor.set_program(edit_source_epoch(editor.program, editor.path, "add")[0])
    original = editor.program
    rules = (
        Variation((0,), 0, "Speed", (10.0, 20.0)),
        Variation((0,), 0, "Direction", (0.0, 90.0)),
    )
    grouped, _ = make_group(original, (), 0, 1, 2, True, rules)
    group = grouped.sequence[0]
    assert group.order_unit == "condition_rows"
    assert len(group.conditions.rows) == 2
    expanded = expand_program(grouped, seed_decimal="42", max_expanded_epochs=100)
    assert len(expanded) == 8
    assert expanded == expand_program(
        grouped, seed_decimal="42", max_expanded_epochs=100
    )
    for offset in range(0, 8, 2):
        assert expanded[offset].settings
        assert expanded[offset + 1].settings == ()
        assert expanded[offset].lineage == expanded[offset + 1].lineage
    rates = {
        (
            round(e.settings[0].motion.x.function.value, 6),
            round(e.settings[0].motion.y.function.value, 6),
        )
        for e in expanded
        if e.settings
    }
    assert rates == {(0.0, -10.0), (-20.0, 0.0)}
    combined, _ = make_group(original, (), 0, 1, 1, False, rules, combinations=True)
    assert len(combined.sequence[0].conditions.rows) == 4
    assert len(expand_program(combined, seed_decimal="0", max_expanded_epochs=100)) == 8
    with pytest.raises(ValueError, match="equally long"):
        make_group(
            original,
            (),
            0,
            1,
            1,
            False,
            (rules[0], Variation((0,), 0, "Direction", (90.0,))),
        )


def test_nested_group_edit_and_duplicate_reference_remapping(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import Variation, make_group
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    grouped, _ = make_group(
        editor.program, (), 0, 0, 2, False, (Variation((0,), 0, "Speed", (10.0, 20.0)),)
    )
    editor.set_program(grouped)
    editor.enter_group()
    assert editor.scope == (0,)
    editor.group_editor.repetitions.setText("0")
    editor.group_editor.mark_changed()
    assert editor.undo_action.isEnabled()
    editor.undo_action.trigger()
    assert editor.program == grouped and editor.group_editor.repetitions.text() == "2"
    editor.group_editor.name.setText("Condition sequence")
    editor.group_editor.mark_changed()
    assert editor.group_editor.apply()
    assert editor.program.sequence[0].group_id == "Condition_sequence"
    renamed = expand_program(editor.program, seed_decimal="0", max_expanded_epochs=100)
    assert len(renamed) == 4
    assert all(e.lineage[0].group_id == "Condition_sequence" for e in renamed)
    from cephvr.gui.protocol_nodes import edit_epoch_metadata

    editor.commit(
        edit_epoch_metadata(
            editor.program, (0, 0), node_at(editor.program, (0, 0)).epoch_id, "61"
        )
    )
    assert node_at(editor.program, (0, 0)).duration.duration.seconds == "61"
    editor.edit_group("duplicate")
    assert len(editor.program.sequence) == 2
    assert editor.program.sequence[0].group_id != editor.program.sequence[1].group_id
    assert (
        len(expand_program(editor.program, seed_decimal="0", max_expanded_epochs=100))
        == 8
    )
    out = tmp_path / "groups.json"
    window.protocol.save_program(str(out))
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    assert parse_program_json(out.read_text(), max_bytes=1_048_576) == editor.program
    editor.undo()
    assert len(editor.program.sequence) == 1
    assert node_at(editor.program, (0, 0)).duration.duration.seconds == "61"


def test_group_fields_reject_bad_values_and_lock_on_authority_loss(window):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.set_program(grouped_program(blank_program()))
    editor.enter_group()
    original = editor.program
    editor.group_editor.repetitions.setText("0")
    editor.group_editor.mark_changed()
    assert not editor.group_editor.apply()
    assert editor.program == original
    editor.undo()
    window.apply_view(review_view(Phase.RUNNING))
    editor.group_editor.repetitions.setText("2")
    assert not editor.group_editor.apply()
    assert editor.program == original


def test_motion_auto_commit_and_invalid_edit_undo(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    editor.timeline.set_screens(("Front",))
    open_protocol_group(editor)
    window.page_buttons[1].click()
    app.processEvents()
    motion = editor.subgroup.composer.rows["Front"].parameters.forms[0]
    original = editor.program
    motion.speed.setFocus()
    motion.speed.selectAll()
    QTest.keyClicks(motion.speed, "30")
    editor.subgroup.composer.duration.setFocus()
    app.processEvents()
    assert editor.program != original
    assert editor.program.sequence[0].body[0].settings[
        0
    ].motion.x.function.value == pytest.approx(-30)
    editor.undo()
    assert editor.program == original
    editor.subgroup.composer.duration.setText("invalid")
    editor.subgroup.apply()
    assert not editor.flush_parameters()
    editor.undo()
    assert editor.subgroup.composer.duration.text() == "00:01:00"
    assert editor.program == original


def test_saved_variations_reopen_as_speed_direction_lists(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.condition_values import ConditionValues
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import Variation, make_group, update_group
    from cephvr.visual_stimulus.compiler.expansion import expand_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    grouped, _ = make_group(
        editor.program,
        (),
        0,
        0,
        1,
        False,
        (
            Variation((0,), 0, "Speed", (10.0, 20.0)),
            Variation((0,), 0, "Direction", (0.0, 90.0)),
        ),
    )
    loaded = parse_program_json(grouped.model_dump_json(), max_bytes=1_048_576)
    values = ConditionValues(loaded.sequence[0])
    assert values.targets
    assert {name for _, name, _ in values.controls} == {"Speed", "Direction"}
    assert values.read() == loaded.sequence[0].conditions.model_dump(mode="json")
    speed = next(control for _, name, control in values.controls if name == "Speed")
    speed.setText("30, 20")
    values.changed.emit()
    updated = update_group(loaded, 0, 1, False, values.read())
    expanded = expand_program(updated, seed_decimal="0", max_expanded_epochs=20)
    assert expanded[0].settings[0].motion.x.function.value == pytest.approx(-30)
    assert (
        updated.sequence[0].conditions.rows[1] == loaded.sequence[0].conditions.rows[1]
    )
    speed.setText("30")
    with pytest.raises(ValueError, match="equally long"):
        values.read()


def test_variation_bounds_and_preview_limit(window: DashboardWindow) -> None:
    from cephvr.gui.group_editor import ExpandedPreview
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import Variation, make_group

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Image")
    original = editor.program
    with pytest.raises(ValueError, match="512"):
        make_group(
            original,
            (),
            0,
            0,
            1,
            False,
            (Variation((0,), 0, "Speed", tuple(float(i) for i in range(513))),),
        )
    with pytest.raises(ValueError):
        make_group(
            original, (), 0, 0, 1, False, (Variation((0,), 0, "Width", (-1.0,)),)
        )
    huge, _ = make_group(original, (), 0, 0, 2001, False)
    preview = ExpandedPreview(huge, editor)
    assert "max_expanded_epochs" in preview.output.toPlainText()
    assert editor.program == original
    preview.close()


def test_stationary_texture_speed_variation_defaults_toward_rig_right(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import Variation, make_group, motion_numbers
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    assert motion_numbers(
        editor.program.sequence[0].settings[0].model_dump(mode="json")
    )[:2] == (0.0, 0.0)
    grouped, _ = make_group(
        editor.program, (), 0, 0, 1, False, (Variation((0,), 0, "Speed", (10.0,)),)
    )
    expanded = expand_program(grouped, seed_decimal="0", max_expanded_epochs=10)
    assert expanded[0].settings[0].motion.x.function.value < 0
    assert motion_numbers(expanded[0].settings[0].model_dump(mode="json"))[:2] == (
        10.0,
        0.0,
    )
    from cephvr.gui.protocol_nodes import edit_epoch_metadata

    editor.commit(
        edit_epoch_metadata(
            editor.program, editor.path, editor.program.sequence[0].epoch_id, "70"
        )
    )
    assert editor.sequence_summary.text() == "1 epoch · 1 block · 00:01:10"


@pytest.mark.parametrize("gap", ["0", "1.25"])
def test_expanded_close_and_trial_deletion(
    window: DashboardWindow, app: QApplication, tmp_path: Path, gap: str
) -> None:
    from PyQt6.QtWidgets import QMessageBox

    editor = window.protocol.editor
    editor.open_preview()
    preview = editor.expanded_preview
    assert preview is not None
    preview.close_button.click()
    app.processEvents()
    assert editor.expanded_preview is None
    saved = tmp_path / "keep.json"
    window.protocol.save_program(str(saved))
    original = editor.program
    editor.add_trial()
    editor.drafts[0].gap_after_seconds = gap
    editor.trials.delete_requested.emit(editor.index)
    editor.delete_dialog.button(QMessageBox.StandardButton.Cancel).click()
    assert len(editor.drafts) == 2
    assert editor.drafts[0].gap_after_seconds == gap
    editor.trials.delete_requested.emit(editor.index)
    editor.delete_dialog.button(QMessageBox.StandardButton.Yes).click()
    assert len(editor.drafts) == 1 and editor.program == original
    assert editor.drafts[0].gap_after_seconds == ""
    from cephvr.control.v1 import types_pb2 as control_pb

    configuration = control_pb.ExperimentConfiguration()
    window.protocol.session_mode.setCurrentText("Open-loop")
    window.protocol.apply_schedule(configuration)
    assert len(configuration.trials) == 1 and not configuration.gaps
    editor.trials.delete_requested.emit(editor.index)
    editor.delete_dialog.button(QMessageBox.StandardButton.Yes).click()
    assert len(editor.drafts) == 1 and editor.program != original
    assert saved.exists()
    assert len(editor.histories) == editor.trials.count() == 1
    window.apply_view(review_view(Phase.RUNNING))
    editor.delete_trial()
    assert editor.delete_dialog is None


def test_recording_checks_stay_next_to_labels(
    window: DashboardWindow, app: QApplication
) -> None:
    window.page_buttons[0].click()
    app.processEvents()
    panel = window.recordings
    panel.sync_cameras()
    panel.sync_cameras()
    grid = panel.source_grid
    assert panel.video_heading.text() == "Videos"
    assert panel.data_heading.text() == "Data"
    video_row = grid.getItemPosition(grid.indexOf(panel.video_heading))[0]
    data_row = grid.getItemPosition(grid.indexOf(panel.data_heading))[0]
    assert data_row == 0
    for camera in window.devices.cameras.drafts:
        row = grid.getItemPosition(grid.indexOf(panel.record[camera.key]))[0]
        assert row > video_row
    assert grid.getItemPosition(grid.indexOf(panel.record["stimulus"]))[0] > video_row
    for control in (panel.velocities, panel.spikeglx):
        assert data_row < grid.getItemPosition(grid.indexOf(control))[0] < video_row
    assert grid.count() == 2 + 2 * (len(panel.record) + 2)
    dashboard = window.dashboard
    assert dashboard.isAncestorOf(panel)
    assert not window.protocol.isAncestorOf(panel)
    for width in (1175, 720, 1920, 720):
        window.resize(width, 883)
        app.processEvents()
        dashboard.config_scroll.ensureWidgetVisible(panel)
        app.processEvents()
        assert panel.y() > dashboard.subject_card.geometry().bottom()
        assert panel.width() == dashboard.subject_card.width()
        pairs = [
            (panel.source_labels[key], check) for key, check in panel.record.items()
        ]
        for caption, check in (*pairs, (panel.velocity_label, panel.velocities)):
            gap = caption.mapTo(panel, QPoint()).x() - (
                check.mapTo(panel, QPoint()).x() + check.width()
            )
            assert 0 <= gap <= 12
            assert caption.height() >= caption.heightForWidth(caption.width())
        assert panel.height() >= panel.heightForWidth(panel.width())


def test_looming_primary_controls_and_custom_size_fidelity(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.looming_size import LoomingSize
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Looming image")
    parameters = editor.parameters
    size = next(f for f in parameters.forms if isinstance(f, LoomingSize))
    size.start.setText("2")
    size.end.setText("45")
    size.duration.setText("12.125")
    size.changed.emit()
    assert parameters.apply()
    node = editor.program.sequence[0].settings[0]
    assert node.width == node.height
    assert node.width.knots[0].value == 2
    assert node.width.knots[1].value == 45
    assert node.width.knots[1].time.ns() == 12_125_000_000
    before = editor.program
    size.custom.setChecked(True)
    assert parameters.apply() and editor.program == before
    size.custom.setChecked(False)
    size.duration.setText("0")
    size.changed.emit()
    assert not parameters.apply()
    assert editor.program == before
    parameters.reset()
    data = before.model_dump(mode="json")
    data["sequence"][0]["settings"][0]["width"]["knots"].insert(
        1, {"time": {"seconds": "5"}, "value": 12.0}
    )
    custom = validate(data)
    editor.set_program(custom)
    size = next(f for f in parameters.forms if isinstance(f, LoomingSize))
    assert size.custom.isChecked() and not size.custom.isEnabled()
    parameters.more.setChecked(True)
    assert parameters.apply() and editor.program == custom
    parameters.more.setChecked(False)
    assert parameters.apply() and editor.program == custom


def test_batch_create_variations_preview_insert_and_reload(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_batch import epoch_paths
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.visual_stimulus.compiler.expansion import expand_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
    window.page_buttons[1].click()
    from cephvr.gui.protocol_batches import grouped_program

    editor.set_program(grouped_program(blank_program()))
    editor.enter_group()
    editor.timeline.set_screens(("Left", "Right"))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    create = editor.subgroup
    create.composer.set_asset_root(str(tmp_path))
    editor.group_editor.repetitions.setText("2")
    editor.group_editor.mark_changed()
    assert editor.group_editor.apply()
    original = editor.program
    create.composer.add_file("Texture", str(path), "Left")
    create.composer.duration.setText("00:00:05.000000001")
    create.add_variation()
    create.rows[0].method.setCurrentIndex(1)
    create.rows[0].values.setText("0, 1, 0.25")
    create.refresh_preview()
    assert create.add_button.isEnabled(), create.summary.text()
    assert create.summary.text().startswith("5 epochs")
    create.rows[0].method.setCurrentIndex(0)
    create.rows[0].values.setText("10, 20, 40")
    create.add_variation()
    create.rows[1].parameter.setCurrentIndex(
        create.rows[1].parameter.findData("Direction")
    )
    create.rows[1].values.setText("0, 180")
    create.refresh_preview()
    assert create.add_button.isEnabled()
    assert create.notice.text()
    assert create.notice.dialog is None
    assert editor.program == original
    create.rows[0].values.setText("10, 10, 20, 20, 40, 40")
    create.rows[1].values.setText("0, 180, 0, 180, 0, 180")
    assert create.parameter_fields[2].isHidden()
    create.refresh_preview()
    assert create.add_button.isEnabled(), create.summary.text()
    assert create.summary.text().startswith("6 epochs")
    assert editor.program == original
    create.generate()
    program = editor.program
    assert len(epoch_paths(program)) == 6
    assert len(expand_program(program, seed_decimal="8", max_expanded_epochs=100)) == 12
    assert program.sequence[0].order == "as_listed"
    assert program.sequence[0].conditions is None
    numbers = {
        tuple(
            round(v, 6)
            for v in motion_numbers(
                node_at(program, path).settings[0].model_dump(mode="json")
            )[:2]
        )
        for path in epoch_paths(program)
    }
    assert numbers == {(speed, angle) for speed in (10, 20, 40) for angle in (0, 180)}
    assert all(
        node_at(program, p).duration.duration.ns() == 5_000_000_001
        for p in epoch_paths(program)
    )
    assert parse_program_json(program.model_dump_json(), max_bytes=1_048_576) == program
    editor.undo(False)
    assert editor.program == original
    assert not create.composer.program.sequence[0].settings
    editor.set_program(program)
    editor.select_epochs(((0, 5),))
    before_path = editor.path
    editor.add_subgroup()
    assert len(editor.selected_paths) == 1
    assert len(editor.program.sequence[0].body) == 7
    editor.undo(False)
    assert editor.program == program and editor.path == before_path
    app.processEvents()


def test_trial_overview_selects_ranges_and_sources_across_groups(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import make_group
    from cephvr.gui.protocol_nodes import edit_epoch

    editor = window.protocol.editor
    window.page_buttons[1].click()
    program, _ = edit_epoch(blank_program(), 0, "duplicate")
    program, _ = edit_epoch(program, 1, "duplicate")
    program, _ = make_group(program, (), 1, 2, 2, False)
    editor.set_program(program)
    timeline = editor.timeline
    assert len(timeline.nodes) == 2
    timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    assert editor.selected_paths == ((1, 0),)
    assert editor.scope == (1,)
    assert len(timeline.nodes) == 2  # Persistent collapsed trial overview.
    contents = editor.hierarchy.contents
    assert len(contents.nodes) == 2
    contents.choose(1, Qt.KeyboardModifier.ShiftModifier)
    assert set(editor.selected_paths) == {(1, 0), (1, 1)}
    assert not hasattr(editor, "back_button")
    timeline.choose(0, Qt.KeyboardModifier.NoModifier)
    timeline.choose(1, Qt.KeyboardModifier.ShiftModifier)
    assert editor.selected_paths == ((0,), (1,))
    assert editor.subgroup.isHidden()
    assert not hasattr(editor.hierarchy, "wrap")
    assert editor.program == program
    assert not any(
        control.text() in {"Duplicate", "Delete"}
        for control in editor.timeline_card.findChildren(QPushButton)
    )
    actions = editor.timeline_actions.layout()
    assert actions.count() == 1
    assert actions.indexOf(editor.output_preview_button) == 0
    assert not any(
        control.text() == "Actions…"
        for control in editor.settings_card.findChildren(QPushButton)
    )
    window.apply_view(review_view(Phase.RUNNING))
    before = editor.program
    editor.subgroup.generate()
    editor.subgroup.apply()
    assert editor.program == before
    app.processEvents()


def test_review_projector_inventory_drives_devices_and_planner(
    app: QApplication,
) -> None:
    sample = DashboardWindow(sample=True)
    ReviewControls(sample, simulate_projectors=True)
    try:
        panel = sample.devices.projectors
        editor = sample.protocol.editor
        faces = ("Front", "Left", "Right", "Bottom")
        assert panel.table.rowCount() == 4
        assert panel.enabled_screens == editor.timeline.screens == faces
        assert [panel.table.item(i, 1).text() for i in range(4)] == ["1", "2", "3", "4"]
        key = panel.keys[2]
        panel.enable_controls[key].setChecked(False)
        assert editor.timeline.screens == ("Front", "Left", "Bottom")
        panel.request("Refresh displays")
        assert panel.table.rowCount() == 4
        assert not panel.enable_controls[key].isChecked()
        assert panel.enabled_screens == editor.timeline.screens
        assert "simulated projector displays" in panel.console.toPlainText()
        panel.enable_controls[key].setChecked(True)
        assert editor.timeline.screens == faces
        original = editor.program
        editor.add_button.click()
        assert editor.trials.currentRow() == editor.index == 1
        editor.trials.setCurrentRow(0)
        assert editor.program == original
    finally:
        sample.close()


def test_timeline_overview_colors_and_current_epoch_details(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.timeline_details import stimulus_color, stimulus_key

    window.page_buttons[1].click()
    editor = window.protocol.editor
    program = review_program()
    editor.set_program(program)
    timeline = editor.timeline
    timeline.set_screens(("Front", "Left", "Right", "Bottom"))
    app.processEvents()
    assert editor.trial_card.width() == 208
    overview = [(rect, i) for rect, i, face, _ in timeline.hits if not face]
    assert overview[0][0].left() == 1
    assert overview[-1][0].right() <= timeline.width()
    assert len(timeline.hover_text) == len(timeline.nodes)  # Compact overview.
    assert timeline.type_keys[0] == timeline.type_keys[2]
    assert timeline.type_keys[0] != timeline.type_keys[1]
    assert stimulus_color(timeline.type_keys[0]) != stimulus_color(
        timeline.type_keys[1]
    )
    assert all(rows == [(-1, "Blank")] for _, rows in timeline.detail_rows())
    bar = next(rect for rect, i, face, layer in timeline.hits if i == 1 and face == "")
    QTest.mouseClick(timeline, Qt.MouseButton.LeftButton, pos=bar.center().toPoint())
    app.processEvents()
    assert timeline.index == 1 and editor.selected_paths == ((1,),)
    rows = dict(timeline.detail_rows())
    assert rows["Front"] == rows["Bottom"] == [(-1, "Blank")]
    assert "Texture" in rows["Left"][0][1]
    assert rows["Left"] == rows["Right"]
    timeline.choose(2, Qt.KeyboardModifier.ShiftModifier)
    assert editor.selected_paths == ((1,), (2,))
    assert timeline.index == 2
    assert all(rows == [(-1, "Blank")] for _, rows in timeline.detail_rows())
    assert not hasattr(editor, "modes")
    assert editor.timeline_card.height() == editor.trial_card.height()
    assert editor.program == program
    node = program.sequence[1]
    renamed = node.model_copy(
        update={"epoch_id": "Different_name", "duration": program.sequence[0].duration}
    )
    assert stimulus_key(program, renamed) == timeline.type_keys[1]
    changed = node.model_copy(
        update={
            "settings": (
                node.settings[0].model_copy(update={"initial_phase_x_cycles": 0.5}),
            )
        }
    )
    assert stimulus_key(program, changed) != timeline.type_keys[1]


@pytest.mark.parametrize("mode", ["generate", "selection"])
def test_epoch_parameter_warnings_wait_for_submission(window, app, tmp_path, mode):
    from PyQt6.QtGui import QImage

    from cephvr.gui.notices import FormNotice
    from cephvr.gui.protocol_document import review_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(review_program())
    open_protocol_group(editor)
    if mode == "generate":
        owner = editor.subgroup
        composer = owner.composer
        composer.set_screens(("Front", "Left", "Right", "Bottom"))
        composer.set_asset_root(str(tmp_path))
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.fill(0)
        path = tmp_path / "tile.png"
        assert image.save(str(path))
        composer.add_file("Texture", str(path), "Front")
        notice = owner.notice
    else:
        editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
        editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
        owner = editor.subgroup
        composer = owner.composer
        notice = owner.notice
    composer.set_subject_height("0")
    app.processEvents()
    row = next(row for row in composer.rows.values() if row.indices)
    parameters = row.parameters
    assert parameters.fades is not None
    parameters.more.setChecked(True)
    original, reference = editor.program, composer.program
    fade = parameters.fades.fade_in
    fade.setFocus()
    fade.selectAll()
    QTest.keyClicks(fade, "-1")
    composer.duration.setFocus()
    app.processEvents()
    parameters.auto_apply()
    parameters.finish_edit(fade, composer.duration)
    composer.change_mode(1 - composer.active_mode)
    composer.change_type(row.face, "Image")
    composer.add_empty_layer(row.face)
    if mode == "generate":
        owner.add_variation()
        owner.refresh_preview()
    assert parameters.dirty and fade.text() == "-1"
    assert editor.program == original and composer.program == reference
    assert all(n.dialog is None for n in editor.findChildren(FormNotice))
    editor.flush_parameters()
    app.processEvents()
    assert notice.dialog is not None
    assert "fade" in notice.text().lower()
    assert sum(n.dialog is not None for n in editor.findChildren(FormNotice)) == 1
    assert editor.program == original
    notice.clear()
    fade.setText("1")
    parameters.fades.mark_changed()
    parameters.apply()
    owner.queue_update()
    app.processEvents()
    assert editor.program != original
    assert all(n.dialog is None for n in editor.findChildren(FormNotice))


def test_batch_reference_projector_parameters_and_layers(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.looming_size import LoomingSize
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.gui.stimulus_scope import surfaces

    editor = window.protocol.editor
    open_protocol_group(editor)
    composer = editor.subgroup.composer
    window.page_buttons[1].click()
    composer.set_screens(("Front", "Left", "Right", "Bottom"))
    composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    for kind, face in (
        ("Texture", "Front"),
        ("Looming image", "Left"),
        ("Image", "Right"),
    ):
        composer.add_file(kind, str(path), face)
    video = tmp_path / "clip.mp4"
    video.touch()  # Authoring checks a file reference, not video decoding.
    composer.add_file("Video", str(video), "Bottom")
    app.processEvents()
    assert all(not composer.rows[face].isHidden() for face in composer.screens)
    assert composer.rows[""].isHidden()
    assert composer.rows["Bottom"].parameters.primary.count() == 1
    front = composer.rows["Front"].parameters
    left = composer.rows["Left"].parameters
    motion = next(form for form in front.forms if isinstance(form, EpochMotion))
    looming = next(form for form in left.forms if isinstance(form, LoomingSize))
    before = editor.program
    # Keep two rows dirty together: accepting one must not discard the other's draft.
    motion.speed.setText("24")
    motion.direction.setText("90")
    motion.edited = True
    front.dirty = True
    looming.end.setText("72")
    looming.edited = True
    left.dirty = True
    assert front.apply()
    assert left.dirty and looming.end.text() == "72"
    program = composer.value()
    assert editor.program == before
    settings = program.sequence[0].settings
    assert motion_numbers(settings[0].model_dump(mode="json"))[:2] == pytest.approx(
        (24, 90)
    )
    assert settings[1].width.knots[-1].value == 72
    assert [surfaces(s.model_dump(mode="json")) for s in settings] == [
        ["front"],
        ["left"],
        ["right"],
        ["bottom"],
    ]
    # Add a foreground layer, then return to the existing texture's values.
    composer.add_file("Looming image", str(path), "Front")
    row = composer.rows["Front"]
    assert len(row.indices) == 2
    row.select_layer(row.indices[0])
    restored = next(
        form for form in row.parameters.forms if isinstance(form, EpochMotion)
    )
    assert float(restored.speed.text()) == pytest.approx(24)
    composer.set_screens(("Front", "Left", "Bottom"))
    assert composer.rows["Right"].caption.text() == "Right (inactive)"
    assert not composer.rows["Right"].add.isEnabled()
    assert len(composer.value().sequence[0].settings) == 5
    composer.set_screens(("Front", "Left", "Right", "Bottom"))
    composer.rows["Front"].select_layer(composer.rows["Front"].indices[1])
    composer.remove_layer("Front")
    assert len(composer.value().sequence[0].settings) == 4
    editor.subgroup.refresh_preview()
    assert editor.subgroup.add_button.isEnabled(), editor.subgroup.summary.text()
    generated = editor.subgroup.candidate()
    assert generated.sequence[0].settings == composer.value().sequence[0].settings
    restored = next(
        form for form in row.parameters.forms if isinstance(form, EpochMotion)
    )
    restored.speed.setText("invalid")
    restored.edited = True
    row.parameters.dirty = True
    editor.subgroup.refresh_preview()
    assert editor.subgroup.add_button.isEnabled()
    assert not editor.subgroup.notice.text()
    assert editor.subgroup.notice.dialog is None
    assert editor.program == before


def test_batch_reference_picker_scope_and_lock(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    composer = window.protocol.editor.subgroup.composer
    composer.set_screens(("Left", "Right"))
    window.protocol.assets.folders["root"].editor.setText(str(tmp_path))
    assert all(
        row.parameters.asset_root == str(tmp_path) for row in composer.rows.values()
    )
    composer.choose("Texture", "Left")
    picker = composer.picker.dialog
    assert picker is not None
    composer.choose("Image", "Right")
    assert composer.picker_face == "Left"
    before = composer.program
    picker.reject()
    app.processEvents()
    assert composer.program == before
    composer.choose("Image", "Right")
    assert composer.picker_face == "Right"
    window.apply_view(review_view(Phase.RUNNING))
    app.processEvents()
    assert composer.picker.dialog is None
    assert not composer.isEnabled()


@pytest.mark.parametrize(
    "modifier", [Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.MetaModifier]
)
def test_compact_reference_rows_share_headers_and_commit_relocated_fields(
    window: DashboardWindow, app: QApplication, tmp_path: Path, modifier
) -> None:
    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.protocol_groups import motion_numbers

    window.resize(1350, 900)
    window.page_buttons[1].click()
    open_protocol_group(window.protocol.editor, generate=True)
    composer = window.protocol.editor.subgroup.composer
    composer.set_screens(("Left", "Right"))
    composer.set_asset_root(str(tmp_path))
    path = tmp_path / "tile.png"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(path))
    composer.add_file("Texture", str(path), "Left")
    composer.add_file("Texture", str(path), "Right")
    app.processEvents()
    left, right = composer.rows["Left"], composer.rows["Right"]
    assert not left.narrow
    assert left.show_header and not right.show_header
    assert not right.identity_header
    assert right.height() < 80
    assert left.height() == right.height()
    assert left.parameters.more.isHidden()
    assert not left.parameters.advanced.isVisible()
    second = tmp_path / "second.png"
    assert image.save(str(second))
    left.parameters.set_media_path(next(iter(left.parameters.asset_forms)), str(second))
    source = next(iter(left.parameters.asset_forms.values()))
    destination = next(iter(right.parameters.asset_forms.values()))
    assert not destination.isReadOnly()
    clipboard = app.clipboard()
    assert clipboard is not None
    previous_clipboard = clipboard.text()
    try:
        source.setFocus()
        QTest.keyClick(source, Qt.Key.Key_A, modifier)
        QTest.keyClick(source, Qt.Key.Key_C, modifier)
        assert clipboard.text() == "second.png"
        pasted_path = (
            str(second)
            if modifier == Qt.KeyboardModifier.MetaModifier
            else clipboard.text()
        )
        clipboard.setText(pasted_path)
        destination.setFocus()
        QTest.keyClick(destination, Qt.Key.Key_A, modifier)
        QTest.keyClick(destination, Qt.Key.Key_V, modifier)
        assert destination.text() == pasted_path
    finally:
        clipboard.setText(previous_clipboard)
    composer.duration.setFocus()
    app.processEvents()
    assets = {asset.asset_id: asset.logical_path for asset in composer.program.assets}
    assert [
        assets[setting.pattern.asset_id]
        for setting in composer.program.sequence[0].settings
    ] == [
        "second.png",
        "second.png",
    ]
    assert not right.parameters.message.text()
    saved = composer.program
    destination = next(iter(right.parameters.asset_forms.values()))
    destination.setFocus()
    destination.selectAll()
    QTest.keyClicks(destination, "missing.png")
    composer.duration.setFocus()
    app.processEvents()
    assert composer.program == saved
    assert "missing" in right.parameters.message.text()
    destination.setFocus()
    destination.selectAll()
    QTest.keyClicks(destination, "second.png")
    composer.duration.setFocus()
    app.processEvents()
    assert composer.program == saved
    motion = next(f for f in left.parameters.forms if isinstance(f, EpochMotion))
    # The row uses the actual family controls, including their focus/validation path.
    motion.speed.setFocus()
    motion.speed.selectAll()
    QTest.keyClicks(motion.speed, "17.5")
    assert left.parameters.dirty
    composer.duration.setFocus()
    app.processEvents()
    assert not left.parameters.dirty
    values = composer.program.sequence[0].settings
    assert motion_numbers(values[0].model_dump(mode="json"))[0] == pytest.approx(17.5)
    assert motion_numbers(values[1].model_dump(mode="json"))[0] == 0
    left.actions_button.click()
    app.processEvents()
    assert left.parameters.advanced.isVisible()
    left.actions_button.click()
    assert not left.parameters.advanced.isVisible()
    composer.remove_layer("Left")
    app.processEvents()
    assert left.stimulus.currentText() == "None"
    assert not left.actions_button.isHidden()


@pytest.mark.parametrize("selection", ["picker", "paste"])
def test_reference_type_change_clears_asset_and_switches_stimulus_mode(
    window: DashboardWindow, app: QApplication, tmp_path: Path, selection: str
) -> None:
    from PyQt6.QtGui import QImage

    window.page_buttons[1].click()
    editor = window.protocol.editor
    open_protocol_group(editor)
    composer = editor.subgroup.composer
    composer.set_subject_height("0")
    composer.set_screens(("Front", "Right"))
    composer.set_asset_root(str(tmp_path))
    folder = tmp_path / "images"
    folder.mkdir()
    path = folder / "tile.png"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(path))
    composer.add_file("Texture", str(path), "Front")
    composer.add_file("Image", str(path), "Right")
    row = composer.rows["Front"]
    before = editor.program
    row.stimulus.setCurrentText("Looming")
    assert row.stimulus.currentText() == "Looming"
    assert all(not field.text() for field in row.parameters.asset_forms.values())
    assert all(not h.text() for h in row.headings[:1])
    with pytest.raises(ValueError, match="Choose an asset"):
        composer.value()
    asset_id = next(iter(row.parameters.asset_forms))
    if selection == "picker":
        row.parameters.set_media_path(asset_id, str(path))
    else:
        field = row.parameters.asset_forms[asset_id]
        field.setFocus()
        app.clipboard().setText("images/missing.png")
        QTest.keyClick(field, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        with pytest.raises(ValueError):
            composer.value()
        assert composer.pending_assets
        field.selectAll()
        app.clipboard().setText("images/tile.png")
        QTest.keyClick(field, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        composer.value()
    assert not composer.pending_assets
    field = next(iter(row.parameters.asset_forms.values()))
    assert field.text() == "images/tile.png" and field.filename_only
    assert field.toolTip() == "images/tile.png"
    assert {s.kind for s in composer.value().sequence[0].settings} == {"image"}
    assert editor.program == before
    # Keep the 2D draft when selecting a rig-wide arena, but do not generate it.
    composer.mode.setCurrentIndex(1)
    assert composer.rows["Front"].isHidden()
    assert not composer.rows[""].isHidden()
    with pytest.raises(ValueError, match="Choose an asset"):
        composer.value()
    arena = tmp_path / "arena.glb"
    arena.touch()  # Asset authoring, no GLB decoding or rendering.
    arena_row = composer.rows[""]
    arena_row.parameters.set_media_path(
        next(iter(arena_row.parameters.asset_forms)), str(arena)
    )
    program = composer.value()
    assert [s.kind for s in program.sequence[0].settings] == ["arena"]
    assert [a.logical_path for a in program.assets] == ["arena.glb"]
    composer.mode.setCurrentIndex(0)
    assert len(composer.value().sequence[0].settings) == 2
    assert all(a.logical_path == "images/tile.png" for a in composer.value().assets)
    # Another type change clears the file again, even though an asset existed.
    row.stimulus.setCurrentText("Video")
    editor.subgroup.refresh_preview()
    assert editor.subgroup.add_button.isEnabled()
    assert not editor.subgroup.notice.text()
    assert editor.subgroup.notice.dialog is None
    assert all(not f.text() for f in row.parameters.asset_forms.values())
    row.stimulus.setCurrentText("None")
    assert len(composer.value().sequence[0].settings) == 1
    app.processEvents()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("append", ["", "", "", "", "", "Batch", "Batch"]),
        ("start", ["Batch", "Batch", "", "", "", "", ""]),
        ("before", ["", "Batch", "Batch", "", "", "", ""]),
        ("after", ["", "", "Batch", "Batch", "", "", ""]),
        ("replace", ["Batch", "Batch"]),
        ("stride", ["", "", "Batch", "", "", "Batch", ""]),
    ],
)
def test_batch_insertion_positions_are_atomic_and_select_new_epochs(
    mode: str, expected: list[str]
) -> None:
    from cephvr.gui.batch_insertion import Insertion, insert_batch
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.protocol_document import blank_program

    base = blank_program()
    source = base.sequence[0]
    trial = base.model_copy(
        update={
            "sequence": tuple(
                source.model_copy(update={"epoch_id": f"old_{i}"}) for i in range(5)
            )
        }
    )
    batch = base.model_copy(
        update={
            "sequence": tuple(
                source.model_copy(
                    update={"epoch_id": f"new_{i}", "batch_label": "Batch"}
                )
                for i in range(2)
            )
        }
    )
    result, selected = insert_batch(trial, batch, (1,), Insertion(mode, 2))
    assert [e.batch_label for e in result.sequence] == expected
    assert len(selected) == 2
    assert all(node_at(result, p).batch_label == "Batch" for p in selected)
    assert len(trial.sequence) == 5
    with pytest.raises(ValueError):
        insert_batch(trial, batch, (1,), Insertion("stride", 0))


def test_arena_axis_gains_roundtrip_and_editor_spacing(window, app, tmp_path):
    import json

    from cephvr.gui.arena_movement import ArenaMovement
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    window.resize(1350, 900)
    window.page_buttons[1].click()
    editor = window.protocol.editor
    open_protocol_group(editor, generate=True)
    batch = editor.subgroup
    composer = batch.composer
    composer.set_asset_root(str(tmp_path))
    composer.set_subject_height("0")
    composer.mode.setCurrentIndex(1)
    path = tmp_path / "arena.glb"
    path.touch()
    row = composer.rows[""]
    row.parameters.set_media_path(next(iter(row.parameters.asset_forms)), str(path))
    app.processEvents()
    assert row.stimulus.isHidden()
    assert "Stimulus" not in row.signature
    assert (
        composer.mode.mapTo(composer, QPoint()).y()
        == composer.duration.mapTo(composer, QPoint()).y()
    )
    assert not batch.repetitions.isVisible()
    assert (
        composer.duration.mapTo(composer, QPoint()).y()
        == composer.batch_label.mapTo(composer, QPoint()).y()
    )
    assert (
        row.mapTo(composer, QPoint()).y()
        - batch.generation_controls.geometry().bottom()
        >= 24
    )
    assert (
        batch.mapTo(editor.settings_card, QPoint()).y()
        - editor.hierarchy.mapTo(
            editor.settings_card, QPoint(0, editor.hierarchy.height())
        ).y()
        >= 16
    )
    movement = next(f for f in row.parameters.forms if isinstance(f, ArenaMovement))
    for axis, gain, value in zip(movement.axes, movement.gains, (2, 3, 4), strict=True):
        axis.setChecked(True)
        gain.setText(str(value))
    assert row.parameters.apply()
    saved = parse_program_json(
        json.dumps(composer.value().model_dump(mode="json")), max_bytes=1_048_576
    )
    planar, turn = saved.sequence[0].settings[0].feedback
    assert (planar.gain.value, planar.sideways_gain.value, turn.gain.value) == (2, 3, 4)
    assert len(saved.input_channels) == 3
    # Disabling one body axis leaves the other two untouched, including after reload.
    movement.axes[0].setChecked(False)
    assert row.parameters.apply()
    row.bind(composer.program)
    movement = next(f for f in row.parameters.forms if isinstance(f, ArenaMovement))
    assert [a.isChecked() for a in movement.axes] == [False, True, True]
    assert [float(g.text()) for g in movement.gains[1:]] == [3, 4]
    movement.gains[1].setText("nan")
    movement.mark_edited()
    before = composer.program
    assert not row.parameters.apply()
    assert composer.program == before


def test_arena_custom_feedback_is_preserved_and_channel_conflicts_rejected(
    window, app, tmp_path
):
    from cephvr.gui.arena_movement import ArenaMovement
    from cephvr.visual_stimulus.config.models.program_model import InputChannel

    composer = window.protocol.editor.subgroup.composer
    composer.set_asset_root(str(tmp_path))
    composer.set_subject_height("0")
    composer.mode.setCurrentIndex(1)
    path = tmp_path / "arena.glb"
    path.touch()
    params = composer.rows[""].parameters
    params.set_media_path(next(iter(params.asset_forms)), str(path))
    movement = next(f for f in params.forms if isinstance(f, ArenaMovement))
    movement.axes[0].setChecked(True)
    assert params.apply()
    setting = composer.program.sequence[0].settings[0]
    values = setting.model_dump(mode="json")
    values["feedback"][0]["sideways_gain"] = None
    legacy = ArenaMovement(values)
    assert legacy.read()["feedback"] == values["feedback"]
    assert float(legacy.gains[0].text()) == float(legacy.gains[1].text())
    legacy.deleteLater()
    values["feedback"][0]["gain"] = {"kind": "ramp", "initial": 1, "slope_per_s": 2}
    custom = ArenaMovement(values)
    assert not custom.supported
    assert all(not cell.isEnabled() for _, cell in custom.cells)
    assert custom.read()["feedback"] == values["feedback"]
    custom.deleteLater()
    # Existing incompatible channel declarations are never silently replaced.
    params.program = params.program.model_copy(
        update={
            "input_channels": (
                InputChannel(
                    channel_id="forward_drive",
                    stream_id="tracking",
                    value_kind="interval_average_rate",
                    unit="px/s",
                    frame_id="anatomical_body",
                ),
            )
        }
    )
    movement.mark_edited()
    before = composer.program
    assert not params.apply()
    assert "conflicts" in params.message.text()
    assert composer.program == before
    app.processEvents()


def test_front_attached_screens_share_plot_and_prepared_corners(
    window: DashboardWindow,
):
    panel = window.devices.projectors
    from cephvr.gui.calibration_arena import geometry_from_calibration
    from cephvr.gui.trial_preview_surfaces import PreviewGeometry

    for key, value in zip(
        panel.rig_editor.fields, (200, 300, 150, 80, 100, 75), strict=True
    ):
        panel.rig_editor.fields[key].setText(str(value))
    for face in ("Front", "Left", "Right", "Bottom"):
        panel.screen_editor.fields[face, "width"].setText("300")
        panel.screen_editor.fields[face, "height"].setText("180")
    for face, distance in (("Front", 140), ("Left", 130), ("Bottom", 95)):
        panel.rig_editor.screen_distances[face].setText(str(distance))
    planes = panel.tank.screen_planes()
    assert all(p[1] == -40 for p in planes["Front"])
    for face in ("Left", "Right", "Bottom"):
        assert min(p[1] for p in planes[face]) == -35
    assert max(p[1] for p in planes["Left"]) == 265
    assert max(p[1] for p in planes["Bottom"]) == 265
    for distance, lower in ((95, -15), (55, 25)):
        panel.rig_editor.screen_distances["Bottom"].setText(str(distance))
        planes = panel.tank.screen_planes()
        assert all(p[2] == lower - 5 for p in planes["Bottom"])
        for face in ("Front", "Left", "Right"):
            assert min(p[2] for p in planes[face]) == lower
            assert max(p[2] for p in planes[face]) == lower + 180
        preview = PreviewGeometry.from_drafts(
            panel.rig_editor.dimensions(), panel.screen_editor.drafts
        )
        numeric = panel.calibration_files.calibration_snapshot()
        _, exported = geometry_from_calibration(numeric)
        assert exported == planes
        assert {f: list(s.corners) for f, s in preview.surfaces.items()} == planes
    payload = panel.rig_editor.geometry_payload(panel.screen_editor.drafts)
    for surface in payload["surfaces"]:
        face = surface["surface_id"].title()
        assert list(surface.values())[1:] == planes[face]
    for invalid in ("", "0", "-1", "nan", "inf"):
        panel.rig_editor.screen_distances["Bottom"].setText(invalid)
        assert panel.tank.screen_planes() == {}
        assert not PreviewGeometry.from_drafts(
            panel.rig_editor.dimensions(), panel.screen_editor.drafts
        ).surfaces
        with pytest.raises(ValueError):
            panel.rig_editor.geometry_payload(panel.screen_editor.drafts)
        with pytest.raises(ValueError):
            geometry_from_calibration(panel.calibration_files.calibration_snapshot())
    panel.rig_editor.screen_distances["Bottom"].setText("55")
    panel.rig_editor.screen_distances["Front"].setText("160")
    assert all(
        min(p[1] for p in corners) == (-60 if face == "Front" else -55)
        for face, corners in panel.tank.screen_planes().items()
    )
    # Bottom image X runs along depth, while image Y runs across tank width.
    panel.screen_editor.fields["Bottom", "width"].setText("126")
    panel.screen_editor.fields["Bottom", "height"].setText("94")
    bottom = panel.tank.screen_planes()["Bottom"]
    assert bottom[1][1] - bottom[0][1] == 126
    assert bottom[3][0] - bottom[0][0] == -94
    assert {p[0] for p in bottom} == {53, 147}
    # Portrait output calibration must not resize the physical floor in Trial Preview.
    from cephvr.gui.trial_preview_rig import PreviewRig

    drafts = {face: dict(values) for face, values in panel.screen_editor.drafts.items()}
    drafts["Bottom"].update(
        reference_width_px="720",
        reference_height_px="1280",
        reference_x_px="180",
        reference_y_px="320",
        reference_x_mm="24",
        reference_y_mm="44",
        valid_width_px="685",
        valid_height_px="940",
    )
    geometry = PreviewGeometry.from_drafts(
        panel.rig_editor.dimensions(), drafts, {"Bottom": (720, 1280)}
    )
    view = PreviewRig(geometry, {})
    assert view.screen_planes()["Bottom"] == bottom
    surface = geometry.surfaces["Bottom"]
    assert surface.corners != surface.physical_corners
    assert surface.width == pytest.approx(940 * 44 / 320)
    assert surface.height == pytest.approx(685 * 24 / 180)
    view.deleteLater()
    current = panel.calibration_files.calibration_snapshot()
    legacy = dict(current, version=4, values=dict(current["values"]))
    for face in ("Front", "Left", "Right", "Bottom"):
        for old, new in (("scale_u", "valid_width_px"), ("scale_v", "valid_height_px")):
            legacy["values"].pop(f"screens.{face}.{new}")
            legacy["values"][f"screens.{face}.{old}"] = None
    legacy["values"]["screens.Bottom.width"] = 94
    legacy["values"]["screens.Bottom.height"] = 126
    assert panel.calibration_files.validate(legacy) == current["values"]
    assert geometry_from_calibration(legacy)[1] == geometry_from_calibration(current)[1]
    from cephvr.gui.calibration_profile import MonitorBinding, face_mapping

    measured = dict(current, values=dict(current["values"]))
    measured["values"].update(
        {
            "screens.Bottom.reference_width_px": 720,
            "screens.Bottom.reference_height_px": 1280,
            "screens.Bottom.reference_x_px": 180,
            "screens.Bottom.reference_y_px": 320,
            "screens.Bottom.reference_x_mm": 49,
            "screens.Bottom.reference_y_mm": 37,
            "screens.Bottom.scale_u": 1,
            "screens.Bottom.scale_v": 1,
        }
    )
    vertices, _ = face_mapping(
        measured, "Bottom", MonitorBinding("", 0, 0, 720, 1280, 60, 8)
    )
    assert (vertices[1]["xy"][0] - vertices[0]["xy"][0]) * 196 == pytest.approx(
        round(94 / 196 * 720) * 196 / 720
    )
    assert (vertices[2]["xy"][1] - vertices[0]["xy"][1]) * 148 == pytest.approx(
        round(126 / 148 * 1280) * 148 / 1280
    )

    old_crop = dict(measured, version=5, values=dict(measured["values"]))
    for face in ("Front", "Left", "Right", "Bottom"):
        for old_key, new_key in (
            ("scale_u", "valid_width_px"),
            ("scale_v", "valid_height_px"),
        ):
            old_crop["values"].pop(f"screens.{face}.{new_key}")
            old_crop["values"][f"screens.{face}.{old_key}"] = None
    old_crop["values"]["screens.Bottom.scale_u"] = 1.02
    old_crop["values"]["screens.Bottom.scale_v"] = 1.08
    migrated = panel.calibration_files.validate(old_crop)
    assert migrated["screens.Bottom.valid_width_px"] == pytest.approx(
        round(round(94 / 196 * 720) * 1.02)
    )
    assert migrated["screens.Bottom.valid_height_px"] == pytest.approx(
        round(round(126 / 148 * 1280) * 1.08)
    )
    assert migrated["screens.Bottom.reference_x_mm"] == 49
    assert migrated["screens.Bottom.reference_y_mm"] == 37
    assert "screens.Bottom.scale_u" not in migrated
    missing_mode = dict(old_crop, values=dict(old_crop["values"]))
    missing_mode["values"]["screens.Bottom.reference_width_px"] = None
    before = panel.calibration_files.snapshot()
    with pytest.raises(ValueError, match="reference output dimensions"):
        panel.calibration_files.apply_snapshot(missing_mode)
    assert panel.calibration_files.snapshot() == before

    old_full = dict(
        panel.calibration_files.snapshot(), version=7, values=legacy["values"]
    )
    assert panel.calibration_files.validate(old_full) == current["values"]
    panel.rig_editor.screen_distances["Front"].clear()
    assert panel.tank.screen_planes() == {}
    with pytest.raises(ValueError):
        panel.rig_editor.geometry_payload(panel.screen_editor.drafts)


def test_centered_projection_uses_throw_and_assigned_aspect(window: DashboardWindow):
    from cephvr.gui.projector_geometry import RigDimensions, screen_corners
    from cephvr.gui.projector_optics import projection_footprint

    rig = RigDimensions(200, 300, 150, (80, 100, 75))
    for face, axis, sign in (
        ("Front", 1, -1),
        ("Left", 0, -1),
        ("Right", 0, 1),
        ("Bottom", 2, -1),
    ):
        corners = screen_corners(
            rig,
            face,
            dict(width="300", height="180", subject_distance="140"),
            front_distance="140",
            bottom_distance="140",
        )
        footprint = projection_footprint(corners, "600", "1.5", 16 / 9)
        assert footprint.width == 400 and footprint.height == 225
        center = tuple(sum(p[i] for p in corners) / 4 for i in range(3))
        assert footprint.projector[axis] == center[axis] + sign * 600
        assert (
            tuple(sum(p[i] for p in footprint.corners) / 4 for i in range(3)) == center
        )
        for distance, throw, aspect in (
            ("", "1", 1),
            ("0", "1", 1),
            ("100", "nan", 1),
            ("100", "1", 0),
        ):
            with pytest.raises(ValueError):
                projection_footprint(corners, distance, throw, aspect)
    panel = window.devices.projectors
    from cephvr.gui.projectors import DisplayInfo

    panel.review_displays = (
        DisplayInfo("test", "Sample", "2", QRect(0, 0, 1600, 1200)),
    )
    panel.request("Refresh displays")
    panel.projectors["test"].setCurrentText("Front")
    for key, value in zip(
        panel.rig_editor.fields, (200, 300, 150, 80, 100, 75), strict=True
    ):
        panel.rig_editor.fields[key].setText(str(value))
    panel.rig_editor.screen_distances["Front"].setText("140")
    panel.rig_editor.screen_distances["Bottom"].setText("140")
    for key, value in (
        ("width", "300"),
        ("height", "180"),
        ("distance", "600"),
        ("throw", "1.5"),
    ):
        panel.screen_editor.fields["Front", key].setText(value)
    assert panel.tank.footprints(panel.tank.screen_planes())["Front"].height == 300
    assert "400 × 300 mm" in panel.tank.toolTip()
    before = panel.tank.screen_planes()
    panel.enable_controls["test"].click()
    assert panel.tank.footprints(panel.tank.screen_planes()) == {}
    assert panel.tank.screen_planes() == before
    panel.enable_controls["test"].click()
    panel.screen_editor.fields["Front", "throw"].clear()
    assert panel.tank.footprints(panel.tank.screen_planes()) == {}


def test_tank_drag_changes_view_only_and_double_click_resets(
    window: DashboardWindow, app: QApplication
):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent

    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(2)
    panel = window.devices.projectors
    diagram = panel.tank
    before = panel.calibration_files.snapshot()
    QTest.mousePress(diagram, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(170, 110),
        QPointF(170, 110),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(diagram, move)
    QTest.mouseRelease(diagram, Qt.MouseButton.LeftButton, pos=QPoint(170, 110))
    assert (diagram.azimuth, diagram.elevation) == (105, 55)
    assert diagram.drag_origin is None
    assert panel.calibration_files.snapshot() == before
    app.processEvents()
    QTest.mouseDClick(diagram, Qt.MouseButton.LeftButton)
    assert (diagram.azimuth, diagram.elevation) == (45, 25)
    assert panel.calibration_files.snapshot() == before


def test_bottom_mirror_reflects_cone_and_uses_total_path():
    import math

    from cephvr.gui.projector_geometry import RigDimensions, screen_corners
    from cephvr.gui.projector_optics import bottom_mirror_footprint

    rig = RigDimensions(200, 300, 150, (80, 100, 75))
    values = dict(width="300", height="200", subject_distance="140")
    bottom = screen_corners(rig, "Bottom", values, front_distance="140")
    right = screen_corners(
        rig, "Right", values, front_distance="140", bottom_distance="140"
    )
    folded = bottom_mirror_footprint(bottom, right, "900", "2", 16 / 9, "300")
    assert folded.width == 450 and folded.height == 253.125
    rx, ry, rz = (sum(p[i] for p in right) / 4 for i in range(3))
    assert folded.projector[:2] == (rx + 300, ry)
    assert folded.projector[2] < rz
    assert len(folded.mirror) == 4 and max(p[2] for p in folded.mirror) < 0
    center = tuple(sum(p[i] for p in bottom) / 4 for i in range(3))
    h = math.hypot(folded.projector[0] - center[0], folded.projector[1] - center[1])
    normal = (
        (folded.projector[0] - center[0]) / h / math.sqrt(2),
        (folded.projector[1] - center[1]) / h / math.sqrt(2),
        1 / math.sqrt(2),
    )
    mirror_center = (center[0], center[1], folded.projector[2])
    assert h + center[2] - mirror_center[2] == pytest.approx(900)
    for bounce, target in zip(folded.mirror, folded.corners, strict=True):
        assert sum(
            (bounce[i] - mirror_center[i]) * normal[i] for i in range(3)
        ) == pytest.approx(0, abs=1e-9)
        incoming = tuple(bounce[i] - folded.projector[i] for i in range(3))
        outgoing = tuple(target[i] - bounce[i] for i in range(3))
        incoming = tuple(v / math.sqrt(sum(c * c for c in incoming)) for v in incoming)
        outgoing = tuple(v / math.sqrt(sum(c * c for c in outgoing)) for v in outgoing)
        dot = sum(incoming[i] * normal[i] for i in range(3))
        assert tuple(
            incoming[i] - 2 * dot * normal[i] for i in range(3)
        ) == pytest.approx(outgoing)
    for length, throw, right_distance in (
        ("200", "2", "300"),
        ("900", "2", ""),
    ):
        with pytest.raises(ValueError):
            bottom_mirror_footprint(
                bottom, right, length, throw, 16 / 9, right_distance
            )


def test_plot_legends_are_view_only_and_survive_refresh(
    window: DashboardWindow, app: QApplication
):
    panel = window.devices.projectors
    before = panel.calibration_files.snapshot()
    participation = dict(panel.participation)
    panel.tank.setFixedWidth(180)
    panel.tank.grab()
    regions = dict(panel.tank.legend_regions)
    assert set(regions) == set(panel.tank.visible_elements)
    assert len({region.y() for region in regions.values()}) > 1
    angles = (panel.tank.azimuth, panel.tank.elevation)
    for key, region in regions.items():
        assert panel.tank.visible_elements[key]
        QTest.mouseClick(
            panel.tank, Qt.MouseButton.LeftButton, pos=region.center().toPoint()
        )
        assert not panel.tank.visible_elements[key]
        assert panel.tank.drag_origin is None
    assert (panel.tank.azimuth, panel.tank.elevation) == angles
    window.apply_view(review_view(Phase.RUNNING))
    panel.update_geometry()
    assert not any(panel.tank.visible_elements.values())
    panel.tank.grab()
    assert panel.tank.legend_regions == regions
    for key, region in panel.tank.legend_regions.items():
        QTest.mouseClick(
            panel.tank, Qt.MouseButton.LeftButton, pos=region.center().toPoint()
        )
        assert panel.tank.visible_elements[key]
    assert panel.calibration_files.snapshot() == before
    assert panel.participation == participation
    origin = QPoint(80, 110)
    QTest.mousePress(panel.tank, Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseMove(panel.tank, QPoint(100, 120))
    QTest.mouseRelease(panel.tank, Qt.MouseButton.LeftButton, pos=QPoint(100, 120))
    assert (panel.tank.azimuth, panel.tank.elevation) != angles
    QTest.mouseDClick(panel.tank, Qt.MouseButton.LeftButton, pos=origin)
    assert (panel.tank.azimuth, panel.tank.elevation) == (45.0, 25.0)
    app.processEvents()


def test_bottom_optics_survive_disabled_right_output(window: DashboardWindow):
    from cephvr.gui.projectors import DisplayInfo

    panel = window.devices.projectors
    panel.review_displays = tuple(
        DisplayInfo(face, face, str(i + 2), QRect(i * 1920, 0, 1920, 1080))
        for i, face in enumerate(("Right", "Bottom"))
    )
    panel.request("Refresh displays")
    for face in ("Right", "Bottom"):
        panel.projectors[face].setCurrentText(face)
    for key, value in zip(
        panel.rig_editor.fields, (200, 300, 150, 85, 100, 75), strict=True
    ):
        panel.rig_editor.fields[key].setText(str(value))
    for face, distance in (("Front", 125), ("Left", 110), ("Bottom", 100)):
        panel.rig_editor.screen_distances[face].setText(str(distance))
    for face in ("Right", "Bottom"):
        for key, value in (
            ("width", 300),
            ("height", 200),
            ("distance", 700 if face == "Bottom" else 300),
            ("throw", 2),
        ):
            panel.screen_editor.fields[face, key].setText(str(value))
    before = panel.tank.footprints(panel.tank.screen_planes())["Bottom"]
    assert before.mirror
    panel.enable_controls["Right"].click()
    after = panel.tank.footprints(panel.tank.screen_planes())
    assert set(after) == {"Bottom"} and after["Bottom"] == before
    panel.screen_editor.fields["Bottom", "distance"].setText("100")
    assert panel.tank.footprints(panel.tank.screen_planes()) == {}
    assert "Bottom" in panel.tank.projection_issues
    assert "total path" in panel.tank.toolTip()


def test_label_insertion_repeats_batch_in_original_scope_and_undo(window, app):
    from cephvr.gui.batch_insertion import Insertion, insert_batch
    from cephvr.gui.epoch_batch import epoch_paths
    from cephvr.gui.program_editing import node_at, validate
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import make_group

    base = blank_program()
    data = base.model_dump(mode="json")
    first = data["sequence"][0]
    data["sequence"] = [
        dict(first, epoch_id="a", batch_label="Target"),
        dict(first, epoch_id="b", batch_label="Other"),
        dict(first, epoch_id="c", batch_label="Target"),
    ]
    original, _ = make_group(validate(data), (), 0, 1, 2, False, (), False)
    batch = base.model_copy(
        update={
            "sequence": (base.sequence[0].model_copy(update={"batch_label": "Target"}),)
        }
    )
    result, paths = insert_batch(
        original, batch, (), Insertion("label", label="Target")
    )
    assert len(paths) == 2  # The newly inserted matching labels are not targeted again.
    assert paths == ((0, 1), (2,))
    assert result.sequence[0].repetitions == 2
    assert len(result.sequence[0].body) == 3
    assert len({node_at(result, p).epoch_id for p in epoch_paths(result)}) == 5
    assert len(epoch_paths(original)) == 3
    with pytest.raises(ValueError, match="label"):
        insert_batch(original, batch, (), Insertion("label", label="Missing"))
    editor = window.protocol.editor
    editor.set_program(original)
    editor.enter_group()
    editor.commit(result, scope=(0,), selected=1, paths=((0, 1),))
    editor.undo()
    assert editor.program == original
    app.processEvents()


def test_visible_layer_selector_and_opacity_preserve_prepared_placement(
    window, app, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.stimulus_form import ValueEditor

    window.resize(1350, 900)
    window.page_buttons[1].click()
    editor = window.protocol.editor
    open_protocol_group(editor, generate=True)
    composer = editor.subgroup.composer
    composer.set_screens(("Front",))
    composer.set_asset_root(str(tmp_path))
    path = tmp_path / "tile.png"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(path))
    composer.add_file("Texture", str(path), "Front")
    composer.add_file("Looming image", str(path), "Front")
    app.processEvents()
    row = composer.rows["Front"]
    assert row.layer.count() == 2
    assert row.layer.isVisible() and row.layer.isEnabled()
    assert "Layer" in row.signature
    row.layer.setCurrentIndex(0)
    app.processEvents()
    assert row.stimulus.currentText() == "Texture"
    before = composer.program.sequence[0].settings[0].model_dump(mode="json")
    assert not hasattr(row.parameters, "tabs")
    assert not any(
        isinstance(f, ValueEditor) and "opacity" in f.children_by_key
        for f in row.parameters.forms
    )
    row.parameters.retain.setChecked(False)
    assert row.parameters.apply()
    after = composer.program.sequence[0].settings[0].model_dump(mode="json")
    assert after["opacity"] == before["opacity"]
    assert all(
        after[key] == before[key] for key in ("space", "initial", "width", "height")
    )
    row.layer.setCurrentIndex(1)
    app.processEvents()
    assert row.stimulus.currentText() == "Looming"
    assert row.parameters.layer_index == row.indices[1]
    from PyQt6.QtWidgets import QScrollArea

    window.resize(720, 800)
    for _ in range(4):
        app.processEvents()
    scroll = next(
        s for s in window.findChildren(QScrollArea) if s.isAncestorOf(composer)
    )
    assert scroll.horizontalScrollBar().maximum() == 0
    batch = editor.subgroup
    assert not batch.insert.isVisible()
    assert not batch.repetitions.isVisible()
    assert composer.batch_label.isVisible()
    assert composer.batch_label.mapTo(batch, QPoint()).y() >= (
        composer.duration.mapTo(batch, QPoint()).y()
    )


def test_bottom_center_path_survives_outer_ray_clearance():
    from cephvr.gui.projector_geometry import RigDimensions, screen_corners
    from cephvr.gui.projector_optics import bottom_mirror_footprint

    rig = RigDimensions(200, 300, 150, (85, 100, 75))
    bottom = screen_corners(
        rig,
        "Bottom",
        dict(width="325", height="250", subject_distance="100"),
        front_distance="125",
    )
    right = screen_corners(
        rig,
        "Right",
        dict(width="325", height="180", subject_distance="140"),
        front_distance="125",
        bottom_distance="100",
    )
    # No fixed 700 cutoff: full-cone clearance already works at 650 for this rig.
    for length in ("650", "699", "700"):
        complete = bottom_mirror_footprint(bottom, right, length, "1.6", 16 / 9, "300")
        assert complete.mirror and not complete.warning
    partial = bottom_mirror_footprint(bottom, right, "500", "1.6", 16 / 9, "300")
    assert partial.projector == (525, 142.5, -100)
    assert partial.mirror_center == (100, 142.5, -100)
    assert not partial.mirror and "outer rays" in partial.warning
    assert partial.width == 312.5 and partial.height == 175.78125
    elevated_bottom = screen_corners(
        rig,
        "Bottom",
        dict(width="325", height="250", subject_distance="50"),
        front_distance="125",
    )
    upper_edge = bottom_mirror_footprint(
        elevated_bottom, right, "460", "10", 16 / 9, "300"
    )
    assert upper_edge.mirror_center and upper_edge.warning
    assert "tank bottom" in upper_edge.warning
    for length in ("425", "400"):
        with pytest.raises(ValueError, match="total path"):
            bottom_mirror_footprint(bottom, right, length, "1.6", 16 / 9, "300")


def test_projection_group_replaces_individual_visibility_controls(
    window: DashboardWindow,
):
    from cephvr.gui.theme import COLORS

    panel = window.devices.projectors
    panel.tank.grab()
    assert set(panel.tank.legend_regions) == {
        "tank",
        "screens",
        "projection",
        "subject",
    }
    assert set(panel.tank.visible_elements) == set(panel.tank.legend_regions)
    assert not any(
        control.property("role") == "plot-toggle"
        for control in panel.tank_card.findChildren(QPushButton)
    )
    assert COLORS.footprint != COLORS.projection
    QTest.mouseClick(
        panel.tank,
        Qt.MouseButton.LeftButton,
        pos=panel.tank.legend_regions["projection"].center().toPoint(),
    )
    assert not panel.tank.visible_elements["projection"]
    assert panel.tank.visible_elements["screens"]
    assert panel.enabled_screens == ()


def test_projector_codec_preserves_file_pacing_and_imported_calibration():
    import json

    from tests.visual_stimulus.support import valid_display_json

    from cephvr.gui.projector_codec import merge_projector_draft
    from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb

    profile = json.loads(valid_display_json())
    source_output = profile["outputs"][0]
    source_mapping = profile["mappings"][0]
    faces = ("front", "left", "right", "bottom")
    outputs = []
    mappings = []
    for face in faces:
        output_id = f"projector/{face}"
        outputs.append(
            {
                **source_output,
                "output_id": output_id,
                "device_identity": f"edid:{face}",
                "photometric_profile": {"logical_path": f"measured/{face}.json"},
            }
        )
        mappings.append(
            {
                **source_mapping,
                "mapping_id": f"map-{face}",
                "surface_id": face,
                "output_id": output_id,
                "geometric_profile": {"logical_path": f"measured/geometry-{face}.json"},
            }
        )
    profile["outputs"] = outputs
    profile["mappings"] = mappings
    profile["photometric_mode"] = "calibrated"
    profile["presentation_mode"] = "photodiode_only_vsync"
    profile["photodiode_enabled"] = False
    profile["photodiode_output_id"] = "projector/front"
    profile["photodiode_patch"] = {
        "rect": {"x": 1, "y": 2, "width": 3, "height": 4},
        "high_linear_rgb": [0.8, 0.7, 0.6],
        "low_linear_rgb": [0.1, 0.2, 0.3],
    }
    assert "pacing_output_id" not in profile
    base = visual_stimulus_pb.DisplayConfiguration(profile_json=json.dumps(profile))

    updated = merge_projector_draft(
        base,
        assignments={f"edid:{face}": face.title() for face in faces},
        participation={"edid:left": False},
        pulse_enabled=False,
        pulse_output_identity="edid:bottom",
        presentation_mode="photodiode_only_vsync",
        pulse_patch={"rect": {"x": 0, "y": 0, "width": 3, "height": 4}},
        geometry=None,
        blackout_zones=[dict(face="Left", x=1, y=2, width=10, height=20)],
    )
    result = json.loads(updated.profile_json)

    assert "pacing_output_id" not in result
    assert result["outputs"][1]["enabled"] is False
    assert result["outputs"][1]["blackout_zones"] == [
        dict(x=1, y=2, width=10, height=20)
    ]
    assert result["outputs"][0]["blackout_zones"] == []
    assert result["photodiode_enabled"] is False
    assert result["photodiode_output_id"] == "projector/bottom"
    assert result["photodiode_patch"]["rect"]["x"] == 0
    assert result["photodiode_patch"]["rect"]["y"] == 0
    assert result["photodiode_patch"]["high_linear_rgb"] == [0.8, 0.7, 0.6]
    assert result["photometric_mode"] == "calibrated"
    assert (
        result["outputs"][0]["photometric_profile"]["logical_path"]
        == "measured/front.json"
    )
    assert (
        result["mappings"][0]["geometric_profile"]["logical_path"]
        == "measured/geometry-front.json"
    )


@pytest.mark.parametrize("disconnected", [False, True])
@pytest.mark.parametrize(
    "presentation_mode", ["photodiode_only_vsync", "all_outputs_vsync"]
)
def test_projectors_page_install_collect_keeps_file_owned_pacing_absent(
    window: DashboardWindow,
    disconnected: bool,
    presentation_mode: str,
):
    import json

    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb

    source = json.loads(valid_display_json())
    source["presentation_mode"] = presentation_mode
    source["photodiode_enabled"] = False
    source["photodiode_output_id"] = None
    source.pop("pacing_output_id", None)
    display = visual_stimulus_pb.DisplayConfiguration(profile_json=json.dumps(source))
    panel = window.devices.projectors

    panel.install_configuration(display)
    if disconnected:
        panel.review_displays = ()
        panel.discover_displays()
        assert not panel.keys
    result = panel.configuration_for_submit(display)
    profile = json.loads(result.profile_json)

    assert profile["photodiode_enabled"] is False
    assert "pacing_output_id" not in profile
    from cephvr.visual_stimulus.configuration import load_projection_settings

    assert profile["geometry"] == {**source["geometry"], **load_projection_settings()}
    assert profile["mappings"] == source["mappings"]
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.visual_stimulus.configuration import (
        validate_configuration,
        validate_display_profile,
    )

    if presentation_mode == "all_outputs_vsync":
        assert validate_display_profile(result.profile_json)
        candidate = pb.ExperimentConfiguration()
        backend = candidate.backends.add(backend_name="visual_stimulus")
        backend.visual_stimulus.display.CopyFrom(result)
        validation = validate_configuration(candidate)
        assert validation.completed and validation.valid
    else:
        with pytest.raises(ValueError, match="mixed pacing requires"):
            validate_display_profile(result.profile_json)


@pytest.mark.parametrize("version", [2, 3, 4, 5, 6, 7])
def test_calibration_arena_uses_saved_screen_planes_and_backend_glb_profile(version):
    from cephvr.gui.calibration_arena import (
        geometry_from_calibration,
        make_calibration_glb,
    )
    from cephvr.gui.projector_geometry import FACES
    from cephvr.visual_stimulus.resources.glb import parse_glb

    values = {
        "rig.width": 200,
        "rig.depth": 300,
        "rig.height": 150,
        "rig.subject_x": 80,
        "rig.subject_y": 100,
        "rig.subject_z": 75,
    }
    for face in FACES:
        values[f"screens.{face}.width"] = 180
        values[f"screens.{face}.height"] = 130
        if face != "Right":
            values[f"screens.{face}.subject_distance"] = 90
    payload = {"format": "cephvr-rig-calibration", "version": version, "values": values}
    rig, screens = geometry_from_calibration(payload)
    assert screens["Right"][0][0] == pytest.approx(210)
    scene = parse_glb(
        make_calibration_glb(rig, screens), max_bytes=1_000_000, max_elements=200_000
    )
    primitive = scene.nodes[0].primitives[0]
    assert primitive.colors is not None
    colors = set(primitive.colors)
    assert (1.0, 1.0, 1.0, 1.0) in colors  # face names
    expected_colors = (
        (1.0, 1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0, 1.0),
        (0.025, 0.035, 0.055, 1.0),
        (0.35, 0.4, 0.45, 1.0),
    )
    assert len(colors) == len(expected_colors)
    assert all(
        any(color == pytest.approx(c) for c in expected_colors) for color in colors
    )
    for face in FACES:
        for corner in screens[face]:
            assert any(point == pytest.approx(corner) for point in primitive.positions)
    for invalid in (1, 9, True, 4.0, "4"):
        with pytest.raises(ValueError, match="version 2/3/4/5/6/7"):
            geometry_from_calibration(dict(payload, version=invalid))


@pytest.mark.parametrize("version", [2, 3, 4, 5, 6, 7])
def test_calibration_identity_profiles_bind_unique_native_monitors(tmp_path, version):
    from cephvr.gui.calibration_profile import (
        AssignedDisplay,
        MonitorBinding,
        diagnostic_display_profile,
        write_diagnostic_bundle,
    )
    from cephvr.gui.projector_geometry import FACES

    values = {
        "rig.width": 120,
        "rig.depth": 166,
        "rig.height": 110,
        "rig.subject_x": 60,
        "rig.subject_y": 93,
        "rig.subject_z": 53,
    }
    for face in FACES:
        values[f"screens.{face}.width"] = 90
        values[f"screens.{face}.height"] = 80
        if face != "Right":
            values[f"screens.{face}.subject_distance"] = 50
    calibration = {
        "format": "cephvr-rig-calibration",
        "version": version,
        "values": values,
    }
    assignments = tuple(
        AssignedDisplay(face, index * 1280, 0, 1280, 720, True)
        for index, face in enumerate(FACES)
    )
    monitors = tuple(
        MonitorBinding(f"interface-{index}", index * 1280, 0, 1280, 720, 60, 8)
        for index in range(4)
    )
    zones = [dict(face="Front", x=10, y=20, width=100, height=80)]
    profile, meshes = diagnostic_display_profile(calibration, assignments, monitors)
    masked_profile, _ = diagnostic_display_profile(
        calibration, assignments, monitors, blackout_zones=zones
    )
    assert masked_profile.outputs[0].blackout_zones[0].x == 10
    with pytest.raises(ValueError, match="Blackout zone exceeds"):
        diagnostic_display_profile(
            calibration,
            assignments,
            monitors,
            blackout_zones=[dict(face="Front", x=0, y=0, width=2000, height=80)],
        )
    assert {output.device_identity for output in profile.outputs} == {
        monitor.interface for monitor in monitors
    }
    assert profile.photometric_mode == "uncalibrated"
    assert profile.presentation_mode == "all_outputs_vsync"
    assert profile.geometry.near_mm == 1
    assert profile.geometry.far_mm == 250
    assert profile.geometry.positional_tolerance_mm == 0.000166
    assert profile.geometry.orthogonality_tolerance == 0.000001
    assert set(meshes) == {face.lower() for face in FACES}
    assert all(
        mesh.vertices[0].uv == mesh.vertices[0].xy
        for face, mesh in meshes.items()
        if face != "bottom"
    )
    assert meshes["bottom"].vertices[0].uv == (0, 1)
    assert all(mesh.orientation == "preserving" for mesh in meshes.values())

    bars, bar_meshes = diagnostic_display_profile(
        calibration, assignments, monitors, view="reference_bars"
    )
    assert bars.calibration_view == "reference_bars"
    assert all(
        mesh.vertices[0].uv == mesh.vertices[0].xy for mesh in bar_meshes.values()
    )
    with pytest.raises(ValueError, match="measure both reference bars"):
        diagnostic_display_profile(
            calibration, assignments, monitors, view="frame_grid"
        )
    measured_values = dict(values)
    for face in FACES:
        measured_values.update(
            {
                f"screens.{face}.reference_width_px": 1280,
                f"screens.{face}.reference_height_px": 720,
                f"screens.{face}.reference_x_px": 200,
                f"screens.{face}.reference_y_px": 100,
                f"screens.{face}.reference_x_mm": 80,
                f"screens.{face}.reference_y_mm": 50,
            }
        )
    measured_calibration = dict(calibration, values=measured_values)
    grid, grid_meshes = diagnostic_display_profile(
        measured_calibration, assignments, monitors, view="frame_grid"
    )
    assert grid.calibration_view == "frame_grid"
    assert grid_meshes["front"].vertices[0].xy == (0, 0)
    assert grid_meshes["front"].valid_area == pytest.approx(
        (
            0.5 - round(90 / 0.4) / 1280 / 2,
            0.5 - 160 / 720 / 2,
            0.5 + round(90 / 0.4) / 1280 / 2,
            0.5 + 160 / 720 / 2,
        )
    )
    measured_values["screens.Front.offset_x_px"] = 75
    measured_values["screens.Front.offset_y_px"] = -35
    _, shifted_meshes = diagnostic_display_profile(
        measured_calibration, assignments, monitors, view="frame_grid"
    )
    bounds = shifted_meshes["front"].valid_area
    assert (bounds[0] + bounds[2]) / 2 == pytest.approx(0.5 + 75 / 1280)
    assert (bounds[1] + bounds[3]) / 2 == pytest.approx(0.5 - 35 / 720)
    measured_values["screens.Front.offset_x_px"] = 10000
    with pytest.raises(ValueError, match="projection image"):
        diagnostic_display_profile(
            measured_calibration, assignments, monitors, view="frame_grid"
        )
    measured_values.pop("screens.Front.offset_x_px")
    measured_values.pop("screens.Front.offset_y_px")
    measured_values["screens.Front.throw"] = 1.5
    assert diagnostic_display_profile(
        measured_calibration, assignments, monitors, view="frame_grid"
    ) == (grid, grid_meshes)
    measured_values["screens.Front.reference_width_px"] = 1920
    with pytest.raises(ValueError, match="assigned output mode"):
        diagnostic_display_profile(
            measured_calibration, assignments, monitors, view="frame_grid"
        )
    # Stale measurements and invalid manual correction cannot block remeasurement.
    measured_values["screens.Front.scale_u"] = 100
    remeasured, remeasurement_meshes = diagnostic_display_profile(
        measured_calibration, assignments, monitors, view="reference_bars"
    )
    assert remeasurement_meshes == bar_meshes
    assert remeasured.calibration_view == "reference_bars"
    assert all(
        o.reference_bars.x_length_px == 200 and o.reference_bars.y_length_px == 100
        for o in remeasured.outputs
    )
    values["screens.Front.valid_width_px"] = 1024
    values["screens.Left.flip_x"] = True
    adjusted, adjusted_meshes = diagnostic_display_profile(
        calibration, assignments, monitors
    )
    assert adjusted == profile
    assert adjusted_meshes["front"].vertices == meshes["front"].vertices
    assert adjusted_meshes["front"].valid_area[0] == pytest.approx(0.5 - 0.4)
    assert adjusted_meshes["left"].orientation == "mirrored"
    values["screens.Front.valid_width_px"] = 10000
    with pytest.raises(ValueError, match="whole pixels"):
        diagnostic_display_profile(calibration, assignments, monitors)
    values["screens.Front.offset_x"] = None
    values["screens.Front.valid_width_px"] = None
    values["screens.Left.flip_x"] = False
    with pytest.raises(ValueError, match="unique native monitor"):
        diagnostic_display_profile(calibration, assignments, monitors[:-1])
    runtime = tmp_path / "runtime-data"
    arena_path = write_diagnostic_bundle(
        tmp_path,
        calibration,
        assignments,
        monitors,
        blackout_zones=zones,
        runtime_root=runtime,
    )
    assert arena_path.is_file()
    from cephvr.visual_stimulus.resources.glb import parse_glb

    grid_scene = parse_glb(
        arena_path.read_bytes(), max_bytes=1_000_000, max_elements=200_000
    )
    grid_primitive = grid_scene.nodes[0].primitives[0]
    assert grid_primitive.colors is not None
    grey_quads = [
        grid_primitive.positions[start : start + 4]
        for start in range(0, len(grid_primitive.positions), 4)
        if grid_primitive.colors[start] == pytest.approx((0.35, 0.4, 0.45, 1))
    ]
    assert grey_quads
    # This fixture's vertical pitch is 80/720 mm/px: the old .2mm stroke
    # is too thin, so exporting must propagate native resolution to the mesh.
    import math

    assert all(math.dist(q[0], q[1]) >= 0.2 - 1e-5 for q in grey_quads)
    assert max(math.dist(q[0], q[1]) for q in grey_quads) > 0.22
    assert not (arena_path.parent / "rig_geometry_grid.program.json").exists()
    assert not list(arena_path.parent.glob("*.json"))
    assert (
        runtime / "calibration" / arena_path.name
    ).read_bytes() == arena_path.read_bytes()
    assert (runtime / "calibration/diagnostic_display_profile.json").is_file()
    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

    saved_profile = DisplayProfile.model_validate_json(
        (runtime / "calibration/diagnostic_display_profile.json").read_text()
    )
    assert (
        saved_profile.outputs[0].blackout_zones
        == masked_profile.outputs[0].blackout_zones
    )
    assert all(
        (runtime / "calibration" / f"diagnostic_{face.lower()}.json").is_file()
        for face in FACES
    )

    grid_bytes = arena_path.read_bytes()
    bars_path = write_diagnostic_bundle(
        tmp_path,
        calibration,
        assignments,
        monitors,
        view="reference_bars",
        runtime_root=tmp_path / "bars-runtime",
    )
    assert bars_path.name == "reference_bars.glb"
    assert arena_path.name == "frame_grid.glb" and arena_path.read_bytes() == grid_bytes
    assert {p.name for p in arena_path.parent.iterdir()} == {
        "reference_bars.glb",
        "frame_grid.glb",
    }
    assert len(bars_path.read_bytes()) < len(grid_bytes)
    from cephvr.visual_stimulus.resources.glb import parse_glb

    scene = parse_glb(bars_path.read_bytes(), max_bytes=1_000_000, max_elements=200_000)
    primitive = scene.nodes[0].primitives[0]
    assert primitive.colors is not None
    assert sum(color == (1, 1, 1, 1) for color in primitive.colors) == 16 * len(FACES)
    assert len(primitive.positions) == 24 * len(FACES)  # Four frame edges + two bars.


def test_calibration_button_reflects_confirmed_managed_output(
    window, monkeypatch, tmp_path
):
    panel = window.devices.projectors
    table = panel.calibration
    arena = tmp_path / "frame_grid.glb"
    prepared = []
    result = [arena]

    def prepare(**kwargs):
        prepared.append(kwargs.get("view", "frame_grid"))
        return result[0]

    monkeypatch.setattr(panel, "prepare_calibration", prepare)
    output_requests = []
    panel.calibration_launch_requested.connect(output_requests.append)
    launched: list[bool] = []
    closed: list[bool] = []
    table.launch_requested.connect(lambda: launched.append(True))
    table.close_requested.connect(lambda: closed.append(True))
    assert set(table.findChildren(QPushButton)) == {table.presentation_button}
    assert not table.isAncestorOf(panel.measurements)
    assert panel.measurements.isAncestorOf(table.measurement_button)
    assert table.body.indexOf(table.presentation_button) < table.body.indexOf(
        table.table
    )
    assert panel.measurements.body.indexOf(
        table.measurement_button
    ) < panel.measurements.body.indexOf(panel.measurements.table)
    assert table.measurement_button.text() == "Launch reference calibration"
    assert not table.presentation_button.isEnabled()
    table.set_presentation_state(active=False, available=True)
    table.presentation_button.click()
    assert launched == [True]
    assert prepared == ["frame_grid"]
    assert output_requests == [str(arena)]
    assert table.presentation_button.text() == "Launch projection calibration"
    table.set_presentation_state(active=True, available=True)
    assert table.presentation_button.text() == "Close"
    table.presentation_button.click()
    assert closed == [True]
    assert prepared == ["frame_grid"]
    assert table.presentation_button.text() == "Close"
    table.set_presentation_state(active=True, available=True, pending=True)
    assert not table.presentation_button.isEnabled()
    table.set_presentation_state(active=False, available=False)
    assert table.presentation_button.text() == "Launch projection calibration"
    assert not table.presentation_button.isEnabled()
    result[0] = None
    table.set_presentation_state(active=False, available=True)
    table.presentation_button.click()
    assert prepared == ["frame_grid", "frame_grid"]
    assert output_requests == [str(arena)]  # Failed preparation never requests output.
    result[0] = arena
    table.measurement_button.click()
    assert prepared[-1] == "reference_bars"
    assert output_requests == [str(arena), str(arena)]
    table.set_presentation_state(active=True, available=True)
    assert not table.measurement_button.isEnabled()
    table.measurement_button.click()
    assert len(prepared) == 3
    table.set_presentation_state(active=True, available=True, view="reference_bars")
    assert table.measurement_button.text() == "Close"
    assert table.measurement_button.isEnabled()
    assert table.presentation_button.text() == "Launch projection calibration"
    assert not table.presentation_button.isEnabled()
    table.request_presentation()
    assert closed == [True]
    table.measurement_button.click()
    assert closed == [True, True] and len(prepared) == 3
    table.set_presentation_state(
        active=True, available=True, pending=True, view="reference_bars"
    )
    assert table.measurement_button.text() == "Close"
    assert not table.measurement_button.isEnabled()
    table.request_measurement()
    assert closed == [True, True]
    table.set_presentation_state(active=False, available=True)
    assert table.measurement_button.text() == "Launch reference calibration"
    assert (
        table.measurement_button.isEnabled() and table.presentation_button.isEnabled()
    )
    table.set_presentation_state(active=True, available=True, view="frame_grid")
    assert table.presentation_button.text() == "Close"
    assert table.measurement_button.text() == "Launch reference calibration"
    table.request_measurement()
    assert closed == [True, True]
    table.presentation_button.click()
    assert closed == [True, True, True]


def test_managed_first_use_calibration_launches_before_display_initialization(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    from PyQt6.QtCore import QObject

    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_display import ManagedDisplayOperations
    from cephvr.shared.auth import Principal

    client_id = str(uuid4())
    generation = str(uuid4())
    manager = ManagedGui.__new__(ManagedGui)
    QObject.__init__(manager)
    manager.window = window
    manager.bridge = SimpleNamespace(principal=Principal("gui", client_id, "token"))
    manager.control_ready = True
    manager.close_pending = False
    manager._retained_ack_required = False
    state = pb.Snapshot(controller_generation=generation)
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 4
    state.configuration_values.revision = 4
    state.control.holder_client_id = client_id
    state.configuration_values.current.asset_root = str(tmp_path)
    monkeypatch.setattr(
        "cephvr.gui.managed_display_operations.calibration_asset_root", lambda: tmp_path
    )
    monkeypatch.setattr(
        "cephvr.gui.managed_display_operations.calibration_runtime_root",
        lambda _view: tmp_path,
    )
    calibration_dir = tmp_path / "calibration"
    calibration_dir.mkdir()
    (calibration_dir / "diagnostic_display_profile.json").write_text("{}")
    backend = state.configuration_values.current.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    backend.visual_stimulus.SetInParent()  # First-use: display is absent/incomplete.

    panel = window.devices.projectors
    arena = calibration_dir / "frame_grid.glb"
    arena.write_bytes(b"arena")
    monkeypatch.setattr(panel, "prepare_calibration", lambda **kwargs: arena)
    output_requests: list[str] = []
    panel.calibration_launch_requested.connect(output_requests.append)
    operations = ManagedDisplayOperations(
        panel,
        window.devices.spikeglx,
        snapshot=lambda: state,
        connection_identity=lambda: None,
        send=lambda action, **_kwargs: output_requests.append(action) or True,
    )
    operations.install_calibration_state(
        state, launch_eligible=ManagedGui._calibration_launch_eligible(manager, state)
    )
    panel.calibration_launch_requested.disconnect(output_requests.append)
    panel.calibration_launch_requested.connect(operations.open_calibration)

    assert panel.calibration.presentation_button.isEnabled()
    panel.calibration.presentation_button.click()
    assert output_requests == ["open_display_calibration"]

    manager.close_pending = True
    operations.install_calibration_state(
        state, launch_eligible=ManagedGui._calibration_launch_eligible(manager, state)
    )
    assert not panel.calibration.presentation_button.isEnabled()
    manager.close_pending = False
    state.session.phase = pb.SESSION_PHASE_ENDED
    operations.install_calibration_state(
        state, launch_eligible=ManagedGui._calibration_launch_eligible(manager, state)
    )
    assert not panel.calibration.presentation_button.isEnabled()


def test_unified_feedback_input_mapping_and_retain_state(window, app):
    import json

    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    parameters = editor.parameters
    parameters.more.setChecked(True)
    assert not hasattr(parameters, "tabs")
    margins = parameters.advanced_layout.contentsMargins()
    assert margins.left() == 0 and margins.top() >= 12
    data = editor.program.model_dump(mode="json")
    data["sequence"][0]["settings"][0]["assignments"] = [
        {"target": "phase_x", "value": 0.25}
    ]
    editor.set_program(parse_program_json(json.dumps(data), max_bytes=1_048_576))
    original = editor.program.sequence[0].settings[0]
    parameters.retain.setChecked(True)
    assert parameters.apply()
    assert not editor.program.sequence[0].settings[0].reset
    assert editor.program.sequence[0].settings[0].assignments == original.assignments
    feedback = parameters.feedback
    feedback.add_input(
        {
            "channel_id": "speed",
            "stream_id": "external",
            "frame_id": "screen",
            "value_kind": "interval_average_rate",
            "unit": "mm/s",
        }
    )
    row = feedback.entries[0]
    row.target.setCurrentIndex(row.target.findData("phase_x"))
    row.gain.setText("2")
    row.mark_changed()
    assert parameters.apply()
    setting = editor.program.sequence[0].settings[0]
    mapping = setting.feedback[0]
    assert mapping.binding_id and mapping.operation == "movement_integration"
    assert mapping.source_channel == "speed" and mapping.target == "phase_x"
    assert mapping.gain.value == 2
    assert row.target.findData("opacity") == -1
    assert editor.program.input_channels[0].stream_id == "external"
    before = editor.program
    row.gain.setText("nan")
    row.mark_changed()
    assert not parameters.apply() and editor.program == before
    row.gain.setText("3")
    row.mark_changed()
    assert parameters.apply()
    assert (
        parse_program_json(editor.program.model_dump_json(), max_bytes=1_048_576)
        == editor.program
    )
    # Removing a mapping preserves declarations other epochs might reference.
    feedback.remove(row)
    assert parameters.apply()
    assert not editor.program.sequence[0].settings[0].feedback
    assert editor.program.input_channels
    feedback.add_input(
        {
            "channel_id": "brightness",
            "stream_id": "external",
            "frame_id": "screen",
            "value_kind": "absolute",
            "unit": "1",
        }
    )
    row = feedback.entries[0]
    row.target.setCurrentIndex(row.target.findData("opacity"))
    assert parameters.apply()
    assert (
        editor.program.sequence[0].settings[0].feedback[0].operation == "direct_value"
    )
    assert (
        json.loads(editor.program.model_dump_json())["sequence"][0]["settings"][0][
            "reset"
        ]
        is False
    )
    app.processEvents()


def test_arena_feedback_and_axis_editors_stay_synchronized(window, tmp_path):
    from cephvr.gui.arena_movement import ArenaMovement

    composer = window.protocol.editor.subgroup.composer
    composer.set_asset_root(str(tmp_path))
    composer.set_subject_height("0")
    composer.mode.setCurrentIndex(1)
    path = tmp_path / "arena.glb"
    path.touch()
    params = composer.rows[""].parameters
    params.set_media_path(next(iter(params.asset_forms)), str(path))
    axes = next(f for f in params.forms if isinstance(f, ArenaMovement))
    axes.axes[0].setChecked(True)
    assert params.apply()
    feedback = params.feedback
    assert len(feedback.entries) == 1
    row = feedback.entries[0]
    row.gain.setText("4")
    row.sideways.setText("3")
    row.mark_changed()
    assert params.apply()
    assert axes.gains[0].text() == "4" and axes.gains[1].text() == "3"
    assert axes.axes[1].isChecked()
    axes.gains[0].setText("7")
    axes.mark_edited()
    assert params.apply()
    assert row.gain.text() == "7"
    feedback.remove(row)
    assert params.apply()
    assert not any(a.isChecked() for a in axes.axes)
    assert not axes.read()["feedback"]


def test_stimulus_mode_and_duration_use_proportional_header_widths(window, app):
    window.page_buttons[1].click()
    open_protocol_group(window.protocol.editor, generate=True)
    batch = window.protocol.editor.subgroup
    for width in (1350, 720):
        window.resize(width, 900)
        app.processEvents()
        if width == 1350:
            assert batch.composer.mode.width() > batch.composer.duration.width()
        assert batch.composer.mode.width() > 0 and batch.composer.duration.width() > 0
        assert (
            batch.composer.mode.mapTo(batch, QPoint()).y()
            == batch.composer.duration.mapTo(batch, QPoint()).y()
        )


def test_new_stimuli_retain_state_without_changing_imported_reset(window, app):
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import PRESETS, add_stimulus

    for preset in PRESETS:
        program = add_stimulus(blank_program(), 0, preset, ("Front",))
        assert not program.sequence[0].settings[0].reset
    editor = ParameterDocument(window)
    program = add_stimulus(blank_program(), 0, "Texture", ("Front",))
    epoch = program.sequence[0]
    setting = epoch.settings[0].model_copy(update={"reset": True})
    imported = program.model_copy(
        update={"sequence": (epoch.model_copy(update={"settings": (setting,)}),)}
    )
    editor.set_program(imported)
    assert not editor.parameters.retain.isChecked()
    assert editor.program.sequence[0].settings[0].reset


def test_reference_advanced_controls_align_to_layer_and_retain_first(window, app):
    from cephvr.gui.protocol_document import blank_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(blank_program())
    open_protocol_group(editor, generate=True)
    composer = editor.subgroup.composer
    composer.set_screens(("Front", "Bottom"))
    composer.change_type("Front", "Texture")
    row = composer.rows["Front"]
    row.actions_button.setChecked(True)
    for width in (1350, 720):
        window.resize(width, 900)
        app.processEvents()
        row.align_advanced()
        QTest.qWait(10)
        app.processEvents()
        params = row.parameters
        assert params.extra_body.itemAt(1).widget() is params.retain
        appearance = params.extra_body.itemAt(2).widget()
        assert appearance is not None
        assert params.fades is not None
        for control in (params.fades.fade_in, params.fades.fade_out):
            bottom = control.mapTo(appearance, QPoint(0, control.height())).y()
            assert bottom <= appearance.height()
        assert (
            params.advanced_card.mapTo(row, QPoint()).x()
            == row.layer.mapTo(row, QPoint()).x()
        )
        assert (
            params.retain.mapTo(row, QPoint()).y()
            < params.feedback.mapTo(row, QPoint()).y()
        )
        assert (
            params.feedback.mapTo(row, QPoint()).x()
            == params.retain.mapTo(row, QPoint()).x()
        )


def test_control_dialog_does_not_expand_projector_row_and_cancels(window, app):
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    params = editor.parameters
    controls = params.feedback
    assert controls.add.isHidden()
    window.protocol.session_mode.setCurrentText("Closed-loop")
    assert not controls.add.isHidden()
    original = editor.program
    controls.add.click()
    app.processEvents()
    assert controls.dialog.isVisible()
    assert controls.add.isHidden()
    assert not controls.entries
    assert controls.layout().indexOf(controls.add) >= 0
    assert params.advanced_card.isAncestorOf(controls.add)
    assert not params.advanced_card.isAncestorOf(controls.editor)
    draft = controls.editor
    assert [draft.input.itemData(i) for i in range(draft.input.count())] == [
        "forward_drive",
        "sideways_drive",
        "turn_drive",
    ]
    assert not draft.save.isEnabled()  # V24's 2D conversion is still unresolved.
    draft.cancel.click()
    assert not controls.dialog.isVisible() and editor.program == original
    assert not controls.add.isHidden()
    assert not controls.entries
    controls.add.click()
    window.protocol.session_mode.setCurrentText("Open-loop")
    assert not controls.dialog.isVisible() and controls.add.isHidden()
    assert editor.program == original


def test_control_action_is_limited_to_closed_loop_texture_and_looming(window):
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    window.protocol.session_mode.setCurrentText("Closed-loop")
    for kind in ("Texture", "Looming image", "Image", "Video", "3D arena"):
        editor.set_program(blank_program())
        editor.add_stimulus(kind)
        assert editor.parameters.feedback.add.isHidden() == (
            kind not in ("Texture", "Looming image")
        )


def test_fades_render_and_retime_without_changing_motion(window):
    from cephvr.gui.epoch_batch import apply_batch
    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.rendering.motion import evaluate_function

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    params = editor.parameters
    before = editor.program.sequence[0].settings[0]
    params.fades.fade_in.setText("2")
    params.fades.fade_out.setText("3")
    params.fades.mark_changed()
    assert params.apply()
    setting = editor.program.sequence[0].settings[0]
    assert setting.motion == before.motion and setting.reset == before.reset
    duration = editor.program.sequence[0].duration.duration.ns()
    assert evaluate_function(setting.opacity, 0) == 0
    assert evaluate_function(setting.opacity, 1_000_000_000) == 0.5
    assert evaluate_function(setting.opacity, 2_000_000_000) == 1
    assert evaluate_function(setting.opacity, duration - 1_500_000_000) == 0.5
    assert evaluate_function(setting.opacity, duration) == 0
    changed = apply_batch(editor.program, ((0,),), None, {"Duration": "120"})
    opacity = changed.sequence[0].settings[0].opacity
    assert evaluate_function(opacity, 118_500_000_000) == 0.5
    original = editor.program
    params.fades.fade_out.setText("1000")
    params.fades.mark_changed()
    assert not params.apply() and editor.program == original


def test_reference_fades_follow_batch_duration_and_new_rows(window, tmp_path):
    from PyQt6.QtGui import QImage

    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.rendering.motion import evaluate_function

    editor = window.protocol.editor
    editor.set_program(blank_program())
    composer = editor.subgroup.composer
    composer.set_screens(("Front",))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    composer.set_asset_root(str(tmp_path))
    composer.add_file("Texture", str(path), "Front")
    parameters = composer.rows["Front"].parameters
    parameters.fades.fade_in.setText("1")
    parameters.fades.fade_out.setText("2")
    parameters.fades.mark_changed()
    assert parameters.apply()
    composer.duration.setText("00:00:30")
    composer.update_duration()
    assert not composer.message.text()
    setting = composer.program.sequence[0].settings[0]
    assert evaluate_function(setting.opacity, 29_000_000_000) == 0.5
    composer.set_screens(("Front", "Bottom"))
    composer.change_type("Bottom", "Texture")
    assert composer.rows["Bottom"].parameters.fades.duration_ns == 30_000_000_000
    before = composer.program
    composer.duration.setText("00:00:02")
    composer.update_duration()
    assert "fit within" in composer.message.text() and composer.program == before


def test_imported_opacity_curve_is_preserved_and_not_editable(window):
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import blank_program

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    data = editor.program.model_dump(mode="json")
    curve = {"kind": "ramp", "initial": 0.1, "slope_per_s": 0.001}
    data["sequence"][0]["settings"][0]["opacity"] = curve
    editor.set_program(validate(data))
    parameters = editor.parameters
    assert not parameters.fades.fade_in.isEnabled()
    parameters.retain.setChecked(False)
    assert parameters.apply()
    assert (
        editor.program.sequence[0].settings[0].opacity.model_dump(mode="json") == curve
    )


def test_blank_layer_then_family_keeps_each_projector_layer_configuration(
    window, app, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.looming_size import LoomingSize
    from cephvr.gui.protocol_groups import motion_numbers

    composer = window.protocol.editor.subgroup.composer
    composer.set_screens(("Front", "Right"))
    composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    row = composer.rows["Front"]
    before = composer.program
    row.add.trigger()
    assert row.layer.currentText() == "1"
    assert row.stimulus.currentText() == "None"
    assert composer.program is before and composer.picker.dialog is None
    row.stimulus.setCurrentText("Texture")
    parameters = row.parameters
    identity = next(iter(parameters.asset_forms))
    parameters.set_media_path(identity, str(path))
    motion = next(f for f in row.parameters.forms if isinstance(f, EpochMotion))
    motion.speed.setText("17")
    motion.direction.setText("90")
    motion.edited = True
    row.parameters.mark_changed()
    assert row.parameters.apply()
    first = (
        composer.program.sequence[0].settings[row.parameters.layer_index].instance_id
    )
    row.add.trigger()
    assert row.layer.currentText() == "2"
    row.stimulus.setCurrentText("Looming")
    row.parameters.set_media_path(next(iter(row.parameters.asset_forms)), str(path))
    looming = next(f for f in row.parameters.forms if isinstance(f, LoomingSize))
    looming.end.setText("77")
    looming.edited = True
    row.parameters.mark_changed()
    assert row.parameters.apply()
    second = (
        composer.program.sequence[0].settings[row.parameters.layer_index].instance_id
    )
    composer.add_file("Texture", str(path), "Right")
    row.layer.setCurrentIndex(row.layer.findData(first))
    assert motion_numbers(
        composer.program.sequence[0]
        .settings[row.parameters.layer_index]
        .model_dump(mode="json")
    )[:2] == pytest.approx((17, 90))
    row.layer.setCurrentIndex(row.layer.findData(second))
    assert (
        composer.program.sequence[0]
        .settings[row.parameters.layer_index]
        .width.knots[-1]
        .value
        == 77
    )
    assert composer.rows["Right"].parameters.program is composer.program
    row.add.trigger()
    row.remove.trigger()
    assert not row.slots.blanks and row.layer.count() == 2


def test_first_source_epoch_fade_does_not_change_rest_of_batch(window):
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    data = editor.program.model_dump(mode="json")
    source = data["sequence"][0]
    data["sequence"] = [
        {
            **source,
            "epoch_id": f"Epoch_{i}",
            "duration": {"kind": "fixed", "duration": {"seconds": "20"}},
        }
        for i in range(3)
    ]
    editor.set_program(validate(data))
    open_protocol_group(editor)
    editor.select_epochs(((0, 0),))
    parameters = editor.subgroup.composer.rows["Front"].parameters
    parameters.more.setChecked(True)
    parameters.fades.fade_in.setText("2")
    parameters.fades.mark_changed()
    assert parameters.apply()
    editor.subgroup.apply()
    epochs = editor.program.sequence[0].body
    assert epochs[0].settings[0].opacity.kind == "keyframes"
    assert all(e.settings[0].opacity.kind == "constant" for e in epochs[1:])


def test_200_epoch_timeline_reuses_views_and_metadata_noop(window, monkeypatch):
    from cephvr.gui import protocol_timeline, timeline_views
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.protocol_nodes import edit_epoch_metadata

    calls = []
    source_nodes = timeline_views.nodes_at

    def counted(program, scope=()):
        calls.append(program)
        return source_nodes(program, scope)

    monkeypatch.setattr(timeline_views, "nodes_at", counted)
    base = review_program()
    program = base.model_copy(
        update={
            "sequence": tuple(
                base.sequence[i % len(base.sequence)].model_copy(
                    update={"epoch_id": f"Epoch_{i}"}
                )
                for i in range(200)
            )
        }
    )
    timeline = window.protocol.editor.timeline
    lane_scans = []
    layers = protocol_timeline.layers_for

    def counted_layers(*args):
        lane_scans.append(args)
        return layers(*args)

    monkeypatch.setattr(protocol_timeline, "layers_for", counted_layers)
    timeline.set_program(program)
    nodes = timeline.nodes
    scan_count = len(lane_scans)
    for index in (1, 20, 100, 199):
        timeline.set_program(program, index)
        assert timeline.nodes is nodes and timeline.paths[timeline.index] == (index,)
        assert len(lane_scans) == scan_count
    assert len(calls) == 1
    first = program.sequence[0]
    assert (
        edit_epoch_metadata(program, 0, first.epoch_id, first.duration.duration.seconds)
        is program
    )
    changed = edit_epoch_metadata(
        program, 0, "Changed", first.duration.duration.seconds
    )
    timeline.set_program(changed)
    assert len(calls) == 2 and timeline.nodes[0].epoch_id == "Changed"
    timeline.set_program(program)
    assert len(calls) == 2 and timeline.nodes is nodes
    for i in range(5):
        timeline.set_program(
            edit_epoch_metadata(
                program, 0, f"Version_{i}", first.duration.duration.seconds
            )
        )
    assert len(timeline.views.entries) == 4


def test_200_epoch_eight_layer_protocol_round_trip_exceeds_old_gui_limit(
    window, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_file_stimulus
    from cephvr.visual_stimulus.config.models.schema_common import (
        DEFAULT_DOCUMENT_BYTES,
    )

    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    asset = tmp_path / "tile.png"
    assert image.save(str(asset))
    base = blank_program()
    for face in ("Front", "Left", "Right", "Bottom"):
        for kind in ("Texture", "Looming image"):
            base = add_file_stimulus(base, 0, kind, (face,), str(tmp_path), str(asset))
    program = base.model_copy(
        update={
            "sequence": tuple(
                base.sequence[0].model_copy(update={"epoch_id": f"Epoch_{i}"})
                for i in range(200)
            )
        }
    )
    path = tmp_path / "large.json"
    raw = program.model_dump_json(indent=2)
    assert 1_048_576 < len(raw.encode()) < DEFAULT_DOCUMENT_BYTES
    path.write_text(raw)
    window.protocol.load_program(str(path))
    assert window.protocol.editor.program == program
    assert len(window.protocol.editor.timeline.nodes) == 200
    saved = tmp_path / "saved.json"
    window.protocol.save_program(str(saved))
    window.protocol.load_program(str(saved))
    assert window.protocol.editor.program == program


def test_variation_controls_fit_narrow_protocol_without_horizontal_scroll(
    window, app, tmp_path
):
    from PyQt6.QtGui import QImage

    window.page_buttons[1].click()
    window.protocol.session_mode.setCurrentText("Closed-loop")
    editor = window.protocol.editor
    open_protocol_group(editor)
    composer = editor.subgroup.composer
    composer.set_screens(("Front", "Right"))
    composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "a_prepared_texture_with_a_long_filename.png"
    assert image.save(str(path))
    composer.add_file("Texture", str(path), "Front")
    composer.add_file("Texture", str(path), "Front")
    composer.rows["Front"].actions_button.setChecked(True)
    form = editor.subgroup
    assert not hasattr(form, "vary") and form.add_rule.isVisible()
    form.add_rule.click()
    row = form.rows[0]
    row.layer.setCurrentIndex(row.layer.findData(-1))
    assert row.layer.currentText() == "All"
    for width in (1280, 720):
        window.resize(width, 1000)
        for method in ("Values", "Sweep (min, max, step)", "Random"):
            row.method.setCurrentText(method)
            QTest.qWait(30)
            app.processEvents()
            assert row.layer.width() == 64
            table = form.variation_table
            assert table.columnCount() == 6
            assert table.columnViewportPosition(2) >= table.columnViewportPosition(
                1
            ) + table.columnWidth(1)
            assert row.target.height() == row.layer.height() == row.parameter.height()
            assert window.protocol.config_scroll.horizontalScrollBar().maximum() == 0
    form.remove_variation(row)
    assert not form.rows and form.add_rule.isVisible()


def test_batch_variations_target_projectors_and_local_layer_ordinals(
    window, app, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.components import Card
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    open_protocol_group(editor)
    create = editor.subgroup
    create.composer.set_screens(("Left", "Right"))
    create.composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    for face in ("Left", "Right"):
        for _ in range(2):
            create.composer.add_file("Texture", str(path), face)
    create.add_variation()
    row = create.rows[0]
    assert isinstance(create.variation_host, Card)
    assert not hasattr(create, "combine")
    row.target.setCurrentIndex(row.target.findText("All projectors"))
    row.layer.setCurrentIndex(row.layer.findData(1))
    row.values.setText("10, 20")
    epochs = expand_program(
        create.candidate(), seed_decimal="0", max_expanded_epochs=2000
    )
    assert len(epochs) == 2
    for epoch, speed in zip(epochs, (10, 20), strict=True):
        for index in row.target_indices():
            assert (
                motion_numbers(epoch.settings[index].model_dump(mode="json"))[0]
                == speed
            )
        for index in (0, 2):
            assert motion_numbers(epoch.settings[index].model_dump(mode="json"))[0] == 0
    row.target.setCurrentIndex(row.target.findText("Right"))
    row.layer.setCurrentIndex(row.layer.findData(-1))
    assert row.target_indices() == [2, 3]
    for width in (1350, 720):
        window.resize(width, 900)
        app.processEvents()
        table = create.variation_table
        assert table.isVisible() and row.isVisible() and row.parameter.isVisible()
        assert table.cellWidget(0, 2).isAncestorOf(row.parameter)
        assert table.cellWidget(0, 5).isAncestorOf(row.remove)
        assert (
            row.remove.mapTo(table.viewport(), QPoint()).y()
            == row.parameter.mapTo(table.viewport(), QPoint()).y()
        )
        assert row.remove.height() == row.parameter.height()
    create.composer.remove_layer("Right")
    with pytest.raises(ValueError, match="varied layer changed"):
        create.candidate()


def test_layer_actions_offer_up_down_and_preserve_projector_values(
    window, app, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.projector_layers import layers_for

    window.page_buttons[1].click()
    composer = window.protocol.editor.subgroup.composer
    composer.set_screens(("Left", "Right"))
    composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    for face in ("Left", "Left", "Right"):
        composer.add_file("Texture", str(path), face)
    left = composer.rows["Left"]
    assert [
        a.text() for a in left.layer.operations.actions() if not a.isSeparator()
    ] == ["Add layer", "Remove layer", "Move layer"]
    assert [a.text() for a in left.move_menu.actions()] == ["Move up", "Move down"]
    assert left.actions_button.isCheckable()
    assert left.actions_button.menu() is None
    assert left.layer.isEnabled()
    left.layer.showPopup()
    assert [a.text() for a in left.layer.menu.actions() if not a.isSeparator()] == [
        "1",
        "2",
        "Add layer",
        "Remove layer",
        "Move layer",
    ]
    left.layer.menu.actions()[0].trigger()
    left.layer.hidePopup()
    assert left.layer.currentIndex() == 0
    original = composer.program
    right = tuple(s for s in original.sequence[0].settings if "right" in str(s.space))
    left.select_layer(0)
    assert not left.backward.isEnabled() and left.forward.isEnabled()
    left.forward.trigger()
    epoch = composer.program.sequence[0]
    ids = [
        epoch.settings[i].instance_id
        for i in layers_for(composer.program, epoch, "Left")
    ]
    assert ids == [
        original.sequence[0].settings[1].instance_id,
        original.sequence[0].settings[0].instance_id,
    ]
    assert left.backward.isEnabled() and not left.forward.isEnabled()
    left.backward.trigger()
    assert composer.program.sequence[0].settings[-1] == right[0]
    assert [a.text() for a in left.move_menu.actions()] == ["Move up", "Move down"]


def test_variations_use_stimulus_columns_and_materialize_looming_and_video(
    app, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.batch_create import BatchCreate
    from cephvr.gui.batch_values import ValueRule, materialize_values
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_columns import stimulus_columns
    from cephvr.gui.stimulus_presets import add_stimulus

    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    create = BatchCreate()
    create.composer.set_asset_root(str(tmp_path))
    create.composer.set_screens(("Left",))
    create.composer.add_file("Looming image", str(path), "Left")
    create.add_variation()
    row = create.rows[0]
    columns = stimulus_columns(create.composer.program.sequence[0].settings[0])
    assert [row.parameter.itemText(i) for i in range(row.parameter.count())] == [
        label for label, _ in columns
    ]
    row.parameter.setCurrentIndex(row.parameter.findData("End size"))
    row.values.setText("10, 20, 30")
    program = create.candidate()
    assert [epoch.settings[0].width.knots[-1].value for epoch in program.sequence] == [
        10,
        20,
        30,
    ]
    assert [epoch.settings[0].height.knots[-1].value for epoch in program.sequence] == [
        10,
        20,
        30,
    ]
    assert not any(
        row.parameter.findData(name) >= 0
        for name in ("Width", "Height", "Opacity", "Angular speed")
    )
    video = add_stimulus(blank_program(), 0, "Video", ("Left",))
    varied = materialize_values(
        video,
        (
            ValueRule((0,), 0, "Playback start", ("0", "2")),
            ValueRule((0,), 0, "At end", ("loop", "hold final frame")),
        ),
    )
    assert [e.settings[0].initial_playback.ns() for e in varied.sequence] == [
        0,
        2_000_000_000,
    ]
    assert [e.settings[0].end_behavior for e in varied.sequence] == [
        "loop",
        "hold_final_frame",
    ]
    create.deleteLater()


def test_preview_uses_retained_motion_and_backward_scrubbing(app):
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.trial_preview_plan import PreviewPlan
    from cephvr.visual_stimulus.config.models.program_model import Rate, Time

    program = add_stimulus(blank_program(), 0, "Image", ("Left",))
    epoch = program.sequence[0]
    setting = epoch.settings[0]
    motion = setting.motion.model_copy(
        update={
            "x": Rate.model_validate(
                {"kind": "rate", "function": {"kind": "constant", "value": 2}}
            )
        }
    )
    setting = setting.model_copy(update={"motion": motion, "reset": False})
    epoch = epoch.model_copy(
        update={
            "settings": (setting,),
            "duration": epoch.duration.model_copy(
                update={"duration": Time(seconds="2")}
            ),
        }
    )
    program = program.model_copy(
        update={"sequence": (epoch, epoch.model_copy(update={"epoch_id": "second"}))}
    )
    plan = PreviewPlan(program)
    initial = float(setting.initial.x)
    assert plan.seek(3_000_000_000)[0].values["x"] == initial + 6
    assert plan.seek(1_000_000_000)[0].values["x"] == initial + 2
    assert plan.seek(3_000_000_000)[0].values["x"] == initial + 6
    assert program.sequence[0].settings[0].initial.x == initial


def test_trial_preview_is_read_only_has_enabled_screens_and_cleans_up(
    window, app, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_file_stimulus

    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    program = add_file_stimulus(
        blank_program(), 0, "Texture", ("Left",), str(tmp_path), str(path)
    )
    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(program)
    window.protocol.assets.folders["root"].editor.setText(str(tmp_path))
    editor.output_preview_button.click()
    app.processEvents()
    preview = window.trial_preview
    assert preview is not None and preview.isVisible()
    assert tuple(preview.canvases) == ("Left", "Right")
    assert preview.rig_view.enabled_faces == ("Left", "Right")
    assert preview.rig_view.snapshot.rig is None
    preview.grab()
    assert len(preview.media.images) == 1
    preview.slider.setValue(5000)
    assert preview.time_ns == preview.plan.total_ns // 2
    preview.play.click()
    assert preview.playing and preview.play.text() == "Pause"
    preview.play.click()
    assert not preview.playing and preview.play.text() == "Play"
    assert editor.program == program
    preview.close()
    from PyQt6.sip import isdeleted

    assert isdeleted(preview.timer) or not preview.timer.isActive()
    assert not preview.media.images and not preview.media.videos
    app.processEvents()
    assert window.trial_preview is None


def test_preview_rejects_setup_resolved_durations_without_mutating_program(app):
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.trial_preview_plan import PreviewPlan
    from cephvr.visual_stimulus.config.models.program_model import Random

    original = review_program()
    source = original.sequence[0]
    program = original.model_copy(
        update={
            "sequence": (source.model_copy(update={"duration": Random(kind="random")}),)
        }
    )
    with pytest.raises(ValueError, match="fixed epoch durations"):
        PreviewPlan(program)
    assert original.sequence[0].duration.kind == "fixed"


def test_planning_arena_draws_a_bounded_glb_on_a_configured_surface(app, tmp_path):
    import json
    import struct

    from PyQt6.QtWidgets import QWidget

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_file_stimulus
    from cephvr.gui.trial_preview import TrialPreview
    from cephvr.gui.trial_preview_surfaces import PreviewGeometry, PreviewSurface

    binary = struct.pack("<9f3H", -20, -150, -20, 20, -150, -20, 0, -150, 20, 0, 1, 2)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": 3},
            {"bufferView": 1, "componentType": 5123, "type": "SCALAR", "count": 3},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    raw = json.dumps(document).encode()
    raw += b" " * (-len(raw) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    chunks = (
        struct.pack("<II", len(raw), 0x4E4F534A)
        + raw
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )
    path = tmp_path / "arena.glb"
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks)
    program = add_file_stimulus(
        blank_program(), 0, "3D arena", (), str(tmp_path), str(path)
    )
    epoch = program.sequence[0]
    setting = epoch.settings[0].model_copy(update={"fixed_height_mm": 0.0})
    program = program.model_copy(
        update={"sequence": (epoch.model_copy(update={"settings": (setting,)}),)}
    )
    geometry = PreviewGeometry(
        {
            "Front": PreviewSurface(
                100,
                100,
                ((50, -100, -50), (-50, -100, -50), (-50, -100, 50), (50, -100, 50)),
            )
        },
        (0, 0, 0),
    )
    parent = QWidget()
    preview = TrialPreview(program, ("Front",), str(tmp_path), geometry, parent)
    preview.show()
    app.processEvents()
    image = preview.canvases["Front"].grab().toImage()
    assert image.pixelColor(image.width() // 2, image.height() // 2).red() > 200
    assert len(preview.media.arenas.scenes) == 1
    preview.close()
    app.processEvents()
    parent.deleteLater()


def test_arena_variations_change_axis_gains_without_changing_other_axes(app):
    from cephvr.gui.batch_values import ValueRule, materialize_values
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus

    program = add_stimulus(blank_program(), 0, "3D arena", ())
    result = materialize_values(
        program, (ValueRule((0,), 0, "Longitudinal", ("0.5", "1")),)
    )
    assert len(result.sequence) == 2
    for epoch, gain in zip(result.sequence, (0.5, 1), strict=True):
        binding = epoch.settings[0].feedback[0]
        assert binding.gain.value == gain
        assert binding.sideways_gain.value == 0
    assert {c.channel_id for c in result.input_channels} == {
        "forward_drive",
        "sideways_drive",
    }
    assert not program.sequence[0].settings[0].feedback


def test_planning_preview_uses_rig_planes_and_only_enabled_projector_frames(
    app, tmp_path
):
    from PyQt6.QtWidgets import QWidget

    from cephvr.gui.projector_geometry import RigDimensions
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.trial_preview import TrialPreview
    from cephvr.gui.trial_preview_surfaces import PreviewGeometry

    rig = RigDimensions(200, 300, 150, (100, 150, 75))
    drafts = {
        face: {"width": "200", "height": "150", "subject_distance": "150"}
        for face in ("Front", "Left", "Right", "Bottom")
    }
    geometry = PreviewGeometry.from_drafts(rig, drafts)
    parent = QWidget()
    preview = TrialPreview(
        add_stimulus(blank_program(), 0, "Texture", ("Front",)),
        ("Front", "Bottom"),
        str(tmp_path),
        geometry,
        parent,
    )
    preview.show()
    app.processEvents()
    view = preview.rig_view
    assert view.rig == rig
    assert view.azimuth == 25.0
    view.grab()
    assert view.face_labels["Left · Off"].x() < view.face_labels["Right · Off"].x()
    assert max(p[0] for p in view.screen_planes()["Left"]) < rig.subject[0]
    assert min(p[0] for p in view.screen_planes()["Right"]) > rig.subject[0]
    assert set(view.screen_planes()) == {"Front", "Left", "Right", "Bottom"}
    assert view.screen_planes()["Front"] == list(geometry.surfaces["Front"].corners)
    view.grab()
    assert set(view.frames) == {"Front", "Bottom"}
    # Both camera hemispheres paint the enabled screen, not just its inward face.
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor, QImage, QPainter, QPolygonF

    original_frame = view.frames["Front"]
    white = QImage(16, 16, QImage.Format.Format_RGB32)
    white.fill(QColor("white"))
    view.frames["Front"] = white
    for azimuth, elevation in ((45, 25), (155, 25), (225, -25), (315, -25)):
        view.azimuth, view.elevation = azimuth, elevation
        target = QImage(100, 100, QImage.Format.Format_RGB32)
        target.fill(QColor("black"))
        painter = QPainter(target)
        view.draw_screen(
            painter,
            "Front",
            QPolygonF(
                [QPointF(10, 90), QPointF(90, 90), QPointF(90, 10), QPointF(10, 10)]
            ),
        )
        painter.end()
        assert target.pixelColor(50, 50) == QColor("white")
        assert "Front" in view.face_labels
    view.frames["Front"] = original_frame
    cached = view.frames["Front"].cacheKey()
    view.azimuth += 40
    view.grab()
    assert view.frames["Front"].cacheKey() == cached
    preview.slider.setValue(1000)
    view.grab()
    assert view.frames["Front"].cacheKey() != cached
    assert all(
        max(image.width(), image.height()) <= 512 for image in view.frames.values()
    )
    preview.close()
    app.processEvents()
    parent.deleteLater()


def test_preview_calibration_matches_export_and_uses_display_pixels(app):
    from PyQt6.QtGui import QColor, QImage

    from cephvr.gui.calibration_profile import MonitorBinding, face_mapping
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.trial_preview_canvas import PreviewCanvas
    from cephvr.gui.trial_preview_media import PreviewMedia
    from cephvr.gui.trial_preview_surfaces import (
        PreviewCorrection,
        PreviewGeometry,
        PreviewSurface,
    )

    draft = {
        "valid_width_px": "50",
        "valid_height_px": "50",
        "offset_x_px": "10",
        "offset_y_px": "20",
        "flip_x": "True",
        "flip_y": "False",
    }
    correction = PreviewCorrection.from_draft("Front", draft, (100, 100))
    assert not correction.error
    assert correction.valid_area == pytest.approx((0.35, 0.45, 0.85, 0.95))
    values = {
        f"screens.Front.{key}": value.lower() == "true"
        if key.startswith("flip")
        else float(value)
        for key, value in draft.items()
    }
    vertices, _ = face_mapping(
        {"values": values}, "Front", MonitorBinding("", 0, 0, 100, 100, 60, 8)
    )
    assert correction.corners == tuple(vertices[i]["xy"] for i in (0, 1, 3, 2))
    media = PreviewMedia(blank_program(), "", None)
    canvas = PreviewCanvas(
        "Front",
        media,
        PreviewGeometry(
            {"Front": PreviewSurface(100, 100, correction=correction)}, (0, 0, 0)
        ),
    )
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    for x in range(50, 100):
        for y in range(100):
            image.setPixelColor(x, y, QColor("blue"))
    output = canvas.correct_frame(image)
    assert output.pixelColor(40, 30) == QColor("blue")
    assert output.pixelColor(60, 30) == QColor("red")
    assert output.pixelColor(20, 30) == QColor("black")
    assert output.pixelColor(50, 80) == QColor("black")
    # The same pixel offset becomes a smaller normalized shift on a larger display.
    larger = PreviewCorrection.from_draft("Front", draft, (200, 200))
    assert larger.valid_area != correction.valid_area
    assert larger.valid_area[0] == pytest.approx(0.425)
    assert larger.valid_area[1] == pytest.approx(0.475)
    vertical = PreviewCorrection.from_draft("Front", {"flip_y": "True"}, (100, 100))
    canvas.rig_geometry = PreviewGeometry(
        {"Front": PreviewSurface(100, 100, correction=vertical)}, (0, 0, 0)
    )
    image.fill(QColor("red"))
    for y in range(50, 100):
        for x in range(100):
            image.setPixelColor(x, y, QColor("blue"))
    flipped = canvas.correct_frame(image)
    assert flipped.pixelColor(25, 25) == QColor("blue")
    assert flipped.pixelColor(25, 75) == QColor("red")
    media.close()
    canvas.deleteLater()


def test_preview_rejects_invalid_corrections_and_unresolved_pixel_sizes():
    from cephvr.gui.trial_preview_surfaces import PreviewCorrection

    for axis in ("x", "y"):
        assert (
            "Assign a display"
            in PreviewCorrection.from_draft(
                "Front", {f"offset_{axis}_px": "1"}, None
            ).error
        )
        assert (
            "must fit"
            in PreviewCorrection.from_draft(
                "Front",
                {
                    "valid_width_px": "50",
                    "valid_height_px": "50",
                    f"offset_{axis}_px": "26",
                },
                (100, 100),
            ).error
        )
    assert (
        "Assign a display"
        in PreviewCorrection.from_draft("Front", {"valid_width_px": "10"}, None).error
    )
    assert (
        "whole pixels"
        in PreviewCorrection.from_draft(
            "Front", {"valid_width_px": "0"}, (1920, 1080)
        ).error
    )
    assert (
        "whole pixels"
        in PreviewCorrection.from_draft(
            "Front", {"valid_width_px": "1921"}, (1920, 1080)
        ).error
    )
    identity = PreviewCorrection.from_draft("Front", {}, None)
    assert not identity.error
    assert identity.corners == ((0, 0), (1, 0), (1, 1), (0, 1))


def test_random_variations_respect_bounds_precision_and_size():
    from decimal import Decimal
    from random import Random

    from cephvr.gui.batch_random import random_values

    values = random_values("-1.03", "2.04", "0.1", "100", Random(42).randrange)
    assert len(values) == 100
    assert len(set(values)) > 10
    assert all(Decimal("-1.03") <= Decimal(v) <= Decimal("2.04") for v in values)
    assert all(Decimal(v) % Decimal("0.1") == 0 for v in values)
    assert random_values("1", "1", "0.1", "3", Random(42).randrange) == ("1.0",) * 3
    for fields in (
        ("0", "1", "0", "100"),
        ("2", "1", "1", "100"),
        ("0", "1", "1", "2001"),
        ("0.01", "0.09", "1", "100"),
        ("nan", "1", "1", "100"),
        ("0", "1", "1e-99999", "100"),
    ):
        with pytest.raises(ValueError):
            random_values(*fields, Random(42).randrange)


def test_random_batch_values_stay_fixed_across_preview_and_save(window, app, tmp_path):
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.visual_stimulus.config.models.program_model import Program

    window.page_buttons[1].click()
    from cephvr.gui.batch_create import BatchCreate

    create = BatchCreate()
    create.setParent(window)
    from PyQt6.QtGui import QImage

    create.composer.set_screens(("Front",))
    create.composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    create.composer.add_file("Texture", str(path), "Front")
    create.add_variation()
    row = create.rows[0]
    row.random.seed(42)
    row.method.setCurrentText("Random")
    for key, value in {
        "minimum": "1",
        "maximum": "5",
        "precision": "0.1",
    }.items():
        row.random_fields[key].setText(value)
    assert set(row.random_fields) == {"minimum", "maximum", "precision"}
    create.repetitions.setText("100")
    first = create.candidate()
    assert len(first.sequence) == 100
    assert create.candidate() == first
    row.random_fields["precision"].setText("0.2")
    second = create.candidate()
    assert second != first
    assert len(second.sequence) == 100
    assert create.candidate() == second
    values = [
        motion_numbers(epoch.settings[0].model_dump(mode="json"))[0]
        for epoch in second.sequence
    ]
    assert all(1 <= value <= 5 for value in values)
    assert len(set(values)) > 10
    assert Program.model_validate_json(second.model_dump_json()) == second
    create.repetitions.setText("10")
    shorter = create.candidate()
    assert len(shorter.sequence) == 10
    assert create.candidate() == shorter
    create.repetitions.setText("999")
    assert len(create.candidate().sequence) == 999
    create.repetitions.setText("3")
    create.add_variation()
    fixed = create.rows[1]
    fixed.parameter.setCurrentIndex(fixed.parameter.findData("Direction"))
    fixed.values.setText("0, 90")
    mixed = create.candidate()
    assert len(mixed.sequence) == 6
    assert [
        motion_numbers(epoch.settings[0].model_dump(mode="json"))[1]
        for epoch in mixed.sequence
    ] == [0, 90, 0, 90, 0, 90]
    assert create.candidate() == mixed
    for width in (1350, 720):
        window.resize(width, 900)
        app.processEvents()
        assert window.protocol.config_scroll.horizontalScrollBar().maximum() == 0


def test_timeline_epoch_shortcuts_and_keyboard_history(window, app):
    window.page_buttons[1].click()
    editor = window.protocol.editor
    from cephvr.gui.protocol_batches import grouped_program

    editor.set_program(grouped_program(editor.program))
    editor.enter_group()
    original = editor.program
    editor.hierarchy.contents.setFocus()
    app.processEvents()
    QTest.keyClick(
        editor.hierarchy.contents, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier
    )
    duplicate = editor.program
    assert len(duplicate.sequence[0].body) == len(original.sequence[0].body) + 1
    editor.hierarchy.contents.setFocus()
    app.processEvents()
    QTest.keyClick(
        editor.hierarchy.contents, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
    )
    assert editor.program == original
    QTest.keyClick(
        editor.hierarchy.contents, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier
    )
    assert editor.program == duplicate
    QTest.keyClick(editor.hierarchy.contents, Qt.Key.Key_Backspace)
    assert len(editor.program.sequence[0].body) == len(original.sequence[0].body)
    assert not any(
        action.text() in {"Undo", "Redo"} for action in editor.epoch_menu.actions()
    )
    editor.hierarchy.contents.choose(0, Qt.KeyboardModifier.NoModifier)
    editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.ShiftModifier)
    before = editor.program
    QTest.keyClick(
        editor.hierarchy.contents, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier
    )
    QTest.keyClick(editor.hierarchy.contents, Qt.Key.Key_Backspace)
    assert editor.program == before
    text_field = editor.subgroup.composer.duration
    text_field.setText("123")
    text_field.setFocus()
    text_field.setCursorPosition(3)
    app.processEvents()
    before = editor.program
    QTest.keyClick(text_field, Qt.Key.Key_Backspace)
    assert text_field.text() == "12"
    assert editor.program == before
    editor.subgroup.discard()
    window.apply_view(review_view(Phase.RUNNING))
    for operation in ("duplicate", "remove"):
        editor.edit_epoch(operation)
    assert editor.program == before


def test_image_fit_and_motion_are_saved_without_texture_phase(window, app):
    from cephvr.gui.image_parameters import ImageParameters
    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = ParameterDocument(window)
    editor.set_program(blank_program())
    editor.add_stimulus("Image")
    editor.parameters.bind(editor.program, (0,), 0, "Left")
    parameters = editor.parameters
    image = next(form for form in parameters.forms if isinstance(form, ImageParameters))
    assert image.fit.currentText() == "Contain"
    image.fit.setCurrentText("Cover")
    image.motion.speed.setText("12")
    image.motion.direction.setText("90")
    image.motion.edited = True
    image.initial_x.setText("4")
    assert parameters.apply()
    restored = parse_program_json(editor.program.model_dump_json(), max_bytes=1_048_576)
    setting = restored.sequence[0].settings[parameters.layer_index]
    assert setting.kind == "image" and setting.fit == "cover"
    assert setting.initial.x == 4
    assert setting.motion.y.function.value == pytest.approx(12)
    assert "phase_x" not in setting.model_dump()


@pytest.mark.parametrize("preset", ["Video", "Looming image", "3D arena"])
@pytest.mark.parametrize("reset", [True, False])
def test_family_advanced_controls_preserve_hidden_state(window, app, preset, reset):
    from cephvr.gui.advanced_appearance import AdvancedAppearance
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus

    program = add_stimulus(blank_program(), 0, preset, ("Front",))
    epoch = program.sequence[0]
    imported = epoch.settings[0].model_copy(update={"reset": reset})
    program = program.model_copy(
        update={"sequence": (epoch.model_copy(update={"settings": (imported,)}),)}
    )
    editor = ParameterDocument(window)
    editor.set_program(program)
    parameters = editor.parameters
    parameters.more.setChecked(True)
    app.processEvents()
    appearance = parameters.advanced_card.findChild(AdvancedAppearance)
    if preset == "3D arena":
        from cephvr.gui.arena_movement import ArenaMovement

        assert appearance is None
        movement = next(
            form for form in parameters.forms if isinstance(form, ArenaMovement)
        )
        from cephvr.gui.stimulus_form import ValueEditor

        initial = next(
            form
            for form in parameters.forms
            if isinstance(form, ValueEditor)
            and "fixed_height_mm" in form.children_by_key
        )
        assert parameters.advanced_card.isAncestorOf(initial)
        initial.children_by_key["fixed_height_mm"].control.setText("12.5")
        initial.children_by_key["yaw_deg"].control.setText("45")
        movement.axes[0].setChecked(True)
        movement.gains[0].setText("0.5")
        movement.mark_edited()
    else:
        assert appearance is not None and appearance.link_field.isHidden()
        parameters.fades.fade_in.setText("1")
        parameters.fades.mark_changed()
    hidden = preset in ("Video", "3D arena")
    assert parameters.retain.isHidden() == hidden
    if hidden:
        parameters.retain.setChecked(reset)
    assert parameters.apply()
    assert editor.program.sequence[0].settings[0].reset == reset
    if preset == "3D arena":
        assert editor.program.sequence[0].settings[0].fixed_height_mm == 12.5
        assert editor.program.sequence[0].settings[0].initial.yaw_deg == 45
    if preset == "3D arena":
        real_editor = window.protocol.editor
        real_editor.set_program(program)
        open_protocol_group(real_editor)
        assert real_editor.subgroup.composer.rows[""].parameters.retain.isHidden()


def test_image_fit_preview_contains_crops_and_stretches(app):
    from PyQt6.QtGui import QColor, QImage, QPainter

    from cephvr.gui.trial_preview_canvas import fitted_image

    source = QImage(200, 100, QImage.Format.Format_RGB32)
    source.fill(QColor("red"))
    painter = QPainter(source)
    painter.fillRect(50, 0, 100, 100, QColor("blue"))
    painter.end()
    contained = fitted_image(source, "contain", 1, 1)
    assert contained.pixelColor(256, 10).alpha() == 0
    assert contained.pixelColor(10, 256).red() > 200
    assert contained.pixelColor(256, 256).blue() > 200
    covered = fitted_image(source, "cover", 1, 1)
    assert covered.pixelColor(10, 256).blue() > 200
    stretched = fitted_image(source, "stretch", 1, 1)
    assert stretched.pixelColor(5, 50).red() > 200


def test_batch_image_fit_preserves_legacy_default_and_rejects_invalid_values():
    import json

    from cephvr.gui.epoch_batch import patch_setting
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    program = add_stimulus(blank_program(), 0, "Image", ("Front",))
    data = program.model_dump(mode="json")
    setting = data["sequence"][0]["settings"][0]
    patch_setting(setting, {"Fit": "cover"})
    assert (
        parse_program_json(json.dumps(data), max_bytes=1_048_576)
        .sequence[0]
        .settings[0]
        .fit
        == "cover"
    )
    setting.pop("fit")
    assert (
        parse_program_json(json.dumps(data), max_bytes=1_048_576)
        .sequence[0]
        .settings[0]
        .fit
        == "stretch"
    )
    setting["fit"] = "invalid"
    with pytest.raises(ValueError):
        parse_program_json(json.dumps(data), max_bytes=1_048_576)


def test_selected_epoch_type_change_keeps_other_projector_and_sibling_epochs(window):
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_document import review_program

    editor = window.protocol.editor
    editor.set_program(review_program())
    editor.timeline.set_screens(("Left", "Right"))
    open_protocol_group(editor)
    editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
    original = editor.program
    form = editor.subgroup
    form.composer.change_type("Left", "None")
    form.apply()
    assert not form.notice.text()
    updated = editor.program
    node = node_at(updated, (0, 1))
    assert layers_for(updated, node, "Left") == []
    assert len(layers_for(updated, node, "Right")) == 1
    assert updated.sequence[0].body[0] == original.sequence[0].body[0]
    assert updated.sequence[0].body[2] == original.sequence[0].body[2]
    assert node.epoch_id == original.sequence[0].body[1].epoch_id


def test_managed_mcu_pending_completion_and_final_status(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_mcu import ManagedMcu

    panel = window.devices.microcontroller
    panel.managed = True
    panel.set_saved_pins("COM8", "D9", True, "D2", True)
    window.apply_view(
        DashboardView(connected=True, has_control=True, configuration_wired=False)
    )
    state = pb.Snapshot()
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    pulses = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition.pulses
    pulses.port, pulses.trial_state_pin = "COM8", "D9"
    pulses.trial_state_enabled = True
    sent: list[tuple[str, dict[str, object]]] = []
    binding = ManagedMcu(
        panel,
        SimpleNamespace(request=lambda action, **kw: sent.append((action, kw)) or True),
        lambda: state,
    )
    manager = SimpleNamespace(
        window=window,
        mcu=binding,
        action_progress=SimpleNamespace(finished=lambda *_: False),
        cameras=SimpleNamespace(finished=lambda *_: None),
    )
    binding.test_connection()
    binding.test_connection()
    assert len(sent) == 1 and panel.connection_pending
    assert not panel.test_buttons["trial-state"].isEnabled()
    binding.finished("mcu", True, "Connected")
    assert not panel.connection_pending
    binding.test_pin("trial-state", True)
    assert not binding.settle.isActive()
    diagnostic = state.microcontroller.diagnostic
    diagnostic.signal = pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE
    diagnostic.active = True
    diagnostic.rising_edges = 1
    diagnostic.observed_monotonic_ns = 100
    binding.install(state, True)
    ManagedGui.command_finished(manager, "mcu", True, "Started")
    assert binding.settle.isActive()
    assert binding.settle.interval() == 500
    assert panel.test_buttons["trial-state"].text() == "Stop"
    console_before = panel.console.toPlainText()
    log_before = window.dashboard.log_console.toPlainText()
    for observed in range(101, 108):
        binding.read_status()
        assert sent[-1][1]["kind"] == rpc.MICROCONTROLLER_COMMAND_KIND_STATUS
        diagnostic.observed_monotonic_ns = observed
        binding.install(state, True)
        ManagedGui.command_finished(manager, "mcu", True, "Completed")
        assert panel.console.toPlainText() == console_before
        assert window.dashboard.log_console.toPlainText() == log_before
        assert not binding.pending and binding.pending_kind == 0
    assert binding.settle.isActive()
    assert panel.test_buttons["trial-state"].text() == "Stop"
    binding.test_pin("trial-state", False)
    assert sent[-1][1]["kind"] == rpc.MICROCONTROLLER_COMMAND_KIND_STOP
    diagnostic.active = False
    diagnostic.observed_monotonic_ns = 5_000_000_200
    diagnostic.rising_edges = 10
    binding.install(state, True)
    ManagedGui.command_finished(manager, "mcu", True, "Stopped")
    assert not binding.settle.isActive()
    assert panel.test_buttons["trial-state"].text() == "Test"
    assert "output LOW, 10 rising transitions" in panel.status_column.hud.toPlainText()
    assert "MCU command: Stopped" not in panel.console.toPlainText()
    assert (
        sum(
            options["kind"] == rpc.MICROCONTROLLER_COMMAND_KIND_START
            for _, options in sent
        )
        == 1
    )
    diagnostic.signal = pb.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL
    diagnostic.active = True
    diagnostic.observed_monotonic_ns = 300
    binding.install(state, True)
    assert panel.test_buttons["behavioral"].text() == "Stop"
    console_before = panel.console.toPlainText()
    binding.read_status()
    diagnostic.rising_edges = 59
    diagnostic.observed_monotonic_ns = 301
    binding.install(state, True)
    ManagedGui.command_finished(manager, "mcu", True, "Completed")
    assert panel.console.toPlainText() == console_before
    assert "59 rising transitions" in panel.status_column.hud.toPlainText()
    binding.read_status()
    ManagedGui.command_finished(manager, "mcu", False, "Status unavailable")
    assert "MCU command failed: Status unavailable" in panel.console.toPlainText()
    assert (
        "MCU command failed: Status unavailable"
        in window.dashboard.log_console.toPlainText()
    )
    state.microcontroller.ClearField("diagnostic")
    state.microcontroller.ClearField("observation")
    binding.install(state, True)
    assert panel.test_buttons["trial-state"].text() == "Test"
    assert not binding.settle.isActive()
    assert "Not connected" in panel.status_column.hud.toPlainText()
    binding.disconnected()
    assert not panel.connection_pending and not binding.pending


@pytest.mark.asyncio
async def test_managed_camera_batch_checks_continue_after_failure_without_capture() -> (
    None
):
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.device_requests import test_camera_connections

    state = pb.Snapshot()
    entry = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    for camera, serial in (
        (entry.acquisition.behavioral, "A"),
        (entry.acquisition.tracking, "B"),
    ):
        camera.enabled = True
        camera.device.device_id = serial
    requests = []

    async def execute(method, request):
        requests.append((method, request))
        return SimpleNamespace(succeeded=request.camera == 2, failure="unavailable")

    success, message = await test_camera_connections(
        SimpleNamespace(
            snapshot=state,
            execute=execute,
            operator_command=lambda: rpc.OperatorCommand(),
        ),
        [(1, "A"), (2, "B")],
    )
    assert (
        not success
        and "A: unavailable" in message
        and "B: connection and identity verified" in message
    )
    assert len(requests) == 2
    assert all(
        request.kind == rpc.CAMERA_COMMAND_KIND_TEST_CONNECTION
        for _, request in requests
    )
    state.acquisition_devices.behavioral.preview_running = True
    requests.clear()
    await test_camera_connections(
        SimpleNamespace(
            snapshot=state,
            execute=execute,
            operator_command=lambda: rpc.OperatorCommand(),
        ),
        [(1, "A")],
    )
    assert not requests


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_managed_role_assignment_is_atomic_and_preserves_participation(
    enabled: bool,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.device_requests import assign_camera_role

    state = pb.Snapshot()
    state.configuration.revision = 7
    acquisition = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    acquisition.behavioral.enabled = True
    acquisition.behavioral.device.device_id = "A"
    acquisition.tracking.device.device_id = "old"
    acquisition.tracking.enabled = enabled
    requests = []

    async def execute(method, request):
        requests.append(request)
        return SimpleNamespace(succeeded=True)

    await assign_camera_role(
        SimpleNamespace(
            snapshot=state,
            execute=execute,
            operator_command=lambda: rpc.OperatorCommand(),
        ),
        {"serial": "A", "role": "Tracking cam"},
    )
    request = requests[0]
    assert request.expected_revision == 7
    updated = request.proposed.backends[0].acquisition
    assert updated.behavioral.device.device_id == "" and updated.behavioral.enabled
    assert (
        updated.tracking.device.device_id == "A" and updated.tracking.enabled is enabled
    )
    assert acquisition.behavioral.device.device_id == "A"


def test_managed_camera_projection_distinguishes_open_capture_and_cleanup(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_cameras import ManagedCameras
    from cephvr.gui.managed_preview_viewers import ManagedPreviewViewers

    panel = window.devices.cameras
    panel.managed = True
    state = pb.Snapshot()
    state.configuration.revision = 3
    entry = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    entry.acquisition.behavioral.device.device_id = panel.drafts[0].serial
    entry.acquisition.behavioral.enabled = True
    entry.acquisition.behavioral.device.frame_timing = 1
    calls = []
    binding = ManagedCameras(
        panel,
        SimpleNamespace(
            request=lambda action, **kw: calls.append((action, kw)) or True
        ),
        lambda *_: False,
    )
    view = state.acquisition_devices.behavioral
    view.device_open = True
    previews = binding.install(state)
    panel.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            configuration_wired=False,
            previews=previews,
        )
    )
    assert panel.connect_button.text() == "Disconnect selected"
    assert not panel.preset_field.isEnabled()
    panel.connect_button.click()
    assert calls[-1][1]["kind"] == rpc.CAMERA_COMMAND_KIND_FINISH_EDITING
    assert not panel.connect_button.isEnabled()
    binding.finished("camera", False, "still open")
    view.preview_running = True
    previews = binding.install(state)
    panel.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            configuration_wired=False,
            previews=previews,
        )
    )
    assert panel.connect_button.text() == "Disconnect selected"
    viewers = ManagedPreviewViewers(
        lambda: state,
        panel,
        lambda role, kind, **options: binding.queue(
            "camera", role=role, kind=kind, **options
        ),
        placement=lambda key: key.encode(),
    )
    viewers.preview_visibility(panel.drafts[0].key, True)
    count = len(calls)
    assert calls[-1][1]["kind"] == rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
    assert calls[-1][1]["placement"] == panel.drafts[0].key.encode()
    assert not panel.connect_button.isEnabled()
    viewers.preview_visibility(panel.drafts[0].key, True)
    panel.connect_button.click()
    assert len(calls) == count
    assert "Preview was not sent" in panel.console.toPlainText()
    binding.finished("camera", False, "viewer transfer rejected")
    assert "viewer transfer rejected" in panel.console.toPlainText()
    view.preview_run_id = str(uuid4())
    view.preview_visible = True
    view.preview_visibility_revision = 1
    assert viewers.viewer_state(1, True, view.preview_run_id)
    viewers.preview_visibility(panel.drafts[0].key, False)
    assert calls[-1][1]["kind"] == rpc.CAMERA_COMMAND_KIND_HIDE_PREVIEW
    assert "placement" not in calls[-1][1]
    assert view.preview_running
    binding.finished("camera", True, "window closed")
    view.preview_visible = False
    view.preview_visibility_revision = 2
    assert not viewers.viewer_state(1, True, view.preview_run_id)
    panel.connect_button.click()
    assert calls[-1][1]["kind"] == rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW
    binding.disconnected()


@pytest.mark.parametrize("holder", ["", "other-client", "this-gui"])
def test_managed_gui_auto_claims_only_unheld_control_once(holder: str) -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui

    requests = []
    state = pb.Snapshot()
    state.control.holder_client_id = holder
    manager = SimpleNamespace(
        control_ready=True,
        state=state,
        _retained_ack_required=False,
        auto_control_attempted=False,
        bridge=SimpleNamespace(request=lambda action: requests.append(action)),
    )
    ManagedGui.claim_unheld_control(manager)
    assert requests == (["take_control"] if not holder else [])
    # Manual release or another holder relinquishing does not cause automatic takeover.
    state.control.holder_client_id = ""
    ManagedGui.claim_unheld_control(manager)
    assert len(requests) == (1 if not holder else 0)


def test_managed_gui_waits_for_synchronization_and_warning_acknowledgement() -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui

    requests = []
    manager = SimpleNamespace(
        control_ready=False,
        state=pb.Snapshot(),
        _retained_ack_required=True,
        auto_control_attempted=False,
        bridge=SimpleNamespace(request=lambda action: requests.append(action)),
    )
    ManagedGui.claim_unheld_control(manager)
    assert not requests and not manager.auto_control_attempted
    manager.control_ready = True
    manager.state = None
    ManagedGui.claim_unheld_control(manager)
    assert not requests and not manager.auto_control_attempted
    manager.state = pb.Snapshot()
    ManagedGui.claim_unheld_control(manager)
    assert not requests
    manager._retained_ack_required = False
    ManagedGui.claim_unheld_control(manager)
    assert requests == ["take_control"]


def test_retained_acknowledgement_cannot_clear_guard_without_current_snapshot() -> None:
    from cephvr.gui.main import ManagedGui

    manager = SimpleNamespace(
        _retained_ack_required=True,
        state=None,
        _connection_identity=None,
        _retained_ack_identity=(4, "controller-1"),
    )
    ManagedGui.retained_state_acknowledged(manager, 4, "controller-1")
    assert manager._retained_ack_required


def test_initial_and_reopened_retained_warnings_gate_auto_claim() -> None:
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.main import ManagedGui

    class Action:
        def __init__(self) -> None:
            self.enabled = False

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

    requests: list[str] = []
    prompt_updates: list[tuple[bool, int]] = []

    def install_prompts(
        _state: pb.Snapshot,
        *,
        require_acknowledgement: bool,
        can_respond: bool,
        connection_epoch: int,
    ) -> None:
        assert not can_respond
        prompt_updates.append((require_acknowledgement, connection_epoch))

    manager = SimpleNamespace(
        _retained_ack_required=False,
        _retained_ack_identity=None,
        _acknowledged_identity=None,
        _awaiting_reconnect_review=False,
        _connection_epoch=1,
        _connection_identity=None,
        history=SimpleNamespace(restore_attempted=True),
        state=None,
        configuration=SimpleNamespace(
            install=lambda _state: True,
            installing_projection=nullcontext,
            stale=False,
            last_error="",
            _installing=False,
        ),
        bridge=SimpleNamespace(
            principal=SimpleNamespace(generation="gui-1"),
            request=lambda action: requests.append(action),
        ),
        cameras=SimpleNamespace(install=lambda _state: []),
        window=SimpleNamespace(
            devices=SimpleNamespace(sync_cameras=lambda: None),
            apply_view=lambda _view: None,
        ),
        display_operations=SimpleNamespace(
            install_calibration_state=lambda _state, *, launch_eligible: None,
            install_pairing=lambda: None,
        ),
        _calibration_launch_eligible=lambda _state: False,
        mcu=SimpleNamespace(install=lambda _state, _held: None),
        prompts=SimpleNamespace(update=install_prompts),
        tracking_diagnostics=SimpleNamespace(install_snapshot=lambda _state: None),
        action_progress=SimpleNamespace(install=lambda _epoch, _state: None),
        stimulus_preview=SimpleNamespace(pending=""),
        review_retained=Action(),
        take=Action(),
        takeover=Action(),
        release=Action(),
        review_prompt=Action(),
        reload_configuration=Action(),
        control_ready=True,
        auto_control_attempted=False,
    )
    manager.claim_unheld_control = lambda: ManagedGui.claim_unheld_control(manager)
    initial = pb.Snapshot(controller_generation="controller-1")
    initial.warnings.add(message="retained device warning")
    ManagedGui.install_snapshot(manager, 1, "controller-1", initial.SerializeToString())
    assert manager._retained_ack_required
    assert manager.review_retained.enabled
    assert prompt_updates[-1] == (True, 1)
    assert not requests

    # An authoritative update in the same connection cannot clear an open guard.
    same_identity = pb.Snapshot(controller_generation="controller-1")
    ManagedGui.install_snapshot(
        manager, 1, "controller-1", same_identity.SerializeToString()
    )
    assert manager._retained_ack_required
    assert manager._retained_ack_identity == (1, "controller-1")
    assert prompt_updates[-1] == (True, 1)
    assert manager.review_retained.enabled
    assert not requests

    manager.state = None
    manager._awaiting_reconnect_review = True
    manager._retained_ack_identity = (1, "controller-1")
    manager.auto_control_attempted = False
    reopened = pb.Snapshot(controller_generation="controller-1")
    reopened.operations.add(command="Setup", complete=True, succeeded=True)
    ManagedGui.install_snapshot(
        manager, 2, "controller-1", reopened.SerializeToString()
    )
    assert not manager._retained_ack_required
    assert manager._retained_ack_identity is None
    assert prompt_updates[-1] == (False, 2)
    assert manager.review_retained.enabled
    assert requests == ["take_control"]

    manager._retained_ack_required = True
    manager._retained_ack_identity = (5, "controller-1")
    manager.state = SimpleNamespace(controller_generation="controller-1")
    manager._connection_identity = (5, "controller-1")
    ManagedGui.retained_state_acknowledged(manager, 4, "controller-1")
    assert manager._retained_ack_required


def test_shared_notices_warn_on_action_and_send_status_to_log(window, app):
    from PyQt6.QtWidgets import QMessageBox

    from cephvr.gui.notices import FormNotice, passive_validation

    notice = FormNotice()
    window.protocol.program_card.body.addWidget(notice)
    notice.setText("Unfinished value")
    notice.show()
    assert notice.isHidden() and notice.dialog is None
    with passive_validation():
        notice.warn("Incomplete value")
    assert notice.dialog is None
    notice.warn("Choose a valid value")
    dialog = notice.dialog
    assert dialog is not None and dialog.icon() == QMessageBox.Icon.Warning
    assert dialog.text() == "Choose a valid value"
    notice.warn("Correct the value")
    assert notice.dialog is dialog and dialog.text() == "Correct the value"
    notice.clear()
    assert notice.dialog is None
    notice.status("Trial saved")
    assert "Trial saved" in window.dashboard.log_console.toPlainText()
    assert notice.isHidden() and not notice.text()
    notice.warn("Action failed")
    notice.setEnabled(False)
    assert notice.dialog is None


def test_tracking_methods_preserve_fields_and_hide_unrelated_controls(
    window: DashboardWindow, app: QApplication
) -> None:
    page = window.tracking
    window.select_page(3)
    assert page.pipeline.currentText() == "Water flow"
    assert page.forms.method.currentText() == "Manual"
    assert page.forms.flow_method.text() == "NVIDIA OF"
    assert page.forms.flow_method.isReadOnly()
    assert not page.forms.advanced_body.isHidden()
    calibration = page.forms.calibration.layout()
    assert calibration.indexOf(page.forms.reference) < calibration.indexOf(
        page.forms.distance_calibration
    )
    pose = page.forms.subject.layout()
    assert pose.indexOf(page.forms.search) < pose.indexOf(page.forms.pose)
    page.forms.fields["threshold"].setText("120")
    page.forms.method.setCurrentText("Manual")
    app.processEvents()
    assert page.forms.search.isHidden()
    assert not page.forms.method_pages[2].isHidden()
    page.forms.method.setCurrentText("Keypoint model")
    assert not page.forms.method_pages[1].isHidden()
    page.forms.method.setCurrentText("Threshold + contour")
    assert page.forms.fields["threshold"].text() == "120"
    assert not page.forms.search.isHidden()
    page.forms.fields["coverage"].setText("0.4")
    page.pipeline.setCurrentText("Fin flow")
    assert page.forms.fields["coverage"].text() == "0.25"
    assert not page.forms.fin.isHidden()
    page.forms.fields["fin_span"].setText("90")
    page.pipeline.setCurrentText("Water flow")
    assert page.forms.fields["coverage"].text() == "0.4"
    assert page.forms.fin.isHidden()
    page.pipeline.setCurrentText("Fin flow")
    assert page.forms.fields["fin_span"].text() == "90"
    page.tabs.setCurrentIndex(2)
    for width in (1280, 720):
        window.resize(width, 950)
        page.forms.method.setCurrentText("Manual")
        app.processEvents()
        manual = page.forms.method_pages[2]
        points = page.forms.manual_points
        assert manual.rect().contains(points.geometry())
        assert page.forms.pose_pages.rect().contains(manual.geometry())
        assert page.forms.set_manual.x() == points.x()
        assert all(toggle.text() == "Enable" for toggle in page.forms.stages.values())
        assert not any(
            button.text() == "Draw region" for button in page.findChildren(QPushButton)
        )
        page.forms.method.setCurrentText("Threshold + contour")


def test_tracking_draft_roundtrip_and_invalid_load_is_atomic(
    window: DashboardWindow,
) -> None:
    import copy

    page = window.tracking
    page.forms.fields["threshold"].setText("123")
    page.annotation.image_size = [640, 480]
    page.annotation.canvas.points["Reference points"] = [[100, 200]]
    draft = page.snapshot()
    page.forms.fields["threshold"].setText("80")
    page.restore(draft)
    assert page.snapshot() == draft
    invalid = copy.deepcopy(draft)
    invalid["annotations"]["Reference points"] = [[900, 20]]
    with pytest.raises(ValueError, match="outside"):
        page.restore(invalid)
    assert page.snapshot() == draft


def test_tracking_camera_changes_invalidate_reference_and_lock_closes_tool(
    window: DashboardWindow, app: QApplication
) -> None:
    page = window.tracking
    cameras = window.devices.cameras
    cameras.set_participation(0, True)
    assert page.source_serial == cameras.drafts[1].serial
    page.annotation.image_size = [640, 480]
    page.annotation.canvas.points["Reference points"] = [[20, 30]]
    cameras.drafts[1].role = "Unassigned"
    cameras.drafts[0].role = "Tracking cam"
    cameras.drafts_changed.emit()
    assert page.source_serial == cameras.drafts[0].serial
    assert page.annotation.canvas.points["Reference points"] == []
    page.open_annotation("Manual pose")
    assert page.annotation.isVisible()
    page.apply_view(review_view(Phase.RUNNING))
    assert not page.annotation.isVisible()
    assert not page.configuration.isEnabled()
    page.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            configuration_wired=False,
        )
    )
    assert not page.configuration.isEnabled()
    app.processEvents()


def test_tracking_annotation_maps_letterboxed_image_to_source_pixels(
    app: QApplication,
) -> None:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QImage

    from cephvr.gui.tracking_annotation import AnnotationCanvas

    canvas = AnnotationCanvas()
    canvas.resize(800, 400)
    canvas.image = QImage(200, 200, QImage.Format.Format_RGB32)
    assert canvas.coordinate(QPointF(10, 200)) is None
    point = canvas.coordinate(canvas.image_rect().center())
    assert point == QPointF(100, 100)
    canvas.show()
    QTest.mouseClick(
        canvas, Qt.MouseButton.LeftButton, pos=canvas.image_rect().center().toPoint()
    )
    assert canvas.points["Reference points"] == [[100.0, 100.0]]
    canvas.close()


def test_tracking_distance_and_regions_use_original_pixels(
    window: DashboardWindow,
) -> None:
    page = window.tracking
    page.annotation.image_size = [640, 480]
    distance = page.forms.distance_calibration
    assert distance.summary.isHidden()
    for editor, value in zip(distance.coordinates, (10, 20, 310, 420), strict=True):
        editor.setText(str(value))
    distance.distance.setText("10")
    page.distance_edited()
    assert not distance.summary.isHidden()
    assert distance.summary.text() == "50 px/mm   ·   0.02 mm/px"
    crop = page.forms.preprocessing
    crop.enabled.setChecked(True)
    crop.region.set_values([10, 20, 400, 200])
    page.region_edited("Input crop")
    crop.scale.setValue(50)
    assert crop.scale.value() == 50
    assert distance.summary.text() == "50 px/mm   ·   0.02 mm/px"
    assert page.annotation.canvas.points["Input crop"] == [[10, 20], [410, 220]]
    page.annotation.canvas.points["Search region"] = [[50, 60], [250, 160]]
    page.update_annotations()
    assert page.forms.search_region.values() == [50, 60, 200, 100]
    draft = page.snapshot()
    page.restore(draft)
    assert page.snapshot() == draft
    assert distance.summary.text() == "50 px/mm   ·   0.02 mm/px"


def test_tracking_v1_draft_migrates_without_inventing_calibration(
    window: DashboardWindow,
) -> None:
    page = window.tracking
    draft = page.snapshot()
    draft["version"] = 1
    draft.pop("diagnostics")
    draft.pop("preprocessing")
    draft.pop("distance_mm")
    draft["annotations"].pop("Input crop")
    draft["annotations"].pop("Distance reference")
    page.restore(draft)
    assert page.snapshot()["version"] == 4
    assert all(page.snapshot()["diagnostics"].values())
    assert not page.forms.preprocessing.enabled.isChecked()
    assert page.forms.preprocessing.scale.value() == 100
    assert page.forms.distance_calibration.distance.text() == ""


def test_tracking_preview_stages_retain_settings_and_clear_only_subject_reference(
    window: DashboardWindow, app: QApplication
) -> None:
    import copy

    page = window.tracking
    window.page_buttons[3].click()
    page.annotation.image_size = [640, 480]
    page.annotation.canvas.points["Reference points"] = [[20, 30]]
    page.annotation.canvas.points["Manual pose"] = [[40, 50]]
    page.annotation.canvas.points["Distance reference"] = [[0, 0], [100, 0]]
    page.forms.distance_calibration.distance.setText("10")
    page.update_annotations()
    page.forms.clear_reference.click()
    assert page.annotation.canvas.points["Reference points"] == []
    assert page.forms.reference_points.points() == []
    assert page.annotation.canvas.points["Manual pose"] == [[40, 50]]
    assert page.forms.distance_calibration.summary.text() == "10 px/mm   ·   0.1 mm/px"
    page.forms.fields["coverage"].setText("0.42")
    page.forms.preprocessing.scale.setValue(50)
    page.open_annotation("Manual pose")
    # Stage switches start off for first-use diagnostics; toggle one on so this
    # assertion exercises the changed-draft path rather than a no-op setChecked.
    next(iter(page.forms.stages.values())).setChecked(True)
    for toggle in page.forms.stages.values():
        toggle.setChecked(False)
    assert not page.annotation.isVisible()
    assert not page.forms.fields["coverage"].isEnabled()
    assert page.forms.preprocessing.scale.isEnabled()
    draft = page.snapshot()
    invalid = copy.deepcopy(draft)
    invalid["diagnostics"]["pose"] = "false"
    with pytest.raises(ValueError, match="diagnostic"):
        page.restore(invalid)
    assert page.snapshot() == draft
    for toggle in page.forms.stages.values():
        toggle.setChecked(True)
    page.restore(draft)
    assert not any(page.snapshot()["diagnostics"].values())
    page.apply_view(review_view(Phase.RUNNING))
    assert all(not toggle.isEnabled() for toggle in page.forms.stages.values())
    page.apply_view(review_view(Phase.CONFIGURATION))
    for toggle in page.forms.stages.values():
        toggle.setChecked(True)
    assert page.forms.fields["coverage"].text() == "0.42"
    assert page.forms.fields["coverage"].isEnabled()
    assert page.forms.preprocessing.scale.value() == 50
    old = page.snapshot()
    old["version"] = 2
    old.pop("diagnostics")
    page.restore(old)
    assert all(page.snapshot()["diagnostics"].values())
    old = page.snapshot()
    old["version"] = 3
    old["diagnostics"]["preprocessing"] = False
    old["diagnostics"]["pose"] = False
    page.restore(old)
    assert "preprocessing" not in page.snapshot()["diagnostics"]
    assert not page.forms.pose.enabled.isChecked()
    assert page.forms.preprocessing.scale.value() == 50
    assert page.forms.preprocessing.scale.isEnabled()


def test_tracking_region_bounds_and_full_frame_are_validated(
    window: DashboardWindow,
) -> None:
    import copy

    page = window.tracking
    page.annotation.image_size = [640, 480]
    page.forms.preprocessing.region.set_values([0, 0, 640, 480])
    page.region_edited("Input crop")
    draft = page.snapshot()
    page.restore(draft)
    assert page.forms.preprocessing.region.values() == [0, 0, 640, 480]
    invalid = copy.deepcopy(draft)
    invalid["annotations"]["Input crop"][1][0] = 641
    with pytest.raises(ValueError, match="outside"):
        page.restore(invalid)
    assert page.snapshot() == draft


@pytest.mark.parametrize(
    "mode", ["Reference points", "Manual pose", "Distance reference"]
)
def test_tracking_coordinate_corrections_sync_annotations_and_preserve_incomplete_edits(
    window: DashboardWindow, mode: str
) -> None:
    page = window.tracking
    page.annotation.image_size = [640, 480]
    editor = {
        "Reference points": page.forms.reference_points,
        "Manual pose": page.forms.manual_points,
        "Distance reference": page.forms.distance_calibration.point_editor,
    }[mode]
    points = [[20.0 + i * 10, 30.0] for i in range(len(editor.coordinates) // 2)]
    page.annotation.canvas.points[mode] = points
    page.update_annotations()
    assert editor.points() == points
    editor.coordinates[0].setText("22.5")
    editor.coordinates[0].editingFinished.emit()
    expected = [[22.5, 30.0], *points[1:]]
    assert page.annotation.canvas.points[mode] == expected
    editor.coordinates[1].clear()
    editor.coordinates[1].editingFinished.emit()
    assert page.annotation.canvas.points[mode] == expected
    editor.coordinates[1].setText("35.25")
    editor.coordinates[1].editingFinished.emit()
    expected[0][1] = 35.25
    assert page.annotation.canvas.points[mode] == expected
    draft = page.snapshot()
    page.restore(draft)
    assert editor.points() == expected
    # Drawing and clearing remain reflected in the numeric rows.
    page.annotation.canvas.points[mode] = [[50, 60]]
    page.update_annotations()
    assert editor.points() == [[50, 60]]
    page.annotation.reset()
    assert all(not coordinate.text() for coordinate in editor.coordinates)


@pytest.mark.parametrize("with_crop", [False, True])
def test_older_tracking_crop_fields_migrate_without_losing_annotations(
    window: DashboardWindow, with_crop: bool
) -> None:
    import copy

    page = window.tracking
    page.annotation.image_size = [640, 480]
    page.annotation.canvas.points["Search region"] = [[10, 20], [110, 220]]
    if with_crop:
        page.annotation.canvas.points["Input crop"] = [[20, 30], [120, 230]]
    page.update_annotations()
    original = page.snapshot()
    older = copy.deepcopy(original)
    older["preprocessing"].pop("region")
    older.pop("annotation_source")
    page.restore(older)
    assert page.snapshot() == original
    assert "region" not in older["preprocessing"]  # Loading leaves source data intact.
    invalid = copy.deepcopy(older)
    invalid["annotations"]["Search region"] = [[110, 20], [10, 220]]
    with pytest.raises(ValueError, match="region requires"):
        page.restore(invalid)
    assert page.snapshot() == original


@pytest.mark.parametrize("width", [1280, 720])
@pytest.mark.parametrize("runtime_authority", [False, True])
def test_review_and_runtime_share_page_elements_and_card_layouts(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    runtime_authority: bool,
) -> None:
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QAbstractButton, QComboBox, QLineEdit

    from cephvr.gui.cameras import CamerasPanel
    from cephvr.gui.components import Card
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.gui.main import ManagedGui
    from cephvr.gui.managed_window import ManagedDashboardWindow
    from cephvr.gui.microcontroller import MicrocontrollerPanel
    from cephvr.gui.projectors import ProjectorsPanel
    from cephvr.gui.review import ReviewDashboardWindow
    from cephvr.shared.auth import Principal

    # Exercise both real composition paths, without SDK discovery or controller work.
    monkeypatch.setattr(CamerasPanel, "refresh_inventory", lambda self: None)
    monkeypatch.setattr(MicrocontrollerPanel, "scan_ports", lambda self: None)
    discover_displays = ProjectorsPanel.discover_displays
    monkeypatch.setattr(
        ProjectorsPanel,
        "discover_displays",
        lambda self: (
            discover_displays(self) if self.review_displays is not None else None
        ),
    )
    monkeypatch.setattr(ControllerBridge, "start", lambda self: None)
    review = ReviewDashboardWindow(
        sample=True,
        device_review=False,
        settings=QSettings(str(tmp_path / "review.ini"), QSettings.Format.IniFormat),
    )
    runtime = ManagedDashboardWindow(
        sample=False,
        settings=QSettings(str(tmp_path / "runtime.ini"), QSettings.Format.IniFormat),
    )
    controls = ReviewControls(review, simulate_projectors=True)
    bridge = ControllerBridge(
        Principal("gui", str(uuid4()), "test-token"), 50051, 1024, (0,)
    )
    manager = ManagedGui(
        runtime, bridge, gui_history_path=tmp_path / "runtime_gui.json"
    )
    for status in ("completed", "failed", "rejected", "unconfirmed"):
        manager.stimulus_preview.pending = True
        bridge.operation_finished.emit("set_stimulus_preview", "preview", status, "")
        assert not manager.stimulus_preview.pending
    from cephvr.control.v1 import types_pb2 as pb

    refreshes = []
    manager.state = pb.Snapshot(controller_generation="test-controller")
    with monkeypatch.context() as patch:
        patch.setattr(manager, "install_snapshot", lambda *args: refreshes.append(args))
        manager.stimulus_preview.pending = True
        bridge.operation_finished.emit(
            "set_stimulus_preview", "preview", "completed", ""
        )
    assert not manager.stimulus_preview.pending and len(refreshes) == 1
    manager.state = None
    runtime.devices.cameras.drafts = [
        replace(camera, values=dict(camera.values))
        for camera in review.devices.cameras.drafts
    ]
    runtime.devices.cameras.drafts_changed.emit()
    runtime.apply_view(replace(review.dashboard.view, sample=False, connected=True))
    projectors = runtime.devices.projectors
    projectors.review_displays = review.devices.projectors.review_displays
    projectors.assignments.update(review.devices.projectors.assignments)
    projectors.request("Refresh displays")
    for panel in (review.devices.projectors, projectors):
        for key in panel.keys:
            panel.set_participation(key, True)

    def signature(page: QWidget) -> tuple:
        return (
            tuple(card.caption.text() for card in page.findChildren(Card)),
            tuple(control.text() for control in page.findChildren(QAbstractButton)),
            tuple(editor.placeholderText() for editor in page.findChildren(QLineEdit)),
            tuple(
                tuple(editor.itemText(i) for i in range(editor.count()))
                for editor in page.findChildren(QComboBox)
            ),
        )

    def editor_geometry(parent: QWidget) -> list:
        return sorted(
            (
                (
                    type(control).__name__,
                    control.accessibleName(),
                    control.text()
                    if isinstance(control, (QLabel, QLineEdit, QAbstractButton))
                    else control.currentText(),
                    control.mapTo(parent, QPoint()),
                    control.size(),
                )
                for control in parent.findChildren(QWidget)
                if isinstance(control, (QLabel, QLineEdit, QComboBox, QAbstractButton))
                and control.isVisible()
            ),
            key=repr,
        )

    def control_gates(parent: QWidget) -> list:
        return sorted(
            (
                type(control).__name__,
                control.accessibleName(),
                control.text()
                if isinstance(control, (QAbstractButton, QLineEdit))
                else control.currentText(),
                control.isEnabled(),
            )
            for control in parent.findChildren((QAbstractButton, QLineEdit, QComboBox))
        )

    try:
        runtime.devices.cameras.populate_inventory()
        runtime.devices.cameras.load_selected()
        runtime.devices.sync_cameras()
        runtime.snapshots.restore(
            runtime.snapshots.validate(review.snapshots.capture())
        )
        runtime.devices.cameras.table.selectRow(
            review.devices.cameras.table.currentRow()
        )
        runtime.devices.cameras.load_selected()
        runtime.apply_view(
            replace(review.dashboard.view, sample=False, connected=True)
            if runtime_authority
            else review.dashboard.view
        )
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for window in (review, runtime):
            window.resize(width, 940)
            window.update_preview_timeline()
            window.show()
        assert [b.text() for b in review.page_buttons] == [
            b.text() for b in runtime.page_buttons
        ]
        for review_items, runtime_items in zip(
            signature(review.centralWidget()),
            signature(runtime.centralWidget()),
            strict=True,
        ):
            assert len(review_items) == len(runtime_items)
            assert [
                (left, right)
                for left, right in zip(review_items, runtime_items, strict=True)
                if left != right
            ] == []
        selections = [(0, None, None), (1, None, None)]
        selections += [(3, None, i) for i in range(review.tracking.tabs.count())]
        selections += [(2, i, None) for i in range(4)]
        selections += [
            (2, 2, i) for i in range(review.devices.projectors.setup_tabs.count())
        ]
        for page, subtab, inner_tab in selections:
            for window in (review, runtime):
                window.select_page(page)
                if subtab is not None:
                    window.devices.tabs.setCurrentIndex(subtab)
                if inner_tab is not None:
                    tabs = (
                        window.tracking.tabs
                        if page == 3
                        else window.devices.projectors.setup_tabs
                    )
                    tabs.setCurrentIndex(inner_tab)
            for _ in range(4):
                app.processEvents()
            assert review.page_header.geometry() == runtime.page_header.geometry()
            review_page, runtime_page = (
                review.stack.currentWidget(),
                runtime.stack.currentWidget(),
            )
            assert signature(review_page) == signature(runtime_page)

            def visible_cards(parent: QWidget) -> list:
                return [
                    (
                        card.caption.text(),
                        card.geometry(),
                    )
                    for card in parent.findChildren(Card)
                    if card.isVisible()
                ]

            assert visible_cards(review_page) == visible_cards(runtime_page)
            assert editor_geometry(review_page) == editor_geometry(runtime_page), (
                page,
                subtab,
                inner_tab,
            )
        # Authoring gates match; hardware actions retain their transport prerequisites.
        for phase in Phase:
            for observer in (False, True):
                view = review_view(phase, observer=observer)
                review.apply_view(view)
                runtime.apply_view(replace(view, sample=False, connected=True))
                for left, right in (
                    (review.dashboard, runtime.dashboard),
                    (review.protocol, runtime.protocol),
                    (review.tracking, runtime.tracking),
                ):
                    assert control_gates(left) == control_gates(right), (
                        phase,
                        observer,
                    )
                assert (
                    review.dashboard.stop_choices() == runtime.dashboard.stop_choices()
                )
        review.apply_view(review_view(Phase.CONFIGURATION))
        runtime.apply_view(replace(review.dashboard.view, sample=False, connected=True))
        # Family-specific fields are created on selection, including initial pose
        # and arena limits. Compare their placement with Advanced settings open.
        from cephvr.gui.protocol_batches import grouped_program
        from cephvr.gui.protocol_document import blank_program
        from cephvr.gui.stimulus_presets import add_stimulus

        for preset in ("Texture", "Image", "Video", "Looming image", "3D arena"):
            program = grouped_program(
                add_stimulus(
                    blank_program(), 0, preset, ("Front", "Left", "Right", "Bottom")
                )
            )
            for window in (review, runtime):
                window.select_page(1)
                window.protocol.editor.set_program(program)
                for row in window.protocol.editor.subgroup.composer.rows.values():
                    row.parameters.more.setChecked(True)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            for _ in range(4):
                app.processEvents()
            assert signature(review.protocol) == signature(runtime.protocol), preset
            assert editor_geometry(review.protocol.editor) == editor_geometry(
                runtime.protocol.editor
            ), preset
        # Authority stays in the Runtime menu without changing any page geometry.
        requests = []
        monkeypatch.setattr(
            bridge,
            "request",
            lambda action, **options: requests.append((action, options)),
        )
        for action in (manager.take, manager.release, manager.takeover):
            action.setEnabled(True)
        manager.take.trigger()
        manager.release.trigger()
        from PyQt6.QtWidgets import QMessageBox

        for answer in (QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes):
            monkeypatch.setattr(
                QMessageBox, "question", lambda *args, response=answer: response
            )
            manager.takeover.trigger()
        assert requests == [
            ("take_control", {}),
            ("release_control", {}),
            ("take_control", {"takeover": True}),
        ]
    finally:
        # Avoid persistence/controller shutdown dialogs in this isolated layout check.
        review.tracking.annotation.close()
        runtime.tracking.annotation.close()
        review.hide()
        runtime.hide()
        review.deleteLater()
        runtime.deleteLater()
        app.processEvents()
        assert not bridge.isRunning()
        assert controls.window is review and manager.window is runtime


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "start_ok,show_ok", [(True, True), (False, True), (True, False)]
)
async def test_camera_connect_opens_only_the_confirmed_run(start_ok, show_ok):
    from cephvr.client.session import ClientError
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_device_commands import _camera

    state = pb.Snapshot()
    state.configuration.revision = 9
    requests = []
    placement = rpc.PreviewWindowPlacement(x=1440, y=0, side=480)
    run = str(uuid4())

    async def execute(method, request):
        requests.append(request)
        if request.kind == rpc.CAMERA_COMMAND_KIND_START_PREVIEW:
            state.acquisition_devices.behavioral.preview_running = start_ok
            state.acquisition_devices.behavioral.preview_run_id = (
                run if start_ok else ""
            )
            return SimpleNamespace(succeeded=start_ok, failure="capture rejected")
        assert request.kind == rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW
        assert request.preview_run_id == run and request.preview_placement == placement
        assert request.expected_configuration_revision == 9
        return SimpleNamespace(succeeded=show_ok, failure="viewer rejected")

    client = SimpleNamespace(
        snapshot=state, execute=execute, operator_command=lambda: rpc.OperatorCommand()
    )
    options = {
        "kind": rpc.CAMERA_COMMAND_KIND_START_PREVIEW,
        "role": 1,
        "show_preview": True,
        "placement": placement.SerializeToString(),
    }
    if start_ok and show_ok:
        await _camera(client, options)
    else:
        with pytest.raises(
            ClientError,
            match="capture rejected"
            if not start_ok
            else "Capture started; preview could not open",
        ):
            await _camera(client, options)
    assert len(requests) == (2 if start_ok else 1)
    assert state.acquisition_devices.behavioral.preview_running == start_ok


def test_camera_selection_restores_pfs_source_and_frequency(window, tmp_path):
    panel = window.devices.cameras
    first, second = panel.drafts
    first.values.update(
        preset=str(tmp_path / "one.pfs"),
        trigger_clock="External controller",
        trigger_source="Line3",
        trigger_frequency_hz="30",
    )
    second.values.update(
        preset=str(tmp_path / "two.pfs"),
        trigger_clock="Internal clock",
        trigger_frequency_hz="60",
    )
    for row, draft in ((1, second), (0, first), (1, second)):
        panel.table.selectRow(row)
        assert panel.preset_field.editor.text() == draft.values["preset"]
        assert panel.preset_field.editor.toolTip() == draft.values["preset"]
        assert panel.preset_field.editor.filename_only
        assert panel.preset_field.editor.isReadOnly()
        assert panel.trigger_source.currentText() == draft.values["trigger_clock"]
        assert (
            panel.fields["trigger_frequency_hz"].text()
            == draft.values["trigger_frequency_hz"]
        )
    assert first.values["trigger_source"] == "Line3"


@pytest.mark.parametrize("selected_row", (0, 1))
def test_managed_camera_inventory_restores_selected_configuration(
    window, tmp_path, selected_row
):
    from cephvr.acquisition.v1 import camera_pb2 as camera
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.camera_inventory import CameraDraft
    from cephvr.gui.managed_cameras import ManagedCameras

    panel = window.devices.cameras
    panel.managed = True
    serials = [draft.serial for draft in panel.drafts]
    panel.drafts = []
    panel.populate_inventory()
    assert "CAMERAS FOUND     0" in panel.status_column.hud.toPlainText()
    requests = []
    binding = ManagedCameras(
        panel,
        SimpleNamespace(
            request=lambda action, **options: requests.append((action, options)) or True
        ),
        lambda *_: False,
    )
    state = pb.Snapshot()
    state.configuration.revision = 7
    entry = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    settings = entry.acquisition
    for index, role in enumerate(("behavioral", "tracking")):
        device = getattr(settings, role).device
        device.device_id = serials[index]
        device.frame_timing = (
            camera.FRAME_TIMING_EXTERNAL_TRIGGER
            if index == 0
            else camera.FRAME_TIMING_FREE_RUNNING
        )
        device.pfs_source_filename = str(tmp_path / f"{role}.pfs")
        if index == 0:
            device.settings.trigger_source = "Line2"
        getattr(settings.pulses, role).requested_frequency_hz = 30 * (index + 1)
    binding.install(state)

    panel.drafts = [
        CameraDraft(f"camera-{serial}", "Unassigned", serial, "Basler", enabled=False)
        for serial in serials
    ]
    panel.populate_inventory()
    panel.table.selectRow(selected_row)
    window.recordings.sync_cameras()
    recording_choices = {
        key: control.isChecked() for key, control in window.recordings.record.items()
    }
    recording_touched = set(window.recordings.touched)
    recording_edits = []
    window.recordings.changed.connect(lambda: recording_edits.append(True))
    binding.install(state)  # Inventory changed; controller revision did not.
    window.apply_view(DashboardView(connected=True, has_control=True))
    for draft in panel.drafts:
        assert (
            window.recordings.source_labels[draft.key].text()
            == f"Save {draft.role} video"
        )
        assert (
            window.recordings.record[draft.key].accessibleName()
            == f"Save {draft.role} video"
        )
    assert {
        key: control.isChecked() for key, control in window.recordings.record.items()
    } == recording_choices
    assert window.recordings.touched == recording_touched
    assert not recording_edits
    for row in (selected_row, 1 - selected_row, selected_row):
        panel.table.selectRow(row)
        draft = panel.drafts[row]
        assert panel.selected is draft
        assert panel.role.currentText() == draft.role
        assert panel.preset.text() == draft.values["preset"]
        assert panel.preset.toolTip() == draft.values["preset"]
        assert panel.trigger_source.currentText() == draft.values["trigger_clock"]
        assert panel.fields["trigger_frequency_hz"].text() == str(30 * (row + 1))
        hud = panel.status_column.hud.toPlainText()
        assert hud.splitlines()[:2] == ["CAMERAS FOUND     2", "CAMERAS ENABLED   0"]
        assert "\n\n" in hud
        details = dict(
            line.split("  ", 1) for line in hud.split("\n\n")[1].splitlines()
        )
        details = {key.strip(): value.strip() for key, value in details.items()}
        assert details == {
            "CAMERA ROLE": draft.role,
            "STATUS": "Not connected",
            "TRIGGER SOURCE": "External controller" if row == 0 else "Internal clock",
            "TRIGGER RATE": "30 Hz" if row == 0 else "—",
            "ACQUISITION RATE": "—",
        }
    assert list(details).index("TRIGGER SOURCE") < list(details).index("TRIGGER RATE")
    panel.edit("trigger_frequency_hz", "45")
    binding.install(state)
    assert panel.selected.values["trigger_frequency_hz"] == "45"
    panel.table.selectRow(0)
    panel.refresh_controls()
    assert "30 Hz" in panel.status_column.hud.toPlainText()
    assert "45 Hz" not in panel.status_column.hud.toPlainText()
    binding.disconnected()
    panel.refresh_controls()
    assert "30 Hz" not in panel.status_column.hud.toPlainText()
    assert (
        dict(row for row in panel.status_column.rows if row is not None)[
            "TRIGGER SOURCE"
        ]
        == "—"
    )
    panel.drafts[0].enabled = True
    panel.drafts[0].connected = True
    panel.refresh_controls()
    hud = panel.status_column.hud.toPlainText()
    assert "CAMERAS ENABLED   1" in hud
    assert "STATUS            Connected" in hud
    assert not requests


@pytest.mark.parametrize("raster_size", [None, (720, 1280), (1280, 720), (320, 180)])
def test_calibration_guides_keep_world_phase_with_solid_lines_and_one_name(raster_size):
    from cephvr.gui.calibration_guides import GRID, WHITE, add_face_guides

    class Mesh:
        def __init__(self):
            self.lines = []
            self.quads = []

        def line(self, start, end, width, normal, color):
            self.lines.append((start, end, width, color))

        def quad(self, corners, color):
            self.quads.append((corners, color))

    for face in ("Front", "Left", "Right", "Bottom"):
        for sign, origin in ((1, (23.0, 0.0, 0.0)), (-1, (203.0, 0.0, 0.0))):
            mesh = Mesh()

            def at(x, y, z, origin=origin, sign=sign):
                return origin[0] + sign * x, y, z

            add_face_guides(
                mesh,
                face,
                at,
                origin,
                (sign, 0, 0),
                (0, 1, 0),
                (0, 0, sign),
                180,
                130,
                10,
                raster_size=raster_size,
            )
            grid = [line for line in mesh.lines if line[3] == GRID]
            vertical = [line for line in grid if line[0][0] == line[1][0]]
            horizontal = [line for line in grid if line[0][1] == line[1][1]]
            assert len(vertical) == 18 and len(horizontal) == 12
            assert all(start[0] % 10 == 0 for start, end, width, color in vertical)
            assert all(start[1] == 0 and end[1] == 130 for start, end, _, _ in vertical)
            assert all(abs(end[0] - start[0]) == 180 for start, end, _, _ in horizontal)
            for lines, extent, pixels in (
                (vertical, 180, None if raster_size is None else raster_size[0]),
                (horizontal, 130, None if raster_size is None else raster_size[1]),
            ):
                expected = 0.2 if pixels is None else max(0.2, 2 * extent / pixels)
                assert all(width == expected for _, _, width, _ in lines)
                if pixels is not None:
                    # Even the worst subpixel phase covers native sample centers.
                    pixel_width = expected * pixels / extent
                    assert pixel_width >= 2
                    for phase in (0, 0.25, 0.5, 0.75):
                        assert any(
                            abs(sample + 0.5 - phase) < pixel_width / 2
                            for sample in range(-2, 3)
                        )
            assert len([line for line in mesh.lines if line[3] == WHITE]) == 4
            assert len(mesh.lines) == len(grid) + 4
            backgrounds = [quad for quad in mesh.quads if quad[1] == (0, 0, 0, 1)]
            assert len(backgrounds) == 1  # Only the screen name; no dimensions/ruler.
            assert all(
                color == WHITE for _, color in mesh.quads if color != (0, 0, 0, 1)
            )


@pytest.mark.parametrize("suffix", ["hex", "ino"])
def test_managed_firmware_controls_require_idle_configuration(window, tmp_path, suffix):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_mcu import ManagedMcu

    panel = window.devices.microcontroller
    panel.managed = True
    state = pb.Snapshot()
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition.pulses.port = "COM8"
    state.configuration.revision = 1
    calls = []
    binding = ManagedMcu(
        panel,
        SimpleNamespace(
            request=lambda action, **kw: calls.append((action, kw)) or True
        ),
        lambda: state,
    )
    panel.apply_view(DashboardView(connected=True, has_control=True))
    binding.install(state, True)
    panel.firmware.editor.setText(str(tmp_path / f"uno.{suffix}"))
    assert panel.upload.isEnabled()
    state.microcontroller.diagnostic.active = True
    binding.install(state, True)
    assert not panel.upload.isEnabled()
    state.microcontroller.diagnostic.active = False
    state.microcontroller.failure = "MCU firmware does not support CAPS"
    binding.install(state, True)
    assert panel.upload.isEnabled()
    assert panel.firmware.browse.isEnabled()
    for view, attribute in (
        (state.microcontroller, "cleanup_pending"),
        (state.acquisition_devices.behavioral, "preview_running"),
        (state.acquisition_devices.tracking, "device_open"),
        (state.acquisition_devices.eye_tracking, "cleanup_pending"),
    ):
        setattr(view, attribute, True)
        binding.install(state, True)
        assert not panel.upload.isEnabled()
        setattr(view, attribute, False)
    panel.apply_view(DashboardView(connected=True, has_control=True))
    binding.install(state, True)
    panel.upload.click()
    assert calls == [("mcu_upload", {"path": str(tmp_path / f"uno.{suffix}")})]
    assert panel.upload.text() == "Uploading…" and not panel.port.isEnabled()
    binding.finished("mcu_upload", False, "verification failed")
    assert panel.upload.text() == "Upload" and panel.upload.isEnabled()
    binding.install(state, False)
    assert not panel.upload.isEnabled()


def test_projector_configuration_json_restores_all_settings_without_screen_mapping(
    window: DashboardWindow, tmp_path: Path
):
    import json

    from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_pb

    panel = window.devices.projectors
    assert panel.calibration_files.load_button.text() == "Load…"
    panel.assignments = {"current-left": "Left", "current-front": "Front"}
    panel.participation = {"current-left": True, "current-front": False}
    panel.keys = list(panel.assignments)
    panel.diagram.outputs = [
        ("2", QRect(0, 0, 1920, 1080)),
        ("3", QRect(1920, 0, 1920, 1080)),
    ]
    panel.timing.set_displays(
        [
            ("current-left", "Display 2 · Left", True),
            ("current-front", "Display 3 · Front", False),
        ]
    )
    panel.timing.pulse.setChecked(False)
    panel.timing.mode.setCurrentText("VSync on all displays")
    panel.timing.target.setCurrentIndex(panel.timing.target.findData("current-front"))
    for key, value in zip(panel.timing.fields, (10, 20, 30, 40), strict=True):
        panel.timing.fields[key].setText(str(value))
    panel.calibration_files.profile = {
        "mappings": [
            {
                "surface_id": "front",
                "projector_role": "front",
                "geometric_profile": {"logical_path": "calibration/front.json"},
            }
        ],
        "output_settings": {
            "front": {"photometric_profile": {"logical_path": "color/front.json"}}
        },
    }
    expected = panel.calibration_files.snapshot()
    path = tmp_path / "projectors.json"
    panel.calibration_files.save_path(str(path))
    assert "current-front" not in path.read_text()
    assert "current-left" not in path.read_text()
    panel.timing.pulse.setChecked(True)
    panel.timing.mode.setCurrentText("VSync on pulse display")
    panel.timing.fields["Width"].clear()
    panel.assignments = {"new-left": "Left", "new-front": "Front"}
    panel.participation = {"new-left": False, "new-front": True}
    panel.keys = list(panel.assignments)
    panel.timing.set_displays(
        [
            ("new-left", "Display 4 · Left", False),
            ("new-front", "Display 5 · Front", True),
        ]
    )
    panel.calibration_files.load_path(str(path))
    assert panel.calibration_files.snapshot() == expected
    assert panel.assignments == {"new-left": "Left", "new-front": "Front"}
    assert panel.participation == {"new-left": True, "new-front": False}
    assert panel.timing.target.currentData() == "new-front"
    panel._profile_outputs = [
        {"output_id": face, "device_identity": f"new-{face}", "enabled": True}
        for face in ("left", "front")
    ]
    result = json.loads(
        panel.configuration_for_submit(visual_pb.DisplayConfiguration()).profile_json
    )
    assert result["mappings"][0]["output_id"] == "front"
    assert (
        result["mappings"][0]["geometric_profile"]["logical_path"]
        == "calibration/front.json"
    )
    assert (
        result["outputs"][1]["photometric_profile"]["logical_path"]
        == "color/front.json"
    )
    assert result["outputs"][1]["enabled"] is False
    assert set(result["photodiode_patches"]) == {"front"}
    assert result["photodiode_enabled"] is False
    assert result["photodiode_patches"]["front"]["rect"] == dict(
        x=10, y=20, width=30, height=40
    )


@pytest.mark.parametrize("invalid", ["pulse", "mapping", "nonfinite", "duplicate"])
def test_projector_configuration_invalid_settings_preserve_complete_draft(
    window: DashboardWindow, tmp_path: Path, invalid: str
):
    import json

    panel = window.devices.projectors
    before = panel.calibration_files.snapshot()
    payload = panel.calibration_files.snapshot()
    payload["values"]["rig.width"] = 123
    if invalid == "pulse":
        payload["settings"]["pulse_rect"]["Width"] = -10
    elif invalid == "mapping":
        payload["screen_profile"] = {"outputs": [], "mappings": []}
    elif invalid == "nonfinite":
        payload["screen_profile"] = {
            "mappings": [],
            "idle_linear_rgb": [float("nan"), 0, 0],
        }
    text = json.dumps(payload)
    if invalid == "duplicate":
        version = payload["version"]
        text = text.replace(
            f'"version": {version}', f'"version": {version}, "version": {version}'
        )
    path = tmp_path / "invalid.json"
    path.write_text(text)
    panel.calibration_files.load_path(str(path))
    assert panel.calibration_files.snapshot() == before
    assert "load failed" in panel.console.toPlainText()


def test_photodiode_frame_pulse_and_blackout_files_preserve_old_drafts(
    window, tmp_path
):
    panel = window.devices.projectors
    timing = panel.timing
    assert timing.blackouts.table.horizontalHeader().isHidden()
    timing.pulse.setChecked(True)
    for key, value in dict(X=100, Y=200, Width=180, Height=120).items():
        timing.fields[key].setText(str(value))
    for key, value in dict(X=20, Y=30, Width=40, Height=30).items():
        timing.pulse_fields[key].setText(str(value))
    timing.blackouts.add(dict(face="Front", x=10, y=20, width=100, height=50))
    assert not timing.blackouts.table.horizontalHeader().isHidden()
    expected = panel.calibration_files.snapshot()
    path = tmp_path / "overlays.json"
    panel.calibration_files.save_path(str(path))
    assert path.is_file()
    timing.blackouts.remove(timing.blackouts.rows[0])
    assert timing.blackouts.table.horizontalHeader().isHidden()
    timing.pulse_fields["Width"].clear()
    panel.calibration_files.load_path(str(path))
    assert not timing.blackouts.table.horizontalHeader().isHidden()
    assert panel.calibration_files.snapshot() == expected
    patch = timing.patch_draft()
    assert patch == {
        "background_rect": dict(x=100, y=200, width=180, height=120),
        "rect": dict(x=120, y=230, width=40, height=30),
    }
    overlays = timing.preview_overlays({"Front": (1000, 1000)}, "Front")
    assert overlays["Front"][0] == [(0.01, 0.02, 0.1, 0.05), (0.1, 0.2, 0.18, 0.12)]
    assert overlays["Front"][1] == (0.12, 0.23, 0.04, 0.03)
    timing.pulse_fields["Width"].setText("200")
    with pytest.raises(ValueError, match="fit inside"):
        timing.patch_draft()
    with pytest.raises(ValueError, match="fit inside"):
        panel.calibration_files.validate(panel.calibration_files.snapshot())
    legacy_square = dict(expected, version=6, settings=dict(expected["settings"]))
    legacy_square["settings"]["pulse_rect"] = legacy_square["settings"].pop(
        "frame_rect"
    )
    legacy_square["settings"]["pulse_square"] = dict(X=20, Y=30, Size=40)
    for face in ("Front", "Left", "Right", "Bottom"):
        for old, new in (("scale_u", "valid_width_px"), ("scale_v", "valid_height_px")):
            legacy_square["values"].pop(f"screens.{face}.{new}")
            legacy_square["values"][f"screens.{face}.{old}"] = None
    panel.calibration_files.apply_snapshot(legacy_square)
    assert timing.pulse_fields["Width"].text() == "40"
    assert timing.pulse_fields["Height"].text() == "40"
    before = panel.calibration_files.snapshot()
    legacy_square["settings"]["pulse_square"]["Size"] = 200
    with pytest.raises(ValueError, match="fit inside"):
        panel.calibration_files.apply_snapshot(legacy_square)
    assert panel.calibration_files.snapshot() == before
    legacy = dict(expected, version=5, settings=dict(expected["settings"]))
    legacy["settings"]["pulse_rect"] = legacy["settings"].pop("frame_rect")
    legacy["settings"].pop("blackout_zones")
    panel.calibration_files.apply_snapshot(legacy)
    assert not timing.blackouts.rows
    assert timing.blackouts.table.horizontalHeader().isHidden()
    assert timing.patch_draft() == {
        "rect": dict(x=100, y=200, width=180, height=120),
        "background_rect": None,
    }
    window.apply_view(review_view(Phase.RUNNING))
    timing.blackouts.add()
    assert not timing.blackouts.rows


@pytest.mark.parametrize("width", [1280, 720])
def test_photodiode_controls_fit_with_growing_blackouts(window, app, width):
    panel = window.devices.projectors
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(2)
    panel.setup_tabs.setCurrentIndex(1)
    panel.timing.pulse.setChecked(True)
    definition = panel.timing.definition
    assert definition.columnCount() == 5
    assert definition.rowCount() == 2
    assert [definition.horizontalHeaderItem(i).text() for i in range(1, 5)] == [
        "Origin X",
        "Origin Y",
        "Width",
        "Height",
    ]
    assert [definition.item(i, 0).text() for i in range(2)] == [
        "Frame",
        "Pulse",
    ]
    window.resize(width, 940)
    for count in (0, 6):
        for _ in range(count):
            panel.timing.blackouts.add(
                dict(face="Front", x=0, y=0, width=10, height=10)
            )
        for _ in range(5):
            app.processEvents()
        for editor in (
            panel.timing.target,
            panel.timing.mode,
            *panel.timing.fields.values(),
            *panel.timing.pulse_fields.values(),
        ):
            assert editor.parentWidget().rect().contains(editor.geometry())
        page = panel.setup_pages.currentWidget()
        assert page.height() >= page.minimumSizeHint().height()


def test_planning_preview_keeps_square_visible_over_blackout(app):
    from PyQt6.QtGui import QColor

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.trial_preview_canvas import PreviewCanvas
    from cephvr.gui.trial_preview_media import PreviewMedia
    from cephvr.gui.trial_preview_surfaces import PreviewGeometry, PreviewSurface

    surface = PreviewSurface(
        100,
        100,
        blackout_zones=((0.1, 0.1, 0.8, 0.8),),
        marker_rect=(0.4, 0.4, 0.2, 0.2),
    )
    canvas = PreviewCanvas(
        "Front",
        PreviewMedia(blank_program(), "", None),
        PreviewGeometry({"Front": surface}, None),
    )
    canvas.background = QColor("red")
    image = canvas.frame_image()
    assert image.pixelColor(image.width() // 2, image.height() // 2) == QColor("white")
    assert image.pixelColor(image.width() // 4, image.height() // 2) == QColor("black")
    assert image.pixelColor(0, 0) == QColor("red")
    canvas.deleteLater()
    app.processEvents()


def test_authoritative_photodiode_area_installs_relative_square_and_zones(window):
    timing = window.devices.projectors.timing
    patch = dict(
        background_rect=dict(x=100, y=200, width=180, height=120),
        rect=dict(x=120, y=230, width=40, height=40),
        high_linear_rgb=[1, 1, 1],
        low_linear_rgb=[0, 0, 0],
    )
    timing.install_overlays(
        {"photodiode_patch": patch, "photodiode_output_id": "front"},
        {"output": "Front"},
        {
            "output": {
                "output_id": "front",
                "blackout_zones": [dict(x=5, y=10, width=15, height=20)],
            }
        },
    )
    assert timing.patch_draft() == {k: patch[k] for k in ("rect", "background_rect")}
    assert timing.blackouts.snapshot() == [
        dict(face="Front", x=5, y=10, width=15, height=20)
    ]
    with pytest.raises(ValueError, match="positive"):
        timing.preview_overlays({"Front": (0, 0)}, None)


def test_legacy_numeric_projector_json_preserves_synchronization(
    window: DashboardWindow, tmp_path: Path
):
    import json

    panel = window.devices.projectors
    numeric = panel.calibration_files.calibration_snapshot()
    numeric["values"]["rig.width"] = 200
    panel.timing.pulse.setChecked(True)
    panel.timing.mode.setCurrentText("VSync on all displays")
    path = tmp_path / "legacy-calibration.json"
    path.write_text(json.dumps(numeric))
    panel.calibration_files.load_path(str(path))
    assert panel.rig_editor.fields["width"].text() == "200"
    assert panel.timing.pulse.isChecked()
    assert panel.timing.mode.currentText() == "VSync on all displays"
    assert panel.calibration_files.snapshot()["version"] == 11


def test_portable_screen_profile_rebinds_native_properties_and_preserves_coverage(
    monkeypatch,
):
    import json

    from tests.visual_stimulus.support import valid_display_json

    from cephvr.gui.calibration_profile import MonitorBinding
    from cephvr.gui.projector_profile import (
        bind_profile,
        current_outputs,
        portable_profile,
    )
    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

    original = json.loads(valid_display_json())
    original["photodiode_enabled"] = False
    original["presentation_mode"] = "all_outputs_vsync"
    profile = portable_profile(original)
    monkeypatch.setattr(
        "cephvr.gui.projector_profile.active_monitor_bindings",
        lambda: (MonitorBinding("new-native-id", 0, 0, 1920, 1080, 60, 8),),
    )
    assignments = {"new-native-id": "Front"}
    outputs = current_outputs([], assignments, {}, native=True)
    rebound = bind_profile(profile, outputs, assignments)
    adopted = DisplayProfile.model_validate_json(json.dumps(rebound))
    assert adopted.outputs[0].device_identity == "new-native-id"
    assert adopted.outputs[0].width_px == 1920
    assert len({mapping.output_id for mapping in adopted.mappings}) == 1
    assert adopted.geometry.model_dump(mode="json") == original["geometry"]
    assert [mapping.geometric_profile.logical_path for mapping in adopted.mappings] == [
        f"geometry/{face}.json" for face in ("front", "left", "right", "bottom")
    ]
    assert "edid:one" not in json.dumps(profile)


def test_authoritative_projector_install_clears_previous_profile_on_empty_state(window):
    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_pb

    panel = window.devices.projectors
    panel.install_configuration(
        visual_pb.DisplayConfiguration(profile_json=valid_display_json())
    )
    assert panel.calibration_files.profile is not None
    assert panel._profile_outputs
    panel.install_configuration(visual_pb.DisplayConfiguration())
    assert panel.calibration_files.profile is None
    assert panel._profile_outputs == []


def test_projector_reference_measurements_derive_distance_and_roundtrip(
    window, tmp_path
):
    import json

    from cephvr.gui.calibration_profile import reference_bar_config

    panel = window.devices.projectors
    table = panel.measurements.table
    assert panel.screen_editor.fields["Front", "throw"].isHidden()
    assert panel.screen_editor.fields["Front", "throw"].isReadOnly()
    assert panel.screen_editor.table.columnCount() == 4
    assert [
        table.horizontalHeaderItem(i).text() for i in range(table.columnCount())
    ] == [
        "Screen",
        "Measured X / Y (mm)",
        "X / Y (mm/px)",
    ]
    assert not any(
        "Launch calibration and measure" in caption.text()
        for caption in panel.measurements.findChildren(QLabel)
    )
    x_field = panel.measurements.fields["Front", "reference_x_mm"]
    y_field = panel.measurements.fields["Front", "reference_y_mm"]
    assert x_field.parentWidget() is y_field.parentWidget()
    panel.display_pixels = {"reference-test": (1280, 720)}
    panel.assignments["reference-test"] = "Front"
    panel.screen_editor.fields["Front", "throw"].setText("1.5")
    panel.measurements.fields["Front", "reference_x_mm"].setText("160")
    assert panel.screen_editor.fields["Front", "distance"].text() == ""
    panel.measurements.fields["Front", "reference_y_mm"].setText("90")
    distance = panel.screen_editor.fields["Front", "distance"]
    assert distance.isReadOnly()
    assert float(distance.text()) == pytest.approx(960)
    assert distance.text() == "960.0"
    panel.measurements.fields["Front", "reference_x_mm"].setText("30.4")
    assert distance.text() == "182.4"
    assert panel.measurements.scales["Front"].text() == "0.1 / 0.5"
    assert (
        panel.calibration_files.snapshot()["values"]["screens.Front.reference_x_mm"]
        == 30.4
    )
    panel.measurements.fields["Front", "reference_x_mm"].setText("160")
    assert panel.measurements.scales["Front"].text() == "0.5 / 0.5"
    snapshot = panel.calibration_files.snapshot()
    assert snapshot["version"] == 11
    assert snapshot["values"]["screens.Front.reference_width_px"] == 1280
    panel.measurements.fields["Front", "reference_x_mm"].setText("200")
    panel.calibration_files.apply_snapshot(snapshot)
    panel.update_geometry()
    assert float(distance.text()) == pytest.approx(960)
    assert panel.calibration_files.snapshot() == snapshot
    configured = json.loads(json.dumps(snapshot))
    configured["values"]["screens.Front.reference_x_px"] = 200
    configured["values"]["screens.Front.reference_y_px"] = 100
    path = tmp_path / "bars.json"
    path.write_text(json.dumps(configured), encoding="utf-8")
    panel.calibration_files.load_path(str(path))
    assert reference_bar_config(
        panel.calibration_files.calibration_snapshot(), "Front", 1280, 720
    ) == {
        "x_length_px": 200,
        "y_length_px": 100,
    }
    assert panel.measurements.scales["Front"].text() == "0.8 / 0.9"
    assert float(distance.text()) == pytest.approx(1536)
    panel.screen_editor.fields["Front", "throw"].clear()
    assert panel.measurements.scales["Front"].text() == "0.8 / 0.9"
    assert distance.text() == ""
    legacy = json.loads(json.dumps(snapshot))
    legacy["version"] = 4
    legacy["values"] = {
        k: v
        for k, v in legacy["values"].items()
        if not k.endswith(("offset_x_px", "offset_y_px"))
    }
    legacy["settings"]["pulse_rect"] = legacy["settings"].pop("frame_rect")
    legacy["settings"].pop("blackout_zones")
    legacy["values"] = {
        key: value
        for key, value in legacy["values"].items()
        if key.rsplit(".", 1)[-1] not in {"reference_x_px", "reference_y_px"}
    }
    for face in ("Front", "Left", "Right", "Bottom"):
        for old, new in (("scale_u", "valid_width_px"), ("scale_v", "valid_height_px")):
            legacy["values"].pop(f"screens.{face}.{new}")
            legacy["values"][f"screens.{face}.{old}"] = None
    panel.calibration_files.apply_snapshot(legacy)
    panel.update_geometry()
    assert panel.calibration_files.snapshot() == snapshot
    for invalid_length in (1.5, 1281):
        invalid = json.loads(json.dumps(snapshot))
        invalid["values"]["screens.Front.reference_x_px"] = invalid_length
        with pytest.raises(ValueError):
            panel.calibration_files.apply_snapshot(invalid)
        assert panel.calibration_files.snapshot() == snapshot
    panel.calibration_files.apply_snapshot(snapshot)
    panel.update_geometry()
    panel.display_pixels["reference-test"] = (1920, 1080)
    panel.update_geometry()
    assert distance.text() == ""
    assert panel.measurements.fields["Front", "reference_width_px"].text() == "1280.0"
    assert panel.measurements.fields["Front", "reference_x_mm"].text() == "160.0"


def test_old_projector_snapshot_retains_unmeasured_distance_and_rejects_new_fields(
    window,
):
    import copy

    panel = window.devices.projectors
    old = panel.calibration_files.snapshot()
    old["version"] = 3
    old["values"] = {
        k: v
        for k, v in old["values"].items()
        if not k.endswith(("offset_x_px", "offset_y_px"))
    }
    old["settings"]["pulse_rect"] = old["settings"].pop("frame_rect")
    old["settings"].pop("blackout_zones")
    old["values"] = {
        key: value
        for key, value in old["values"].items()
        if not key.rsplit(".", 1)[-1].startswith("reference_")
    }
    old["values"]["screens.Front.distance"] = 500
    for face in ("Front", "Left", "Right", "Bottom"):
        for old_key, new in (
            ("scale_u", "valid_width_px"),
            ("scale_v", "valid_height_px"),
        ):
            old["values"].pop(f"screens.{face}.{new}")
            old["values"][f"screens.{face}.{old_key}"] = None
    panel.calibration_files.apply_snapshot(old)
    assert panel.screen_editor.fields["Front", "distance"].text() == "500"
    assert panel.measurements.fields["Front", "reference_x_mm"].text() == ""
    before = panel.calibration_files.snapshot()
    invalid = copy.deepcopy(old)
    invalid["values"]["screens.Front.reference_x_mm"] = 100
    with pytest.raises(ValueError, match="inventory"):
        panel.calibration_files.apply_snapshot(invalid)
    assert panel.calibration_files.snapshot() == before


@pytest.mark.parametrize("extra_x,extra_y", [(1.0, 1.0), (1.1, 0.95), (0.9, 1.05)])
@pytest.mark.parametrize("throw", [None, 1.5])
def test_measured_affine_profiles_preserve_assets_and_match_preview(
    tmp_path, extra_x, extra_y, throw
):
    import json

    from cephvr.gui.calibration_profile import (
        AssignedDisplay,
        MonitorBinding,
        diagnostic_display_profile,
        write_diagnostic_bundle,
    )
    from cephvr.gui.projector_geometry import FACES
    from cephvr.gui.projector_measured_profiles import measured_profiles
    from cephvr.gui.trial_preview_surfaces import PreviewCorrection

    values = dict(
        zip(
            (
                "rig.width",
                "rig.depth",
                "rig.height",
                "rig.subject_x",
                "rig.subject_y",
                "rig.subject_z",
            ),
            (120, 166, 110, 60, 93, 53),
            strict=True,
        )
    )
    for face in FACES:
        values[f"screens.{face}.width"] = 90
        values[f"screens.{face}.height"] = 80
        if face != "Right":
            values[f"screens.{face}.subject_distance"] = 50
    calibration = {"format": "cephvr-rig-calibration", "version": 6, "values": values}
    assignments = tuple(
        AssignedDisplay(f, i * 1280, 0, 1280, 720, True) for i, f in enumerate(FACES)
    )
    monitors = tuple(
        MonitorBinding(f"interface-{i}", i * 1280, 0, 1280, 720, 60, 8)
        for i in range(4)
    )
    profile, _ = diagnostic_display_profile(calibration, assignments, monitors)
    write_diagnostic_bundle(
        tmp_path, calibration, assignments, monitors, runtime_root=tmp_path
    )
    original = tmp_path / "calibration/diagnostic_front.json"
    original_bytes = original.read_bytes()
    for key, value in dict(
        reference_width_px=1280,
        reference_height_px=720,
        reference_x_px=200,
        reference_y_px=100,
        reference_x_mm=160,
        reference_y_mm=90,
        throw=throw,
        valid_width_px=round(90 / 0.8 * extra_x),
        valid_height_px=round(80 / 0.9 * extra_y),
    ).items():
        for face in FACES:
            values[f"screens.{face}.{key}"] = value
    _, grid_meshes = diagnostic_display_profile(
        calibration, assignments, monitors, view="frame_grid"
    )
    document = measured_profiles(
        profile.model_dump(mode="json"), calibration, str(tmp_path)
    )
    front_output = next(
        o for o in document["outputs"] if o["output_id"] == "calibration_front"
    )
    assert front_output["reference_bars"] == {"x_length_px": 200, "y_length_px": 100}
    front = next(m for m in document["mappings"] if m["surface_id"] == "front")
    generated = tmp_path / front["geometric_profile"]["logical_path"]
    assert generated != original
    mesh = json.loads(generated.read_text(encoding="utf-8"))
    assert mesh["vertices"][0]["xy"] == pytest.approx(
        [
            0.5 - round(90 / 0.8 * extra_x) / 1280 / 2,
            0.5 - round(80 / 0.9 * extra_y) / 720 / 2,
        ]
    )
    for face in FACES:
        mapping = next(
            m for m in document["mappings"] if m["surface_id"] == face.lower()
        )
        submitted = json.loads(
            (tmp_path / mapping["geometric_profile"]["logical_path"]).read_text(
                encoding="utf-8"
            )
        )
        assert submitted["valid_area"] == list(grid_meshes[face.lower()].valid_area)
        assert abs(
            grid_meshes[face.lower()].vertices[1].xy[0]
            - grid_meshes[face.lower()].vertices[0].xy[0]
        ) == pytest.approx(1)
        import math
        from types import SimpleNamespace

        from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
        from cephvr.visual_stimulus.rendering.layer_projection import physical_corners

        surface = next(
            s
            for s in document["geometry"]["surfaces"]
            if s["surface_id"] == face.lower()
        )
        extent_x = math.dist(surface["bottom_left_mm"], surface["bottom_right_mm"])
        extent_y = math.dist(surface["bottom_left_mm"], surface["top_left_mm"])
        pixels = (round(90 / 0.8 * extra_x), round(80 / 0.9 * extra_y))
        pitch = (0.8, 0.9)
        if face == "Bottom":
            pixels, pitch = pixels[::-1], pitch[::-1]
        assert extent_x == pytest.approx(pixels[0] * pitch[0])
        assert extent_y == pytest.approx(pixels[1] * pitch[1])
        projected = physical_corners(
            SimpleNamespace(
                display=DisplayProfile.model_validate_json(json.dumps(document))
            ),
            SimpleNamespace(state=(("width", 20), ("height", 10), ("x", 0), ("y", 0))),
            face.lower(),
            SimpleNamespace(matrix=((1, 0, 0), (0, 1, 0))),
        )
        # A 20-by-10 mm texture retains its physical period, irrespective of view crop.
        assert (projected[1][0] - projected[0][0]) / 2 * pixels[0] == pytest.approx(
            20 / pitch[0]
        )
        assert (projected[3][1] - projected[0][1]) / 2 * pixels[1] == pytest.approx(
            10 / pitch[1]
        )
        # Cropping changes visible extents while physical pixel pitch stays fixed.
        bounds = submitted["valid_area"]
        assert (bounds[2] - bounds[0]) * 1280 == pytest.approx(
            round(90 / 0.8 * extra_x)
        )
        assert (bounds[3] - bounds[1]) * 720 == pytest.approx(round(80 / 0.9 * extra_y))
        bottom_left, bottom_right, top_left = submitted["vertices"][:3]
        assert (bottom_right["xy"][0] - bottom_left["xy"][0]) * 1024 == pytest.approx(
            round(90 / 0.8 * extra_x) * 0.8
        )
        assert (top_left["xy"][1] - bottom_left["xy"][1]) * 648 == pytest.approx(
            round(80 / 0.9 * extra_y) * 0.9
        )
    draft = {
        k.removeprefix("screens.Front."): "" if v is None else str(v)
        for k, v in values.items()
        if k.startswith("screens.Front.")
    }
    preview = PreviewCorrection.from_draft("Front", draft, (1280, 720))
    assert not preview.error
    assert preview.corners == tuple(
        tuple(mesh["vertices"][i]["xy"]) for i in (0, 1, 3, 2)
    )
    assert original.read_bytes() == original_bytes
    # Repeated submission produces the same content-addressed asset.
    assert measured_profiles(document, calibration, str(tmp_path)) == document
    values["screens.Front.reference_width_px"] = 1920
    with pytest.raises(ValueError, match="output mode"):
        measured_profiles(document, calibration, str(tmp_path))
    values["screens.Front.reference_width_px"] = 1280
    mesh["calibration_id"] = "imported-optical-warp"
    generated.write_text(json.dumps(mesh), encoding="utf-8")
    with pytest.raises(ValueError, match="imported warp"):
        measured_profiles(document, calibration, str(tmp_path))
    generated.unlink()
    with pytest.raises(ValueError, match="Front: cannot read geometric calibration"):
        measured_profiles(document, calibration, str(tmp_path))
    assert not generated.exists()


@pytest.mark.parametrize("suffix", ["hex", "ino"])
@pytest.mark.asyncio
async def test_gui_firmware_dispatch_pins_selected_sketch_or_image(tmp_path, suffix):
    from cephvr.client.session import CommandOutcome
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.controller.microcontroller.firmware_source import read_firmware
    from cephvr.gui.managed_device_commands import dispatch_device_action
    from cephvr.shared.auth import Principal

    path = tmp_path / f"uno.{suffix}"
    path.write_bytes(
        b"void setup() {}\nvoid loop() {}\n"
        if suffix == "ino"
        else b":0400000001020304F2\n:00000001FF\n"
    )
    if suffix == "ino":
        (tmp_path / "pins.h").write_text("#define PIN 9\n")
    expected = read_firmware(str(path))
    calls = []

    class Client:
        snapshot = pb.Snapshot()
        snapshot.configuration.revision = 4

        def operator_command(self):
            return rpc.OperatorCommand(operator=pb.OperatorContext(command_id="upload"))

        async def execute(self, method, request):
            calls.append((method, request))
            return CommandOutcome("upload", True, True)

    result = await dispatch_device_action(
        Client(),
        "mcu_upload",
        {"path": str(path)},
        Principal("gui", "generation", "token"),
    )
    assert result == (True, "Completed")
    method, request = calls[0]
    assert method == "ExecuteMicrocontrollerCommand"
    assert request.kind == rpc.MICROCONTROLLER_COMMAND_KIND_UPLOAD_FIRMWARE
    assert request.expected_configuration_revision == 4
    assert request.firmware_path == str(path)
    assert request.firmware_sha256 == expected.digest


def test_group_actions_preserve_contents_selection_and_history(window, tmp_path):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
    editor.set_program(grouped_program(review_program()))
    original = editor.program
    assert editor.path == (0, 0)
    editor.timeline.block_actions.add.click()
    assert len(editor.program.sequence) == 2 and editor.path == (1, 0)
    assert editor.program.sequence[0] == original.sequence[0]
    added = editor.snapshot()
    editor.remove_block(((editor.path[0],),))
    assert editor.program.sequence == original.sequence
    assert editor.path == (0, 0)
    editor.undo()
    assert editor.snapshot() == added
    path = tmp_path / "groups.json"
    window.protocol.save_program(str(path))
    assert parse_program_json(path.read_text(), max_bytes=1_048_576) == added.program
    editor.undo()
    assert editor.program == original


def test_group_actions_obey_authority_and_pending_validation(window):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.protocol_nodes import edit_epoch

    editor = window.protocol.editor
    editor.set_program(edit_epoch(grouped_program(review_program()), 0, "duplicate")[0])
    original = editor.program
    editor.setEnabled(False)
    editor.edit_group("remove")
    editor.add_group()
    assert editor.program == original
    editor.setEnabled(True)
    editor.subgroup.composer.duration.setText("invalid")
    editor.edit_group("remove")
    editor.add_group()
    assert editor.program == original
    assert not editor.histories[editor.index].past


def test_group_actions_keep_one_group_and_noop_history(window):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program

    editor = window.protocol.editor
    editor.set_program(grouped_program(review_program()))
    original = editor.snapshot()
    assert not hasattr(editor, "shuffle_trial_button")
    assert not hasattr(editor, "remove_group_button")
    editor.edit_group("earlier")
    assert editor.snapshot() == original
    assert not editor.histories[editor.index].past


@pytest.mark.parametrize("reload", [False, True])
def test_rejected_controller_configuration_restores_edit_tracking(window, reload):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_configuration import (
        ConfigurationPages,
        ManagedConfiguration,
    )

    manager = ManagedConfiguration(
        ConfigurationPages(
            window.dashboard,
            window.protocol,
            window.recordings,
            window.devices.cameras,
            window.devices.projectors,
            window.tracking,
        )
    )
    state = pb.Snapshot(controller_generation="controller")
    state.configuration.revision = state.configuration_values.revision = 1
    assert manager.install(state)
    broken = pb.Snapshot.FromString(state.SerializeToString())
    broken.configuration.revision = broken.configuration_values.revision = 2
    broken.configuration_values.current.trials.add(
        trial_number=1
    ).stimulus.program.program_json = "invalid"
    original = window.protocol.editor.program
    if reload:
        manager.stale = True
        assert not manager.reload(broken)
        assert "Trial 1 source is invalid" in manager.last_error
    else:
        with pytest.raises(ValueError, match="Trial 1 source is invalid"):
            manager.install(broken)
    assert not manager._installing
    assert manager.revision == 1
    assert window.protocol.editor.program == original
    before = manager.edit_serial
    window.dashboard.subject_id.textEdited.emit("still editable")
    assert manager.dirty and manager.edit_serial == before + 1
    assert manager.reload(state)
    assert not manager.stale and not manager.dirty and not manager.last_error


def test_calibration_adjustment_steps_preserve_drafts(app):
    from cephvr.gui.projector_calibration import CalibrationTable
    from cephvr.gui.projector_geometry import FACES

    drafts = {face: {} for face in FACES}
    table = CalibrationTable(drafts)
    edits = []
    table.adjustments_changed.connect(lambda face, key: edits.append((face, key)))
    for key, initial, increased, decreased in (
        ("valid_width_px", "100", "101", "100"),
        ("valid_height_px", "80", "81", "80"),
    ):
        editor = table.controls["Front", key]
        editor.setText(initial)
        QTest.keyClick(editor, Qt.Key.Key_Up)
        assert editor.text() == increased
        assert drafts["Front"][key] == increased
        assert edits[-1] == ("Front", key)
        QTest.keyClick(editor, Qt.Key.Key_Down)
        assert editor.text() == decreased
    scale = table.controls["Front", "valid_width_px"]
    scale.setText("0.812345")
    assert scale.text() == "0.812345"  # Loading does not round saved precision.
    for partial in ("-", "nan", "inf"):
        scale.setText(partial)
        count = len(edits)
        QTest.keyClick(scale, Qt.Key.Key_Up)
        assert scale.text() == partial and len(edits) == count
    scale.setText("0.01")
    QTest.keyClick(scale, Qt.Key.Key_Down)
    assert scale.text() == "0.01"
    scale.setReadOnly(True)
    QTest.keyClick(scale, Qt.Key.Key_Up)
    assert scale.text() == "0.01"
    assert table.table.columnCount() == 4
    assert (
        table.controls["Front", "offset_x_px"].parentWidget()
        is table.controls["Front", "offset_y_px"].parentWidget()
    )
    from PyQt6.QtWidgets import QToolButton

    assert not table.findChildren(QToolButton)
    scale.setReadOnly(False)
    table.refresh_dimensions({"Front": (120, 100)})
    scale.setText("119")
    QTest.keyClick(scale, Qt.Key.Key_Up)
    QTest.keyClick(scale, Qt.Key.Key_Up)
    assert scale.text() == "120"
    scale.setText("100")
    scale.textEdited.emit("100")
    offset = table.controls["Front", "offset_x_px"]
    offset.setText("10")
    QTest.keyClick(offset, Qt.Key.Key_Up)
    assert offset.text() == "10"
    offset.setText("-10")
    QTest.keyClick(offset, Qt.Key.Key_Down)
    assert offset.text() == "-10"
    scale.setText("120")
    scale.textEdited.emit("120")
    assert offset.text() == "0" and drafts["Front"]["offset_x_px"] == "0"
    scale.setText("10000")
    scale.textEdited.emit("10000")
    assert scale.text() == "120"
    table.close()


def test_live_calibration_coalesces_edits_and_retains_last_valid_projection(window):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.live_calibration import LiveCalibration
    from cephvr.gui.projector_geometry import FACES
    from cephvr.visual_stimulus.v1 import messages_pb2 as messages
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

    panel = window.devices.projectors
    panel.apply_view(review_view(Phase.CONFIGURATION))
    for face in FACES:
        for key, value in (("width", "90"), ("height", "80")):
            panel.screen_editor.fields[face, key].setText(value)
        for key, value in (
            ("reference_width_px", "1280"),
            ("reference_height_px", "720"),
            ("reference_x_mm", "160"),
            ("reference_y_mm", "90"),
        ):
            panel.measurements.fields[face, key].setText(value)
    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 4
    evidence = state.visual_stimulus_display.calibration
    evidence.controller_generation = state.controller_generation
    evidence.configuration_revision = 4
    evidence.diagnostic_id = str(uuid4())
    evidence.calibration_view = "frame_grid"
    evidence.state = vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    sent = []
    live = LiveCalibration(
        panel,
        snapshot=lambda: state,
        send=lambda action, **options: sent.append((action, options)) or True,
    )
    live.install(state)
    panel.set_calibration_presentation_state(
        active=True, available=True, view="frame_grid"
    )
    assert panel.calibration.controls["Front", "valid_width_px"].isEnabled()
    assert not panel.calibration.controls["Front", "flip_x"].isEnabled()
    assert not panel.measurements.isEnabled()
    assert not panel.rig_editor.isEnabled()
    offset = panel.calibration.controls["Front", "valid_width_px"]
    offset.setText("16")
    QTest.keyClick(offset, Qt.Key.Key_Up)
    live.flush()
    assert len(sent) == 1
    action, first = sent[0]
    assert action == "update_display_calibration"
    assert first["adjustment_sequence"] == 1
    assert first["diagnostic_id"] == evidence.diagnostic_id
    adjustment = messages.DisplayCalibrationAdjustment.FromString(
        first["adjustments"][0]
    )
    assert adjustment.mapping_id == "diagnostic_front"
    assert adjustment.destination_xy[0] == pytest.approx(0.5 - 17 / 1280 / 2)
    offset.setText("32")
    offset.textEdited.emit("32")
    live.flush()
    assert len(sent) == 1  # One RPC in flight; retain latest edit.
    evidence.adjustment_sequence = 1
    live.install(state)
    live.flush()
    assert len(sent) == 2 and sent[-1][1]["adjustment_sequence"] == 2
    evidence.adjustment_sequence = 2
    live.install(state)
    offset.setText("-")
    offset.textEdited.emit("-")
    live.flush()
    assert len(sent) == 2
    offset.setText("10000")
    offset.textEdited.emit("10000")
    live.flush()
    assert len(sent) == 2  # Outside output leaves the confirmed frame unchanged.
    offset.setText("40")
    offset.textEdited.emit("40")
    evidence.state = vp.DISPLAY_CALIBRATION_STATE_IDLE
    live.install(state)
    live.flush()
    assert len(sent) == 2 and not live.dirty and not live.inflight
    evidence.state = vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    evidence.calibration_view = "reference_bars"
    live.edited()
    live.flush()
    assert len(sent) == 2
    evidence.calibration_view = "frame_grid"
    panel.apply_view(review_view(Phase.CONFIGURATION, observer=True))
    live.edited()
    live.flush()
    assert len(sent) == 2 and not offset.isEnabled()
    live.reset()

    # Unknown presentation remains closable, with all tuning disabled.
    from cephvr.gui.managed_display import ManagedDisplayOperations

    panel.apply_view(review_view(Phase.CONFIGURATION))
    evidence.state = vp.DISPLAY_CALIBRATION_STATE_UNKNOWN
    operations = ManagedDisplayOperations(
        panel,
        window.devices.spikeglx,
        snapshot=lambda: state,
        connection_identity=lambda: (1, state.controller_generation),
        send=lambda *_args, **_kwargs: True,
    )
    operations.install_calibration_state(state, launch_eligible=True)
    assert panel.calibration.presentation_button.text() == "Close"
    assert panel.calibration.presentation_button.isEnabled()
    assert not offset.isEnabled()
    operations.live.reset()


def test_grouped_editor_pair_creation_repeat_scope_and_history(window, tmp_path, app):
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_nodes import edit_epoch
    from cephvr.visual_stimulus.config.models.program_model import (
        Group,
        parse_program_json,
    )

    window.page_buttons[1].click()
    editor = window.protocol.editor
    pair, _ = edit_epoch(blank_program(), 0, "duplicate")
    from cephvr.gui.protocol_batches import grouped_program

    editor.set_program(grouped_program(pair))
    editor.timeline.choose(0, Qt.KeyboardModifier.NoModifier)
    assert editor.scope == (0,) and len(editor.timeline.nodes) == 1
    assert len(editor.hierarchy.contents.nodes) == 2
    group = editor.program.sequence[0]
    assert isinstance(group, Group) and group.body == pair.sequence
    fields = editor.group_editor
    fields.name.setText("Image Grey")
    fields.repetitions.setText("300")
    fields.mark_changed()
    assert fields.apply()
    assert editor.program.sequence[0].group_id == "Image_Grey"
    assert editor.program.sequence[0].repetitions == 300
    assert "600 epochs" in editor.sequence_summary.text()
    assert len(editor.hierarchy.contents.nodes) == 2
    fields.mark_changed()  # A pending field commit must preserve the clicked selection.
    editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
    assert editor.path == (0, 1)
    assert editor.hierarchy.contents.index == editor.hierarchy.contents.anchor == 1
    editor.subgroup.composer.duration.setText("00:00:02")
    editor.subgroup.apply()
    assert editor.program.sequence[0].body[1].duration.duration.seconds == "2"
    assert editor.program.sequence[0].repetitions == 300
    path = tmp_path / "grouped.json"
    window.protocol.save_program(str(path))
    saved = parse_program_json(path.read_text(), max_bytes=1_048_576)
    assert saved == editor.program
    editor.undo()
    assert editor.program.sequence[0].body[1].duration.duration.seconds == "60"
    editor.undo()
    assert editor.program.sequence[0].repetitions == 1
    editor.undo(True)
    assert editor.scope == (0,)
    editor.timeline.context_selected.emit(((0,),))
    assert editor.path == (0, 0) and editor.scope == (0,)
    assert not editor.subgroup.isHidden()
    editor.edit_group("duplicate")
    assert len(editor.program.sequence) == 2
    assert all(isinstance(n, Group) for n in editor.program.sequence)
    editor.undo()
    editor.timeline.choose(0, Qt.KeyboardModifier.NoModifier)
    assert editor.scope == (0,)
    app.processEvents()
    for width in (1280, 720):
        window.resize(width, 1000)
        for _ in range(3):
            app.processEvents()
        assert fields.repetitions.width() >= 40
        assert not hasattr(fields, "order")
        assert editor.hierarchy.contents.block_actions.enabled
        assert editor.hierarchy.contents.isVisible()


@pytest.mark.parametrize(
    "mode", ["append", "start", "before", "after", "replace", "stride", "label"]
)
def test_grouped_batch_insertion_stays_inside_open_group(mode):
    from cephvr.gui.batch_insertion import Insertion, insert_batch
    from cephvr.gui.program_editing import data_node, validate
    from cephvr.gui.protocol_document import blank_program, review_program
    from cephvr.gui.protocol_groups import make_group

    program, _ = make_group(review_program(), (), 0, 1, 300, False)
    data = program.model_dump(mode="json")
    data_node(data, (0, 0))["batch_label"] = "target"
    data_node(data, (1,))["batch_label"] = "target"
    program = validate(data)
    result, paths = insert_batch(
        program, blank_program(), (0, 0), Insertion(mode, 1, "target"), scope=(0,)
    )
    assert result.sequence[1] == program.sequence[1]
    assert result.sequence[0].group_id == program.sequence[0].group_id
    assert result.sequence[0].repetitions == 300
    assert paths and all(p[0] == 0 for p in paths)
    assert len(result.sequence[0].body) == (1 if mode == "replace" else 3)


def test_grouped_timeline_large_repeat_and_visible_paint_are_bounded(
    window, app, monkeypatch
):
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.protocol_groups import make_group
    from cephvr.visual_stimulus.compiler import expansion

    program, _ = make_group(review_program(), (), 0, 1, 50_000, False)
    editor = window.protocol.editor
    editor.set_program(program)
    monkeypatch.setattr(
        expansion,
        "expand_program",
        lambda *a, **k: pytest.fail("Timeline expanded repetitions"),
    )
    editor.timeline.choose(0, Qt.KeyboardModifier.NoModifier)
    assert len(editor.timeline.nodes) == len(editor.hierarchy.contents.nodes) == 2
    assert "100,001 epochs" in editor.timeline.summary()
    source = review_program()
    many = source.model_copy(
        update={
            "sequence": tuple(
                source.sequence[0].model_copy(update={"epoch_id": f"Epoch_{i}"})
                for i in range(5000)
            )
        }
    )
    # No backend preparation, image loading or occurrence expansion is needed to paint.
    timeline = editor.timeline
    timeline.set_program(many, 4999)
    timeline.resize(400, timeline.height())
    timeline.reveal_selection()
    timeline.grab()
    assert len(timeline.hits) <= 4
    assert any(i == 4999 for _, i, _, _ in timeline.hits)


def test_flat_group_initial_trials_and_legacy_imports(app):
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.protocol_groups import make_group
    from cephvr.visual_stimulus.config.models.program_model import Epoch, Group

    window = DashboardWindow(sample=True)
    ReviewControls(window)
    window.show()
    window.page_buttons[1].click()
    editor = window.protocol.editor
    assert all(isinstance(n, Group) for n in editor.program.sequence)
    assert all(isinstance(n, Epoch) for n in editor.program.sequence[0].body)
    before = editor.program
    editor.edit_epoch("add")
    assert len(editor.program.sequence[0].body) == len(before.sequence[0].body) + 1
    assert editor.selected_paths == ((0, 3),)
    editor.feedback.clear()
    editor.timeline.context_selected.emit(((0,),))
    window.activateWindow()
    editor.timeline.setFocus()
    app.processEvents()
    QTest.keyClick(editor.timeline, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert len(editor.program.sequence) == 2
    assert all(isinstance(n, Group) for n in editor.program.sequence)
    editor.add_trial()
    assert isinstance(editor.program.sequence[0], Group)
    nested, _ = make_group(review_program(), (), 0, 1, 3, True)
    nested, _ = make_group(nested, (), 0, 1, 2, False)
    editor.set_program(nested)
    editor.enter_group()
    assert editor.program == nested  # Never resolve imported shuffle while loading.
    assert editor.timeline.block_actions.enabled
    assert not editor.hierarchy.contents.block_actions.enabled
    assert editor.subgroup.isHidden()
    editor.subgroup.generate()
    assert editor.program == nested
    editor.add_group()
    assert editor.program.sequence[:-1] == nested.sequence
    window.close()
    window.deleteLater()
    app.processEvents()


def test_unified_subgroup_template_add_apply_history_and_files(window, app, tmp_path):
    from PyQt6.QtWidgets import QTabBar

    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(grouped_program(review_program()))
    editor.timeline.set_screens(("Left", "Right"))
    editor.enter_group()
    editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
    form = editor.subgroup
    original = editor.program
    template = original.sequence[0].body[1]
    assert not editor.settings_card.findChildren(QTabBar)
    assert not hasattr(editor.hierarchy, "batch_picker")
    assert not hasattr(editor, "batch_edit")
    assert editor.hierarchy.contents.block_actions.add.menu() is None
    editor.hierarchy.contents.block_actions.add.click()
    assert editor.selected_paths == ((0, 3),)
    created = editor.program.sequence[0].body[3]
    assert created.settings[0].model_dump(exclude={"instance_id"}) == template.settings[
        0
    ].model_dump(exclude={"instance_id"})
    assert created.duration == template.duration
    assert created.batch_id and created.epoch_id != template.epoch_id
    assert form.parameter_fields[2].isHidden()
    form.composer.duration.setText("00:00:12")
    form.composer.batch_label.setText("Flow copies")
    form.composer.duration.editingFinished.emit()
    app.processEvents()
    assert not form.notice.text()
    assert editor.selected_paths == ((0, 3),)
    assert editor.program.sequence[0].body[:3] == original.sequence[0].body
    assert all(
        n.duration.duration.seconds == "12" for n in editor.program.sequence[0].body[3:]
    )
    assert len({n.batch_id for n in editor.program.sequence[0].body[3:]}) == 1
    applied = editor.program
    editor.undo()
    assert len(editor.program.sequence[0].body) == 4
    editor.undo(True)
    assert editor.program == applied
    form.composer.duration.setText("invalid")
    form.composer.duration.editingFinished.emit()
    app.processEvents()
    assert editor.program == applied
    form.notice.clear()
    editor.undo()
    path = tmp_path / "unified.json"
    window.protocol.save_program(str(path))
    loaded = parse_program_json(path.read_text(), max_bytes=1_048_576)
    assert loaded == applied
    editor.set_program(loaded)
    editor.enter_group()
    editor.select_epochs(((0, 3),))
    assert form.parameter_fields[2].isHidden()
    assert form.summary.isHidden()
    assert form.composer.batch_label.text() == "Flow copies"
    for width in (1280, 720):
        window.resize(width, 1100)
        app.processEvents()
        assert form.isVisible()
        assert form.add_button.isHidden()
        assert not hasattr(form, "reset")
        contents = editor.hierarchy.contents
        assert not contents.show_details
        assert contents.scrollbar.geometry().bottom() < contents.height()
        assert form.composer.rows["Left"].isVisible()
        assert window.protocol.config_scroll.horizontalScrollBar().maximum() == 0
    window.apply_view(review_view(Phase.RUNNING))
    before = editor.program
    form.apply()
    editor.add_subgroup()
    assert editor.program == before


def test_unified_subgroup_patch_preserves_variants_and_shared_sources():
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.subgroup_operations import update_subgroup
    from cephvr.gui.subgroup_structure import edit_subgroup

    source = review_program()
    epoch = source.sequence[1]
    data = source.model_dump(mode="json")
    data["sequence"] = [epoch.model_dump(mode="json") for _ in range(3)]
    for i, e in enumerate(data["sequence"]):
        e["epoch_id"] = f"Flow_{i}"
        e["batch_id"] = "batch_flow"
        e["settings"][0]["contrast"]["value"] = (i + 1) / 3
    program = grouped_program(validate(data))
    paths = ((0, 0), (0, 1))
    before = program.model_copy(update={"sequence": (program.sequence[0].body[0],)})
    edit = before.model_dump(mode="json")
    edit["sequence"][0]["settings"][0]["reset"] = False
    from cephvr.visual_stimulus.config.models.program_model import Epoch

    reference = before.model_copy(
        update={
            "sequence": (
                Epoch.model_validate_json(
                    __import__("json").dumps(edit["sequence"][0])
                ),
            )
        }
    )
    changed, selected = update_subgroup(program, paths, before, reference, 2)
    assert selected == paths
    for old, new in zip(
        program.sequence[0].body[:2], changed.sequence[0].body[:2], strict=True
    ):
        assert old.epoch_id == new.epoch_id
        assert old.settings[0].instance_id == new.settings[0].instance_id
        assert old.settings[0].contrast == new.settings[0].contrast
        assert new.settings[0].reset is False
    assert changed.sequence[0].body[2] == program.sequence[0].body[2]
    copied, selected = edit_subgroup(changed, paths, "duplicate")
    assert len(selected) == 2
    assert copied.sequence[0].body[2].batch_id != "batch_flow"
    moved, selected = edit_subgroup(copied, selected, "earlier")
    assert selected == ((0, 0), (0, 1))
    removed, _ = edit_subgroup(moved, selected, "remove")
    assert removed.sequence == changed.sequence


def test_unified_subgroup_preserves_projector_variants_and_guards_drafts(window):
    from cephvr.gui.program_editing import validate
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program

    data = review_program().model_dump(mode="json")
    source = data["sequence"][1]
    import copy

    data["sequence"] = [copy.deepcopy(source) for _ in range(3)]
    for i, epoch in enumerate(data["sequence"]):
        epoch.update(epoch_id=f"Flow_{i}", batch_id="shared_batch")
        epoch["duration"]["duration"]["seconds"] = "60"
        epoch["settings"][0]["contrast"]["value"] = (i + 1) / 4
    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(grouped_program(validate(data)))
    editor.enter_group()
    editor.select_epochs(((0, 0), (0, 1), (0, 2)))
    form = editor.subgroup
    parameters = form.composer.rows["Left"].parameters
    parameters.retain.setChecked(True)
    parameters.mark_changed()
    form.apply()
    assert not form.notice.text()
    for i, epoch in enumerate(editor.program.sequence[0].body):
        left = epoch.settings[layers_for(editor.program, epoch, "Left")[0]]
        right = epoch.settings[layers_for(editor.program, epoch, "Right")[0]]
        assert left.reset is False and right.reset is True
        assert left.contrast.value == right.contrast.value == (i + 1) / 4
    form.composer.duration.setText("00:01:05")
    editor.add_subgroup()
    assert editor.selected_paths == ((0, 3),)
    body = editor.program.sequence[0].body
    assert all(epoch.duration.duration.seconds == "65" for epoch in body)
    assert body[3].batch_id != body[0].batch_id
    assert form.repetitions.text() == "1"
    saved = editor.program
    form.composer.duration.setText("invalid")
    editor.add_subgroup()
    editor.select_epochs(((0, 0),))
    assert editor.program == saved and editor.selected_paths == ((0, 3),)
    assert form.composer.duration.text() == "invalid"
    form.discard()
    editor.select_epochs(((0, 0),))
    assert editor.path == (0, 0)


def test_unified_subgroup_duration_preserves_each_fade_and_batch_identity():
    import copy
    import json

    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.stimulus_fades import envelope, fade_values, retime_fades
    from cephvr.gui.subgroup_operations import update_subgroup
    from cephvr.gui.subgroup_structure import edit_subgroup
    from cephvr.visual_stimulus.config.models.program_model import Epoch

    data = review_program().model_dump(mode="json")
    source = data["sequence"][1]
    data["sequence"] = [copy.deepcopy(source) for _ in range(3)]
    for i, epoch in enumerate(data["sequence"]):
        epoch.update(epoch_id=f"Fade_{i}", batch_id=f"batch_{i}")
        epoch["duration"]["duration"]["seconds"] = str(60 + i * 10)
        epoch["settings"][0]["opacity"] = envelope(
            (i + 1) * 1_000_000_000, 2_000_000_000, 1, (60 + i * 10) * 1_000_000_000
        )
    program = grouped_program(validate(data))
    before = program.model_copy(update={"sequence": (program.sequence[0].body[0],)})
    edited = before.sequence[0].model_dump(mode="json")
    edited["duration"]["duration"]["seconds"] = "80"
    retime_fades(edited["settings"], 60_000_000_000, 80_000_000_000)
    reference = before.model_copy(
        update={"sequence": (Epoch.model_validate_json(json.dumps(edited)),)}
    )
    paths = ((0, 0), (0, 1), (0, 2))
    result, _ = update_subgroup(program, paths, before, reference, 3)
    for i, epoch in enumerate(result.sequence[0].body):
        assert epoch.batch_id == f"batch_{i}"
        assert epoch.duration.duration.seconds == "80"
        assert fade_values(
            epoch.settings[0].opacity.model_dump(mode="json"), 80_000_000_000
        )[:2] == ((i + 1) * 1_000_000_000, 2_000_000_000)
    with pytest.raises(ValueError, match="one subgroup"):
        update_subgroup(program, paths, before, reference, 4)
    duplicate, copied_paths = edit_subgroup(result, paths, "duplicate")
    assert len({duplicate.sequence[0].body[p[-1]].batch_id for p in copied_paths}) == 3
    assert not {duplicate.sequence[0].body[p[-1]].batch_id for p in copied_paths} & {
        "batch_0",
        "batch_1",
        "batch_2",
    }
    moved, selected = edit_subgroup(result, ((0, 0),), "later")
    assert selected == ((0, 1),)
    restored, _ = edit_subgroup(moved, selected, "earlier")
    assert restored == result


def test_unified_subgroup_asset_edit_is_projector_local_and_atomic(window, tmp_path):
    import copy

    from PyQt6.QtGui import QImage

    from cephvr.gui.program_editing import validate
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus

    for name in ("image.png", "replacement.png"):
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(0)
        assert image.save(str(tmp_path / name))
    source = add_stimulus(blank_program(), 0, "Image", ("Left", "Right"))
    data = source.model_dump(mode="json")
    data["sequence"] = [copy.deepcopy(data["sequence"][0]) for _ in range(3)]
    for i, epoch in enumerate(data["sequence"]):
        epoch.update(epoch_id=f"Image_{i}", batch_id="image_batch")
    original = grouped_program(validate(data))
    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(original)
    editor.enter_group()
    editor.select_epochs(((0, 0), (0, 1)))
    form = editor.subgroup
    composer = form.composer
    composer.set_asset_root(str(tmp_path))
    left = composer.rows["Left"].parameters
    left.set_media_path(next(iter(left.asset_forms)), str(tmp_path / "replacement.png"))
    right = composer.rows["Right"].parameters
    right.fades.fade_in.setText("-1")
    right.fades.mark_changed()
    form.apply()
    assert form.notice.text() and editor.program == original
    right.fades.fade_in.setText("0")
    right.fades.mark_changed()
    form.apply()
    assert not form.notice.text()
    program = editor.program
    assets = {asset.asset_id: asset.logical_path for asset in program.assets}
    for epoch in program.sequence[0].body:
        left_layer = epoch.settings[layers_for(program, epoch, "Left")[0]]
        right_layer = epoch.settings[layers_for(program, epoch, "Right")[0]]
        assert assets[left_layer.asset_id] == "replacement.png"
        assert assets[right_layer.asset_id] == "image.png"
    assert len(editor.selected_paths) == 3
    editor.undo()
    assert editor.program == original


def test_direct_group_editor_starts_open_and_uses_only_group_repetitions(
    window, app, tmp_path
):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_snapshot import (
        capture_protocol,
        restore_protocol,
        validate_protocol,
    )
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(grouped_program(blank_program()))
    assert editor.path == (0, 0) and editor.subgroup.isVisible()
    assert not hasattr(editor, "back_button") and not hasattr(editor, "breadcrumb")
    assert not hasattr(editor, "shuffle_trial_button")
    editor.subgroup.composer.duration.setText("00:00:01")
    editor.group_editor.repetitions.setText("300")
    editor.group_editor.mark_changed()
    assert editor.group_editor.apply()
    assert editor.subgroup.composer.duration.text() == "00:00:01"
    editor.subgroup.apply()
    editor.hierarchy.contents.block_actions.add.click()
    assert editor.path == (0, 1)
    assert len(editor.program.sequence[0].body) == 2
    assert (
        len(expand_program(editor.program, seed_decimal="0", max_expanded_epochs=1000))
        == 600
    )
    assert editor.subgroup.parameter_fields[2].isHidden()
    assert editor.subgroup.summary.isHidden()
    assert editor.group_editor.summary.isHidden()
    assert not editor.hierarchy.contents.toolTip()
    assert editor.hierarchy.contents_title.text() == "Epochs"
    saved = capture_protocol(window.protocol)
    editor.add_trial()
    assert editor.path == (0, 0)
    restore_protocol(window.protocol, validate_protocol(saved))
    assert editor.path == (0, 0) and editor.subgroup.isVisible()
    for width in (1280, 720):
        window.resize(width, 1100)
        app.processEvents()
        for control in (editor.output_preview_button,):
            assert (
                control.isVisible()
                and control.width() >= control.minimumSizeHint().width()
            )
        assert window.protocol.config_scroll.horizontalScrollBar().maximum() == 0


def test_demo_assets_can_be_selected_and_review_path_restores(window, demo_assets):
    import json

    from PyQt6.QtGui import QImage

    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_files import resolve_stimulus_file

    root = demo_assets
    manifest = json.loads((root / "manifest.json").read_text())
    for path in manifest["images"]:
        assert not QImage(str(root / path)).isNull()
        assert (
            resolve_stimulus_file(str(root), str(root / path), texture=False).path
            == path
        )
    for path in manifest["textures"]:
        selected = resolve_stimulus_file(str(root), str(root / path), texture=True)
        assert selected.tile_width_mm == selected.tile_height_mm == 40
        assert selected.path == path
        assert selected.profile == "cephvr1_texture_json_v1"
        recipe = json.loads((root / selected.path).read_text())
        assert recipe["pattern"] == "image"
        assert not QImage(
            str((root / path).parent / recipe["params"]["texture_path"])
        ).isNull()
    editor = window.protocol.editor
    editor.set_program(grouped_program(blank_program()))
    editor.timeline.set_screens(("Left",))
    window.protocol.assets.folders["root"].editor.setText(str(root))
    form = editor.subgroup
    form.composer.add_file("Texture", str(root / manifest["textures"][0]), "Left")
    form.apply()
    assert not form.notice.text()
    assert editor.program.assets[0].logical_path == "textures/checkerboard.texture.json"


@pytest.mark.parametrize("sample", [False, True])
def test_empty_variation_blocks_add_group_without_losing_draft(window, app, sample):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program, review_program

    editor = window.protocol.editor
    window.page_buttons[1].click()
    editor.set_program(grouped_program(review_program() if sample else blank_program()))
    form = editor.subgroup
    form.add_variation()
    app.processEvents()
    row = form.rows[0]
    assert row.values.text() == ""
    row.values.setFocus()
    app.processEvents()
    before = editor.snapshot()
    QTest.mouseClick(editor.timeline.block_actions.add, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert editor.snapshot() == before
    assert form.rows == [row] and form.dirty
    assert form.notice.dialog is not None
    form.notice.dialog.accept()
    app.processEvents()
    row.remove.click()
    app.processEvents()
    editor.timeline.block_actions.add.click()
    assert len(editor.program.sequence) == len(before.program.sequence) + 1


def test_subgroup_rules_persist_and_random_projectors_are_independent(
    window, app, demo_assets
):
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(grouped_program(blank_program()))
    editor.group_editor.repetitions.setText("3")
    editor.group_editor.mark_changed()
    assert editor.group_editor.apply()
    form = editor.subgroup
    root = demo_assets
    form.composer.set_asset_root(str(root))
    for face in ("Left", "Right"):
        form.composer.add_file("Texture", str(root / "textures/checkerboard.png"), face)
    form.add_variation()
    row = form.rows[0]
    row.target.setCurrentIndex(row.target.findText("All projectors"))
    row.parameter.setCurrentIndex(row.parameter.findData("Speed"))
    row.values.setText("10,20,30")
    row.values.editingFinished.emit()
    app.processEvents()
    assert not form.notice.text()
    assert len(form.paths) == 3
    assert not form.dirty
    assert form.rows and form.rows[0].values.text() == "10,20,30"
    editor.select_epochs(((0, 2),))
    assert len(form.paths) == 3
    row = form.rows[0]
    row.method.setCurrentText("Random")
    row.random_fields["maximum"].setText("1000000")
    row.random.seed(42)
    row.random_cache = None
    form.apply()
    assert not form.notice.text() and not form.dirty
    first = editor.program
    assert len(first.sequence[0].body) == 3

    def speeds(program, face):
        return [
            motion_numbers(
                e.settings[layers_for(program, e, face)[0]].model_dump(mode="json")
            )[0]
            for e in program.sequence[0].body
        ]

    assert speeds(first, "Left") != speeds(first, "Right")
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    expanded = expand_program(first, seed_decimal="1", max_expanded_epochs=100)
    assert len(expanded) == 9
    assert expanded[0].settings != expanded[3].settings != expanded[6].settings
    assert all(
        e.repetition_rules and not e.repetition_settings for e in first.sequence[0].body
    )
    assert expand_program(first, seed_decimal="2", max_expanded_epochs=100) == expanded
    form.apply()
    assert editor.program == first
    restored = parse_program_json(first.model_dump_json(), max_bytes=1048576)
    editor.set_program(restored)
    assert form.rows and form.rows[0].method.currentText() == "Random"
    assert not form.dirty
    form.remove_variation(form.rows[0])
    form.apply()
    assert not form.notice.text() and not form.rows
    assert all(not e.repetition_rules for e in editor.program.sequence[0].body)
    editor.undo()
    assert editor.program == restored and len(form.rows) == 1
    form.composer.duration.setText("00:00:30")
    form.apply()
    assert not form.notice.text()
    assert all(
        e.duration.duration.ns() == 30_000_000_000
        for e in editor.program.sequence[0].body
    )
    assert speeds(editor.program, "Left") == speeds(first, "Left")
    assert [e.repetition_settings for e in editor.program.sequence[0].body] == [
        e.repetition_settings for e in first.sequence[0].body
    ]
    form.rows[0].shared.setChecked(True)
    form.apply()
    assert not form.notice.text()
    assert speeds(editor.program, "Left") == speeds(editor.program, "Right")
    editor.undo()
    assert not form.rows[0].shared.isChecked()
    assert speeds(editor.program, "Left") == speeds(first, "Left")

    editor.group_editor.repetitions.setText("5")
    editor.group_editor.mark_changed()
    assert editor.group_editor.apply()
    assert all(
        e.repetition_rules and not e.repetition_settings
        for e in editor.program.sequence[0].body
    )
    assert (
        len(expand_program(editor.program, seed_decimal="1", max_expanded_epochs=100))
        == 15
    )
    assert form.rows[0].method.currentText() == "Random"
    assert not form.dirty

    editor.add_subgroup()
    assert len(form.paths) == 1 and not form.rows
    added = editor.program.sequence[0].body[-1]
    assert added.subgroup_draft is None and not added.repetition_settings
    form.add_variation()
    form.rows[0].method.setCurrentText("Random")
    form.rows[0].random_fields["minimum"].setText("2000001")
    form.rows[0].random_fields["maximum"].setText("3000000")
    form.apply()
    assert not form.notice.text()
    drafts = [e.subgroup_draft for e in editor.program.sequence[0].body]
    editor.select_epochs(((0, 0), (0, 3)))
    form.composer.duration.setText("00:00:20")
    form.apply()
    assert not form.notice.text()
    assert [e.subgroup_draft for e in editor.program.sequence[0].body] == drafts
    assert all(
        e.duration.duration.ns() == 20_000_000_000
        for e in editor.program.sequence[0].body
    )
    # Rules belong to one batch identity: a mixed selection rejects them and keeps the edit.
    mixed = editor.program
    form.rows[0].random_fields["maximum"].setText("3000001")
    form.rows[0].random_fields["maximum"].editingFinished.emit()
    form.apply()
    assert "one subgroup" in form.notice.text()
    assert editor.program == mixed and form.dirty
    form.discard()
    assert not form.dirty and form.notice.dialog is None

    editor.select_epochs(((0, 0),))
    saved = editor.program
    form.rows[0].random_fields["minimum"].setText("not a number")
    form.rows[0].random_fields["minimum"].editingFinished.emit()
    app.processEvents()
    assert editor.program == saved and form.dirty
    assert not form.update_timer.isActive()
    assert form.notice.dialog is None


def test_large_random_group_stays_compact_and_layer_controls_are_indices(
    window, app, demo_assets
):
    from unittest.mock import patch

    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.repetition_values import resolve_repetition

    editor = window.protocol.editor
    window.page_buttons[1].click()
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(grouped_program(blank_program()))
    form = editor.subgroup
    root = demo_assets
    form.composer.set_asset_root(str(root))
    for face in ("Left", "Right"):
        form.composer.add_file("Texture", str(root / "textures/checkerboard.png"), face)
    form.add_variation()
    row = form.rows[0]
    row.target.setCurrentIndex(row.target.findText("All projectors"))
    row.method.setCurrentText("Random")
    row.random_fields["maximum"].setText("1000000")
    form.apply()
    assert not form.notice.text() and not form.dirty
    small = editor.program
    initial_rules = small.sequence[0].body[0].repetition_rules
    for repetitions in (10000, 1000000):
        with patch(
            "cephvr.gui.subgroup_repetitions.resolve_repetition",
            wraps=resolve_repetition,
        ) as sampled:
            editor.group_editor.repetitions.setText(str(repetitions))
            editor.group_editor.mark_changed()
            assert editor.group_editor.apply()
            assert sampled.call_count == 1
        app.processEvents()
        program = editor.program
        epoch = program.sequence[0].body[0]
        assert epoch.repetition_rules == initial_rules
        assert len(program.model_dump_json()) < len(small.model_dump_json()) + 128
        assert not epoch.repetition_settings
        assert len(editor.hierarchy.contents.nodes) == len(editor.timeline.nodes) == 1
        assert resolve_repetition(
            epoch.settings, epoch.repetition_rules, repetitions - 1
        ) != resolve_repetition(epoch.settings, epoch.repetition_rules, 0)
        assert not form.dirty
    assert not hasattr(editor.group_editor, "order")
    for row in form.composer.rows.values():
        if row.face:
            assert row.layer.itemText(0) == "1" and row.layer.maximumWidth() <= 72
    assert form.rows[0].layer.itemText(0) == "1"
    assert form.rows[0].layer.minimumWidth() == 64
    assert " s" not in editor.sequence_summary.text()
    assert ":" in editor.sequence_summary.text()


def test_inline_timeline_actions_target_blocks_append_and_preserve_undo(window, app):
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QPushButton

    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    data = grouped_program(review_program()).model_dump(mode="json")
    data["sequence"][0]["repetitions"] = 10
    for epoch in data["sequence"][0]["body"][:2]:
        epoch["batch_id"] = "batch_pair"
    editor.set_program(validate(data))
    window.resize(1280, 1100)
    app.processEvents()
    contents = editor.hierarchy.contents
    before = editor.program
    assert not any(
        control.text() in ("+ Group", "− Group", "+ Epoch")
        for control in editor.findChildren(QPushButton)
    )
    # Selection alone has no cross; hovering reveals a standard compact control.
    QTest.mouseMove(editor.group_editor.name)
    app.processEvents()
    assert not any(c.isVisible() for c in contents.block_actions.removers)
    _move_mouse_and_wait_for_native_event(
        contents, contents.batch_hits[0][0].center().toPoint(), app
    )
    # One cross removes the complete selected batch, preserving the remaining source.
    remove = next(c for c in contents.block_actions.removers if c.isVisible())
    assert remove.property("role") == "compact" and not remove.styleSheet()
    assert remove.property("paths") == ((0, 0), (0, 1))
    assert remove.isEnabled()
    assert not editor.subgroup.dirty
    QTest.mouseClick(remove, Qt.MouseButton.LeftButton)
    assert len(editor.program.sequence[0].body) == 1, editor.feedback.text()
    editor.undo()
    assert editor.program == before
    app.processEvents()
    QTest.mouseClick(contents.block_actions.add, Qt.MouseButton.LeftButton)
    assert editor.path == (0, 3)
    assert len(editor.program.sequence[0].body) == 4
    # Add always appends, even when an earlier group is selected.
    editor.timeline.block_actions.add.click()
    editor.timeline.choose(0, Qt.KeyboardModifier.NoModifier)
    editor.timeline.block_actions.add.click()
    assert editor.path == (2, 0) and len(editor.program.sequence) == 3
    app.processEvents()
    timeline = editor.timeline
    first_rect = next(rect for rect, i, _, _ in timeline.hits if i == 0)
    _move_mouse_and_wait_for_native_event(timeline, first_rect.center().toPoint(), app)
    remove = next(
        c
        for c in timeline.block_actions.removers
        if c.isVisible() and c.property("paths") == ((0,),)
    )
    before_delete = editor.program
    QTest.mouseClick(remove, Qt.MouseButton.LeftButton)
    assert editor.program.sequence == before_delete.sequence[1:]
    editor.undo()
    assert editor.program == before_delete
    # A bad draft must block deletion without changing document or selection.
    app.processEvents()
    editor.subgroup.composer.duration.setText("invalid")
    snapshot = editor.snapshot()
    editor.remove_block(((0,),))
    assert editor.snapshot() == snapshot
    editor.subgroup.discard()
    editor.setEnabled(False)
    editor.remove_block(((0,),))
    editor.timeline.block_actions.add.click()
    assert editor.program == before_delete
    editor.setEnabled(True)
    # Trailing plus remains reachable after horizontal scrolling.
    for _ in range(8):
        editor.add_group()
    app.processEvents()
    timeline.scrollbar.setValue(timeline.scrollbar.maximum())
    app.processEvents()
    assert timeline.block_actions.add.isVisible()
    assert timeline.rect().contains(timeline.block_actions.add.geometry())
    assert (
        len(timeline.block_actions.removers) <= 9
    )  # Only visible blocks allocate controls.


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_trial_row_actions_scroll_target_and_align_cards(window, app, style):
    from PyQt6.QtWidgets import QMessageBox

    window.appearance.select(style)
    window.page_buttons[1].click()
    editor = window.protocol.editor
    open_protocol_group(editor)
    trials = editor.trials
    editor.drafts[editor.index].name = "Primate - Part 1 of 2 (10 minutes)"
    trials.item(editor.index).setText(editor.drafts[editor.index].name)
    window.resize(1280, 1100)
    app.processEvents()
    assert editor.trial_card.height() == editor.timeline_card.height()
    for card, controls in (
        (editor.trial_card, (editor.trial_card.caption, trials)),
        (
            editor.timeline_card,
            (
                editor.timeline_card.caption,
                editor.timeline,
                editor.group_editor,
                editor.output_preview_button,
                editor.sequence_summary,
            ),
        ),
    ):
        assert all(
            card.rect().contains(
                control.rect().translated(control.mapTo(card, QPoint()))
            )
            for control in controls
        )
    assert editor.selected_group_label.text() == "Selected group"
    assert editor.group_editor.parentWidget() is editor.timeline_card
    assert editor.sequence_summary.geometry().bottom() < editor.timeline.y()
    assert editor.group_editor.y() > editor.timeline.geometry().bottom()
    last_right = (
        editor.timeline.x()
        + len(editor.timeline.nodes) * editor.timeline.block_width()
        - 7
    )
    assert abs(editor.group_editor.geometry().right() + 1 - last_right) <= 1
    QTest.mouseMove(editor.group_editor.name)
    app.processEvents()
    remove = next(c for c in trials.removers if c.isVisible())
    assert remove.property("trial_row") == editor.index
    assert trials.viewport().rect().contains(remove.geometry())
    assert not remove.visibleRegion().isEmpty()
    QTest.mouseClick(remove, Qt.MouseButton.LeftButton)
    assert editor.drafts[editor.index].name in editor.delete_dialog.text()
    editor.delete_dialog.button(QMessageBox.StandardButton.Cancel).click()
    assert not hasattr(editor, "delete_trial_button")
    assert trials.add.height() == trials.visualItemRect(trials.item(0)).height()
    assert trials.add.y() > trials.visualItemRect(trials.item(0)).bottom()
    QTest.mouseClick(trials.add, Qt.MouseButton.LeftButton)
    editor.add_trial()
    assert editor.index == 2
    app.processEvents()
    rect = trials.visualItemRect(trials.item(0))
    _move_mouse_and_wait_for_native_event(trials.viewport(), rect.center(), app)
    remove = next(
        c for c in trials.removers if c.isVisible() and c.property("trial_row") == 0
    )
    selected = editor.drafts[2]
    QTest.mouseClick(remove, Qt.MouseButton.LeftButton)
    assert editor.drafts[0].name in editor.delete_dialog.text()
    editor.delete_dialog.button(QMessageBox.StandardButton.Cancel).click()
    assert editor.drafts[editor.index] is selected and len(editor.drafts) == 3
    remove.click()
    editor.delete_dialog.button(QMessageBox.StandardButton.Yes).click()
    assert editor.drafts[editor.index] is selected and len(editor.drafts) == 2
    for _ in range(8):
        editor.add_trial()
    for width in (1280, 720):
        window.resize(width, 1100)
        QTest.qWait(30)
        app.processEvents()
        trials.verticalScrollBar().setValue(trials.verticalScrollBar().maximum())
        app.processEvents()
        assert trials.add.isVisible()
        assert trials.viewport().rect().contains(trials.add.geometry())
        assert (
            trials.add.y()
            > trials.visualItemRect(trials.item(trials.count() - 1)).bottom()
        )
        assert editor.trial_card.y() == editor.timeline_card.y()
        assert (
            editor.trial_card.caption.geometry().center().y()
            == editor.timeline_card.caption.geometry().center().y()
        )
        assert editor.trial_card.height() == editor.timeline_card.height()
        assert window.protocol.config_scroll.horizontalScrollBar().maximum() == 0
    previous = len(editor.drafts)
    QTest.mouseClick(trials.add, Qt.MouseButton.LeftButton)
    assert len(editor.drafts) == previous + 1 and editor.index == previous
    editor.setEnabled(False)
    trials.add.click()
    editor.delete_trial(0)
    assert len(editor.drafts) == previous + 1 and editor.delete_dialog is None


def test_texture_recipe_file_selection_preserves_original_json(tmp_path: Path) -> None:
    import json

    from cephvr.gui.stimulus_files import resolve_stimulus_file

    design = tmp_path / "legacy.JSON"
    design.write_text(
        json.dumps(
            {
                "pattern": "substrate",
                "pattern_params": {"seed": 5},
                "preview_file": "absent.png",
            }
        )
    )
    selected = resolve_stimulus_file(str(tmp_path), str(design), texture=True)
    assert selected.path == "legacy.JSON"
    assert selected.profile == "cephvr1_texture_json_v1"
    assert selected.tile_width_mm is None
    with pytest.raises(ValueError, match="only"):
        resolve_stimulus_file(str(tmp_path), str(design), texture=False)
    design.write_text('{"kind":"arena","pattern":"checker"}')
    with pytest.raises(ValueError, match="texture"):
        resolve_stimulus_file(str(tmp_path), str(design), texture=True)
    outside = tmp_path.parent / "outside.JSON"
    with pytest.raises(ValueError):
        resolve_stimulus_file(str(tmp_path), str(outside), texture=True)


def test_texture_reference_link_keeps_appearance_and_disables_reparented_motion(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.reference_fields import reference_fields
    from cephvr.gui.stimulus_parameters import StimulusParameters
    from cephvr.gui.stimulus_presets import add_stimulus

    program = add_stimulus(blank_program(), 0, "Texture", ("Bottom",))
    program = add_stimulus(program, 0, "Texture", ("Left",))
    source, target = program.sequence[0].settings
    panel = StimulusParameters(compact=True)
    panel.setParent(window)
    panel.bind(program, 0, 1, "Left")
    assert panel.linked_to.isEnabled()
    assert not any(
        "initial" in getattr(form, "children_by_key", {}) for form in panel.forms
    )
    panel.linked_to.setCurrentIndex(panel.linked_to.findData(source.instance_id))
    reference_fields(panel)
    motion = next(f for f in panel.forms if isinstance(f, EpochMotion))
    assert not motion.speed.isEnabled() and not motion.angular.isEnabled()
    assert panel.apply(), panel.message.text()
    linked = panel.program.sequence[0].settings[1]
    assert linked.linked_to == source.instance_id
    assert linked.pattern == target.pattern and linked.initial == target.initial
    assert linked.phase_x.kind == linked.phase_y.kind == "hold"
    assert linked.reset == target.reset
    panel.bind(panel.program, 0, 1, "Left")
    assert panel.linked_to.currentData() == source.instance_id
    panel.linked_to.setCurrentIndex(0)
    reference_fields(panel)
    motion = next(f for f in panel.forms if isinstance(f, EpochMotion))
    assert motion.speed.isEnabled() and motion.angular.isEnabled()
    assert panel.apply(), panel.message.text()
    assert panel.program.sequence[0].settings[1].linked_to is None


def test_epoch_automatic_updates_preserve_focus_validation_and_history(window, app):
    from PyQt6.QtWidgets import QLineEdit

    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(grouped_program(blank_program()))
    form = editor.subgroup
    original = editor.program
    form.composer.duration.setText("00:01:05")
    form.composer.duration.editingFinished.emit()
    app.processEvents()
    changed = editor.program
    assert changed != original
    assert not form.dirty
    assert changed.sequence[0].body[0].duration.duration.seconds == "65"
    form.composer.batch_label.setFocus()
    form.composer.batch_label.setText("Updated epoch")
    form.composer.batch_label.editingFinished.emit()
    app.processEvents()
    assert app.focusWidget() is form.composer.batch_label
    assert isinstance(app.focusWidget(), QLineEdit)
    assert editor.program.sequence[0].body[0].batch_label == "Updated epoch"
    editor.undo()
    assert editor.program == changed
    editor.undo(True)
    saved = editor.program
    form.composer.duration.setText("invalid")
    form.composer.duration.editingFinished.emit()
    app.processEvents()
    assert editor.program == saved and form.dirty
    assert form.notice.text() and form.notice.dialog is None
    form.composer.duration.setText("00:01:10")
    form.composer.duration.editingFinished.emit()
    app.processEvents()
    assert not form.dirty and not form.notice.text()
    assert editor.program.sequence[0].body[0].duration.duration.seconds == "70"


@pytest.mark.parametrize("view", ["reference_bars", "frame_grid", ""])
def test_active_calibration_measurements_are_editable_only_for_reference_bars(
    window, view
):
    from cephvr.gui.projector_geometry import FACES

    panel = window.devices.projectors
    panel.apply_view(review_view(Phase.CONFIGURATION))
    panel.set_calibration_presentation_state(active=True, available=True, view=view)
    editable = view == "reference_bars"
    for face in FACES:
        for axis in ("x", "y"):
            assert (
                panel.measurements.fields[face, f"reference_{axis}_mm"].isEnabled()
                == editable
            )
    assert not panel.rig_editor.isEnabled() and not panel.screen_editor.isEnabled()
    assert not panel.timing.isEnabled()
    assert panel.calibration.measurement_button.isEnabled() == editable
    if editable:
        editor = panel.measurements.fields["Front", "reference_x_mm"]
        editor.clear()
        QTest.keyClicks(editor, "123.5")
        assert panel.screen_editor.drafts["Front"]["reference_x_mm"] == "123.5"
        assert (
            panel.calibration_files.calibration_snapshot()["values"][
                "screens.Front.reference_x_mm"
            ]
            == 123.5
        )
    panel.set_calibration_presentation_state(
        active=True, available=True, pending=True, view=view
    )
    assert not panel.measurements.isEnabled()
    panel.set_calibration_presentation_state(
        active=False, available=False, pending=True, view=view
    )
    assert not panel.measurements.isEnabled()
    panel.set_calibration_presentation_state(active=False, available=True)
    assert panel.measurements.isEnabled()
    panel.set_calibration_presentation_state(
        active=True, available=True, view="reference_bars"
    )
    panel.apply_view(review_view(Phase.CONFIGURATION, observer=True))
    assert not panel.measurements.isEnabled()


def test_shared_tables_tab_between_nested_editors_and_other_controls(app):
    from PyQt6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QHBoxLayout,
        QLineEdit,
        QVBoxLayout,
        QWidget,
    )

    from cephvr.gui.tables import DataTable

    host = QWidget()
    layout = QVBoxLayout(host)
    table = DataTable(2, 2)
    layout.addWidget(table)
    pair = QWidget()
    pair_layout = QHBoxLayout(pair)
    x, y = QLineEdit(), QLineEdit()
    pair_layout.addWidget(x)
    pair_layout.addWidget(y)
    choice, toggle, last = QComboBox(), QCheckBox(), QLineEdit()
    choice.addItems(["A", "B"])
    table.set_control(0, 0, pair)
    table.set_control(0, 1, choice)
    table.set_control(1, 0, toggle)
    table.set_control(1, 1, last)
    host.show()
    host.activateWindow()
    x.setFocus()
    app.processEvents()
    try:
        sequence = [x, y, choice, toggle, last]
        for current, following in zip(sequence[:-1], sequence[1:], strict=True):
            assert app.focusWidget() is current
            QTest.keyClick(current, Qt.Key.Key_Tab)
            assert app.focusWidget() is following
        for current, previous in zip(
            reversed(sequence[1:]), reversed(sequence[:-1]), strict=True
        ):
            QTest.keyClick(current, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
            assert app.focusWidget() is previous
        y.setEnabled(False)
        QTest.keyClick(x, Qt.Key.Key_Tab)
        assert app.focusWidget() is choice
    finally:
        host.close()


def test_console_tab_leaves_text_view_for_next_control(app):
    from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

    from cephvr.gui.components import Console

    host = QWidget()
    layout = QVBoxLayout(host)
    console, editor = Console(), QLineEdit()
    layout.addWidget(console)
    layout.addWidget(editor)
    host.show()
    host.activateWindow()
    console.setFocus()
    app.processEvents()
    try:
        QTest.keyClick(console, Qt.Key.Key_Tab)
        assert app.focusWidget() is editor
        QTest.keyClick(editor, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert app.focusWidget() is console
    finally:
        host.close()


def test_valid_pixels_and_axis_pitch_produce_coherent_views_across_projectors():
    import math
    from types import SimpleNamespace

    from cephvr.gui.calibration_profile import (
        AssignedDisplay,
        MonitorBinding,
        diagnostic_display_profile,
    )
    from cephvr.gui.projector_geometry import FACES
    from cephvr.visual_stimulus.rendering.arena import off_axis_view_projection
    from cephvr.visual_stimulus.rendering.layer_projection import physical_corners

    geometries = []
    matrices = []
    for native_width, native_height, pitch_x, pitch_y in (
        (1000, 600, 0.1, 0.2),
        (1920, 1080, 0.2, 0.1),
    ):
        values = dict(
            zip(
                (
                    "rig.width",
                    "rig.depth",
                    "rig.height",
                    "rig.subject_x",
                    "rig.subject_y",
                    "rig.subject_z",
                ),
                (120, 166, 110, 60, 93, 53),
                strict=True,
            )
        )
        for face in FACES:
            for key, value in dict(
                width=90,
                height=80,
                reference_width_px=native_width,
                reference_height_px=native_height,
                reference_x_px=200,
                reference_y_px=100,
                reference_x_mm=200 * pitch_x,
                reference_y_mm=100 * pitch_y,
                valid_width_px=round(80 / pitch_x),
                valid_height_px=round(40 / pitch_y),
            ).items():
                values[f"screens.{face}.{key}"] = value
            if face != "Right":
                values[f"screens.{face}.subject_distance"] = 50
        display, profiles = diagnostic_display_profile(
            {"format": "cephvr-rig-calibration", "version": 7, "values": values},
            tuple(
                AssignedDisplay(
                    f, i * native_width, 0, native_width, native_height, True
                )
                for i, f in enumerate(FACES)
            ),
            tuple(
                MonitorBinding(
                    f"interface-{i}",
                    i * native_width,
                    0,
                    native_width,
                    native_height,
                    60,
                    8,
                )
                for i in range(4)
            ),
            view="frame_grid",
        )
        geometries.append(display.geometry)
        matrices.append(
            tuple(
                off_axis_view_projection(display, surface)
                for surface in display.geometry.surfaces
            )
        )
        for surface in display.geometry.surfaces:
            extent_x, extent_y = native_width * pitch_x, native_height * pitch_y
            if surface.surface_id == "bottom":
                extent_x, extent_y = extent_y, extent_x
            assert math.dist(
                surface.bottom_left_mm, surface.bottom_right_mm
            ) == pytest.approx(extent_x)
            assert math.dist(
                surface.bottom_left_mm, surface.top_left_mm
            ) == pytest.approx(extent_y)
            corners = physical_corners(
                SimpleNamespace(display=display),
                SimpleNamespace(
                    state=(("width", 20), ("height", 10), ("x", 0), ("y", 0))
                ),
                surface.surface_id,
                SimpleNamespace(matrix=((1, 0, 0), (0, 1, 0))),
            )
            mesh = profiles[surface.surface_id]
            output_span_x = (
                mesh.vertices[1].xy[0] - mesh.vertices[0].xy[0]
            ) * native_width
            output_span_y = (
                mesh.vertices[2].xy[1] - mesh.vertices[0].xy[1]
            ) * native_height
            span_x, span_y = output_span_x * pitch_x, output_span_y * pitch_y
            if surface.surface_id == "bottom":
                span_x, span_y = span_y, span_x
            assert (corners[1][0] - corners[0][0]) / 2 * span_x == pytest.approx(20)
            assert (corners[3][1] - corners[0][1]) / 2 * span_y == pytest.approx(10)
    assert geometries[0] != geometries[1]
    assert matrices[0] != matrices[1]


@pytest.mark.parametrize(
    ("legacy", "shared", "expected"),
    [
        ("retro_console", None, "retro_console"),
        ("retro_console", "standard", "standard"),
        ("standard", "retro_console", "retro_console"),
        ("retro_console", "unknown", "standard"),
        ("standard", "amber_phosphor", "amber_phosphor"),
    ],
)
def test_managed_appearance_restores_shared_or_legacy_preference(
    app: QApplication, tmp_path: Path, legacy: str, shared: str | None, expected: str
) -> None:
    from cephvr.gui.managed_window import ManagedDashboardWindow

    settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    settings.setValue("review/appearance", legacy)
    if shared is not None:
        settings.setValue("appearance/style", shared)
    window = ManagedDashboardWindow(settings=settings)
    try:
        assert window.appearance.name == expected
        assert window.appearance.actions[expected].isChecked()
        assert window.property("retroConsole") == (expected != "standard")
        assert window.property("retroPalette") == (
            None if expected == "standard" else expected
        )
        assert settings.value("review/appearance") == legacy
        assert settings.value("appearance/style") == shared
    finally:
        window.tracking.annotation.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_retro_family_switch_repaints_with_owning_palette(
    app: QApplication, tmp_path: Path
) -> None:
    from cephvr.gui.components import Button, StatusColumn
    from cephvr.gui.managed_window import ManagedDashboardWindow
    from cephvr.gui.retro_instruments import TabBrackets
    from cephvr.gui.theme import (
        COLORS,
        PHOSPHOR_COLORS,
        RETRO_COLORS,
        colors_for,
        suggestion_popup_stylesheet,
    )

    settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    other = QSettings(str(tmp_path / "other.ini"), QSettings.Format.IniFormat)
    phosphor = ManagedDashboardWindow(settings=settings)
    retro = ManagedDashboardWindow(settings=other)
    try:
        retro.appearance.select("retro_console")
        for name, expected in (
            ("amber_phosphor", PHOSPHOR_COLORS),
            ("retro_console", RETRO_COLORS),
            ("amber_phosphor", PHOSPHOR_COLORS),
        ):
            phosphor.appearance.select(name)
            assert phosphor.appearance.actions[name].isChecked()
            assert phosphor.property("retroConsole") is True
            assert phosphor.appearance.brand.text() == "CEPHVR"
            for page in (phosphor.dashboard, phosphor.protocol, phosphor.devices):
                assert colors_for(page) == expected
            assert expected.accent in phosphor.dashboard.styleSheet()
            assert expected.window in suggestion_popup_stylesheet(
                phosphor.dashboard.subject_id
            )
            # A second window keeps its own Retro-family palette.
            assert colors_for(retro.dashboard) == RETRO_COLORS
            phosphor_style = name == "amber_phosphor"
            caption = phosphor.dashboard.session_controls.caption.text()
            assert caption == (
                "< SYSTEM CONTROLS >" if phosphor_style else "SYSTEM CONTROLS"
            )
            heading = phosphor.recordings.data_heading
            assert heading.text() == ("/// DATA \\\\\\" if phosphor_style else "Data")
            assert phosphor.page_header.isHidden() == phosphor_style
            appearance = phosphor.appearance
            unit = next(
                caption
                for caption, text in appearance.field_labels.items()
                if "(mA)" in text
            )
            assert ("(mA)" in unit.text()) and (
                unit.text().startswith("RGB LED CURRENT") == phosphor_style
            )
            nested = [
                card for card in appearance.card_titles if card.property("nestedCard")
            ]
            assert nested and all(
                card.caption.text().startswith("///") == phosphor_style
                for card in nested
            )
            assert phosphor.devices.tab_bar.findChild(TabBrackets) is not None
            centred = (
                phosphor.appearance.brand.alignment() & Qt.AlignmentFlag.AlignHCenter
            )
            assert bool(centred) == phosphor_style
            status = phosphor.findChild(StatusColumn)
            assert status is not None
            assert status.hud_card.property("openFrame") is True
            assert status.log_card.property("openFrame") is True
            log = status.console
            assert log.column_header.isHidden() != phosphor_style
            assert (log.header_height > 0) == phosphor_style
            nav = next(item for item in phosphor.page_buttons if item.isChecked())
            assert isinstance(nav, Button)
            assert nav.retro_label() == (
                f"> {nav.text()} <" if phosphor_style else f"> {nav.text()}"
            )
        assert settings.value("appearance/style") == "amber_phosphor"
        phosphor.appearance.select("standard")
        assert colors_for(phosphor.dashboard) == COLORS
        assert phosphor.property("retroPalette") is None
    finally:
        for window in (phosphor, retro):
            window.tracking.annotation.close()
            window.hide()
            window.deleteLater()
        app.processEvents()


def test_log_wrap_hangs_under_message_column_and_round_trips() -> None:
    from cephvr.gui.log_wrap import LINE_SEPARATOR, unwrap_row, wrap_row

    row = "21:57:11  [GUI]       Local review draft restored;  no controller applied."
    wrapped = wrap_row(row, 40, 22)
    lines = wrapped.split(LINE_SEPARATOR)
    assert len(lines) > 1 and all(len(line) <= 40 for line in lines)
    assert all(
        line.startswith(" " * 22) and line[22] != " " or line.startswith(" " * 23)
        for line in lines[1:]
    )
    assert unwrap_row(wrapped, 22) == row
    assert wrap_row(row, 200, 22) == row
    assert wrap_row("x" * 60, 40, 22) == "x" * 60


def test_phosphor_log_wraps_for_display_only(app: QApplication) -> None:
    from cephvr.gui.components import LogConsole
    from cephvr.gui.log_wrap import LINE_SEPARATOR

    host = QWidget()
    host.setProperty("retroConsole", True)
    host.setProperty("retroPalette", "amber_phosphor")
    log = LogConsole()
    log.setParent(host)
    log.resize(320, 200)
    message = "Local review draft restored; no controller configuration applied."
    log.appendPlainText(message)
    log.set_entry_prompts(True)
    text = log.document().firstBlock().text()
    assert LINE_SEPARATOR in text
    indent = log._wrap_indent
    assert indent > 0
    assert all(line.startswith(" " * indent) for line in text.split(LINE_SEPARATOR)[1:])
    log.selectAll()
    copied = log.createMimeDataFromSelection()
    assert copied is not None and copied.text().endswith(message)
    assert LINE_SEPARATOR not in copied.text()
    host.setProperty("retroPalette", "retro_console")
    log.set_entry_prompts(True)
    assert LINE_SEPARATOR not in log.document().firstBlock().text()
    host.deleteLater()


def test_phosphor_popups_and_owned_windows_get_scanline_film(
    app: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtWidgets import QDialog

    from cephvr.gui.managed_window import ManagedDashboardWindow
    from cephvr.gui.retro_overlay import PHOSPHOR_SCANLINE_ALPHA, CrtOverlay

    settings = QSettings(str(tmp_path / "films.ini"), QSettings.Format.IniFormat)
    window = ManagedDashboardWindow(settings=settings)
    dialog = QDialog(window)
    try:
        window.appearance.select("amber_phosphor")
        window.appearance.crt_action.setChecked(True)
        dialog.show()
        app.processEvents()
        film = dialog.findChild(CrtOverlay)
        assert film is not None and film.isVisible()
        assert film.scanline_alpha == PHOSPHOR_SCANLINE_ALPHA
        window.appearance.crt_action.setChecked(False)
        assert film.isHidden()
    finally:
        dialog.close()
        window.tracking.annotation.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_log_column_header_tracks_category_width(app: QApplication) -> None:
    from cephvr.gui.components import LogConsole

    log = LogConsole()
    log.appendPlainText("Sample subject loaded.")
    row = log.document().firstBlock().text()
    assert log.column_titles().index("MESSAGE") == row.index("Sample")
    log.appendPlainText("[LONGCATEGORY] Wider source column.")
    row = log.document().firstBlock().text()
    assert log.column_titles().index("MESSAGE") == row.index("Sample")
    log.set_column_header(True)
    assert log.header_height > 0 and log.viewportMargins().top() == log.header_height
    log.set_entry_prompts(True)
    assert log.viewportMargins().top() == log.header_height
    log.set_column_header(False)
    assert log.viewportMargins().top() == 0
    log.deleteLater()


@pytest.mark.parametrize("width", [1440, 720])
@pytest.mark.parametrize("managed", [False, True])
def test_review_appearance_switch_preserves_drafts_and_runtime(
    app: QApplication, tmp_path: Path, width: int, managed: bool
) -> None:
    from PyQt6.QtGui import QFontInfo

    from cephvr.gui.components import Button
    from cephvr.gui.managed_window import ManagedDashboardWindow
    from cephvr.gui.review import ReviewDashboardWindow
    from cephvr.gui.theme import COLORS, RETRO_COLORS, colors_for

    path = str(tmp_path / "appearance.ini")
    settings = QSettings(path, QSettings.Format.IniFormat)
    window_class = ManagedDashboardWindow if managed else ReviewDashboardWindow
    review = window_class(sample=True, settings=settings)
    runtime = ManagedDashboardWindow(settings=settings)
    reopened = None
    try:
        review.resize(width, 940)
        review.show()
        review.apply_view(review_view(Phase.CONFIGURATION))
        review.dashboard.subject_id.setText("Unsaved subject")
        review.dashboard.age.setText("Unfinished edit")
        review.dashboard.log_console.setPlainText("Existing log entry")
        selector = review.dashboard.preview_workspace
        preview_views = dict(selector.views)
        preview_requests = []
        selector.visibility_requested.connect(
            lambda *args: preview_requests.append(args)
        )
        device_gates = {
            control: control.isEnabled()
            for control in review.devices.findChildren(Button)
        }
        before = review.snapshots.capture()
        editors = review.dashboard.subject_editors
        gates = [
            button.isEnabled() for button in review.dashboard.command_buttons.values()
        ]
        original_application_style = app.styleSheet()
        standard_hud = review.dashboard.runtime_console.toPlainText()
        log_margin = review.dashboard.log_console.document().documentMargin()
        current_view = review.dashboard.view
        brackets = next(
            item
            for item in review.appearance.focus_brackets
            if item.parentWidget() is review.dashboard.subject_id
        )
        assert review.appearance.name == "standard"
        assert "Style" in [action.text() for action in runtime.menuBar().actions()]
        for name in ("retro_console", "standard", "retro_console"):
            review.appearance.actions[name].trigger()
            for _ in range(4):
                app.processEvents()
            review.activateWindow()
            review.dashboard.subject_id.setFocus()
            app.processEvents()
            assert review.dashboard.subject_id.hasFocus()
            assert brackets.isVisible() == (name == "retro_console")
            assert brackets.testAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            assert not hasattr(review.dashboard, "trial_position")
            assert review.appearance.name == name
            assert review.appearance.actions[name].isChecked()
            from cephvr.gui.components import StatusColumn

            for status in review.findChildren(StatusColumn):
                rendered = status.hud.toPlainText()
                labelled = [row for row in status.rows if row is not None and row[0]]
                assert all(row[0].upper() in rendered for row in labelled)
                if name == "retro_console" and labelled:
                    assert (
                        len(
                            {
                                line.index(" : ")
                                for line in rendered.splitlines()
                                if " : " in line
                            }
                        )
                        == 1
                    )
                if name == "standard":
                    assert " : " not in rendered
            assert review.snapshots.capture() == before
            assert review.dashboard.subject_editors == editors
            assert log_rows(review.dashboard.log_console) == [
                "[GUI]       Existing log entry"
            ]
            margin = review.dashboard.log_console.document().documentMargin()
            assert margin == log_margin
            gutter = review.dashboard.log_console.gutter
            assert gutter.isVisible() == (name == "retro_console")
            assert review.dashboard.view == current_view
            assert all(
                control.isEnabled() == enabled
                for control, enabled in device_gates.items()
            )
            # The runtime preview layout renders in the chosen style, then returns.
            show_previews(review)
            assert selector.isVisible()
            assert selector.views == preview_views and not preview_requests
            assert selector.timeline.property("role") != "card"
            review.apply_view(current_view)
            assert review.devices.config_cards[0].caption.text() == (
                "CONFIGURATION FILE"
                if name == "retro_console"
                else "Configuration file"
            )
            assert review.dashboard.session_controls.caption.text() == (
                "SYSTEM CONTROLS" if name == "retro_console" else "System controls"
            )
            assert review.dashboard.hud_card.caption.text() == "HUD"
            assert (
                runtime.dashboard.session_controls.caption.text() == "System controls"
            )
            hud = review.dashboard.runtime_console.toPlainText()
            if name == "retro_console":
                rows = [line for line in hud.splitlines() if line]
                assert len({line.index(" : ") for line in rows}) == 1
                assert f" : {current_view.phase.value}" in hud
            else:
                assert hud == standard_hud
            assert [
                button.isEnabled()
                for button in review.dashboard.command_buttons.values()
            ] == gates
            assert colors_for(review.dashboard.subject_card) == (
                RETRO_COLORS if name == "retro_console" else COLORS
            )
            assert colors_for(runtime.dashboard.subject_card) == COLORS
            for page in (review.protocol, review.devices, review.tracking):
                assert colors_for(page) == (
                    RETRO_COLORS if name == "retro_console" else COLORS
                )
                for child in page.findChildren(QWidget):
                    assert colors_for(child) == colors_for(page)
            assert runtime.styleSheet() == ""
            assert app.styleSheet() == original_application_style
            if name == "retro_console":
                assert (
                    QFontInfo(review.dashboard.subject_id.font()).family()
                    == "IBM Plex Mono"
                )
                assert review.appearance.brand.text() == "CEPHVR"
                start = review.dashboard.command_buttons["Start"]
                assert isinstance(start, Button)
                assert start.retro_label() == "[ SETUP ]"
                assert review.page_buttons[0].retro_label() == "> Dashboard"
                overlay = review.appearance.crt.overlay
                assert overlay.host is review
                assert overlay.testAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
                assert not overlay.grab().isNull()
                film = overlay.film
                overlay.grab()
                assert overlay.film is film
                title_glow = review.page_title.graphicsEffect()
                card_glow = review.dashboard.session_controls.caption.graphicsEffect()
                assert title_glow is not None and card_glow is not None
                assert title_glow.blurRadius() == card_glow.blurRadius()
                assert title_glow.color() == card_glow.color()
                setup = review.dashboard.command_buttons["Start"]
                assert setup.height() >= setup.sizeHint().height()
                assert not overlay.band_timer.isActive()
                review.appearance.band_action.setChecked(True)
                assert overlay.band_timer.isActive()
                review.appearance.band_action.setChecked(False)
                assert not overlay.band_timer.isActive()
                review.appearance.crt_action.setChecked(False)
                assert overlay.isHidden()
                assert review.page_title.graphicsEffect() is None
                assert (
                    review.dashboard.session_controls.caption.graphicsEffect() is None
                )
                review.appearance.crt_action.setChecked(True)
                assert overlay.isVisible()
                assert review.page_title.graphicsEffect() is not None
        review.appearance.select("standard")
        assert brackets.isHidden()
        assert review.page_title.graphicsEffect() is None
        review.appearance.select("retro_console")
        review.dashboard.subject_id.setFocus()
        QTest.keyClicks(review.dashboard.subject_id, "-edited")
        assert review.dashboard.subject_id.text().endswith("-edited")
        review.dashboard.sex.setFocus()
        app.processEvents()
        assert brackets.isHidden()
        assert any(
            item.isVisible() and item.parentWidget() is review.dashboard.sex
            for item in review.appearance.focus_brackets
        )
        reopened = ManagedDashboardWindow(
            settings=QSettings(path, QSettings.Format.IniFormat)
        )
        assert reopened.appearance.name == "retro_console"
        assert reopened.appearance.actions["retro_console"].isChecked()
        assert settings.value("appearance/style") == "retro_console"
    finally:
        for window in (review, runtime, reopened):
            if window is not None:
                window.tracking.annotation.close()
                window.hide()
                window.deleteLater()
        app.processEvents()


def test_camera_pin_tracks_selected_role_and_table_edits(
    window: DashboardWindow, app: QApplication
) -> None:
    devices = window.devices
    cameras, panel = devices.cameras, devices.microcontroller
    window.apply_view(review_view(Phase.CONFIGURATION))
    panel.set_role_pin("behavioral", "5")
    panel.set_role_pin("tracking", "11")
    assert cameras.trigger_pin.text() == "5"
    cameras.table.selectRow(1)
    assert cameras.trigger_pin.text() == "11"
    cameras.trigger_pin.selectAll()
    QTest.keyClicks(cameras.trigger_pin, "8")
    assert panel.pin_editors["tracking"].text() == "8"
    cameras.trigger_pin.setCursorPosition(0)
    QTest.keyClicks(cameras.trigger_pin, "1")
    assert cameras.trigger_pin.cursorPosition() == 1
    assert panel.pin_editors["tracking"].text() == "18"
    cameras.trigger_pin.selectAll()
    QTest.keyClick(cameras.trigger_pin, Qt.Key.Key_Backspace)
    assert panel.pin_editors["tracking"].text() == ""
    assert panel.pin_editors["behavioral"].text() == "5"
    panel.output_remove["tracking"].click()
    assert cameras.trigger_pin.text() == ""
    panel.pin_editors["tracking"].setText("D9")
    assert cameras.trigger_pin.text() == "9"
    snapshot = panel.snapshots.capture()
    snapshot["camera_pins"]["tracking"] = "D10"
    panel.snapshots.restore(snapshot)
    assert cameras.trigger_pin.text() == "10"
    cameras.role.setCurrentText("Eye tracking")
    assert cameras.trigger_pin.text() == ""
    QTest.keyClicks(cameras.trigger_pin, "7")
    assert panel.pin_editors["eye_tracking"].text() == "7"
    assert panel.pin_editors["tracking"].text() == "10"
    cameras.role.setCurrentText("Unassigned")
    assert cameras.trigger_pin.text() == ""
    assert not cameras.trigger_pin.isEnabled()


@pytest.mark.parametrize(
    "change", ["authority", "pending", "connection", "upload", "capture", "phase"]
)
def test_camera_pin_obeys_editing_and_diagnostic_locks(
    window: DashboardWindow, app: QApplication, change: str
) -> None:
    devices = window.devices
    cameras, panel = devices.cameras, devices.microcontroller
    window.apply_view(review_view(Phase.CONFIGURATION))
    panel.set_role_pin("behavioral", "5")
    if change == "authority":
        panel.can_review = False
    elif change == "pending":
        panel.pending_test_key = "behavioral"
    elif change == "connection":
        panel.connection_pending = True
    elif change == "upload":
        panel.upload_pending = True
    elif change == "capture":
        assert cameras.selected is not None
        cameras.selected.connected = True
    else:
        window.apply_view(review_view(Phase.RUNNING))
    panel.refresh_tests()
    assert not cameras.trigger_pin.isEnabled()
    devices.edit_camera_pin("9")
    assert panel.pin_editors["behavioral"].text() == "5"
    assert cameras.trigger_pin.text() == "5"


def test_reference_bar_lengths_follow_the_output_until_measured(
    window: DashboardWindow,
):
    panel = window.devices.projectors
    drafts = panel.screen_editor.drafts
    panel.display_pixels = {"native-a": (1280, 720)}
    panel.assignments["native-a"] = "Front"
    panel.update_geometry()
    assert drafts["Front"]["reference_x_px"] == ""
    panel.display_pixels = {"native-a": (1920, 1080)}
    panel.update_geometry()
    assert drafts["Front"]["reference_width_px"] == "1920"
    assert drafts["Front"]["reference_x_px"] == ""
    panel.screen_editor.fields["Front", "throw"].setText("1.5")
    panel.measurements.fields["Front", "reference_x_mm"].setText("160")
    panel.measurements.fields["Front", "reference_y_mm"].setText("90")
    assert drafts["Front"]["reference_x_px"] == "480"  # Pinned by the measurement.
    distance = float(drafts["Front"]["distance"])
    assert distance > 0
    # A partial edit keeps the derived distance instead of blanking it.
    panel.measurements.fields["Front", "reference_y_mm"].setText("")
    assert float(drafts["Front"]["distance"]) == pytest.approx(distance)
    panel.measurements.fields["Front", "reference_y_mm"].setText("0")
    assert drafts["Front"]["distance"] == ""  # A complete but invalid pair clears it.


def test_native_adapter_name_identifies_scaled_displays(app: QApplication):
    from types import SimpleNamespace

    from PyQt6.QtCore import QRect

    from cephvr.gui.calibration_profile import MonitorBinding
    from cephvr.gui.projectors import _stable_display_identity

    # Qt reports 125 % scaling in logical units, so rectangles cannot match GLFW's.
    screen = SimpleNamespace(
        name=lambda: r"\\.\DISPLAY3",
        geometry=lambda: QRect(1536, 0, 2048, 1600),
        devicePixelRatio=lambda: 1.25,
        manufacturer=lambda: "m",
        model=lambda: "d",
        serialNumber=lambda: "s",
    )
    bindings = (
        MonitorBinding("interface-2", 2000, 0, 2560, 2000, 60, 8, r"\\.\DISPLAY2"),
        MonitorBinding("interface-3", 1920, 0, 2560, 2000, 60, 8, r"\\.\display3"),
    )
    assert _stable_display_identity(screen, bindings) == "interface-3"
    assert _stable_display_identity(screen, bindings[:1]) == "|".join(
        ("\\\\.\\DISPLAY3", "m", "d", "s")
    )


def test_protocol_arena_limits_default_edit_undo_and_saved_region(window, app):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_snapshot import (
        capture_protocol,
        restore_protocol,
        validate_protocol,
    )
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.visual_stimulus.config.models.program_model import TrialArenaBoundaries

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(
        grouped_program(add_stimulus(blank_program(), 0, "3D arena", ()))
    )
    parameters = editor.subgroup.composer.rows[""].parameters
    limits = parameters.arena_limits
    editor.subgroup.composer.rows[""].actions_button.setChecked(True)
    from cephvr.gui.stimulus_form import ValueEditor

    initial = next(
        form
        for form in parameters.forms
        if isinstance(form, ValueEditor) and "fixed_height_mm" in form.children_by_key
    )
    for width in (1280, 720):
        window.resize(width, 1100)
        app.processEvents()
        assert initial.height() >= initial.minimumSizeHint().height()

    assert parameters.advanced_card.isAncestorOf(limits)
    assert limits.mode.currentText() == "From arena file"
    assert limits.margin.text() == "30"
    limits.margin.setText("35")
    limits.mark_changed()
    assert editor.flush_parameters()
    raw = editor.drafts[0].arena_boundaries_json
    assert (
        TrialArenaBoundaries.model_validate_json(raw).bindings[0].region.margin_mm == 35
    )
    snapshot = capture_protocol(window.protocol)
    validate_protocol(snapshot)
    editor.undo()
    limits = editor.subgroup.composer.rows[""].parameters.arena_limits
    assert limits.margin.text() == "30"
    limits.margin.setText("nan")
    limits.mark_changed()
    assert not editor.flush_parameters()
    limits.margin.setText("30")
    assert limits.apply()
    limits.mode.setCurrentIndex(1)
    assert (
        TrialArenaBoundaries.model_validate_json(editor.drafts[0].arena_boundaries_json)
        .bindings[0]
        .region.kind
        == "unrestricted"
    )
    editor.undo()
    assert (
        editor.subgroup.composer.rows[""].parameters.arena_limits.mode.currentIndex()
        == 0
    )
    document = TrialArenaBoundaries.model_validate_json(
        editor.drafts[0].arena_boundaries_json
    )
    binding = document.bindings[0]
    from cephvr.visual_stimulus.config.models.program_model import ConvexPolygon

    explicit = binding.model_copy(
        update={
            "region": ConvexPolygon(
                kind="convex_polygon_xy",
                vertices_mm=((-100, -100), (100, -100), (100, 100), (-100, 100)),
                margin_mm=12,
            )
        }
    )
    editor.drafts[0].arena_boundaries_json = document.model_copy(
        update={"bindings": (explicit,)}
    ).model_dump_json()
    editor.render_selection()
    limits = editor.subgroup.composer.rows[""].parameters.arena_limits
    assert limits.mode.currentText() == "Saved explicit region"
    assert limits.margin.text() == "12" and not limits.margin.isEnabled()
    assert (
        TrialArenaBoundaries.model_validate_json(
            editor.drafts[0].arena_boundaries_json
        ).bindings[0]
        == explicit
    )
    saved = capture_protocol(window.protocol)
    restore_protocol(window.protocol, saved)
    assert (
        TrialArenaBoundaries.model_validate_json(
            editor.drafts[0].arena_boundaries_json
        ).bindings[0]
        == explicit
    )


def test_arena_xyz_orientation_default_subject_height_and_alignment(
    window, app, tmp_path
):
    from cephvr.gui.initial_pose import ArenaPose
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(grouped_program(blank_program()))
    composer = editor.subgroup.composer
    composer.set_asset_root(str(tmp_path))
    path = tmp_path / "arena.glb"
    path.write_bytes(b"arena")
    height = window.devices.projectors.rig_editor.fields["subject_z"]
    height.setText("67.5")
    composer.mode.setCurrentIndex(1)
    setting = composer.program.sequence[0].settings[0]
    assert setting.initial.position_mm == (0, 0)
    assert setting.fixed_height_mm == 67.5
    assert (
        setting.initial.yaw_deg,
        setting.fixed_pitch_deg,
        setting.fixed_roll_deg,
    ) == (0, 0, 0)
    height.setText("88")
    assert composer.program.sequence[0].settings[0].fixed_height_mm == 67.5
    row = composer.rows[""]
    row.parameters.set_media_path(next(iter(row.parameters.asset_forms)), str(path))
    row.actions_button.setChecked(True)
    parameters = row.parameters
    pose = next(form for form in parameters.forms if isinstance(form, ArenaPose))
    from PyQt6.QtWidgets import QComboBox

    assert not pose.findChildren(QComboBox)
    from cephvr.gui.initial_pose import PoseNumber

    saved = {"column_id": "height"}
    referenced = PoseNumber({"type": "number"}, saved, {})
    assert referenced.control.isReadOnly()
    assert referenced.read() == saved
    assert not referenced.findChildren(QComboBox)
    referenced.deleteLater()
    for width in (1280, 720):
        window.resize(width, 1100)
        app.processEvents()
        assert (
            parameters.arena_limits.mapTo(parameters, QPoint()).y()
            < pose.mapTo(parameters, QPoint()).y()
        )
        limits = parameters.arena_limits
        left = pose.position_fields[0]
        right = pose.orientation_fields[0]
        assert (
            limits.mode_field.mapTo(parameters, QPoint()).x()
            == left.mapTo(parameters, QPoint()).x()
        )
        assert (
            limits.margin_field.mapTo(parameters, QPoint()).x()
            == right.mapTo(parameters, QPoint()).x()
        )
        assert limits.mode_field.width() == left.width()
        assert limits.margin_field.width() == right.width()
        for position, orientation in zip(
            pose.position_fields, pose.orientation_fields, strict=True
        ):
            assert (
                position.mapTo(parameters, QPoint()).y()
                == orientation.mapTo(parameters, QPoint()).y()
            )
            assert position.height() == orientation.height()
    for key, value in (
        ("x", "2"),
        ("y", "3"),
        ("fixed_height_mm", "40"),
        ("yaw_deg", "15"),
        ("fixed_pitch_deg", "10"),
        ("fixed_roll_deg", "5"),
    ):
        pose.children_by_key[key].control.setText(value)
    parameters.mark_changed()
    assert parameters.apply(), parameters.message.text()
    setting = composer.program.sequence[0].settings[0]
    assert setting.initial.position_mm == (2, 3)
    assert setting.fixed_height_mm == 40
    assert (
        setting.initial.yaw_deg,
        setting.fixed_pitch_deg,
        setting.fixed_roll_deg,
    ) == (15, 10, 5)
    # File-based creation uses the same current height, without changing existing poses.
    from cephvr.gui.epoch_composer import EpochComposer

    standalone = EpochComposer()
    standalone.set_subject_height(height.text())
    standalone.set_asset_root(str(tmp_path))
    path = tmp_path / "arena.glb"
    path.write_bytes(b"arena")
    standalone.add_file("3D arena", str(path), "")
    assert standalone.program.sequence[0].settings[0].fixed_height_mm == 88
    before = standalone.program
    standalone.set_subject_height("")
    standalone.add_file("3D arena", str(path), "")
    assert standalone.program == before
    assert "subject height" in standalone.message.text()
    standalone.deleteLater()


def test_arena_mode_missing_height_keeps_previous_editor_and_reports_error(window, app):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(grouped_program(blank_program()))
    composer = editor.subgroup.composer
    composer.set_screens(("Front",))
    window.devices.projectors.rig_editor.fields["subject_z"].clear()
    before = composer.program
    composer.mode.setCurrentIndex(1)
    app.processEvents()
    assert composer.mode.currentIndex() == composer.active_mode == 0
    assert composer.program == before
    assert not composer.rows["Front"].isHidden()
    assert composer.rows[""].isHidden()
    assert "subject height" in composer.message.text()
    assert composer.message.dialog is not None
    composer.message.dialog.accept()
    window.devices.projectors.rig_editor.fields["subject_z"].setText("67.5")
    composer.mode.setCurrentIndex(1)
    assert composer.active_mode == composer.mode.currentIndex() == 1
    assert composer.rows[""].indices
    assert composer.rows[""].parameters.asset_forms
    assert composer.program.sequence[0].settings[0].fixed_height_mm == 67.5
    app.processEvents()
    composer.mode.setCurrentIndex(0)
    assert composer.mode.currentIndex() == composer.active_mode == 0
    assert not composer.rows["Front"].isHidden()


@pytest.mark.parametrize("view", ["photodiode_placement", "blackout_placement"])
def test_placement_buttons_live_edits_and_unknown_close(
    window, monkeypatch, tmp_path, view
):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.live_calibration import LiveCalibration
    from cephvr.gui.projector_geometry import FACES
    from cephvr.visual_stimulus.config.calibration_placement import parse_placement
    from cephvr.visual_stimulus.v1 import runtime_pb2 as vp

    panel = window.devices.projectors
    panel.apply_view(review_view(Phase.CONFIGURATION))
    for i, face in enumerate(FACES):
        panel.assignments[f"screen{i}"] = face
        panel.display_pixels[f"screen{i}"] = (1280, 720)
    panel.select_pulse_face("Front")
    from cephvr.gui.placement_calibration import initial_photodiode_patches

    for control in (*panel.timing.fields.values(), *panel.timing.pulse_fields.values()):
        control.clear()
    assert initial_photodiode_patches(panel) is None
    panel.timing.fields["X"].setText("5")
    assert initial_photodiode_patches(panel) is None
    for key, value in (("X", "10"), ("Y", "20"), ("Width", "100"), ("Height", "80")):
        panel.timing.fields[key].setText(value)
    for key, value in (("X", "5"), ("Y", "6"), ("Width", "20"), ("Height", "10")):
        panel.timing.pulse_fields[key].setText(value)
    panel.timing.blackouts.add(dict(face="Front", x=2, y=3, width=40, height=50))
    launch = (
        panel.timing.placement_button
        if view == "photodiode_placement"
        else panel.timing.blackouts.placement_button
    )
    other = (
        panel.timing.blackouts.placement_button
        if view == "photodiode_placement"
        else panel.timing.placement_button
    )
    prepared = []
    launched = []
    closed = []
    monkeypatch.setattr(
        panel,
        "prepare_calibration",
        lambda **kw: prepared.append(kw) or tmp_path / "placement.glb",
    )
    panel.calibration_launch_requested.connect(launched.append)
    panel.calibration_close_requested.connect(lambda: closed.append(True))
    panel.set_calibration_presentation_state(active=False, available=True)
    launch.click()
    assert prepared == [dict(view=view)] and len(launched) == 1
    state = pb.Snapshot(controller_generation=str(uuid4()))
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = 4
    evidence = state.visual_stimulus_display.calibration
    evidence.controller_generation = state.controller_generation
    evidence.configuration_revision = 4
    evidence.diagnostic_id = str(uuid4())
    evidence.state = vp.DISPLAY_CALIBRATION_STATE_ACTIVE
    evidence.calibration_view = view
    sent = []
    live = LiveCalibration(
        panel, snapshot=lambda: state, send=lambda action, **kw: sent.append(kw) or True
    )
    live.install(state)
    panel.set_calibration_presentation_state(active=True, available=True, view=view)
    assert launch.text() == "Close" and launch.isEnabled() and not other.isEnabled()
    assert not panel.calibration.presentation_button.isEnabled()
    assert not panel.timing.mode.isEnabled() and not panel.rig_editor.isEnabled()
    editor = (
        panel.timing.fields["X"]
        if view == "photodiode_placement"
        else panel.timing.blackouts.rows[0][1][0]
    )
    assert editor.isEnabled()
    editor.setText("30")
    editor.textEdited.emit("30")
    live.flush()
    assert len(sent) == 1 and not sent[0]["adjustments"]
    parsed = parse_placement(sent[0]["placement_json"])
    assert (
        parsed.marker_patches["calibration_front"].rect.x
        if view == "photodiode_placement"
        else parsed.outputs[0].blackout_zones[0].x
    ) == (35 if view == "photodiode_placement" else 30)
    editor.setText("40")
    editor.textEdited.emit("40")
    live.flush()
    assert len(sent) == 1
    evidence.adjustment_sequence = 1
    live.install(state)
    live.flush()
    assert len(sent) == 2 and sent[-1]["adjustment_sequence"] == 2
    evidence.adjustment_sequence = 2
    live.install(state)
    for invalid in ("-", "10000"):
        editor.setText(invalid)
        editor.textEdited.emit(invalid)
        live.flush()
        assert len(sent) == 2
    if view == "photodiode_placement":
        editor.setText("40")
        for key, value in (
            ("X", "7"),
            ("Y", "8"),
            ("Width", "21"),
            ("Height", "11"),
        ):
            control = panel.timing.pulse_fields[key]
            control.setText(value)
            control.textEdited.emit(value)
        live.flush()
        assert len(sent) == 3
        patch = parse_placement(sent[-1]["placement_json"]).marker_patches[
            "calibration_front"
        ]
        assert (patch.rect.x, patch.rect.y, patch.rect.width, patch.rect.height) == (
            47,
            28,
            21,
            11,
        )
    panel.set_calibration_presentation_state(
        active=True, available=True, view=view, tunable=False
    )
    assert not editor.isEnabled() and launch.isEnabled()
    launch.click()
    assert closed == [True]
    live.reset()


@pytest.mark.parametrize(
    "view, empty",
    [
        ("photodiode_placement", False),
        ("photodiode_placement", True),
        ("blackout_placement", False),
    ],
)
def test_placement_bundle_uses_native_pixels_without_reference_measurements(
    tmp_path, view, empty
):
    import json

    from cephvr.gui.calibration_profile import (
        AssignedDisplay,
        MonitorBinding,
        write_diagnostic_bundle,
    )
    from cephvr.gui.projector_geometry import FACES
    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile

    values = dict(
        zip(
            (
                "rig.width",
                "rig.depth",
                "rig.height",
                "rig.subject_x",
                "rig.subject_y",
                "rig.subject_z",
            ),
            (120, 166, 110, 60, 93, 53),
            strict=True,
        )
    )
    monitors = []
    assignments = []
    for index, face in enumerate(FACES):
        values[f"screens.{face}.width"] = 90
        values[f"screens.{face}.height"] = 80
        if face != "Right":
            values[f"screens.{face}.subject_distance"] = 50
        w, h = (720, 1280) if face == "Bottom" else (1280, 720)
        monitors.append(MonitorBinding(f"native{index}", index * 1280, 0, w, h, 60, 8))
        assignments.append(AssignedDisplay(face, index * 1280, 0, w, h, True))
    calibration = dict(format="cephvr-rig-calibration", version=8, values=values)
    zones = [dict(face="Bottom", x=5, y=6, width=10, height=20)]
    pulse = dict(
        rect=dict(x=15, y=26, width=10, height=11),
        background_rect=dict(x=10, y=20, width=100, height=80),
    )
    path = write_diagnostic_bundle(
        tmp_path,
        calibration,
        tuple(assignments),
        tuple(monitors),
        view=view,
        runtime_root=tmp_path / "runtime",
        blackout_zones=zones if view == "blackout_placement" else None,
        photodiode_face="Bottom",
        photodiode_patch=None if empty else pulse,
    )
    assert path.name == f"{view}.glb"
    profile = DisplayProfile.model_validate_json(
        (tmp_path / "runtime/calibration/diagnostic_display_profile.json").read_text()
    )
    assert profile.calibration_view == view
    assert (
        tmp_path / "runtime/calibration" / path.name
    ).read_bytes() == path.read_bytes()
    assert profile.photodiode_enabled == (view == "photodiode_placement" and not empty)
    if view == "photodiode_placement" and not empty:
        assert profile.photodiode_output_id == "calibration_bottom"
        assert profile.photodiode_patch.rect.x == 15
    elif view == "blackout_placement":
        assert profile.outputs[-1].blackout_zones[0].x == 5
    else:
        assert profile.photodiode_output_id is None
        assert profile.photodiode_patch is None
    for mapping in profile.mappings:
        data = json.loads(
            (tmp_path / "runtime" / mapping.geometric_profile.logical_path).read_text()
        )
        assert data["valid_area"] is None
        assert all(vertex["uv"] == vertex["xy"] for vertex in data["vertices"])


@pytest.mark.parametrize("width", [720, 1280])
def test_device_layout_shared_with_runtime(app, tmp_path, width):
    from PyQt6.QtWidgets import QVBoxLayout

    from cephvr.gui.review import ReviewDashboardWindow

    reviewed = ReviewDashboardWindow(sample=True)
    runtime = DashboardWindow(sample=True)
    try:
        ReviewControls(reviewed, simulate_projectors=True)
        reviewed.resize(width, 940)
        reviewed.select_page(2)
        reviewed.show()
        app.processEvents()
        cameras = reviewed.devices.cameras
        left = cameras.connect_button.mapTo(cameras, QPoint())
        right = cameras.connect_all_button.mapTo(cameras, QPoint())
        assert left.y() == right.y()
        assert left.x() + cameras.connect_button.width() <= right.x()
        assert not cameras.wiring_button.isVisible()
        assert runtime.devices.cameras.wiring_button.isHidden()
        assert (
            runtime.devices.cameras.inventory_actions.itemAtPosition(0, 1).widget()
            is runtime.devices.cameras.connect_all_button
        )
        mcu = reviewed.devices.microcontroller
        reviewed.devices.tabs.setCurrentIndex(1)
        app.processEvents()
        layout = mcu.columns[0].layout()
        assert isinstance(layout, QVBoxLayout)
        assert layout.indexOf(mcu.io) == layout.indexOf(mcu.configuration) + 1
        assert layout.indexOf(mcu.triggers) == layout.indexOf(mcu.io) + 1
        assert mcu.io.isVisible()
        assert not mcu.flip_pin.isEnabled()
        runtime_mcu = runtime.devices.microcontroller
        runtime_layout = runtime_mcu.columns[0].layout()
        assert (
            runtime_layout.indexOf(runtime_mcu.io)
            == runtime_layout.indexOf(runtime_mcu.configuration) + 1
        )
        assert (
            runtime_layout.indexOf(runtime_mcu.triggers)
            == runtime_layout.indexOf(runtime_mcu.io) + 1
        )
        assert not runtime_mcu.io.isHidden()
        assert (
            runtime_layout.itemAt(
                runtime_layout.indexOf(runtime_mcu.triggers) + 1
            ).spacerItem()
            is not None
        )
    finally:
        reviewed.deleteLater()
        runtime.deleteLater()


def test_review_per_screen_pulses_blank_vsync_and_local_restore(app, tmp_path):
    from cephvr.gui.projector_pulses import ProjectorPulses
    from cephvr.gui.review import ReviewDashboardWindow
    from cephvr.gui.review_draft import load_review_draft, save_review_draft

    reviewed = ReviewDashboardWindow(sample=True)
    restored = ReviewDashboardWindow(sample=True)
    try:
        for target in (reviewed, restored):
            ReviewControls(target, simulate_projectors=True)
        timing = reviewed.devices.projectors.timing
        assert isinstance(timing, ProjectorPulses)
        timing.pulse.setChecked(True)
        timing.target.setCurrentIndex(0)
        for key, value in zip(
            ("X", "Y", "Width", "Height"), ("10", "20", "100", "80"), strict=True
        ):
            timing.fields[key].setText(value)
        for key, value in zip(
            ("X", "Y", "Width", "Height"), ("5", "6", "20", "30"), strict=True
        ):
            timing.pulse_fields[key].setText(value)
        timing.target.setCurrentIndex(1)
        assert all(not edit.text() for edit in timing.fields.values())
        assert set(timing.patches()) == {"Front"}
        for key, value in zip(
            ("X", "Y", "Width", "Height"), ("30", "40", "50", "60"), strict=True
        ):
            timing.fields[key].setText(value)
        assert set(timing.patches()) == {"Front", "Left"}
        assert timing.vsync_faces() == ("Front", "Left")
        overlays = timing.preview_overlays(timing.resolutions(), "Left")
        assert overlays["Front"][1] == (15 / 1920, 26 / 1080, 20 / 1920, 30 / 1080)
        assert timing.placement_button.isEnabled()
        timing.placement_button.click()
        assert timing.preview is not None
        preview = timing.preview
        preview.advance()
        timing.target.setCurrentIndex(2)
        assert preview.index == 1
        timing.fields["X"].setText("5")
        assert set(timing.patches(strict=False)) == {"Front", "Left"}
        assert timing.vsync_faces() == ("Front", "Left")
        with pytest.raises(ValueError):
            timing.patches()
        timing.fields["X"].clear()
        assert set(timing.patches()) == {"Front", "Left"}
        timing.target.setCurrentIndex(0)
        assert timing.fields["X"].text() == "10"
        assert timing.pulse_fields["X"].text() == "5"
        path = tmp_path / "review.json"
        save_review_draft(reviewed, path)
        assert load_review_draft(restored, path)
        fresh = restored.devices.projectors.timing
        saved_config = reviewed.devices.projectors.calibration_files.snapshot()
        fresh.restore_drafts({})
        restored.devices.projectors.calibration_files.apply_snapshot(saved_config)
        assert fresh.drafts == timing.drafts
        legacy = dict(saved_config)
        legacy.pop("review_pulse_screens")
        fresh.target.setCurrentIndex(1)
        restored.devices.projectors.calibration_files.apply_snapshot(legacy)
        assert set(fresh.patches()) == {"Front"}
        assert fresh.patches()["Front"].rect.x == 15
        restored.devices.projectors.calibration_files.apply_snapshot(saved_config)
        runtime = DashboardWindow(sample=True)
        try:
            runtime.devices.projectors.calibration_files.apply_snapshot(saved_config)
            assert runtime.devices.projectors.timing.drafts == timing.drafts
        finally:
            runtime.deleteLater()
        assert fresh.vsync_faces() == ("Front", "Left")
        for field in (*timing.fields.values(), *timing.pulse_fields.values()):
            field.clear()
        assert set(timing.patches()) == {"Left"}
        assert timing.vsync_faces() == ("Left",)
        timing.pulse.setChecked(False)
        assert timing.vsync_faces() == ()
        timing.set_presentation_mode("all_outputs_vsync")
        assert timing.vsync_faces() == ("Front", "Left", "Right", "Bottom")
        timing.set_presentation_mode("free_run")
        assert timing.vsync_faces() == ()
        reviewed.apply_view(review_view(Phase.RUNNING))
        assert timing.preview is None
    finally:
        if timing.preview is not None:
            timing.preview.close()
        reviewed.deleteLater()
        restored.deleteLater()


@pytest.mark.parametrize(
    "role,expected", [("behavioral", 1), ("tracking", 2), ("eye_tracking", 7)]
)
@pytest.mark.parametrize("backend_enabled", [False, True])
@pytest.mark.parametrize("camera_enabled", [False, True])
@pytest.mark.parametrize("external", [False, True])
def test_inventory_camera_roles_require_active_external_trigger(
    role, expected, backend_enabled, camera_enabled, external
):
    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_display_operations import required_inventory_roles

    configuration = pb.ExperimentConfiguration()
    backend = configuration.backends.add(
        backend_name="acquisition", enabled=backend_enabled
    )
    camera = getattr(backend.acquisition, role)
    camera.enabled = camera_enabled
    camera.device.frame_timing = (
        camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
        if external
        else camera_pb2.FRAME_TIMING_FREE_RUNNING
    )
    assert required_inventory_roles(configuration) == (
        frozenset({expected})
        if backend_enabled and camera_enabled and external
        else frozenset()
    )


@pytest.mark.parametrize("width", [720, 1280])
@pytest.mark.parametrize("runtime", [False, True])
def test_mcu_inputs_define_remove_and_hide_empty_header(app, width, runtime):
    from cephvr.gui.review import ReviewDashboardWindow

    reviewed = (DashboardWindow if runtime else ReviewDashboardWindow)(sample=True)
    try:
        ReviewControls(reviewed, simulate_projectors=True)
        reviewed.resize(width, 940)
        reviewed.select_page(2)
        reviewed.devices.tabs.setCurrentIndex(1)
        reviewed.show()
        app.processEvents()
        panel = reviewed.devices.microcontroller
        inputs = panel.inputs
        assert inputs is not None
        header = panel.input_table.horizontalHeader()
        assert header is not None
        assert inputs.add_button.isVisible() and inputs.add_button.isEnabled()
        assert header.isHidden() and not panel.input_table.isVisible()
        assert all(
            label.text() != "No inputs configured"
            for label in panel.io.findChildren(QLabel)
        )
        inputs.add_button.click()
        first = inputs.rows[0]
        first.name.setText("Photodiode")
        first.pin.setText("D3")
        inputs.add_button.click()
        second = inputs.rows[1]
        second.name.setText("External event")
        second.pin.setText("2")
        second.enabled.setChecked(False)
        app.processEvents()
        assert header.isVisible()
        assert panel.input_table.rowCount() == 3  # Inert legacy slot plus two inputs.
        assert inputs.snapshot() == [
            dict(name="Photodiode", pin="3", enabled=True),
            dict(name="External event", pin="2", enabled=False),
        ]
        assert not first.test.isEnabled()  # No physical input diagnostics in review.
        first.remove.click()
        assert inputs.snapshot() == [
            dict(name="External event", pin="2", enabled=False)
        ]
        second.remove.click()
        app.processEvents()
        assert inputs.snapshot() == []
        assert header.isHidden() and not panel.input_table.isVisible()
        assert inputs.add_button.isVisible() and inputs.add_button.isEnabled()
    finally:
        reviewed.deleteLater()


def test_mcu_inputs_persist_and_respect_editing_gates(app, tmp_path):
    from cephvr.gui.review import ReviewDashboardWindow
    from cephvr.gui.review_draft import load_review_draft, save_review_draft

    reviewed = ReviewDashboardWindow(sample=True)
    restored = ReviewDashboardWindow(sample=True)
    runtime = DashboardWindow(sample=True)
    try:
        for target in (reviewed, restored):
            ReviewControls(target, simulate_projectors=True)
        panel = reviewed.devices.microcontroller
        inputs = panel.inputs
        fresh = restored.devices.microcontroller.inputs
        assert inputs is not None and fresh is not None
        inputs.add_button.click()
        row = inputs.rows[0]
        row.name.setText("Sync edge")
        row.pin.setText("3")
        inputs.add_button.click()  # Retain an unfinished definition too.
        expected = inputs.snapshot()
        path = tmp_path / "review-inputs.json"
        save_review_draft(reviewed, path)
        assert load_review_draft(restored, path)
        assert fresh.snapshot() == expected
        document = panel.snapshots.capture()
        fresh.restore([])
        restored.devices.microcontroller.snapshots.restore(document)
        assert fresh.snapshot() == expected
        runtime.devices.microcontroller.snapshots.restore(document)
        assert runtime.devices.microcontroller.inputs.snapshot() == expected
        legacy = dict(document)
        legacy.pop("review_inputs")
        restored.devices.microcontroller.snapshots.restore(legacy)
        assert fresh.snapshot() == []
        with pytest.raises(ValueError, match="input drafts"):
            fresh.restore([dict(name="Bad", pin="3", enabled="yes")])
        assert fresh.snapshot() == []
        reviewed.apply_view(review_view(Phase.RUNNING))
        assert not inputs.add_button.isEnabled()
        assert not row.name.isEnabled() and not row.pin.isEnabled()
        assert not row.remove.isEnabled()
        inputs.add()
        inputs.remove(row)
        assert inputs.snapshot() == expected
        reviewed.apply_view(review_view(Phase.CONFIGURATION, observer=True))
        assert not inputs.add_button.isEnabled()
        reviewed.apply_view(review_view(Phase.CONFIGURATION))
        panel.review_tests.add("trial-state")
        panel.refresh_tests()
        assert not inputs.add_button.isEnabled()
        panel.review_tests.clear()
        panel.refresh_tests()
        assert inputs.add_button.isEnabled()
    finally:
        reviewed.deleteLater()
        restored.deleteLater()
        runtime.deleteLater()


@pytest.mark.parametrize("width", [720, 1175, 1440])
def test_review_devices_capture_aligned_fields_and_wrapped_headers(app, width):
    from cephvr.gui.review import ReviewDashboardWindow
    from cephvr.gui.table_header import TableHeader
    from cephvr.gui.tables import DataTable

    reviewed = ReviewDashboardWindow(sample=True)
    try:
        ReviewControls(reviewed, simulate_projectors=True)
        reviewed.appearance.select("retro_console")
        reviewed.resize(width, 940)
        reviewed.show()
        reviewed.page_buttons[2].click()
        for _ in range(5):
            app.processEvents()
        camera = reviewed.devices.cameras
        editors = (
            camera.trigger_source,
            camera.fields["trigger_frequency_hz"],
            camera.trigger_pin,
        )
        assert len({e.mapTo(camera.configuration, QPoint()).y() for e in editors}) == 1
        assert len({e.height() for e in editors}) == 1
        for index in range(4):
            reviewed.devices.tabs.setCurrentIndex(index)
            for _ in range(5):
                app.processEvents()
            for table in reviewed.devices.panels[index].findChildren(DataTable):
                if not table.isVisible():
                    continue
                header = table.horizontalHeader()
                assert isinstance(header, TableHeader)
                if header.isHidden():
                    continue
                for column in range(header.count()):
                    if not header.isSectionHidden(column):
                        layout = header.label_layout(column, header.sectionSize(column))
                        assert layout.boundingRect().height() + 16 <= header.height()
        projectors = reviewed.devices.projectors
        reviewed.devices.tabs.setCurrentIndex(2)
        projectors.setup_tabs.setCurrentIndex(2)
        for _ in range(5):
            app.processEvents()
        timing = projectors.timing
        assert timing.mode_field.width() == timing.width()
        assert (
            timing.mode_field.mapTo(projectors, QPoint()).x()
            == timing.mapTo(projectors, QPoint()).x()
        )
    finally:
        reviewed.hide()
        reviewed.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("width", [720, 1440])
def test_review_inline_output_templates_keep_pins_and_unfinished_rows(
    app, tmp_path, monkeypatch, width
):
    from PyQt6.QtWidgets import QInputDialog

    from cephvr.gui.mcu_outputs import MicrocontrollerOutputDrafts
    from cephvr.gui.review import ReviewDashboardWindow
    from cephvr.gui.review_draft import load_review_draft, save_review_draft

    monkeypatch.setattr(
        QInputDialog, "getInt", lambda *_: pytest.fail("Pin dialog must not open")
    )
    reviewed = ReviewDashboardWindow(sample=True)
    try:
        ReviewControls(reviewed, simulate_projectors=True)
        reviewed.appearance.select("retro_console")
        reviewed.resize(width, 940)
        reviewed.show()
        reviewed.page_buttons[2].click()
        reviewed.devices.tabs.setCurrentIndex(1)
        app.processEvents()
        panel = reviewed.devices.microcontroller
        signals = panel.signals
        assert isinstance(signals, MicrocontrollerOutputDrafts)
        add = signals.add_buttons[0][0]
        assert add.menu() is None
        before = [
            (draft.role, draft.enabled) for draft in reviewed.devices.cameras.drafts
        ]
        add.click()
        assert len(signals.templates) == 1
        template = signals.templates[0]
        assert template.selector.currentIndex() == -1 and not template.pin.text()
        assert all(not editor.text() for editor in signals.editors.values())
        template.pin.setText("8")
        template.selector.setCurrentIndex(template.selector.findData("behavioral"))
        assert not signals.templates
        assert panel.pin_editors["behavioral"].text() == "8"
        assert before == [
            (draft.role, draft.enabled) for draft in reviewed.devices.cameras.drafts
        ]
        add.click()
        template = signals.templates[0]
        template.selector.setCurrentIndex(template.selector.findData("trial-state"))
        assert not panel.trial_pin.text()
        assert not panel.output_table.isRowHidden(0)
        add.click()
        signals.templates[0].pin.setText("7")
        data = panel.snapshots.capture()
        signals.remove("behavioral")
        panel.snapshots.restore(data)
        assert panel.snapshots.capture() == data
        assert signals.templates[0].pin.text() == "7"
        assert panel.pin_editors["behavioral"].text() == "8"
        assert not panel.output_table.isRowHidden(0)
        path = tmp_path / "unfinished-output-review.json"
        save_review_draft(reviewed, path)
        signals.remove_template(signals.templates[0])
        signals.remove("trial-state")
        assert load_review_draft(reviewed, path)
        assert panel.snapshots.capture() == data
        selected = signals.selectors["behavioral"]
        selected.setCurrentIndex(selected.findData("tracking"))
        assert panel.pin_editors["behavioral"].text() == ""
        assert panel.pin_editors["tracking"].text() == "8"
        assert before == [
            (draft.role, draft.enabled) for draft in reviewed.devices.cameras.drafts
        ]
        panel.set_role_pin("eye_tracking", "9")
        panel.refresh_tests()
        panel.pin_editors["eye_tracking"].clear()
        panel.refresh_tests()
        assert not panel.output_table.isRowHidden(panel.role_rows["eye_tracking"])
        signals.remove("eye_tracking")
        assert panel.output_table.isRowHidden(panel.role_rows["eye_tracking"])
        current = panel.snapshots.capture()
        reviewed.apply_view(review_view(Phase.RUNNING))
        signals.add()
        signals.remove("tracking")
        assert panel.snapshots.capture() == current
        assert not add.isEnabled()
    finally:
        reviewed.hide()
        reviewed.deleteLater()
        app.processEvents()


@pytest.mark.parametrize(
    "modifier", [Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.MetaModifier]
)
def test_directory_paths_clipboard_and_editing_locks(window, app, modifier):
    clipboard = app.clipboard()
    assert clipboard is not None
    previous = clipboard.text()
    path = "/data/experiment α/" + "long directory/" * 12
    try:
        for page, editor in (
            (0, window.dashboard.output_field.editor),
            (1, window.protocol.assets.folders["root"].editor),
        ):
            window.page_buttons[page].click()
            editor.setFocus()
            clipboard.setText(path)
            QTest.keyClick(editor, Qt.Key.Key_A, modifier)
            QTest.keyClick(editor, Qt.Key.Key_V, modifier)
            assert editor.text() == path and editor.toolTip() == path
            QTest.keyClick(editor, Qt.Key.Key_A, modifier)
            QTest.keyClick(editor, Qt.Key.Key_C, modifier)
            assert clipboard.text() == path
            QTest.keyClick(editor, Qt.Key.Key_X, modifier)
            assert editor.text() == "" and clipboard.text() == path
            QTest.keyClick(editor, Qt.Key.Key_V, modifier)
            assert editor.text() == path
            editor.setReadOnly(True)
            QTest.keyClick(editor, Qt.Key.Key_A, modifier)
            clipboard.setText("different")
            QTest.keyClick(editor, Qt.Key.Key_C, modifier)
            assert clipboard.text() == path
            clipboard.setText("different")
            QTest.keyClick(editor, Qt.Key.Key_V, modifier)
            QTest.keyClick(editor, Qt.Key.Key_X, modifier)
            assert editor.text() == path
            editor.setReadOnly(False)
        assert window.devices.projectors.asset_root == path
        window.apply_view(review_view(Phase.RUNNING))
        for editor in (
            window.dashboard.output_field.editor,
            window.protocol.assets.folders["root"].editor,
        ):
            clipboard.setText("locked replacement")
            QTest.keyClick(editor, Qt.Key.Key_A, modifier)
            QTest.keyClick(editor, Qt.Key.Key_V, modifier)
            assert editor.text() == path
    finally:
        clipboard.setText(previous)


@pytest.mark.parametrize("width", [1440, 720])
def test_review_protocol_style_keeps_drafts_history_and_dynamic_screen_rows(
    app, tmp_path, width
):
    from cephvr.gui.components import Button
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.review import ReviewDashboardWindow
    from cephvr.gui.theme import COLORS, RETRO_COLORS, colors_for

    settings = QSettings(
        str(tmp_path / "protocol-style.ini"), QSettings.Format.IniFormat
    )
    reviewed = ReviewDashboardWindow(sample=True, settings=settings)
    try:
        reviewed.resize(width, 1000)
        reviewed.apply_view(review_view(Phase.CONFIGURATION))
        reviewed.page_buttons[1].click()
        reviewed.show()
        editor = reviewed.protocol.editor
        editor.set_program(review_program())
        open_protocol_group(editor)
        reviewed.appearance.select("retro_console")
        editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
        editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
        for _ in range(5):
            app.processEvents()
        composer = editor.subgroup.composer
        advanced = composer.rows["Front"].parameters.advanced_card
        assert advanced.caption.text() == "ADVANCED SETTINGS"
        assert advanced.caption.graphicsEffect() is not None
        reviewed.activateWindow()
        reviewed.protocol.config_scroll.ensureWidgetVisible(composer.rows["Front"])
        composer.rows["Front"].stimulus.setFocus()
        app.processEvents()
        assert any(
            item.parentWidget() is composer.rows["Front"].stimulus and item.isVisible()
            for item in reviewed.appearance.focus_brackets
        )
        composer.batch_label.setText("Unsaved style draft")
        editor.subgroup.apply()
        app.processEvents()
        original = editor.program
        history = (
            list(editor.histories[editor.index].past),
            list(editor.histories[editor.index].future),
        )
        gates = {
            control: control.isEnabled() for control in editor.findChildren(Button)
        }
        source = (
            editor.timeline.paths,
            editor.timeline.type_keys,
            editor.timeline.selection,
        )
        for style in ("standard", "retro_console", "standard", "retro_console"):
            reviewed.appearance.select(style)
            for _ in range(5):
                app.processEvents()
            assert composer.batch_label.text() == "Unsaved style draft"
            assert editor.program == original
            assert (
                editor.histories[editor.index].past,
                editor.histories[editor.index].future,
            ) == history
            assert (
                editor.timeline.paths,
                editor.timeline.type_keys,
                editor.timeline.selection,
            ) == source
            assert all(
                control.isEnabled() == enabled for control, enabled in gates.items()
            )
            assert colors_for(editor.timeline) == (
                RETRO_COLORS if style == "retro_console" else COLORS
            )
            assert advanced.caption.text() == (
                "ADVANCED SETTINGS" if style == "retro_console" else "Advanced settings"
            )
            viewport = reviewed.protocol.config_scroll.viewport()
            assert reviewed.protocol.config_scroll.widget().width() <= viewport.width()
            assert editor.settings_card.width() == editor.width()
            assert editor.timeline_card.height() == editor.trial_card.height()
            for caption in editor.group_editor.findChildren(QLabel):
                if caption.isVisible() and caption.property("role") == "label":
                    assert caption.width() >= caption.fontMetrics().horizontalAdvance(
                        caption.text()
                    )
            shot = editor.timeline.grab().toImage()
            rect = next(
                rect
                for rect, index, face, _ in editor.timeline.hits
                if not face
                and editor.timeline.paths[index] in editor.timeline.selection
            )
            if style == "retro_console":
                assert (
                    shot.pixelColor(
                        round(rect.right() - 10), round(rect.bottom() - 10)
                    ).name()
                    == RETRO_COLORS.accent
                )
        reviewed.apply_view(review_view(Phase.RUNNING))
        locked = {
            control: control.isEnabled() for control in editor.findChildren(Button)
        }
        for style in ("standard", "retro_console"):
            reviewed.appearance.select(style)
            assert all(
                control.isEnabled() == enabled for control, enabled in locked.items()
            )
            assert not reviewed.protocol.can_edit
    finally:
        reviewed.appearance.select("standard")
        reviewed.hide()
        reviewed.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_variation_hover_does_not_change_visibility_during_enter_dispatch(
    window, app, monkeypatch, style
):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QCursor, QEnterEvent

    appearance = window.appearance
    appearance.select(style, persist=False)
    try:
        window.page_buttons[1].click()
        editor = window.protocol.editor
        open_protocol_group(editor)
        editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
        editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
        form = editor.subgroup
        form.add_rule.click()
        app.processEvents()
        row = form.rows[0]
        table = form.variation_table
        calls = []
        with monkeypatch.context() as patch:
            patch.setattr(
                row.remove, "setVisible", lambda visible: calls.append(visible)
            )
            point = QPointF(row.target.rect().center())
            event = QEnterEvent(
                point, point, QPointF(row.target.mapToGlobal(point.toPoint()))
            )
            table.eventFilter(row.target, event)
            assert calls == []
        row.remove.hide()
        row.enterEvent(event)
        assert row.remove.isHidden()  # Table mode has one hover owner.
        window.protocol.config_scroll.ensureWidgetVisible(table)
        app.processEvents()
        QTest.mouseMove(form.add_rule, form.add_rule.rect().center())
        QTest.qWait(20)
        QTest.mouseMove(row.target, row.target.rect().center())
        QTest.qWait(50)
        app.processEvents()
        assert not row.remove.isHidden(), (
            QCursor.pos(),
            row.target.mapToGlobal(row.target.rect().center()),
            table.viewport().mapFromGlobal(QCursor.pos()),
            table.viewport().rect(),
            table.isVisible(),
        )
        QTest.mouseMove(form.add_rule, form.add_rule.rect().center())
        QTest.qWait(50)
        assert row.remove.isHidden()
        # Pending hover work must tolerate removal and a fresh rule immediately after.
        table.eventFilter(row.target, event)
        form.remove_variation(row)
        form.add_rule.click()
        app.processEvents()
        assert len(form.rows) == len(table.rules) == 1
        assert form.rows[0] is not row
    finally:
        appearance.select("standard", persist=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cancel_at", ["queued", "start", "show", "cleanup_failure", "generation"]
)
async def test_camera_safe_cancellation_waits_and_closes_exact_new_run(cancel_at):
    from cephvr.client.session import ClientError
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_cancellation import Cancellation
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    token = Cancellation()
    state = pb.Snapshot(controller_generation="original")
    state.configuration.revision = 7
    device = state.acquisition_devices.behavioral
    calls, finished = [], []

    async def execute(method, request):
        calls.append(request)
        if request.kind == rpc.CAMERA_COMMAND_KIND_START_PREVIEW:
            device.device_open = device.preview_running = True
            device.preview_run_id = "new-run"
            if cancel_at != "show":
                token.requested.set()
            if cancel_at == "generation":
                state.controller_generation = "replacement"
        elif request.kind == rpc.CAMERA_COMMAND_KIND_SHOW_PREVIEW:
            token.requested.set()
        else:
            assert request.kind == rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW
            assert request.preview_run_id == "new-run"
            assert request.expected_configuration_revision == 7
            assert not finished  # Cancelling lasts through confirmed cleanup.
            if cancel_at == "cleanup_failure":
                return SimpleNamespace(succeeded=False, failure="release unconfirmed")
            device.Clear()
        return SimpleNamespace(succeeded=True, failure="")

    client = SimpleNamespace(
        snapshot=state, execute=execute, operator_command=lambda: rpc.OperatorCommand()
    )
    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    bridge.command_finished.connect(lambda *args: finished.append(args))
    if cancel_at == "queued":
        token.requested.set()
    operation = bridge._dispatch(
        client,
        "camera",
        dict(
            kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW,
            role=1,
            show_preview=True,
            cancellation=token,
        ),
    )
    if cancel_at in {"cleanup_failure", "generation"}:
        with pytest.raises(ClientError, match="unconfirmed"):
            await operation
        assert not finished
    else:
        await operation
        assert finished[0][1] is False and finished[0][2].startswith("Cancelled")
        assert not device.device_open
    assert (
        len(calls)
        == {"queued": 0, "start": 2, "show": 3, "cleanup_failure": 2, "generation": 1}[
            cancel_at
        ]
    )


@pytest.mark.asyncio
async def test_camera_cancel_waits_for_inflight_call_and_exact_cleanup():
    import asyncio

    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_cancellation import Cancellation
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation="generation")
    state.configuration.revision = 7
    device = state.acquisition_devices.behavioral
    token = Cancellation()
    started, cleanup_started = asyncio.Event(), asyncio.Event()
    complete_call, complete_cleanup = asyncio.Event(), asyncio.Event()
    events, cancelled, finished = [], [], []

    async def execute(method, request):
        assert method == "ExecuteCameraCommand"
        try:
            if request.kind == rpc.CAMERA_COMMAND_KIND_START_PREVIEW:
                events.append("start")
                started.set()
                await complete_call.wait()
                device.device_open = device.preview_running = True
                device.preview_run_id = "created-run"
                events.append("started")
            else:
                assert request.kind == rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW
                assert request.preview_run_id == "created-run"
                assert request.expected_configuration_revision == 7
                events.append("cleanup")
                cleanup_started.set()
                await complete_cleanup.wait()
                device.Clear()
                events.append("closed")
        except asyncio.CancelledError:
            cancelled.append(request.kind)
            raise
        return SimpleNamespace(succeeded=True, failure="")

    client = SimpleNamespace(
        snapshot=state, execute=execute, operator_command=lambda: rpc.OperatorCommand()
    )
    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )

    def terminal(*args):
        events.append("terminal")
        finished.append(args)

    bridge.command_finished.connect(terminal)
    operation = asyncio.create_task(
        bridge._dispatch(
            client,
            "camera",
            dict(
                kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW,
                role=1,
                show_preview=True,
                cancellation=token,
            ),
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 1)
        token.requested.set()
        await asyncio.sleep(0)
        assert events == ["start"] and not finished and not operation.done()
        complete_call.set()
        await asyncio.wait_for(cleanup_started.wait(), 1)
        assert events == ["start", "started", "cleanup"]
        assert device.device_open and not finished and not operation.done()
        complete_cleanup.set()
        await asyncio.wait_for(asyncio.shield(operation), 1)
        assert events == ["start", "started", "cleanup", "closed", "terminal"]
        assert not cancelled and not device.device_open
        assert len(finished) == 1 and finished[0][1] is False
        assert finished[0][2].startswith("Cancelled; cleanup confirmed")
    finally:
        complete_call.set()
        complete_cleanup.set()
        await asyncio.wait_for(operation, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("preexisting", [False, True])
async def test_mcu_cancel_preserves_existing_connection_and_stops_new_test(preexisting):
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_cancellation import Cancellation
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation="generation")
    state.configuration.revision = 3
    if preexisting:
        state.microcontroller.observation.connection_id = "connection"
    token = Cancellation()
    calls = []

    async def execute(method, request):
        calls.append(request)
        if request.kind == rpc.MICROCONTROLLER_COMMAND_KIND_START:
            state.microcontroller.observation.connection_id = "connection"
            state.microcontroller.diagnostic.active = True
            state.microcontroller.diagnostic.signal = (
                pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE
            )
            token.requested.set()
        elif preexisting:
            assert request.kind == rpc.MICROCONTROLLER_COMMAND_KIND_STOP
            state.microcontroller.ClearField("diagnostic")
        else:
            assert request.kind == rpc.MICROCONTROLLER_COMMAND_KIND_DISCONNECT
            assert request.expected_connection_id == "connection"
            state.microcontroller.Clear()
        return SimpleNamespace(succeeded=True, failure="")

    client = SimpleNamespace(
        snapshot=state, execute=execute, operator_command=lambda: rpc.OperatorCommand()
    )
    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    await bridge._dispatch(
        client,
        "mcu",
        dict(
            kind=rpc.MICROCONTROLLER_COMMAND_KIND_START,
            signal=pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
            cancellation=token,
        ),
    )
    assert len(calls) == 2
    assert bool(state.microcontroller.observation.connection_id) == preexisting
    assert not state.microcontroller.diagnostic.active


def test_pending_mcu_button_cancels_without_dispatching_twice(window):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_mcu import ManagedMcu

    panel = window.devices.microcontroller
    panel.managed = True
    panel.set_saved_pins("COM8", "D9", True, "D2", True)
    window.apply_view(
        DashboardView(connected=True, has_control=True, configuration_wired=False)
    )
    state = pb.Snapshot()
    state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition.pulses.port = "COM8"
    calls = []
    binding = ManagedMcu(
        panel,
        SimpleNamespace(
            request=lambda action, **kw: calls.append((action, kw)) or True
        ),
        lambda: state,
    )
    control = panel.test_connection_button
    original = control.text()
    control.click()
    assert control.text() == "Cancel" and control.isEnabled()
    token = calls[0][1]["cancellation"]
    control.click()
    assert token.requested.is_set() and control.text().startswith("Cancelling")
    assert not control.isEnabled() and len(calls) == 1
    panel.refresh_tests()
    assert not control.isEnabled()
    binding.finished("mcu", False, "Cancelled; cleanup confirmed")
    assert control.text() == original and control.isEnabled()

    binding.test_pin("trial-state", True)
    pin_button = panel.test_buttons["trial-state"]
    assert pin_button.text() == "Cancel" and pin_button.isEnabled()
    pin_button.click()
    assert calls[-1][1]["cancellation"].requested.is_set()
    assert pin_button.text().startswith("Cancelling") and not pin_button.isEnabled()
    binding.finished(calls[-1][0], False, "Cancelled; cleanup confirmed")
    assert pin_button.text() == "Test"


def test_spikeglx_check_cancel_survives_view_refresh(window):
    panel = window.devices.spikeglx
    view = DashboardView(connected=True, has_control=True)
    panel.apply_view(view)
    calls = []
    panel.connection_requested.connect(
        lambda: panel.start_connection_check(
            lambda action, **kw: calls.append((action, kw)) or True
        )
    )
    control = panel.action_buttons[0]
    control.click()
    panel.apply_view(view)
    assert control.text() == "Cancel" and control.isEnabled()
    control.click()
    panel.apply_view(view)
    assert control.text().startswith("Cancelling") and not control.isEnabled()
    assert len(calls) == 1 and calls[0][1]["cancellation"].requested.is_set()
    panel.pending_action.finish()
    panel.apply_view(view)
    assert control.text() == "Test connection" and control.isEnabled()


@pytest.mark.asyncio
async def test_cancel_after_mcu_settings_acceptance_skips_hardware_and_retains_settings():
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_cancellation import Cancellation
    from cephvr.gui.controller_bridge import ControllerBridge
    from cephvr.shared.auth import Principal

    state = pb.Snapshot(controller_generation="generation")
    state.session.phase = pb.SESSION_PHASE_CONFIGURATION
    state.configuration.revision = state.configuration_values.revision = 7
    settings = state.configuration_values.current.backends.add(
        backend_name="acquisition"
    ).acquisition
    settings.pulses.port = "COM8"
    token = Cancellation()
    options = dict(
        generation="generation",
        base_revision=7,
        base_configuration=state.configuration_values.current.SerializeToString(
            deterministic=True
        ),
        port="COM9",
        kind=rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT,
        cancellation=token,
    )
    calls, accepted, finished = [], [], []

    async def execute(method, request):
        calls.append(method)
        assert method == "UpdateConfiguration"
        state.configuration_values.current.CopyFrom(request.proposed)
        state.configuration.revision = state.configuration_values.revision = 8
        token.requested.set()
        return SimpleNamespace(succeeded=True, failure="")

    client = SimpleNamespace(
        snapshot=state, execute=execute, operator_command=lambda: rpc.OperatorCommand()
    )
    bridge = ControllerBridge(
        Principal("gui", "gui-generation", "token"), 50051, 1024, (0,)
    )
    bridge.device_configuration_accepted.connect(lambda *args: accepted.append(args))
    bridge.command_finished.connect(lambda *args: finished.append(args))
    await bridge._dispatch(client, "prepare_mcu_connection", options)
    assert calls == ["UpdateConfiguration"] and len(accepted) == 1
    assert (
        state.configuration_values.current.backends[0].acquisition.pulses.port == "COM9"
    )
    assert finished[0][2].startswith("Cancelled")


@pytest.mark.asyncio
async def test_cancel_camera_test_does_not_close_preexisting_preview():
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.cancel_cleanup import cleanup_cancelled_device

    before = pb.Snapshot(controller_generation="generation")
    before.acquisition_devices.behavioral.preview_running = True
    before.acquisition_devices.behavioral.preview_run_id = "already-open"
    client = SimpleNamespace(
        snapshot=pb.Snapshot.FromString(before.SerializeToString())
    )
    await cleanup_cancelled_device(client, "camera", {"role": 1}, before)
    assert (
        client.snapshot.acquisition_devices.behavioral.preview_run_id == "already-open"
    )


@pytest.mark.parametrize("wired", [False, True])
@pytest.mark.parametrize(
    "outcome",
    [
        "complete",
        "partial",
        "failed",
        "cancel",
        "queue",
        "authority",
        "selection",
        "disconnect_failure",
    ],
)
def test_enabled_camera_bulk_connections_use_sequential_confirmed_intents(
    window, app, wired, outcome
):
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.gui.camera_inventory import CameraDraft
    from cephvr.gui.managed_cameras import ManagedCameras

    panel = window.devices.cameras
    panel.managed = panel.snapshot_draft = True
    panel.drafts.append(
        CameraDraft(
            "disabled",
            "Eye tracking",
            "disabled",
            "sample",
            enabled=False,
            connected=True,
        )
    )
    panel.populate_inventory()
    for draft in panel.drafts:
        draft.values["trigger_clock"] = "Internal clock"
    if outcome == "partial":
        panel.drafts[0].connected = panel.drafts[0].capture_running = True
    panel.apply_view(
        DashboardView(connected=True, has_control=True, configuration_wired=wired)
    )
    calls = []
    revision = 4

    def request(action, **options):
        calls.append((action, options))
        return outcome != "queue"

    binding = ManagedCameras(
        panel,
        SimpleNamespace(request=request),
        lambda *_: False,
        preview_placement=lambda key: key.encode(),
        submission_options=lambda _: {"base_revision": revision},
    )
    assert not hasattr(panel, "selected_test_button")
    assert panel.connect_all_button.text() == "Connect all"
    panel.connect_all_button.click()
    assert len(calls) == 1
    assert calls[0][0] == "prepare_camera"
    assert calls[0][1]["camera_role"] == (2 if outcome == "partial" else 1)
    assert calls[0][1]["show_preview"]
    if outcome == "queue":
        assert not binding.pending and not panel.bulk_pending
        assert panel.pending_action.token is None
        return
    assert not panel.connect_button.isEnabled()
    assert panel.connect_all_button.text() == "Cancel"
    panel.table.selectRow(1)  # Selection changes do not retarget the in-flight request.
    if outcome == "selection":
        panel.drafts[1].role = "Eye tracking"
        panel.drafts[0].connected = panel.drafts[0].capture_running = True
        binding.finished("prepare_camera", True, "connected")
        app.processEvents()
        assert len(calls) == 1 and not panel.bulk_pending
        return
    if outcome in {"failed", "cancel", "authority"}:
        if outcome == "cancel":
            panel.connect_all_button.click()
            assert calls[0][1]["cancellation"].requested.is_set()
        if outcome == "authority":
            panel.apply_view(DashboardView(connected=True, has_control=False))
        binding.finished("prepare_camera", outcome == "authority", "terminal")
        app.processEvents()
        assert len(calls) == 1 and not panel.bulk_pending
        assert not panel.drafts[1].connected
        return
    first = 1 if outcome == "partial" else 0
    for index in range(first, 2):
        assert calls[-1][1]["camera_role"] == index + 1
        assert calls[-1][1]["base_revision"] == revision
        # Apply the confirmed result before allowing the next camera command.
        panel.drafts[index].connected = panel.drafts[index].capture_running = True
        revision += 1
        binding.finished("prepare_camera", True, "connected")
        app.processEvents()
    assert not panel.bulk_pending and not binding.pending
    assert panel.connect_button.text() == "Disconnect selected"
    assert panel.connect_all_button.text() == "Disconnect all"
    assert len(calls) == (1 if outcome == "partial" else 2)
    panel.connect_all_button.click()
    for index in range(2):
        assert calls[-1][0] == "camera"
        assert calls[-1][1]["role"] == index + 1
        assert calls[-1][1]["kind"] == rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW
        success = outcome != "disconnect_failure" or index != 0
        if success:
            panel.drafts[index].connected = panel.drafts[index].capture_running = False
        binding.finished("camera", success, "terminal")
        app.processEvents()
    assert not panel.bulk_pending and not binding.pending
    assert panel.drafts[0].connected == (outcome == "disconnect_failure")
    assert not panel.drafts[1].connected
    assert panel.drafts[2].connected  # Disabled cameras are outside the bulk selection.
    assert panel.connect_all_button.text() == "Connect all"


def test_review_camera_selected_and_all_controls_follow_enabled_state(window):
    panel = window.devices.cameras
    window.apply_view(review_view(Phase.CONFIGURATION))
    requests = []
    panel.preview_requested.connect(lambda *args: requests.append(args))
    panel.connect_button.click()
    assert panel.connect_button.text() == "Disconnect selected"
    assert panel.connect_all_button.text() == "Connect all"
    panel.connect_all_button.click()
    assert all(draft.connected for draft in panel.drafts)
    assert requests == [(panel.drafts[0].key, True), (panel.drafts[1].key, True)]
    assert panel.connect_all_button.text() == "Disconnect all"
    panel.connect_all_button.click()
    assert not any(draft.connected for draft in panel.drafts)
    assert panel.connect_button.text() == "Connect selected"
    assert panel.connect_all_button.text() == "Connect all"
    panel.enable_controls[1].setChecked(False)
    panel.connect_all_button.click()
    assert panel.drafts[0].connected and not panel.drafts[1].connected
    panel.connect_all_button.click()
    panel.enable_controls[0].setChecked(False)
    assert not panel.connect_all_button.isEnabled()


@pytest.mark.parametrize("wired", [False, True])
def test_pending_camera_button_cancel_is_bound_to_original_request(window, wired):
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.gui.managed_cameras import ManagedCameras

    panel = window.devices.cameras
    panel.managed = True
    window.apply_view(
        DashboardView(connected=True, has_control=True, configuration_wired=wired)
    )
    calls = []
    binding = ManagedCameras(
        panel,
        SimpleNamespace(
            request=lambda action, **kw: calls.append((action, kw)) or True
        ),
        lambda *_: False,
    )
    assert binding.queue("camera", kind=rpc.CAMERA_COMMAND_KIND_START_PREVIEW, role=1)
    control = panel.connect_button
    assert control.text() == "Cancel" and control.isEnabled()
    control.click()
    assert len(calls) == 1 and calls[0][1]["role"] == 1
    assert calls[0][1]["cancellation"].requested.is_set()
    panel.refresh_controls()
    assert control.text().startswith("Cancelling") and not control.isEnabled()
    binding.finished("camera", False, "Cancelled; cleanup confirmed")
    assert control.text() in {"Connect selected", "Disconnect selected"}
    assert panel.pending_action.token is None


@pytest.mark.parametrize("style", ["retro_console", "amber_phosphor"])
def test_retro_epoch_tints_are_stable_and_dim(app: QApplication, style: str) -> None:
    from PyQt6.QtGui import QColor

    from cephvr.gui.retro_instruments import tile_tint, unselected_epoch_brush
    from cephvr.gui.theme import RETRO_PALETTES

    colors, tints = RETRO_PALETTES[style]
    owner = QWidget()
    owner.setProperty("retroPalette", style)
    allowed = {QColor(item).name() for item in tints}
    for key in ("flow", "baseline", "recovery"):
        tint = tile_tint(key, owner)
        assert tint == tile_tint(key, owner) and tint.name() in allowed
        brush = unselected_epoch_brush(tint, colors)
        assert brush.lightnessF() < tint.lightnessF()
        assert brush.lightnessF() > QColor(colors.card).lightnessF()


def test_managed_preview_relayout_requires_visible_run_and_control(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_preview_viewers import ManagedPreviewViewers

    panel = window.devices.cameras
    panel.managed = True
    key = panel.drafts[0].key
    panel.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            previews=(PreviewView(key, "Camera", active=True, visible=True),),
        )
    )
    state = pb.Snapshot()
    device = state.acquisition_devices.behavioral
    device.preview_running = device.preview_visible = True
    device.preview_run_id = "run-a"
    calls = []
    hint = rpc.PreviewWindowPlacement(x=20, y=30, side=320)
    viewers = ManagedPreviewViewers(
        lambda: state,
        panel,
        lambda *args, **kw: calls.append((args, kw)) or True,
        lambda _key: hint.SerializeToString(),
    )
    viewers.layout_timer.stop()
    viewers.relayout()
    assert len(calls) == 1
    sent = rpc.PreviewWindowPlacement.FromString(calls[-1][1]["placement"])
    assert sent.update_existing_only and sent.side == 320
    viewers.relayout()
    assert len(calls) == 1
    viewers.snap(key)
    snap = rpc.PreviewWindowPlacement.FromString(calls.pop()[1]["placement"])
    assert snap.snap_to_grid and snap.update_existing_only
    hint.side = 256
    viewers.relayout()
    assert len(calls) == 2
    device.preview_visible = False
    hint.side = 200
    viewers.relayout()
    assert len(calls) == 2
    device.preview_visible = True
    panel.apply_view(
        DashboardView(connected=True, has_control=False, previews=panel.view.previews)
    )
    viewers.relayout()
    assert len(calls) == 2


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6])
def test_preview_slot_adapts_open_source_grid(app: QApplication, count: int) -> None:
    from cephvr.gui.preview_placement import PreviewSlot

    slot = PreviewSlot()
    slot.resize(900, 900)
    sources = tuple(
        PreviewView(str(i), f"Camera {i}", visible=i < count) for i in range(7)
    )
    slot.set_sources(sources)
    slot.show()
    app.processEvents()
    assert list(slot.frames) == [str(i) for i in range(count)]
    snapped = []
    slot.snap_requested.connect(snapped.append)
    slot.frames[str(count - 1)].snap_button.click()
    assert snapped == [str(count - 1)]
    for i, frame in enumerate(slot.frames.values()):
        row, col, rows, cols = slot.grid.getItemPosition(slot.grid.indexOf(frame))
        assert (row, col, rows, cols) == (i // 2, i % 2, 1, 2 if count == 1 else 1)
    slot.set_sources((PreviewView("0", "Camera 0", visible=True),))
    app.processEvents()
    assert slot.frames["0"].width() == slot.width()
    slot.close()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_preview_log_four_lines_and_collapse_follows_latest(
    window: DashboardWindow, app: QApplication, style: str
) -> None:
    window.appearance.select(style, persist=False)
    dashboard_log = window.dashboard.log_console
    expanded = dashboard_log.height()
    window.select_page(2)
    console = window.devices.cameras.status_column.console
    console.setPlainText("\n".join(f"Entry {i}" for i in range(50)))
    scroll = console.verticalScrollBar()
    scroll.setValue(0)
    view = replace(
        window.dashboard.view,
        previews=(PreviewView("camera-1", "Camera", active=True, visible=True),),
    )
    window.apply_view(view)
    for _ in range(4):
        app.processEvents()
    assert scroll.value() == scroll.maximum()
    assert console.minimumHeight() == console.maximumHeight()
    document = console.document()
    available = console.viewport().height() - 2 * document.documentMargin()
    assert abs(available - 4 * console.fontMetrics().lineSpacing()) <= 1
    scroll.setValue(0)
    window.apply_view(view)
    app.processEvents()
    assert scroll.value() == 0
    window.select_page(0)
    show_previews(window)
    for _ in range(4):
        app.processEvents()
    assert not dashboard_log.preview_compact
    assert dashboard_log.height() == expanded
    assert dashboard_log.maximumHeight() > dashboard_log.minimumHeight()
    window.select_page(2)
    app.processEvents()
    assert console.preview_compact
    window.apply_view(replace(view, previews=()))
    for _ in range(4):
        app.processEvents()
    assert console.maximumHeight() > console.minimumHeight()
    assert not hasattr(window.dashboard, "trial_position")


def test_devices_side_rail_mirrors_tabs_and_yields_when_narrow(
    app: QApplication, tmp_path: Path
) -> None:
    settings = QSettings(str(tmp_path / "rail.ini"), QSettings.Format.IniFormat)
    window = DashboardWindow(sample=True, settings=settings)
    devices = window.devices
    try:
        window.resize(1600, 900)
        window.show()
        window.page_buttons[2].click()
        app.processEvents()
        # Default: the existing top tabs, no rail.
        assert not devices.rail_mode and devices.rail_host.isHidden()
        assert devices.navigation.isVisible()
        window.side_rail_action.setChecked(True)
        app.processEvents()
        assert devices.rail_mode and devices.rail_host.isVisible()
        assert devices.navigation.isHidden()
        assert devices.projectors.setup_tabs.isHidden()
        assert settings.value("devices/side_rail", type=bool) is True
        rail = devices.rail
        assert [rail.devices[i].text(0) for i in range(4)] == [
            devices.tab_bar.tabText(i) for i in range(4)
        ]
        # Rail drives the tab bar and the Projectors section tabs.
        rail.item_chosen(rail.rows[(2, 1)])
        assert devices.tab_bar.currentIndex() == 2
        assert devices.projectors.setup_tabs.currentIndex() == 1
        assert rail.currentItem() is rail.rows[(2, 1)]
        # Tab changes elsewhere are mirrored without echoing a choice back.
        chosen: list[tuple[int, int]] = []
        rail.chosen.connect(lambda device, section: chosen.append((device, section)))
        devices.projectors.setup_tabs.setCurrentIndex(2)
        devices.tab_bar.setCurrentIndex(3)
        assert rail.currentItem() is rail.rows[(3, -1)] and not chosen
        # Narrow pages fall back to the top tabs.
        window.resize(900, 800)
        app.processEvents()
        assert not devices.rail_mode and devices.rail_host.isHidden()
        assert devices.navigation.isVisible()
        assert devices.projectors.setup_tabs.isVisibleTo(devices.projectors)
        window.resize(1600, 900)
        window.side_rail_action.setChecked(False)
        app.processEvents()
        assert not devices.rail_mode and devices.navigation.isVisible()
        assert settings.value("devices/side_rail", type=bool) is False
    finally:
        window.close()


def test_empty_states_and_disabled_file_controls_explain_themselves(
    app: QApplication,
) -> None:
    from cephvr.gui.configuration_files import LOCKED_REASON

    window = DashboardWindow(sample=False)
    try:
        window.resize(1400, 900)
        window.show()
        window.page_buttons[2].click()
        app.processEvents()
        projectors = window.devices.projectors
        assert "No displays listed" in projectors.table.empty_text
        assert not projectors.table.has_visible_rows()
        assert not projectors.table.grab().isNull()
        assert "refresh" in projectors.diagram.paint_text().lower()
        # Observer/disconnected: Load/Save are disabled and say why.
        for controls in (window.devices.cameras.config_files,):
            assert not controls.load_button.isEnabled()
            assert LOCKED_REASON in controls.load_button.toolTip()
            assert LOCKED_REASON in controls.save_button.toolTip()
        files = projectors.calibration_files
        assert not files.isEnabled()
        assert LOCKED_REASON in files.load_button.toolTip()
        window.apply_view(review_view(Phase.CONFIGURATION))
        app.processEvents()
        assert window.devices.cameras.config_files.load_button.isEnabled()
        assert (
            LOCKED_REASON
            not in window.devices.cameras.config_files.load_button.toolTip()
        )
        assert LOCKED_REASON not in files.load_button.toolTip()
    finally:
        window.close()


def test_recent_values_are_deduplicated_ordered_bounded_and_persisted(
    app: QApplication, tmp_path: Path
) -> None:
    from cephvr.gui.dashboard import Dashboard
    from cephvr.gui.recent_values import RECENT_LIMIT, RecentValues

    settings = QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat)
    recent = RecentValues(settings, "k")
    for value in ("  ", "Sepia officinalis", "Sepia bandensis", "sepia OFFICINALIS"):
        recent.remember(value)
    assert recent.values() == ["sepia OFFICINALIS", "Sepia bandensis"]
    for index in range(RECENT_LIMIT + 3):
        recent.remember(f"value {index}")
    assert len(recent.values()) == RECENT_LIMIT
    assert recent.values()[0] == f"value {RECENT_LIMIT + 2}"
    assert RecentValues(settings, "k").values() == recent.values()
    assert RecentValues(None, "k").values() == []

    dashboard = Dashboard(sample=True, settings=settings)
    emitted: list[str] = []
    dashboard.action_requested.connect(emitted.append)
    try:
        dashboard.apply_view(review_view(Phase.CONFIGURATION))
        dashboard.species.setCurrentText("Sepia Latimanus")
        dashboard.condition.setText("Dark control")
        dashboard.setup()
        assert emitted == ["Setup"]
        assert dashboard.recent_conditions.values() == ["Dark control"]
        # A blocked request (observer) must not record anything.
        dashboard.apply_view(review_view(Phase.CONFIGURATION, observer=True))
        dashboard.condition.setText("Never requested")
        dashboard.setup()
        assert emitted == ["Setup"]
        assert "Never requested" not in dashboard.recent_conditions.values()
        completer = dashboard.condition.completer()
        assert completer is not None and completer.model().rowCount() > 0
    finally:
        dashboard.deleteLater()


def test_subject_history_reads_the_controller_session_layout(tmp_path: Path) -> None:
    from datetime import date

    from cephvr.gui.subject_history import find_subject_sessions

    root = tmp_path / "data"
    for name in (
        "20261018_Optic_flow/CEPH-007-090000",
        "20261019_Optic_flow/CEPH-007-101500",
        "20261019_Water_flow/CEPH-008-101500",
        "20261019_Water_flow/CEPH-0070-111111",
        "notes/CEPH-007-123456",
    ):
        (root / name).mkdir(parents=True)
    (root / "20261019_Optic_flow" / "CEPH-007-111111").write_text(
        "a file, not a session"
    )
    today = date(2026, 10, 19)
    found = find_subject_sessions(str(root), "CEPH-007", "Optic flow", today)
    assert found is not None and found.count == 2
    assert found.latest == "2026-10-19 Optic_flow 10:15"
    assert found.same_experiment_today
    other = find_subject_sessions(str(root), "CEPH-007", "Water flow", today)
    assert other is not None and other.count == 2 and not other.same_experiment_today
    assert find_subject_sessions(str(root), "CEPH-009", "Optic flow", today) is None
    assert find_subject_sessions(str(root), "", "Optic flow", today) is None
    assert find_subject_sessions(str(root), "///", "Optic flow", today) is None
    assert find_subject_sessions("", "CEPH-007", "Optic flow", today) is None
    assert (
        find_subject_sessions(str(tmp_path / "missing"), "CEPH-007", "x", today) is None
    )
    # An empty experiment cannot match today's folder but still reports history.
    blank = find_subject_sessions(str(root), "CEPH-007", "", today)
    assert blank is not None and not blank.same_experiment_today


@pytest.mark.parametrize(
    ("earlier", "later", "expected"),
    [
        ("20261019_Zulu/090000", "20261019_Alpha/180000", "2026-10-19 Alpha 18:00"),
        ("20261018_Zulu/230000", "20261019_Alpha/010000", "2026-10-19 Alpha 01:00"),
        ("20261019_Zulu/180001", "20261019_Alpha/180002", "2026-10-19 Alpha 18:00"),
        ("20261019_Alpha/180000", "20261019_Zulu/180000", "2026-10-19 Zulu 18:00"),
    ],
)
def test_subject_history_orders_by_date_then_time(
    tmp_path: Path, earlier: str, later: str, expected: str
) -> None:
    from datetime import date

    from cephvr.gui.subject_history import find_subject_sessions

    for session in (later, earlier):
        experiment, clock = session.split("/")
        (tmp_path / experiment / f"CEPH-007-{clock}").mkdir(parents=True)
    found = find_subject_sessions(
        str(tmp_path), "CEPH-007", "Alpha", date(2026, 10, 19)
    )
    assert found is not None and found.count == 2
    assert found.latest == expected
    assert found.same_experiment_today


def test_dashboard_warns_quietly_and_confirms_same_day_reuse(
    app: QApplication, tmp_path: Path
) -> None:
    from datetime import date

    from cephvr.gui.dashboard import Dashboard

    root = tmp_path / "data"
    today = f"{date.today():%Y%m%d}"
    (root / "20200101_Water_flow" / "0007-080000").mkdir(parents=True)
    dashboard = Dashboard(sample=True)
    emitted: list[str] = []
    dashboard.action_requested.connect(emitted.append)
    try:
        dashboard.show()
        dashboard.apply_view(review_view(Phase.CONFIGURATION))
        dashboard.output_root.setText(str(root))
        dashboard.subject_id.setText("0007")
        dashboard.experiment.setText("Optic flow")
        dashboard.refresh_subject_history()
        assert "already has 1 earlier session" in dashboard.subject_id.toolTip()
        log = dashboard.log_console.toPlainText()
        assert log.count("already has 1 earlier session") == 1
        dashboard.refresh_subject_history()
        assert dashboard.log_console.toPlainText() == log
        # Earlier sessions of another experiment/day: Setup goes straight through.
        dashboard.setup()
        assert emitted == ["Setup"] and dashboard.reuse_dialog is None
        emitted.clear()
        (root / f"{today}_Optic_flow" / "0007-090000").mkdir(parents=True)
        dashboard.setup()
        dialog = dashboard.reuse_dialog
        assert dialog is not None and not emitted
        assert "nothing is overwritten" in "".join(
            label.text() for label in dialog.findChildren(QLabel)
        )
        dashboard.setup()
        assert dashboard.reuse_dialog is dialog
        dialog.change.click()
        app.processEvents()
        assert dashboard.reuse_dialog is None and not emitted
        dashboard.setup()
        assert dashboard.reuse_dialog is not None
        dashboard.reuse_dialog.proceed.click()
        app.processEvents()
        assert emitted == ["Setup"] and dashboard.reuse_dialog is None
        # Losing authority while the dialog is open closes it without a request.
        emitted.clear()
        dashboard.setup()
        assert dashboard.reuse_dialog is not None
        dashboard.apply_view(review_view(Phase.CONFIGURATION, observer=True))
        app.processEvents()
        assert dashboard.reuse_dialog is None and not emitted
        # Clearing the subject removes the hint.
        dashboard.subject_id.setText("")
        dashboard.refresh_subject_history()
        assert dashboard.subject_id.toolTip() == ""
    finally:
        dashboard.close()


def test_runtime_per_screen_pulses_submit_restore_and_keep_disabled_placement(window):
    import json

    from tests.visual_stimulus.support import valid_display_json

    from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
    from cephvr.visual_stimulus.v1 import runtime_pb2

    panel = window.devices.projectors
    source = json.loads(valid_display_json())
    prototype = source["outputs"][0]
    faces = ("front", "left", "right", "bottom")
    source["outputs"] = [
        dict(prototype, output_id=face, device_identity=face) for face in faces
    ]
    for mapping, face in zip(source["mappings"], faces, strict=True):
        mapping["output_id"] = face
    source["photodiode_output_id"] = "front"
    source["photodiode_patch"]["high_linear_rgb"] = [0.8, 0.7, 0.6]
    base = runtime_pb2.DisplayConfiguration(profile_json=json.dumps(source))
    panel.install_configuration(base)
    panel.select_pulse_face("Left")
    for name, value in zip(
        ("X", "Y", "Width", "Height"), ("20", "30", "40", "50"), strict=True
    ):
        panel.timing.fields[name].setText(value)
    assert set(panel.timing.patches()) == {"Front", "Left"}
    submitted = panel.configuration_for_submit(base)
    parsed = DisplayProfile.model_validate_json(submitted.profile_json)
    assert set(parsed.marker_patches) == {"front", "left"}
    assert parsed.marker_patches["left"].rect.x == 20
    assert parsed.marker_patches["front"].high_linear_rgb == (0.8, 0.7, 0.6)
    assert [parsed.requested_swap_interval(face) for face in faces] == [1, 1, 0, 0]
    panel.install_configuration(submitted)
    assert set(panel.timing.patches()) == {"Front", "Left"}
    panel.timing.pulse.setChecked(False)
    disabled = panel.configuration_for_submit(submitted)
    parsed = DisplayProfile.model_validate_json(disabled.profile_json)
    assert not parsed.marker_patches and len(parsed.photodiode_patches) == 2
    assert parsed.photodiode_patches["front"].high_linear_rgb == (0.8, 0.7, 0.6)
    panel.calibration_files.apply_snapshot(json.loads(disabled.profile_json))
    assert set(panel.timing.drafts) == {"Front", "Left"}
    panel.timing.pulse.setChecked(True)
    assert set(panel.timing.patches()) == {"Front", "Left"}
    panel.timing.target.addItem("Unassigned display", "unassigned")
    panel.timing.target.setCurrentIndex(panel.timing.target.findData("unassigned"))
    assert panel.timing.face is None
    assert set(panel.timing.drafts) == {"Front", "Left"}


def test_projector_new_pulse_patch_supplies_colors_without_overwriting_explicit_values():
    import json

    from tests.visual_stimulus.support import valid_display_json

    from cephvr.gui.projector_codec import merge_projector_draft
    from cephvr.visual_stimulus.v1 import runtime_pb2

    document = json.loads(valid_display_json())
    document.pop("photodiode_patch", None)
    base = runtime_pb2.DisplayConfiguration(profile_json=json.dumps(document))
    for patch, expected in [
        ({"rect": {"x": 0, "y": 0, "width": 10, "height": 10}}, [1.0, 1.0, 1.0]),
        ({"high_linear_rgb": [0.7, 0.8, 0.9]}, [0.7, 0.8, 0.9]),
    ]:
        result = merge_projector_draft(
            base,
            assignments={},
            participation={},
            pulse_enabled=False,
            pulse_output_identity=None,
            presentation_mode="free_run",
            pulse_patch=patch,
            geometry=None,
        )
        merged = json.loads(result.profile_json)["photodiode_patch"]
        assert merged["high_linear_rgb"] == expected
        assert merged["low_linear_rgb"] == [0.0, 0.0, 0.0]


def test_crt_overlay_remains_input_transparent_when_native(app):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QWidget

    from cephvr.gui.retro_overlay import CrtOverlay

    host = QWidget()
    overlay = CrtOverlay(host)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
    host.close()


@pytest.mark.parametrize("advanced", [False, True])
def test_preview_workspace_pending_visible_update_preserves_placement(app, advanced):
    from cephvr.gui.preview_placement import PreviewSlot
    from cephvr.gui.previews import PreviewWorkspace

    host = QWidget()
    dialog = PreviewWorkspace(None)
    slot = PreviewSlot()
    dialog.preview_layout.addWidget(slot)
    dialog.empty_hint.hide()
    dialog.advanced_toggle.setChecked(advanced)
    source = PreviewView(
        "stimulus",
        "Visual stimulus",
        active=True,
        available=True,
        visible=True,
        reason="",
    )

    def project(view):
        dialog.apply_views((view,), allowed=True)
        slot.set_sources((view,), reserve_active=True)
        slot.attach_controls(dialog, external=True)
        app.processEvents()
        slot.align_headers(True)
        app.processEvents()
        return QRect(slot.target.geometry())

    try:
        project(source)
        dialog.show()
        app.processEvents()
        baseline = project(source)
        for pending in (True, False) * 4:
            assert project(replace(source, pending=pending)) == baseline
            assert dialog.controls[source.key].isEnabled() is not pending
            assert dialog.hints[source.key].text() == ("closing…" if pending else "")
        project(replace(source, visible=False, pending=True))
        assert dialog.statuses[source.key] == "Waiting for viewer…"
        assert not dialog.hints[source.key].text()  # The frame shows the wait.
        # An unshown stream frees its frame; its reason stays on the stream status.
        unavailable = replace(
            source, visible=False, available=False, reason="Available after Setup"
        )
        project(unavailable)
        assert source.key not in slot.frames
        assert dialog.statuses[source.key] == "Available after Setup"
        assert dialog.controls[source.key].toolTip() == "Available after Setup"
        assert dialog.hints[source.key].isHidden()
        assert dialog.names[source.key].isEnabled()
        project(replace(source, reason="Viewer unavailable"))
        assert dialog.statuses[source.key] == "Viewer unavailable"
        assert not dialog.hints[source.key].text()
        dialog.apply_views((source,), allowed=False)
        assert dialog.hints[source.key].text() == "no control"
    finally:
        dialog.hide()
        host.close()
        host.deleteLater()


def test_preview_frame_metrics_show_live_values_and_clear_stale_or_hidden(
    app, monkeypatch
):
    from cephvr.gui import preview_frame
    from cephvr.gui.preview_frame import PreviewFrame

    now = 10_000_000_000
    monkeypatch.setattr(preview_frame, "host_time_ns", lambda: now)
    frame = PreviewFrame()
    frame.resize(600, 900)
    source = PreviewView(
        "stimulus",
        "Visual stimulus",
        visible=True,
        source_fps=59.8,
        preview_fps=29.9,
        rates_observed_ns=now - 100,
    )
    frame.set_metrics(source)
    frame.show()
    app.processEvents()
    assert frame.metrics.text() == "Source: 59.8 fps\nPreview: 29.9 fps"
    assert frame.target.y() - (frame.header.y() + frame.header.height()) == 8
    assert frame.metrics.y() == frame.target.y() + frame.target.height() + 8
    assert frame.rect().contains(frame.metrics.geometry())
    frame.set_metrics(replace(source, visible=False))
    assert frame.metrics.text() == "Source: — fps\nPreview: — fps"
    now += 4_000_000_000
    frame.set_metrics(source)
    assert frame.metrics.text() == "Source: — fps\nPreview: — fps"
    frame.close()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_preview_workspace_frames_shown_streams_and_timeline(
    window, app, style, monkeypatch
):
    from cephvr.gui.preview_placement import preview_window_placement
    from cephvr.gui.protocol_document import TrialDraft, review_program

    window.appearance.select(style, persist=False)
    monkeypatch.setattr(
        window.screen(), "availableGeometry", lambda: QRect(0, 0, 1920, 1080)
    )
    sources = tuple(
        PreviewView(
            str(i), name, active=i < 5, available=i < 4, visible=i < 4, reason=""
        )
        for i, name in enumerate(
            ("Behavior", "Tracking cam", "Eye", "Stimulus", "Tracking", "Disabled")
        )
    )
    window.protocol.editor.drafts = [TrialDraft("Motion", review_program())]
    view = DashboardView(
        connected=True,
        has_control=True,
        previews=sources,
        trial_index=1,
        elapsed_s=12,
        phase=Phase.RUNNING,
    )
    window.apply_view(view)
    show_previews(window)
    dialog = window.dashboard.preview_workspace
    window.resize(1600, 1000)
    app.processEvents()
    # Only shown streams take frames; the active but unavailable "4" has none.
    assert tuple(window.preview_slot.frames) == ("0", "1", "2", "3")
    assert dialog.details.isHidden()
    assert dialog.preview_host.width() == dialog.splitter.width()
    assert dialog.hud.geometry().bottom() < dialog.timeline_card.y()
    assert dialog.timeline_card.geometry().bottom() < dialog.splitter.y()
    assert dialog.timeline_card.width() == dialog.splitter.width()
    assert dialog.timeline_card.isAncestorOf(dialog.toggle_bar)
    assert dialog.timeline_card.isAncestorOf(dialog.video_row)
    assert all(dialog.video_row.isAncestorOf(c) for c in dialog.controls.values())
    targets = {key: frame.target for key, frame in window.preview_slot.frames.items()}
    assert not dialog.empty_hint.isVisible()
    # Playback advances locally while the run is reported as running.
    assert dialog.timeline.elapsed == pytest.approx(12, abs=1)
    assert not dialog.timeline.epoch_timeline.message
    assert not dialog.grab().isNull()
    if QApplication.platformName() != "windows":
        placements = [preview_window_placement(window, key) for key in targets]
        assert all(p.side >= 128 for p in placements)
    # Hiding one stream frees its frame for the others.
    window.apply_view(
        replace(view, previews=(replace(sources[0], visible=False), *sources[1:]))
    )
    assert tuple(window.preview_slot.frames) == ("1", "2", "3")
    window.apply_view(view)
    targets = {key: frame.target for key, frame in window.preview_slot.frames.items()}
    requests = []
    dialog.visibility_requested.connect(lambda *args: requests.append(args))
    dialog.advanced_toggle.click()
    app.processEvents()
    assert dialog.details.isVisible()
    assert dialog.preview_host.geometry().right() < dialog.details.x()
    # Card padding keeps the Projectors card a little above a third.
    assert dialog.details.width() / sum(dialog.splitter.sizes()) == pytest.approx(
        1 / 3, abs=0.06
    )
    assert dialog.details.isAncestorOf(dialog.timeline.motion_section)
    before = dialog.preview_host.width()
    dialog.splitter.moveSplitter(before - 180, 1)
    app.processEvents()
    assert dialog.preview_host.width() < before
    assert dialog.details.width() > sum(dialog.splitter.sizes()) * 0.3
    assert {
        key: frame.target for key, frame in window.preview_slot.frames.items()
    } == targets
    dialog.advanced_toggle.click()
    app.processEvents()
    assert dialog.details.isHidden()
    assert dialog.preview_host.width() == dialog.splitter.width()
    assert not requests
    for name in dialog.names.values():
        assert name.text().startswith("[ ") and name.text().endswith(" ]")
    window.resize(900, 800)
    app.processEvents()
    assert all(
        window.preview_slot.rect().contains(frame.geometry())
        for frame in window.preview_slot.frames.values()
    )


@pytest.mark.parametrize(
    "count,width,height,columns",
    [(3, 1600, 500, 3), (4, 1800, 500, 4), (4, 900, 900, 2)],
)
def test_preview_workspace_chooses_largest_frames(app, count, width, height, columns):
    from cephvr.gui.preview_placement import PreviewSlot

    slot = PreviewSlot()
    slot.resize(width, height)
    slot.set_sources(
        tuple(
            PreviewView(str(i), str(i), active=True, visible=True) for i in range(count)
        ),
        reserve_active=True,
    )
    slot.show()
    app.processEvents()
    assert slot.columns == columns
    targets = [frame.target for frame in slot.frames.values()]
    slot.resize(900, 900)
    app.processEvents()
    assert slot.columns == 2
    assert [frame.target for frame in slot.frames.values()] == targets
    if slot.grid.columnCount() > 3:
        assert slot.grid.columnStretch(3) == 0
    slot.close()


def test_preview_timeline_visibility_and_advanced_preference(app, tmp_path):
    from cephvr.gui.previews import PreviewWorkspace

    settings = QSettings(str(tmp_path / "preview.ini"), QSettings.Format.IniFormat)
    # A preference saved before the timeline became permanent is ignored.
    settings.setValue("windows/preview-timeline-visible", False)
    host = QWidget()
    dialog = PreviewWorkspace(None, settings)
    dialog.show()
    app.processEvents()
    assert dialog.timeline.isVisible()
    assert dialog.advanced_toggle.text() == "Advanced previews"
    assert not hasattr(dialog, "timeline_toggle")
    dialog.hide()
    restored = PreviewWorkspace(
        None, QSettings(settings.fileName(), QSettings.Format.IniFormat)
    )
    # Advanced previews default off and are remembered locally.
    assert not restored.advanced_toggle.isChecked()
    assert not restored.timeline.advanced
    assert restored.toggle_bar.isAncestorOf(restored.advanced_toggle)
    restored.advanced_toggle.click()
    assert restored.timeline.advanced
    assert settings.value("windows/preview-advanced-visible", type=bool)
    again = PreviewWorkspace(
        None, QSettings(settings.fileName(), QSettings.Format.IniFormat)
    )
    assert again.advanced_toggle.isChecked() and again.timeline.advanced
    again.show()
    app.processEvents()
    # Card padding keeps the Projectors card a little above a third.
    assert again.details.width() / sum(again.splitter.sizes()) == pytest.approx(
        1 / 3, abs=0.06
    )
    host.close()
    host.deleteLater()


def test_video_previews_toggle_hides_section_and_closes_open_viewers(app, tmp_path):
    from cephvr.gui.previews import PreviewWorkspace

    path = str(tmp_path / "video.ini")
    settings = QSettings(path, QSettings.Format.IniFormat)
    workspace = PreviewWorkspace(None, settings)
    workspace.resize(1200, 800)
    workspace.apply_views(
        (
            PreviewView("a", "Behavior cam", active=True, available=True, visible=True),
            PreviewView("b", "Tracking cam", active=True, available=True),
        ),
        allowed=True,
    )
    requests = []
    workspace.visibility_requested.connect(lambda *args: requests.append(args))
    workspace.show()
    app.processEvents()
    assert workspace.video_toggle.text() == "Video previews"
    assert workspace.video_toggle.isChecked() and workspace.preview_host.isVisible()
    assert workspace.toggle_bar.isAncestorOf(workspace.video_toggle)
    workspace.advanced_toggle.setChecked(True)
    workspace.video_toggle.click()
    app.processEvents()
    assert workspace.preview_host.isHidden()
    # Only the open viewer is closed; capture and the dials are untouched.
    assert requests == [("a", False)]
    assert workspace.details.isVisible()
    assert not settings.value("windows/preview-video-visible", type=bool)
    workspace.video_toggle.click()
    app.processEvents()
    assert workspace.preview_host.isVisible() and workspace.details.isVisible()
    assert workspace.preview_host.geometry().right() < workspace.details.x()
    restored = PreviewWorkspace(None, QSettings(path, QSettings.Format.IniFormat))
    assert restored.video_toggle.isChecked()
    workspace.video_toggle.click()
    again = PreviewWorkspace(None, QSettings(path, QSettings.Format.IniFormat))
    assert not again.video_toggle.isChecked() and again.preview_host.isHidden()
    workspace.close()


def test_preview_top_row_holds_system_controls_hud_console_and_view_toggles(
    window, app
):
    dialog = window.dashboard.preview_workspace
    show_previews(window)
    assert dialog.toggle_bar.isAncestorOf(dialog.advanced_toggle)
    assert dialog.timeline_card.header.indexOf(dialog.toggle_bar) >= 0
    # No REC or output-fault lamp is drawn in the HUD card.
    assert not dialog.hud_card.findChildren(QLabel, "rec-lamp")
    cards = (window.dashboard.session_controls, dialog.hud_card, dialog.log_card)
    assert cards[0].geometry().right() < cards[1].x()
    assert cards[1].geometry().right() < cards[2].x()
    assert len({card.y() for card in cards}) == 1
    assert dialog.timeline_card.y() > max(card.geometry().bottom() for card in cards)


def test_dashboard_view_tabs_follow_session_and_manual_choice(window, app):
    dashboard = window.dashboard
    tabs = dashboard.view_tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Configure", "Monitor"]
    assert tabs.currentIndex() == 0 and not dashboard.runtime_layout
    tabs.setCurrentIndex(1)  # Monitor before Start: workspace with System controls
    app.processEvents()
    assert dashboard.runtime_layout
    assert dashboard.preview_workspace.top.indexOf(dashboard.session_controls) >= 0
    tabs.setCurrentIndex(0)
    show_previews(window)  # Start switches to Monitor
    assert tabs.currentIndex() == 1 and dashboard.runtime_layout
    tabs.setCurrentIndex(0)  # A manual Configure choice survives running updates
    window.apply_view(replace(dashboard.view, elapsed_s=5))
    assert tabs.currentIndex() == 0 and not dashboard.runtime_layout
    window.apply_view(replace(dashboard.view, phase=Phase.ENDED))
    assert tabs.currentIndex() == 0
    show_previews(window)
    assert tabs.currentIndex() == 1
    window.apply_view(replace(dashboard.view, phase=Phase.ENDED))
    assert tabs.currentIndex() == 0 and not dashboard.runtime_layout


def test_advanced_projector_toggles_free_hidden_sections(app):
    from cephvr.gui.previews import PreviewWorkspace

    workspace = PreviewWorkspace(None)
    timeline = workspace.timeline
    left, right = QWidget(), QWidget()
    timeline.projector_cards = {"Left": left, "Right": right}
    timeline.place_projectors()
    timeline.cards_changed.emit()
    assert list(workspace.projector_controls) == ["Left", "Right"]
    assert (
        workspace.advanced_row.isHidden() is not workspace.advanced_toggle.isChecked()
    )
    workspace.projector_controls["Left"].setChecked(False)
    assert timeline.instrument_host.instruments == [right]
    assert left.isHidden() and not timeline.projector_visible("Left")
    workspace.projector_controls["Right"].setChecked(False)
    assert timeline.instrument_host.instruments == [timeline.notice]
    workspace.projector_controls["Left"].setChecked(True)
    assert timeline.instrument_host.instruments == [left]
    workspace.close()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_preview_inline_controls_follow_camera_recording_choices(app, style):
    from cephvr.gui.camera_inventory import CameraDraft

    window = DashboardWindow(sample=True)
    window.appearance.select(style, persist=False)
    cameras = window.devices.cameras.drafts
    cameras.append(
        CameraDraft("camera-eye", "Eye tracking", "REVIEW-003", "Basler · sample")
    )
    window.recordings.sync_cameras()
    behavior = next(camera for camera in cameras if "behavior" in camera.role.lower())
    others = [camera for camera in cameras if camera is not behavior]
    for camera in cameras:
        camera.enabled = True
    sources = tuple(
        PreviewView(camera.key, camera.role, active=True, available=True, reason="")
        for camera in cameras
    )
    state = DashboardView(
        connected=True, has_control=True, previews=sources, phase=Phase.RUNNING
    )
    window.recordings.install_values({behavior.key: True})
    window.apply_view(state)
    window.show()
    show_previews(window)
    dialog = window.dashboard.preview_workspace
    requests = []
    dialog.visibility_requested.connect(lambda *args: requests.append(args))
    app.processEvents()
    # Toggles live in the timeline's Video row; nothing is shown yet, so no frames.
    assert tuple(window.preview_slot.frames) == ("",)
    for camera in others:
        assert not dialog.controls[camera.key].isEnabled()
        assert dialog.video_row.isAncestorOf(dialog.controls[camera.key])
        dialog.request(camera.key, True)
    assert not requests
    control = dialog.controls[behavior.key]
    assert control.text() == behavior.role
    assert control.isVisible() and control.isEnabled()
    added = others[0].key
    window.recordings.record[added].setChecked(True)
    app.processEvents()
    assert dialog.controls[added].isEnabled()
    dialog.controls[added].click()
    assert requests == [(added, True)] and not dialog.controls[added].isEnabled()
    visible = replace(
        state,
        previews=tuple(
            replace(source, visible=source.key == added) for source in sources
        ),
    )
    window.apply_view(visible)
    app.processEvents()
    assert tuple(window.preview_slot.frames) == (added,)
    frame = window.preview_slot.frames[added]
    assert frame.header.isAncestorOf(dialog.source_widgets[added])
    window.recordings.record[added].setChecked(False)
    assert added in window.preview_slot.frames  # Keep an already-open viewer closable.
    dialog.controls[added].click()
    assert requests[-1] == (added, False)
    window.apply_view(state)
    app.processEvents()
    assert added not in window.preview_slot.frames
    window.select_page(2)
    app.processEvents()
    assert not dialog.source_widgets[behavior.key].isVisible()
    window.select_page(0)
    show_previews(window)
    app.processEvents()
    window.apply_view(replace(state, has_control=False))
    assert not control.isEnabled()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_preview_timeline_dial_units_epochs_and_unresolved_order(app):
    from math import hypot

    from cephvr.gui.preview_motion_data import planned_speed
    from cephvr.gui.preview_timeline import StimulusTimeline
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import review_program
    from cephvr.visual_stimulus.config.models.program_model import (
        Constant,
        ImageTile,
        Rate,
    )

    program = review_program()
    texture = program.sequence[1].settings[0]
    assert planned_speed(texture, 0) == pytest.approx(
        30
    )  # 1.5 cycles/s / 0.05 cycles/deg.
    tile = texture.model_copy(
        update={
            "pattern": ImageTile(
                kind="image_tile",
                asset_id="tile",
                period_x=Constant(kind="constant", value=20),
                period_y=Constant(kind="constant", value=10),
                sampling="linear",
            ),
            "phase_y": Rate(kind="rate", function=Constant(kind="constant", value=4)),
        }
    )
    assert planned_speed(tile, 0) == pytest.approx(50)
    with pytest.raises(ValueError, match="Linked motion"):
        planned_speed(tile.model_copy(update={"linked_to": "reference"}), 0)
    timeline = StimulusTimeline()
    timeline.set_advanced(True)
    timeline.set_program(program, "", "Trial 1")
    assert [(e.start, e.end) for e in timeline.epochs] == [
        (0, 5),
        (5, 25),
        (25, 60),
    ]
    timeline.set_elapsed(2)
    assert timeline.dial_samples[0].message == "No stimulus"
    timeline.set_elapsed(10)
    assert hypot(*timeline.dial_samples[0].vector) == pytest.approx(30)
    assert timeline.dial_samples[0].unit == "deg/s"
    timeline.set_elapsed(30)
    assert timeline.dial_samples[0].vector is None
    grouped = grouped_program(program)
    group = grouped.sequence[0].model_copy(update={"order": "shuffle_each_repetition"})
    shuffled = grouped.model_copy(update={"sequence": (group,)})
    timeline.set_program(shuffled, "", "Shuffled")
    assert "seed" in timeline.epoch_timeline.message and not timeline.dial_samples
    timeline.set_program(shuffled, "42", "Shuffled")
    assert not timeline.epoch_timeline.message and timeline.dial_samples
    timeline.close()


def test_preview_motion_reference_projector_polar_rotation_and_cursor(app):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    from cephvr.gui.preview_motion_data import planned_rotation
    from cephvr.gui.preview_motion_dial import rotation_text, vector_text
    from cephvr.gui.preview_timeline import StimulusTimeline
    from cephvr.gui.protocol_document import review_program
    from cephvr.visual_stimulus.config.models.program_model import Constant, Hold, Rate

    program = review_program()
    epoch = program.sequence[1]
    source = epoch.settings[0]
    source = source.model_copy(
        update={
            "space": source.space.model_copy(update={"surfaces": ("bottom",)}),
            "motion": source.motion.model_copy(
                update={
                    "rotation": Rate(
                        kind="rate", function=Constant(kind="constant", value=-15)
                    )
                }
            ),
        }
    )
    follower = source.model_copy(
        update={
            "instance_id": "follower",
            "linked_to": source.instance_id,
            "space": source.space.model_copy(update={"surfaces": ("left",)}),
        }
    )
    epoch = epoch.model_copy(update={"settings": (follower, source)})
    program = program.model_copy(
        update={"sequence": (program.sequence[0], epoch, program.sequence[2])}
    )
    timeline = StimulusTimeline()
    timeline.resize(1000, 340)
    timeline.set_advanced(True)
    timeline.set_program(program, "", "Trial")
    timeline.show()
    app.processEvents()
    from PyQt6.QtWidgets import QCheckBox

    assert len(timeline.dials) == 2
    assert timeline.sources[0].name == "Bottom · reference"
    cards = timeline.instrument_host.findChildren(QWidget, "ProjectorCard")
    assert len(cards) == 2
    assert all(card.grid is not None for card in cards)
    assert not timeline.instrument_host.findChildren(QCheckBox)
    assert timeline.size_lane.epochs == timeline.epochs
    timeline.set_elapsed(12)
    sample = timeline.dial_samples[0]
    assert vector_text(sample).endswith("· 90°")
    assert sample.angular_speed == -15 and rotation_text(sample) == "-15°/s"
    assert not sample.message
    assert (
        planned_rotation(
            source.model_copy(
                update={
                    "motion": source.motion.model_copy(
                        update={
                            "rotation": Rate(
                                kind="rate",
                                function=Constant(kind="constant", value=15),
                            )
                        }
                    )
                }
            ),
            0,
        )
        == 15
    )
    timeline.set_elapsed(45)
    assert timeline.epoch_timeline.elapsed == timeline.elapsed == 45
    strip = timeline.epoch_timeline
    QTest.mouseClick(
        strip,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(strip.x_at(30)), round(strip.plot_bounds().center().y())),
    )
    assert timeline.elapsed == pytest.approx(30, abs=0.1)
    assert timeline.dial_samples[0].vector is None
    assert timeline.dial_samples[0].angular_speed == 0
    assert timeline.dial_samples[0].message == "No stimulus"
    stopped = source.model_copy(
        update={"phase_x": Hold(kind="hold"), "phase_y": Hold(kind="hold")}
    )
    program = program.model_copy(
        update={"sequence": (epoch.model_copy(update={"settings": (stopped,)}),)}
    )
    timeline.set_program(program, "", "Rotate only")
    timeline.set_elapsed(0)
    # Stationary translation has no arrow.
    assert timeline.dial_samples[0].vector is None
    assert vector_text(timeline.dial_samples[0]) == "0 deg/s · 0°"
    assert timeline.dial_samples[0].angular_speed == -15
    timeline.clear("Unavailable")
    assert not timeline.dial_samples and not timeline.dials
    assert not timeline.epochs and timeline.epoch_timeline.message == "Unavailable"
    timeline.close()


@pytest.mark.parametrize(
    "maximum, expected",
    [
        (0, (0, 5)),
        (9, (0, 5, 10)),
        (30, (0, 10, 20, 30)),
        (96, (0, 20, 40, 60, 80, 100)),
    ],
)
def test_preview_motion_ticks(maximum, expected):
    from cephvr.gui.preview_motion_plot import plot_ticks

    assert plot_ticks(maximum) == expected


@pytest.mark.parametrize(
    "independent,mixed_units", [(False, False), (True, False), (True, True)]
)
def test_preview_motion_overlay_linked_baseline_and_independent(
    app, independent, mixed_units
):
    from math import hypot

    from cephvr.gui.preview_timeline import StimulusTimeline
    from cephvr.gui.protocol_document import review_program
    from cephvr.visual_stimulus.config.models.program_model import (
        Constant,
        Hold,
        PhysicalSpace,
        Rate,
        SurfaceMap,
    )

    program = review_program()
    epoch = program.sequence[1]
    texture = epoch.settings[0]
    settings = []
    baseline = []
    for index, face in enumerate(("bottom", "left", "right", "front")):
        item = texture.model_copy(
            update={
                "instance_id": face,
                "space": texture.space.model_copy(update={"surfaces": (face,)}),
                "linked_to": None
                if index == 0 or (independent and face == "front")
                else "bottom",
                "phase_x": Rate(
                    kind="rate", function=Constant(kind="constant", value=index + 1)
                ),
            }
        )
        if mixed_units and face == "front":
            item = item.model_copy(
                update={
                    "space": PhysicalSpace(
                        kind="physical_surface",
                        frame_id="surface",
                        mappings=(
                            SurfaceMap(
                                surface_id="front", matrix=((1, 0, 0), (0, 1, 0))
                            ),
                        ),
                    )
                }
            )
        settings.append(item)
        baseline.append(
            item.model_copy(
                update={
                    "instance_id": face + "_baseline",
                    "linked_to": None,
                    "phase_x": Hold(kind="hold"),
                    "phase_y": Hold(kind="hold"),
                }
            )
        )
    program = program.model_copy(
        update={
            "sequence": (
                program.sequence[0].model_copy(update={"settings": tuple(baseline)}),
                epoch.model_copy(update={"settings": tuple(settings)}),
                program.sequence[2],
            )
        }
    )
    timeline = StimulusTimeline()
    timeline.resize(1100, 350)
    timeline.set_advanced(True)
    timeline.set_program(program, "", "Overlay")
    timeline.set_elapsed(2)
    # Stationary baselines and linked epochs retain every projector.
    assert timeline.dial_samples[0].vector is None
    timeline.set_elapsed(12)
    assert [s.name for s in timeline.sources] == (
        ["Bottom · reference", "Front", "Left", "Right"]
    )
    samples = timeline.dial_samples
    assert len(samples) == len(timeline.sources)
    # Mixed units stay on separate dials instead of sharing one scale.
    assert {sample.unit for sample in samples} == (
        {"mm/s", "deg/s"} if mixed_units else {"deg/s"}
    )
    assert len({sample.color for sample in samples}) == len(timeline.sources)
    assert hypot(*samples[0].vector) == pytest.approx(20)
    timeline.set_program(program, "", "Overlay")
    assert len(timeline.dial_samples) == len(timeline.sources)
    assert all(not dial.isHidden() for dial in timeline.dials)
    assert timeline.dial_samples[0].name == "Bottom · texture"
    timeline.show()
    app.processEvents()
    assert not timeline.grab().isNull()
    if independent:
        bad = settings[-1].model_copy(
            update={
                "motion": settings[-1].motion.model_copy(
                    update={
                        "x": Rate(
                            kind="rate", function=Constant(kind="constant", value=1)
                        )
                    }
                )
            }
        )
        changed_epoch = program.sequence[1].model_copy(
            update={"settings": (*settings[:-1], bad)}
        )
        timeline.set_program(
            program.model_copy(
                update={
                    "sequence": (
                        program.sequence[0],
                        changed_epoch,
                        program.sequence[2],
                    )
                }
            ),
            "",
            "Unsupported Front",
        )
        timeline.set_elapsed(12)
        valid, unsupported = timeline.dial_samples[:2]
        assert valid.vector is not None and not valid.message
        assert unsupported.name.startswith("Front")
        assert "Combined texture translation" in unsupported.message
    timeline.close()


def test_preview_grid_retains_pending_footprints_and_existing_targets(app):
    from cephvr.gui.preview_placement import PreviewSlot

    slot = PreviewSlot()
    slot.set_sources((PreviewView("a", "A", visible=True),))
    original = slot.frames["a"]
    slot.set_sources(
        (PreviewView("a", "A", pending=True), PreviewView("b", "B", visible=True))
    )
    assert slot.frames["a"] is original
    assert tuple(slot.frames) == ("a", "b")
    slot.set_sources(
        (PreviewView("a", "A", visible=True), PreviewView("b", "B", visible=True))
    )
    assert slot.frames["a"] is original
    slot.close()


def test_managed_camera_reconnect_retains_layout_without_claiming_visibility(window):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_cameras import ManagedCameras

    panel = window.devices.cameras
    state = pb.Snapshot()
    state.configuration.revision = 1
    camera = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    ).acquisition.behavioral
    camera.device.device_id = panel.drafts[0].serial
    camera.enabled = True
    state.acquisition_devices.behavioral.device_open = True
    panel.apply_view(
        DashboardView(
            previews=(PreviewView(panel.drafts[0].key, "Behavior cam", visible=True),)
        )
    )
    binding = ManagedCameras(panel, SimpleNamespace(), lambda *_: False)
    binding.pending = "camera"
    view = binding.install(state)[0]
    assert view.pending and not view.visible
    assert view.reason == "Reconnecting preview…"
    binding.pending = ""
    assert not binding.install(state)[0].pending


@pytest.mark.parametrize("parameter", ["Speed", "Direction", "Angular speed"])
def test_linked_texture_motion_variation_reports_reference_and_recovers(
    window, app, parameter
):
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.visual_stimulus.config.repetition_values import resolve_repetition

    program = add_stimulus(blank_program(), 0, "Texture", ("Bottom",))
    program = add_stimulus(program, 0, "Texture", ("Left",))
    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.timeline.set_screens(("Bottom", "Left"))
    editor.set_program(grouped_program(program))
    form = editor.subgroup
    form.add_variation()
    row = form.rows[0]
    row.target.setCurrentIndex(row.target.findText("All projectors"))
    row.parameter.setCurrentIndex(row.parameter.findData(parameter))
    row.method.setCurrentText("Random")
    row.random_fields["minimum"].setText("1")
    row.random_fields["maximum"].setText("10")
    form.apply()
    assert not form.notice.text()
    before = editor.program
    source = before.sequence[0].body[0].settings[0].instance_id
    panel = form.composer.rows["Left"].parameters
    assert panel.linked_to.findData(source) >= 0, [
        (panel.linked_to.itemText(i), panel.linked_to.itemData(i))
        for i in range(panel.linked_to.count())
    ]
    panel.linked_to.setCurrentIndex(panel.linked_to.findData(source))
    form.queue_update()
    QTest.qWait(50)
    assert editor.program == before
    assert f"{parameter} variation targets linked texture" in form.notice.text()
    assert "target to Bottom" in form.notice.text()
    assert form.notice.dialog is None
    row.target.setCurrentIndex(row.target.findText("Bottom"))
    form.queue_update()
    QTest.qWait(50)
    assert not form.notice.text() and not form.dirty
    epoch = editor.program.sequence[0].body[0]
    assert all(rule.instance_id == source for rule in epoch.repetition_rules)
    for repetition in (0, 1, 99):
        follower = resolve_repetition(
            epoch.settings, epoch.repetition_rules, repetition
        )[1]
        assert follower.linked_to == source
        assert follower.phase_x.kind == follower.phase_y.kind == "hold"
        assert follower.motion.rotation.kind == "hold"


@pytest.mark.parametrize("pattern", ["flat", "filtered_noise"])
def test_trial_preview_generates_recipe_pixels_and_caches_errors(
    app, tmp_path, pattern
):
    import json

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_file_stimulus
    from cephvr.gui.trial_preview_media import PreviewMedia

    path = tmp_path / "stimulus.texture.json"
    recipe = {
        "kind": "texture",
        "pattern": pattern,
        "params": {
            "texture_resolution": 32,
            "seed": 5,
            "color_a": [0.25, 0.25, 0.25],
            "color_b": [0.0, 0.0, 0.0],
        },
        "preview_file": "does-not-exist.png",
    }
    path.write_text(json.dumps(recipe))
    program = add_file_stimulus(
        blank_program(), 0, "Texture", ("Front",), str(tmp_path), str(path)
    )
    asset = program.sequence[0].settings[0].pattern.asset_id
    media = PreviewMedia(program, str(tmp_path), None)
    image = media.image(asset)
    assert not image.isNull() and image.width() == image.height() == 32
    assert not media.errors
    assert any(image.pixelColor(x, y).red() > 0 for x in range(32) for y in range(32))
    assert media.image(asset) is image
    media.close()
    path.write_text('{"pattern":"flat","params":{"texture_resolution":100000}}')
    assert media.image(asset).isNull()
    assert "allocation limit" in media.errors[asset]
    media.close()


@pytest.mark.parametrize("face", ["Front", "Left", "Right", "Bottom"])
@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_trial_preview_maps_usable_pixels_to_screen_without_margins(
    app, face, flip, axis
):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor, QImage, QPainter, QPolygonF

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.trial_preview_canvas import PreviewCanvas
    from cephvr.gui.trial_preview_media import PreviewMedia
    from cephvr.gui.trial_preview_rig import PreviewRig
    from cephvr.gui.trial_preview_surfaces import (
        PreviewCorrection,
        PreviewGeometry,
        PreviewSurface,
    )

    # Noncentral crop on landscape walls and a portrait Bottom output.
    width, height = (200, 100) if face != "Bottom" else (100, 200)
    correction = PreviewCorrection.from_draft(
        face,
        {
            "width": "80",
            "height": "80",
            "reference_width_px": str(width),
            "reference_height_px": str(height),
            "reference_x_px": "20",
            "reference_y_px": "20",
            "reference_x_mm": "20",
            "reference_y_mm": "20",
            "valid_width_px": "80",
            "valid_height_px": "80",
            "offset_x_px": "5",
            "offset_y_px": "-5",
            "flip_x": str(flip),
            "flip_y": str(flip),
        },
        (width, height),
    )
    assert not correction.error
    geometry = PreviewGeometry(
        {face: PreviewSurface(80, 80, correction=correction)}, None
    )
    media = PreviewMedia(blank_program(), "", None)
    canvas = PreviewCanvas(face, media, geometry)
    source = QImage(width, height, QImage.Format.Format_RGB32)
    source.fill(QColor("red"))
    painter = QPainter(source)
    painter.fillRect(
        0,
        0,
        width // 2 if axis == "x" else width,
        height // 2 if axis == "y" else height,
        QColor("blue"),
    )
    painter.end()
    view = PreviewRig(geometry, {face: canvas})
    view.frames[face] = canvas.correct_frame(source)
    target = QImage(120, 120, QImage.Format.Format_RGB32)
    target.fill(QColor("green"))
    painter = QPainter(target)
    view.draw_screen(
        painter,
        face,
        QPolygonF(
            [
                QPointF(10, 110),
                QPointF(110, 110),
                QPointF(110, 10),
                QPointF(10, 10),
            ]
        ),
    )
    painter.end()
    for position in (15, 50, 105):
        first = (20, position) if axis == "x" else (position, 20)
        second = (100, position) if axis == "x" else (position, 100)
        assert target.pixelColor(*first) == QColor("red" if flip else "blue")
        assert target.pixelColor(*second) == QColor("blue" if flip else "red")
    # Unused output pixels must not spill outside the physical screen.
    assert target.pixelColor(5, 60) == QColor("green")
    assert target.pixelColor(115, 60) == QColor("green")
    view.deleteLater()
    canvas.deleteLater()
    media.close()


@pytest.mark.parametrize("spin", [False, True])
def test_preview_linked_motion_moves_followers_and_replays_boundaries(spin):
    from cephvr.gui.projector_geometry import RigDimensions
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.trial_preview_plan import PreviewPlan
    from cephvr.gui.trial_preview_surfaces import PreviewGeometry
    from cephvr.visual_stimulus.config.models.program_model import Rate, Time

    program = blank_program()
    for face in ("Bottom", "Front", "Left", "Right"):
        program = add_stimulus(program, 0, "Texture", (face,))
    epoch = program.sequence[0]
    settings = list(epoch.settings)
    source = settings[0]
    rate = Rate.model_validate(
        {"kind": "rate", "function": {"kind": "constant", "value": 12 if spin else 0.2}}
    )
    source = source.model_copy(
        update={
            "initial": source.initial.model_copy(
                update={"x": 0.0 if spin else -5.0, "y": 0.0}
            ),
            **(
                {"motion": source.motion.model_copy(update={"rotation": rate})}
                if spin
                else {"phase_x": rate}
            ),
        }
    )
    settings = [source] + [
        s.model_copy(update={"linked_to": source.instance_id}) for s in settings[1:]
    ]
    epoch = epoch.model_copy(
        update={
            "settings": tuple(settings),
            "duration": epoch.duration.model_copy(
                update={"duration": Time(seconds="2")}
            ),
        }
    )
    program = program.model_copy(
        update={"sequence": (epoch, epoch.model_copy(update={"epoch_id": "second"}))}
    )
    geometry = (
        PreviewGeometry.from_drafts(
            RigDimensions(200, 300, 150, (100, 100, 75)),
            {
                face: {"width": "200", "height": "150", "subject_distance": "100"}
                for face in ("Front", "Left", "Right", "Bottom")
            },
        )
        .artifact()
        .display.geometry
    )
    with pytest.raises(ValueError, match="four screen planes"):
        PreviewPlan(program)
    plan = PreviewPlan(program, geometry)

    def states(t):
        return {
            layer.setting.instance_id: tuple(
                layer.values[k] for k in ("phase_x", "phase_y", "rotation")
            )
            for layer in plan.seek(t)
        }

    zero, one, three = states(0), states(1_000_000_000), states(3_000_000_000)
    assert all(one[k] != zero[k] for k in one)
    for k in one:
        assert tuple(three[k][i] - zero[k][i] for i in range(3)) == pytest.approx(
            tuple(3 * (one[k][i] - zero[k][i]) for i in range(3))
        )
    assert states(1_000_000_000) == one
    assert states(3_000_000_000) == three


@pytest.mark.parametrize("removed", [0, 1, 2])
@pytest.mark.parametrize("nested", [False, True])
def test_epoch_display_numbers_follow_deletion_and_restore(app, removed, nested):
    import json

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_nodes import edit_epoch
    from cephvr.gui.protocol_timeline import ProgramTimeline
    from cephvr.gui.timeline_details import epoch_heading
    from cephvr.visual_stimulus.config.models.program_model import Group

    original = blank_program()
    original, _ = edit_epoch(original, 0, "add")
    original, _ = edit_epoch(original, 1, "add")
    scope = ()
    if nested:
        group = Group.model_validate_json(
            json.dumps(
                dict(
                    kind="group",
                    group_id="Test",
                    repetitions=100,
                    order="as_listed",
                    order_unit="child_blocks",
                    conditions=None,
                    body=[n.model_dump(mode="json") for n in original.sequence],
                )
            )
        )
        original = original.model_copy(update={"sequence": (group,)})
        scope = (0,)
    timeline = ProgramTimeline(details=False)
    timeline.resize(1000, 250)
    timeline.show()
    timeline.set_program(original, scope=scope)
    old_ids = [n.epoch_id for n in timeline.nodes]
    changed, index = edit_epoch(original, (*scope, removed), "remove")
    timeline.set_program(changed, index, scope=scope)
    timeline.grab()
    labels = [
        text.split("\n")[0]
        for _, text in timeline.hover_text
        if text.startswith("Epoch ")
    ]
    assert labels == ["Epoch 1", "Epoch 2"]
    assert [n.epoch_id for n in timeline.nodes] == [
        v for i, v in enumerate(old_ids) if i != removed
    ]
    assert epoch_heading(timeline.nodes[index], index).startswith(
        f"Epoch {index + 1} ·"
    )
    timeline.set_program(original, scope=scope)
    timeline.grab()
    labels = [
        text.split("\n")[0]
        for _, text in timeline.hover_text
        if text.startswith("Epoch ")
    ]
    assert labels == ["Epoch 1", "Epoch 2", "Epoch 3"]
    timeline.close()
    timeline.deleteLater()


@pytest.mark.parametrize(
    "dx,dy", [(10.0, 0.0), (-10.0, 0.0), (0.0, 10.0), (0.0, -10.0)]
)
def test_bottom_portrait_mapping_preserves_rig_motion_and_measured_pitch(dx, dy):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF, QTransform

    from cephvr.gui.calibration_profile import MonitorBinding, face_mapping
    from cephvr.gui.projector_extent import usable_corners, valid_pixels
    from cephvr.gui.projector_geometry import RigDimensions, screen_corners
    from cephvr.gui.trial_preview_surfaces import PreviewCorrection

    values = dict(
        width=126,
        height=94,
        subject_distance=51,
        reference_width_px=720,
        reference_height_px=1280,
        reference_x_px=180,
        reference_y_px=320,
        reference_x_mm=24,
        reference_y_mm=44,
        valid_width_px=685,
        valid_height_px=940,
        offset_x_px=-10,
        offset_y_px=7,
        flip_x=False,
        flip_y=True,
    )
    numeric = {f"screens.Bottom.{k}": v for k, v in values.items()}
    corners = screen_corners(
        RigDimensions(120, 166, 110, (60, 93, 53)),
        "Bottom",
        {k: str(v) for k, v in values.items()},
        front_distance="91",
    )
    usable = usable_corners(corners, numeric, "Bottom", 720, 1280)
    depth = usable[1][1] - usable[0][1]
    cross_span = usable[0][0] - usable[3][0]
    assert depth == pytest.approx(940 * 44 / 320)
    assert cross_span == pytest.approx(685 * 24 / 180)
    assert valid_pixels(numeric, "Bottom", 720, 1280) == (685, 940)
    vertices, mirrored = face_mapping(
        {"values": numeric}, "Bottom", MonitorBinding("bottom", 0, 0, 720, 1280, 60, 8)
    )
    assert mirrored
    correction = PreviewCorrection.from_draft(
        "Bottom", {k: str(v) for k, v in values.items()}, (720, 1280)
    )
    assert not correction.error
    order = (0, 1, 3, 2)
    assert correction.source_uv == tuple(vertices[i]["uv"] for i in order)
    assert correction.corners == tuple(vertices[i]["xy"] for i in order)
    transform = QTransform()
    assert QTransform.quadToQuad(
        QPolygonF([QPointF(*vertices[i]["uv"]) for i in order]),
        QPolygonF([QPointF(*vertices[i]["xy"]) for i in order]),
        transform,
    )
    start = transform.map(QPointF(0.5, 0.5))
    end = transform.map(QPointF(0.5 + dx / depth, 0.5 + dy / cross_span))
    # Raw image top faces the head; raw +X faces subject-left through the mirror.
    assert (end.y() - start.y()) * 1280 * (44 / 320) == pytest.approx(-dx)
    assert (end.x() - start.x()) * 720 * (24 / 180) == pytest.approx(-dy)


def test_owned_dialogs_follow_style_changes_and_new_dialogs(window, app):
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

    from cephvr.gui.theme import COLORS, RETRO_COLORS

    warning = QMessageBox(
        QMessageBox.Icon.Warning, "Warning", "Keep these details", parent=window
    )
    tool = QDialog(window)
    layout = QVBoxLayout(tool)
    text = QLabel("External window")
    layout.addWidget(text)
    warning.show()
    tool.show()
    try:
        for name, colors in (
            ("retro_console", RETRO_COLORS),
            ("standard", COLORS),
            ("retro_console", RETRO_COLORS),
        ):
            window.appearance.select(name, persist=False)
            app.processEvents()
            fresh = QMessageBox(
                QMessageBox.Icon.Information,
                "New warning",
                "New details",
                parent=window,
            )
            fresh.show()
            app.processEvents()
            try:
                for dialog in (warning, tool, fresh):
                    assert (
                        dialog.palette().color(QPalette.ColorRole.Window).name()
                        == colors.window
                    )
                    for label in dialog.findChildren(QLabel):
                        if label.text():
                            assert (
                                label.palette()
                                .color(QPalette.ColorRole.WindowText)
                                .name()
                                == colors.text
                            )
                            assert ("IBM Plex Mono" in label.font().family()) == (
                                name == "retro_console"
                            )
                assert warning.text() == "Keep these details"
                assert tool.isVisible()
            finally:
                fresh.close()
                fresh.deleteLater()
    finally:
        warning.close()
        tool.close()
        warning.deleteLater()
        tool.deleteLater()


def test_projector_brightness_adjust_review_and_authority_gates(
    window: DashboardWindow,
) -> None:
    panel = window.devices.projectors
    panel.review = True
    control = panel.brightness
    window.apply_view(review_view(Phase.CONFIGURATION))
    assert control.current.minimum() == 101 and control.current.maximum() == 2500
    control.current.setValue(350)
    control.adjust.click()
    assert "350 mA; no hardware command sent" in panel.console.toPlainText()
    assert not control.pending
    for view in (
        review_view(Phase.RUNNING),
        review_view(Phase.READY),
        review_view(Phase.CONFIGURATION, observer=True),
    ):
        window.apply_view(view)
        assert not control.adjust.isEnabled()
    control.apply_view(review_view(Phase.CONFIGURATION))
    panel.review = False
    values = []
    control.requested.connect(values.append)
    control.adjust.click()
    control.submit()
    assert values == [350] and control.pending
    assert not control.adjust.isEnabled()
    control.apply_view(review_view(Phase.CONFIGURATION, observer=True))
    control.finish()
    assert not control.adjust.isEnabled()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
@pytest.mark.parametrize("width", [320, 580])
def test_projector_brightness_layout(app, style, width):
    from PyQt6.QtWidgets import QAbstractSpinBox

    from cephvr.gui.projector_brightness import ProjectorBrightnessCard
    from cephvr.gui.theme import retro_stylesheet, stylesheet

    card = ProjectorBrightnessCard()
    card.setStyleSheet(retro_stylesheet() if style == "retro_console" else stylesheet())
    card.resize(width, card.sizeHint().height())
    card.show()
    app.processEvents()
    try:
        editor = QRect(card.current.mapTo(card, QPoint()), card.current.size())
        action = QRect(card.adjust.mapTo(card, QPoint()), card.adjust.size())
        assert abs(editor.bottom() - action.bottom()) <= 1
        assert editor.right() < action.left()
        assert card.rect().contains(editor) and card.rect().contains(action)
        assert card.adjust.width() >= card.adjust.sizeHint().width()
        assert card.current.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        assert card.current.value() == 101
    finally:
        card.close()
        card.deleteLater()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_mcu_test_buttons_fit_action_labels(window, app, style):
    window.page_buttons[2].click()
    window.devices.tabs.setCurrentIndex(1)
    window.appearance.select(style, persist=False)
    panel = window.devices.microcontroller
    for text in ("Test", "Stop", "Cancel"):
        for control in panel.test_buttons.values():
            control.setText(text)
        for _ in range(3):
            app.processEvents()
        for control in panel.test_buttons.values():
            if control.isVisible():
                assert control.width() >= control.sizeHint().width()
                assert control.parentWidget().rect().contains(control.geometry())


def test_managed_stimulus_preview_requires_current_setup_and_tracks_native_close():
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_stimulus_preview import stimulus_preview_view

    state = pb.Snapshot()
    state.configuration_values.current.backends.add(
        backend_name="visual_stimulus", enabled=True
    )
    assert (
        stimulus_preview_view(state).active
        and not stimulus_preview_view(state).available
    )
    state.session.context.session_id = str(uuid4())
    state.session.phase = pb.SESSION_PHASE_READY
    state.configuration.revision = 7
    participant = state.participants.add(connected=True, process_running=True)
    participant.process.role = "visual_stimulus"
    participant.process.generation = str(uuid4())
    view = state.stimulus_preview
    view.backend.backend_generation = participant.process.generation
    view.session.CopyFrom(state.session.context)
    view.configuration_revision = 7
    view.available = True
    view.visible = True
    assert (
        stimulus_preview_view(state).available and stimulus_preview_view(state).visible
    )
    view.visible = False
    assert (
        stimulus_preview_view(state).available
        and not stimulus_preview_view(state).visible
    )
    view.configuration_revision = 6
    assert not stimulus_preview_view(state).available
    view.configuration_revision = 7
    participant.connected = False
    assert not stimulus_preview_view(state).available


@pytest.mark.parametrize("linked", [False, True])
@pytest.mark.parametrize("velocity", [(30.0, 40.0), (-40.0, 30.0)])
def test_texture_drift_preserves_mm_speed_across_projector_pitches(linked, velocity):
    import math
    from types import SimpleNamespace

    from tests.visual_stimulus.test_compilation import (
        _linked_texture_fixture,
        _texture_rate,
    )

    from cephvr.gui.calibration_profile import MonitorBinding, face_mapping
    from cephvr.gui.projector_extent import usable_corners
    from cephvr.visual_stimulus.config.texture_links import linked_rates, rates
    from cephvr.visual_stimulus.rendering.layer_projection import physical_corners

    geometry, settings = _linked_texture_fixture()
    source = settings[0].model_copy(
        update={
            "phase_x": _texture_rate(-velocity[0] / 100),
            "phase_y": _texture_rate(-velocity[1] / 100),
        }
    )
    pixel_speeds = []
    for index, setting in enumerate([source, *settings[1:]]):
        face = setting.instance_id.title()
        width, height = (720, 1280) if face == "Bottom" else (1280, 720)
        pitch_x, pitch_y = 0.1 + index * 0.04, 0.15 + index * 0.06
        values = {
            f"screens.{face}.{key}": value
            for key, value in dict(
                width=120,
                height=120,
                reference_width_px=width,
                reference_height_px=height,
                reference_x_px=200,
                reference_y_px=200,
                reference_x_mm=200 * pitch_x,
                reference_y_mm=200 * pitch_y,
                valid_width_px=width - 100,
                valid_height_px=height - 80,
                offset_x_px=10,
                offset_y_px=-7,
            ).items()
        }
        surface = geometry.surfaces[index]
        names = ("bottom_left_mm", "bottom_right_mm", "top_right_mm", "top_left_mm")
        corners = usable_corners(
            [getattr(surface, name) for name in names], values, face, width, height
        )
        calibrated = surface.model_copy(update=dict(zip(names, corners, strict=True)))
        artifact = SimpleNamespace(
            display=SimpleNamespace(
                geometry=geometry.model_copy(update={"surfaces": (calibrated,)})
            )
        )
        if linked and index:
            phase_x, phase_y, _ = linked_rates(
                source, setting, geometry, source_rotation=0, target_rotation=0
            )
            vx = -phase_x * setting.pattern.period_x.value
            vy = -phase_y * setting.pattern.period_y.value
        else:
            independent = setting.model_copy(
                update={
                    "linked_to": None,
                    "phase_x": _texture_rate(
                        -velocity[0] / setting.pattern.period_x.value
                    ),
                    "phase_y": _texture_rate(
                        -velocity[1] / setting.pattern.period_y.value
                    ),
                }
            )
            vx, vy, _ = rates(independent)
        vertices, _ = face_mapping(
            {"values": values}, face, MonitorBinding(face, 0, 0, width, height, 60, 8)
        )
        by_uv = {tuple(v["uv"]): v["xy"] for v in vertices}

        def output_position(
            x,
            y,
            artifact=artifact,
            surface=surface,
            setting=setting,
            by_uv=by_uv,
            width=width,
            height=height,
        ):
            snapshot = SimpleNamespace(
                state=(("x", x), ("y", y), ("width", 1), ("height", 1), ("rotation", 0))
            )
            projected = physical_corners(
                artifact, snapshot, surface.surface_id, setting.space.mappings[0]
            )
            u, v = (0.5 + sum(p[i] for p in projected) / 8 for i in (0, 1))
            return tuple(
                (
                    by_uv[0, 0][i]
                    + u * (by_uv[1, 0][i] - by_uv[0, 0][i])
                    + v * (by_uv[0, 1][i] - by_uv[0, 0][i])
                )
                * size
                for i, size in enumerate((width, height))
            )

        start, end = output_position(0, 0), output_position(vx, vy)
        dx, dy = (end[i] - start[i] for i in (0, 1))
        # A feature's displacement over one second must remain 50 mm on every face.
        assert math.hypot(dx * pitch_x, dy * pitch_y) == pytest.approx(50)
        pixel_speeds.append(math.hypot(dx, dy))
    assert len({round(speed, 6) for speed in pixel_speeds}) == 4


@pytest.mark.parametrize(
    "subject", ["0000", "0001", "1234", "", "123", "12345", "ABCD", "12a4", "１２３４"]
)
def test_four_digit_subject_and_species_setup(window, subject):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.dashboard import SPECIES
    from cephvr.gui.managed_config import (
        install_subject_metadata,
        subject_metadata_from_fields,
    )

    dashboard = window.dashboard
    dashboard.apply_view(review_view(Phase.CONFIGURATION))
    assert not dashboard.species.isEditable()
    assert [
        dashboard.species.itemText(i) for i in range(dashboard.species.count())
    ] == list(SPECIES)
    for species in SPECIES:
        config = pb.ExperimentConfiguration(subject="0001")
        config.subject_metadata.species = species
        install_subject_metadata(dashboard, config)
        assert dashboard.subject_id.text() == "0001"
        assert subject_metadata_from_fields(dashboard).species == species
    dashboard.subject_id.setText(subject)
    requested = []
    dashboard.action_requested.connect(requested.append)
    dashboard.setup()
    valid = len(subject) == 4 and subject.isascii() and subject.isdigit()
    assert requested == (["Setup"] if valid else [])
    assert dashboard.subject_id.text() == subject
    dashboard.subject_id.setText("0001")
    dashboard.set_species("Historical species")
    assert dashboard.species.currentText() == "Historical species"
    assert (
        not dashboard.species.model().item(dashboard.species.currentIndex()).isEnabled()
    )
    assert subject_metadata_from_fields(dashboard).species == "Historical species"
    requested.clear()
    dashboard.setup()
    assert not requested
    dashboard.set_species("sepia pharaonis")
    assert dashboard.species.currentText() == "Sepia Pharaonis"
    assert dashboard.species.count() == 3
    dashboard.set_species("")
    requested.clear()
    dashboard.setup()
    assert requested == ["Setup"]  # Optional metadata remains absent when unset.


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_texture_setup_checklist_retains_stages_through_ready(window, app, style):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_progress import ActionProgress

    window.appearance.select(style, persist=False)
    consoles = (window.dashboard.log_console, window.devices.projectors.console)
    for console in consoles:
        console.clear()

    def update(_target, *args):
        for console in consoles:
            console.action_entry(*args)

    log = ActionProgress(lambda *_: None, update)
    state = pb.Snapshot(controller_generation="controller")
    state.session.context.session_id = "session"
    state.session.phase = pb.SESSION_PHASE_SETTING_UP
    participant = state.participants.add()
    participant.process.role = "visual_stimulus"
    participant.process.generation = "renderer"
    participant.preparation_progress = "Decoding textures: 0/500"
    log.install(1, state)
    originals = [console.toPlainText()[:STAMP_WIDTH] for console in consoles]
    for console in consoles:
        console.appendPlainText("Unrelated camera observation")
    for count in range(1, 501):
        participant.preparation_progress = f"Decoding textures: {count}/500"
        log.install(1, state)
    participant.preparation_progress = "Uploading initial textures: 8/40"
    log.install(1, state)
    for console, stamp in zip(consoles, originals, strict=True):
        rows = console.toPlainText().splitlines()
        assert len(rows) == 3
        assert rows[0] == stamp + "[STIMULUS]  Decoding textures: 500/500"
        assert rows[2].endswith("Uploading initial textures: 8/40")
        assert rows[1].endswith("Unrelated camera observation")
        assert "[Done]" not in console.toPlainText()
    participant.ready.required_checks_passed = True
    log.install(1, state)
    for console in consoles:
        rows = console.toPlainText().splitlines()
        assert len(rows) == 3
        assert rows[0].endswith("500/500 [Done]")
        assert rows[2].endswith("8/40 [Done]")
    app.processEvents()


def test_in_place_progress_preserves_reader_selection_and_scroll(window, app):
    from PyQt6.QtGui import QTextCursor

    console = window.dashboard.log_console
    console.clear()
    console.action_entry(("loading",), "Visual stimulus · Decoding: 0/500")
    for number in range(100):
        console.appendPlainText(f"Observation {number}")
    app.processEvents()
    document = console.document()
    cursor = QTextCursor(document.findBlockByNumber(40))
    cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
    console.setTextCursor(cursor)
    selected = console.textCursor().selectedText()
    scroll = console.verticalScrollBar()
    scroll.setValue(20)
    before = scroll.value()
    console.action_entry(("loading",), "Visual stimulus · Decoding: 250/500")
    app.processEvents()
    assert scroll.value() == before
    assert console.textCursor().selectedText() == selected
    anchor = console.firstVisibleBlock().text()
    console.action_entry(
        ("loading",), "Visual stimulus · " + "Long wrapping preparation stage " * 20
    )
    app.processEvents()
    assert console.firstVisibleBlock().text() == anchor
    assert console.textCursor().selectedText() == selected
    scroll.setValue(scroll.maximum())
    console.action_entry(("loading",), "Visual stimulus · Decoding: 500/500")
    app.processEvents()
    assert scroll.value() == scroll.maximum()
    assert document.blockCount() == 101


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_log_categories_expand_to_longest_without_replacing_rows(window, app, style):
    from PyQt6.QtGui import QTextCursor

    window.appearance.select(style, persist=False)
    console = window.dashboard.log_console
    console.clear()
    console.append_entry(
        "Configuration · restored", "configuration details", error=False
    )
    first = console.document().begin()
    stamp = first.text()[:STAMP_WIDTH]
    metadata = first.userData()
    console.action_entry(("loading",), "Visual stimulus · loading")
    loading = console.document().lastBlock()
    console.appendPlainText("Controller · connected")
    rows = console.toPlainText().splitlines()
    assert (
        len(
            {
                row.index(word)
                for row, word in zip(
                    rows, ("restored", "loading", "connected"), strict=True
                )
            }
        )
        == 1
    )
    assert first.text().startswith(stamp) and first.userData() is metadata
    assert console.document().findBlockByNumber(1) == loading
    cursor = QTextCursor(first)
    cursor.setPosition(first.position() + first.text().index("restored"))
    cursor.movePosition(
        QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
    )
    console.setTextCursor(cursor)
    console.appendPlainText("Category much longer · extended")
    assert console.textCursor().selectedText() == "restored"
    console.action_entry(("loading",), "Visual stimulus · uploaded")
    console.action_entry(("loading",), "", "Done")
    rows = console.toPlainText().splitlines()
    assert len(rows) == 4
    assert (
        len(
            {
                row.index(word)
                for row, word in zip(
                    rows, ("restored", "uploaded", "connected", "extended"), strict=True
                )
            }
        )
        == 1
    )
    assert rows[1].endswith("uploaded [Done]")
    assert first.userData() is metadata
    console.appendPlainText("Configuration · repeated")
    console.appendPlainText("Configuration · repeated")
    assert len(console.toPlainText().splitlines()) == 5
    app.processEvents()


def test_category_expansion_preserves_reading_position_and_resets_on_clear(window, app):
    console = window.dashboard.log_console
    console.clear()
    console.action_entry(("loading",), "Setup · progress")
    for index in range(100):
        console.appendPlainText(f"Setup · Observation {index}")
    app.processEvents()
    scroll = console.verticalScrollBar()
    scroll.setValue(20)
    anchor = console.firstVisibleBlock()
    console.action_entry(("loading",), "A much longer category · progress")
    app.processEvents()
    assert console.firstVisibleBlock() == anchor
    assert console.document().blockCount() == 101
    console.clear()
    console.appendPlainText("Setup · reset")
    assert console.toPlainText()[STAMP_WIDTH:] == "[SETUP]     reset"


@pytest.mark.parametrize(
    "message", ["Plain message", " · Missing subject", "[MCU] Already tagged"]
)
def test_log_entry_paths_always_include_category(window, message):
    from cephvr.gui.log_format import CATEGORY_PREFIX

    console = window.dashboard.log_console
    console.clear()
    console.setPlainText(message)
    console.appendPlainText(message + " appended")
    console.append_entry(message, "diagnostic details")
    console.action_entry(("progress",), message)
    console.action_entry(("progress",), message + " updated")
    console.action_entry(("progress",), "", "Done")
    rows = console.toPlainText().splitlines()
    assert len(rows) == 4
    assert all(CATEGORY_PREFIX.match(row[STAMP_WIDTH:]) for row in rows)
    assert (
        all(row.count("[MCU]") == 1 for row in rows)
        if message.startswith("[MCU]")
        else all("[GUI]" in row for row in rows)
    )
    assert rows[-1].endswith("updated [Done]")


def test_preview_window_supplies_current_profile_or_edited_geometry(
    window, monkeypatch
):
    import json

    from cephvr.visual_stimulus.config.models.display_profile import Geometry

    projectors = window.devices.projectors
    for key, value in zip(
        projectors.rig_editor.fields, (200, 300, 150, 100, 100, 75), strict=True
    ):
        projectors.rig_editor.fields[key].setText(str(value))
    drafts = {
        face: {"width": "200", "height": "150", "subject_distance": "200"}
        for face in ("Front", "Left", "Right", "Bottom")
    }
    geometry = Geometry.model_validate_json(
        json.dumps(projectors.rig_editor.geometry_payload(drafts))
    )
    projectors.calibration_files.profile = {
        "geometry": geometry.model_dump(mode="json")
    }
    projectors._geometry_dirty = False
    window.update_preview_timeline()
    preview = window.dashboard.preview_workspace.timeline
    assert preview.plan.geometry == geometry
    changed = geometry.model_copy(update={"observer_mm": (101.0, 100.0, 75.0)})
    monkeypatch.setattr(
        projectors.rig_editor,
        "geometry_payload",
        lambda drafts: changed.model_dump(mode="json"),
    )
    projectors._geometry_dirty = True
    window.update_preview_timeline()
    assert preview.plan.geometry == changed
    monkeypatch.setattr(projectors.rig_editor, "geometry_payload", lambda drafts: {})
    window.update_preview_timeline()
    assert preview.plan.geometry is None


@pytest.mark.parametrize("ready", [True, False])
def test_setup_checklist_camera_scope_completion_and_reconnect(window, ready):
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.action_progress import ActionProgress

    console = window.dashboard.log_console
    console.clear()
    log = ActionProgress(
        lambda *_: None, lambda _target, *args: console.action_entry(*args)
    )
    state = pb.Snapshot(controller_generation="controller")
    state.session.context.session_id = "session"
    state.session.phase = pb.SESSION_PHASE_SETTING_UP
    state.configuration.revision = 4
    state.configuration_values.revision = 4
    backend = state.configuration_values.current.backends.add(
        backend_name="acquisition", enabled=True
    )
    backend.acquisition.behavioral.enabled = True
    backend.acquisition.eye_tracking.enabled = True
    participant = state.participants.add()
    participant.process.role = "acquisition"
    participant.process.generation = "camera-owner"
    state.microcontroller.observation.connection_id = "connection"
    state.microcontroller.observation.observed_monotonic_ns = 1
    log.install(1, state)
    initial = console.toPlainText()
    assert "[BEH CAM]" in initial and "[EYE CAM]" in initial
    assert "[TRK CAM]" not in initial
    assert "Reading connection and configuration… [Done]" in initial
    assert "Ready" not in initial
    state.ClearField("configuration_values")
    log.install(1, state)
    assert console.toPlainText() == initial
    participant.ready.required_checks_passed = ready
    state.session.phase = (
        pb.SESSION_PHASE_READY if ready else pb.SESSION_PHASE_CONFIGURATION
    )
    log.install(1, state)
    rows = console.toPlainText().splitlines()
    camera_rows = [row for row in rows if "Preparing camera for session" in row]
    assert len(camera_rows) == 2
    assert all(
        row.endswith("[Done]" if ready else "[Unconfirmed]") for row in camera_rows
    )
    log.install(1, state)
    assert console.toPlainText().splitlines() == rows
    console.clear()
    log.install(2, state)
    assert "[Done]" not in console.toPlainText()
    assert "Preparing camera for session" not in console.toPlainText()


def test_runtime_commands_use_shared_validation_and_stop_choices(app):
    from cephvr.gui.dashboard import Dashboard

    dashboard = Dashboard(sample=True)
    preview = dashboard.preview_workspace
    buttons = dashboard.command_buttons
    actions = []
    dashboard.action_requested.connect(actions.append)
    dashboard.apply_view(review_view(Phase.CONFIGURATION))
    dashboard.subject_id.setText("")
    buttons["Start"].click()
    assert not actions
    assert "Subject ID" in preview.log_tail.toPlainText()
    dashboard.subject_id.setText("0001")
    buttons["Start"].click()
    assert actions == ["Setup"]
    dashboard.apply_view(review_view(Phase.READY))
    buttons["Start"].click()
    buttons["Stop"].click()
    assert actions[-2:] == ["Start", "Cancel Setup"]
    # Starting swaps the layout; the same System controls stay wired to the Dashboard.
    dashboard.apply_view(review_view(Phase.RUNNING))
    assert dashboard.runtime_layout
    buttons["Stop"].click()
    assert dashboard.stop_dialog.parent() is dashboard
    dashboard.stop_dialog.choice_buttons["Stop after trial"].click()
    assert actions[-1] == "Stop after trial"
    buttons["Stop"].click()
    dashboard.apply_view(review_view(Phase.RUNNING, observer=True))
    assert dashboard.stop_dialog is None
    before = list(actions)
    dashboard.session_controls.action_requested.emit("Start")
    assert actions == before
    dashboard.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("style", ["standard", "retro_console"])
def test_preview_log_tail_tracks_four_rows_and_in_place_results(window, app, style):
    window.appearance.select(style, persist=False)
    dashboard = window.dashboard
    source = dashboard.log_console
    tail = dashboard.preview_workspace.log_tail
    source.clear()
    for index in range(6):
        source.appendPlainText(f"Setup · Step {index}")
    source.action_entry(("setup-test",), "Setup · Preparing…")
    source.action_entry(("setup-test",), "Setup · Registering outputs…")
    source.action_entry(("setup-test",), "", "Done", "Confirmed")
    app.processEvents()
    assert tail.toPlainText().splitlines() == source.toPlainText().splitlines()[-4:]
    assert "Registering outputs… [Done]" in tail.toPlainText()
    assert tail.isReadOnly()
    assert tail.document().blockCount() == 4
    dialog = dashboard.preview_workspace
    show_previews(window)
    assert tail.height() == dialog.hud.height()
    assert dialog.timeline.property("role") != "card"
    controls = dashboard.session_controls
    start, stop = controls.command_buttons.values()
    assert start.geometry().center().y() == stop.geometry().center().y()
    assert abs(start.width() - stop.width()) <= 1
    row_host = start.parentWidget()
    assert row_host is not None
    assert abs(start.geometry().center().y() - row_host.rect().center().y()) <= 1
    assert row_host.y() > controls.caption.geometry().bottom()
    from PyQt6.QtGui import QColor, QPalette

    from cephvr.gui.theme import colors_for

    for card in (controls, dialog.hud_card, dialog.log_card):
        assert card.caption.palette().color(QPalette.ColorRole.WindowText) == QColor(
            colors_for(card).coral
        )
    source.clear()
    assert tail.toPlainText() == "\n\n\n"
    assert source.toPlainText() == ""


def test_review_session_commands_walk_phases_and_swap_preview_layout(window, app):
    """G02: Start swaps the Dashboard to the preview layout; review simulates phases."""
    controls = next(
        item for item in window.children() if isinstance(item, ReviewControls)
    )
    dashboard = window.dashboard

    def settle(phase: Phase) -> None:
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.start(8000)
        while dashboard.view.phase != phase and deadline.isActive():
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        assert dashboard.view.phase == phase

    settle(Phase.CONFIGURATION)
    assert not dashboard.runtime_layout
    dashboard.control_action("Start")
    settle(Phase.READY)
    assert not dashboard.runtime_layout
    assert dashboard.session_controls.parentWidget() is not None
    assert dashboard.left_layout.indexOf(dashboard.session_controls) == 0
    dashboard.control_action("Start")
    settle(Phase.RUNNING)
    app.processEvents()
    workspace = dashboard.preview_workspace
    assert dashboard.runtime_layout
    assert dashboard.pages.currentWidget() is workspace
    cell = workspace.top.itemAtPosition(0, 0)
    assert cell is not None and cell.widget() is dashboard.session_controls
    assert dashboard.left_layout.indexOf(dashboard.session_controls) == -1
    # The dummy run shows the epoch timeline and the motion dials.
    assert workspace.advanced_toggle.isChecked() and workspace.timeline.advanced
    assert workspace.timeline.isVisible() and workspace.details.isVisible()
    assert workspace.timeline.epochs and workspace.timeline.panels
    controls.simulate_action("Abort now")
    settle(Phase.ENDED)
    assert not dashboard.runtime_layout
    assert dashboard.pages.currentWidget() is dashboard.form
    assert dashboard.left_layout.indexOf(dashboard.session_controls) == 0
    # A manual phase choice cancels pending simulated steps.
    controls.simulate_action("Start")
    controls.set_phase(Phase.CONFIGURATION)
    for _ in range(40):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    assert dashboard.view.phase == Phase.CONFIGURATION
