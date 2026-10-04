"""Native frontend behavior and ownership; no controller or rig execution."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, QRect, QSettings, QSize, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton, QWidget

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
    assert panel.port.itemText(0) == "COM7"
    assert panel.port.itemData(0) == "COM7"
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
    assert "×" in panel.table.item(0, 2).text()
    assert panel.diagram.outputs


def test_windows_display_number_mapping_and_unknowns(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cephvr.gui import projectors

    screen = projectors.QGuiApplication.screens()[0]
    monkeypatch.setattr(projectors.QGuiApplication, "primaryScreen", lambda: None)
    monkeypatch.setattr(
        projectors,
        "windows_display_indices",
        lambda: ({screen.name().casefold(): "4"}, ""),
    )
    panel = window.devices.projectors
    panel.request("Refresh displays")
    assert panel.table.item(0, 0).text() == "4"
    assert panel.diagram.outputs[0][0] == "4"
    monkeypatch.setattr(
        projectors, "windows_display_indices", lambda: ({}, "Unavailable")
    )
    panel.request("Refresh displays")
    assert panel.table.item(0, 0).text() == "—"
    assert "Unavailable" in panel.console.toPlainText()


def test_windows_display_query_preserves_clone_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.gui import display_indices as native

    class Function:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args):
            return self.fn(*args)

    def sizes(flags, paths, modes):
        paths._obj.value = 2
        modes._obj.value = 1
        return 0

    def query(flags, count, paths, modes_count, modes, topology):
        paths[0].source.id = 0
        paths[1].source.id = 0
        return 0

    def source(header):
        name = native.ct.cast(header, native.ct.POINTER(native.SourceName)).contents
        name.name = "display-source"
        return 0

    class Api:
        GetDisplayConfigBufferSizes = Function(sizes)
        QueryDisplayConfig = Function(query)
        DisplayConfigGetDeviceInfo = Function(source)

    monkeypatch.setattr(native.sys, "platform", "win32")
    monkeypatch.setattr(
        native.ct, "WinDLL", lambda *args, **kwargs: Api(), raising=False
    )
    assert native.windows_display_indices() == ({"display-source": "1/2"}, "")
    assert native.ct.sizeof(native.DisplayPath) == 72
    Api.QueryDisplayConfig = Function(lambda *args: 122)
    values, error = native.windows_display_indices()
    assert not values and "repeatedly" in error


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


def test_projectors_exclude_primary_without_renumbering(
    window: DashboardWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PyQt6.QtCore import QRect

    from cephvr.gui import projectors

    class Screen:
        def __init__(self, name):
            self.identity = name

        def name(self):
            return self.identity

        def manufacturer(self):
            return ""

        def model(self):
            return ""

        def serialNumber(self):
            return ""

        def geometry(self):
            return QRect(0, 0, 1920, 1080)

        def devicePixelRatio(self):
            return 1

    main, extra = Screen("main"), Screen("extra")
    monkeypatch.setattr(projectors.QGuiApplication, "screens", lambda: [main, extra])
    monkeypatch.setattr(projectors.QGuiApplication, "primaryScreen", lambda: main)
    monkeypatch.setattr(
        projectors, "windows_display_indices", lambda: ({"main": "2", "extra": "4"}, "")
    )
    panel = window.devices.projectors
    panel.request("Refresh displays")
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "4"
    assert [index for index, _ in panel.diagram.outputs] == ["4"]
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
        assert editor.timeline_card.height() == editor.trial_card.height() == 366
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
    position = editor.settings_card.y()
    editor.timeline.set_screens(("Front", "Left", "Right", "Bottom"))
    for _ in range(3):
        app.processEvents()
    assert editor.timeline_card.height() == 366
    assert editor.settings_card.y() == position
    editor.timeline.setMinimumHeight(800)
    for _ in range(3):
        app.processEvents()
    bar = editor.timeline_scroll.verticalScrollBar()
    assert bar is not None and bar.maximum() > 0
    bar.setValue(bar.maximum())
    assert editor.timeline.y() < 0
    assert editor.timeline_card.height() == 366
    assert editor.settings_card.y() == position
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
    opacity = parameters.forms[1].children_by_key["opacity"]
    value = opacity.variant.children_by_key["value"].variant.control
    value.setText("0.4")
    parameters.mark_changed()
    assert parameters.apply()
    assert editor.program.sequence[1].settings[0].opacity.value == 0.4
    value.setText("-1")
    parameters.mark_changed()
    before = editor.program
    editor.select_node(2)
    assert editor.node_index == 1
    assert editor.program == before
    assert parameters.dirty
    value.setText("0.9")
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
    opacity = parameters.forms[1].children_by_key["opacity"]
    opacity.control.setCurrentText("Ramp")
    fields = opacity.variant.children_by_key
    fields["initial"].variant.control.setText("0.1")
    fields["slope_per_s"].variant.control.setText("0.001")
    assert parameters.apply()
    setting = editor.program.sequence[0].settings[0]
    assert setting.opacity.kind == "ramp"
    assert setting.opacity.initial == 0.1
    assert setting.opacity.slope_per_s == 0.001
    fields["initial"].variant.control.setText("bad")
    parameters.mark_changed()
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
    create.composer.duration.setText("2.000000001")
    create.vary.setChecked(True)
    create.add_variation()
    create.rows[0].values.setText("10, 20, 40")
    create.add_variation()
    create.rows[1].parameter.setCurrentText("Direction")
    create.rows[1].values.setText("0, 180")
    create.refresh_preview()
    assert not create.add_button.isEnabled()
    assert editor.program == original
    create.combine.setCurrentIndex(1)
    create.repetitions.setText("2")
    create.order.setCurrentIndex(1)
    create.refresh_preview()
    assert create.add_button.isEnabled(), create.summary.text()
    assert create.summary.text().startswith("12 epochs")
    assert editor.program == original
    create.generate()
    program = editor.program
    assert len(epoch_paths(program)) == 7
    assert len(expand_program(program, seed_decimal="8", max_expanded_epochs=100)) == 13
    assert program.sequence[1].order == "shuffle_each_repetition"
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
    panel.face.setCurrentIndex(panel.face.findData("Left"))
    panel.layer.setCurrentIndex(
        next(i for i, t in enumerate(panel.targets) if t.family == "Texture")
    )
    check, value = panel.fields["Speed"]
    assert value.text() == "" and value.placeholderText() == "Mixed"
    assert not check.isChecked()
    value.setText("25")
    value.textEdited.emit("25")
    app.processEvents()
    assert check.isChecked() and editor.program == program
    panel.apply()
    edited = editor.program
    for old, new in zip(program.sequence, edited.sequence, strict=True):
        left = new.settings[layers_for(edited, new, "Left")[0]]
        assert motion_numbers(left.model_dump(mode="json"))[0] == pytest.approx(25)
        right = new.settings[layers_for(edited, new, "Right")[0]]
        original_right = old.settings[0].model_dump(mode="json")
        actual_right = right.model_dump(mode="json")
        original_right["space"] = actual_right["space"]
        assert original_right == actual_right
        assert new.settings[-1] == old.settings[-1]  # Looming overlay untouched.
        assert new.duration == old.duration
    assert len(editor.selected_paths) == 2
    editor.undo(False)
    assert editor.program == program
    with pytest.raises(ValueError, match="no Video"):
        apply_batch(
            program,
            ((0,), (1,)),
            LayerTarget("Left", "Video"),
            {"Duration": "10", "Speed": "2"},
        )
    assert editor.program == program
    panel = editor.batch_edit
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
    assert not editor.timeline_card.findChildren(QPushButton)
    assert editor.settings_card.isAncestorOf(editor.epoch_button)
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
    editor.select_epochs(((0,),))
    panel = editor.batch_edit
    check, value = panel.fields["Duration"]
    value.setText("45")
    value.textEdited.emit("45")
    assert panel.dirty
    old_face = panel.face.currentIndex()
    panel.face.setCurrentIndex(1)
    assert panel.face.currentIndex() == old_face
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
        assert [panel.table.item(i, 0).text() for i in range(4)] == ["2", "3", "4", "5"]
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
    assert editor.modes.tabText(0) == "Batch create"
    assert editor.modes.tabText(1) == "Batch edit"
    assert editor.timeline_card.height() == 366
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
    check, value = editor.batch_edit.fields["Duration"]
    check.setChecked(True)
    value.setText("12")
    editor.modes.setCurrentIndex(0)
    assert editor.create_batch.repetitions.text() == "2"
    assert editor.program == original
    editor.modes.setCurrentIndex(1)
    assert value.text() == "12" and check.isChecked()
    editor.batch_edit.reset.click()
    assert not editor.batch_edit.dirty and editor.program == original
    check, value = editor.batch_edit.fields["Duration"]
    check.setChecked(True)
    value.setText("-1")
    editor.batch_edit.apply_button.click()
    assert editor.batch_edit.isVisible() and editor.program == original
    value.setText("12")
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
    assert left.actions_button.isHidden()


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
    edit.epoch_scope.setCurrentIndex(edit.epoch_scope.findData("label:Adaptation"))
    assert editor.selected_paths == labelled
    assert edit.paths == labelled
    check, duration = edit.fields["Duration"]
    check.setChecked(True)
    duration.setText("7")
    edit.epoch_scope.setCurrentIndex(edit.epoch_scope.findData("all"))
    assert edit.epoch_scope.currentData() == "label:Adaptation"
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
        < composer.duration.mapTo(composer, QPoint()).y()
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
    opacity = next(
        f
        for f in row.parameters.forms
        if isinstance(f, ValueEditor) and "opacity" in f.children_by_key
    )
    opacity.children_by_key["opacity"].variant.children_by_key[
        "value"
    ].variant.control.setText("0.4")
    assert row.parameters.apply()
    after = composer.program.sequence[0].settings[0].model_dump(mode="json")
    assert after["opacity"]["value"] == 0.4
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
        "labels",
    }
    assert set(panel.tank.visible_elements) == set(panel.plot_toggles)
    assert COLORS.footprint != COLORS.projection
    panel.plot_toggles["projection"].click()
    assert not panel.tank.visible_elements["projection"]
    assert panel.tank.visible_elements["screens"]
    assert panel.enabled_screens == ()


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
    margins = parameters.extra_body.contentsMargins()
    assert margins.left() >= 20 and margins.top() >= 12
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
    definition = feedback.definition
    definition.name.setText("speed")
    definition.source.setText("external")
    definition.coordinates.setText("screen")
    definition.measurement.setCurrentIndex(2)
    definition.units.setCurrentText("mm/s")
    definition.submit()
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


def test_stimulus_mode_matches_duration_width(window, app):
    window.page_buttons[1].click()
    batch = window.protocol.editor.create_batch
    for width in (1350, 720):
        window.resize(width, 900)
        window.protocol.editor.modes.setCurrentIndex(0)
        app.processEvents()
        assert batch.composer.mode.width() == batch.composer.duration.width()
