"""Dashboard presentation, with no transport, SDK or experiment ownership."""

from datetime import date

from PyQt6.QtCore import QRegularExpression, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator, QStandardItemModel
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QStackedLayout,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import (
    Card,
    StatusColumn,
    StatusIndicator,
    combo,
    field,
)
from cephvr.gui.devices_rail import DeviceRail
from cephvr.gui.dialogs import StopDialog, SubjectReuseDialog
from cephvr.gui.formatting import duration, hud_grid
from cephvr.gui.layouts import ResponsiveColumns, column
from cephvr.gui.paths import DirectoryField
from cephvr.gui.previews import PreviewWorkspace
from cephvr.gui.recent_values import RecentValues, suggest_values
from cephvr.gui.subject_history import SubjectSessions, find_subject_sessions
from cephvr.gui.system_controls import SystemControls
from cephvr.gui.theme import SIZES, retro_console
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


# Phases after Start is pressed; the preview workspace replaces the form for these.
RUNTIME_PHASES = frozenset(
    {Phase.STARTING, Phase.RUNNING, Phase.STOPPING, Phase.FINALIZING}
)


class Dashboard(QWidget):
    action_requested = pyqtSignal(str)
    preview_requested = pyqtSignal(str, bool)
    runtime_layout_shown = pyqtSignal()
    layout_switched = pyqtSignal()

    def __init__(
        self, *, sample: bool = False, settings: QSettings | None = None
    ) -> None:
        super().__init__()
        left, left_layout = column()
        self.left_layout = left_layout
        right = StatusColumn()
        self.status_column = right
        self.form = ResponsiveColumns(left, right)
        self.columns = self.form.columns
        self.scrollers = self.form.scrollers
        self.config_scroll = self.form.config_scroll
        self.view = DashboardView()
        self.stop_dialog: StopDialog | None = None
        self.runtime_layout = False
        self.session_running = False
        self.preview_workspace = PreviewWorkspace(self, settings)
        self.preview_workspace.visibility_requested.connect(self.preview_requested.emit)
        # Configure/Monitor follow session start/end; the operator may switch anytime.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SIZES.card_gap)
        self.view_tabs = QTabBar()
        self.view_tabs.setDrawBase(False)
        self.view_tabs.setExpanding(False)
        for title in ("Configure", "Monitor"):
            self.view_tabs.addTab(title)
        self.view_tabs.setAccessibleName("Dashboard view")
        self.view_tabs.currentChanged.connect(
            lambda index: self.set_runtime_layout(index == 1)
        )
        outer.addWidget(self.view_tabs, 0, Qt.AlignmentFlag.AlignLeft)
        pages_host = QWidget()
        self.rail = DeviceRail(
            ("Configure", "Monitor"), {}, icons=("configure", "monitor")
        )
        self.rail.setAccessibleName("Dashboard navigation")
        self.rail.chosen.connect(
            lambda index, section: self.view_tabs.setCurrentIndex(index)
        )
        self.rail.show_position(0, -1)
        self.side_rail = True
        self.rail.setParent(self)
        self.rail.hide()
        outer.addWidget(pages_host, 1)
        self.pages = QStackedLayout(pages_host)
        self.pages.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.form)
        self.pages.addWidget(self.preview_workspace)
        self.session_controls = self.build_controls()
        self.subject_card = self.build_subject(sample)
        self.install_subject_helpers(settings)
        for card in (self.session_controls, self.subject_card):
            left_layout.addWidget(card)
        left_layout.addStretch()
        self.hud_card = right.hud_card
        self.log_card = right.log_card
        self.runtime_console = right.hud
        self.runtime_console.setToolTip(
            "Total time is progress through the planned trials and gaps; "
            "it excludes setup and finalization overhead. Unresolved timing shows —."
        )
        self.preview_workspace.hud.setToolTip(self.runtime_console.toolTip())
        self.log_console = right.console
        log_document = self.log_console.document()
        assert log_document is not None
        self.log_console.textChanged.connect(
            lambda: self.preview_workspace.log_tail.show_tail(log_document)
        )
        self.preview_workspace.log_tail.show_tail(log_document)
        self.apply_view(self.view)

    @property
    def mode(self) -> str:
        """Column arrangement of the form (wide or stacked)."""
        return self.form.mode

    def build_controls(self) -> SystemControls:
        controls = SystemControls()
        status_row = QHBoxLayout()
        status_row.setSpacing(SIZES.field_x_gap)
        self.backend_indicators = {}
        for name in ("Cameras", "Visual stimulus", "Tracking"):
            indicator = StatusIndicator(name)
            self.backend_indicators[name] = indicator
            status_row.addWidget(indicator, 1)
        controls.body.insertLayout(1, status_row)
        self.command_buttons = controls.command_buttons
        controls.action_requested.connect(self.control_action)
        return controls

    def control_action(self, action: str) -> None:
        if action == "Start" and self.view.phase in {
            Phase.CONFIGURATION,
            Phase.SETTING_UP,
            Phase.ENDED,
        }:
            self.setup()
        elif action == "Stop":
            self.stop()
        else:
            self.request_action(action)

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
            and (action not in {"Setup", "Start", "New session"} or view.can_edit)
            and (view.connected or view.sample)
        )

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
        self.preview_workspace.apply_views(
            view.previews, allowed=view.has_control and (view.connected or view.sample)
        )
        setup_mode = view.phase in {Phase.CONFIGURATION, Phase.SETTING_UP, Phase.ENDED}
        primary_action = (
            ("New session" if view.phase == Phase.ENDED else "Setup")
            if setup_mode
            else "Start"
        )
        primary = self.session_controls.command_buttons["Start"]
        primary.setText("Setup" if setup_mode else "Start")
        primary.setEnabled(self.can_request(primary_action))
        primary.setToolTip(
            "Return to Configuration for a new session."
            if view.phase == Phase.ENDED
            else "Prepare a session."
            if setup_mode
            else "Start the prepared session."
        )
        stop = self.session_controls.command_buttons["Stop"]
        stop.setEnabled(self.can_request("Cancel Setup") or bool(self.stop_choices()))
        stop.setToolTip(
            "Cancel setup and return to Configuration."
            if self.can_request("Cancel Setup")
            else "Choose Stop now or Stop after trial."
        )
        if self.stop_dialog is not None:
            self.stop_dialog.update_actions(self.stop_choices())
        for editor in self.subject_editors:
            editor.setEnabled(view.can_edit_session)
        running = view.phase in RUNTIME_PHASES
        if running != self.session_running:
            # Only session start/end switch views; a manual choice otherwise stands.
            self.session_running = running
            self.set_runtime_layout(running)
        self.render_hud()
        for name, status in (
            ("Cameras", view.camera_status),
            ("Visual stimulus", view.stimulus_status),
            ("Tracking", view.tracking_status),
        ):
            self.backend_indicators[name].set_status(status)

    def set_side_rail(self, enabled: bool) -> None:
        self.side_rail = enabled
        self.view_tabs.setVisible(not enabled)

    def set_runtime_layout(self, active: bool) -> None:
        """Show the preview workspace from Start until the session ends.

        The Dashboard's own System controls card moves between the form column and
        the workspace's top row, so its state and command wiring are never duplicated.
        """
        if active == self.runtime_layout:
            return
        self.runtime_layout = active
        self.view_tabs.blockSignals(True)
        self.view_tabs.setCurrentIndex(1 if active else 0)
        self.view_tabs.blockSignals(False)
        self.rail.show_position(1 if active else 0, -1)
        controls = self.session_controls
        if active:
            self.left_layout.removeWidget(controls)
            # Match the HUD/Console row height; content stays at the top.
            controls.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            controls.body.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.preview_workspace.top.addWidget(controls, 0, 0)
            self.pages.setCurrentWidget(self.preview_workspace)
            self.runtime_layout_shown.emit()
        else:
            self.preview_workspace.top.removeWidget(controls)
            controls.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
            )
            controls.body.setAlignment(Qt.AlignmentFlag(0))
            self.left_layout.insertWidget(0, controls)
            self.pages.setCurrentWidget(self.form)
        self.layout_switched.emit()

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
            ("OUTPUT DIR", view.output_directory or "—"),
        )
        self.status_column.set_rows((rows[0], None, *rows[1:]))
        hud = self.preview_workspace.hud
        hud.setPlainText(
            hud_grid(tuple((row,) for row in rows[:4]), retro=retro_console(hud))
        )
