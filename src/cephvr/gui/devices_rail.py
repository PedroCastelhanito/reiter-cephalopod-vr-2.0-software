"""Optional Devices side rail: one list for devices and their sections.

Presentation only. The device tab bar and the Projectors section tabs stay the
source of truth; the rail mirrors and drives them.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from cephvr.gui.icons import device_icon
from cephvr.gui.theme import (
    PHOSPHOR_TAB_DIM,
    SIZES,
    colors_for,
    minimal_frames,
    retro_console,
)

RAIL_WIDTH = 176
# Below this page width the rail yields to the top tabs so the two columns keep room.
RAIL_MIN_PAGE_WIDTH = 1000
DEVICE_ICONS = ("camera", "board", "projector", "signal")


class DeviceRail(QTreeWidget):
    """Devices as top-level rows; a device's sections are its indented children."""

    chosen = pyqtSignal(int, int)  # device index, section index (-1 = the device)

    def __init__(
        self, names: tuple[str, ...], sections: dict[int, tuple[str, ...]]
    ) -> None:
        super().__init__()
        self.setProperty("role", "rail")
        self.setAccessibleName("Devices navigation")
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
        finally:
            self.blockSignals(False)
        self.refresh_icons()

    def refresh_icons(self) -> None:
        """Icons follow the active palette; a selected device row uses inverse ink."""
        colors = colors_for(self)
        current = self.currentItem()
        for index, item in enumerate(self.devices):
            selected = current is item
            if minimal_frames(self) and retro_console(self):
                ink = colors.text if selected else PHOSPHOR_TAB_DIM
            else:
                ink = (
                    colors.window if selected and retro_console(self) else colors.accent
                )
            item.setIcon(0, device_icon(DEVICE_ICONS[index], ink))
