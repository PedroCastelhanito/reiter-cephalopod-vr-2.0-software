"""Present the existing motion link as a Self/Linked choice and source selector."""

from PyQt6.QtWidgets import QComboBox

from cephvr.gui.components import SelectionBox


class MotionSource(SelectionBox):
    def __init__(self, linked_to: QComboBox) -> None:
        super().__init__()
        self.setProperty("chevron", True)
        self.linked_to = linked_to
        self.addItems(("Self", "Linked"))
        self.setCurrentIndex(1 if linked_to.currentData() is not None else 0)
        linked_to.setPlaceholderText("Choose source")
        self.currentIndexChanged.connect(self.choose)
        linked_to.currentIndexChanged.connect(self.sync)

    def showPopup(self) -> None:
        view = self.view()
        assert view is not None
        view.ensurePolished()
        # Styled popup chrome must not force either of the two choices to scroll.
        view.setMinimumHeight(
            sum(view.sizeHintForRow(index) for index in range(self.count()))
            + 2 * view.frameWidth()
        )
        super().showPopup()

    def choose(self, index: int) -> None:
        if index == 0:
            self.linked_to.setCurrentIndex(0)
        elif self.linked_to.currentIndex() == 0:
            self.linked_to.setCurrentIndex(-1)

    def sync(self, index: int) -> None:
        if self.linked_to.currentData() is not None:
            self.setCurrentIndex(1)
        elif index == 0:
            self.setCurrentIndex(0)

    def validate(self) -> None:
        if self.currentText() == "Linked" and self.linked_to.currentData() is None:
            raise ValueError("Choose a motion source for linked motion")
