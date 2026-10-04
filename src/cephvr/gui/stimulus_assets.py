"""Single asset root shared by the protocol's prepared stimulus files."""

from cephvr.gui.components import Card
from cephvr.gui.paths import PathField
from cephvr.gui.view import DashboardView


class StimulusAssetsCard(Card):
    def __init__(self) -> None:
        super().__init__("Assets folder")
        picker = PathField(
            title="Select assets folder", placeholder="Select assets folder"
        )
        picker.setToolTip(
            "Base folder for prepared stimuli; program file paths are relative to this folder."
        )
        self.folders = {"root": picker}
        self.body.addWidget(picker)

    def apply_view(self, view: DashboardView) -> None:
        editable = view.sample and view.can_edit
        picker = self.folders["root"]
        if not editable and picker.dialog is not None:
            picker.dialog.reject()
        self.setEnabled(editable)
