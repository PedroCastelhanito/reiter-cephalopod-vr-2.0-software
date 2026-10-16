"""Painted source blocks and selected-epoch details, without repeat expansion."""

from math import ceil

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QScrollBar, QWidget

from cephvr.gui.formatting import clock_duration
from cephvr.gui.projector_layers import layers_for
from cephvr.gui.protocol_document import node_name
from cephvr.gui.theme import colors_for, retro_console
from cephvr.gui.timeline_actions import TimelineActions
from cephvr.gui.timeline_details import (
    epoch_heading,
    layer_description,
    stimulus_color,
)
from cephvr.gui.timeline_views import TimelineViews
from cephvr.visual_stimulus.config.models.program_model import (
    Epoch,
    Group,
    Node,
    Program,
)


class ProgramTimeline(QWidget):
    epochs_selected = pyqtSignal(object)
    context_selected = pyqtSignal(object)
    batch_selected = pyqtSignal(object)
    screens_changed = pyqtSignal()
    height_changed = pyqtSignal()
    viewport_changed = pyqtSignal()

    def __init__(self, *, details: bool = True) -> None:
        super().__init__()
        self.show_details = details
        self.block_actions = TimelineActions(self)
        self.hover_position = QPointF(-1, -1)
        self.program: Program | None = None
        self.views = TimelineViews()
        self.index = 0
        self.screens: tuple[str, ...] = ()
        self.paths: tuple[tuple[int, ...], ...] = ()
        self.nodes: tuple[Node, ...] = ()
        self.selection: tuple[tuple[int, ...], ...] = ()
        self.anchor = 0
        self.hits: list[tuple[QRectF, int, str, int]] = []
        self.error = ""
        self.type_keys: tuple[str, ...] = ()
        self.hover_text: list[tuple[QRectF, str]] = []
        self._height_scope: tuple[int, tuple[int, ...], tuple[str, ...]] | None = None
        self.scope: tuple[int, ...] = ()
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal, self)
        self.scrollbar.setObjectName("TimelineScroll")
        self.scrollbar.valueChanged.connect(lambda _value: self.update())
        self.scrollbar.valueChanged.connect(self.viewport_changed)
        self.batch_runs: tuple[tuple[int, int, str] | None, ...] = ()
        self.batch_hits: list[tuple[QRectF, str]] = []
        self.batch_offset = 0
        self.counts: tuple[int, ...] = ()
        self.durations: tuple[float | None, ...] = ()
        self.setMouseTracking(True)
        self.setMinimumWidth(0)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(
            "Timeline blocks. Click a group to open it; Shift selects a range; Ctrl or Command toggles blocks."
        )
        self.setToolTip(
            "Groups remain collapsed. Edit source epochs once for all repetitions. Setup resolves the final order."
        )

    def set_program(
        self,
        program: Program,
        index: int = 0,
        scope: tuple[int, ...] = (),
        face: str = "",
        layer: int = -1,
    ) -> None:
        self.program, self.scope = program, scope
        view = self.views.get(program, scope)
        self.nodes, self.paths, self.type_keys = view.nodes, view.paths, view.keys
        self.counts, self.durations = view.counts, view.durations
        self.batch_runs = view.batch_runs
        self.batch_offset = (
            40
            if any(isinstance(node, Group) for node in self.nodes)
            or (scope and any(view.batch_runs))
            else 0
        )
        self.index = max(0, min(index, len(self.nodes) - 1))
        self.selection = (self.paths[self.index],) if self.paths else ()
        self.anchor = self.index
        self.fit_lanes()
        self.fit_scroll()
        self.reveal_selection()
        self.update()

    def summary(self) -> str:
        count, blocks = sum(self.counts), len(self.nodes)
        summary = (
            f"{count:,} epoch{'s' if count != 1 else ''} · "
            f"{blocks} block{'s' if blocks != 1 else ''}"
        )
        if all(v is not None for v in self.durations):
            summary += f" · {clock_duration(sum(v or 0 for v in self.durations))}"
        else:
            summary += " · duration resolved at Setup"
        return summary

    def block_width(self) -> float:
        return max(
            150.0,
            (self.width() - (40 if self.block_actions.enabled else -7))
            / max(1, len(self.nodes)),
        )

    def fit_scroll(self) -> None:
        self.scrollbar.setGeometry(0, 70 + self.batch_offset, self.width(), 14)
        self.scrollbar.setRange(
            0,
            max(
                0,
                ceil(
                    len(self.nodes) * self.block_width()
                    - self.width()
                    + (40 if self.block_actions.enabled else -7)
                ),
            ),
        )
        self.scrollbar.setPageStep(self.width())
        self.scrollbar.setSingleStep(150)
        self.scrollbar.setVisible(self.scrollbar.maximum() > 0)
        self.viewport_changed.emit()

    def reveal_selection(self) -> None:
        start = int(self.index * self.block_width())
        end = int(start + self.block_width())
        selected = set(self.selection)
        indices = [i for i, path in enumerate(self.paths) if path in selected]
        if (
            indices
            and (indices[-1] - indices[0] + 1) * self.block_width() <= self.width()
        ):
            start = int(indices[0] * self.block_width())
            end = int((indices[-1] + 1) * self.block_width())
        if start < self.scrollbar.value():
            self.scrollbar.setValue(start)
        elif end > self.scrollbar.value() + self.width():
            self.scrollbar.setValue(end - self.width() + 8)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        self.fit_scroll()
        self.reveal_selection()
        super().resizeEvent(event)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is not None and self.scrollbar.maximum():
            delta = event.angleDelta()
            self.scrollbar.setValue(self.scrollbar.value() - (delta.x() or delta.y()))
            event.accept()
            return
        super().wheelEvent(event)

    def set_selection(self, paths: tuple[tuple[int, ...], ...]) -> None:
        self.selection = paths
        if self.paths and self.paths[self.index] not in paths:
            self.index = next(
                (i for i, path in enumerate(self.paths) if path in paths), 0
            )
        self.update()
        self.reveal_selection()

    def set_screens(self, screens: tuple[str, ...]) -> None:
        self.screens = screens
        self.screens_changed.emit()
        self.fit_lanes()
        self.update()

    def detail_rows(self) -> list[tuple[str, list[tuple[int, str]]]]:
        if not self.nodes or self.program is None:
            return []
        node = self.nodes[self.index]
        if isinstance(node, Group):
            return []
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
        scope = (id(self.program), self.scope, self.screens)
        if scope == self._height_scope:
            return
        if not self.show_details:
            self.setFixedHeight(86 + self.batch_offset)
            self._height_scope = scope
            self.height_changed.emit()
            return
        # Reserve the largest epoch, so selection never resizes the trial card.
        height = (
            120
            + max(
                (
                    sum(
                        max(38, 12 + 25 * len(layers_for(self.program, node, face)))
                        for face in self.screens or ("",)
                    )
                    for node in self.nodes
                    if isinstance(node, Epoch)
                ),
                default=38,
            )
            if self.program is not None
            else 158
        )
        self.setFixedHeight(height + self.batch_offset)
        self.updateGeometry()
        self._height_scope = scope
        self.height_changed.emit()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        colors = colors_for(self)
        retro = retro_console(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.hits.clear()
        self.batch_hits.clear()
        self.hover_text.clear()
        self.block_actions.begin()
        if self.program is None or not self.nodes or self.error:
            self.block_actions.finish(self.width(), 0, self.width())
        if self.program is None:
            return
        if self.error:
            painter.setPen(QColor(colors.muted))
            painter.drawText(self.rect(), Qt.TextFlag.TextWordWrap, self.error)
            return
        if not self.nodes:
            return
        width = self.block_width()
        first = max(0, int(self.scrollbar.value() // width))
        last = min(
            len(self.nodes), ceil((self.scrollbar.value() + self.width()) / width)
        )
        drawn_batches: set[int] = set()
        for i in range(first, last):
            node = self.nodes[i]
            run = self.batch_runs[i] if self.batch_offset else None
            if run and run[0] not in drawn_batches:
                start, end, title = run
                drawn_batches.add(start)
                left = max(1.0, start * width - self.scrollbar.value() + 1)
                right = min(
                    float(self.width() - 1), end * width - self.scrollbar.value() - 7
                )
                band = QRectF(left, 0, right - left, 36)
                painter.setBrush(QColor(colors.selection))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(band, 0 if retro else 4, 0 if retro else 4)
                painter.setPen(QColor(colors.accent))
                painter.drawText(
                    band.adjusted(8, 0, -44, 0),
                    Qt.AlignmentFlag.AlignVCenter,
                    self.fontMetrics().elidedText(
                        title,
                        Qt.TextElideMode.ElideRight,
                        max(1, int(band.width()) - 52),
                    ),
                )
                assert isinstance(node, Epoch) and node.batch_id is not None
                self.batch_hits.append((band, node.batch_id))
                paths = self.paths[start:end]
                area = QRectF(band.left(), 0, band.width(), 65 + self.batch_offset)
                if self.block_actions.enabled and (area.contains(self.hover_position)):
                    self.block_actions.place(
                        band, paths, enabled=len(paths) < len(self.paths)
                    )
                self.hover_text.append((band, title + " · Click to edit this batch"))
            rect = QRectF(
                i * width - self.scrollbar.value() + 1,
                5 + self.batch_offset,
                width - 8,
                60,
            )
            selected = self.paths[i] in self.selection
            group = isinstance(node, Group)
            painter.setBrush(
                QColor(colors.accent)
                if retro and selected
                else QColor(colors.selection if selected else colors.input)
                if group
                else stimulus_color(self.type_keys[i])
            )
            painter.setPen(
                QPen(
                    QColor(
                        (colors.accent if group else colors.text)
                        if selected
                        else colors.border
                    ),
                    2 if selected else 1,
                )
            )
            painter.drawRoundedRect(rect, 0 if retro else 6, 0 if retro else 6)
            painter.setPen(QColor(colors.window if retro and selected else colors.text))
            name = node_name(node).replace("_", " ")
            value = self.durations[i]
            summary = clock_duration(value) if value is not None else "Timing at Setup"
            lines: tuple[tuple[int, str], ...] = ((5, name), (29, summary))
            if isinstance(node, Group):
                counts = (
                    f"{node.repetitions:,} repeat{'s' if node.repetitions != 1 else ''}"
                )
                compact = (
                    max(
                        self.fontMetrics().horizontalAdvance(text)
                        for text in (counts, summary)
                    )
                    > rect.width() - 16
                )
                group_heading = QRectF(rect.left(), 0, rect.width(), 36)
                painter.setPen(QColor(colors.text))
                painter.drawText(
                    group_heading.adjusted(8, 0, -8, 0),
                    Qt.AlignmentFlag.AlignVCenter,
                    self.fontMetrics().elidedText(
                        name,
                        Qt.TextElideMode.ElideRight,
                        max(1, int(group_heading.width()) - 16),
                    ),
                )
                self.hover_text.append((group_heading, name))
                painter.setPen(
                    QColor(colors.window if retro and selected else colors.text)
                )
                lines = ((5, counts),) if compact else ((5, counts), (29, summary))
                summary = counts + " · " + summary
            for offset, text in lines:
                painter.drawText(
                    rect.adjusted(8, offset, -44 if offset == 5 else -8, 0),
                    Qt.AlignmentFlag.AlignTop,
                    self.fontMetrics().elidedText(
                        text,
                        Qt.TextElideMode.ElideRight,
                        max(1, int(rect.width()) - (52 if offset == 5 else 16)),
                    ),
                )
            if (
                self.block_actions.enabled
                and not run
                and rect.contains(self.hover_position)
            ):
                self.block_actions.place(
                    rect, (self.paths[i],), enabled=len(self.paths) > 1
                )
            self.hits.append((rect, i, "", -1))
            self.hover_text.append((rect, name + "\n" + summary))
        self.block_actions.finish(
            len(self.nodes) * width - self.scrollbar.value() + 4,
            5 + self.batch_offset,
            self.width(),
        )
        if not self.show_details:
            return
        node = self.nodes[self.index]
        heading = (
            f"{node_name(node).replace('_', ' ')} · Open group to edit its sequence"
            if isinstance(node, Group)
            else epoch_heading(node, self.index)
        )
        if len(self.selection) > 1:
            heading += f" · {len(self.selection)} selected"
        painter.setPen(QColor(colors.text))
        heading_rect = QRectF(0, 88 + self.batch_offset, self.width(), 24)
        painter.drawText(
            heading_rect,
            Qt.AlignmentFlag.AlignVCenter,
            self.fontMetrics().elidedText(
                heading, Qt.TextElideMode.ElideRight, self.width()
            ),
        )
        self.hover_text.append((heading_rect, heading))
        x0, width = 57.0, max(1.0, self.width() - 65.0)
        y = 120.0 + self.batch_offset
        for (face, layers), height in zip(
            self.detail_rows(), self.lane_heights(), strict=True
        ):
            painter.setPen(QColor(colors.label))
            painter.drawText(
                QRectF(0, y, 53, height), Qt.AlignmentFlag.AlignVCenter, face
            )
            rect = QRectF(x0, y, width, height - 5)
            painter.setBrush(QColor(colors.input))
            painter.setPen(QPen(QColor(colors.border), 1))
            painter.drawRoundedRect(rect, 0 if retro else 4, 0 if retro else 4)
            for position, (layer, text) in enumerate(layers):
                line = QRectF(x0 + 8, y + 4 + 25 * position, width - 16, 25)
                painter.setPen(QColor(colors.text if layer >= 0 else colors.muted))
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

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None:
            self.hover_position = event.position()
            self.update()
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

    def leaveEvent(self, event: QEvent | None) -> None:
        # Child action buttons remain inside the timeline; their hover must not hide them.
        from PyQt6.QtGui import QCursor

        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.hover_position = QPointF(-1, -1)
            self.update()
        super().leaveEvent(event)

    def choose(self, index: int, modifiers: Qt.KeyboardModifier) -> None:
        if not self.paths:
            return
        index = max(0, min(index, len(self.paths) - 1))
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            paths = self.paths[min(self.anchor, index) : max(self.anchor, index) + 1]
        elif modifiers & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            selected = set(self.selection)
            path = self.paths[index]
            selected.symmetric_difference_update((path,))
            paths = tuple(p for p in self.paths if p in selected)
            if not paths:
                paths = (path,)
            self.anchor = index
        else:
            paths = (self.paths[index],)
            self.anchor = index
        self.index = index
        self.selection = tuple(dict.fromkeys(paths))
        self.reveal_selection()
        self.epochs_selected.emit(self.selection)
        self.fit_lanes()
        self.update()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.RightButton:
            for rect, i, _, _ in reversed(self.hits):
                if rect.contains(event.position()):
                    self.index = self.anchor = i
                    self.context_selected.emit((self.paths[i],))
                    break
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            for rect, identity in self.batch_hits:
                if rect.contains(event.position()):
                    self.batch_selected.emit(
                        tuple(
                            p
                            for p, n in zip(self.paths, self.nodes, strict=True)
                            if isinstance(n, Epoch) and n.batch_id == identity
                        )
                    )
                    return
            for rect, i, _, _ in reversed(self.hits):
                if rect.contains(event.position()):
                    self.choose(i, event.modifiers())
                    return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
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
