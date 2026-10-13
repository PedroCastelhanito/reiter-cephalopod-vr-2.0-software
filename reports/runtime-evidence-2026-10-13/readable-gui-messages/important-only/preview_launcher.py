"""Interactive sample GUI using production warning and log widgets."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication, QPushButton

from cephvr.control.v1 import types_pb2 as pb
from cephvr.gui.layouts import fit_window_to_screen
from cephvr.gui.main import ManagedGui
from cephvr.gui.managed_prompts import ManagedPrompts
from cephvr.gui.managed_status import has_retained_review
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow

app = QApplication([])
app.setApplicationName('CephVR message preview')
apply_theme(app)
settings_dir = TemporaryDirectory(prefix='cephvr-message-preview-')
settings = QSettings(str(Path(settings_dir.name) / 'preview.ini'), QSettings.Format.IniFormat)
window = DashboardWindow(sample=True, settings=settings)
window.setWindowTitle('CephVR — Warning and log examples · local preview')
console = window.dashboard.log_console
console.clear()
manager = SimpleNamespace(
    window=window,
    prompts=SimpleNamespace(operation_finished=lambda *_: None),
)
command = str(uuid4())
ManagedGui.command_admitted(manager, 'Setup', command)
ManagedGui.operation_finished(manager, 'Setup', command, 'completed', 'Completed.')
command = str(uuid4())
ManagedGui.command_admitted(manager, 'open_display_calibration', command)
ManagedGui.operation_finished(manager, 'open_display_calibration', command, 'failed',
    '<unknown> renderer failed to initialize.\nCleanup remains unconfirmed; review before retrying.')
console.append_entry('Camera preview stopped.',
    f'Action: ExecuteCameraCommand\nCommand ID: {uuid4()}\nStatus: completed\nMessage: Preview stopped and camera resources released.')
console.append_entry('MCU connection unavailable: reconnect the controller.',
    'Action: mcu\nStatus: failed\nMessage: Controller endpoint unavailable; connection state is unconfirmed.')
console.append_entry('Examples only — right-click a log entry to view or copy details.',
    'This local preview uses synthetic events and has no backend connection.')

state = pb.Snapshot(controller_generation=str(uuid4()), retained_truncated=True)
state.errors.add(error_id=str(uuid4()), failure=pb.Failure(
    code='renderer_initialization_failed', message='Renderer initialization failed; cleanup needs review.'))
state.warnings.add(warning_id=str(uuid4()), message='MCU connection is unavailable. Reconnect before starting an experiment.')
prompt = state.prompts.add(prompt_id=str(uuid4()), explanation='A camera stopped recording. Choose how to continue.')
prompt.permitted_choices.extend(['Continue session', 'Abort session'])
failed = state.operations.add(command='OpenDisplayCalibration', complete=True, succeeded=False)
failed.context.command_id = str(uuid4())
failed.failure.CopyFrom(pb.Failure(code='cleanup_unconfirmed', message='<unknown> renderer cleanup remains unconfirmed.'))
pending = state.operations.add(command='ExecuteCameraCommand', progress='Waiting for camera release confirmation.')
pending.context.command_id = str(uuid4())
for name in ['SetupSession', 'SaveConfigurationHistory', 'ExecuteCameraCommand']:
    operation = state.operations.add(command=name, complete=True, succeeded=True)
    operation.context.command_id = str(uuid4())
prompts = ManagedPrompts(window, queue_response=lambda *_: False,
    acknowledged=lambda *_: None, log=console.appendPlainText)
review_button = QPushButton('Review controller history')
review_button.clicked.connect(prompts.review_retained_summary)
window.page_header.layout().addWidget(review_button)
fit_window_to_screen(window)
window.show()
window.raise_()
window.activateWindow()

def show_examples():
    prompts.update(state, require_acknowledgement=has_retained_review(state), can_respond=False, connection_epoch=1)
    print(f'PREVIEW_READY window_visible={window.isVisible()} warning_visible={prompts.retained_dialog.isVisible()}', flush=True)

def show_routine_history():
    quiet = pb.Snapshot(controller_generation=state.controller_generation)
    quiet.configuration.revision = 1
    validation = quiet.configuration.edit_validation.add(
        configuration_revision=1, component='acquisition', completed=True, valid=True)
    validation.issues.add(component='acquisition', field_path='optional_metadata',
        failure=pb.Failure(message='Optional preview metadata is unavailable.'))
    warning = quiet.warnings.add(warning_id='configuration:1:acquisition:nonfatal',
        component='acquisition', message='Configuration has nonfatal preparation warnings')
    warning.issues.extend(validation.issues)
    quiet.recoveries.add(attempt_id=str(uuid4()), outcome=pb.RECOVERY_OUTCOME_COMPLETED,
        completion_monotonic_ns=123, progress='Cleanup completed successfully.')
    quiet.operations.add(command='SaveConfigurationHistory', complete=True, succeeded=True)
    needed = has_retained_review(quiet)
    prompts.update(quiet, require_acknowledgement=needed, can_respond=False, connection_epoch=1)
    print(f'PREVIEW_READY window_visible={window.isVisible()} automatic_review={needed} warning_visible={prompts.retained_dialog is not None and prompts.retained_dialog.isVisible()}', flush=True)

important_button = QPushButton('Show important warning examples')
important_button.clicked.connect(show_examples)
window.page_header.layout().addWidget(important_button)
QTimer.singleShot(250, show_routine_history)
app.aboutToQuit.connect(settings_dir.cleanup)
raise SystemExit(app.exec())
