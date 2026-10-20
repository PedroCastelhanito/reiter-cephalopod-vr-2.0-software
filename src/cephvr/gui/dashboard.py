"""Dashboard presentation, with no transport, SDK or experiment ownership."""

from datetime import date

from PyQt6.QtCore import QRegularExpression, QSettings, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator, QStandardItemModel
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
)
from cephvr.gui.dialogs import StopDialog, SubjectReuseDialog
from cephvr.gui.formatting import duration
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.paths import DirectoryField
from cephvr.gui.previews import PreviewDialog
from cephvr.gui.recent_values import RecentValues, suggest_values
from cephvr.gui.subject_history import SubjectSessions, find_subject_sessions
from cephvr.gui.theme import SIZES
from cephvr.gui.view import DashboardView, Phase

SPECIES = ("Sepia Pharaonis", "Sepia Latimanus", "Sepioteuthis lessoniana")

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
        self.status_column = right
        super().__init__(left, right)
        self.view = DashboardView()
        self.stop_dialog: StopDialog | None = None
        self.preview_dialog = PreviewDialog(self, settings)
        self.preview_dialog.visibility_requested.connect(self.preview_requested.emit)
        self.preview_button = button("Previews…")
        self.preview_button.clicked.connect(self.show_previews)
        self.session_controls = self.build_controls()
        self.subject_card = self.build_subject(sample)
        self.install_subject_helpers(settings)
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
        return card

    def build_subject(self, sample: bool) -> Card:
        card = Card("Session config")
        grid = QGridLayout()
        grid.setHorizontalSpacing(SIZES.field_x_gap)
        grid.setVerticalSpacing(SIZES.field_y_gap)
        self.subject_id = QLineEdit("0007" if sample else "")
        self.subject_id.setValidator(
            QRegularExpressionValidator(QRegularExpression("[0-9]{4}"), self.subject_id)
        )
        self.subject_id.setPlaceholderText("4 digits (e.g. 0001)")
        self.species = combo(SPECIES)
        self.species.setPlaceholderText("Select species")
        self.species.setCurrentIndex(0 if sample else -1)
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

    def install_subject_helpers(self, settings: QSettings | None) -> None:
        """Recent-value suggestions and the earlier-sessions hint; local aids only."""
        self.recent_conditions = RecentValues(settings, "dashboard/recent_conditions")
        suggest_values(self.condition, self.recent_conditions)
        self.reuse_dialog: SubjectReuseDialog | None = None
        self.announced_subject: tuple[str, str, int] | None = None
        for editor in (self.subject_id, self.output_root):
            editor.editingFinished.connect(self.refresh_subject_history)

    def subject_history(self) -> SubjectSessions | None:
        return find_subject_sessions(
            self.output_root.text(),
            self.subject_id.text(),
            self.experiment.text(),
            date.today(),
        )

    def refresh_subject_history(self) -> None:
        """Quiet hint (tooltip and one log line) when this ID already has sessions."""
        history = self.subject_history()
        subject = self.subject_id.text().strip()
        if history is None:
            self.subject_id.setToolTip("")
            self.announced_subject = None
            return
        plural = "s" if history.count != 1 else ""
        note = (
            f"Subject {subject} already has {history.count} earlier session{plural} "
            f"in this output directory (latest: {history.latest})."
        )
        self.subject_id.setToolTip(note + " Check for typos if this is a new animal.")
        key = (self.output_root.text().strip(), subject, history.count)
        if key != self.announced_subject:
            self.announced_subject = key
            self.log_console.appendPlainText(note)

    def confirm_subject_reuse(self, history: SubjectSessions) -> None:
        if self.reuse_dialog is not None:
            self.reuse_dialog.raise_()
            return
        dialog = SubjectReuseDialog(
            self.subject_id.text().strip(),
            self.experiment.text().strip(),
            history.count,
            history.latest,
            self,
        )
        self.reuse_dialog = dialog
        dialog.confirmed.connect(lambda: self.request_action("Setup"))
        dialog.rejected.connect(self.subject_id.setFocus)
        dialog.finished.connect(self.reuse_dialog_finished)
        dialog.finished.connect(dialog.deleteLater)
        dialog.open()

    def reuse_dialog_finished(self, result: int) -> None:
        self.reuse_dialog = None

    def can_request(self, action: str) -> bool:
        view = self.view
        return (
            action in ACTION_PHASES
            and view.phase in ACTION_PHASES[action]
            and view.has_control
            and (view.connected or view.sample)
        )

    def show_previews(self) -> None:
        main = self.window()
        if main is not None:
            self.preview_dialog.show_saved(main)

    def request_action(self, action: str) -> None:
        if self.can_request(action):
            if action == "Setup" and not self.valid_subject():
                return
            if action == "Setup":
                self.recent_conditions.remember(self.condition.text())
            self.action_requested.emit(action)

    def set_species(self, value: str) -> None:
        """Retain unlisted historical metadata until the operator chooses a species."""
        while self.species.count() > len(SPECIES):
            self.species.removeItem(self.species.count() - 1)
        selected = next(
            (name for name in SPECIES if name.casefold() == value.casefold()), value
        )
        if selected and selected not in SPECIES:
            self.species.addItem(selected)
            model = self.species.model()
            assert isinstance(model, QStandardItemModel)
            item = model.item(self.species.count() - 1)
            assert item is not None
            item.setEnabled(False)
        self.species.setCurrentIndex(self.species.findText(selected))

    def valid_subject(self) -> bool:
        if not self.subject_id.hasAcceptableInput():
            self.log_console.appendPlainText(
                "Subject ID must contain exactly 4 digits (e.g. 0001)."
            )
            self.subject_id.setFocus()
            return False
        if self.species.currentText() and self.species.currentText() not in SPECIES:
            self.log_console.appendPlainText(
                "Select a species from the dropdown before Setup."
            )
            self.species.setFocus()
            return False
        return True

    def setup(self) -> None:
        if self.view.phase == Phase.ENDED:
            self.request_action("New session")
            return
        if self.can_request("Setup") and not self.valid_subject():
            return
        history = self.subject_history() if self.can_request("Setup") else None
        if history is not None and history.same_experiment_today:
            self.confirm_subject_reuse(history)
        else:
            self.request_action("Setup")

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
        if self.reuse_dialog is not None and not self.can_request("Setup"):
            self.reuse_dialog.reject()
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
            editor.setEnabled(view.can_edit_session)
        self.render_hud()
        for name, status in (
            ("Cameras", view.camera_status),
            ("Visual stimulus", view.stimulus_status),
            ("Tracking", view.tracking_status),
        ):
            self.backend_indicators[name].set_status(status)

    def render_hud(self) -> None:
        """Refresh presentation from the current view without touching controls."""
        view = self.view
        rows = (
            ("STATUS", view.outcome if view.outcome != "—" else view.phase.value),
            (
                "TRIAL",
                f"{view.trial_index}/{view.trial_count}" if view.trial_count else "—",
            ),
            (
                "TRIAL TIME",
                f"{duration(view.elapsed_s)} / {duration(view.trial_duration_s)}",
            ),
            (
                "TOTAL TIME",
                f"{duration(view.total_elapsed_s)} / {duration(view.total_duration_s)}",
            ),
        )
        self.status_column.set_rows((rows[0], None, *rows[1:]))
