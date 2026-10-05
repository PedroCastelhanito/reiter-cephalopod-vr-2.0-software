"""Responsive linking/fade row inside the projector's advanced card."""

from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from cephvr.gui.components import combo, field
from cephvr.gui.projector_layers import layer_title
from cephvr.gui.stimulus_fades import StimulusFades
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Program, Settings


class AdvancedAppearance(QWidget):
    def __init__(
        self, program: Program, epoch: Epoch, setting: Settings, duration: object
    ) -> None:
        super().__init__()
        self.linked_to = combo(("Independent",))
        self.linked_to.setMinimumWidth(0)
        self.linked_to.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        for source in epoch.settings:
            if source.instance_id != setting.instance_id:
                faces = "/".join(
                    f.title() for f in surfaces(source.model_dump(mode="json"))
                )
                self.linked_to.addItem(
                    f"{faces or 'Rig-wide'} · {layer_title(program, source)}",
                    source.instance_id,
                )
        self.linked_to.setEnabled(False)
        self.linked_to.setToolTip(
            "Linked movement awaits the source/target Tracking control ownership choice; no link is applied yet."
        )
        self.link_field = field("Linked to", self.linked_to)
        self.fades = StimulusFades(setting.model_dump(mode="json")["opacity"], duration)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self.arrange()

    def arrange(self) -> None:
        narrow = self.width() < 600
        self.grid.removeWidget(self.link_field)
        self.grid.removeWidget(self.fades)
        self.grid.addWidget(self.link_field, 0, 0, 1, 2 if narrow else 1)
        self.grid.addWidget(
            self.fades, 1 if narrow else 0, 0 if narrow else 1, 1, 2 if narrow else 1
        )
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 0 if narrow else 2)
        self.grid.activate()
        self.setMinimumHeight(self.grid.minimumSize().height())

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.arrange()
