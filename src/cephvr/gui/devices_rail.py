"""Optional Devices side rail: one list for devices and their sections.

Presentation only. The device tab bar and the Projectors section tabs stay the
source of truth; the rail mirrors and drives them.
"""

from PyQt6.QtCore import QEvent, QModelIndex, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
)

from cephvr.gui.icons import device_icon
from cephvr.gui.theme import (
    PHOSPHOR_TAB_DIM,
    SIZES,
    colors_for,
    minimal_frames,
    retro_console,
)

RAIL_WIDTH = 176
DEVICE_ICONS = ("camera", "board", "projector", "signal")


class RailMarkerDelegate(QStyledItemDelegate):
    """Amber rows have a leading `>` and a coral trailing `<` when selected."""

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        if painter is None:
            return
        view = self.parent()
        if not isinstance(view, QTreeWidget) or not (
            minimal_frames(view) and retro_console(view)
        ):
            super().paint(painter, option, index)
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        item = QStyleOptionViewItem(option)
        self.initStyleOption(item, index)
        style = view.style()
        assert style is not None
        font = QFont(view.font())
        font.setPixelSize(SIZES.label_font + 3)
        trailing: QRectF | None = None
        if selected:
            text_rect = style.subElementRect(
                QStyle.SubElement.SE_ItemViewItemText, item, view
            )
            marker_metrics = QFontMetrics(font)
            marker_width = marker_metrics.horizontalAdvance("<")
            inset = (
                style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, item, view)
                + 1
            )
            text_left = text_rect.left() + inset
            content_left = (
                style.subElementRect(
                    QStyle.SubElement.SE_ItemViewItemDecoration, item, view
                ).left()
                if not item.icon.isNull()
                else text_left
            )
            if not item.icon.isNull():
                pixmap = item.icon.pixmap(item.decorationSize)
                content_left += round(
                    QRegion(pixmap.mask()).boundingRect().left()
                    / pixmap.devicePixelRatio()
                )
            gap = content_left - (
                option.rect.left() + 4 + marker_metrics.boundingRect(">").right()
            )
            item.text = item.fontMetrics.elidedText(
                item.text,
                item.textElideMode,
                max(0, text_rect.width() - marker_width - gap - 2 * inset),
            )
            trailing = QRectF(
                text_left
                + item.fontMetrics.boundingRect(item.text).right()
                + gap
                - marker_metrics.boundingRect("<").left(),
                option.rect.top(),
                14,
                option.rect.height(),
            )
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, item, painter, view)
        colors = colors_for(view)
        painter.save()
        painter.setFont(font)
        painter.setPen(
            QColor(
                colors.coral
                if selected
                else colors.text
                if hovered
                else PHOSPHOR_TAB_DIM
            )
        )
        painter.drawText(
            QRectF(option.rect.left() + 4, option.rect.top(), 14, option.rect.height()),
            Qt.AlignmentFlag.AlignVCenter,
            ">",
        )
        if trailing is not None:
            painter.drawText(trailing, Qt.AlignmentFlag.AlignVCenter, "<")
        painter.restore()


class DeviceRail(QTreeWidget):
    """Devices as top-level rows; a device's sections are its indented children."""

    chosen = pyqtSignal(int, int)  # device index, section index (-1 = the device)

    def __init__(
        self,
        names: tuple[str, ...],
        sections: dict[int, tuple[str, ...]],
        *,
        icons: tuple[str, ...] = DEVICE_ICONS,
    ) -> None:
        super().__init__()
        self.icons = icons
        self.setProperty("role", "rail")
        self.setAccessibleName("Devices navigation")
        self.hover: QTreeWidgetItem | None = None
        self.navigation_active = True
        self.setMouseTracking(True)
        self.setItemDelegate(RailMarkerDelegate(self))
        self.itemEntered.connect(self.set_hover)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        # Sections align under the device label via a blank icon, not a tree indent.
        self.setIndentation(0)
        self.setIconSize(QSize(20, 20))
        self.setFixedWidth(RAIL_WIDTH)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.devices: list[QTreeWidgetItem] = []
        self.rows: dict[tuple[int, int], QTreeWidgetItem] = {}
        blank = QPixmap(20, 20)
        blank.fill(Qt.GlobalColor.transparent)
        child_font = QFont(self.font())
        child_font.setPixelSize(SIZES.label_font + 1)
        for index, name in enumerate(names):
            item = QTreeWidgetItem([name])
            item.setData(0, Qt.ItemDataRole.UserRole, (index, -1))
            self.addTopLevelItem(item)
            self.devices.append(item)
            self.rows[(index, -1)] = item
            for section, title in enumerate(sections.get(index, ())):
                child = QTreeWidgetItem([title])
                child.setData(0, Qt.ItemDataRole.UserRole, (index, section))
                child.setFont(0, child_font)
                child.setIcon(0, QIcon(blank))
                item.addChild(child)
                self.rows[(index, section)] = child
            item.setExpanded(True)
        self.itemClicked.connect(self.item_chosen)
        self.currentItemChanged.connect(self.current_changed)
        self.refresh_icons()

    def item_chosen(self, item: QTreeWidgetItem | None, column: int = 0) -> None:
        if item is not None:
            self.chosen.emit(*item.data(0, Qt.ItemDataRole.UserRole))

    def current_changed(
        self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None
    ) -> None:
        """Keyboard navigation selects too; mirror it exactly like a click."""
        if current is not None and self.hasFocus():
            self.item_chosen(current)

    def show_position(self, device: int, section: int) -> None:
        """Mirror the page state without emitting a choice back."""
        row = self.rows.get((device, section if section >= 0 else -1))
        if row is None:
            return
        self.blockSignals(True)
        try:
            self.setCurrentItem(row)
            row.setSelected(self.navigation_active)
        finally:
            self.blockSignals(False)
        self.refresh_icons()

    def set_navigation_active(self, active: bool) -> None:
        """Hide selection outside the owning main page, retaining its current row."""
        self.navigation_active = active
        current = self.currentItem()
        if current is not None:
            current.setSelected(active)
        self.refresh_icons()

    def set_hover(self, item: QTreeWidgetItem | None, column: int = 0) -> None:
        if item is not self.hover:
            self.hover = item
            self.refresh_icons()

    def leaveEvent(self, event: QEvent | None) -> None:
        self.set_hover(None)
        super().leaveEvent(event)

    def refresh_icons(self) -> None:
        """Selected icons brighten with their text on the unfilled navigation row."""
        colors = colors_for(self)
        current = self.currentItem()
        for index, item in enumerate(self.devices):
            selected = current is item and item.isSelected()
            if minimal_frames(self) and retro_console(self):
                ink = (
                    colors.coral
                    if selected
                    else colors.text
                    if item is self.hover
                    else PHOSPHOR_TAB_DIM
                )
            else:
                ink = colors.text if selected else colors.accent
            item.setIcon(
                0,
                device_icon(self.icons[index], ink)
                if index < len(self.icons)
                else QIcon(),
            )
