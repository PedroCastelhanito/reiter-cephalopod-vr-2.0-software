"""Trial-owned movement boundary drafts and the arena Advanced settings form."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QSizePolicy, QVBoxLayout, QWidget

from cephvr.gui.components import combo, equal_row_height, field, label
from cephvr.gui.epoch_batch import epoch_paths
from cephvr.gui.layouts import advanced_grid
from cephvr.gui.program_editing import node_at
from cephvr.visual_stimulus.compiler.arena_regions import geometry_vertices
from cephvr.visual_stimulus.config.models.program_model import (
    ArenaBoundary,
    ArenaFileRegion,
    ArenaSettings,
    ConvexPolygon,
    Epoch,
    Program,
    TrialArenaBoundaries,
    UnrestrictedRegion,
)
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES
from cephvr.visual_stimulus.resources.arena_geometry import read_geometry_preview


def boundary_document(program: Program, raw: str) -> TrialArenaBoundaries:
    document = (
        TrialArenaBoundaries.model_validate_json(raw)
        if raw
        else TrialArenaBoundaries(format_version=1, bindings=())
    )
    known = {binding.instance_id: binding for binding in document.bindings}
    used: dict[str, ArenaBoundary] = {}
    for path in epoch_paths(program):
        epoch = node_at(program, path)
        assert isinstance(epoch, Epoch)
        for setting in epoch.settings:
            if isinstance(setting, ArenaSettings):
                used[setting.instance_id] = known.get(
                    setting.instance_id
                ) or ArenaBoundary(
                    instance_id=setting.instance_id,
                    world_frame_id=setting.world_frame_id,
                    region=ArenaFileRegion(kind="arena_file"),
                )
    return TrialArenaBoundaries(format_version=1, bindings=tuple(used.values()))


def geometry_description(program: Program, setting: ArenaSettings, root: str) -> str:
    try:
        asset = next(a for a in program.assets if a.asset_id == setting.asset_id)
        base = Path(root).resolve()
        path = (base / asset.logical_path).resolve()
        path.relative_to(base)
        if not root:
            raise ValueError("Choose the Assets folder")
        vertices = geometry_vertices(
            read_geometry_preview(path, max_document_bytes=DEFAULT_DOCUMENT_BYTES)
        )
        xs, ys = zip(*vertices, strict=True)
        return f"Arena-file bounds: X {min(xs):g}–{max(xs):g} mm; Y {min(ys):g}–{max(ys):g} mm. Setup applies the asset transform and validates the inset region."
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        return f"Arena-file geometry unavailable: {error}. Setup requires rectangular/convex geometry."


class ArenaLimits(QWidget):
    committed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.binding: ArenaBoundary | None = None
        self.dirty = False
        self.saved_region: ConvexPolygon | None = None
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        grid = advanced_grid()
        body.addLayout(grid)
        self.mode = combo(("From arena file", "Unrestricted", "Saved explicit region"))
        self.mode.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.mode.setMinimumWidth(0)
        self.mode_field = field("Movement limits", self.mode)
        grid.addWidget(self.mode_field, 0, 0)
        self.margin = QLineEdit("30")
        self.margin_field = field("Distance from walls (mm)", self.margin)
        grid.addWidget(self.margin_field, 0, 1)
        equal_row_height(self.mode, self.margin)
        self.note = label(
            "Uses rectangular/convex geometry declared in the arena GLB. Setup validates the region and initial position.",
            wrap=True,
        )
        grid.addWidget(self.note, 1, 0, 1, 2)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.margin.textEdited.connect(self.mark_changed)
        self.margin.editingFinished.connect(self.apply)

    def bind(self, binding: ArenaBoundary, description: str = "") -> None:
        if (
            self.dirty
            and self.binding is not None
            and self.binding.instance_id == binding.instance_id
        ):
            return
        self.note.setText(
            description
            or "Setup validates arena-file geometry and the initial position."
        )
        self.binding = binding
        self.saved_region = (
            binding.region if binding.region.kind == "convex_polygon_xy" else None
        )
        region = binding.region
        self.mode.blockSignals(True)
        self.mode.clear()
        self.mode.addItems(("From arena file", "Unrestricted"))
        if self.saved_region is not None:
            self.mode.addItem("Saved explicit region")
        self.mode.setCurrentIndex(
            0
            if region.kind == "arena_file"
            else 1
            if region.kind == "unrestricted"
            else 2
        )
        self.mode.blockSignals(False)
        self.margin.setText(f"{getattr(region, 'margin_mm', 30):g}")
        self.margin_field.setVisible(region.kind != "unrestricted")
        self.margin.setEnabled(region.kind == "arena_file")
        self.dirty = False

    def mark_changed(self) -> None:
        self.dirty = True
        self.changed.emit()

    def change_mode(self) -> None:
        self.mark_changed()
        self.margin_field.setVisible(self.mode.currentIndex() != 1)
        self.margin.setEnabled(self.mode.currentIndex() == 0)
        self.apply()

    def apply(self) -> bool:
        if not self.dirty or self.binding is None:
            return True
        try:
            index = self.mode.currentIndex()
            region = (
                ArenaFileRegion(kind="arena_file", margin_mm=float(self.margin.text()))
                if index == 0
                else UnrestrictedRegion(kind="unrestricted")
                if index == 1
                else self.saved_region
            )
            if region is None:
                raise ValueError("No saved explicit region is available")
        except (ValueError, TypeError):
            self.margin.setToolTip(
                "Enter a finite nonnegative wall distance; correct the draft before saving"
            )
            return False
        self.binding = self.binding.model_copy(update={"region": region})
        self.dirty = False
        self.committed.emit(self.binding)
        return True
