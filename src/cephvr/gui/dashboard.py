"""Dashboard presentation, with no transport, SDK or experiment ownership."""

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
)

from cephvr.gui.components import (
    Card,
    StatusColumn,
    StatusIndicator,
    button,
    combo,
    field,
    label,
)
from cephvr.gui.dialogs import StopDialog
from cephvr.gui.formatting import duration, metrics_text
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.paths import DirectoryField
from cephvr.gui.previews import PreviewDialog
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView, Phase

ACTION_PHASES = {
    "Setup": {Phase.CONFIGURATION},
    "Cancel Setup": {Phase.SETTING_UP, Phase.READY},
    "Start": {Phase.READY},
    "Stop after trial": {Phase.STARTING, Phase.RUNNING},
    "Abort now": {Phase.STARTING, Phase.RUNNING, Phase.STOPPING, Phase.FINALIZING},
    "New session": {Phase.ENDED},
}


class Dashboard(ResponsiveColumns):
    action_requested = pyqtSignal(str)
    preview_requested = pyqtSignal(str, bool)

    def __init__(
        self, *, sample: bool = False, settings: QSettings | None = None
    ) -> None:
        left, left_layout = column()
        right = StatusColumn()
        super().__init__(left, right)
        self.view = DashboardView()
        self.stop_dialog: StopDialog | None = None
        self.preview_dialog = PreviewDialog(self, settings)
        self.preview_dialog.visibility_requested.connect(self.preview_requested.emit)
        self.preview_button = button("Previews…")
        self.preview_button.clicked.connect(self.show_previews)
        self.session_controls = self.build_controls()
        self.subject_card = self.build_subject(sample)
        for card in (self.session_controls, self.subject_card):
            left_layout.addWidget(card)
        left_layout.addStretch()
        self.hud_card = right.hud_card
        self.log_card = right.log_card
        self.runtime_console = right.hud
        self.log_console = right.console
        self.apply_view(self.view)

    def build_controls(self) -> Card:
        card = Card("System controls")
        status_row = QHBoxLayout()
        status_row.setSpacing(SIZES.field_x_gap)
        self.backend_indicators = {}
        for name in ("Cameras", "Visual stimulus", "Tracking"):
            indicator = StatusIndicator(name)
            self.backend_indicators[name] = indicator
            status_row.addWidget(indicator, 1)
        card.body.addLayout(status_row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(SIZES.field_x_gap)
        grid.setVerticalSpacing(SIZES.field_y_gap)
        self.command_buttons: dict[str, QPushButton] = {}
        handlers = {
            "Setup": self.setup,
            "Start": lambda: self.request_action("Start"),
            "Stop": self.stop,
        }
        for index, (name, handler) in enumerate(handlers.items()):
            control = button(name, "danger" if name == "Stop" else "primary")
            control.clicked.connect(handler)
            self.command_buttons[name] = control
            if name == "Setup":
                grid.addWidget(control, 0, 0, 1, 2)
            else:
                grid.addWidget(control, 1, index - 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        self.control_hint = label(
            "Waiting for a controller connection.", "muted", wrap=True
        )
        card.body.addWidget(self.control_hint)
        return card

    def build_subject(self, sample: bool) -> Card:
        card = Card("Session config")
        grid = QGridLayout()
        grid.setHorizontalSpacing(SIZES.field_x_gap)
        grid.setVerticalSpacing(SIZES.field_y_gap)
        self.subject_id = QLineEdit("CEPH-007" if sample else "")
        self.subject_id.setPlaceholderText("Subject ID")
        self.species = QLineEdit("Sepia officinalis" if sample else "")
        self.species.setPlaceholderText("Species")
        self.sex = combo(("Not specified", "Female", "Male"))
        self.age = QLineEdit()
        self.age.setPlaceholderText("Age (dph)")
        self.subject_size = QLineEdit()
        self.subject_size.setPlaceholderText("Size (mm)")
        self.experiment = QLineEdit("Optic flow" if sample else "")
        self.condition = QLineEdit("Baseline" if sample else "")
        self.output_field = DirectoryField()
        self.output_root = self.output_field.editor
        self.subject_editors = (
            self.subject_id,
            self.species,
            self.sex,
            self.age,
            self.subject_size,
            self.experiment,
            self.condition,
            self.output_field,
        )
        grid.addWidget(field("SUBJECT ID", self.subject_id), 0, 0)
        grid.addWidget(field("EXPERIMENT", self.experiment), 0, 1)
        grid.addWidget(field("OUTPUT DIRECTORY", self.output_field), 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        card.body.addSpacing(SIZES.card_padding)
        details = QGridLayout()
        details.setHorizontalSpacing(SIZES.field_x_gap)
        details.setVerticalSpacing(SIZES.field_y_gap)
        fields = (
            ("SPECIES", self.species),
            ("SEX", self.sex),
            ("AGE (dph)", self.age),
            ("SIZE (mm)", self.subject_size),
        )
        for index, (title, editor) in enumerate(fields):
            details.addWidget(field(title, editor), index // 2, index % 2)
        details.addWidget(field("CONDITION", self.condition), 2, 0, 1, 2)
        details.setColumnStretch(0, 1)
        details.setColumnStretch(1, 1)
        card.body.addLayout(details)
        return card

    def can_request(self, action: str) -> bool:
        view = self.view
        return (
            action in ACTION_PHASES
            and view.phase in ACTION_PHASES[action]
            and view.has_control
            and (view.connected or view.sample)
        )

    def show_previews(self) -> None:
        if self.preview_dialog.isVisible():
            self.preview_dialog.close()
            return
        main = self.window()
        if main is not None:
            self.preview_dialog.show_saved(main)

    def request_action(self, action: str) -> None:
        if self.can_request(action):
            self.action_requested.emit(action)

    def setup(self) -> None:
        self.request_action(
            "New session" if self.view.phase == Phase.ENDED else "Setup"
        )

    def stop_choices(self) -> frozenset[str]:
        return frozenset(
            action
            for action in ("Abort now", "Stop after trial")
            if self.can_request(action)
        )

    def stop(self) -> None:
        if self.can_request("Cancel Setup"):
            self.request_action("Cancel Setup")
            return
        choices = self.stop_choices()
        if not choices:
            return
        if self.stop_dialog is not None:
            self.stop_dialog.raise_()
            return
        dialog = StopDialog(choices, self)
        self.stop_dialog = dialog
        dialog.action_selected.connect(self.request_action)
        dialog.finished.connect(self.stop_dialog_finished)
        dialog.finished.connect(dialog.deleteLater)
        dialog.open()

    def stop_dialog_finished(self, result: int) -> None:
        self.stop_dialog = None

    def apply_view(self, view: DashboardView) -> None:
        self.view = view
        self.preview_dialog.apply_views(
            view.previews,
            allowed=view.has_control and (view.connected or view.sample),
            sample=view.sample,
        )
        setup_action = "New session" if view.phase == Phase.ENDED else "Setup"
        self.command_buttons["Setup"].setEnabled(self.can_request(setup_action))
        self.command_buttons["Start"].setEnabled(self.can_request("Start"))
        self.command_buttons["Stop"].setEnabled(
            self.can_request("Cancel Setup") or bool(self.stop_choices())
        )
        self.command_buttons["Setup"].setToolTip(
            "Return to Configuration for a new session."
            if view.phase == Phase.ENDED
            else "Prepare a session."
        )
        self.command_buttons["Stop"].setToolTip(
            "Cancel setup and return to Configuration."
            if self.can_request("Cancel Setup")
            else "Choose Stop now or Stop after trial."
        )
        if self.stop_dialog is not None:
            self.stop_dialog.update_actions(self.stop_choices())
        for editor in self.subject_editors:
            editor.setEnabled(view.can_edit)
        self.control_hint.setText(
            "Local review · buttons report intent only."
            if view.sample and view.has_control
            else "Observer · editing and commands unavailable."
            if view.sample or view.connected
            else "Waiting for a controller connection."
        )
        self.control_hint.setVisible(not view.sample)
        rows = (
            ("PHASE", view.phase.value),
            ("CONTROL", "Local review" if view.sample else "Observer"),
            (
                "TRIAL",
                f"{view.trial_index}/{view.trial_count}" if view.trial_count else "—",
            ),
            ("ELAPSED", duration(view.elapsed_s)),
            ("OUTCOME", view.outcome),
        )
        output_rows = (
            ("RECORDING", view.output_status),
            ("METADATA", view.metadata_status),
        )
        self.runtime_console.setPlainText(
            metrics_text(rows) + "\n\n" + metrics_text(output_rows)
        )
        for name, status in (
            ("Cameras", view.camera_status),
            ("Visual stimulus", view.stimulus_status),
            ("Tracking", view.tracking_status),
        ):
            self.backend_indicators[name].set_status(status)
