"""Editor transactions and embedded hosting, independent of physical displays."""

import copy
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QMessageBox

from cephvr.generate_stimulus import window as window_module
from cephvr.generate_stimulus.window import AuthoringWindow
from cephvr.gui.stimulus_authoring import StimulusAuthoringPage


@pytest.fixture(scope="session")
def authoring_app():
    app = QApplication.instance() or QApplication([])
    yield app


def choose_save(monkeypatch, path) -> None:
    monkeypatch.setattr(window_module, "save_file_name", lambda *a: str(path))


def answer(monkeypatch, choice: str, prompts: list | None = None) -> None:
    """Stand in for the modal unsaved-changes prompt."""
    monkeypatch.setattr(
        window_module,
        "ask_unsaved",
        lambda *a: (prompts.append(a) if prompts is not None else None) or choice,
    )


@pytest.fixture
def editor(tmp_path: Path, authoring_app):
    window = AuthoringWindow(tmp_path)
    window.timer.stop()
    yield window
    window.saved = copy.deepcopy(window.documents)
    window.close()
    authoring_app.processEvents()


def test_edit_and_save(editor, tmp_path, monkeypatch) -> None:
    spin = editor.properties.findChild(QDoubleSpinBox, "spatial_period_mm")
    spin.setValue(20)
    assert editor.documents[0]["params"]["spatial_period_mm"] == 20
    path = tmp_path / "texture.json"
    choose_save(monkeypatch, path)
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
    choose_save(monkeypatch, path)
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
        before = editor.image.pixels.copy()
    editor.save()
    key = "spatial_period_mm" if workspace == 0 else "width_mm"
    spin = editor.properties.findChild(QDoubleSpinBox, key)
    spin.setValue(80)
    document = editor.documents[workspace]
    assert (document["params"] if workspace == 0 else document)[key] == 80
    assert editor.documents != editor.saved
    if workspace == 0:
        editor.preview()
        editor.collect()
        assert not np.array_equal(editor.image.pixels, before)
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

    def choose(_parent, title, suggested):
        assert title == "Save design as"
        suggestions.append(suggested)
        selected = next(choices)
        return str(selected) if selected else ""

    monkeypatch.setattr(window_module, "save_file_name", choose)
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
    from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoiseAppearance

    data = {"active_probability": 1, "min_active_cell_distance_mm": 0}
    panel = property_form(
        data, lambda: None, lambda: None, schema=SparseNoiseAppearance
    )
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
    answer(monkeypatch, "cancel")
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


def test_stale_results_are_ignored(editor) -> None:
    editor.jobs.serial = 4
    editor.jobs.results.put((3, None, "obsolete error"))
    editor.status.showMessage("current")
    editor.collect()
    assert editor.status.currentMessage() == "current"


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
    answer(monkeypatch, "discard", prompts)
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
        if editor.image.pixels is not None:
            loop.quit()

    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(4000, loop.quit)
    editor.preview()
    loop.exec()
    timer.stop()
    assert editor.image.pixels is not None


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
    assert selector.currentData() == "grating"
    assert selector.currentText() == "Grating"
    assert selector.findData("bars_horizontal") == -1
    assert selector.findData("bars_vertical") == -1
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
    assert selector.placeholderText().endswith(" bars (saved recipe)")
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
    choose_save(monkeypatch, path)
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


def run_jobs_inline(editor, monkeypatch) -> None:
    """Execute submitted work synchronously and queue its result like the worker."""
    from cephvr.generate_stimulus.errors import describe_error

    def submit(operation):
        editor.jobs.cancel.clear()
        editor.jobs.serial += 1
        try:
            outcome = (editor.jobs.serial, operation(lambda: None), None)
        except Exception as error:
            outcome = (editor.jobs.serial, None, describe_error(error))
        editor.jobs.results.put(outcome)
        return editor.jobs.serial

    monkeypatch.setattr(editor.jobs, "submit", submit)


def add_scatter(editor, **values) -> None:
    from PyQt6.QtWidgets import QPushButton

    [
        b
        for b in editor.properties.findChildren(QPushButton)
        if "Add object" in b.text()
    ][0].click()
    editor.documents[1]["surfaces"]["floor"]["scatters"][0].update(values)
    editor.rebuild()


def test_numeric_controls_take_type_and_limits_from_models(editor) -> None:
    editor.tabs.setCurrentIndex(1)
    add_scatter(editor)
    clustering = editor.properties.findChild(QDoubleSpinBox, "clustering")
    assert (clustering.minimum(), clustering.maximum()) == (0, 1)
    clustering.setValue(0.5)
    scale = editor.properties.findChild(QDoubleSpinBox, "min_scale")
    assert scale.minimum() > 0
    scale.setValue(0.25)
    scatter = editor.documents[1]["surfaces"]["floor"]["scatters"][0]
    assert (scatter["clustering"], scatter["min_scale"]) == (0.5, 0.25)
    width = editor.properties.findChild(QDoubleSpinBox, "width_mm")
    width.setValue(12.5)
    assert editor.documents[1]["width_mm"] == 12.5
    width.setValue(-5)
    assert editor.documents[1]["width_mm"] > 0
    segments = editor.properties.findChild(QDoubleSpinBox, "segments")
    segments.setValue(64)
    assert editor.documents[1]["segments"] == 64
    assert type(editor.documents[1]["segments"]) is int
    segments.setValue(2)
    assert editor.documents[1]["segments"] == 8
    editor.tabs.setCurrentIndex(0)
    editor.documents[0] = __import__(
        "cephvr.generate_stimulus.textures", fromlist=["new_texture"]
    ).new_texture("sparse_noise")
    editor.rebuild()
    size = editor.properties.findChild(QDoubleSpinBox, "square_size_mm")
    assert size.minimum() > 0
    size.setValue(-5)
    assert editor.documents[0]["square_size_mm"] > 0


def seed_edit(editor):
    from PyQt6.QtWidgets import QLineEdit, QWidget

    return editor.properties.findChild(QWidget, "seed").findChild(QLineEdit)


def test_tooltips_and_labels_survive_field_wrapping(editor) -> None:
    from PyQt6.QtWidgets import QLabel

    from cephvr.generate_stimulus.textures import new_texture

    editor.documents[0] = new_texture("sparse_noise")
    editor.rebuild()
    for key in ("active_probability", "min_active_cell_distance_mm"):
        assert editor.properties.findChild(QDoubleSpinBox, key).toolTip()
    editor.documents[0] = new_texture("grating")
    editor.rebuild()
    assert editor.properties.findChild(QDoubleSpinBox, "feature_sharpness").toolTip()
    captions = {
        label.text()
        for label in editor.properties.findChildren(QLabel)
        if label.property("role") == "label"
    }
    assert {
        "Spatial period (mm)",
        "Sharpness (0–1)",
        "Color A (linear RGB)",
    } <= captions
    editor.tabs.setCurrentIndex(1)
    add_scatter(editor)
    assert editor.properties.findChild(QDoubleSpinBox, "clustering").toolTip()
    editor.documents[0] = new_texture("polar_grating")
    editor.documents[0]["params"]["extra_values"] = [1, 2]
    editor.tabs.setCurrentIndex(0)
    from PyQt6.QtWidgets import QLineEdit

    assert editor.properties.findChild(QLineEdit, "extra_values").toolTip()


def test_pattern_dropdown_uses_names_with_ids_as_data(editor) -> None:
    from cephvr.gui.components import SelectionBox

    selector = editor.properties.findChild(SelectionBox)
    row = selector.findData("dots_rand")
    assert selector.itemText(row) == "Random dots"
    assert selector.itemData(row) == "dots_rand"
    assert selector.findData("sparse_noise") >= 0


def test_invalid_document_marks_field_dims_preview_and_recovers(
    editor, monkeypatch
) -> None:
    from PyQt6.QtWidgets import QLabel

    run_jobs_inline(editor, monkeypatch)
    editor.tabs.setCurrentIndex(1)
    add_scatter(editor, min_scale=5, max_scale=2)
    editor.preview()
    editor.collect()
    message = editor.status.currentMessage()
    assert message.startswith("Preview not updated. Floor")
    assert "pydantic" not in message and "[type=" not in message
    assert not editor.preview_note.isHidden()
    banners = [
        b
        for b in editor.properties.findChildren(QLabel, "FormError")
        if not b.isHidden()
    ]
    assert banners and "Minimum scale" in banners[0].text()
    # A located issue marks its own control with text and a tooltip, not colour alone.
    editor.documents[1]["surfaces"]["floor"]["scatters"][0].update(
        min_scale=1, max_scale=1
    )
    editor.documents[1]["surfaces"]["floor"]["relief"]["seed"] = "oops"
    editor.rebuild()
    editor.preview()
    editor.collect()
    edit = seed_edit(editor)
    assert edit.property("invalid") is True and edit.toolTip()
    notes = [
        n
        for n in editor.properties.findChildren(QLabel, "FieldError")
        if not n.isHidden()
    ]
    assert notes and notes[0].text()
    editor.documents[1]["surfaces"]["floor"]["relief"]["seed"] = 3
    editor.documents[1]["surfaces"]["floor"]["scatters"] = []
    editor.rebuild()
    editor.preview()
    editor.collect()
    assert editor.preview_note.isHidden() and not editor.image.dimmer.isEnabled()
    assert seed_edit(editor).property("invalid") is not True
    assert not [
        b
        for b in editor.properties.findChildren(QLabel, "FormError")
        if not b.isHidden()
    ]


def test_texture_error_marks_named_parameters_and_dims_image(editor, monkeypatch):
    from cephvr.generate_stimulus.textures import new_texture

    run_jobs_inline(editor, monkeypatch)
    editor.documents[0] = new_texture("noise_gray")
    editor.documents[0]["params"]["blur_mm"] = 5.0
    editor.rebuild()
    editor.preview()
    editor.collect()
    assert editor.image.dimmer.isEnabled()
    marked = {
        spin.objectName()
        for spin in editor.properties.findChildren(QDoubleSpinBox)
        if spin.property("invalid") is True
    }
    assert {"blur_mm", "element_size_mm"} <= marked


def test_rebuild_preserves_modified_state_and_surface_selection(editor) -> None:
    editor.tabs.setCurrentIndex(1)
    editor.surfaces.clearSelection()
    editor.surfaces.item(2).setSelected(True)
    assert editor.selected_names == ["wall_n"]
    editor.properties.findChild(QDoubleSpinBox, "texture_scale_mm").setValue(60)
    assert editor.isWindowModified()
    editor.rebuild()
    assert editor.isWindowModified()
    assert [
        i.data(Qt.ItemDataRole.UserRole) for i in editor.surfaces.selectedItems()
    ] == ["wall_n"]


def test_pending_text_is_committed_by_save_close_and_tab_change(
    editor, tmp_path, monkeypatch
) -> None:
    import json

    from PyQt6.QtTest import QTest

    from cephvr.generate_stimulus.textures import new_texture

    editor.documents[0] = new_texture("noise_gray")
    editor.rebuild()
    seed = seed_edit(editor)
    seed.setFocus()
    QTest.keyClicks(seed, "7")
    assert editor.documents[0]["params"]["seed"] == 0
    path = tmp_path / "noise.json"
    choose_save(monkeypatch, path)
    editor.save()
    assert json.loads(path.read_bytes())["params"]["seed"] == 7
    spin = editor.properties.findChild(QDoubleSpinBox, "element_size_mm")
    spin.lineEdit().setText("3")
    answer(monkeypatch, "discard")
    assert editor.confirm_close()
    assert editor.documents[0]["params"]["element_size_mm"] == 3
    editor.tabs.setCurrentIndex(1)
    assert editor.documents[0]["params"]["element_size_mm"] == 3
    editor.tabs.setCurrentIndex(0)
    spin = editor.properties.findChild(QDoubleSpinBox, "blur_mm")
    spin.lineEdit().setText("0.25")
    editor.tabs.setCurrentIndex(1)
    assert editor.documents[0]["params"]["blur_mm"] == 0.25
    assert editor.documents[0] != editor.saved[0]
    assert editor.documents[1] == editor.saved[1]


def test_open_asks_after_the_chooser_and_only_for_the_replaced_design(
    editor, tmp_path, monkeypatch
) -> None:
    from PyQt6.QtWidgets import QFileDialog

    from cephvr.generate_stimulus.documents import save_design
    from cephvr.generate_stimulus.models import ArenaDesign
    from cephvr.generate_stimulus.textures import new_texture

    texture, arena = tmp_path / "t.json", tmp_path / "a.json"
    save_design(new_texture("checker"), tmp_path, texture, tmp_path)
    save_design(ArenaDesign().model_dump(mode="json"), tmp_path, arena, tmp_path)
    prompts: list = []
    answer(monkeypatch, "cancel", prompts)
    editor.documents[0]["params"]["seed"] = 5
    chosen = [""]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (chosen[0], ""))
    editor.open()
    assert prompts == []
    # The arena file targets the other, unmodified workspace: no prompt.
    chosen[0] = str(arena)
    editor.open()
    assert prompts == [] and editor.active() == 1
    editor.tabs.setCurrentIndex(0)
    chosen[0] = str(texture)
    editor.open()
    assert len(prompts) == 1 and editor.documents[0]["params"]["seed"] == 5
    answer(monkeypatch, "discard", prompts)
    editor.open()
    assert editor.documents[0]["pattern"] == "checker"


def test_unsaved_prompt_defaults_to_cancel_and_offers_save_discard(
    editor, monkeypatch
) -> None:
    from cephvr.generate_stimulus import prompts

    seen = {}

    def fake_exec(box):
        seen["default"] = box.defaultButton().text()
        seen["escape"] = box.escapeButton().text()
        seen["buttons"] = sorted(b.text() for b in box.buttons())
        box.button(QMessageBox.StandardButton.Discard).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert prompts.ask_unsaved(editor, "t", "x") == "discard"
    assert seen["default"] == seen["escape"] == "Cancel"
    assert len(seen["buttons"]) == 3 and "Cancel" in seen["buttons"]
    monkeypatch.setattr(QMessageBox, "exec", lambda box: 0)
    assert prompts.ask_unsaved(editor, "t", "x") == "cancel"
    assert not prompts.ask_reset(editor, "t", "x", "Reset")


def test_pattern_change_prompts_only_when_parameters_were_edited(
    editor, monkeypatch
) -> None:
    from cephvr.gui.components import SelectionBox

    asked = []
    monkeypatch.setattr(window_module, "ask_reset", lambda *a: asked.append(a) or False)
    selector = editor.properties.findChild(SelectionBox)
    selector.setCurrentIndex(selector.findData("checker"))
    assert asked == [] and editor.documents[0]["pattern"] == "checker"
    editor.properties.findChild(QDoubleSpinBox, "cell_size_mm").setValue(40)
    selector = editor.properties.findChild(SelectionBox)
    selector.setCurrentIndex(selector.findData("dots_grid"))
    assert len(asked) == 1
    assert editor.documents[0]["pattern"] == "checker"
    assert selector.currentData() == "checker"
    monkeypatch.setattr(window_module, "ask_reset", lambda *a: True)
    selector.setCurrentIndex(selector.findData("dots_grid"))
    assert editor.documents[0]["pattern"] == "dots_grid"


def test_save_dialog_appends_json_suffix(editor, monkeypatch) -> None:
    from PyQt6.QtWidgets import QFileDialog

    from cephvr.generate_stimulus import prompts

    seen = {}

    def fake_exec(dialog):
        seen["suffix"] = dialog.defaultSuffix()
        seen["mode"] = dialog.acceptMode()
        return 1

    monkeypatch.setattr(QFileDialog, "exec", fake_exec)
    monkeypatch.setattr(QFileDialog, "selectedFiles", lambda dialog: ["x.json"])
    assert prompts.save_file_name(editor, "Save", "start") == "x.json"
    assert seen == {"suffix": "json", "mode": QFileDialog.AcceptMode.AcceptSave}


def test_poll_runs_only_while_a_job_is_outstanding(editor) -> None:
    from PyQt6.QtCore import QEventLoop

    assert not editor.poll.isActive()
    loop = QEventLoop()
    done = QTimer()
    done.setInterval(20)
    done.timeout.connect(lambda: loop.quit() if not editor.poll.isActive() else None)
    done.start()
    QTimer.singleShot(5000, loop.quit)
    editor.preview()
    assert editor.poll.isActive()
    loop.exec()
    done.stop()
    assert editor.image.pixels is not None
    assert not editor.poll.isActive()
    editor.shutdown()
    assert not editor.poll.isActive() and editor.jobs.closed.is_set()


def test_preview_pixels_are_converted_once_and_scaled_smoothly(editor) -> None:
    import numpy as np

    pixels = np.zeros((40, 80, 3), dtype=np.uint8)
    pixels[:, ::2] = 255
    editor.resize(900, 700)
    editor.image.set_pixels(pixels)
    image = editor.image.image
    assert (image.width(), image.height()) == (80, 40)
    shown = editor.image.pixmap()
    editor.image.refresh()
    editor.image.refresh()
    assert editor.image.image is image
    assert editor.image.pixmap().cacheKey() == shown.cacheKey()
    scaled = shown.toImage()
    # Smooth scaling blends the 1-pixel stripes instead of repeating them.
    row = scaled.height() // 2
    values = {scaled.pixelColor(x, row).red() for x in range(scaled.width())}
    assert len(values) > 2


def test_fit_button_sits_in_body_and_viewport_refits_on_size_change(
    editor, tmp_path
) -> None:
    from cephvr.generate_stimulus.arena import compile_arena
    from cephvr.generate_stimulus.models import ArenaDesign

    assert editor.fit_button.parentWidget() is editor.arena_controls
    assert editor.viewport.toolTip()
    viewport = editor.viewport
    refits = []
    viewport.fit = lambda: refits.append(1) or type(viewport).fit(viewport)
    design = ArenaDesign(subdivisions=1)
    viewport.set_arena(compile_arena(design, tmp_path))
    assert len(refits) == 1
    distance = viewport.distance
    viewport.distance = distance * 2
    design.surfaces["floor"].color = (1, 0, 0, 1)
    viewport.set_arena(compile_arena(design, tmp_path))
    assert len(refits) == 1 and viewport.distance == distance * 2
    design.width_mm = 900
    viewport.set_arena(compile_arena(design, tmp_path))
    assert len(refits) == 2 and viewport.distance != distance * 2


def test_viewport_uploads_only_the_variant_each_material_uses(
    editor, tmp_path, monkeypatch
) -> None:
    from types import SimpleNamespace

    from cephvr.generate_stimulus.arena import compile_arena
    from cephvr.generate_stimulus.documents import save_design
    from cephvr.generate_stimulus.models import ArenaDesign
    from cephvr.generate_stimulus.textures import new_texture

    save_design(new_texture("grating"), tmp_path, tmp_path / "f.json", tmp_path)
    design = ArenaDesign(subdivisions=1)
    for name in ("floor", "wall_n"):
        design.surfaces[name].texture = "f.json"
    design.surfaces["wall_n"].alpha_mode = "MASK"
    uploads = []
    released = SimpleNamespace(release=lambda: None)
    context = SimpleNamespace(
        texture=lambda size, comps, raw, dtype: uploads.append(raw) or released,
        buffer=lambda data: released,
        vertex_array=lambda *a, **k: released,
    )
    monkeypatch.setattr(
        "cephvr.visual_stimulus.rendering.arena_gpu.configure_sampler",
        lambda texture, sampler: None,
    )
    viewport = editor.viewport
    viewport.ctx, viewport.program = context, object()
    viewport.result = compile_arena(design, tmp_path)
    viewport._upload()
    textured = [d for d in viewport.draws if d[2] is not None]
    assert textured and len(uploads) == 2
    # Opaque and cutout materials need different alpha handling.
    assert uploads[0] != uploads[1]


def test_surface_list_and_error_styles_are_themed(authoring_app, editor) -> None:
    from cephvr.gui.theme import (
        PHOSPHOR_COLORS,
        RETRO_COLORS,
        phosphor_stylesheet,
        retro_stylesheet,
        stylesheet,
    )

    editor.tabs.setCurrentIndex(1)
    assert editor.surfaces.property("role") == "surfaces"
    assert editor.surfaces.accessibleName() == "Surfaces"
    for sheet in (
        stylesheet(),
        retro_stylesheet(),
        retro_stylesheet(PHOSPHOR_COLORS) + phosphor_stylesheet(),
    ):
        assert "QListWidget[role='surfaces']::item:selected" in sheet
        assert "QDoubleSpinBox[invalid='true']" in sheet
    original = authoring_app.styleSheet()
    try:
        authoring_app.setStyleSheet(stylesheet())
        editor.show()
        authoring_app.processEvents()
        image = editor.surfaces.viewport().grab().toImage()
        background = image.pixelColor(image.width() - 3, image.height() - 3)
        # A themed list is dark, not the default white base.
        assert background.lightness() < 60
        assert RETRO_COLORS.input
    finally:
        authoring_app.setStyleSheet(original)


@pytest.mark.parametrize(
    "pattern", ["noise_binary", "bars_horizontal", "bars_vertical"]
)
def test_legacy_open_is_modified_and_save_never_overwrites_the_source(
    editor, tmp_path, monkeypatch, pattern
) -> None:
    import json

    from PyQt6.QtWidgets import QFileDialog
    from tests.generate_stimulus.test_authoring import LEGACY_NOISE

    source = tmp_path / "legacy.json"
    recipe = copy.deepcopy(LEGACY_NOISE)
    if pattern != "noise_binary":
        recipe["pattern"] = pattern
        recipe["params"] = {"line_width_mm": 5, "line_spacing_mm": 8}
    source.write_text(json.dumps(recipe))
    original = source.read_bytes()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (str(source), "")
    )
    editor.open()
    assert "dropped fields" in editor.legacy_note.text()
    assert not editor.legacy_note.isHidden()
    assert editor.documents[0] != editor.saved[0] and editor.isWindowModified()
    suggestions, warnings = [], []
    choices = iter([source, tmp_path / "legacy.converted.json"])

    def choose(_parent, title, suggested):
        suggestions.append((title, suggested))
        return str(next(choices))

    monkeypatch.setattr(window_module, "save_file_name", choose)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a))
    assert not editor.save()
    assert source.read_bytes() == original and len(warnings) == 1
    assert editor.documents[0] != editor.saved[0]
    assert editor.save()
    converted = tmp_path / "legacy.converted.json"
    assert source.read_bytes() == original
    assert json.loads(converted.read_text())["cephvr_asset_type"] == "texture_field"
    assert suggestions[0][1] == str(converted) and "legacy" in suggestions[0][0]
    assert editor.paths[0] == converted and editor.legacy[0] is None
    assert editor.documents[0] == editor.saved[0] and not editor.isWindowModified()
    assert editor.legacy_note.isHidden()


def test_non_legacy_open_keeps_plain_save(editor, tmp_path, monkeypatch) -> None:
    from PyQt6.QtWidgets import QFileDialog

    from cephvr.generate_stimulus.documents import save_design
    from cephvr.generate_stimulus.textures import new_texture

    path = tmp_path / "field.json"
    save_design(new_texture("checker"), tmp_path, path, tmp_path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    editor.open()
    assert editor.legacy_note.isHidden() and not editor.isWindowModified()
    seen = []
    monkeypatch.setattr(
        window_module,
        "save_file_name",
        lambda _p, title, s: seen.append((title, s)) or s,
    )
    assert editor.save()
    assert seen == [("Save design as", str(path))]
