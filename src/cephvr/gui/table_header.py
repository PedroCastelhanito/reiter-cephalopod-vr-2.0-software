"""Shared styled headers that wrap within their actual section widths."""

from PyQt6.QtCore import QPointF, QRect, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QTextLayout, QTextOption
from PyQt6.QtWidgets import QHeaderView, QStyle, QStyleOptionHeader

from cephvr.gui.formatting import caption_caps
from cephvr.gui.theme import SIZES, colors_for, minimal_frames, retro_console


class TableHeader(QHeaderView):
    def phosphor(self) -> bool:
        return minimal_frames(self) and retro_console(self)

    def label_layout(self, index: int, width: int) -> QTextLayout:
        model = self.model()
        text = str(model.headerData(index, self.orientation()) or "") if model else ""
        font = QFont(self.font())
        font.setPixelSize(SIZES.label_font)
        text = text.replace("\n", " ")
        if self.phosphor():
            # Same caption treatment as field labels: tracked, uppercase, regular.
            text = caption_caps(text)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        else:
            font.setBold(True)
        layout = QTextLayout(text, font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        y = 0.0
        while (line := layout.createLine()).isValid():
            line.setLineWidth(max(1, width - 2 * SIZES.table_cell_padding))
            line.setPosition(QPointF(0, y))
            y += line.height()
        layout.endLayout()
        return layout

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        height = max(
            (
                self.label_layout(i, self.sectionSize(i)).boundingRect().height()
                for i in range(self.count())
                if not self.isSectionHidden(i)
            ),
            default=0,
        )
        size.setHeight(max(size.height(), int(height + 16)))
        return size

    def paintSection(self, painter: QPainter | None, rect: QRect, index: int) -> None:
        if painter is None:
            return
        option = QStyleOptionHeader()
        self.initStyleOptionForIndex(option, index)
        option.rect = rect
        option.text = ""
        style = self.style()
        assert style is not None
        painter.save()
        style.drawControl(QStyle.ControlElement.CE_Header, option, painter, self)
        painter.setClipRect(rect)
        colors = colors_for(self)
        painter.setPen(QColor(colors.label if self.phosphor() else colors.accent))
        layout = self.label_layout(index, rect.width())
        layout.draw(
            painter,
            QPointF(
                rect.left() + SIZES.table_cell_padding,
                rect.top() + (rect.height() - layout.boundingRect().height()) / 2,
            ),
        )
        painter.restore()
