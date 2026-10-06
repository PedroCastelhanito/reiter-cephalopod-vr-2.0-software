"""Native frontend behavior and ownership; no controller or rig execution."""

import sys
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, QRect, QSettings, QSize, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QPushButton,
    QWidget,
)

from cephvr.gui.layouts import tool_window_position
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import DashboardView, Phase, PreviewView, review_view
from cephvr.gui.window import DashboardWindow


@pytest.fixture(scope="module")
def app() -> QApplication:
    result = QApplication.instance()
    if result is None:
        result = QApplication([])
    assert isinstance(result, QApplication)
    apply_theme(result)
    return result


@pytest.fixture
def window(app: QApplication) -> Iterator[DashboardWindow]:
    result = DashboardWindow(sample=True)
    ReviewControls(result)
    result.show()
    app.processEvents()
    yield result
    result.close()
    result.deleteLater()
    app.processEvents()


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


def test_managed_spikeglx_connection_emits_read_only_intent(app: QApplication) -> None:
    from cephvr.gui.spikeglx import SpikeGLXPanel

    panel = SpikeGLXPanel()
    requested: list[bool] = []
    panel.connection_requested.connect(lambda: requested.append(True))
    panel.apply_view(DashboardView(connected=True))
    assert panel.action_buttons[0].isEnabled()
    assert not panel.editors[0].isEnabled()
    panel.action_buttons[0].click()
    assert requested == [True]
    panel.close()
    panel.deleteLater()
    app.processEvents()


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


@pytest.mark.windows
@pytest.mark.skipif(
    sys.platform != "win32", reason="named preview rings require Windows"
)
def test_native_latest_frame_viewer_reads_and_releases_ring(app: QApplication) -> None:
    pytest.importorskip("pypylon")
    from cephvr.acquisition.buffers.layout import allocation_size
    from cephvr.acquisition.buffers.records import FrameRecord
    from cephvr.acquisition.buffers.ring import SharedRing
    from cephvr.acquisition.camera.native_formats import pylon_pixel_format
    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.acquisition.v1 import messages_pb2 as acq
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.camera_viewer import PreviewReader
    from cephvr.shared.pixels.types import PixelLayout

    allocation, run_id = uuid4(), uuid4()
    owner = pb.ProcessIdentity(role="acquisition", generation=str(uuid4()))
    producer = pb.ProcessIdentity(
        role="acquisition_behavioral_worker", generation=str(uuid4())
    )
    consumer = pb.ProcessIdentity(role="gui", generation=str(uuid4()))
    layout = PixelLayout(2, 2, pylon_pixel_format("Mono8"), 2, 4)
    descriptor = acq.FrameBufferDescriptor(
        allocation_id=str(allocation),
        owner=owner,
        producer=producer,
        camera=camera_pb2.CAMERA_ROLE_BEHAVIORAL,
        kind=acq.FRAME_BUFFER_KIND_PREVIEW,
        layout_version=2,
        capacity_frames=1,
        shared_memory_name=f"Local\\cephvr-{allocation}-frames",
        configuration_revision=1,
        allocation_bytes=allocation_size(1, 4),
    )
    descriptor.preview.acquisition_run_id = str(run_id)
    descriptor.image.width = 2
    descriptor.image.height = 2
    descriptor.image.pixel_format = "Mono8"
    descriptor.image.row_stride_bytes = 2
    descriptor.image.image_payload_bytes = 4
    attachment = acq.FrameBufferAttachment(buffer=descriptor)
    attachment.sync.transfer_id = str(uuid4())
    attachment.sync.target.CopyFrom(owner)
    attachment.sync.event_name = f"Local\\cephvr-{allocation}-event"
    ring = SharedRing.create(attachment, layout, owner)
    producer_ring = None
    reader = None
    try:
        ring.reset_quiescent(run_id, prior_completion_confirmed=True)
        attachment.sync.target.CopyFrom(producer)
        producer_ring = SharedRing.attach(attachment, layout, producer)
        producer_ring.open_admission(run_id)
        attachment.sync.target.CopyFrom(consumer)
        reader = PreviewReader(attachment, run_id=str(run_id))
        errors: list[str] = []
        reader.failed.connect(errors.append)
        reader.start()
        producer_ring.publish(
            FrameRecord(1, 1, None, None, True, None), memoryview(b"\x00\x40\x80\xff")
        )
        producer_ring.publish(
            FrameRecord(2, 2, None, None, True, None), memoryview(b"\xff\x80\x40\x00")
        )
        deadline = time.monotonic() + 3
        latest = None
        while time.monotonic() < deadline and latest is None:
            app.processEvents()
            latest = reader.take_latest()
            time.sleep(0.01)
        assert latest is not None, errors
        assert latest[0] == b"\xff\x80\x40\x00"
        assert latest[1:3] == (2, 2)
    finally:
        if reader is not None:
            reader.stop()
            assert reader.wait(2000)
        if producer_ring is not None:
            producer_ring.close()
        ring.close()


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
        panel.action_buttons[0].click()
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
            panel.request("Test connection")
            assert panel.console.toPlainText() == before


@pytest.mark.parametrize("width", [720, 1175])
def test_devices_draft_reflows_without_horizontal_clipping(
    window: DashboardWindow, app: QApplication, width: int
) -> None:
    window.resize(width, 883)
    window.page_buttons[2].click()
    for index in range(4):
        window.devices.tabs.setCurrentIndex(index)
        app.processEvents()
        scroll = window.devices.panels[index].scrollers[0]
        assert scroll.horizontalScrollBar().maximum() == 0


def test_folder_picker_selection_cancellation_and_phase_lock(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(QFileDialog, "open", lambda self: None)
    field = window.dashboard.output_field
    field.editor.setText(str(tmp_path))
    field.browse.click()
    dialog = field.dialog
    assert dialog is not None
    assert dialog.directory().absolutePath() == str(tmp_path)
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
    window.dashboard.preview_button.setFocus()
    assert editor.text() == path and editor.toolTip() == path
    assert not editor.grab().isNull()
    editor.setFocus()
    editor.selectAll()
    assert editor.selectedText() == path
    editor.insert(r"D:\new folder")
    assert editor.toolTip() == r"D:\new folder"


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
    console.appendPlainText("Fresh")
    assert console.toPlainText() == "Fresh"


def test_preview_geometry_survives_recreation(
    app: QApplication, tmp_path: Path
) -> None:
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    first = DashboardWindow(settings=settings)
    first.show()
    first.dashboard.show_previews()
    dialog = first.dashboard.preview_dialog
    dialog.move(70, 60)
    app.processEvents()
    expected = dialog.frameGeometry()
    dialog.close()
    first.dashboard.show_previews()
    assert dialog.frameGeometry() == expected
    first.close()
    first.deleteLater()
    app.processEvents()
    second = DashboardWindow(
        settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    )
    second.show()
    second.dashboard.show_previews()
    app.processEvents()
    assert second.dashboard.preview_dialog.frameGeometry() == expected
    second.close()
    second.deleteLater()
    app.processEvents()


def test_review_intent_does_not_advance_session(window: DashboardWindow) -> None:
    dashboard = window.dashboard
    QTest.mouseClick(dashboard.command_buttons["Setup"], Qt.MouseButton.LeftButton)
    assert "Setup selected; no command sent" in dashboard.log_console.toPlainText()
    assert dashboard.view.phase == Phase.CONFIGURATION


def test_preview_selector_reuses_modeless_window_and_keeps_visibility(
    window: DashboardWindow, app: QApplication
) -> None:
    dashboard = window.dashboard
    assert not dashboard.session_controls.isAncestorOf(dashboard.preview_button)
    assert dashboard.preview_button.mapTo(window, QPoint()).y() < (
        dashboard.session_controls.mapTo(window, QPoint()).y()
    )
    assert dashboard.preview_button.mapTo(window, QPoint()).x() > window.width() / 2
    dashboard.preview_button.click()
    dialog = dashboard.preview_dialog
    assert dialog.isVisible() and not dialog.isModal()
    assert not dialog.findChildren(QPushButton)
    assert dialog.height() < 200
    assert all(
        control.width() >= control.sizeHint().width()
        for control in dialog.controls.values()
    )
    screen = window.screen()
    assert screen is not None
    assert dialog.frameGeometry().topLeft() == tool_window_position(
        window.frameGeometry(),
        dialog.frameGeometry().size(),
        screen.availableGeometry(),
    )
    dialog.controls["camera-1"].click()
    assert dialog.controls["camera-1"].isChecked()
    assert dashboard.view.phase == Phase.CONFIGURATION
    dialog.close()
    app.processEvents()
    dashboard.preview_button.click()
    assert dashboard.preview_dialog is dialog
    assert dialog.controls["camera-1"].isChecked()
    dashboard.preview_button.click()
    assert not dialog.isVisible()
    dashboard.preview_button.click()
    assert dialog.isVisible()
    dialog.controls["tracking"].click()
    dialog.controls["camera-1"].click()
    dialog.controls["tracking"].click()
    assert not any(item.visible for item in dashboard.view.previews)
    assert "no viewer command sent" in dashboard.log_console.toPlainText()
    window.select_page(1)
    assert not dashboard.preview_button.isVisible()
    window.select_page(0)
    assert dashboard.preview_button.isVisible()


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
    dialog = dashboard.preview_dialog
    dialog.controls["camera"].click()
    assert requests == [("camera", True)]
    assert not dialog.controls["camera"].isChecked()
    assert not dialog.controls["camera"].isEnabled()
    dialog.request("camera", True)
    assert len(requests) == 1
    dashboard.apply_view(
        replace(state, previews=(replace(item, reason="Open failed"),))
    )
    assert dialog.statuses["camera"].text() == "Open failed"
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
    dialog = dashboard.preview_dialog
    assert dialog.controls["camera"].isChecked()
    assert not dialog.controls["camera"].isEnabled()
    assert dialog.statuses["camera"].text() == "Offline"


@pytest.mark.parametrize(
    ("phase", "actions", "editable"),
    [
        (Phase.CONFIGURATION, {"Setup"}, True),
        (Phase.SETTING_UP, {"Stop"}, False),
        (Phase.READY, {"Start", "Stop"}, True),
        (Phase.STARTING, {"Stop"}, False),
        (Phase.RUNNING, {"Stop"}, False),
        (Phase.STOPPING, {"Stop"}, False),
        (Phase.FINALIZING, {"Stop"}, False),
        (Phase.ENDED, {"Setup"}, False),
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
    for width in (1440, 1100, 720, 1440):
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
    assert "Closed" in window.dashboard.runtime_console.toPlainText()
    controls.observer.setChecked(True)
    assert not window.dashboard.command_buttons["Setup"].isEnabled()


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
    }
    assert titles == {
        "System controls",
        "Session config",
        "Recordings",
        "Runtime HUD",
        "Activity log",
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


def test_hud_fits_content_and_log_fills_available_height(
    app: QApplication, window: DashboardWindow
) -> None:
    dashboard = window.dashboard
    panel_heights = []
    log_heights = []
    for height in (883, 1100):
        window.resize(1175, height)
        app.processEvents()
        right = dashboard.columns[1]
        assert dashboard.hud_card.y() == 0
        assert dashboard.log_card.geometry().bottom() == right.height() - 1
        assert dashboard.runtime_console.verticalScrollBar().maximum() == 0
        assert dashboard.log_console.height() > dashboard.log_console.minimumHeight()
        log_heights.append(dashboard.log_console.height())
        panel_heights.append(dashboard.runtime_console.height())
    assert panel_heights[1] == panel_heights[0]
    assert log_heights[1] - log_heights[0] == 1100 - 883
    original = dashboard.runtime_console.toPlainText()
    dashboard.runtime_console.setPlainText(
        original + "\nEXTRA  additional runtime evidence"
    )
    app.processEvents()
    assert dashboard.runtime_console.height() > panel_heights[0]
    dashboard.runtime_console.setPlainText(original)
    app.processEvents()
    assert dashboard.runtime_console.height() == panel_heights[0]
    setup, start, stop = (
        dashboard.command_buttons[name] for name in ("Setup", "Start", "Stop")
    )
    assert setup.geometry().bottom() < start.y() == stop.y()
    assert setup.x() == start.x()
    assert setup.geometry().right() == stop.geometry().right()
    assert abs(start.width() - stop.width()) <= 1
    indicators = list(dashboard.backend_indicators.values())
    assert len({indicator.y() for indicator in indicators}) == 1
    assert all(
        indicator.parentWidget() is dashboard.session_controls
        for indicator in indicators
    )
    assert max(indicator.geometry().bottom() for indicator in indicators) < setup.y()
    assert indicators[-1].geometry().right() < dashboard.session_controls.width()


def test_setup_serves_as_new_session_after_completion(window: DashboardWindow) -> None:
    dashboard = window.dashboard
    requests: list[str] = []
    dashboard.action_requested.connect(requests.append)
    assert list(dashboard.command_buttons) == ["Setup", "Start", "Stop"]
    dashboard.command_buttons["Setup"].click()
    window.apply_view(review_view(Phase.ENDED))
    dashboard.command_buttons["Setup"].click()
    assert requests == ["Setup", "New session"]
    assert dashboard.view.phase == Phase.ENDED
    assert "New session selected" in dashboard.log_console.toPlainText()


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


def test_runtime_indicators_are_independent_and_read_only(
    window: DashboardWindow,
) -> None:
    indicators = window.dashboard.backend_indicators
    assert not any(indicator.isChecked() for indicator in indicators.values())
    window.apply_view(review_view(Phase.READY))
    assert all(indicator.isChecked() for indicator in indicators.values())
    camera = indicators["Cameras"]
    QTest.mouseClick(camera, Qt.MouseButton.LeftButton)
    QTest.keyClick(camera, Qt.Key.Key_Space)
    assert camera.isChecked()
    assert "Cameras · Ready" == camera.accessibleName()
    window.apply_view(review_view(Phase.CONFIGURATION))
    camera.click()
    assert not camera.isChecked()
    assert "Not prepared" in camera.toolTip()


def test_preview_participation_gates_and_camera_draft_selection(
    window: DashboardWindow,
) -> None:
    cameras = window.devices.cameras
    dashboard = window.dashboard
    dialog = dashboard.preview_dialog
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
    cameras.preview_button.click()
    assert dialog.controls["camera-1"].isChecked()
    cameras.enable_controls[0].click()
    assert not dialog.controls["camera-1"].isEnabled()
    assert not dialog.names["camera-1"].isEnabled()
    assert not cameras.preview_button.isEnabled()
    requests = []
    dashboard.preview_requested.connect(lambda *args: requests.append(args))
    dialog.request("camera-1", True)
    cameras.toggle_preview()
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
    cameras.set_participation(0, True)
    cameras.toggle_connection()
    cameras.edit("trigger_frequency_hz", "9999")
    assert not cameras.drafts[0].enabled
    assert cameras.drafts[0].values["trigger_frequency_hz"] == "1200"


def test_camera_role_uniqueness_and_extra_preview_rows(window: DashboardWindow) -> None:
    cameras = window.devices.cameras
    cameras.role.setCurrentText("Tracking cam")
    assert cameras.selected.role == "Behavior cam"
    cameras.role.setCurrentText("Unassigned")
    assert "camera-1" not in window.dashboard.preview_dialog.controls
    cameras.table.selectRow(1)
    cameras.role.setCurrentText("Behavior cam")
    assert cameras.selected.role == "Behavior cam"
    extra = PreviewView("extra", "Side cam", active=False, available=True, reason="")
    window.apply_view(
        replace(
            window.dashboard.view, previews=(*window.dashboard.view.previews, extra)
        )
    )
    dialog = window.dashboard.preview_dialog
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
    assert "not applied" in cameras.status_column.hud.toPlainText()
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
            window.resize(1175, height)
            app.processEvents()
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
    window.resize(1175, 940)
    app.processEvents()
    hud_top = window.dashboard.hud_card.mapTo(window, QPoint()).y()
    window.page_buttons[2].click()
    from cephvr.gui.theme import SIZES

    bar = window.devices.tab_bar
    for width in (1175, 720, 1175):
        window.resize(width, 940)
        for index in (2, 0, 3, 1):
            app.processEvents()
            QTest.mouseClick(
                bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(index).center()
            )
            app.processEvents()
            assert window.devices.tabs.currentIndex() == index
            panel = window.devices.panels[index]
            left = panel.columns[0]
            assert window.devices.navigation.parentWidget() is left
            assert bar.isVisible()
            assert bar.width() == left.width()
            assert bar.tabRect(3).right() == bar.width() - 1
            if width == 1175:
                hud = panel.layout_card if index == 2 else panel.columns[1].hud_card
                border_top = (
                    hud.mapTo(window, QPoint()).y()
                    + hud.caption.geometry().center().y()
                )
                assert abs(bar.mapTo(window, QPoint()).y() - border_top) <= 1
            card = left.layout().itemAt(1).widget()
            assert card.y() >= window.devices.navigation.height() + SIZES.card_gap
            assert (
                window.devices.panels[index]
                .scrollers[0]
                .horizontalScrollBar()
                .maximum()
                == 0
            )
            if width == 1175:
                assert (
                    panel.layout_card if index == 2 else panel.columns[1].hud_card
                ).mapTo(window, QPoint()).y() == hud_top
    window.page_buttons[0].click()
    app.processEvents()
    assert window.dashboard.hud_card.mapTo(window, QPoint()).y() == hud_top
    assert window.dashboard.preview_button.parentWidget() is window.page_header


def test_camera_batch_check_preserves_selection_and_connections(
    window: DashboardWindow,
) -> None:
    cameras = window.devices.cameras
    cameras.enable_controls[1].setChecked(False)
    cameras.table.selectRow(1)
    cameras.test_button.click()
    log = cameras.console.toPlainText()
    assert "requested for Behavior cam (REVIEW-001)" in log
    assert "requested for Tracking cam" not in log
    assert "not tested" in log
    assert cameras.selected is cameras.drafts[1]
    assert not any(draft.connected for draft in cameras.drafts)
    cameras.connect_button.click()
    assert cameras.connect_button.text() == "Disconnect"
    cameras.connect_button.click()
    assert cameras.connect_button.text() == "Connect"
    cameras.enable_controls[0].setChecked(False)
    assert not cameras.test_button.isEnabled()
    cameras.enable_controls[0].setChecked(True)
    window.apply_view(review_view(Phase.RUNNING))
    before = cameras.console.toPlainText()
    cameras.test_enabled()
    assert cameras.console.toPlainText() == before
    assert not cameras.test_button.isEnabled()


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
    panel.real_devices = True
    panel.refresh_inventory()
    assert [draft.serial for draft in panel.drafts] == ["40065509", "40747103"]
    assert [draft.role for draft in panel.drafts] == ["Behavior cam", "Tracking cam"]
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
    panel.pin_editors["camera-1"].setText("5")
    camera.enable_controls[1].setChecked(False)
    assert list(panel.pin_editors) == ["camera-1", "camera-2"]
    assert not panel.enable_controls["camera-2"].isChecked()
    assert not panel.pin_editors["camera-2"].isEnabled()
    assert panel.pins["camera-1"] == "5"
    panel.test_pin("camera-1")
    assert (
        "pin 5, requested 120 Hz output test; not tested" in panel.console.toPlainText()
    )
    panel.test_pin("camera-1")  # Stop the review before changing wiring.
    panel.flip_pin.setText("5")
    panel.test_pin("camera-1")
    assert "duplicate" in panel.console.toPlainText().splitlines()[-1]
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
    assert "×" in panel.table.item(0, 2).text()
    assert panel.diagram.outputs


def test_gui_display_number_is_local_and_shared_with_layout(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import projectors

    monkeypatch.setattr(projectors.QGuiApplication, "primaryScreen", lambda: None)
    panel = window.devices.projectors
    panel.request("Refresh displays")
    assert panel.table.item(0, 0).text() == "1"
    assert panel.diagram.outputs[0][0] == "1"
    assert "numbers are independent" in panel.console.toPlainText()
    assert panel.table.horizontalHeaderItem(0).text() == "CephVR ID"


def test_microcontroller_fixed_signal_tests_and_layout(window: DashboardWindow) -> None:
    panel = window.devices.microcontroller
    panel.port.addItem("COM7", "COM7")
    panel.port.setCurrentIndex(0)
    panel.trial_pin.setText("3")
    panel.flip_pin.setText("4")
    panel.test_buttons["trial-state"].click()
    assert "pin 3, active-high output test; not tested" in panel.console.toPlainText()
    panel.test_buttons["projector-flip"].click()
    assert (
        "pin 4, rising-edge input observation; not tested"
        in panel.console.toPlainText()
    )
    layout = panel.columns[0].layout()
    assert layout.indexOf(panel.io) < layout.indexOf(panel.triggers)
    captions = [label.text() for label in panel.triggers.findChildren(QLabel)]
    assert "RATE (Hz)" not in captions and "CAMERA" not in captions
    assert not hasattr(panel, "trial_polarity") and not hasattr(panel, "flip_edge")
    window.apply_view(review_view(Phase.RUNNING))
    before = panel.console.toPlainText()
    panel.test_pin("trial-state")
    panel.test_pin("projector-flip")
    assert panel.console.toPlainText() == before


def test_live_review_microcontroller_routes_bounded_tests(
    window: DashboardWindow,
) -> None:
    panel = window.devices.microcontroller
    panel.live_review = True
    panel.port.addItem("COM8", "COM8")
    panel.port.setCurrentIndex(0)
    panel.trial_pin.setText("9")
    panel.flip_pin.setText("2")
    connections: list[bool] = []
    tests: list[tuple[str, bool]] = []
    panel.connection_requested.connect(lambda: connections.append(True))
    panel.pin_test_requested.connect(lambda key, start: tests.append((key, start)))

    panel.action_buttons[1].click()
    assert connections == [True]
    assert not panel.port.isEnabled()
    panel.connection_pending = False  # Simulate the worker's matched connection result.
    panel.refresh_tests()
    panel.test_buttons["projector-flip"].click()
    assert tests == [("projector-flip", True)]
    assert not panel.port.isEnabled()
    panel.set_diagnostic("projector-flip", True, 0)
    panel.test_buttons["projector-flip"].click()
    assert tests[-1] == ("projector-flip", False)
    panel.set_diagnostic("projector-flip", False, 3)
    assert panel.port.isEnabled()
    assert "3 rising edges reported" in panel.console.toPlainText()


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
    saves: list[tuple[str, str, bool, str, bool, str | None, str | None]] = []
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
    panel.pin_editors["camera-1"].setText("D10")
    panel.pin_editors["camera-2"].setText("D11")
    assert saves == []  # Controller snapshots and unfinished drafts stay silent.
    panel.pin_editors["camera-2"].editingFinished.emit()
    panel.action_buttons[1].click()
    panel.test_buttons["trial-state"].click()
    panel.set_diagnostic("trial-state", True, 0)
    panel.test_buttons["trial-state"].click()

    assert saves == [("COM8", "D9", True, "D2", True, "D10", "D11")]
    assert connections == [True]
    assert pin_tests == [("trial-state", True), ("trial-state", False)]
    assert "no command sent" not in panel.console.toPlainText().splitlines()[-1]
    assert "Save pins" not in [b.text() for b in panel.findChildren(QPushButton)]
    assert not panel.enable_controls["projector-flip"].isEnabled()
    panel.set_diagnostic("trial-state", False, 0)
    panel.enable_controls["projector-flip"].setChecked(False)
    assert saves[-1] == ("COM8", "D9", True, "D2", False, "D10", "D11")
    panel.port.addItem("COM9", "COM9")
    panel.port.setCurrentIndex(panel.port.findData("COM9"))
    assert saves[-1][0] == "COM9"
    saved_count = len(saves)
    panel.set_saved_pins("COM9", "D9", True, "D2", False)
    assert len(saves) == saved_count
    panel.simulated_inventory = True
    panel.scan_ports()
    assert len(saves) == saved_count
    panel.apply_view(DashboardView(connected=True, has_control=False))
    panel.trial_pin.editingFinished.emit()
    assert len(saves) == saved_count


def test_managed_camera_enable_waits_for_controller_confirmation(
    window: DashboardWindow,
) -> None:
    panel = window.devices.cameras
    panel.managed = True
    requests: list[tuple[str, bool]] = []
    panel.enable_requested.connect(
        lambda serial, enabled: requests.append((serial, enabled))
    )
    panel.drafts[0].enabled = False
    panel.apply_view(
        DashboardView(
            connected=True,
            has_control=True,
            configuration_wired=False,
            phase=Phase.CONFIGURATION,
        )
    )
    assert panel.enable_controls[0].isEnabled()
    panel.enable_controls[0].click()
    assert requests == [("REVIEW-001", True)]
    assert not panel.drafts[0].enabled
    assert panel.enable_controls[0].isChecked()
    assert not panel.enable_controls[0].isEnabled()
    panel.pending_enable.clear()
    panel.refresh_controls()
    assert not panel.enable_controls[0].isChecked()


def test_managed_camera_enable_explains_missing_external_input(
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
    assert requests == []
    assert not panel.enable_controls[0].isChecked()
    assert "FrameStart line source" in panel.console.toPlainText()


def test_managed_dashboard_exposes_explicit_control_acquisition(
    window: DashboardWindow,
) -> None:
    requested: list[bool] = []
    window.dashboard.control_requested.connect(lambda: requested.append(True))
    window.apply_view(
        DashboardView(connected=True, has_control=False, configuration_wired=False)
    )
    assert window.dashboard.control_button.isVisible()
    assert window.dashboard.control_button.isEnabled()
    assert "take control" in window.dashboard.control_hint.text().lower()
    window.dashboard.control_button.click()
    assert requested == [True]
    window.apply_view(
        DashboardView(connected=True, has_control=True, configuration_wired=False)
    )
    assert not window.dashboard.control_button.isEnabled()
    assert "control held" in window.dashboard.control_hint.text().lower()


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
    panel.trigger_source.setCurrentText("Internal clock")
    assert submissions[-1][1] == "Internal clock"
    preset = tmp_path / "external.pfs"
    preset.write_text(
        "# GenApi persistence file\nTriggerSelector\tFrameStart\n"
        "TriggerMode\tOn\nTriggerSource\tLine3\n"
    )
    submitted_count = len(submissions)
    panel.preset_field.select_path(str(preset))
    assert len(submissions) == submitted_count + 1
    assert submissions[-1][1:4] == ("External controller", "Line3", str(preset))
    submitted_count = len(submissions)
    panel.fields["trigger_frequency_hz"].setText("0.01")
    panel.fields["trigger_frequency_hz"].editingFinished.emit()
    assert len(submissions) == submitted_count
    submitted_count = len(submissions)
    panel.apply_view(DashboardView(connected=True, has_control=False))
    panel.fields["trigger_frequency_hz"].editingFinished.emit()
    assert len(submissions) == submitted_count


@pytest.mark.asyncio
async def test_managed_camera_enable_updates_only_assigned_camera() -> None:
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
        client, "set_camera_enabled", {"serial": "40065509", "enabled": True}
    )
    assert len(requests) == 1
    method, request = requests[0]
    assert method == "UpdateConfiguration"
    assert request.expected_revision == 4
    updated = request.proposed.backends[0]
    assert updated.enabled
    assert updated.acquisition.behavioral.enabled
    assert not updated.acquisition.tracking.enabled
    assert not state.configuration_values.current.backends[0].enabled


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
async def test_managed_mcu_save_includes_camera_output_pins() -> None:
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
            "trial_pin": "D9",
            "trial_enabled": True,
            "flip_pin": "D2",
            "flip_enabled": True,
            "behavioral_pin": "D10",
            "tracking_pin": None,
        },
    )
    method, request = requests[0]
    assert method == "UpdateConfiguration"
    pulses = request.proposed.backends[0].acquisition.pulses
    assert pulses.behavioral.pin == "D10"
    assert pulses.tracking.pin == "D11"
    assert (
        state.configuration_values.current.backends[0].acquisition.pulses.behavioral.pin
        == ""
    )


def test_managed_microcontroller_forwards_only_saved_pin(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui import managed_mcu

    panel = window.devices.microcontroller
    panel.managed = True
    panel.set_saved_pins("COM8", "D9", True, "D2", True)
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
    acquisition.pulses.trial_state_pin = "D9"
    acquisition.pulses.projector_flip_pin = "D2"
    requests: list[tuple[str, dict[str, object]]] = []
    bridge = SimpleNamespace(
        request=lambda action, **options: requests.append((action, options)) or True
    )
    monkeypatch.setattr(managed_mcu.QTimer, "singleShot", lambda *_: None)
    binding = managed_mcu.ManagedMcu(panel, bridge, lambda: snapshot)

    binding.test_connection()
    binding.finished("mcu", True, "Completed")
    binding.test_pin("trial-state", True)
    panel.trial_pin.setText("D8")
    binding.test_pin("trial-state", True)

    assert requests == [
        ("mcu", {"kind": rpc.MICROCONTROLLER_COMMAND_KIND_CONNECT}),
        (
            "mcu",
            {
                "kind": rpc.MICROCONTROLLER_COMMAND_KIND_START,
                "signal": pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE,
            },
        ),
    ]
    assert (
        "Await controller confirmation of this pin assignment"
        in panel.console.toPlainText()
    )


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
        (CameraTrigger("camera-1", "Behavior cam", "External controller", "30", True),)
    )
    panel.pin_editors["camera-1"].setText("D10")
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
    binding.test_pin("camera-1", True)
    assert requests == [
        (
            "mcu",
            {
                "kind": rpc.MICROCONTROLLER_COMMAND_KIND_START,
                "signal": pb.MICROCONTROLLER_SIGNAL_KIND_BEHAVIORAL,
            },
        )
    ]
    panel.pin_editors["camera-1"].setText("D12")
    binding.test_pin("camera-1", True)
    assert len(requests) == 1
    assert (
        "Await controller confirmation of this pin assignment"
        in panel.console.toPlainText()
    )


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
        state=pb.Snapshot(),
        bridge=SimpleNamespace(request=lambda action: requests.append(action) or True),
        window=SimpleNamespace(
            dashboard=window.dashboard,
            devices=window.devices,
            finish_close=lambda: closed.append(True),
        ),
    )

    manager.cameras = SimpleNamespace(finished=lambda *_: None)
    ManagedGui.request_close(manager)
    assert manager.close_pending and not closed
    assert requests == ["save_configuration_history"]

    ManagedGui.command_finished(manager, "save_configuration_history", True, "Saved")
    assert not manager.close_pending
    assert closed == [True]


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


def test_review_draft_restores_local_configuration(
    app: QApplication, tmp_path: Path
) -> None:
    from cephvr.gui.review_draft import load_review_draft, save_review_draft

    path = tmp_path / "review_draft.json"
    first = DashboardWindow(sample=True)
    ReviewControls(first)
    first.dashboard.subject_id.setText("LAST-SUBJECT")
    first.devices.cameras.drafts[0].values["trigger_frequency_hz"] = "30"
    first.devices.microcontroller.set_saved_pins("COM8", "D9", True, "D2", True)
    first.devices.microcontroller.pins[first.devices.cameras.drafts[0].key] = "D10"
    first.protocol.editor.drafts[0].name = "Last trial"
    first.devices.projectors.rig_editor.fields["width"].setText("250")
    first.devices.spikeglx.editors[0].setText("10.0.0.2")  # type: ignore[attr-defined]
    save_review_draft(first, path)

    second = DashboardWindow(sample=True)
    ReviewControls(second)
    assert load_review_draft(second, path)
    assert second.dashboard.subject_id.text() == "LAST-SUBJECT"
    assert second.devices.cameras.drafts[0].values["trigger_frequency_hz"] == "30"
    assert second.devices.microcontroller.trial_pin.text() == "D9"
    assert second.devices.microcontroller.flip_pin.text() == "D2"
    assert (
        second.devices.microcontroller.pins[second.devices.cameras.drafts[0].key]
        == "D10"
    )
    assert second.protocol.editor.drafts[0].name == "Last trial"
    assert second.devices.projectors.rig_editor.fields["width"].text() == "250"
    assert second.devices.spikeglx.editors[0].text() == "10.0.0.2"  # type: ignore[attr-defined]
    for item in (first, second):
        item.close()
        item.deleteLater()
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
    panel.pin_editors["camera-1"].setText("5")
    panel.test_pin("camera-1")
    assert "camera-1" in panel.review_tests
    panel.enable_controls["camera-1"].click()
    assert not cameras.drafts[0].enabled
    assert not cameras.enable_controls[0].isChecked()
    assert not panel.review_tests
    assert not panel.pin_editors["camera-1"].isEnabled()
    panel.test_pin("camera-1")
    assert not panel.review_tests
    panel.enable_controls["camera-1"].click()
    assert cameras.drafts[0].enabled
    assert panel.pin_editors["camera-1"].text() == "5"
    cameras.enable_controls[0].click()
    assert not panel.enable_controls["camera-1"].isChecked()
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
    assert [panel.table.item(row, 0).text() for row in range(2)] == ["1", "2"]
    assert [index for index, _ in panel.diagram.outputs] == ["1", "2"]
    panel.projectors[panel.keys[0]].setCurrentText("Front")
    monkeypatch.setattr(
        projectors.QGuiApplication, "screens", lambda: [left, right, main]
    )
    panel.request("Refresh displays")
    assert panel.table.item(0, 0).text() == "1"
    assert panel.projectors[panel.keys[0]].currentText() == "Front"
    left.x, right.x = -1000, -3840
    panel.request("Refresh displays")
    assert panel.keys == ["right|||", "left|||"]
    assert panel.projectors["left|||"].currentText() == "Front"
    assert panel.table.item(1, 0).text() == "2"
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
    assert not timing.target.isEnabled() and not timing.mode.isEnabled()
    rig = panel.rig_editor
    for key, value in zip(rig.fields, (200, 300, 150, 100, 100, 75), strict=True):
        rig.fields[key].setText(str(value))
    assert panel.tank.rig is not None and panel.tank.rig.subject == (100, 100, 75)
    import json
    from types import SimpleNamespace

    from cephvr.visual_stimulus.config.models.display_profile import Geometry
    from cephvr.visual_stimulus.rendering.arena import off_axis_view_projection

    for key, value in zip(rig.projection_fields, (1, 1000, 0.1, 0.01), strict=True):
        rig.projection_fields[key].setText(str(value))
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
        "Synchronization",
        "Rig geometry",
    ]
    panel.setup_tabs.setCurrentIndex(2)
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
    panel.calibration.controls["Front", "scale_u"].setText("1.2")
    panel.calibration.controls["Front", "flip_x"].setChecked(True)
    panel.screen_editor.fields["Front", "width"].setText("200")
    assert panel.screen_editor.drafts["Front"]["scale_u"] == "1.2"
    assert panel.screen_editor.drafts["Front"]["flip_x"] == "True"
    assert panel.screen_editor.fields["Front", "width"].text() == "200"


def test_spikeglx_sources_preserve_maps_and_follow_enablement(window: DashboardWindow):
    devices = window.devices
    panel = devices.spikeglx
    camera = devices.cameras.drafts[0]
    panel.rows[camera.key][3].setText("3")
    devices.cameras.set_participation(0, False)
    assert not panel.rows[camera.key][3].isEnabled()
    devices.cameras.set_participation(0, True)
    assert panel.rows[camera.key][3].text() == "3"
    assert panel.rows[camera.key][3].isEnabled()
    devices.projectors.timing.pulse.setChecked(True)
    panel.rows["photodiode"][3].setText("7")
    devices.projectors.timing.pulse.setChecked(False)
    assert panel.rows["photodiode"][3].isHidden()
    devices.projectors.timing.pulse.setChecked(True)
    assert panel.rows["photodiode"][3].text() == "7"
    panel.add_input.click()
    assert "custom:1" in panel.rows
    window.apply_view(review_view(Phase.RUNNING))
    assert not panel.rows["custom:1"][3].isEnabled()
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
        corners = screen_corners(rig, face, values, front_distance="150")
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
    assert all(len(row) == 4 for row in window.devices.spikeglx.rows.values())


def test_all_screen_calibration_json_roundtrip_and_rejection(
    window: DashboardWindow, tmp_path: Path
):
    import json

    panel = window.devices.projectors
    files = panel.calibration_files
    panel.rig_editor.fields["width"].setText("200")
    panel.rig_editor.screen_distances["Left"].setText("150")
    panel.calibration.controls["Bottom", "offset_x"].setText("-12.5")
    panel.calibration.controls["Right", "flip_x"].setChecked(True)
    path = tmp_path / "calibration.json"
    expected = files.snapshot()
    panel.assignments["local-display"] = "Front"
    panel.participation["local-display"] = False
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
    assert panel.screen_editor.drafts["Bottom"]["offset_x"] == "-12.5"
    assert panel.screen_editor.drafts["Right"]["flip_x"] == "True"
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


def test_wheel_does_not_switch_epoch_tabs(
    window: DashboardWindow, app: QApplication
) -> None:
    from PyQt6.QtGui import QWheelEvent

    window.page_buttons[1].click()
    tabs = window.protocol.editor.modes
    tabs.setCurrentIndex(0)
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
    QApplication.sendEvent(tabs, event)
    app.processEvents()
    assert tabs.currentIndex() == 0


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

        def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
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
    panel.remove_buttons["custom:1"].click()
    assert "custom:1" not in panel.rows
    panel.add_input.click()
    window.apply_view(review_view(Phase.RUNNING))
    panel.remove_custom("custom:2")
    assert "custom:2" in panel.rows


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
        rig.dimensions(), "Right", panel.tank.screens["Right"], front_distance="150"
    )
    assert all(p[0] == 250 for p in corners)
    payload = panel.calibration_files.snapshot()
    assert "screens.Right.subject_distance" not in payload["values"]
    legacy = dict(
        payload,
        version=1,
        values=dict(payload["values"], **{"screens.Right.subject_distance": 170}),
    )
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
    assert json.loads(path.read_text()) == source
    panel.editor.duration.setText("1")
    panel.editor.edit_duration()
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
    original = editor.program
    parse_program_json(original.model_dump_json(), max_bytes=1_048_576)
    editor.timeline.setFocus()
    QTest.keyClick(editor.timeline, Qt.Key.Key_Right)
    assert editor.name.text() == "Flow"
    editor.duration.setText("21.000000001")
    editor.edit_duration()
    edited = editor.program
    assert edited.sequence[1].duration.duration.seconds == "21.000000001"
    assert edited.sequence[1].settings == original.sequence[1].settings
    editor.duration.setText("not a duration")
    editor.edit_duration()
    assert editor.program == edited
    assert editor.feedback.isVisible()
    editor.duration.setText("21.000000001")
    editor.add_button.click()
    assert editor.index == 1
    editor.trials.setCurrentRow(0)
    assert editor.program == edited
    group = Group(
        kind="group",
        group_id="repeat",
        repetitions=2,
        order="shuffle_each_repetition",
        order_unit="child_blocks",
        conditions=None,
        body=edited.sequence,
    )
    grouped = edited.model_copy(update={"sequence": (group,)})
    editor.set_program(grouped)
    assert editor.duration.isReadOnly()
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
    assert not panel.findChildren(QTableWidget)
    for width in (1175, 720, 1175):
        window.resize(width, 883)
        for _ in range(3):
            app.processEvents()
        editor = panel.editor
        assert editor.settings_card.width() == editor.width()
        assert editor.trial_card.y() == editor.timeline_card.y()
        assert editor.trial_card.geometry().right() < editor.timeline_card.x()
        assert editor.timeline_card.geometry().right() == editor.width() - 1
        assert editor.timeline_card.height() == editor.trial_card.height()
        assert editor.sequence_summary.alignment() == Qt.AlignmentFlag.AlignCenter
        assert editor.settings_card.y() > editor.timeline_card.geometry().bottom()
        viewport = panel.config_scroll.viewport()
        assert panel.config_scroll.widget().width() <= viewport.width()
        assert set(panel.assets.folders) == {"root"}
        assert not hasattr(panel.assets, "more")
        if width == 1175:
            assert panel.assets.y() == panel.program_card.y()
            assert panel.program_card.x() < panel.assets.x()
        panel.editor.rename_epoch()
        app.processEvents()
        panel.config_scroll.ensureWidgetVisible(panel.editor.duration)
        app.processEvents()
        point = panel.editor.duration.mapTo(viewport, QPoint())
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
    assert editor.timeline.height() >= 120 + sum(editor.timeline.lane_heights())
    for index in range(len(editor.timeline.nodes)):
        editor.timeline.choose(index, Qt.KeyboardModifier.NoModifier)
        app.processEvents()
        assert editor.timeline_card.height() == height
        assert editor.settings_card.y() == position
        assert editor.timeline.height() >= 120 + sum(editor.timeline.lane_heights())
    assert editor.program == original


def test_protocol_controls_and_enabled_screen_lanes(window: DashboardWindow) -> None:
    from PyQt6.QtWidgets import QLineEdit

    panel = window.protocol
    assert window.recordings.velocities.text() == ""
    assert window.recordings.velocity_label.text() == "Tracking velocities"
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

    panel = window.protocol
    editor = panel.editor
    editor.set_program(blank_program())
    editor.add_stimulus(preset)
    program = editor.program
    assert len(program.sequence[0].settings) == 1
    assert editor.parameters.apply()
    assert editor.program == program
    path = tmp_path / "program.json"
    panel.save_program(str(path))
    assert parse_program_json(path.read_text(), max_bytes=1_048_576) == program
    if preset in ("Image", "Video", "3D arena", "Looming image", "Image tile"):
        assert editor.parameters.asset_forms
    if preset == "Looming image":
        assert program.sequence[0].settings[0].width.kind == "keyframes"


def test_stimulus_parameter_edit_invalid_guard_and_media_root(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.select_node(1)
    parameters = editor.parameters
    value = parameters.fades.fade_in
    value.setText("0.4")
    parameters.fades.mark_changed()
    parameters.mark_changed()
    assert parameters.apply()
    assert editor.program.sequence[1].settings[0].opacity.kind == "keyframes"
    value.setText("-1")
    parameters.mark_changed()
    before = editor.program
    editor.select_node(2)
    assert editor.node_index == 1
    assert editor.program == before
    assert parameters.dirty
    value.setText("0.9")
    parameters.fades.mark_changed()
    editor.select_node(2)
    assert editor.node_index == 2
    editor.set_program(blank_program())
    editor.add_stimulus("Video")
    identity = editor.program.sequence[0].settings[0].asset_id
    parameters.asset_root = str(tmp_path)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"authoring-path-fixture")
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

    editor = window.protocol.editor
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

    editor = window.protocol.editor
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
    assert editor.program.assets[0].logical_path == "pattern.png"
    assert not parameters.message.text()
    assert editor.program.sequence[0].settings[0].pattern.period_x.value == 104
    assert parameters.file_rows
    assert parameters.advanced.isHidden()
    parameters.more.setChecked(True)
    assert not parameters.advanced.isHidden()
    parameters.more.setChecked(False)
    motion = parameters.forms[0]
    assert isinstance(motion, EpochMotion)
    motion.speed.setText("52")
    motion.direction.setText("90")
    motion.angular.setText("5")
    motion.changed.emit()
    assert parameters.apply()
    setting = editor.program.sequence[0].settings[0]
    assert setting.phase_x.function.value == pytest.approx(0, abs=1e-12)
    assert setting.phase_y.function.value == pytest.approx(-0.5)
    assert setting.motion.rotation.function.value == 5
    before = editor.program
    design.write_text(
        json.dumps(
            {
                "cephvr_asset_type": "texture_design",
                "kind": "texture",
                "params": {"tile_width_mm": 104},
                "preview_file": "missing.png",
            }
        )
    )
    identity = setting.pattern.asset_id
    parameters.set_media_path(identity, str(design))
    assert editor.program == before
    assert "missing" in parameters.message.toolTip()


def test_prepared_file_change_is_epoch_local(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
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
    editor.set_program(blank_program())
    editor.add_epoch_button.menu().actions()[0].trigger()
    assert len(editor.program.sequence) == 2
    assert editor.node_index == 1
    added = editor.program.sequence[1].epoch_id
    editor.edit_epoch("earlier")
    assert editor.program.sequence[0].epoch_id == added
    editor.edit_epoch("duplicate")
    assert len(editor.program.sequence) == 3
    assert len({node.epoch_id for node in editor.program.sequence}) == 3
    editor.edit_epoch("remove")
    assert len(editor.program.sequence) == 2
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
    editor.parameters.asset_root = str(tmp_path)
    before = editor.program
    editor.choose_stimulus("Image")
    assert editor.source_dialog is not None
    editor.source_dialog.reject()
    assert editor.program == before
    path = tmp_path / "image.png"
    path.write_bytes(b"authoring-only-file-fixture")
    editor.add_file("Image", str(path))
    assert len(editor.program.sequence[0].settings) == 1
    assert editor.program.assets[0].logical_path == "image.png"
    before = editor.program
    editor.add_file("Video", str(path))
    assert editor.program == before
    editor.choose_stimulus("Image")
    window.apply_view(review_view(Phase.RUNNING))
    assert editor.source_dialog is None


def test_file_first_epoch_insertion_and_history(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.parameters.asset_root = str(tmp_path)
    original = editor.program
    editor.choose_stimulus("Texture", new_epoch=True)
    assert editor.source_dialog is not None
    editor.source_dialog.reject()
    assert editor.program == original
    image = tmp_path / "tile.png"
    image.write_bytes(b"authoring-only fixture")
    editor.add_file("Texture", str(image), new_epoch=True)
    assert len(editor.program.sequence) == 2
    assert editor.node_index == 1
    added = editor.program
    assert added.sequence[1].settings[0].pattern.kind == "image_tile"
    editor.undo()
    assert editor.program == original
    editor.undo(True)
    assert editor.program == added
    editor.add_file("Video", str(image), new_epoch=True)
    assert editor.program == added
    assert len(editor.histories[0].past) == 1


def test_screen_overrides_and_layers_preserve_other_epochs(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_scope import change_scope, move_layer, split_screens

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.timeline.set_screens(("Left", "Right"))
    editor.add_stimulus("Texture")
    editor.edit_epoch("duplicate")
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
    editor.select_node(1)
    editor.timeline.set_screens(("Left",))
    editor.select_layer(1)
    assert editor.scope_controls.checks["right"].isChecked()
    assert "inactive" in editor.scope_controls.checks["right"].text()
    assert editor.program == split


def test_repeat_variation_uses_canonical_expansion_and_preserves_choreography(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import Variation, make_group
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.timeline.set_screens(("Left", "Right"))
    editor.add_stimulus("Texture")
    editor.edit_epoch("add")
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
            round(e.settings[0].phase_x.function.value, 6),
            round(e.settings[0].phase_y.function.value, 6),
        )
        for e in expanded
        if e.settings
    }
    assert rates == {(-0.5, 0.0), (0.0, -1.0)}
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
    editor.duration.setText("61")
    editor.edit_duration()
    assert node_at(editor.program, (0, 0)).duration.duration.seconds == "61"
    editor.leave_group()
    editor.edit_epoch("duplicate")
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


def test_group_dialog_rejects_bad_values_and_closes_on_authority_loss(
    window: DashboardWindow,
) -> None:
    editor = window.protocol.editor
    original = editor.program
    editor.open_group_dialog()
    dialog = editor.group_dialog
    assert dialog is not None
    dialog.repetitions.setText("0")
    dialog.apply()
    assert editor.program == original
    assert dialog.message.text()
    dialog.repetitions.setText("2")
    dialog.first.setCurrentIndex(0)
    dialog.last.setCurrentIndex(2)
    dialog.apply()
    assert len(editor.program.sequence) == 1
    assert editor.program.sequence[0].repetitions == 2
    editor.open_group_dialog()
    window.apply_view(review_view(Phase.RUNNING))
    assert editor.group_dialog is None


def test_motion_auto_commit_and_invalid_edit_undo(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    window.page_buttons[1].click()
    app.processEvents()
    motion = editor.parameters.forms[0]
    original = editor.program
    motion.speed.setFocus()
    motion.speed.selectAll()
    QTest.keyClicks(motion.speed, "30")
    editor.duration.setFocus()
    app.processEvents()
    assert editor.program != original
    assert editor.program.sequence[0].settings[0].phase_x.function.value == -1.5
    editor.undo()
    assert editor.program == original
    editor.duration.setText("invalid")
    editor.edit_duration()
    assert not editor.flush_parameters()
    editor.undo()
    assert editor.duration.text() == "60"
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
    assert expanded[0].settings[0].phase_x.function.value == -1.5
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


def test_stationary_texture_speed_variation_keeps_positive_x_direction(
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
    assert expanded[0].settings[0].phase_x.function.value < 0
    assert motion_numbers(expanded[0].settings[0].model_dump(mode="json"))[:2] == (
        10.0,
        0.0,
    )
    editor.duration.setText("70")
    editor.edit_duration()
    assert editor.sequence_summary.text() == "1 epoch · 70 s"


def test_expanded_close_and_trial_deletion(
    window: DashboardWindow, app: QApplication, tmp_path: Path
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
    editor.delete_trial_button.click()
    editor.delete_dialog.button(QMessageBox.StandardButton.Cancel).click()
    assert len(editor.drafts) == 2
    editor.delete_trial_button.click()
    editor.delete_dialog.button(QMessageBox.StandardButton.Yes).click()
    assert len(editor.drafts) == 1 and editor.program == original
    editor.delete_trial_button.click()
    editor.delete_dialog.button(QMessageBox.StandardButton.Yes).click()
    assert len(editor.drafts) == 1 and editor.program != original
    assert saved.exists()
    assert len(editor.histories) == editor.trials.count() == 1
    window.apply_view(review_view(Phase.RUNNING))
    editor.delete_trial()
    assert editor.delete_dialog is None


def test_projector_lane_layers_isolate_file_motion_and_removal(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.projector_layers import layer_title, layers_for
    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    original = editor.program
    window.page_buttons[1].click()
    app.processEvents()
    hit = next(
        rect
        for rect, index, face, layer in editor.timeline.hits
        if face == "Left" and layer == 0
    )
    QTest.mouseClick(
        editor.timeline, Qt.MouseButton.LeftButton, pos=hit.center().toPoint()
    )
    assert editor.selected_paths == ((0,),)
    assert editor.program == original
    editor.select_projector(0, "Left", 0)  # Selection alone never clones a stimulus.
    motion = next(
        form for form in editor.parameters.forms if isinstance(form, EpochMotion)
    )
    motion.speed.setText("12")
    motion.changed.emit()
    assert editor.parameters.apply()
    node = editor.program.sequence[0]
    right = node.settings[layers_for(editor.program, node, "Right")[0]]
    left_index = layers_for(editor.program, node, "Left")[0]
    assert right == original.sequence[0].settings[0].model_copy(
        update={
            "space": original.sequence[0]
            .settings[0]
            .space.model_copy(
                update={
                    "mappings": (original.sequence[0].settings[0].space.mappings[1],)
                }
            )
        }
    )
    assert node.settings[left_index].phase_x.function.value == -0.6
    editor.undo()
    assert editor.program == original
    editor.undo(True)
    assert editor.projector_layers.face == "Left"
    editor.parameters.asset_root = str(tmp_path)
    (tmp_path / "loom.png").write_bytes(b"prepared image fixture")
    (tmp_path / "video.mp4").write_bytes(b"prepared video fixture")
    editor.add_file("Looming image", str(tmp_path / "loom.png"))
    node = editor.program.sequence[0]
    assert len(layers_for(editor.program, node, "Left")) == 2
    assert len(layers_for(editor.program, node, "Right")) == 1
    assert layer_title(
        editor.program, node.settings[editor.projector_layers.layer]
    ).startswith("Looming")
    editor.reorder_layer(-1)
    node = editor.program.sequence[0]
    assert node.settings[layers_for(editor.program, node, "Left")[0]].kind == "image"
    assert node.settings[layers_for(editor.program, node, "Right")[0]] == right
    editor.select_projector(0, "Right", -1)
    editor.remove_stimulus()
    assert editor.projector_layers.layer == -1
    assert not editor.parameters.isVisible()
    editor.add_file("Video", str(tmp_path / "video.mp4"))
    node = editor.program.sequence[0]
    assert node.settings[layers_for(editor.program, node, "Right")[0]].kind == "video"
    assert len(layers_for(editor.program, node, "Left")) == 2
    loaded = parse_program_json(editor.program.model_dump_json(), max_bytes=1_048_576)
    editor.set_program(loaded)
    assert editor.program == loaded
    editor.timeline.set_screens(("Left",))
    assert layers_for(editor.program, editor.program.sequence[0], "Right")
    assert editor.projector_layers.face == "Right"


def test_projector_shared_file_replacement_and_stack_order(
    window: DashboardWindow, tmp_path: Path
) -> None:
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    editor.add_stimulus("Image")
    original = editor.program
    editor.parameters.asset_root = str(tmp_path)
    (tmp_path / "alternate.png").write_bytes(b"prepared image fixture")
    editor.select_projector(0, "Left", 1)
    asset_id = editor.program.sequence[0].settings[1].asset_id
    editor.parameters.set_media_path(asset_id, str(tmp_path / "alternate.png"))
    node = editor.program.sequence[0]
    right_layers = [node.settings[i] for i in layers_for(editor.program, node, "Right")]
    assert [s.instance_id for s in right_layers] == [
        s.instance_id for s in original.sequence[0].settings
    ]
    assert right_layers[1].asset_id == asset_id
    left_image = node.settings[editor.projector_layers.layer]
    assert left_image.asset_id != asset_id
    editor.reorder_layer(-1)
    node = editor.program.sequence[0]
    assert [
        node.settings[i].kind for i in layers_for(editor.program, node, "Left")
    ] == ["image", "texture"]
    assert [
        node.settings[i].kind for i in layers_for(editor.program, node, "Right")
    ] == ["texture", "image"]

    editor.add_stimulus("3D arena")
    node = editor.program.sequence[0]
    arena = next(
        i for i, setting in enumerate(node.settings) if setting.kind == "arena"
    )
    editor.select_projector(0, "Left", arena)
    assert not editor.parameters.isEnabled()
    before = editor.program
    editor.remove_stimulus()
    assert editor.program == before
    editor.select_layer(layers_for(editor.program, node, "Left")[1])
    assert editor.parameters.isEnabled()


def test_recording_checks_stay_next_to_labels(
    window: DashboardWindow, app: QApplication
) -> None:
    window.page_buttons[0].click()
    app.processEvents()
    panel = window.recordings
    dashboard = window.dashboard
    assert dashboard.isAncestorOf(panel)
    assert not window.protocol.isAncestorOf(panel)
    for width in (1175, 720):
        window.resize(width, 883)
        app.processEvents()
        dashboard.config_scroll.ensureWidgetVisible(panel)
        app.processEvents()
        assert panel.y() > dashboard.subject_card.geometry().bottom()
        assert panel.width() == dashboard.subject_card.width()
        for key, check in panel.record.items():
            caption = panel.source_labels[key]
            gap = caption.mapTo(panel, QPoint()).x() - (
                check.mapTo(panel, QPoint()).x() + check.width()
            )
            assert 0 <= gap <= 12
            assert caption.height() >= caption.heightForWidth(caption.width())


def test_compact_stimulus_inspector_preserves_hidden_settings(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.protocol_document import blank_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    editor.select_projector(0, "Left", 0)
    app.processEvents()
    assert editor.settings_card.caption.text() == "Epoch editor"
    assert not editor.timeline_card.isAncestorOf(editor.duration)
    assert editor.settings_card.isAncestorOf(editor.name)
    assert editor.context.text() == "Left → Texture"
    parameters = editor.parameters
    motion = next(f for f in parameters.forms if isinstance(f, EpochMotion))
    assert motion.speed.isVisible() and motion.direction.isVisible()
    assert not motion.angular.isVisible() and not motion.custom.isVisible()
    assert not parameters.advanced.isVisible()
    assert len(parameters.file_rows) == 1
    assert parameters.file_rows[0].findChild(QPushButton).text() == "Replace…"
    before = editor.program
    parameters.more.setChecked(True)
    assert parameters.advanced.isVisible()
    assert not motion.custom.isVisible()
    parameters.more.setChecked(False)
    assert parameters.apply() and editor.program == before
    assert editor.name.isReadOnly()
    editor.rename_action.trigger()
    assert not editor.name.isReadOnly()
    editor.name.setText("Forward flow")
    editor.edit_duration()
    assert editor.program.sequence[0].epoch_id == "Forward_flow"
    assert editor.name.isReadOnly()


def test_looming_primary_controls_and_custom_size_fidelity(
    window: DashboardWindow,
) -> None:
    from cephvr.gui.looming_size import LoomingSize
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import blank_program

    editor = window.protocol.editor
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


def test_timeline_layer_actions_and_inactive_selection_menu(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.protocol_document import blank_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(blank_program())
    editor.add_stimulus("Texture")
    before = editor.program
    app.processEvents()
    rect = editor.timeline.hits[0][0]
    QTest.mouseClick(
        editor.timeline, Qt.MouseButton.LeftButton, pos=rect.center().toPoint()
    )
    assert editor.selected_paths == ((0,),)
    assert not editor.layer_menu.isVisible()
    assert editor.program == before
    editor.timeline.set_screens(("Left",))
    editor.selection_menu.populate(editor.program, editor.path, editor.timeline.screens)
    inactive = next(
        a.menu()
        for a in editor.selection_menu.actions()
        if a.text() == "Right (inactive)"
    )
    inactive.actions()[0].trigger()
    assert editor.context.text().startswith("Right (inactive)")
    assert editor.program == before
    shared = editor.selection_menu.actions()[0].menu()
    shared.actions()[0].trigger()
    assert editor.projector_layers.face == ""
    window.apply_view(review_view(Phase.RUNNING))
    editor.layer_button.click()
    assert not editor.layer_menu.isVisible()


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
    editor.set_program(blank_program())
    editor.timeline.set_screens(("Left", "Right"))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    create = editor.create_batch
    create.composer.set_asset_root(str(tmp_path))
    editor.modes.setCurrentIndex(0)
    original = editor.program
    create.composer.add_file("Texture", str(path), "Left")
    create.composer.duration.setText("00:00:02.000000001")
    create.vary.setChecked(True)
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
    assert not create.add_button.isEnabled()
    assert editor.program == original
    create.rows[0].values.setText("10, 10, 20, 20, 40, 40")
    create.rows[1].values.setText("0, 180, 0, 180, 0, 180")
    create.repetitions.setText("2")
    create.refresh_preview()
    assert create.add_button.isEnabled(), create.summary.text()
    assert create.summary.text().startswith("12 epochs")
    assert editor.program == original
    create.generate()
    program = editor.program
    assert len(epoch_paths(program)) == 7
    assert len(expand_program(program, seed_decimal="8", max_expanded_epochs=100)) == 13
    assert program.sequence[1].order == "as_listed"
    assert program.sequence[1].conditions is None
    numbers = {
        tuple(
            round(v, 6)
            for v in motion_numbers(
                node_at(program, path).settings[0].model_dump(mode="json")
            )[:2]
        )
        for path in epoch_paths(program)[1:]
    }
    assert numbers == {(speed, angle) for speed in (10, 20, 40) for angle in (0, 180)}
    assert all(
        node_at(program, p).duration.duration.ns() == 2_000_000_001
        for p in epoch_paths(program)[1:]
    )
    assert parse_program_json(program.model_dump_json(), max_bytes=1_048_576) == program
    editor.undo(False)
    assert editor.program == original
    assert create.composer.program.sequence[0].settings
    editor.set_program(program)
    editor.select_epochs(((1, 5),))
    before_path = editor.path
    create.insert.setCurrentIndex(1)
    create.generate()
    assert len(editor.selected_paths) == 6
    editor.undo(False)
    assert editor.program == program and editor.path == before_path
    app.processEvents()


def test_batch_edit_mixed_values_isolation_atomic_failure_and_undo(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.epoch_batch import LayerTarget, apply_batch, epoch_paths
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.gui.protocol_nodes import edit_epoch
    from cephvr.gui.stimulus_presets import add_stimulus

    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    program = add_stimulus(blank_program(), 0, "Texture", ("Left", "Right"))
    program = add_stimulus(program, 0, "Looming image", ("Left",))
    program, _ = edit_epoch(program, 0, "duplicate")
    program = apply_batch(program, ((1,),), LayerTarget("", "Texture"), {"Speed": "12"})
    editor.set_program(program)
    editor.select_epochs(epoch_paths(program))
    panel = editor.batch_edit
    assert panel.parameter.findText("Speed") >= 0
    assert panel.parameter.findText("Playback start") < 0
    assert panel.targets.grid.itemAtPosition(0, 0).widget() is panel.scope_field
    assert (
        panel.targets.grid.itemAtPosition(0, 2).widget() is panel.targets.filter_field
    )
    assert panel.parameter_row.layout().itemAt(0).widget() is panel.parameter_field
    assert panel.parameter_row.layout().itemAt(1).widget() is panel.duration_row
    panel.parameter.setCurrentText("Start size")
    assert panel.parameter.findText("Start size") >= 0
    assert panel.rows["Left"].target.family == "Looming image"
    assert panel.rows["Right"].target is None
    panel.parameter.setCurrentText("Speed")
    assert panel.duration_row.isHidden() and not panel.projector_host.isHidden()
    assert panel.rows["Left"].target.family == "Texture"
    assert panel.rows["Right"].target.family == "Texture"
    value = panel.rows["Left"].value
    assert value.text() == "" and value.placeholderText() == "Mixed"
    assert not panel.dirty
    value.setText("25")
    value.textEdited.emit("25")
    right_value = panel.rows["Right"].value
    right_value.setText("30")
    right_value.textEdited.emit("30")
    app.processEvents()
    assert panel.dirty and editor.program == program
    panel.apply()
    edited = editor.program
    for old, new in zip(program.sequence, edited.sequence, strict=True):
        left = new.settings[layers_for(edited, new, "Left")[0]]
        assert motion_numbers(left.model_dump(mode="json"))[0] == pytest.approx(25)
        right = new.settings[layers_for(edited, new, "Right")[0]]
        assert motion_numbers(right.model_dump(mode="json"))[0] == pytest.approx(30)
        assert new.settings[-1] == old.settings[-1]  # Looming overlay untouched.
        assert new.duration == old.duration
    assert len(editor.selected_paths) == 2
    editor.undo(False)
    assert editor.program == program
    panel = editor.batch_edit
    panel.parameter.setCurrentText("Speed")
    panel.rows["Left"].value.setText("25")
    panel.rows["Left"].value.textEdited.emit("25")
    panel.rows["Right"].value.setText("invalid")
    panel.rows["Right"].value.textEdited.emit("invalid")
    panel.apply()
    assert editor.program == program and panel.message.text()
    panel.discard()
    with pytest.raises(ValueError, match="no Video"):
        apply_batch(
            program,
            ((0,), (1,)),
            LayerTarget("Left", "Video"),
            {"Duration": "10", "Speed": "2"},
        )
    assert editor.program == program
    panel = editor.batch_edit
    panel.parameter.setCurrentText("Duration")
    assert not panel.duration_row.isHidden() and panel.projector_host.isHidden()
    check, value = panel.fields["Duration"]
    check.setChecked(True)
    value.setText("-1")
    panel.apply()
    assert editor.program == program
    assert panel.message.text()


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
    assert len(timeline.nodes) == 5
    timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    assert editor.selected_paths == ((1, 0),)
    assert len(timeline.nodes) == 5  # Never zooms into only the selected group.
    timeline.choose(2, Qt.KeyboardModifier.ShiftModifier)
    assert set(editor.selected_paths) == {(1, 0), (1, 1)}
    timeline.choose(0, Qt.KeyboardModifier.ControlModifier)
    assert len(editor.selected_paths) == 3
    timeline.choose(4, Qt.KeyboardModifier.ControlModifier)
    assert set(editor.selected_paths) == {(0,), (1, 0)}
    assert editor.program == program
    assert editor.timeline_card.findChildren(QPushButton) == [
        editor.output_preview_button,
    ]
    assert editor.batch_edit.isAncestorOf(editor.duplicate_epoch_button)
    assert editor.batch_edit.isAncestorOf(editor.remove_epoch_button)
    assert not any(
        control.text() == "Actions…"
        for control in editor.settings_card.findChildren(QPushButton)
    )
    window.apply_view(review_view(Phase.RUNNING))
    before = editor.program
    editor.create_batch.generate()
    editor.batch_edit.apply()
    assert editor.program == before
    app.processEvents()


def test_batch_media_changes_and_pending_edits_are_isolated(
    window: DashboardWindow, tmp_path: Path, app: QApplication
) -> None:
    import json

    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_batch import LayerTarget, apply_batch
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_nodes import edit_epoch
    from cephvr.gui.stimulus_presets import add_file_stimulus

    for name in ("a.png", "b.png"):
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.fill(0)
        assert image.save(str(tmp_path / name))
    (tmp_path / "b.texture.json").write_text(
        json.dumps(
            {
                "cephvr_asset_type": "texture_design",
                "kind": "texture",
                "params": {"tile_width_mm": 50},
                "preview_file": "b.png",
            }
        )
    )
    program = add_file_stimulus(
        blank_program(),
        0,
        "Texture",
        ("Left", "Right"),
        str(tmp_path),
        str(tmp_path / "a.png"),
    )
    program, _ = edit_epoch(program, 0, "duplicate")
    changed = apply_batch(
        program,
        ((0,), (1,)),
        LayerTarget("Left", "Texture"),
        {"Asset": str(tmp_path / "b.texture.json")},
        str(tmp_path),
    )
    for epoch in changed.sequence:
        left = epoch.settings[layers_for(changed, epoch, "Left")[0]]
        right = epoch.settings[layers_for(changed, epoch, "Right")[0]]
        assets = {a.asset_id: a.logical_path for a in changed.assets}
        assert assets[left.pattern.asset_id] == "b.png"
        assert assets[right.pattern.asset_id] == "a.png"
        assert left.pattern.period_x.value == 50
    editor = window.protocol.editor
    editor.set_program(program)
    editor.timeline.set_screens(("Left", "Right"))
    window.protocol.assets.folders["root"].editor.setText(str(tmp_path))
    editor.select_epochs(((0,),))
    panel = editor.batch_edit
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    panel.targets.filter.setCurrentIndex(2)
    panel.targets.index.setText("1")
    panel.targets.index.textEdited.emit("1")
    panel.parameter.setCurrentText("Asset")
    left_value = panel.rows["Left"].value
    assert left_value.text() == "a.png"
    assert panel.rows["Right"].value.text() == "a.png"
    left_value.setText("b.texture.json")
    left_value.textEdited.emit("b.texture.json")
    panel.apply()
    updated = editor.program.sequence[0]
    left = updated.settings[layers_for(editor.program, updated, "Left")[0]]
    right = updated.settings[layers_for(editor.program, updated, "Right")[0]]
    assets = {asset.asset_id: asset.logical_path for asset in editor.program.assets}
    assert assets[left.pattern.asset_id] == "b.png"
    assert assets[right.pattern.asset_id] == "a.png"
    editor.set_program(program)
    panel = editor.batch_edit
    panel.parameter.setCurrentText("Duration")
    check, value = panel.fields["Duration"]
    value.setText("45")
    value.textEdited.emit("45")
    assert panel.dirty
    old_parameter = panel.parameter.currentIndex()
    panel.parameter.setCurrentText("Asset")
    assert panel.parameter.currentIndex() == old_parameter
    editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    assert editor.selected_paths == ((0,),)
    assert editor.timeline.selection == ((0,),)
    assert editor.program == program
    panel.reset.click()
    assert not panel.dirty
    editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    assert editor.selected_paths == ((1,),)
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
        assert [panel.table.item(i, 0).text() for i in range(4)] == ["1", "2", "3", "4"]
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
    assert overview[-1][0].right() == timeline.width() - 8
    assert (
        timeline.hover_text[len(timeline.nodes)][0].top() - overview[0][0].bottom()
        >= 25
    )
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
    assert editor.modes.tabText(0) == "Batch generate"
    assert editor.modes.tabText(1) == "Batch edit"
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


def test_batch_tabs_preserve_drafts_apply_and_phase_lock(
    window: DashboardWindow, app: QApplication
) -> None:
    window.page_buttons[1].click()
    editor = window.protocol.editor
    original = editor.program
    editor.modes.setCurrentIndex(0)
    app.processEvents()
    assert editor.create_batch.isVisible() and not editor.batch_edit.isVisible()
    assert editor.settings_card.isAncestorOf(editor.create_batch)
    assert editor.settings_card.isAncestorOf(editor.batch_edit)
    assert editor.create_batch.window() is window
    assert editor.batch_edit.window() is window
    editor.create_batch.repetitions.setText("2")
    editor.modes.setCurrentIndex(1)
    assert editor.program == original
    assert editor.batch_edit.isVisible() and not editor.create_batch.isVisible()
    panel = editor.batch_edit
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    panel.targets.filter.setCurrentIndex(2)
    panel.targets.index.setText("1")
    panel.targets.index.textEdited.emit("1")
    check, value = editor.batch_edit.fields["Duration"]
    check.setChecked(True)
    value.setText("00:00:12")
    editor.modes.setCurrentIndex(0)
    assert editor.create_batch.repetitions.text() == "2"
    assert editor.program == original
    editor.modes.setCurrentIndex(1)
    assert value.text() == "00:00:12" and check.isChecked()
    editor.batch_edit.reset.click()
    assert not editor.batch_edit.dirty and editor.program == original
    check, value = editor.batch_edit.fields["Duration"]
    check.setChecked(True)
    value.setText("-1")
    editor.batch_edit.apply_button.click()
    assert editor.batch_edit.isVisible() and editor.program == original
    value.setText("00:00:12")
    editor.batch_edit.apply_button.click()
    assert editor.batch_edit.isVisible()
    assert editor.program.sequence[0].duration.duration.seconds == "12"
    window.apply_view(review_view(Phase.RUNNING))
    assert not editor.modes.isEnabled()
    assert not editor.create_batch.isEnabled() and not editor.batch_edit.isEnabled()
    window.apply_view(review_view(Phase.CONFIGURATION))
    editor.modes.setCurrentIndex(0)
    assert editor.create_batch.isVisible() and editor.create_batch.isEnabled()


def test_batch_reference_projector_parameters_and_layers(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.looming_size import LoomingSize
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.gui.stimulus_scope import surfaces

    editor = window.protocol.editor
    composer = editor.create_batch.composer
    window.page_buttons[1].click()
    editor.modes.setCurrentIndex(0)
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
    editor.create_batch.refresh_preview()
    assert editor.create_batch.add_button.isEnabled(), (
        editor.create_batch.summary.text()
    )
    generated = editor.create_batch.candidate()
    assert generated.sequence[0].settings == composer.value().sequence[0].settings
    restored = next(
        form for form in row.parameters.forms if isinstance(form, EpochMotion)
    )
    restored.speed.setText("invalid")
    restored.edited = True
    row.parameters.dirty = True
    editor.create_batch.refresh_preview()
    assert not editor.create_batch.add_button.isEnabled()
    assert editor.program == before


def test_batch_reference_picker_scope_and_lock(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    composer = window.protocol.editor.create_batch.composer
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


def test_compact_reference_rows_share_headers_and_commit_relocated_fields(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_motion import EpochMotion
    from cephvr.gui.protocol_groups import motion_numbers

    window.resize(1350, 900)
    window.page_buttons[1].click()
    window.protocol.editor.modes.setCurrentIndex(0)
    composer = window.protocol.editor.create_batch.composer
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
    destination.setFocus()
    destination.selectAll()
    QTest.keyClicks(destination, source.text())
    composer.duration.setFocus()
    app.processEvents()
    assert [asset.logical_path for asset in composer.program.assets] == [
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
    left.advanced.trigger()
    app.processEvents()
    assert left.parameters.advanced.isVisible()
    left.advanced.trigger()
    assert not left.parameters.advanced.isVisible()
    composer.remove_layer("Left")
    app.processEvents()
    assert left.stimulus.currentText() == "None"
    assert not left.actions_button.isHidden()


def test_reference_type_change_clears_asset_and_switches_stimulus_mode(
    window: DashboardWindow, app: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtGui import QImage

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.modes.setCurrentIndex(0)
    composer = editor.create_batch.composer
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
    row.parameters.set_media_path(asset_id, str(path))
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
    editor.create_batch.refresh_preview()
    assert not editor.create_batch.add_button.isEnabled()
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


def test_generated_batch_label_survives_reload_and_targets_edits(
    window: DashboardWindow, app: QApplication
) -> None:
    from cephvr.gui.epoch_batch import epoch_paths
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
    editor.set_program(blank_program())
    create = editor.create_batch
    create.composer.batch_label.setText("Adaptation")
    create.repetitions.setText("3")
    original = editor.program
    create.generate()
    saved = parse_program_json(editor.program.model_dump_json(), max_bytes=1_048_576)
    labelled = tuple(
        p for p in epoch_paths(saved) if node_at(saved, p).batch_label == "Adaptation"
    )
    assert labelled and len(epoch_paths(saved)) == 2
    editor.undo(False)
    assert editor.program == original
    editor.set_program(saved)
    editor.select_epochs(((0,),))
    edit = editor.batch_edit
    edit.epoch_scope.setCurrentIndex(edit.epoch_scope.findData("target"))
    edit.targets.filter.setCurrentIndex(1)
    edit.targets.labels.setCurrentText("Adaptation")
    assert editor.selected_paths == labelled
    assert edit.paths == labelled
    check, duration = edit.fields["Duration"]
    check.setChecked(True)
    duration.setText("00:00:07")
    edit.targets.filter.setCurrentIndex(0)
    assert edit.targets.filter.currentText() == "Epoch label"
    edit.apply()
    assert node_at(editor.program, labelled[0]).duration.duration.seconds == "7"
    assert editor.program.sequence[0].duration.duration.seconds == "60"
    assert node_at(editor.program, labelled[0]).batch_label == "Adaptation"
    app.processEvents()


def test_arena_axis_gains_roundtrip_and_editor_spacing(window, app, tmp_path):
    import json

    from cephvr.gui.arena_movement import ArenaMovement
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    window.resize(1350, 900)
    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.modes.setCurrentIndex(0)
    batch = editor.create_batch
    composer = batch.composer
    composer.set_asset_root(str(tmp_path))
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
    assert (
        composer.duration.mapTo(composer, QPoint()).y()
        == batch.repetitions.mapTo(composer, QPoint()).y()
    )
    assert (
        row.mapTo(composer, QPoint()).y()
        - batch.generation_controls.geometry().bottom()
        >= 24
    )
    assert (
        batch.mapTo(editor.settings_card, QPoint()).y()
        - editor.modes.mapTo(editor.settings_card, QPoint(0, editor.modes.height())).y()
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

    composer = window.protocol.editor.create_batch.composer
    composer.set_asset_root(str(tmp_path))
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
                    unit="mm/s",
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
    for key, value in zip(
        panel.rig_editor.fields, (200, 300, 150, 80, 100, 75), strict=True
    ):
        panel.rig_editor.fields[key].setText(str(value))
    for key, value in zip(
        panel.rig_editor.projection_fields, (1, 1000, 0.1, 0.01), strict=True
    ):
        panel.rig_editor.projection_fields[key].setText(str(value))
    for face in ("Front", "Left", "Right", "Bottom"):
        panel.screen_editor.fields[face, "width"].setText("300")
        panel.screen_editor.fields[face, "height"].setText("180")
    for face, distance in (("Front", 140), ("Left", 130), ("Bottom", 95)):
        panel.rig_editor.screen_distances[face].setText(str(distance))
    planes = panel.tank.screen_planes()
    assert all(p[1] == -40 for p in planes["Front"])
    for face in ("Left", "Right", "Bottom"):
        assert min(p[1] for p in planes[face]) == -40
    assert max(p[1] for p in planes["Left"]) == 260
    assert max(p[1] for p in planes["Bottom"]) == 140
    payload = panel.rig_editor.geometry_payload(panel.screen_editor.drafts)
    for surface in payload["surfaces"]:
        face = surface["surface_id"].title()
        assert list(surface.values())[1:] == planes[face]
    panel.rig_editor.screen_distances["Front"].setText("160")
    assert all(
        min(p[1] for p in corners) == -60
        for corners in panel.tank.screen_planes().values()
    )
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
    right = screen_corners(rig, "Right", values, front_distance="140")
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


def test_plot_toggles_are_view_only_and_survive_refresh(
    window: DashboardWindow, app: QApplication
):
    panel = window.devices.projectors
    before = panel.calibration_files.snapshot()
    participation = dict(panel.participation)
    for key, control in panel.plot_toggles.items():
        assert control.isCheckable() and control.isChecked()
        control.click()
        assert not panel.tank.visible_elements[key]
    window.apply_view(review_view(Phase.RUNNING))
    panel.update_geometry()
    assert not any(panel.tank.visible_elements.values())
    for key, control in panel.plot_toggles.items():
        assert control.isEnabled()
        control.click()
        assert panel.tank.visible_elements[key]
    assert panel.calibration_files.snapshot() == before
    assert panel.participation == participation
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
    create = editor.create_batch
    create.insert.setCurrentIndex(create.insert.findData("label"))
    create.target_label.setCurrentText("Target")
    assert not create.target_field.isHidden()
    assert create.label_counts["Target"] == 2
    editor.insert_batch(batch, Insertion("label", label="Target"))
    assert len(editor.selected_paths) == 2
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
    editor.modes.setCurrentIndex(0)
    composer = editor.create_batch.composer
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
    app.processEvents()
    app.processEvents()
    scroll = next(
        s for s in window.findChildren(QScrollArea) if s.isAncestorOf(composer)
    )
    assert scroll.horizontalScrollBar().maximum() == 0
    batch = editor.create_batch
    assert (
        batch.insert.mapTo(batch, QPoint()).y()
        > composer.duration.mapTo(batch, QPoint()).y()
    )


def test_bottom_center_path_survives_outer_ray_clearance():
    from cephvr.gui.projector_geometry import RigDimensions, screen_corners
    from cephvr.gui.projector_optics import bottom_mirror_footprint

    rig = RigDimensions(200, 300, 150, (85, 100, 75))
    bottom = screen_corners(
        rig,
        "Bottom",
        dict(width="250", height="325", subject_distance="100"),
        front_distance="125",
    )
    right = screen_corners(
        rig,
        "Right",
        dict(width="325", height="180", subject_distance="140"),
        front_distance="125",
    )
    # No fixed 700 cutoff: full-cone clearance already works at 650 for this rig.
    for length in ("650", "699", "700"):
        complete = bottom_mirror_footprint(bottom, right, length, "1.6", 16 / 9, "300")
        assert complete.mirror and not complete.warning
    partial = bottom_mirror_footprint(bottom, right, "600", "1.6", 16 / 9, "300")
    assert partial.projector == (525, 137.5, -200)
    assert partial.mirror_center == (100, 137.5, -200)
    assert not partial.mirror and "outer rays" in partial.warning
    assert partial.width == 375 and partial.height == 210.9375
    elevated_bottom = screen_corners(
        rig,
        "Bottom",
        dict(width="250", height="325", subject_distance="50"),
        front_distance="125",
    )
    upper_edge = bottom_mirror_footprint(
        elevated_bottom, right, "470", "10", 16 / 9, "300"
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
    assert set(panel.plot_toggles) == {
        "tank",
        "screens",
        "projection",
        "subject",
    }
    assert set(panel.tank.visible_elements) == set(panel.plot_toggles)
    assert COLORS.footprint != COLORS.projection
    panel.plot_toggles["projection"].click()
    assert not panel.tank.visible_elements["projection"]
    assert panel.tank.visible_elements["screens"]
    assert panel.enabled_screens == ()


def test_calibration_arena_uses_saved_screen_planes_and_backend_glb_profile():
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
    payload = {"format": "cephvr-rig-calibration", "version": 2, "values": values}
    rig, screens = geometry_from_calibration(payload)
    assert screens["Right"][0][0] == pytest.approx(210)
    scene = parse_glb(
        make_calibration_glb(rig, screens), max_bytes=1_000_000, max_elements=200_000
    )
    primitive = scene.nodes[0].primitives[0]
    assert primitive.colors is not None
    colors = set(primitive.colors)
    assert (1.0, 1.0, 1.0, 1.0) in colors  # face names
    assert any(color == pytest.approx((1.0, 0.86, 0.12, 1.0)) for color in colors)
    for face in FACES:
        for corner in screens[face]:
            assert any(point == pytest.approx(corner) for point in primitive.positions)


def test_calibration_identity_profiles_bind_unique_native_monitors(tmp_path):
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
    calibration = {"format": "cephvr-rig-calibration", "version": 2, "values": values}
    assignments = tuple(
        AssignedDisplay(face, index * 1280, 0, 1280, 720, True)
        for index, face in enumerate(FACES)
    )
    monitors = tuple(
        MonitorBinding(f"interface-{index}", index * 1280, 0, 1280, 720, 60, 8)
        for index in range(4)
    )
    profile, meshes = diagnostic_display_profile(calibration, assignments, monitors)
    assert {output.device_identity for output in profile.outputs} == {
        monitor.interface for monitor in monitors
    }
    assert profile.photometric_mode == "uncalibrated"
    assert profile.presentation_mode == "all_outputs_vsync"
    assert profile.geometry.near_mm < 1 < profile.geometry.far_mm
    assert set(meshes) == {face.lower() for face in FACES}
    assert all(mesh.vertices[0].uv == mesh.vertices[0].xy for mesh in meshes.values())
    assert all(mesh.orientation == "preserving" for mesh in meshes.values())
    values["screens.Front.scale_u"] = 0.8
    values["screens.Front.offset_x"] = 40
    values["screens.Left.flip_x"] = True
    adjusted, adjusted_meshes = diagnostic_display_profile(
        calibration, assignments, monitors
    )
    assert adjusted == profile
    assert adjusted_meshes["front"].vertices[0].xy[0] == pytest.approx(
        0.5 - 0.4 + 40 / 1280
    )
    assert adjusted_meshes["left"].orientation == "mirrored"
    values["screens.Front.offset_x"] = 1000
    with pytest.raises(ValueError, match="extends beyond"):
        diagnostic_display_profile(calibration, assignments, monitors)
    values["screens.Front.offset_x"] = None
    values["screens.Front.scale_u"] = None
    values["screens.Left.flip_x"] = False
    with pytest.raises(ValueError, match="unique native monitor"):
        diagnostic_display_profile(calibration, assignments, monitors[:-1])
    arena_path = write_diagnostic_bundle(tmp_path, calibration, assignments, monitors)
    assert arena_path.is_file()
    assert not (arena_path.parent / "rig_geometry_grid.program.json").exists()
    assert (arena_path.parent / "diagnostic_display_profile.json").is_file()
    assert all(
        (arena_path.parent / f"diagnostic_{face.lower()}.json").is_file()
        for face in FACES
    )


def test_calibration_button_reflects_confirmed_managed_output(
    window, monkeypatch, tmp_path
):
    panel = window.devices.projectors
    table = panel.calibration
    arena = tmp_path / "rig_geometry_grid.glb"
    prepared = []
    result = [arena]

    def prepare():
        prepared.append(True)
        return result[0]

    monkeypatch.setattr(panel, "prepare_calibration", prepare)
    output_requests = []
    panel.calibration_launch_requested.connect(output_requests.append)
    launched: list[bool] = []
    closed: list[bool] = []
    table.launch_requested.connect(lambda: launched.append(True))
    table.close_requested.connect(lambda: closed.append(True))
    assert table.findChildren(QPushButton) == [table.presentation_button]
    assert not table.presentation_button.isEnabled()
    table.set_presentation_state(active=False, available=True)
    table.presentation_button.click()
    assert launched == [True]
    assert prepared == [True]
    assert output_requests == [str(arena)]
    assert table.presentation_button.text() == "Launch"
    table.set_presentation_state(active=True, available=True)
    assert table.presentation_button.text() == "Close"
    table.presentation_button.click()
    assert closed == [True]
    assert prepared == [True]
    assert table.presentation_button.text() == "Close"
    table.set_presentation_state(active=True, available=True, pending=True)
    assert not table.presentation_button.isEnabled()
    table.set_presentation_state(active=False, available=False)
    assert table.presentation_button.text() == "Launch"
    assert not table.presentation_button.isEnabled()
    result[0] = None
    table.set_presentation_state(active=False, available=True)
    table.presentation_button.click()
    assert prepared == [True, True]
    assert output_requests == [str(arena)]  # Failed preparation never requests output.


def test_unified_feedback_input_mapping_and_retain_state(window, app):
    import json

    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
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

    composer = window.protocol.editor.create_batch.composer
    composer.set_asset_root(str(tmp_path))
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
    batch = window.protocol.editor.create_batch
    for width in (1350, 720):
        window.resize(width, 900)
        window.protocol.editor.modes.setCurrentIndex(0)
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
    editor = window.protocol.editor
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
    composer = editor.create_batch.composer
    composer.set_screens(("Front", "Bottom"))
    composer.change_type("Front", "Texture")
    editor.modes.setCurrentIndex(0)
    row = composer.rows["Front"]
    row.advanced.setChecked(True)
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

    editor = window.protocol.editor
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

    editor = window.protocol.editor
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

    editor = window.protocol.editor
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
    composer = editor.create_batch.composer
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

    editor = window.protocol.editor
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

    composer = window.protocol.editor.create_batch.composer
    composer.set_screens(("Front", "Right"))
    composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    row = composer.rows["Front"]
    before = composer.program
    row.add.trigger()
    assert row.layer.currentText() == "1 · Empty"
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
    assert row.layer.currentText() == "2 · Empty"
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
    editor.select_epochs(((0,),))
    editor.open_details("", 0)
    parameters = editor.parameters
    parameters.more.setChecked(True)
    parameters.fades.fade_in.setText("2")
    parameters.fades.mark_changed()
    assert parameters.apply()
    epochs = editor.program.sequence
    assert epochs[0].settings[0].opacity.kind == "keyframes"
    assert all(e.settings[0].opacity.kind == "constant" for e in epochs[1:])


def test_200_epoch_timeline_reuses_views_and_metadata_noop(window, monkeypatch):
    from cephvr.gui import protocol_timeline, timeline_views
    from cephvr.gui.protocol_document import review_program
    from cephvr.gui.protocol_nodes import edit_epoch_metadata

    calls = []
    expand = timeline_views.expand_program

    def counted(program, **kwargs):
        calls.append(program)
        return expand(program, **kwargs)

    monkeypatch.setattr(timeline_views, "expand_program", counted)
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
    editor.modes.setCurrentIndex(0)
    composer = editor.create_batch.composer
    composer.set_screens(("Front", "Right"))
    composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "a_prepared_texture_with_a_long_filename.png"
    assert image.save(str(path))
    composer.add_file("Texture", str(path), "Front")
    composer.rows["Front"].advanced.setChecked(True)
    editor.create_batch.vary.setChecked(True)
    editor.create_batch.add_variation()
    window.resize(720, 900)
    QTest.qWait(30)
    app.processEvents()
    assert window.protocol.config_scroll.horizontalScrollBar().maximum() == 0


def test_batch_variations_target_projectors_and_local_layer_ordinals(
    window, app, tmp_path
):
    from PyQt6.QtGui import QImage

    from cephvr.gui.components import Card
    from cephvr.gui.protocol_groups import motion_numbers
    from cephvr.visual_stimulus.compiler.expansion import expand_program

    window.page_buttons[1].click()
    create = window.protocol.editor.create_batch
    create.composer.set_screens(("Left", "Right"))
    create.composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    for face in ("Left", "Right"):
        for _ in range(2):
            create.composer.add_file("Texture", str(path), face)
    create.vary.setChecked(True)
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
        window.protocol.editor.modes.setCurrentIndex(0)
        app.processEvents()
        assert (
            row.remove.mapTo(row, QPoint()).y()
            == row.parameter.mapTo(row, QPoint()).y()
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
    composer = window.protocol.editor.create_batch.composer
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
        a.text() for a in left.actions_button.menu().actions() if not a.isSeparator()
    ] == ["Add layer", "Remove layer", "Move layer", "Advanced settings"]
    assert [a.text() for a in left.move_menu.actions()] == ["Move up", "Move down"]
    assert left.advanced.isCheckable()
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
    create.vary.setChecked(True)
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
        "scale_u": "0.5",
        "scale_v": "0.5",
        "offset_x": "10",
        "offset_y": "20",
        "flip_x": "True",
        "flip_y": "False",
    }
    correction = PreviewCorrection.from_draft("Front", draft, (100, 100))
    assert not correction.error
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
    assert output.pixelColor(80, 30) == QColor("red")
    assert output.pixelColor(20, 30) == QColor("black")
    assert output.pixelColor(50, 80) == QColor("black")
    # The same pixel offset becomes a smaller normalized shift on a larger display.
    larger = PreviewCorrection.from_draft("Front", draft, (200, 200))
    assert larger.corners[0][0] == pytest.approx(correction.corners[0][0] - 0.05)
    assert larger.corners[0][1] == pytest.approx(correction.corners[0][1] - 0.1)
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


def test_preview_rejects_invalid_corrections_and_unresolved_pixel_offsets():
    from cephvr.gui.trial_preview_surfaces import PreviewCorrection

    assert (
        "Assign a display"
        in PreviewCorrection.from_draft("Front", {"offset_x": "10"}, None).error
    )
    assert (
        "positive"
        in PreviewCorrection.from_draft("Front", {"scale_u": "0"}, (1920, 1080)).error
    )
    assert (
        "beyond"
        in PreviewCorrection.from_draft("Front", {"scale_u": "2"}, (1920, 1080)).error
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
    create = window.protocol.editor.create_batch
    from PyQt6.QtGui import QImage

    create.composer.set_screens(("Front",))
    create.composer.set_asset_root(str(tmp_path))
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    create.composer.add_file("Texture", str(path), "Front")
    create.vary.setChecked(True)
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


def test_timeline_epoch_buttons_and_keyboard_history(window, app):
    window.page_buttons[1].click()
    editor = window.protocol.editor
    original = editor.program
    editor.timeline.setFocus()
    app.processEvents()
    QTest.keyClick(editor.timeline, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    duplicate = editor.program
    assert len(duplicate.sequence) == len(original.sequence) + 1
    editor.timeline.setFocus()
    app.processEvents()
    QTest.keyClick(editor.timeline, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert editor.program == original
    QTest.keyClick(editor.timeline, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert editor.program == duplicate
    QTest.keyClick(editor.timeline, Qt.Key.Key_Backspace)
    assert len(editor.program.sequence) == len(original.sequence)
    assert not any(
        action.text() in {"Undo", "Redo"} for action in editor.epoch_menu.actions()
    )
    editor.timeline.choose(0, Qt.KeyboardModifier.NoModifier)
    editor.timeline.choose(1, Qt.KeyboardModifier.ShiftModifier)
    assert not editor.duplicate_epoch_button.isEnabled()
    assert not editor.remove_epoch_button.isEnabled()
    before = editor.program
    QTest.keyClick(editor.timeline, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(editor.timeline, Qt.Key.Key_Backspace)
    assert editor.program == before
    text_field = editor.batch_edit.duration
    text_field.setText("123")
    text_field.setFocus()
    text_field.setCursorPosition(3)
    app.processEvents()
    before = editor.program
    QTest.keyClick(text_field, Qt.Key.Key_Backspace)
    assert text_field.text() == "12"
    assert editor.program == before


def test_image_fit_and_motion_are_saved_without_texture_phase(window, app):
    from cephvr.gui.image_parameters import ImageParameters
    from cephvr.gui.protocol_document import blank_program
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    editor = window.protocol.editor
    editor.set_program(blank_program())
    editor.add_stimulus("Image")
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
    setting = restored.sequence[0].settings[0]
    assert setting.kind == "image" and setting.fit == "cover"
    assert setting.initial.x == 4
    assert setting.motion.y.function.value == pytest.approx(12)
    assert "phase_x" not in setting.model_dump()


@pytest.mark.parametrize("preset", ["Video", "Looming image"])
def test_family_advanced_controls_preserve_hidden_state(window, app, preset):
    from cephvr.gui.advanced_appearance import AdvancedAppearance
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus

    program = add_stimulus(blank_program(), 0, preset, ("Front",))
    epoch = program.sequence[0]
    imported = epoch.settings[0].model_copy(update={"reset": True})
    program = program.model_copy(
        update={"sequence": (epoch.model_copy(update={"settings": (imported,)}),)}
    )
    editor = window.protocol.editor
    editor.set_program(program)
    parameters = editor.parameters
    parameters.more.setChecked(True)
    app.processEvents()
    appearance = parameters.advanced_card.findChild(AdvancedAppearance)
    assert appearance is not None and appearance.link_field.isHidden()
    assert parameters.retain.isHidden() == (preset == "Video")
    parameters.fades.fade_in.setText("1")
    parameters.fades.mark_changed()
    assert parameters.apply()
    assert editor.program.sequence[0].settings[0].reset


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


def test_batch_fit_choice_and_legacy_image_appearance(app):
    import json

    from cephvr.gui.batch_edit_rows import ProjectorEditRow
    from cephvr.gui.epoch_batch import LayerTarget, patch_setting
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.visual_stimulus.config.models.program_model import parse_program_json

    program = add_stimulus(blank_program(), 0, "Image", ("Front",))
    row = ProjectorEditRow("Front")
    row.bind(program, ((0,),), "Fit", [LayerTarget("Front", "Image")])
    row.fit.setCurrentText("Cover")
    assert row.dirty and row.value.text() == "cover"
    data = program.model_dump(mode="json")
    setting = data["sequence"][0]["settings"][0]
    patch_setting(setting, {"Fit": row.value.text()})
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
    row.close()
    row.deleteLater()
    app.processEvents()


def test_selected_epoch_full_form_and_scope_switching(window, app):
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.protocol_document import review_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(review_program())
    editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
    editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    app.processEvents()
    panel = editor.batch_edit
    form = panel.selection_form
    original = editor.program
    assert form.isVisible() and panel.parameter_field.isHidden()
    assert panel.duplicate_epoch_button.isVisible()
    assert form.composer.program.sequence[0].settings == original.sequence[1].settings
    form.composer.batch_label.setText("Pending label")
    form.mark_changed()
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    assert panel.epoch_scope.currentData() == "timeline"
    assert form.composer.batch_label.text() == "Pending label"
    panel.reset.click()
    assert form.composer.batch_label.text() == original.sequence[1].batch_label
    form.composer.duration.setText("00:00:24")
    form.mark_changed()
    panel.apply_button.click()
    assert not form.message.text()
    changed = editor.program
    assert changed.sequence[1].duration.duration.seconds == "24"
    assert changed.sequence[1].epoch_id == original.sequence[1].epoch_id
    assert changed.sequence[1].settings == original.sequence[1].settings
    assert changed.sequence[0] == original.sequence[0]
    assert changed.sequence[2] == original.sequence[2]
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    app.processEvents()
    assert form.isHidden() and panel.parameter_field.isVisible()
    assert panel.epoch_actions.isHidden()
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("timeline"))
    app.processEvents()
    assert editor.selected_paths == ((1,),)
    assert form.isVisible() and panel.duplicate_epoch_button.isVisible()
    assert node_at(form.composer.program, (0,)).epoch_id == changed.sequence[1].epoch_id
    editor.undo()
    assert editor.program == original


def test_selected_epoch_type_change_keeps_other_projector_and_sibling_epochs(window):
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.projector_layers import layers_for
    from cephvr.gui.protocol_document import review_program

    editor = window.protocol.editor
    editor.set_program(review_program())
    editor.timeline.set_screens(("Left", "Right"))
    editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    original = editor.program
    form = editor.batch_edit.selection_form
    form.composer.change_type("Left", "None")
    form.apply()
    assert not form.message.text()
    updated = editor.program
    node = node_at(updated, (1,))
    assert layers_for(updated, node, "Left") == []
    assert len(layers_for(updated, node, "Right")) == 1
    assert updated.sequence[0] == original.sequence[0]
    assert updated.sequence[2] == original.sequence[2]
    assert node.epoch_id == original.sequence[1].epoch_id


def test_target_epoch_filters_and_invalid_index(window, app):
    from cephvr.gui.program_editing import node_at
    from cephvr.gui.protocol_document import review_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    original = review_program()
    editor.set_program(original)
    editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    panel = editor.batch_edit
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    targets = panel.targets
    assert panel.epoch_scope.currentText() == "Target epochs"
    assert editor.selected_paths == ((0,), (1,), (2,))
    assert targets.label_field.isHidden() and targets.index_field.isHidden()
    targets.filter.setCurrentIndex(2)
    assert targets.index_field.isVisible() and targets.label_field.isHidden()
    assert not panel.apply_button.isEnabled()
    targets.index.setText("2")
    targets.index.textEdited.emit("2")
    assert editor.selected_paths == ((1,),)
    assert panel.apply_button.isEnabled()
    check, duration = panel.fields["Duration"]
    check.setChecked(True)
    duration.setText("00:00:24")
    panel.apply()
    assert node_at(editor.program, (1,)).duration.duration.seconds == "24"
    assert editor.program.sequence[0] == original.sequence[0]
    assert editor.program.sequence[2] == original.sequence[2]
    current = editor.program
    for invalid in ("4", "0", "-1", "1.5", "abc", ""):
        targets.index.setText(invalid)
        targets.index.textEdited.emit(invalid)
        assert targets.message.text()
        assert not panel.apply_button.isEnabled()
        panel.apply()
        assert editor.program == current
    targets.index.setText("3")
    targets.index.textEdited.emit("3")
    assert not targets.message.text()
    assert editor.selected_paths == ((2,),)
    targets.filter.setCurrentIndex(0)
    assert editor.selected_paths == ((0,), (1,), (2,))
    assert panel.apply_button.isEnabled()
    app.processEvents()


def test_target_epoch_labels_refresh_and_preserve_other_epochs(window):
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import review_program

    editor = window.protocol.editor
    data = review_program().model_dump(mode="json")
    data["sequence"][0]["batch_label"] = "Rest"
    data["sequence"][1]["batch_label"] = "Flow"
    data["sequence"][2]["batch_label"] = "Rest"
    original = validate(data)
    editor.set_program(original)
    editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    panel = editor.batch_edit
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    targets = panel.targets
    targets.filter.setCurrentIndex(1)
    assert [targets.labels.itemText(i) for i in range(targets.labels.count())] == [
        "Flow",
        "Rest",
    ]
    targets.labels.setCurrentText("Rest")
    assert panel.paths == ((0,), (2,))
    check, duration = panel.fields["Duration"]
    check.setChecked(True)
    duration.setText("00:00:30")
    panel.apply()
    assert editor.program.sequence[0].duration.duration.seconds == "30"
    assert editor.program.sequence[2].duration.duration.seconds == "30"
    assert editor.program.sequence[1] == original.sequence[1]
    editor.set_program(review_program())
    assert targets.labels.count() == 0
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    assert "No epochs" in targets.message.text()
    assert not panel.apply_button.isEnabled()


def test_epoch_edit_rows_duration_format_and_action_placement(window, app):
    from cephvr.gui.protocol_document import review_program

    window.resize(1280, 1050)
    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.set_program(review_program())
    editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
    editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
    panel = editor.batch_edit
    form = panel.selection_form
    app.processEvents()
    assert panel.apply_button.text() == "Apply"
    assert panel.reset.text() == "Discard"
    assert panel.apply_button.mapTo(panel, QPoint(0, 0)).y() < (
        form.composer.rows["Front"].mapTo(panel, QPoint(0, 0)).y()
    )
    panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
    panel.targets.filter.setCurrentIndex(2)
    panel.targets.index.setText("2")
    panel.targets.index.textEdited.emit("2")
    app.processEvents()
    positions = [
        control.mapTo(panel, QPoint(0, 0)).y()
        for control in (panel.epoch_scope, panel.targets.filter, panel.targets.index)
    ]
    assert max(positions) - min(positions) <= 1
    assert panel.parameter.mapTo(panel, QPoint(0, 0)).y() == (
        panel.duration.mapTo(panel, QPoint(0, 0)).y()
    )
    assert panel.duration.text() == "00:00:20"
    panel.targets.filter.setCurrentIndex(0)
    assert panel.duration.text() == ""
    assert panel.duration.placeholderText() == "hh:mm:ss"
    assert "Mixed durations" in panel.duration.toolTip()
    assert not panel.dirty
    assert panel.apply_button.text() == "Apply" and panel.reset.text() == "Discard"
    panel.duration.setText("00:00:20.125")
    panel.duration.textEdited.emit("00:00:20.125")
    panel.apply()
    assert not panel.message.text()
    assert all(
        epoch.duration.duration.seconds == "20.125" for epoch in editor.program.sequence
    )


def test_epoch_actions_stay_fixed_and_fields_align_across_modes(window, app):
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import review_program

    window.page_buttons[1].click()
    editor = window.protocol.editor
    data = review_program().model_dump(mode="json")
    data["sequence"][1]["batch_label"] = "Flow"
    editor.set_program(validate(data))
    editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
    for width in (1280, 720):
        window.resize(width, 1050)
        editor.timeline.choose(1, Qt.KeyboardModifier.NoModifier)
        app.processEvents()
        panel = editor.batch_edit
        position = panel.apply_button.mapTo(panel, QPoint(0, 0))
        reset_position = panel.reset.mapTo(panel, QPoint(0, 0))
        for mode in (0, 1, 2):
            panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("target"))
            panel.targets.filter.setCurrentIndex(mode)
            if mode == 2:
                panel.targets.index.setText("2")
                panel.targets.index.textEdited.emit("2")
            app.processEvents()
            assert panel.apply_button.mapTo(panel, QPoint(0, 0)) == position
            assert panel.reset.mapTo(panel, QPoint(0, 0)) == reset_position
            if mode:
                choice = panel.targets.labels if mode == 1 else panel.targets.index
                assert panel.epoch_scope.height() == choice.height()
                assert (
                    choice.mapTo(panel, QPoint()).x()
                    - (
                        panel.targets.filter.mapTo(panel, QPoint()).x()
                        + panel.targets.filter.width()
                    )
                    >= 12
                )
                assert panel.epoch_scope.mapTo(panel, QPoint(0, 0)).y() == (
                    choice.mapTo(panel, QPoint(0, 0)).y()
                )
        panel.epoch_scope.setCurrentIndex(panel.epoch_scope.findData("timeline"))
        app.processEvents()
        form = panel.selection_form
        assert panel.apply_button.mapTo(panel, QPoint(0, 0)) == position
        assert panel.reset.mapTo(panel, QPoint(0, 0)) == reset_position
        assert form.composer.batch_label.height() == panel.epoch_scope.height()
        assert form.composer.mode.mapTo(panel, QPoint(0, 0)).x() == (
            panel.epoch_scope.mapTo(panel, QPoint(0, 0)).x()
        )
        assert form.width() <= window.protocol.config_scroll.viewport().width()


def test_managed_mcu_pending_completion_and_final_status(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
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
    binding.test_connection()
    binding.test_connection()
    assert len(sent) == 1 and panel.connection_pending
    assert not panel.test_buttons["trial-state"].isEnabled()
    binding.finished("mcu", True, "Connected")
    assert not panel.connection_pending
    binding.test_pin("trial-state", True)
    assert not binding.settle.isActive()
    diagnostic = state.acquisition_devices.diagnostic
    diagnostic.signal = pb.MICROCONTROLLER_SIGNAL_KIND_TRIAL_STATE
    diagnostic.active = True
    diagnostic.observed_monotonic_ns = 100
    binding.install(state, True)
    binding.finished("mcu", True, "Started")
    assert binding.settle.isActive()
    assert panel.test_buttons["trial-state"].text() == "Stop"
    binding.read_status()
    assert sent[-1][1]["kind"] == rpc.MICROCONTROLLER_COMMAND_KIND_STATUS
    diagnostic.active = False
    diagnostic.observed_monotonic_ns = 200
    diagnostic.rising_edges = 10
    binding.install(state, True)
    binding.finished("mcu", True, "Stopped")
    assert not binding.settle.isActive()
    assert panel.test_buttons["trial-state"].text() == "Test"
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
async def test_managed_role_assignment_is_atomic_and_leaves_camera_disabled() -> None:
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
    assert updated.behavioral.device.device_id == "" and not updated.behavioral.enabled
    assert updated.tracking.device.device_id == "A" and not updated.tracking.enabled
    assert acquisition.behavioral.device.device_id == "A"


def test_managed_camera_projection_distinguishes_open_capture_and_cleanup(
    window: DashboardWindow,
) -> None:
    from cephvr.control.v1 import services_pb2 as rpc
    from cephvr.control.v1 import types_pb2 as pb
    from cephvr.gui.managed_cameras import ManagedCameras

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
    assert panel.connect_button.text() == "Disconnect"
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
    assert panel.connect_button.text() == "Stop capture"
    panel.connect_button.click()
    assert calls[-1][1]["kind"] == rpc.CAMERA_COMMAND_KIND_STOP_PREVIEW
    binding.disconnected()
