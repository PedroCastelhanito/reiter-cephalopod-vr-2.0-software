"""Device layout candidates confined to the local review window."""

from PyQt6.QtWidgets import QVBoxLayout

from cephvr.gui.cameras import CamerasPanel
from cephvr.gui.microcontroller import MicrocontrollerPanel


def arrange_devices(cameras: CamerasPanel, mcu: MicrocontrollerPanel) -> None:
    grid = cameras.inventory_actions
    grid.removeWidget(cameras.wiring_button)
    cameras.wiring_button.hide()
    grid.removeWidget(cameras.connect_button)
    grid.addWidget(cameras.connect_button, 0, 1)
    layout = mcu.columns[0].layout()
    assert isinstance(layout, QVBoxLayout)
    layout.removeWidget(mcu.triggers)
    position = layout.indexOf(mcu.configuration) + 1
    layout.insertWidget(position, mcu.io)
    layout.insertWidget(position + 1, mcu.triggers)
    mcu.io.show()
