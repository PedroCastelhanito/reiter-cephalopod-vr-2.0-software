"""Responsive Tracking configuration actions; page owns operations and drafts."""

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QGridLayout

from cephvr.gui.components import button, combo, equal_row_height, field
from cephvr.gui.editing_card import EditingCard


class TrackingControls(EditingCard):
    def __init__(self) -> None:
        super().__init__("Tracking configuration")
        self.narrow: bool | None = None
        self.pipeline = combo(("Water flow", "Fin flow"))
        self.pipeline_field = field("Pipeline", self.pipeline)
        self.preview_button = button("Annotate")
        self.preview_button.setToolTip(
            "Open the local reference-frame annotation window."
        )
        self.diagnostic_button = button("Live diagnostic")
        self.diagnostic_button.setToolTip(
            "Run selected Tracking diagnostics over the assigned camera preview."
        )
        self.diagnostic_viewer_button = button("Open viewer")
        self.diagnostic_viewer_button.setEnabled(False)
        equal_row_height(
            self.diagnostic_button, self.diagnostic_viewer_button, self.preview_button
        )
        self.action_grid = QGridLayout()
        self.body.addWidget(self.pipeline_field)
        self.body.addLayout(self.action_grid)
        self.arrange()

    def minimumSizeHint(self) -> QSize:
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def arrange(self) -> None:
        narrow = self.width() < 540
        if narrow == self.narrow:
            return
        self.narrow = narrow
        while self.action_grid.count():
            self.action_grid.takeAt(0)
        for column in range(3):
            self.action_grid.setColumnStretch(column, 0)
        for i, control in enumerate(
            (self.diagnostic_button, self.diagnostic_viewer_button, self.preview_button)
        ):
            self.action_grid.addWidget(
                control,
                i // 2 if narrow else 0,
                i % 2 if narrow else i,
                1,
                2 if narrow and i == 2 else 1,
            )
            self.action_grid.setColumnStretch(i, 1 if not narrow or i < 2 else 0)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.arrange()
