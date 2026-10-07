"""Card-based local protocol configuration and canonical timeline editing."""

from decimal import Decimal, InvalidOperation
from pathlib import Path

from PyQt6.QtCore import QIODevice, QSaveFile, Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cephvr.gui.components import Card, button, combo, equal_row_height
from cephvr.gui.layouts import column
from cephvr.gui.notices import FormNotice
from cephvr.gui.protocol_document import TrialDraft, blank_program
from cephvr.gui.protocol_editor import ProtocolEditor
from cephvr.gui.protocol_history import EditHistory
from cephvr.gui.recordings import RecordingsCard
from cephvr.gui.stimulus_assets import StimulusAssetsCard
from cephvr.gui.view import DashboardView
from cephvr.visual_stimulus.config.models.program_model import parse_program_json
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES


class ProtocolPage(QWidget):
    participation_changed = pyqtSignal()

    def __init__(self, recordings: RecordingsCard, *, sample: bool = False) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.config_scroll = QScrollArea()
        self.config_scroll.setWidgetResizable(True)
        self.config_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.config_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content, body = column()
        self.config_scroll.setWidget(content)
        root.addWidget(self.config_scroll)
        top = self.top_grid = QGridLayout()
        top.setSpacing(14)
        body.addLayout(top)
        self.assets = StimulusAssetsCard()
        top.addWidget(
            self.assets,
            0,
            1,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        top.setColumnStretch(0, 3)
        top.setColumnStretch(1, 2)
        self.recordings = recordings
        self.can_edit = False
        self.session_mode = combo(("Not set", "Open-loop", "Closed-loop"))
        self.session_mode.currentTextChanged.connect(self.participation_changed.emit)
        recordings.changed.connect(self.participation_changed.emit)
        self.program_card = Card("Protocol type")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self.session_mode, 1)
        self.load_button = button("Load…")
        self.load_button.clicked.connect(self.choose_load)
        self.save_button = button("Save as…")
        self.save_button.clicked.connect(self.choose_save)
        equal_row_height(self.session_mode, self.load_button, self.save_button)
        toolbar.addWidget(self.load_button, alignment=Qt.AlignmentFlag.AlignBottom)
        toolbar.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignBottom)
        self.program_card.body.addLayout(toolbar)
        self.message = FormNotice()
        self.message.hide()
        self.program_card.body.addWidget(self.message)
        top.addWidget(
            self.program_card,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        self.editor = ProtocolEditor(sample=sample)
        self._schedule_empty = False
        self.editor.changed.connect(self.mark_changed)
        self.editor.trials.currentRowChanged.connect(self.load_schedule_fields)
        schedule = QHBoxLayout()
        self.seed_editor = QLineEdit()
        self.seed_editor.setPlaceholderText("Seed")
        self.gap_editor = QLineEdit()
        self.gap_editor.setPlaceholderText("Gap (s)")
        self.seed_editor.setAccessibleName("Selected trial seed")
        self.gap_editor.setAccessibleName("Gap after selected trial")
        self.seed_editor.setToolTip("Optional nonnegative integer seed for this trial")
        self.gap_editor.setToolTip(
            "Optional nonnegative gap after this trial, in seconds; the final trial has no gap"
        )
        schedule.addWidget(self.seed_editor, 1)
        schedule.addWidget(self.gap_editor, 1)
        self.editor.trial_card.body.insertLayout(0, schedule)
        self.seed_editor.editingFinished.connect(self.save_schedule_fields)
        self.gap_editor.editingFinished.connect(self.save_schedule_fields)
        self.assets.folders["root"].editor.textChanged.connect(
            lambda path: setattr(self.editor.parameters, "asset_root", path)
        )
        self.assets.folders["root"].editor.textChanged.connect(
            self.editor.create_batch.composer.set_asset_root
        )
        self.assets.folders["root"].editor.textChanged.connect(
            self.editor.batch_edit.selection_form.composer.set_asset_root
        )
        self.assets.folders["root"].editor.textChanged.connect(
            lambda path: setattr(self.editor.batch_edit, "asset_root", path)
        )
        self.session_mode.currentTextChanged.connect(self.update_control_mode)
        self.update_control_mode()
        body.addWidget(self.editor, 1)
        self.save_dialog: QFileDialog | None = None
        self.load_dialog: QFileDialog | None = None

    def update_control_mode(self) -> None:
        closed = self.session_mode.currentText() == "Closed-loop"
        self.editor.parameters.set_closed_loop(closed)
        self.editor.create_batch.composer.set_closed_loop(closed)
        self.editor.batch_edit.selection_form.composer.set_closed_loop(closed)

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        wide = self.width() >= 650
        self.top_grid.removeWidget(self.assets)
        self.top_grid.addWidget(
            self.assets,
            0 if wide else 1,
            1 if wide else 0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        self.top_grid.setColumnStretch(1, 2 if wide else 0)

    @property
    def tracking_active(self) -> bool:
        return (
            self.session_mode.currentText() == "Closed-loop"
            or self.recordings.velocities.isChecked()
        )

    def mark_changed(self) -> None:
        self._schedule_empty = False
        self.message.clear()
        self.message.hide()

    def load_schedule_fields(self, index: int) -> None:
        if index < 0 or index >= len(self.editor.drafts):
            self.seed_editor.clear()
            self.gap_editor.clear()
            return
        draft = self.editor.drafts[index]
        for editor, value in (
            (self.seed_editor, draft.stimulus_seed_decimal),
            (self.gap_editor, draft.gap_after_seconds),
        ):
            editor.blockSignals(True)
            editor.setText(value)
            editor.blockSignals(False)

    def save_schedule_fields(self) -> None:
        if not self.can_edit or not (0 <= self.editor.index < len(self.editor.drafts)):
            return
        draft = self.editor.drafts[self.editor.index]
        draft.stimulus_seed_decimal = self.seed_editor.text().strip()
        draft.gap_after_seconds = self.gap_editor.text().strip()
        self.editor.changed.emit()

    def install_configuration(self, configuration: object) -> None:
        """Install only the session protocol fields from an authoritative config."""
        from cephvr.control.v1 import types_pb2 as control_pb

        if not isinstance(configuration, control_pb.ExperimentConfiguration):
            raise TypeError("Expected an ExperimentConfiguration")
        drafts = []
        for index, trial in enumerate(configuration.trials):
            stimulus = trial.stimulus
            try:
                program = parse_program_json(
                    stimulus.program.program_json,
                    max_bytes=DEFAULT_DOCUMENT_BYTES,
                )
            except (ValueError, UnicodeError) as error:
                raise ValueError(
                    f"Trial {index + 1} source is invalid: {error}"
                ) from error
            seed = (
                stimulus.stimulus_seed_decimal
                if stimulus.HasField("stimulus_seed_decimal")
                else ""
            )
            if seed and (
                not seed.isascii() or not seed.isdecimal() or str(int(seed)) != seed
            ):
                raise ValueError(
                    f"Trial {index + 1} seed must be a canonical nonnegative integer"
                )
            drafts.append(
                TrialDraft(
                    f"Trial {index + 1}",
                    program,
                    stimulus.program.logical_source_reference
                    if stimulus.program.HasField("logical_source_reference")
                    else "",
                    seed,
                    "",
                    stimulus.arena_boundaries.boundaries_json
                    if stimulus.HasField("arena_boundaries")
                    else "",
                )
            )
        if not drafts:
            drafts = [TrialDraft("Add a trial", blank_program())]
        seen_gaps: set[int] = set()
        for gap in configuration.gaps:
            if (
                gap.after_trial_number == 0
                or gap.after_trial_number >= len(configuration.trials)
                or gap.after_trial_number in seen_gaps
                or gap.minimum_duration_ns < 0
                or gap.minimum_duration_ns > 2**63 - 1
            ):
                raise ValueError(
                    "Controller gap does not match the ordered trial schedule"
                )
            seen_gaps.add(gap.after_trial_number)
            drafts[gap.after_trial_number - 1].gap_after_seconds = str(
                Decimal(gap.minimum_duration_ns) / Decimal(1_000_000_000)
            )
        mode_text = {
            control_pb.SESSION_MODE_UNSPECIFIED: "Not set",
            control_pb.SESSION_MODE_OPEN_LOOP: "Open-loop",
            control_pb.SESSION_MODE_CLOSED_LOOP: "Closed-loop",
        }.get(configuration.mode)
        if mode_text is None:
            raise ValueError("Controller configuration has an unknown session mode")
        self.session_mode.blockSignals(True)
        self.session_mode.setCurrentText(mode_text)
        self.session_mode.blockSignals(False)
        self.update_control_mode()
        root = configuration.asset_root if configuration.HasField("asset_root") else ""
        self.assets.folders["root"].editor.setText(root)
        self._schedule_empty = not bool(configuration.trials)
        editor = self.editor
        editor.blockSignals(True)
        editor.drafts = drafts
        editor.configuration_schedule_empty = self._schedule_empty
        editor.histories = [EditHistory() for _ in drafts]
        editor.index = editor.node_index = 0
        editor.trials.blockSignals(True)
        editor.trials.clear()
        editor.trials.addItems([draft.name for draft in drafts])
        editor.trials.setCurrentRow(0)
        editor.trials.blockSignals(False)
        editor.render_selection()
        editor.blockSignals(False)
        self.load_schedule_fields(0)

    def apply_schedule(
        self, configuration: object, *, flush_parameters: bool = True
    ) -> None:
        """Replace only mode, asset root, ordered trials and inter-trial gaps."""
        from cephvr.control.v1 import types_pb2 as control_pb

        if not isinstance(configuration, control_pb.ExperimentConfiguration):
            raise TypeError("Expected an ExperimentConfiguration")
        if flush_parameters and not self.editor.flush_parameters():
            raise ValueError(
                "Finish or correct the selected trial's parameter edit first"
            )
        if not self.editor.drafts:
            raise ValueError("Add at least one trial")
        if self._schedule_empty:
            raise ValueError("Add a managed trial before submitting the session")
        if self.session_mode.currentText() == "Not set":
            raise ValueError("Choose an open-loop or closed-loop session mode")
        configuration.mode = (
            control_pb.SESSION_MODE_CLOSED_LOOP
            if self.session_mode.currentText() == "Closed-loop"
            else control_pb.SESSION_MODE_OPEN_LOOP
        )
        root = self.assets.folders["root"].editor.text().strip()
        if root:
            configuration.asset_root = root
        else:
            configuration.ClearField("asset_root")
        del configuration.trials[:]
        del configuration.gaps[:]
        for number, draft in enumerate(self.editor.drafts, start=1):
            trial = configuration.trials.add(trial_number=number)
            trial.stimulus.program.program_json = draft.program.model_dump_json()
            if draft.path:
                trial.stimulus.program.logical_source_reference = draft.path
            seed = draft.stimulus_seed_decimal.strip()
            if seed:
                if not seed.isascii() or not seed.isdecimal() or str(int(seed)) != seed:
                    raise ValueError(
                        f"Trial {number} seed must be a canonical nonnegative integer"
                    )
                trial.stimulus.stimulus_seed_decimal = seed
            if draft.arena_boundaries_json:
                trial.stimulus.arena_boundaries.boundaries_json = (
                    draft.arena_boundaries_json
                )
            gap = draft.gap_after_seconds.strip()
            if gap:
                if number == len(self.editor.drafts):
                    raise ValueError("The final trial cannot have a gap after it")
                try:
                    seconds = Decimal(gap)
                except InvalidOperation as error:
                    raise ValueError(f"Trial {number} gap must be a number") from error
                nanoseconds = seconds * Decimal(1_000_000_000)
                if (
                    not seconds.is_finite()
                    or seconds < 0
                    or nanoseconds != nanoseconds.to_integral_value()
                    or nanoseconds > 2**63 - 1
                ):
                    raise ValueError(
                        f"Trial {number} gap must be nonnegative whole nanoseconds"
                    )
                configuration.gaps.add(
                    after_trial_number=number,
                    minimum_duration_ns=int(nanoseconds),
                )

    def load_program(self, path: str) -> None:
        if not self.can_edit or not path:
            return
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(DEFAULT_DOCUMENT_BYTES + 1)
            program = parse_program_json(
                data.decode("utf-8"), max_bytes=DEFAULT_DOCUMENT_BYTES
            )
        except (OSError, ValueError) as error:
            self.show_error("Cannot load program", error)
            return
        self.editor.drafts[self.editor.index].path = path
        self.editor.set_program(program)
        self.message.hide()

    def show_error(self, title: str, error: Exception) -> None:
        self.message.warn(error, title)
        self.message.show()
        self.message.setToolTip(str(error))

    def choose_load(self) -> None:
        if not self.can_edit:
            return
        if self.load_dialog is not None:
            self.load_dialog.raise_()
            return
        dialog = QFileDialog(self, "Load stimulus program")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("Stimulus programs (*.json)")
        dialog.fileSelected.connect(self.load_program)
        dialog.finished.connect(lambda: setattr(self, "load_dialog", None))
        dialog.finished.connect(dialog.deleteLater)
        self.load_dialog = dialog
        dialog.open()

    def choose_save(self) -> None:
        if not self.can_edit:
            return
        if self.save_dialog is not None:
            self.save_dialog.raise_()
            return
        dialog = QFileDialog(self, "Save stimulus program")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter("Stimulus programs (*.json)")
        dialog.setDefaultSuffix("json")
        dialog.fileSelected.connect(self.save_program)
        dialog.finished.connect(lambda: setattr(self, "save_dialog", None))
        dialog.finished.connect(dialog.deleteLater)
        self.save_dialog = dialog
        dialog.open()

    def save_program(self, path: str) -> None:
        if not self.can_edit or not self.editor.flush_parameters():
            return
        try:
            program = parse_program_json(
                self.editor.program.model_dump_json(), max_bytes=DEFAULT_DOCUMENT_BYTES
            )
            data = program.model_dump_json(indent=2).encode("utf-8")
            if len(data) > DEFAULT_DOCUMENT_BYTES:
                raise ValueError("Formatted protocol exceeds the document byte budget")
            output = QSaveFile(path)
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            if output.write(data) != len(data):
                output.cancelWriting()
                raise OSError(output.errorString())
            if not output.commit():
                raise OSError(output.errorString())
        except (OSError, ValueError) as error:
            self.show_error("Cannot save program", error)
            return
        self.editor.drafts[self.editor.index].path = path
        self.message.status("Trial saved")
        self.message.show()

    def apply_view(self, view: DashboardView) -> None:
        self.assets.apply_view(view)
        self.can_edit = view.can_edit
        if not self.can_edit:
            self.editor.parameters.close_file_dialog()
            self.editor.create_batch.composer.close_file_dialogs()
            self.editor.batch_edit.selection_form.composer.close_file_dialogs()
            batch_picker = self.editor.batch_edit.asset_picker
            if batch_picker.dialog is not None:
                batch_picker.dialog.reject()
            self.editor.close_source_dialog()
            if self.save_dialog is not None:
                self.save_dialog.reject()
            if self.load_dialog is not None:
                self.load_dialog.reject()
        self.program_card.setEnabled(self.can_edit)
        self.editor.setEnabled(self.can_edit)
        self.editor.create_batch.setEnabled(self.can_edit)
        self.editor.batch_edit.setEnabled(self.can_edit)
