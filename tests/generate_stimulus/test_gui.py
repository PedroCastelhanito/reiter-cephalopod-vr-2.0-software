"""Editor transactions and embedded hosting, independent of physical displays."""

import copy
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QFileDialog, QMessageBox

from cephvr.generate_stimulus.window import AuthoringWindow
from cephvr.gui.stimulus_authoring import StimulusAuthoringPage


@pytest.fixture(scope="session")
def authoring_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def editor(tmp_path: Path, authoring_app):
    window = AuthoringWindow(tmp_path)
    window.timer.stop()
    yield window
    window.saved = copy.deepcopy(window.documents)
    window.close()
    authoring_app.processEvents()


def test_edit_undo_redo_and_save(editor, tmp_path, monkeypatch) -> None:
    spin = editor.properties.findChild(QDoubleSpinBox, "spatial_period_mm")
    spin.setValue(20)
    assert editor.documents[0]["params"]["spatial_period_mm"] == 20
    editor.undo()
    assert editor.documents[0]["params"]["spatial_period_mm"] == 12
    editor.redo()
    assert editor.documents[0]["params"]["spatial_period_mm"] == 20
    path = tmp_path / "texture.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    editor.save()
    assert path.exists()
    assert editor.documents == editor.saved


@pytest.mark.parametrize("workspace", [0, 1])
def test_edits_after_save_update_current_document_preview_and_next_save(
    editor, tmp_path, monkeypatch, workspace
):
    import json

    import numpy as np

    editor.tabs.setCurrentIndex(workspace)
    path = tmp_path / "design.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *_: pytest.fail("Save failed"))

    def submit(operation):
        editor.jobs.cancel.clear()
        editor.jobs.serial += 1
        result = operation(lambda: None)
        editor.jobs.results.put((editor.jobs.serial, result, None))
        return editor.jobs.serial

    monkeypatch.setattr(editor.jobs, "submit", submit)
    if workspace == 0:
        editor.preview()
        editor.collect()
        before = editor.pixels.copy()
    editor.save()
    key = "spatial_period_mm" if workspace == 0 else "width_mm"
    spin = editor.properties.findChild(QDoubleSpinBox, key)
    spin.setValue(80)
    document = editor.documents[workspace]
    assert (document["params"] if workspace == 0 else document)[key] == 80
    assert editor.documents != editor.saved
    assert editor.history[workspace][editor.positions[workspace]] == document
    if workspace == 0:
        editor.preview()
        editor.collect()
        assert not np.array_equal(editor.pixels, before)
    editor.save()
    saved = json.loads(path.read_bytes())
    assert (saved["params"] if workspace == 0 else saved)[key] == 80
    # Repeated saves must keep the newly displayed controls connected too.
    editor.properties.findChild(QDoubleSpinBox, key).setValue(40)
    document = editor.documents[workspace]
    assert (document["params"] if workspace == 0 else document)[key] == 40


@pytest.mark.parametrize("workspace", [0, 1])
def test_save_as_always_asks_and_cancel_preserves_previous_file(
    editor, tmp_path, monkeypatch, workspace
):
    editor.tabs.setCurrentIndex(workspace)
    original = tmp_path / "original.json"
    destination = tmp_path / "copy.json"
    choices = iter([original, destination, None])
    suggestions = []

    def choose(_parent, title, suggested, _filter):
        assert title == "Save design as"
        suggestions.append(suggested)
        selected = next(choices)
        return str(selected) if selected else "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *_: pytest.fail("Unexpected save error")
    )
    editor.save()
    original_bytes = original.read_bytes()
    target = (
        editor.documents[workspace]["params"]
        if workspace == 0
        else editor.documents[workspace]["surfaces"]["floor"]
    )
    key = "spatial_period_mm" if workspace == 0 else "texture_scale_mm"
    target[key] = 123
    editor.save()
    assert original.read_bytes() == original_bytes
    assert destination.exists()
    assert editor.paths[workspace] == destination
    assert editor.documents == editor.saved
    copied_bytes = destination.read_bytes()
    saved = copy.deepcopy(editor.saved)
    target = (
        editor.documents[workspace]["params"]
        if workspace == 0
        else editor.documents[workspace]["surfaces"]["floor"]
    )
    target[key] = 456
    draft = copy.deepcopy(editor.documents)
    editor.save()
    assert editor.documents == draft
    assert editor.saved == saved
    assert editor.paths[workspace] == destination
    assert destination.read_bytes() == copied_bytes
    assert original.read_bytes() == original_bytes
    assert suggestions[1:] == [str(original), str(destination)]


def test_sparse_probability_and_distance_controls(authoring_app) -> None:
    from cephvr.generate_stimulus.properties import property_form

    data = {"active_probability": 1, "min_active_cell_distance_mm": 0}
    panel = property_form(data, lambda: None, lambda: None)
    probability = panel.findChild(QDoubleSpinBox, "active_probability")
    distance = panel.findChild(QDoubleSpinBox, "min_active_cell_distance_mm")
    assert (probability.minimum(), probability.maximum()) == (0, 1)
    assert distance.minimum() == 0
    probability.setValue(0.25)
    distance.setValue(12.5)
    assert data == {"active_probability": 0.25, "min_active_cell_distance_mm": 12.5}
    panel.close()


@pytest.mark.parametrize("width", [300, 620])
def test_parameter_pairs_keep_full_width_rgb(authoring_app, width):
    from PyQt6.QtWidgets import QWidget

    from cephvr.generate_stimulus.properties import property_form

    data = {
        "texture_resolution": 1024,
        "color_a": [1.0, 1.0, 1.0],
        "spatial_period_mm": 12.0,
        "orientation_deg": 90.0,
        "feature_sharpness": 1.0,
        "fit_cycles_to_tile": False,
    }
    panel = property_form(data, lambda: None, lambda: None, title="Parameters")
    assert panel.findChild(QWidget, "fit_cycles_to_tile") is None
    panel.resize(width, panel.sizeHint().height())
    panel.show()
    authoring_app.processEvents()
    period = panel.findChild(QDoubleSpinBox, "spatial_period_mm")
    orientation = panel.findChild(QDoubleSpinBox, "orientation_deg")
    left, right = period.parentWidget(), orientation.parentWidget()
    assert left.y() == right.y()
    assert left.x() + left.width() <= right.x()
    assert abs(left.width() - right.width()) <= 1
    color = panel.findChild(QWidget, "color_a")
    sharpness = panel.findChild(QDoubleSpinBox, "feature_sharpness")
    assert left.y() < sharpness.parentWidget().y() < color.parentWidget().y()
    assert panel.findChild(QDoubleSpinBox, "texture_resolution") is None
    assert data["texture_resolution"] == 1024
    assert color.parentWidget().width() > left.width()
    channels = color.findChildren(QDoubleSpinBox)
    assert len({channel.y() for channel in channels}) == 1
    channels[1].setValue(0.25)
    orientation.setValue(45)
    assert data["color_a"] == [1.0, 0.25, 1.0]
    assert data["orientation_deg"] == 45
    panel.close()


def test_close_can_preserve_unsaved_work(editor, monkeypatch) -> None:
    editor.documents[0]["params"]["seed"] = 12
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No
    )
    assert not editor.close()
    assert not editor.jobs.closed.is_set()


def test_multiple_surfaces_edit_only_changed_field(editor) -> None:
    editor.tabs.setCurrentIndex(1)
    editor.documents[1]["surfaces"]["wall_n"]["texture_scale_mm"] = 42
    editor.surfaces.item(2).setSelected(True)
    spin = editor.properties.findChild(QDoubleSpinBox, "texture_scale_mm")
    spin.setValue(60)
    assert editor.documents[1]["surfaces"]["floor"]["texture_scale_mm"] == 60
    assert editor.documents[1]["surfaces"]["wall_n"]["texture_scale_mm"] == 60
    assert editor.documents[1]["surfaces"]["roof"]["visible"] is False
    from cephvr.generate_stimulus.documents import apply_changes

    original = {"relief": {"height_mm": 0, "seed": 1}}
    target = {"relief": {"height_mm": 0, "seed": 99}}
    apply_changes(target, original, {"relief": {"height_mm": 2, "seed": 1}})
    assert target == {"relief": {"height_mm": 2, "seed": 99}}


def test_stale_results_and_export_controls(editor) -> None:
    editor.jobs.serial = 4
    editor.jobs.results.put((3, None, "obsolete error"))
    editor.status.showMessage("current")
    editor.collect()
    assert editor.status.currentMessage() == "current"
    editor.set_exporting(True)
    assert not editor.tabs.isEnabled()
    assert not editor.properties.isEnabled()
    editor.cancel_job()
    assert editor.tabs.isEnabled()


def test_embedded_editor_preserves_drafts_and_standalone_window(editor, tmp_path):
    page = StimulusAuthoringPage()
    assert page.editor is None
    assert page.composition_anchor.isHidden()
    assert page.composition_anchor.context() is None
    page.open_editor(tmp_path, None)
    child = page.editor
    assert editor.isWindow()
    assert not child.isWindow()
    child.documents[0]["params"]["seed"] = 123
    page.open_editor(tmp_path / "other", None)
    assert page.editor is child
    assert child.documents[0]["params"]["seed"] == 123
    assert all(
        action.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut
        for action in child.findChildren(QAction)
        if not action.shortcut().isEmpty()
    )
    page.shutdown()
    assert child.jobs.closed.is_set()


def test_close_approval_is_reused_only_for_same_documents(editor, monkeypatch):
    prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a: prompts.append(a) or QMessageBox.StandardButton.Yes,
    )
    editor.documents[0]["params"]["seed"] = 123
    assert editor.confirm_close()
    assert editor.confirm_close()
    assert len(prompts) == 1
    editor.documents[0]["params"]["seed"] = 124
    assert editor.confirm_close()
    assert len(prompts) == 2


def test_preview_worker_completes_without_viewport(editor) -> None:
    assert editor.image.objectName() == "AssetPreviewPixels"
    from PyQt6.QtCore import QEventLoop

    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(20)

    def poll():
        editor.collect()
        if editor.pixels is not None:
            loop.quit()

    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(4000, loop.quit)
    editor.preview()
    loop.exec()
    timer.stop()
    assert editor.pixels is not None


def test_viewport_picks_visible_surface_and_rejects_backface(editor, tmp_path) -> None:
    import numpy as np

    from cephvr.generate_stimulus.arena import compile_arena
    from cephvr.generate_stimulus.models import ArenaDesign

    viewport = editor.viewport
    viewport.result = compile_arena(
        ArenaDesign(width_mm=1, depth_mm=1, subdivisions=1), tmp_path
    )
    selected = []
    viewport.selected.connect(selected.append)
    viewport.mvp = np.diag([1, 1, -1, 1])
    viewport._pick(viewport.width() / 2, viewport.height() / 2)
    assert selected == ["floor"]
    selected.clear()
    viewport.mvp = np.eye(4)
    viewport._pick(viewport.width() / 2, viewport.height() / 2)
    assert not selected


def test_shared_controls_and_responsive_columns_preserve_edits(editor):
    from cephvr.gui.components import Button, Card, SelectionBox

    assert editor.findChildren(Card)
    assert isinstance(editor.face, SelectionBox)
    assert isinstance(editor.fit_button, Button)
    selector = editor.properties.findChild(SelectionBox)
    assert selector.currentText() == "grating"
    assert selector.findText("bars_horizontal") == -1
    assert selector.findText("bars_vertical") == -1
    assert editor.properties.findChild(QDoubleSpinBox, "orientation_deg") is not None
    spin = editor.properties.findChild(QDoubleSpinBox, "spatial_period_mm")
    spin.setValue(24)
    editor.columns.arrange(600)
    assert editor.columns.mode == "stacked"
    assert editor.properties.findChild(QDoubleSpinBox, "spatial_period_mm") is spin
    assert spin.value() == 24
    editor.columns.arrange(1000)
    assert editor.columns.mode == "wide"
    assert spin.value() == 24
    editor.set_exporting(True)
    assert all(not action.isEnabled() for action in editor.file_actions)
    assert not editor.properties.isEnabled()
    editor.cancel_job()


def test_authoring_captions_follow_shared_theme(editor):
    from cephvr.gui.components import Card

    editor.setProperty("retroConsole", True)
    editor.setProperty("retroPalette", "amber_phosphor")
    editor.refresh_captions()
    assert editor.findChildren(Card)[0].caption.text().startswith("< ")
    editor.setProperty("retroConsole", False)
    editor.refresh_captions()
    assert editor.findChildren(Card)[0].caption.text() == "Design files"


def test_tile_preview_has_no_projector_control(editor):
    assert editor.face_field.isHidden()
    editor.preview_mode.setCurrentIndex(1)
    assert not editor.face_field.isHidden()
    editor.preview_mode.setCurrentIndex(0)
    assert editor.face_field.isHidden()


@pytest.mark.windows
@pytest.mark.parametrize("style", ["standard", "retro", "amber_phosphor"])
def test_dashboard_authoring_popup_shows_all_short_list_choices(
    authoring_app, tmp_path, style
):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtTest import QTest

    from cephvr.gui.theme import apply_theme, load_terminal_font
    from cephvr.gui.window import DashboardWindow

    if authoring_app.platformName() != "windows":
        pytest.skip("Requires the Windows Qt platform")
    original_sheet = authoring_app.styleSheet()
    load_terminal_font()
    apply_theme(authoring_app)
    host = DashboardWindow(
        sample=True,
        settings=QSettings(str(tmp_path / "popup.ini"), QSettings.Format.IniFormat),
    )
    try:
        host.appearance.select(style, persist=False)
        host.protocol.assets.folders["root"].editor.setText(str(tmp_path))
        host.show()
        QTest.qWait(100)
        host.generate_stimulus_button.click()
        authoring_app.processEvents()
        child = host.authoring_page.editor
        child.timer.stop()
        for index in (0, 1):
            child.preview_mode.setCurrentIndex(index)
            for control in (
                (child.preview_mode, child.face) if index else (child.preview_mode,)
            ):
                control.showPopup()
                authoring_app.processEvents()
                view = control.view()
                for row in range(control.count()):
                    rect = view.visualRect(control.model().index(row, 0))
                    assert rect.top() >= 0
                    assert rect.bottom() < view.viewport().height()
                if style == "amber_phosphor" and control is child.preview_mode:
                    view.window().grab().save(str(tmp_path / f"view-{index}.png"))
                control.hidePopup()
    finally:
        host.authoring_page.shutdown()
        host.close()
        host.deleteLater()
        authoring_app.processEvents()
        authoring_app.setStyleSheet(original_sheet)


@pytest.mark.windows
@pytest.mark.parametrize("dashboard", [False, True])
def test_first_embedded_open_preserves_native_window(
    authoring_app, tmp_path, dashboard
):
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

    if authoring_app.platformName() != "windows":
        pytest.skip("Requires the Windows Qt platform")

    events = []

    class WindowEvents(QObject):
        def eventFilter(self, watched, event):
            if event.type() in (
                QEvent.Type.WinIdChange,
                QEvent.Type.Hide,
                QEvent.Type.Close,
            ):
                events.append(event.type())
            return False

    if dashboard:
        from PyQt6.QtCore import QSettings

        from cephvr.gui.window import DashboardWindow

        host = DashboardWindow(
            settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
        )
        stack, page = host.stack, host.authoring_page
        blank = stack.widget(0)
        host.protocol.assets.folders["root"].editor.setText(str(tmp_path))
    else:
        host = QWidget()
        host.resize(960, 720)
        stack = QStackedWidget()
        blank = QWidget()
        page = StimulusAuthoringPage()
        stack.addWidget(blank)
        stack.addWidget(page)
        QVBoxLayout(host).addWidget(stack)
    observer = WindowEvents(host)
    host.installEventFilter(observer)
    host.show()
    QTest.qWait(100)
    handle = int(host.winId())
    events.clear()
    try:
        for _ in range(2):
            if dashboard:
                host.generate_stimulus_button.click()
                assert stack.currentWidget() is page
            else:
                page.open_editor(tmp_path, None)
                stack.setCurrentWidget(page)
            QTest.qWait(100)
            assert int(host.winId()) == handle
            assert not events
            assert host.isVisible()
            stack.setCurrentWidget(blank)
        # Switching to the actual GL view must preserve the same native window too.
        stack.setCurrentWidget(page)
        page.editor.tabs.setCurrentIndex(1)
        QTest.qWait(400)
        assert int(host.winId()) == handle
        assert not events
        assert not page.editor.viewport.error
    finally:
        page.shutdown()
        host.close()
        host.deleteLater()
        authoring_app.processEvents()


@pytest.mark.parametrize("pattern", ["bars_horizontal", "bars_vertical"])
def test_bars_controls_and_single_row_rgb(editor, pattern):
    from PyQt6.QtWidgets import QWidget

    from cephvr.generate_stimulus.textures import new_texture
    from cephvr.gui.components import SelectionBox

    editor.documents[0] = new_texture(pattern)
    editor.rebuild()
    selector = editor.properties.findChild(SelectionBox)
    assert selector.currentIndex() == -1
    assert selector.placeholderText() == f"{pattern} (saved recipe)"
    assert editor.documents[0]["pattern"] == pattern
    names = {
        spin.objectName() for spin in editor.properties.findChildren(QDoubleSpinBox)
    }
    assert {"bar_width_mm", "blur_mm"} <= names
    assert (
        not {"texture_resolution", "tile_width_mm", "line_spacing_mm", "line_width_mm"}
        & names
    )
    width = editor.properties.findChild(QDoubleSpinBox, "bar_width_mm")
    width.setValue(12.5)
    assert editor.documents[0]["params"]["bar_width_mm"] == 12.5
    for key in ("color_a", "color_b"):
        row = editor.properties.findChild(QWidget, key)
        layout = row.layout()
        assert [layout.getItemPosition(i)[:2] for i in range(3)] == [
            (0, 0),
            (0, 1),
            (0, 2),
        ]
        layout.itemAt(2).widget().setValue(0.25)
        assert editor.documents[0]["params"][key][2] == 0.25


def test_tile_and_phase_controls_absent_for_all_textures(editor):
    from cephvr.generate_stimulus.textures import PATTERNS, new_texture

    for pattern in PATTERNS:
        editor.documents[0] = new_texture(pattern)
        editor.rebuild()
        assert editor.properties.findChild(QDoubleSpinBox, "tile_width_mm") is None
        assert editor.properties.findChild(QDoubleSpinBox, "phase_cycles") is None


@pytest.mark.parametrize("arena", [False, True])
def test_preview_is_memory_only_and_save_creates_file(
    editor, tmp_path, monkeypatch, arena
):
    import builtins
    import io
    import os

    from PyQt6.QtWidgets import QPushButton

    if arena:
        editor.tabs.setCurrentIndex(1)
        editor.documents[1]["subdivisions"] = 1
    editor.timer.stop()

    def submit(operation):
        result = operation(lambda: None)
        editor.jobs.results.put((editor.jobs.serial, result, None))
        return editor.jobs.serial

    monkeypatch.setattr(editor.jobs, "submit", submit)
    original_open, original_io_open, original_os_open = builtins.open, io.open, os.open

    def readonly_open(original):
        def guarded(file, mode="r", *args, **kwargs):
            assert not any(flag in mode for flag in "wax+"), (
                "Preview attempted a file write"
            )
            return original(file, mode, *args, **kwargs)

        return guarded

    def readonly_os_open(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        return original_os_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", readonly_open(original_open))
        guard.setattr(io, "open", readonly_open(original_io_open))
        guard.setattr(os, "open", readonly_os_open)
        editor.preview()
        editor.collect()
    assert list(tmp_path.iterdir()) == []
    assert editor.status.currentMessage() == ""
    assert not hasattr(editor, "caption")
    assert not any(
        "Cancel generation" in button.text()
        for button in editor.findChildren(QPushButton)
    )
    path = tmp_path / "design.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    editor.save()
    assert list(tmp_path.iterdir()) == [path]
    assert path.stat().st_size > 0


@pytest.mark.windows
def test_native_arena_viewport_uses_gltf_top_left_image_coordinates():
    import numpy as np

    from cephvr.generate_stimulus.viewport import FRAGMENT, VERTEX
    from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes
    from cephvr.visual_stimulus.resources.media import ImagePixels

    moderngl = pytest.importorskip("moderngl")
    context = moderngl.create_standalone_context(require=330)
    owned = []

    def track(value):
        owned.append(value)
        return value

    try:
        program = track(context.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT))
        vertices = np.array(
            [
                [-1, -1, 0, 0, 1, 1, 1, 1, 1],
                [1, -1, 0, 1, 1, 1, 1, 1, 1],
                [-1, 1, 0, 0, 0, 1, 1, 1, 1],
                [1, 1, 0, 1, 0, 1, 1, 1, 1],
            ],
            dtype="f4",
        )
        buffer = track(context.buffer(vertices.tobytes()))
        array = track(
            context.vertex_array(
                program, [(buffer, "3f 2f 4f", "position", "uv", "color")]
            )
        )
        pixels = np.array(
            [[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [255, 255, 0]]], dtype=np.uint8
        )
        image = ImagePixels(
            2, 2, "uint8", 3, ("red", "green", "blue"), pixels, "linear", "none"
        )
        texture = track(
            context.texture((2, 2), 4, linear_rgba_bytes(image), dtype="f4")
        )
        texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
        texture.use(0)
        target = track(context.simple_framebuffer((2, 2), components=3))
        target.use()
        program["mvp"].write(np.eye(4, dtype="f4").tobytes())
        program["factor"].value = (1, 1, 1, 1)
        program["image"].value = 0
        program["textured"].value = True
        program["alpha_mode"].value = 0
        program["cutoff"].value = 0.5
        array.render(mode=moderngl.TRIANGLE_STRIP)
        actual = np.frombuffer(
            target.read(components=3, alignment=1), dtype=np.uint8
        ).reshape(2, 2, 3)[::-1]
        np.testing.assert_array_equal(actual, pixels)
    finally:
        for item in reversed(owned):
            item.release()
        context.release()
