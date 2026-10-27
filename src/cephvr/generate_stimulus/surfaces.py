"""Arena surface list and the form that edits every selected surface together."""

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout

from .documents import apply_changes
from .fields import SURFACE_NAMES, humanize
from .models import ArenaDesign, Surface
from .properties import property_form

KEY = Qt.ItemDataRole.UserRole


def surface_name(name: str) -> str:
    return SURFACE_NAMES.get(name, humanize(name))


class SurfaceEditor:
    """Owns the list widget and rebuilds its form on selection; selection persists."""

    def __init__(
        self,
        surfaces: dict[str, Any],
        root: Path,
        selected: list[str],
        changed: Callable[[], None],
        rebuilt: Callable[[], None],
    ) -> None:
        self.surfaces, self.root = surfaces, root
        self.selected = selected
        self.changed, self.rebuilt = changed, rebuilt
        self.list = QListWidget()
        self.list.setProperty("role", "surfaces")
        self.list.setAccessibleName("Surfaces")
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for name in surfaces:
            item = QListWidgetItem(surface_name(name))
            item.setData(KEY, name)
            self.list.addItem(item)
        self.list.setFixedHeight(self.list.sizeHintForRow(0) * self.list.count() + 12)
        rows = [r for r in range(self.list.count()) if self.key(r) in selected] or [0]
        for row in rows:
            self.item(row).setSelected(True)
        self.list.setCurrentRow(rows[0], QItemSelectionModel.SelectionFlag.NoUpdate)
        self.form = QVBoxLayout()
        self.list.itemSelectionChanged.connect(self.refresh)
        self.refresh()

    def item(self, row: int) -> QListWidgetItem:
        item = self.list.item(row)
        assert item is not None
        return item

    def key(self, row: int) -> str:
        return str(self.item(row).data(KEY))

    def select(self, name: str) -> None:
        self.list.setCurrentRow(list(self.surfaces).index(name))

    def refresh(self) -> None:
        while self.form.count():
            item = self.form.takeAt(0)
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        selected = [str(item.data(KEY)) for item in self.list.selectedItems()]
        if not selected:
            return
        self.selected[:] = selected
        data = copy.deepcopy(self.surfaces[selected[0]])
        previous = copy.deepcopy(data)

        def edited() -> None:
            nonlocal previous
            for name in selected:
                apply_changes(self.surfaces[name], previous, data)
            previous = copy.deepcopy(data)
            self.changed()

        self.form.addWidget(
            property_form(
                data,
                edited,
                self.refresh,
                title=" / ".join(surface_name(n) for n in selected),
                directory=self.root,
                schema=Surface,
                path=f"surfaces.{selected[0]}",
            )
        )
        self.rebuilt()


def arena_panel(
    layout: QVBoxLayout,
    design: dict[str, Any],
    root: Path,
    selected: list[str],
    changed: Callable[[], None],
    rebuild: Callable[[], None],
    rebuilt: Callable[[], None],
) -> SurfaceEditor:
    """Add the geometry form and surface editor for `design` to `layout`."""
    geometry = {k: v for k, v in design.items() if k != "surfaces"}

    def geometry_changed() -> None:
        design.update(geometry)
        changed()

    layout.addWidget(
        property_form(
            geometry, geometry_changed, rebuild, title="Geometry", schema=ArenaDesign
        )
    )
    editor = SurfaceEditor(design["surfaces"], root, selected, changed, rebuilt)
    layout.addWidget(editor.list)
    layout.addLayout(editor.form)
    return editor
