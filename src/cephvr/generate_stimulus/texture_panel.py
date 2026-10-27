"""Texture workspace controls: the pattern selector and its parameter form."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QWidget

from cephvr.gui.components import Card, SelectionBox, combo, field
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoiseAppearance

from .fields import PATTERN_NAMES, humanize
from .properties import property_form
from .textures import PATTERNS

BARS = {"bars_horizontal", "bars_vertical"}
BAR_HIDDEN = frozenset(
    {"texture_resolution", "tile_width_mm", "line_spacing_mm", "line_width_mm"}
)


def texture_widgets(
    document: dict[str, Any],
    directory: Path,
    changed: Callable[[], None],
    rebuild: Callable[[], None],
    change_pattern: Callable[[SelectionBox, str, str], None],
) -> list[QWidget]:
    """Pattern card and parameter form; `change_pattern(box, old, new)` owns the reset."""
    names = [n for n in [*PATTERNS, "sparse_noise"] if n not in BARS]
    selector = combo(tuple(PATTERN_NAMES.get(n, humanize(n)) for n in names))
    for row, name in enumerate(names):
        selector.setItemData(row, name)
    pattern = document.get("pattern", "sparse_noise")
    shown = PATTERN_NAMES.get(pattern, humanize(pattern))
    selector.setPlaceholderText(f"{shown} (saved recipe)")
    selector.setCurrentIndex(selector.findData(pattern))
    assert isinstance(selector, SelectionBox)
    selector.currentIndexChanged.connect(
        lambda row, box=selector, old=pattern: change_pattern(
            box, old, box.itemData(row)
        )
    )
    card = Card("Texture")
    card.body.addWidget(field("Pattern", selector))
    data = document["params"] if document.get("kind") == "texture" else document
    form = property_form(
        data,
        changed,
        rebuild,
        title="Parameters",
        hidden=BAR_HIDDEN if pattern in BARS else frozenset(),
        directory=directory,
        schema=SparseNoiseAppearance if pattern == "sparse_noise" else None,
    )
    return [card, form]
