"""Portable complete protocol schedules; canonical single-program imports remain valid."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from cephvr.gui.configuration_files import JSON, envelope, fields, text
from cephvr.gui.protocol_batches import grouped_program
from cephvr.gui.protocol_document import TrialDraft, blank_program
from cephvr.gui.protocol_history import EditHistory
from cephvr.visual_stimulus.config.categories import CATEGORY_LABELS
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
    keys = {"mode", "asset_root", "trials", "selected_trial"}
    if isinstance(value, dict) and "category_templates" in value:
        keys.add("category_templates")
    data = deepcopy(envelope(value, FORMAT, keys))
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
    templates = data.get("category_templates", {})
    if isinstance(templates, dict):
        legacy_active = any(
            isinstance(trial, dict)
            and isinstance(trial.get("program"), dict)
            and trial["program"].get("category") == "texture_drift"
            for trial in data["trials"]
        )

        def canonical_trials(trials: Any) -> Any:
            if not isinstance(trials, list):
                return trials
            result = deepcopy(trials)
            for trial in result:
                if isinstance(trial, dict) and isinstance(trial.get("program"), dict):
                    trial["program"] = parse_program_json(
                        json.dumps(trial["program"]), max_bytes=DEFAULT_DOCUMENT_BYTES
                    ).model_dump(mode="json")
            return result

        if "media_presentation" in templates:
            old_media = templates["media_presentation"]
            other = templates.get("texture_drift", {"trials": data["trials"]})
            if ("texture_drift" in templates or legacy_active) and (
                not isinstance(old_media, dict)
                or not isinstance(other, dict)
                or canonical_trials(old_media.get("trials"))
                != canonical_trials(other.get("trials"))
            ):
                raise ValueError(
                    "This legacy file contains separate Media presentation and Texture drift schedules; "
                    "import each schedule separately before combining them. The file has not been changed."
                )
        if "texture_drift" in templates:
            templates["media_presentation"] = templates.pop("texture_drift")
    categories: set[str | None] = set()
    for number, raw in enumerate(data["trials"], 1):
        trial = fields(raw, TRIAL_KEYS, f"Trial {number}")
        for key in TRIAL_KEYS - {"program"}:
            text(trial[key], f"Trial {number} {key}")
        program = parse_program_json(
            json.dumps(trial["program"]), max_bytes=DEFAULT_DOCUMENT_BYTES
        )
        trial["program"] = program.model_dump(mode="json")
        categories.add(program.category)
        if len(categories) > 1:
            raise ValueError("All trials must use the same protocol category")
        if trial["arena_boundaries_json"]:
            from cephvr.visual_stimulus.config.models.program_model import (
                TrialArenaBoundaries,
            )

            TrialArenaBoundaries.model_validate_json(trial["arena_boundaries_json"])
    templates = data.get("category_templates", {})
    if not isinstance(templates, dict) or any(
        category not in CATEGORY_LABELS for category in templates
    ):
        raise ValueError("Unknown protocol category template")
    for category, template in templates.items():
        fields(template, {"trials", "selected_trial"}, "Category template")
        checked = validate_protocol(
            {key: item for key, item in data.items() if key != "category_templates"}
            | template
        )
        template["trials"] = checked["trials"]
        if any(
            trial["program"].get("category") != category for trial in checked["trials"]
        ):
            raise ValueError("Template trials must use their owning category")
    return data


def capture_protocol(page: ProtocolPage, *, flush: bool = True) -> JSON:
    if flush and not page.editor.flush_parameters():
        raise ValueError("Finish or correct the current trial edit before saving")
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
                "program": trial.exported_program.model_dump(mode="json"),
                "stimulus_seed_decimal": trial.stimulus_seed_decimal,
                "gap_after_seconds": trial.gap_after_seconds,
                "arena_boundaries_json": trial.arena_boundaries_json,
            }
            for trial in page.editor.drafts
        ],
        **(
            {"category_templates": page.category_templates}
            if page.category_templates
            else {}
        ),
    }


def restore_protocol(page: ProtocolPage, data: JSON) -> None:
    if data["format"] == "cephvr-program-import":
        page.import_program(
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
    for draft in drafts:
        draft.group_for_editing()
    page.category_templates = dict(data.get("category_templates", {}))
    page.session_mode.setCurrentText(data["mode"])
    page.assets.folders["root"].editor.setText(data["asset_root"])
    editor = page.editor
    editor.drafts = drafts or [
        TrialDraft("Add a trial", grouped_program(blank_program()))
    ]
    editor.histories = [EditHistory() for _ in editor.drafts]
    editor.trials.blockSignals(True)
    editor.trials.clear()
    editor.trials.addItems([draft.name for draft in editor.drafts])
    editor.index = max(0, data["selected_trial"])
    editor.node_index, editor.scope, editor.selected_paths = 0, (), ()
    editor.trials.setCurrentRow(editor.index)
    editor.trials.blockSignals(False)
    editor.render_selection()
    editor.changed.emit()
    page._schedule_empty = editor.configuration_schedule_empty = not bool(drafts)
