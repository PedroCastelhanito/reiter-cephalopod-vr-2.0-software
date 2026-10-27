"""Themed invalid-field markers; every mark also carries text, never colour alone."""

import re

from PyQt6.QtWidgets import QAbstractSpinBox, QComboBox, QLabel, QLineEdit, QWidget

MODEL, LOCAL = "model", "local"


def repolish(widget: QWidget) -> None:
    style = widget.style()
    assert style is not None
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def owning_field(widget: QWidget) -> QWidget | None:
    current: QWidget | None = widget
    while current is not None and current.property("fieldPath") is None:
        current = current.parentWidget()
    return current


def _controls(field: QWidget) -> list[QWidget]:
    return [
        child
        for child in field.findChildren(QWidget)
        if isinstance(child, (QLineEdit, QAbstractSpinBox, QComboBox))
        and not isinstance(child.parentWidget(), QAbstractSpinBox)
    ]


def mark_field(widget: QWidget, message: str, source: str = LOCAL) -> None:
    field = owning_field(widget)
    if field is None:
        return
    for control in _controls(field):
        if control.property("hintText") is None:
            control.setProperty("hintText", control.toolTip())
        control.setProperty("invalid", True)
        control.setToolTip(message)
        repolish(control)
    note = field.findChild(QLabel, "FieldError")
    if note is not None:
        note.setText(message)
        note.setVisible(True)
    field.setProperty("invalidSource", source)


def clear_field(widget: QWidget) -> None:
    field = owning_field(widget)
    if field is None or field.property("invalidSource") is None:
        return
    for control in _controls(field):
        control.setProperty("invalid", False)
        control.setToolTip(str(control.property("hintText") or ""))
        repolish(control)
    note = field.findChild(QLabel, "FieldError")
    if note is not None:
        note.clear()
        note.hide()
    field.setProperty("invalidSource", None)


def clear_errors(panel: QWidget) -> None:
    for field in panel.findChildren(QWidget):
        if field.property("invalidSource") == MODEL:
            clear_field(field)
    for banner in panel.findChildren(QLabel, "FormError"):
        banner.clear()
        banner.hide()


def _mentions(message: str, path: str) -> bool:
    """Whether a message names a parameter by key or by its words, e.g. "element size"."""
    key = path.rsplit(".", 1)[-1]
    stem = re.sub(r"_(mm|deg|per_cm2|octaves)$", "", key)
    words = [key, stem.replace("_", " ")] if len(stem) > 3 else [key]
    return any(re.search(rf"\b{re.escape(w)}\b", message, re.I) for w in words)


def show_errors(panel: QWidget, items: list[tuple[str, str]]) -> list[str]:
    """Mark the control each issue names, else the nearest form; return the unplaced."""
    clear_errors(panel)
    widgets = panel.findChildren(QWidget)
    fields = {
        str(w.property("fieldPath")): w for w in widgets if w.property("fieldPath")
    }
    forms = {
        str(w.property("formPath")): w
        for w in (panel, *widgets)
        if w.property("formPath") is not None
    }
    unplaced = []
    for path, message in items:
        targets = [fields[path]] if path in fields else []
        if not targets and not path:
            # Backend messages without a location usually name their parameters.
            targets = [w for key, w in fields.items() if _mentions(message, key)]
        for target in targets:
            mark_field(target, message, MODEL)
        if targets:
            continue
        owner = max(
            (p for p in forms if path == p or path.startswith(p + ".") or not p),
            key=len,
            default=None,
        )
        banner = None if owner is None else forms[owner].findChild(QLabel, "FormError")
        if banner is None:
            unplaced.append(message)
            continue
        banner.setText((banner.text() + "\n" if banner.text() else "") + message)
        banner.show()
    return unplaced


def workspace_items(
    problems: list[tuple[str, str]], arena: bool, selected: list[str]
) -> list[tuple[str, str]]:
    """Translate document paths to the visible form's paths; drop hidden surfaces."""
    items = []
    for path, message in problems:
        parts = path.split(".")
        if arena and parts[0] == "surfaces" and len(parts) > 1:
            # One form edits all selected surfaces; show the first one's issues.
            if parts[1] not in selected:
                continue
            parts[1] = selected[0]
        elif not arena and parts[0] == "params":
            parts = parts[1:]
        items.append((".".join(parts), message))
    return items
