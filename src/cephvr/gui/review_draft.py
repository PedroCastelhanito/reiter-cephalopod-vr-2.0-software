"""Local review-only draft persistence, separate from E07 controller history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QIODevice, QSaveFile
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit

from cephvr.gui.protocol_document import TrialDraft
from cephvr.gui.protocol_history import EditHistory
from cephvr.gui.window import DashboardWindow
from cephvr.visual_stimulus.config.models.program_model import parse_program_json
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES

_LIMIT = 32 * 1024 * 1024
_DASHBOARD = (
    "subject_id",
    "species",
    "age",
    "subject_size",
    "experiment",
    "condition",
    "output_root",
)


def draft_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config/review_draft.json"


def save_review_draft(window: DashboardWindow, path: Path) -> None:
    """Atomically retain only local review settings; never mark them accepted."""
    editor = window.protocol.editor
    if not editor.flush_parameters():
        raise ValueError("Finish or correct the current trial edit before closing")
    dashboard = window.dashboard
    cameras = window.devices.cameras
    mcu = window.devices.microcontroller
    projectors = window.devices.projectors
    spike = window.devices.spikeglx
    data = {
        "format_version": 1,
        "dashboard": {key: getattr(dashboard, key).text() for key in _DASHBOARD}
        | {"sex": dashboard.sex.currentText()},
        "cameras": [
            {
                "serial": camera.serial,
                "role": camera.role,
                "enabled": camera.enabled,
                "values": dict(camera.values),
                "record": window.recordings.record[camera.key].isChecked(),
                "pin": mcu.pins.get(camera.key, ""),
            }
            for camera in cameras.drafts
        ],
        "microcontroller": {
            "port": mcu.port.currentData() or "",
            "trial_pin": mcu.trial_pin.text(),
            "trial_enabled": mcu.enable_controls["trial-state"].isChecked(),
            "flip_pin": mcu.flip_pin.text(),
            "flip_enabled": mcu.enable_controls["projector-flip"].isChecked(),
        },
        "recordings": {
            "stimulus": window.recordings.record["stimulus"].isChecked(),
            "velocities": window.recordings.velocities.isChecked(),
        },
        "protocol": {
            "mode": window.protocol.session_mode.currentText(),
            "assets_root": window.protocol.assets.folders["root"].editor.text(),
            "selected_trial": editor.index,
            "trials": [
                {
                    "name": trial.name,
                    "path": trial.path,
                    "program": trial.program.model_dump_json(),
                }
                for trial in editor.drafts
            ],
        },
        "projectors": {
            "assignments": dict(projectors.assignments),
            "participation": dict(projectors.participation),
            "rig": {
                key: field.text() for key, field in projectors.rig_editor.fields.items()
            },
            "projection": {
                key: field.text()
                for key, field in projectors.rig_editor.projection_fields.items()
            },
            "distances": {
                key: field.text()
                for key, field in projectors.rig_editor.screen_distances.items()
            },
            "screens": {
                face: dict(values)
                for face, values in projectors.screen_editor.drafts.items()
            },
            "pulse": {
                "enabled": projectors.timing.pulse.isChecked(),
                "target": projectors.timing.target.currentData() or "",
                "mode": projectors.timing.mode.currentText(),
                "fields": {
                    key: field.text() for key, field in projectors.timing.fields.items()
                },
            },
        },
        "spikeglx": {
            "pairing": spike.pairing.isChecked(),
            "host": _line(spike.editors[0]).text(),
            "port": _line(spike.editors[1]).text(),
            "rows": {
                key: {
                    "signal": signal.text(),
                    "stream": stream.currentText(),
                    "index": index.text(),
                    "channel": channel.text(),
                    "enabled": spike.enable_controls[key].isChecked(),
                }
                for key, (signal, stream, index, channel) in spike.rows.items()
                if isinstance(signal, (QLabel, QLineEdit))
                and isinstance(stream, QComboBox)
                and isinstance(index, QLineEdit)
                and isinstance(channel, QLineEdit)
            },
        },
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(payload) > _LIMIT:
        raise ValueError("Review draft exceeds its 32 MiB save limit")
    output = QSaveFile(str(path))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if output.write(payload) != len(payload):
        output.cancelWriting()
        raise OSError(output.errorString())
    if not output.commit():
        raise OSError(output.errorString())


def load_review_draft(window: DashboardWindow, path: Path) -> bool:
    """Restore the last local review draft after hardware inventory is populated."""
    if not path.exists():
        return False
    raw = path.read_bytes()
    if len(raw) > _LIMIT:
        raise ValueError("Review draft exceeds its 32 MiB load limit")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or type(data.get("format_version")) is not int
        or data["format_version"] != 1
    ):
        raise ValueError("Review draft format is unsupported")
    protocol = data["protocol"]
    trials = [
        TrialDraft(
            item["name"],
            parse_program_json(item["program"], max_bytes=DEFAULT_DOCUMENT_BYTES),
            item["path"],
        )
        for item in protocol["trials"]
    ]
    if not trials:
        raise ValueError("Review draft has no trial")
    _restore(window, data, trials)
    return True


def _restore(
    window: DashboardWindow, data: dict[str, Any], trials: list[TrialDraft]
) -> None:
    dashboard = window.dashboard
    for key in _DASHBOARD:
        getattr(dashboard, key).setText(data["dashboard"][key])
    dashboard.sex.setCurrentText(data["dashboard"]["sex"])

    cameras = window.devices.cameras
    saved_cameras = {item["serial"]: item for item in data["cameras"]}
    mcu = window.devices.microcontroller
    for draft in cameras.drafts:
        item = saved_cameras.get(draft.serial)
        if item is None:
            continue
        draft.role = item["role"]
        draft.enabled = item["enabled"]
        draft.values = dict(item["values"])
        mcu.pins[draft.key] = item["pin"]
    cameras.populate_inventory()
    if cameras.drafts:
        cameras.table.selectRow(0)
    cameras.drafts_changed.emit()
    window.devices.sync_cameras()
    for draft in cameras.drafts:
        item = saved_cameras.get(draft.serial)
        if item is not None:
            window.recordings.record[draft.key].setChecked(item["record"])
    window.recordings.record["stimulus"].setChecked(data["recordings"]["stimulus"])
    window.recordings.velocities.setChecked(data["recordings"]["velocities"])
    selected_port = data["microcontroller"]["port"]
    mcu.set_saved_pins(
        selected_port,
        data["microcontroller"]["trial_pin"],
        data["microcontroller"]["trial_enabled"],
        data["microcontroller"]["flip_pin"],
        data["microcontroller"]["flip_enabled"],
    )

    page = window.protocol
    page.assets.folders["root"].editor.setText(data["protocol"]["assets_root"])
    page.session_mode.setCurrentText(data["protocol"]["mode"])
    editor = page.editor
    editor.trials.blockSignals(True)
    editor.drafts = trials
    editor.histories = [EditHistory() for _ in trials]
    editor.index = min(max(0, data["protocol"]["selected_trial"]), len(trials) - 1)
    editor.node_index = 0
    editor.scope = ()
    editor.selected_paths = ()
    editor.trials.clear()
    editor.trials.addItems([trial.name for trial in trials])
    editor.trials.setCurrentRow(editor.index)
    editor.trials.blockSignals(False)
    editor.render_selection()

    projectors = window.devices.projectors
    saved_projectors = data["projectors"]
    projectors.assignments.update(saved_projectors["assignments"])
    projectors.participation.update(saved_projectors["participation"])
    projectors.request("Refresh displays")
    for key, field in projectors.rig_editor.fields.items():
        field.setText(saved_projectors["rig"].get(key, ""))
    for key, field in projectors.rig_editor.projection_fields.items():
        field.setText(saved_projectors["projection"].get(key, ""))
    for key, field in projectors.rig_editor.screen_distances.items():
        field.setText(saved_projectors["distances"].get(key, ""))
    for (face, key), field in projectors.screen_editor.fields.items():
        field.setText(saved_projectors["screens"].get(face, {}).get(key, ""))
    for (face, key), control in projectors.calibration.controls.items():
        value = saved_projectors["screens"].get(face, {}).get(key, "")
        if isinstance(control, QCheckBox):
            control.setChecked(value == "True")
        elif isinstance(control, QLineEdit):
            control.setText(value)
    pulse = saved_projectors["pulse"]
    projectors.timing.pulse.setChecked(pulse["enabled"])
    projectors.timing.mode.setCurrentText(pulse["mode"])
    projectors.timing.target.setCurrentIndex(
        projectors.timing.target.findData(pulse["target"])
    )
    for key, field in projectors.timing.fields.items():
        field.setText(pulse["fields"].get(key, ""))
    projectors.update_geometry()

    spike = window.devices.spikeglx
    spike.pairing.setChecked(data["spikeglx"]["pairing"])
    _line(spike.editors[0]).setText(data["spikeglx"]["host"])
    _line(spike.editors[1]).setText(data["spikeglx"]["port"])
    for key, item in data["spikeglx"]["rows"].items():
        if key not in spike.rows and key.startswith("custom:"):
            spike.add_row(key, "Other input", custom=True)
        if key not in spike.rows:
            continue
        signal, stream, index, channel = spike.rows[key]
        if isinstance(signal, QLineEdit):
            signal.setText(item["signal"])
        if isinstance(stream, QComboBox):
            stream.setCurrentText(item["stream"])
        _line(index).setText(item["index"])
        _line(channel).setText(item["channel"])
        spike.enable_controls[key].setChecked(item["enabled"])
        if key.startswith("custom:"):
            spike.custom_count = max(spike.custom_count, int(key.split(":", 1)[1]))
    spike.refresh_controls()


def _line(widget: object) -> QLineEdit:
    if not isinstance(widget, QLineEdit):
        raise TypeError("Review draft field is not a text editor")
    return widget
