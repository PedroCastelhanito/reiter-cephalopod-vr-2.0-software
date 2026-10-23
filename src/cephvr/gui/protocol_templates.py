"""Category-local trial templates, separate from shared session settings."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from cephvr.gui.protocol_document import blank_program
from cephvr.visual_stimulus.config.categories import Category, suggested_category
from cephvr.visual_stimulus.config.models.program_model import parse_program_json
from cephvr.visual_stimulus.config.models.schema_common import DEFAULT_DOCUMENT_BYTES

if TYPE_CHECKING:
    from cephvr.gui.protocol import ProtocolPage


def switch_category(page: ProtocolPage, category: Category) -> None:
    """Remember the departing schedule and restore or initialize the target."""
    from cephvr.gui.protocol_snapshot import capture_protocol, restore_protocol

    editor = page.editor
    current = editor.program.category
    if current == category:
        return
    snapshot = capture_protocol(page)
    templates = dict(page.category_templates)
    if current is None:
        suggestions = {suggested_category(draft.program) for draft in editor.drafts}
        current = next(
            candidate
            for candidate in ("navigation_3d", "texture_drift", "media_presentation")
            if candidate in suggestions
        )
        snapshot["trials"] = [
            dict(trial, program=dict(trial["program"], category=current))
            for trial in snapshot["trials"]
        ]
    if current is not None:
        templates[current] = {
            key: snapshot[key] for key in ("trials", "selected_trial")
        }
    target = page.category_templates.get(category)
    if target is not None:
        restore_protocol(page, dict(snapshot, **target, category_templates=templates))
    else:
        try:
            programs = [
                parse_program_json(
                    draft.program.model_copy(
                        update={"category": category}
                    ).model_dump_json(),
                    max_bytes=DEFAULT_DOCUMENT_BYTES,
                )
                for draft in editor.drafts
            ]
        except ValueError:
            trial = {
                "name": "Trial 1",
                "path": "",
                "program": blank_program()
                .model_copy(update={"category": category})
                .model_dump(mode="json"),
                "stimulus_seed_decimal": "",
                "gap_after_seconds": "",
                "arena_boundaries_json": "",
            }
            restore_protocol(
                page,
                dict(
                    snapshot,
                    trials=[trial],
                    selected_trial=0,
                    category_templates=templates,
                ),
            )
        else:
            editor.histories[editor.index].push(
                replace(
                    editor.snapshot(),
                    protocol_categories=tuple(
                        draft.program.category for draft in editor.drafts
                    ),
                )
            )
            for draft, program in zip(editor.drafts, programs, strict=True):
                draft.program = program
            page.category_templates = templates
            editor.render_selection()
            editor.changed.emit()
    page.message.hide()
