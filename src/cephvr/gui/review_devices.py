"""Device layout candidates confined to the local review window."""

from PyQt6.QtWidgets import QVBoxLayout

from cephvr.gui.microcontroller import MicrocontrollerPanel


def arrange_devices(mcu: MicrocontrollerPanel) -> None:
    layout = mcu.columns[0].layout()
    assert isinstance(layout, QVBoxLayout)
    layout.removeWidget(mcu.triggers)
    position = layout.indexOf(mcu.configuration) + 1
    layout.insertWidget(position, mcu.io)
    layout.insertWidget(position + 1, mcu.triggers)
    mcu.io.show()
