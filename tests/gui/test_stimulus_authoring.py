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


@pytest.mark.parametrize("angle", range(0, 360, 45))
def test_linked_grating_preview_shares_full_screen_local_pattern(app, angle):
    import json
    from math import cos, radians, sin

    import numpy as np

    from cephvr.gui.projector_geometry import RigDimensions
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.rig_parameter_edits import patch_setting
    from cephvr.gui.stimulus_asset_paths import apply_link
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.trial_preview_canvas import PreviewCanvas
    from cephvr.gui.trial_preview_media import PreviewMedia
    from cephvr.gui.trial_preview_plan import PreviewPlan
    from cephvr.gui.trial_preview_surfaces import PreviewGeometry
    from cephvr.visual_stimulus.config.models.program_model import Program

    program = blank_program()
    faces = ("Bottom", "Front", "Left", "Right")
    for face in faces:
        program = add_stimulus(program, 0, "Grating", (face,))
    data = program.model_dump(mode="json")
    settings = data["sequence"][0]["settings"]
    patch_setting(settings[0], {"Orientation": str(angle), "Speed": "20"})
    settings[0]["pattern"]["frequency"]["value"] = 0.2
    settings[0]["pattern"]["feature_sharpness"] = 0.0
    for target in settings[1:]:
        apply_link(target, settings[0]["instance_id"])
    program = Program.model_validate_json(json.dumps(data))
    rig = RigDimensions(300, 400, 250, (150, 200, 100))
    preview_geometry = PreviewGeometry.from_drafts(
        rig,
        {
            face: dict(width="200", height="150", subject_distance="100")
            for face in faces
        },
    )
    geometry = preview_geometry.artifact().display.geometry
    plan = PreviewPlan(program, geometry)
    before = plan.seek(0)
    seconds = 0.025
    after = plan.seek(round(seconds * 1e9))
    c, s = cos(radians(angle)), sin(radians(angle))
    vx, vy = -20 * s, -20 * c

    def phase(values, x, y):
        r = radians(values["rotation"])
        return values["frequency"] * (x * cos(r) + y * sin(r)) + values["phase_x"]

    for initial, moved in zip(before, after, strict=True):
        values = moved.values
        r = radians(values["rotation"])
        assert values["frequency"] == pytest.approx(0.2)
        assert (cos(r), sin(r)) == pytest.approx((-s, -c), abs=1e-10)
        assert not any(key.startswith("grating_") for key in values)
        # Equal local coordinates see equal phase, across the whole infinite field.
        for x, y in ((0, 0), (-100, -75), (100, 75), (700, -900)):
            assert phase(values, x, y) == pytest.approx(
                phase(after[0].values, x, y), abs=1e-10
            )
            assert phase(values, x + vx * seconds, y + vy * seconds) == pytest.approx(
                phase(initial.values, x, y), abs=1e-10
            )
    assert plan.seek(0) == before
    media = PreviewMedia(program, "", None)

    def frame(canvas, now_ns):
        canvas.present(plan.seek(now_ns), now_ns, (0, 0, 0))
        return canvas.frame_image()

    def pixels(image):
        return np.frombuffer(
            image.constBits().asstring(image.sizeInBytes()), dtype=np.uint8
        ).astype(int)

    for face in faces:
        canvas = PreviewCanvas(face, media, preview_geometry)
        # 50 seconds moves 200 full periods: pixels must retain scale and phase.
        initial_frame = frame(canvas, 0)
        assert frame(canvas, 62_500_000) != initial_frame
        # Allow one 8-bit quantization level for transported floating-point phase.
        assert (
            np.max(abs(pixels(frame(canvas, 50_000_000_000)) - pixels(initial_frame)))
            <= 1
        )
        assert frame(canvas, 0) == initial_frame
        canvas.deleteLater()
    media.close()


def test_random_linked_gratings_share_all_eight_local_directions(app):
    import json
    from math import cos, radians, sin

    from tests.visual_stimulus.support import _linked_texture_fixture

    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.rig_parameter_edits import patch_setting
    from cephvr.gui.stimulus_asset_paths import apply_link
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.trial_preview_plan import PreviewPlan
    from cephvr.visual_stimulus.config.models.program_model import Program

    program = blank_program()
    for face in ("Bottom", "Front", "Left", "Right"):
        program = add_stimulus(program, 0, "Grating", (face,))
    data = grouped_program(program).model_dump(mode="json")
    group = data["sequence"][0]
    group["repetitions"] = 100
    epoch = group["body"][0]
    source = epoch["settings"][0]
    patch_setting(source, {"Orientation": "0", "Speed": "20"})
    source["pattern"]["frequency"]["value"] = 0.2
    for target in epoch["settings"][1:]:
        apply_link(target, source["instance_id"])
    epoch["repetition_rules"] = [
        dict(
            kind="uniform_grid_v1",
            instance_id=source["instance_id"],
            parameter="Orientation",
            minimum="0",
            maximum="315",
            precision="45",
            seed="1" * 32,
            stream="0",
            offset=0,
            stride=1,
            rig_coordinates=True,
            rig_angle_version=2,
        )
    ]
    geometry, _ = _linked_texture_fixture()
    plan = PreviewPlan(Program.model_validate_json(json.dumps(data)), geometry)
    sampled = set()
    for start in plan.starts:
        before = plan.seek(start)
        after = plan.seek(start + 25_000_000)
        rotation = before[0].values["rotation"]
        sampled.add(round((-90 - rotation) % 360) % 360)
        for initial, moved in zip(before, after, strict=True):
            a = radians(initial.values["rotation"])
            assert (cos(a), sin(a)) == pytest.approx(
                (cos(radians(rotation)), sin(radians(rotation))), abs=1e-10
            )
            assert initial.values["frequency"] == pytest.approx(0.2)
            assert initial.values["phase_x"] == pytest.approx(
                before[0].values["phase_x"]
            )
            assert moved.values["phase_x"] - initial.values["phase_x"] == pytest.approx(
                -0.1, abs=1e-9
            )
    assert sampled == set(range(0, 360, 45))


def test_grating_preview_fills_entire_image(app):
    from cephvr.gui.grating_image import grating_image
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus

    setting = (
        add_stimulus(blank_program(), 0, "Grating", ("Bottom",)).sequence[0].settings[0]
    )
    values = dict(width=200.0, height=150.0, frequency=0.2, phase_x=0.137)
    image = grating_image(setting, values)
    for x, y in ((0, 0), (511, 0), (0, 3), (511, 3), (256, 2)):
        assert image.pixelColor(x, y).alpha() == 255


def test_tank_preview_preserves_measured_field_pixel_pitch(app):
    from math import dist

    from cephvr.gui.projector_geometry import RigDimensions
    from cephvr.gui.trial_preview_rig import PreviewRig
    from cephvr.gui.trial_preview_surfaces import PreviewGeometry

    faces = ("Front", "Left", "Right", "Bottom")
    geometry = PreviewGeometry.from_drafts(
        RigDimensions(300, 400, 250, (150, 200, 100)),
        {
            face: dict(
                width="200",
                height="150",
                subject_distance="100",
                reference_width_px="100",
                reference_height_px="100",
                reference_x_px="20",
                reference_y_px="20",
                reference_x_mm="20",
                reference_y_mm="20",
                valid_width_px="80",
                valid_height_px="60",
            )
            for face in faces
        },
        {face: (100, 100) for face in faces},
    )
    view = PreviewRig(geometry, {})
    for face, corners in view.screen_planes().items():
        surface = geometry.surfaces[face]
        assert dist(corners[0], corners[1]) == pytest.approx(surface.width)
        assert dist(corners[0], corners[3]) == pytest.approx(surface.height)
    view.deleteLater()


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


@pytest.mark.parametrize("width", [600, 800, 1100, 1600, 2400])
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
    source = row.parameters.motion_source
    assert source is not None

    def position(control):
        return row.grid.getItemPosition(row.grid.indexOf(control))

    assert position(source)[0] == position(row.stimulus)[0]
    assert position(source)[1] > position(row.stimulus)[1]
    assert position(appearance.color_b)[0] == position(appearance.color_a)[0] + 2
    assert position(appearance.color_a)[1:] == position(appearance.color_b)[1:]
    for a, b in zip(appearance.color_a.edits, appearance.color_b.edits, strict=True):
        assert (
            a.mapTo(row, a.rect().topLeft()).x() == b.mapTo(row, b.rect().topLeft()).x()
        )
    source.setCurrentText("Linked")
    app.processEvents()
    assert position(source)[0] == position(row.stimulus)[0]
    assert appearance.color_a.isHidden() and appearance.color_b.isHidden()
    assert row.parameters.linked_to.isVisibleTo(row)
    source.setCurrentText("Self")
    app.processEvents()
    assert appearance.color_a.isVisibleTo(row) and appearance.color_b.isVisibleTo(row)
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
        for title, control in sorted(
            row.columns,
            key=lambda column: (
                row.grid.getItemPosition(row.grid.indexOf(column[1]))[:2]
                if row.grid.indexOf(column[1]) >= 0
                else (-1, -1)
            ),
        )
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


def test_asset_selection_references_existing_files_without_copying(
    tmp_path, monkeypatch
):
    from cephvr.gui import stimulus_asset_paths
    from cephvr.gui.stimulus_asset_paths import AssetPathResolver
    from cephvr.gui.stimulus_files import resolve_stimulus_file

    root = tmp_path / "assets"
    root.mkdir()
    source = tmp_path / "external.png"
    source.write_bytes(b"one")
    for name in ("external.png", "external.mp4", "external.glb", "external.json"):
        outside = tmp_path / name
        if outside != source:
            outside.write_bytes(b"external")
        with pytest.raises(ValueError, match="inside Protocol Assets"):
            resolve_stimulus_file(
                str(root), str(outside), texture=name.endswith(".json")
            )
    assert list(root.iterdir()) == []
    assert source.read_bytes() == b"one"
    # One common root supports different experimenters without source copies.
    root = tmp_path
    first = resolve_stimulus_file(str(root), str(source), texture=False)
    assert first.path == "external.png"
    assert resolve_stimulus_file(str(root), str(source), texture=False) == first
    assert not list(root.glob("import-*"))

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
    previous = root / "import-existing" / "saved.png"
    previous.parent.mkdir()
    previous.write_bytes(b"saved")
    assert resolve_stimulus_file(str(root), str(previous), texture=False).path == (
        "import-existing/saved.png"
    )
    assert previous.read_bytes() == b"saved"


def test_variation_folder_references_in_root_files_without_copying(app, tmp_path):
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
    with pytest.raises(ValueError, match="inside Protocol Assets"):
        picker.load(blank_program(), str(root), ("image",))
    assert list(root.iterdir()) == []
    assert not picker.loaded and picker.loaded_key is None
    root = tmp_path
    first = picker.load(blank_program(), str(root), ("image",))
    assert [a.logical_path for a in first] == [f"external/{i}.png" for i in range(5)]
    # Another media kind retains the same file references.
    second = picker.load(blank_program(), str(root), ("texture",))
    assert [a.logical_path for a in second] == [a.logical_path for a in first]
    assert not list(root.glob("import-*"))
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


@pytest.mark.parametrize("previous", [None, "Image"])
@pytest.mark.parametrize(
    "preset,kind",
    [("Sparse noise", "sparse_noise"), ("Grating", "texture"), ("Uniform", "texture")],
)
def test_generated_stimulus_epoch_commits_without_an_asset(app, previous, preset, kind):
    from cephvr.gui.epoch_composer import EpochComposer

    composer = EpochComposer()
    composer.set_screens(("Front", "Left"))
    for face in ("Front", "Left"):
        if previous:
            composer.rows[face].stimulus.setCurrentText(previous)
        composer.rows[face].stimulus.setCurrentText(preset)
    program = composer.value()
    assert not program.assets and not composer.pending_assets
    assert len(program.sequence[0].settings) == 2
    assert all(s.kind == kind for s in program.sequence[0].settings)
    if preset == "Grating":
        assert all(s.grating for s in program.sequence[0].settings)
    composer.rows["Left"].stimulus.setCurrentText("Image")
    with pytest.raises(ValueError, match="Choose an asset"):
        composer.value()
    composer.close()


def test_sparse_layer_labels_and_invalid_input_does_not_commit(app):
    from PyQt6.QtWidgets import QLabel

    composer, layer = _sparse_layer()
    labels = [w.text() for w in layer.form.findChildren(QLabel)]
    assert "Seconds" not in labels and "Patterns" not in labels
    assert "pattern_duration" not in layer.form.children_by_key
    assert "Min active cell distance (mm)" in labels
    assert "Background (linear)" in labels
    assert (
        not hasattr(layer, "configure") and "Apply sparse" not in layer.summary.text()
    )
    parameters = composer.rows["Front"].parameters
    before = composer.program
    layer.form.children_by_key["square_size_mm"].control.setText("0")
    layer.mark_changed()
    assert layer.error.text() and "errors.pydantic.dev" not in layer.error.text()
    assert not parameters.apply() and composer.program == before
    layer.form.children_by_key["square_size_mm"].control.setText("5")
    layer.mark_changed()
    assert not layer.error.text() and parameters.apply()
    assert composer.program.sequence[0].settings[-1].appearance.square_size_mm == 5
    assert composer.program.sequence[0].settings[-1].pattern_count == 1
    assert composer.program.sequence[0].settings[-1].pattern_duration is None
    composer.close()


def test_sparse_epoch_edit_replaces_hidden_legacy_pattern_timing(app):
    from cephvr.visual_stimulus.config.models.program_model import Time

    composer, _ = _sparse_layer()
    epoch = composer.program.sequence[0]
    legacy = epoch.settings[-1].model_copy(
        update={"pattern_count": 600, "pattern_duration": Time(seconds="0.1")}
    )
    composer.program = composer.program.model_copy(
        update={
            "sequence": (
                epoch.model_copy(update={"settings": (*epoch.settings[:-1], legacy)}),
            )
        }
    )
    composer.refresh_rows()
    result = composer.reference_value().sequence[0].settings[-1]
    assert result.pattern_count == 1 and result.pattern_duration is None
    composer.close()


@pytest.mark.parametrize("width", [600, 1000])
def test_sparse_layer_new_seed_changes_the_seed_and_marks_the_editor_dirty(app, width):
    composer, layer = _sparse_layer()
    row = composer.rows["Front"]
    row.setFixedWidth(width)
    composer.show()
    app.processEvents()
    seed_cell = dict(row.columns)["Seed"]
    assert seed_cell.y() == row.stimulus.y()
    assert seed_cell.x() >= row.stimulus.geometry().right()
    assert seed_cell.geometry().right() < row.actions_button.x()
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
    assert first == second  # One pattern is held for the full epoch.
    canvas.local_ns = 0
    assert canvas.frame_image() == first  # Deterministic.
    preview.close()


@pytest.mark.parametrize("repetitions", [3, 100, 101, 4000])
def test_sparse_repeated_epoch_preview_uses_distinct_reproducible_patterns(
    app, repetitions
):
    from cephvr.gui.preview_motion_data import motion_epochs
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.trial_preview_plan import PreviewPlan
    from cephvr.visual_stimulus.config.models.program_model import Group
    from cephvr.visual_stimulus.resources.sparse_noise import (
        grid_for_extent,
        pattern_rgba,
    )
    from cephvr.visual_stimulus.resources.sparse_noise_stream import layer_recipe

    program = add_stimulus(blank_program(), 0, "Sparse noise", ("Front",))
    group = Group(
        kind="group",
        group_id="repeated",
        repetitions=repetitions,
        order="as_listed",
        order_unit="child_blocks",
        conditions=None,
        body=program.sequence,
    )
    program = program.model_copy(update={"sequence": (group,)})
    epochs = motion_epochs(program, "0")
    count = min(repetitions, 100)
    assert len(epochs) == count
    plan = PreviewPlan(program)
    assert len(plan.epochs) == count
    assert [epoch.settings for epoch in plan.epochs] == [
        epoch.settings for epoch in epochs
    ]
    assert plan.total_ns == epochs[-1].end_ns
    assert program.sequence[0].repetitions == repetitions
    patterns = []
    for epoch in epochs:
        setting = epoch.settings[0]
        recipe = layer_recipe(setting)
        grid = grid_for_extent(recipe, "front", 100, 100, max_cells=10000)
        patterns.append(pattern_rgba(recipe, grid, setting.pattern_at(59_999_999_999)))
    assert len(set(patterns)) == count
    assert epochs == motion_epochs(program, "0")


def test_looming_duration_follows_epoch_edits_and_has_no_growth_control(app):
    from PyQt6.QtWidgets import QLabel

    from cephvr.gui.epoch_batch import apply_batch
    from cephvr.gui.epoch_composer import EpochComposer
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.protocol_nodes import edit_epoch_metadata
    from cephvr.gui.stimulus_presets import add_stimulus

    program = add_stimulus(blank_program(), 0, "Looming image", ("Front",))
    program = edit_epoch_metadata(program, 0, "loom", "72.125")
    assert program.sequence[0].settings[0].width.knots[-1].time.seconds == "72.125"
    program = apply_batch(program, ((0,),), None, {"Duration": "80"})
    assert program.sequence[0].settings[0].width.knots[-1].time.ns() == 80_000_000_000
    composer = EpochComposer()
    composer.set_screens(("Front",))
    composer.program = program
    composer.refresh_rows()
    composer.duration.setText("00:00:07.500")
    composer.update_duration()
    assert (
        composer.program.sequence[0].settings[0].width.knots[-1].time.ns()
        == 7_500_000_000
    )
    captions = [label.text() for label in composer.rows["Front"].findChildren(QLabel)]
    assert "Growth (s)" not in captions
    composer.close()


@pytest.mark.parametrize("preset", ["Sparse noise", "Grating"])
def test_epoch_type_change_prunes_only_assets_no_other_epoch_needs(window, preset):
    from copy import deepcopy

    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_batches import grouped_program
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_presets import add_stimulus

    data = add_stimulus(blank_program(), 0, "Image", ("Front",)).model_dump(mode="json")
    second = deepcopy(data["sequence"][0])
    second["epoch_id"] = "second"
    data["sequence"].append(second)
    original = grouped_program(validate(data))
    editor = window.protocol.editor
    editor.timeline.set_screens(("Front",))
    editor.set_program(original)
    editor.enter_group()
    for index in range(2):
        editor.select_epochs(((0, index),))
        form = editor.subgroup
        form.composer.rows["Front"].stimulus.setCurrentText(preset)
        form.apply()
        assert not form.notice.text()
        assert editor.program.assets == (original.assets if index == 0 else ())
    assert all(
        s.kind != "image" for e in editor.program.sequence[0].body for s in e.settings
    )


def test_stimulus_memory_is_shared_and_sparse_switch_clears_filename(app, tmp_path):
    from PyQt6.QtGui import QImage

    from cephvr.gui.epoch_composer import EpochComposer

    composer = EpochComposer()
    composer.set_screens(("Front", "Left"))
    composer.set_asset_root(str(tmp_path))
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(0)
    path = tmp_path / "image.png"
    assert image.save(str(path))
    composer.change_type("Front", "Image")
    parameters = composer.rows["Front"].parameters
    parameters.set_media_path(next(iter(parameters.asset_forms)), str(path))
    assert composer.program.assets
    composer.change_type("Front", "Sparse noise")
    parameters = composer.rows["Front"].parameters
    assert not parameters.asset_forms and not composer.program.assets
    seed = parameters.sparse_layer.form.children_by_key["seed"].control
    seed.setText("123")
    parameters.sparse_layer.mark_changed()
    assert parameters.apply()
    composer.change_type("Left", "Sparse noise")
    left = composer.rows["Left"].parameters
    assert left.sparse_layer.form.children_by_key["seed"].control.text() == "123"
    left.sparse_layer.form.children_by_key["seed"].control.setText("456")
    left.sparse_layer.mark_changed()
    assert left.apply()
    # Leaving the older Front values must not overwrite the newer Left edit.
    composer.change_type("Front", "Grating")
    composer.change_type("Front", "Sparse noise")
    front = composer.rows["Front"].parameters
    assert front.sparse_layer.form.children_by_key["seed"].control.text() == "456"
    assert not front.asset_forms
    composer.change_type("Front", "Image")
    assert all(
        not edit.text()
        for edit in composer.rows["Front"].parameters.asset_forms.values()
    )
    with pytest.raises(ValueError, match="Choose an asset"):
        composer.value()
    composer.close()


@pytest.mark.parametrize(
    "preset,field,value",
    [
        (
            "Sparse noise",
            "appearance",
            dict(
                format_version=2,
                kind="sparse_noise",
                seed=57,
                square_size_mm=2.0,
                min_active_cell_distance_mm=9.0,
                active_probability=0.3,
                background_linear=0.4,
            ),
        ),
        ("Grating", "mean_linear_rgb", [0.2, 0.3, 0.4]),
        ("Uniform", "mean_linear_rgb", [0.4, 0.5, 0.6]),
        ("Image", "fit", "source"),
        ("Video", "initial_playback", {"seconds": "3.5"}),
        ("Texture drift", "initial_phase_x_cycles", 0.25),
        ("3D arena", "initial", {"position_mm": [12.0, 13.0], "yaw_deg": 17.0}),
    ],
)
def test_stimulus_memory_restores_only_matching_type_parameters(preset, field, value):
    from cephvr.gui.program_editing import validate
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_memory import StimulusMemory
    from cephvr.gui.stimulus_presets import add_stimulus
    from cephvr.gui.stimulus_scope import surfaces

    source = add_stimulus(blank_program(), 0, preset, ("Front",))
    data = source.model_dump(mode="json")
    data["sequence"][0]["settings"][0][field] = value
    source = validate(data)
    memory = StimulusMemory()
    memory.remember(source.sequence[0].settings[0], 60_000_000_000)
    memory.entries = memory.validate(memory.entries)
    target = add_stimulus(blank_program(), 0, "Uniform", ("Left",))
    target = add_stimulus(target, 0, preset, ("Left",))
    result = memory.apply(
        target, 1, preset, "" if preset == "3D arena" else "Left", 60_000_000_000
    )
    setting = result.sequence[0].settings[1]
    assert setting.model_dump(mode="json")[field] == value
    assert setting.instance_id == target.sequence[0].settings[1].instance_id
    assert result.assets == target.assets
    assert result.sequence[0].settings[0] == target.sequence[0].settings[0]
    if preset != "3D arena":
        assert surfaces(setting.model_dump(mode="json")) == ["left"]


def test_stimulus_memory_round_trips_through_runtime_gui_history(window, tmp_path):
    import json

    from cephvr.gui.gui_history import GuiHistory
    from cephvr.gui.protocol_document import blank_program
    from cephvr.gui.stimulus_memory import StimulusMemory
    from cephvr.gui.stimulus_presets import add_stimulus

    composer = window.protocol.editor.subgroup.composer
    setting = (
        add_stimulus(blank_program(), 0, "Sparse noise", ("Front",))
        .sequence[0]
        .settings[0]
    )
    setting = setting.model_copy(
        update={"appearance": setting.appearance.model_copy(update={"seed": 987})}
    )
    composer.stimulus_memory.remember(setting, 60_000_000_000)
    path = tmp_path / "runtime_gui.json"
    GuiHistory(window.snapshots, path).save()
    composer.stimulus_memory = StimulusMemory()
    assert GuiHistory(window.snapshots, path).restore()
    assert (
        composer.stimulus_memory.entries["Sparse noise"]["setting"]["appearance"][
            "seed"
        ]
        == 987
    )
    old = json.loads(path.read_text(encoding="utf-8"))
    old.pop("stimulus_defaults")
    window.snapshots.validate(old)  # Existing saved GUI files remain readable.
    bad = window.snapshots.capture()
    bad["stimulus_defaults"]["Grating"] = bad["stimulus_defaults"].pop("Sparse noise")
    with pytest.raises(ValueError, match="wrong type"):
        window.snapshots.validate(bad)
    assert "Sparse noise" in composer.stimulus_memory.entries
