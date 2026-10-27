"""Stimulus authoring: sparse noise, grating, media families, imports and trial preview."""

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget
from tests.gui.support import ParameterDocument


def _grating_row(app):
    from cephvr.gui.epoch_composer import EpochComposer
    from cephvr.gui.protocol_document import blank_program

    composer = EpochComposer()
    composer.program = blank_program().model_copy(
        update={"category": "media_presentation"}
    )
    composer.set_screens(("Front",))
    composer.refresh_rows()
    composer.change_type("Front", "Grating")
    return composer, composer.rows["Front"]


def test_field_keeps_a_tooltip_set_before_wrapping(app):
    from cephvr.gui.components import field

    kept, hinted, plain = QLineEdit(), QLineEdit(), QLineEdit()
    kept.setToolTip("set earlier")
    hinted.setToolTip("replaced")
    wrappers = [  # The wrappers own the editors; keep them alive.
        field("Kept", kept),
        field("Hinted", hinted, hint="from hint"),
        field("Plain", plain),
    ]
    assert kept.toolTip() == "set earlier"
    assert hinted.toolTip() == "from hint"
    assert plain.toolTip() == "" and len(wrappers) == 3


@pytest.mark.parametrize("width", [1100, 1600, 2400])
def test_grating_row_controls_keep_single_line_height(app, width):
    from cephvr.gui.grating_appearance import GratingAppearance

    composer, row = _grating_row(app)
    composer.resize(width, 700)
    composer.show()
    QTest.qWait(50)
    heights = {
        title: control.height()
        for title, control in row.columns
        if title in {"Spatial period (mm)", "Color A (linear RGB)", "Speed (mm/s)"}
    }
    assert len(heights) == 3
    # The RGB triplets are one horizontal row, so no control is stretched taller.
    assert max(heights.values()) < 60 and len(set(heights.values())) == 1
    appearance = next(
        f for f in row.parameters.forms if isinstance(f, GratingAppearance)
    )
    assert [e.text() for e in appearance.color_a.edits] == ["1.0"] * 3
    assert [e.text() for e in appearance.color_b.edits] == ["0.0"] * 3
    assert appearance.sharpness.toolTip().startswith("0 = sinusoidal")
    composer.close()


def test_grating_colors_round_trip_and_tab_follows_visual_order(app):
    from cephvr.gui.grating_appearance import GratingAppearance

    composer, row = _grating_row(app)
    appearance = next(
        f for f in row.parameters.forms if isinstance(f, GratingAppearance)
    )
    appearance.color_a.edits[1].setText("0.75")
    appearance.color_b.edits[2].setText("0.25")
    value = appearance.read()
    assert value["mean_linear_rgb"] == pytest.approx([0.5, 0.375, 0.625])
    assert value["modulation_linear_rgb"] == pytest.approx([0.5, 0.375, 0.375])
    appearance.color_a.edits[0].setText("2")
    with pytest.raises(ValueError, match="linear RGB"):
        appearance.read()

    def first_focus(control: QWidget) -> QWidget:
        found = [control, *control.findChildren(QWidget)]
        return next(w for w in found if w.focusPolicy() & 1)

    visible = [
        first_focus(control)
        for title, control in row.columns
        if title and title != "Linked to" and control.isVisibleTo(row)
    ]
    chain, widget = [], visible[0]
    for _ in range(400):
        chain.append(widget)
        widget = widget.nextInFocusChain()
        if widget is visible[0]:
            break
    positions = [chain.index(w) for w in visible]
    assert positions == sorted(positions)
    composer.close()


@pytest.mark.parametrize("cls", ["StimulusParameters", "SubgroupEditor"])
def test_focus_callbacks_do_not_reach_deleted_widgets(app, monkeypatch, cls):
    from PyQt6 import sip

    from cephvr.gui.stimulus_parameters import StimulusParameters
    from cephvr.gui.subgroup_editor import SubgroupEditor

    owner = {
        "StimulusParameters": StimulusParameters,
        "SubgroupEditor": SubgroupEditor,
    }[cls]
    calls: list[object] = []
    original = owner.finish_edit

    def spy(self, previous, current):
        assert not sip.isdeleted(self)
        calls.append(self)
        return original(self, previous, current)

    monkeypatch.setattr(owner, "finish_edit", spy)
    widget = owner()
    app.focusChanged.emit(None, None)
    assert calls == [widget]
    widget.deleteLater()
    QApplication.sendPostedEvents(None, 52)  # QEvent.Type.DeferredDelete
    assert sip.isdeleted(widget)
    app.focusChanged.emit(None, None)
    assert calls == [widget]


@pytest.mark.parametrize(
    "preset, kind, profile",
    [
        ("Uniform", "texture", None),
        ("Texture", "texture", "png_uint_v1"),
        ("Image tile", "texture", "png_uint_v1"),
        ("Grating", "texture", None),
        ("Sine grating", "texture", None),
        ("Square grating", "texture", None),
        ("Checkerboard", "texture", None),
        ("Image", "image", "png_uint_v1"),
        ("Looming image", "image", "png_uint_v1"),
        ("Sparse noise", "sparse_noise", None),
        ("Video", "video", "mp4_h264_sdr8_v1"),
        ("3D arena", "arena", "glb2_static_unlit_v1"),
    ],
)
def test_every_preset_builds_binds_and_applies(window, preset, kind, profile):
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import PRESETS, add_stimulus

    assert preset in PRESETS
    program = add_stimulus(blank_program(), 0, preset, ("Left",))
    setting = program.sequence[0].settings[-1]
    assert setting.kind == kind
    assert [a.profile for a in program.assets] == ([profile] if profile else [])
    document = ParameterDocument(window)
    document.set_program(program)
    assert document.parameters.apply(), document.parameters.message.text()
    assert document.parameters.program.sequence[0].settings[-1].kind == kind
    document.parameters.deleteLater()


def test_trial_preview_rebuilds_from_the_current_program(window, app, tmp_path):
    from PyQt6.QtGui import QImage

    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_file_stimulus

    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    path = tmp_path / "tile.png"
    assert image.save(str(path))
    first = add_file_stimulus(
        blank_program(), 0, "Texture", ("Left",), str(tmp_path), str(path)
    )
    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(first)
    window.protocol.assets.folders["root"].editor.setText(str(tmp_path))
    window.open_trial_preview()
    preview = window.trial_preview
    assert preview is not None and preview.program == first
    assert preview.stale.isHidden()
    window.open_trial_preview()  # Unchanged program: raise the same window.
    assert window.trial_preview is preview
    second = add_file_stimulus(
        first, 0, "Texture", ("Right",), str(tmp_path), str(path)
    )
    editor.set_program(second)
    app.processEvents()
    assert not preview.stale.isHidden()
    preview.refresh_requested.emit()
    app.processEvents()
    rebuilt = window.trial_preview
    assert rebuilt is not preview and rebuilt.program == editor.program == second
    assert rebuilt.stale.isHidden()
    rebuilt.close()
    app.processEvents()
    assert window.trial_preview is None


def test_generate_assets_navigation_has_its_own_icon(window):
    icons = [button.property("iconName") for button in window.page_buttons]
    assert icons[4] != icons[1] and len(set(icons)) == len(icons)


def test_stimulus_geometry_is_validated_only_when_inputs_change(window, monkeypatch):
    from tests.visual_stimulus.support import make_compile_context

    payload = make_compile_context().display.geometry.model_dump(mode="json")
    projectors = window.devices.projectors
    monkeypatch.setattr(
        projectors.rig_editor, "geometry_payload", lambda drafts: payload
    )
    projectors._geometry_dirty = True
    first = window.stimulus_geometry()
    assert window.stimulus_geometry() is first
    payload["observer_mm"] = [1.0, 0.0, 0.0]
    changed = window.stimulus_geometry()
    assert changed is not first and changed.observer_mm == (1.0, 0.0, 0.0)
    assert window.stimulus_geometry() is changed


def test_external_file_is_imported_once_per_unchanged_source(tmp_path, monkeypatch):
    from cephvr.gui import stimulus_asset_paths
    from cephvr.gui.stimulus_asset_paths import AssetPathResolver
    from cephvr.gui.stimulus_files import resolve_stimulus_file

    root = tmp_path / "assets"
    root.mkdir()
    source = tmp_path / "external.png"
    source.write_bytes(b"one")
    first = resolve_stimulus_file(str(root), str(source), texture=False)
    assert resolve_stimulus_file(str(root), str(source), texture=False) == first
    assert len(list(root.glob("import-*"))) == 1
    source.write_bytes(b"changed contents")  # New size and mtime: a new import.
    changed = resolve_stimulus_file(str(root), str(source), texture=False)
    assert changed.path != first.path and len(list(root.glob("import-*"))) == 2
    assert (root / changed.path).read_bytes() == b"changed contents"
    (root / changed.path).unlink()  # A vanished copy is imported again.
    assert (
        root / resolve_stimulus_file(str(root), str(source), texture=False).path
    ).is_file()

    calls = []
    real = stimulus_asset_paths.resolve_stimulus_file
    monkeypatch.setattr(
        stimulus_asset_paths,
        "resolve_stimulus_file",
        lambda *args, **kwargs: calls.append(args) or real(*args, **kwargs),
    )
    resolver = AssetPathResolver()
    once = resolver.resolve(str(root), str(source), texture=False, grating=False)
    assert (
        resolver.resolve(str(root), str(source), texture=False, grating=False) == once
    )
    assert len(calls) == 1
    source.write_bytes(b"third")
    resolver.resolve(str(root), str(source), texture=False, grating=False)
    assert len(calls) == 2


def test_variation_folder_reload_reuses_imported_copies(app, tmp_path):
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.variation_assets import VariationAssets

    root = tmp_path / "assets"
    root.mkdir()
    subset = tmp_path / "external"
    subset.mkdir()
    for index in range(5):
        (subset / f"{index}.png").write_bytes(b"image %d" % index)
    picker = VariationAssets()
    picker.editor.setText(str(subset))
    first = picker.load(blank_program(), str(root), ("image",))
    imports = sorted(p.name for p in root.glob("import-*"))
    assert len(imports) == 5
    # Another media kind misses the loaded key but must not copy the files again.
    second = picker.load(blank_program(), str(root), ("texture",))
    assert [a.logical_path for a in second] == [a.logical_path for a in first]
    assert sorted(p.name for p in root.glob("import-*")) == imports
    picker.deleteLater()


def test_preview_media_cache_is_bounded_by_memory_not_entry_count(
    app, tmp_path, monkeypatch
):
    from PyQt6.QtGui import QImage

    from cephvr.gui import trial_preview_media
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.trial_preview_media import PreviewMedia

    program = add_stimulus(blank_program(), 0, "Image", ("Left",))
    template = program.assets[0]
    count = 40  # More than the former 16-entry cap, as in a long sparse-noise trial.
    assets = []
    for index in range(count):
        name = f"p{index}.png"
        image = QImage(8, 8, QImage.Format.Format_RGB32)
        image.fill(index)
        assert image.save(str(tmp_path / name))
        assets.append(
            template.model_copy(update={"asset_id": f"a{index}", "logical_path": name})
        )
    media = PreviewMedia(
        program.model_copy(update={"assets": tuple(assets)}), str(tmp_path), None
    )
    for asset in assets:
        media.image(asset.asset_id)
    assert len(media.images) == count and media.image_bytes > 0
    size = media.image_bytes // count
    monkeypatch.setattr(trial_preview_media, "IMAGE_CACHE_BYTES", size * 3)
    media.image("a0")  # Cached already; the next miss trims to the budget.
    extra = tmp_path / "extra.png"
    QImage(8, 8, QImage.Format.Format_RGB32).save(str(extra))
    media.assets["extra"] = template.model_copy(
        update={"asset_id": "extra", "logical_path": "extra.png"}
    )
    media.paths["extra"] = "extra.png"
    media.image("extra")
    assert len(media.images) <= 3 and media.image_bytes <= size * 3
    assert set(media.image_sizes) == set(media.images)
    media.close()
    assert media.image_bytes == 0


def test_readable_error_strips_pydantic_boilerplate():
    from cephvr.gui.notices import readable_error
    from cephvr.visual_stimulus.config.models.sparse_noise import (
        SparseNoisePatternRecipe,
    )

    with pytest.raises(ValueError) as caught:
        SparseNoisePatternRecipe.model_validate_json('{"kind": "sparse_noise"}')
    text = readable_error(caught.value)
    assert text and "errors.pydantic.dev" not in text and "input_value" not in text
    assert "validation error" not in text
    assert readable_error(ValueError("plain")) == "plain"


def _wait(predicate, seconds=10):
    import time

    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    return predicate()


def _sparse_layer():
    from cephvr.gui.epoch_composer import EpochComposer

    composer = EpochComposer()
    composer.set_screens(("Front",))
    composer.change_type("Front", "Sparse noise")
    return composer, composer.rows["Front"].parameters.sparse_layer


def test_sparse_layer_labels_and_invalid_input_does_not_commit(app):
    from PyQt6.QtWidgets import QLabel

    composer, layer = _sparse_layer()
    labels = [w.text() for w in layer.form.findChildren(QLabel)]
    assert "Seconds" not in labels and "Patterns" in labels
    assert "Min active cell distance (mm)" in labels
    assert "Background (linear)" in labels
    assert (
        not hasattr(layer, "configure") and "Apply sparse" not in layer.summary.text()
    )
    parameters = composer.rows["Front"].parameters
    before = composer.program
    layer.form.children_by_key["pattern_count"].control.setText("0")
    layer.mark_changed()
    assert layer.error.text() and "errors.pydantic.dev" not in layer.error.text()
    assert not parameters.apply() and composer.program == before
    layer.form.children_by_key["pattern_count"].control.setText("5")
    layer.mark_changed()
    assert not layer.error.text() and parameters.apply()
    assert composer.program.sequence[0].settings[-1].pattern_count == 5
    composer.close()


def test_sparse_layer_new_seed_changes_the_seed_and_marks_the_editor_dirty(app):
    composer, layer = _sparse_layer()
    parameters = composer.rows["Front"].parameters
    before = layer.form.children_by_key["seed"].control.text()
    parameters.dirty = False
    layer.new_seed.click()
    assert layer.form.children_by_key["seed"].control.text() != before
    assert parameters.dirty
    composer.close()


def test_trial_preview_generates_sparse_noise_without_files(window, app):
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus

    program = add_stimulus(blank_program(), 0, "Sparse noise", ("Left",))
    assert not program.assets
    window.page_buttons[1].click()
    editor = window.protocol.editor
    editor.timeline.set_screens(("Left", "Right"))
    editor.set_program(program)
    window.open_trial_preview()
    preview = window.trial_preview
    assert preview is not None
    canvas = preview.canvases["Left"]
    canvas.local_ns = 0
    first = canvas.frame_image()
    canvas.local_ns = 150_000_000
    second = canvas.frame_image()
    media = preview.media
    assert media.sparse_images and not media.images and not media.errors
    assert first != second  # Different indexed patterns.
    canvas.local_ns = 0
    assert canvas.frame_image() == first  # Deterministic.
    preview.close()
