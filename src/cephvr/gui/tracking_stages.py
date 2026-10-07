"""Pre-experiment stage switches; experiment pipelines keep all required stages."""

from PyQt6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from cephvr.gui.components import Card
from cephvr.gui.theme import SIZES

STAGES = (
    "pose",
    "sampling_region",
    "optical_flow",
    "flow_quality",
    "locomotion",
)


def preview_switch() -> QCheckBox:
    toggle = QCheckBox("Enable")
    toggle.setChecked(False)
    toggle.setToolTip(
        "Select this stage for a pre-experiment diagnostic. Experiment Tracking "
        "participation and its required stages are configured separately."
    )
    return toggle


class StageCard(Card):
    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.enabled = preview_switch()
        self.content = QWidget()
        self.body.addWidget(self.enabled)
        self.body.addWidget(self.content)
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, SIZES.section_toggle_gap, 0, 0)
        self.body.setSpacing(10)
        self.content.setEnabled(self.enabled.isChecked())
        self.enabled.toggled.connect(self.content.setEnabled)
