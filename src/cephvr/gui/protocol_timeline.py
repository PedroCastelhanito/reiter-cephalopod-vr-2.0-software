"""Full-trial visualization and source-epoch selection; no mutation controls."""

from math import isfinite

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

from cephvr.gui.projector_layers import layers_for
from cephvr.gui.protocol_document import duration
from cephvr.gui.theme import COLORS
from cephvr.gui.timeline_details import (
    epoch_heading,
    layer_description,
    stimulus_color,
)
from cephvr.gui.timeline_views import TimelineViews
from cephvr.visual_stimulus.config.models.program_model import Epoch, Explicit, Program


class ProgramTimeline(QWidget):
    epochs_selected = pyqtSignal(object)
    screens_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.program: Program | None = None
        self.views = TimelineViews()
        self.index = 0
        self.screens: tuple[str, ...] = ()
        self.paths: tuple[tuple[int, ...], ...] = ()
        self.nodes: tuple[Epoch, ...] = ()
        self.selection: tuple[tuple[int, ...], ...] = ()
        self.anchor = 0
        self.hits: list[tuple[QRectF, int, str, int]] = []
        self.error = ""
        self.type_keys: tuple[str, ...] = ()
        self.hover_text: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setMinimumWidth(0)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(
            "Trial timeline. Click an epoch; Shift selects a range; Ctrl or Command toggles epochs."
        )
        self.setToolTip(
            "Select source epochs. Repeated occurrences share edits. Shuffled order is an authoring example; Setup retains the final order."
        )

    def set_program(
        self,
        program: Program,
        index: int = 0,
        scope: tuple[int, ...] = (),
        face: str = "",
        layer: int = -1,
    ) -> None:
        self.program = program
        view = self.views.get(program)
        paths = view.sources
        self.nodes, self.paths, self.type_keys, self.error = (
            view.nodes,
            view.paths,
            view.keys,
            view.error,
        )
        selected = (*scope, index)
        self.selection = tuple(
            p for p in paths if p == selected or p[: len(selected)] == selected
        )
        self.index = next(
            (i for i, p in enumerate(self.paths) if p in self.selection), 0
        )
        self.anchor = self.index
        self.fit_lanes()
        self.update()

    def summary(self) -> str:
        count = len(self.nodes)
        sources = len(set(self.paths))
        summary = f"{count} epoch{'s' if count != 1 else ''}"
        if sources != count:
            summary += f" · {sources} source epochs"
        values = [duration(n) for n in self.nodes]
        if all(v is not None for v in values):
            summary += f" · {sum(v or 0 for v in values):g} s"
        if self.program and any(n.kind == "group" for n in self.program.sequence):
            summary += " · example order"
        return summary

    def set_selection(self, paths: tuple[tuple[int, ...], ...]) -> None:
        self.selection = paths
        if self.paths and self.paths[self.index] not in paths:
            self.index = next(
                (i for i, path in enumerate(self.paths) if path in paths), 0
            )
        self.fit_lanes()
        self.update()

    def set_screens(self, screens: tuple[str, ...]) -> None:
        self.screens = screens
        self.screens_changed.emit()
        self.fit_lanes()
        self.update()

    def detail_rows(self) -> list[tuple[str, list[tuple[int, str]]]]:
        if not self.nodes or self.program is None:
            return []
        node = self.nodes[self.index]
        rows = []
        scene = next(s for s in self.program.scenes if s.scene_id == node.scene_id)
        background = (
            "Blank"
            if not any(scene.background_linear_rgb)
            else f"Background RGB {scene.background_linear_rgb}"
        )
        for face in self.screens or ("",):
            layers = [
                (i, layer_description(self.program, node.settings[i]))
                for i in layers_for(self.program, node, face)
            ]
            rows.append((face or "All", layers or [(-1, background)]))
        return rows

    def lane_heights(self) -> list[int]:
        return [max(38, 12 + 25 * len(layers)) for _, layers in self.detail_rows()]

    def fit_lanes(self) -> None:
        self.setMinimumHeight(120 + sum(self.lane_heights()))
        self.updateGeometry()

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.hits.clear()
        self.hover_text.clear()
        if self.program is None:
            return
        if self.error:
            painter.setPen(QColor(COLORS.muted))
            painter.drawText(self.rect(), Qt.TextFlag.TextWordWrap, self.error)
            return
        times = [duration(n) for n in self.nodes]
        timed = isinstance(self.program.duration, Explicit) and all(
            t is not None for t in times
        )
        weights = (
            [max(t or 0.0, 0.000001) for t in times] if timed else [1.0] * len(times)
        )
        total = sum(weights)
        if not isfinite(total):
            weights, timed = [1.0] * len(times), False
            total = sum(weights)
        if not total:
            return
        x0, width = 1.0, max(1.0, self.width() - 9.0)
        painter.setPen(QColor(COLORS.muted))
        ticks = 4 if width >= 320 else 2
        for tick in range(ticks + 1):
            x = x0 + width * tick / ticks
            caption = (
                f"{total * tick / ticks:g}"
                if timed
                else ("Sequence order" if tick == 0 else "")
            )
            if tick == ticks and timed:
                caption += " s"
            painter.drawText(
                QRectF(x - (45 if tick == ticks else 0), 0, 55, 22),
                Qt.AlignmentFlag.AlignLeft,
                caption,
            )
        offset = 0.0
        for i, (node, weight) in enumerate(zip(self.nodes, weights, strict=True)):
            rect = QRectF(
                x0 + width * offset / total,
                27,
                max(
                    0.5, width * weight / total - (2 if i < len(self.nodes) - 1 else 0)
                ),
                34,
            )
            offset += weight
            selected = self.paths[i] in self.selection
            painter.setBrush(stimulus_color(self.type_keys[i]))
            painter.setPen(
                QPen(
                    QColor(COLORS.text if selected else COLORS.border),
                    2 if selected else 1,
                )
            )
            painter.drawRoundedRect(rect, 4, 4)
            if rect.width() > 24:
                painter.setPen(QColor(COLORS.text))
                caption = f"{i + 1} · {node.epoch_id.replace('_', ' ')}"
                painter.drawText(
                    rect.adjusted(5, 0, -5, 0),
                    Qt.AlignmentFlag.AlignVCenter,
                    self.fontMetrics().elidedText(
                        caption,
                        Qt.TextElideMode.ElideRight,
                        max(1, int(rect.width()) - 10),
                    ),
                )
            self.hits.append((rect, i, "", -1))
            self.hover_text.append(
                (
                    rect,
                    epoch_heading(node, i)
                    + "\nMatching colors share stimulus settings; names and durations may differ.",
                )
            )
        node = self.nodes[self.index]
        heading = epoch_heading(node, self.index)
        if len(self.selection) > 1:
            heading += f" · {len(self.selection)} selected"
        painter.setPen(QColor(COLORS.text))
        heading_rect = QRectF(0, 88, self.width(), 24)
        painter.drawText(
            heading_rect,
            Qt.AlignmentFlag.AlignVCenter,
            self.fontMetrics().elidedText(
                heading, Qt.TextElideMode.ElideRight, self.width()
            ),
        )
        self.hover_text.append((heading_rect, heading))
        x0, width = 57.0, max(1.0, self.width() - 65.0)
        y = 120.0
        for (face, layers), height in zip(
            self.detail_rows(), self.lane_heights(), strict=True
        ):
            painter.setPen(QColor(COLORS.label))
            painter.drawText(
                QRectF(0, y, 53, height), Qt.AlignmentFlag.AlignVCenter, face
            )
            rect = QRectF(x0, y, width, height - 5)
            painter.setBrush(QColor(COLORS.input))
            painter.setPen(QPen(QColor(COLORS.border), 1))
            painter.drawRoundedRect(rect, 4, 4)
            for position, (layer, text) in enumerate(layers):
                line = QRectF(x0 + 8, y + 4 + 25 * position, width - 16, 25)
                painter.setPen(QColor(COLORS.text if layer >= 0 else COLORS.muted))
                painter.drawText(
                    line,
                    Qt.AlignmentFlag.AlignVCenter,
                    self.fontMetrics().elidedText(
                        text, Qt.TextElideMode.ElideRight, max(1, int(line.width()))
                    ),
                )
                self.hits.append((line, self.index, face, layer))
                self.hover_text.append((line, text))
            y += height

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is not None:
            text = next(
                (
                    text
                    for rect, text in self.hover_text
                    if rect.contains(event.position())
                ),
                "",
            )
            self.setToolTip(text)
        super().mouseMoveEvent(event)

    def choose(self, index: int, modifiers: Qt.KeyboardModifier) -> None:
        if not self.paths:
            return
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            paths = self.paths[min(self.anchor, index) : max(self.anchor, index) + 1]
        elif modifiers & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            selected = set(self.selection)
            path = self.paths[index]
            selected.symmetric_difference_update((path,))
            paths = tuple(p for p in self.paths if p in selected)
            self.anchor = index
        else:
            paths = (self.paths[index],)
            self.anchor = index
        self.index = index
        self.selection = tuple(dict.fromkeys(paths))
        self.epochs_selected.emit(self.selection)
        self.fit_lanes()
        self.update()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            for rect, i, _, _ in reversed(self.hits):
                if rect.contains(event.position()):
                    self.choose(i, event.modifiers())
                    return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        if event is not None and self.paths:
            delta = {int(Qt.Key.Key_Left): -1, int(Qt.Key.Key_Right): 1}.get(
                event.key()
            )
            if delta is not None:
                self.choose(
                    max(0, min(len(self.paths) - 1, self.index + delta)),
                    event.modifiers(),
                )
                return
        super().keyPressEvent(event)
