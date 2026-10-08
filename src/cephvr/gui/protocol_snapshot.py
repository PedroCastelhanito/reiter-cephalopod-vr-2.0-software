"""Portable complete protocol schedules; canonical single-program imports remain valid."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cephvr.gui.configuration_files import JSON, envelope, fields, text
from cephvr.gui.protocol_document import TrialDraft, blank_program
from cephvr.gui.protocol_history import EditHistory
from cephvr.visual_stimulus.config.models.program_model import parse_program_json
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES

if TYPE_CHECKING:
    from cephvr.gui.protocol import ProtocolPage

FORMAT = "cephvr-protocol-config"
TRIAL_KEYS = {
    "name",
    "path",
    "program",
    "stimulus_seed_decimal",
    "gap_after_seconds",
    "arena_boundaries_json",
}


def validate_protocol(value: Any, *, allow_program: bool = False) -> JSON:
    if allow_program and isinstance(value, dict) and "format" not in value:
        program = parse_program_json(
            json.dumps(value), max_bytes=DEFAULT_DOCUMENT_BYTES
        )
        return {
            "format": "cephvr-program-import",
            "program": program.model_dump(mode="json"),
        }
    data = envelope(value, FORMAT, {"mode", "asset_root", "trials", "selected_trial"})
    if data["mode"] not in ("Not set", "Open-loop", "Closed-loop"):
        raise ValueError("Unknown protocol mode")
    text(data["asset_root"], "Asset folder")
    if not isinstance(data["trials"], list):
        raise ValueError("Protocol trials must be an ordered list")
    selected = data["selected_trial"]
    if type(selected) is not int or not (
        selected == -1 if not data["trials"] else 0 <= selected < len(data["trials"])
    ):
        raise ValueError("Selected trial is outside the schedule")
    for number, raw in enumerate(data["trials"], 1):
        trial = fields(raw, TRIAL_KEYS, f"Trial {number}")
        for key in TRIAL_KEYS - {"program"}:
            text(trial[key], f"Trial {number} {key}")
        parse_program_json(
            json.dumps(trial["program"]), max_bytes=DEFAULT_DOCUMENT_BYTES
        )
        if trial["arena_boundaries_json"]:
            from cephvr.visual_stimulus.config.models.program_model import (
                TrialArenaBoundaries,
            )

            TrialArenaBoundaries.model_validate_json(trial["arena_boundaries_json"])
    return data


def capture_protocol(page: ProtocolPage) -> JSON:
    if not page.editor.flush_parameters():
        raise ValueError("Finish or correct the current trial edit before saving")
    if not page._schedule_empty:
        page.save_schedule_fields()
    return {
        "format": FORMAT,
        "version": 1,
        "mode": page.session_mode.currentText(),
        "asset_root": page.assets.folders["root"].editor.text(),
        "selected_trial": -1 if page._schedule_empty else page.editor.index,
        "trials": []
        if page._schedule_empty
        else [
            {
                "name": trial.name,
                "path": trial.path,
                "program": trial.program.model_dump(mode="json"),
                "stimulus_seed_decimal": trial.stimulus_seed_decimal,
                "gap_after_seconds": trial.gap_after_seconds,
                "arena_boundaries_json": trial.arena_boundaries_json,
            }
            for trial in page.editor.drafts
        ],
    }


def restore_protocol(page: ProtocolPage, data: JSON) -> None:
    if data["format"] == "cephvr-program-import":
        page.editor.set_program(
            parse_program_json(
                json.dumps(data["program"]), max_bytes=DEFAULT_DOCUMENT_BYTES
            )
        )
        return
    drafts = [
        TrialDraft(
            trial["name"],
            parse_program_json(
                json.dumps(trial["program"]), max_bytes=DEFAULT_DOCUMENT_BYTES
            ),
            trial["path"],
            trial["stimulus_seed_decimal"],
            trial["gap_after_seconds"],
            trial["arena_boundaries_json"],
        )
        for trial in data["trials"]
    ]
    page.session_mode.setCurrentText(data["mode"])
    page.assets.folders["root"].editor.setText(data["asset_root"])
    editor = page.editor
    editor.drafts = drafts or [TrialDraft("Add a trial", blank_program())]
    editor.histories = [EditHistory() for _ in editor.drafts]
    editor.trials.blockSignals(True)
    editor.trials.clear()
    editor.trials.addItems([draft.name for draft in editor.drafts])
    editor.index = max(0, data["selected_trial"])
    editor.node_index, editor.scope, editor.selected_paths = 0, (), ()
    editor.trials.setCurrentRow(editor.index)
    editor.trials.blockSignals(False)
    editor.render_selection()
    page.load_schedule_fields(editor.index)
    editor.changed.emit()
    page._schedule_empty = editor.configuration_schedule_empty = not bool(drafts)
