"""Inline sparse-noise parameters and cancellable preparation for one epoch layer."""

import json
from collections.abc import Callable
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from cephvr.gui.components import button, label
from cephvr.gui.program_editing import (
    NodePath,
    data_node,
    drop_unused_assets,
    node_at,
    validate,
)
from cephvr.gui.stimulus_form import ValueEditor
from cephvr.visual_stimulus.config.models.display_profile import Geometry
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoisePatternRecipe
from cephvr.visual_stimulus.configuration import load_file_policies
from cephvr.visual_stimulus.resources.sparse_noise import (
    WORKING_BYTES_PER_CELL,
    prepare_sparse_noise,
)


def install_sequence(
    program: Program,
    path: NodePath,
    layer: int,
    prepared: dict[str, Any],
    recipe: SparseNoisePatternRecipe,
) -> Program:
    """Replace one row atomically without changing other layers or their epoch clock."""
    data = program.model_dump(mode="json")
    target = data_node(data, path)["settings"][layer]
    old_assets = {str(target["asset_id"]), *target["sparse_noise"]["asset_ids"]}
    prefix = "sparse_" + uuid4().hex
    identities = {
        a["asset_id"]: f"{prefix}_{i}" for i, a in enumerate(prepared["assets"])
    }
    data["assets"].extend(
        dict(a, asset_id=identities[a["asset_id"]]) for a in prepared["assets"]
    )
    frames = [identities[e["settings"][0]["asset_id"]] for e in prepared["sequence"]]
    replacement = prepared["sequence"][0]["settings"][0]
    replacement = dict(
        replacement,
        instance_id=target["instance_id"],
        asset_id=frames[0],
        opacity=target["opacity"],
        space=target["space"],
        sparse_noise=dict(
            asset_ids=frames,
            pattern_duration=recipe.pattern_duration.model_dump(mode="json"),
            appearance={
                key: value
                for key, value in recipe.model_dump(mode="json").items()
                if key not in {"surfaces", "pattern_count", "pattern_duration"}
            },
            background_linear_rgb=[recipe.background_linear] * 3,
        ),
    )
    data_node(data, path)["settings"][layer] = replacement
    drop_unused_assets(data, old_assets)
    return validate(data)


def _prepare(
    recipe: SparseNoisePatternRecipe,
    root: Path,
    geometry: Geometry,
    cancelled: Event,
    results: SimpleQueue[dict[str, Any] | Exception],
) -> None:
    def check() -> None:
        if cancelled.is_set():
            raise ValueError("Sparse-noise preparation cancelled")

    try:
        limits = load_file_policies(Path(__file__).resolve().parents[3]).limits
        destination = root / "sparse-noise" / uuid4().hex
        path = prepare_sparse_noise(
            recipe,
            geometry,
            destination,
            max_cells=limits.max_asset_cpu_bytes // WORKING_BYTES_PER_CELL,
            max_patterns=limits.max_expanded_epochs,
            max_document_bytes=limits.max_document_bytes,
            layer_sequence=True,
            check=check,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        prefix = destination.relative_to(root).as_posix()
        for asset in data["assets"]:
            asset["logical_path"] = f"{prefix}/{asset['logical_path']}"
        check()
        results.put(data)
    except Exception as error:
        results.put(error)


class SparseNoiseLayer(QWidget):
    committed = pyqtSignal(object)
    edited = pyqtSignal()

    def __init__(
        self,
        program: Program,
        path: NodePath,
        layer: int,
        root: str,
        face: str,
        geometry: Callable[[], Geometry] | None,
        available: Callable[[], bool],
    ) -> None:
        super().__init__()
        self.program, self.path, self.layer = program, path, layer
        self.root, self.face, self.scene_geometry = root, face, geometry
        self.available = available
        self.cancelled = Event()
        self.results: SimpleQueue[dict[str, Any] | Exception] = SimpleQueue()
        self.recipe: SparseNoisePatternRecipe | None = None
        self.dirty = False
        self.running = False
        node = node_at(program, path)
        assert isinstance(node, Epoch)
        setting = node.settings[layer]
        assert setting.kind == "image" and setting.sparse_noise is not None
        sequence = setting.sparse_noise
        appearance = (
            sequence.appearance.model_dump(mode="json")
            if sequence.appearance
            else dict(
                format_version=2,
                kind="sparse_noise",
                seed=0,
                square_size_mm=5.0,
                min_active_cell_distance_mm=0.0,
                active_probability=0.2,
                background_linear=0.5,
            )
        )
        schema = SparseNoisePatternRecipe.model_json_schema()
        values = dict(
            appearance,
            pattern_count=len(sequence.asset_ids) if sequence.appearance else 600,
            pattern_duration=sequence.pattern_duration.model_dump(mode="json"),
        )
        keys = (
            "square_size_mm",
            "min_active_cell_distance_mm",
            "active_probability",
            "background_linear",
            "seed",
            "pattern_count",
            "pattern_duration",
        )
        self.form = ValueEditor(
            {
                "type": "object",
                "properties": {key: schema["properties"][key] for key in keys},
            },
            {key: values[key] for key in keys},
            schema.get("$defs", {}),
        )
        self.form.changed.connect(self.mark_changed)
        self.configure = button("Apply sparse noise")
        self.configure.clicked.connect(self.start)
        self.error = label("", wrap=True)
        self.summary = label("Final pattern is held until the epoch ends.", wrap=True)
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.form)
        body.addWidget(self.configure)
        body.addWidget(self.summary)
        body.addWidget(self.error)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)

    def mark_changed(self) -> None:
        self.dirty = True
        self.edited.emit()

    def start(self) -> None:
        if self.running or not self.available():
            return
        try:
            root = Path(self.root).resolve()
            if not self.root or not root.is_dir() or self.scene_geometry is None:
                raise ValueError("Choose Assets and configure projector geometry first")
            values = self.form.read()
            self.recipe = SparseNoisePatternRecipe.model_validate_json(
                json.dumps(
                    dict(
                        values,
                        format_version=2,
                        kind="sparse_noise",
                        surfaces=[self.face.lower()],
                    )
                )
            )
            self.geometry_snapshot = self.scene_geometry()
            self.cancelled = Event()
            self.results = SimpleQueue()
            self.running = True
            self.configure.setEnabled(False)
            for control in self.form.children_by_key.values():
                control.setEnabled(False)
            self.error.setText("Preparing patterns…")
            Thread(
                target=_prepare,
                args=(
                    self.recipe,
                    root,
                    self.geometry_snapshot,
                    self.cancelled,
                    self.results,
                ),
                daemon=True,
                name="sparse-noise-layer",
            ).start()
            self.timer.start()
        except (OSError, ValueError) as error:
            self.error.setText(str(error))

    def poll(self) -> None:
        try:
            available = (
                self.available()
                and self.scene_geometry is not None
                and self.scene_geometry() == self.geometry_snapshot
            )
        except (OSError, ValueError):
            available = False
        if not available:
            self.close_dialog()
            return
        try:
            result = self.results.get_nowait()
        except Empty:
            return
        self.timer.stop()
        self.running = False
        self.configure.setEnabled(True)
        for control in self.form.children_by_key.values():
            control.setEnabled(True)
        if isinstance(result, Exception):
            self.error.setText(str(result))
            return
        try:
            assert self.recipe is not None
            program = install_sequence(
                self.program, self.path, self.layer, result, self.recipe
            )
            self.dirty = False
            self.committed.emit(program)
        except (OSError, ValueError) as error:
            self.error.setText(str(error))

    def close_dialog(self) -> None:
        self.cancelled.set()
        self.timer.stop()
        if self.running:
            self.running = False
            self.dirty = True
            self.configure.setEnabled(True)
            for control in self.form.children_by_key.values():
                control.setEnabled(True)
            self.error.setText("Preparation cancelled; apply the parameters again.")
