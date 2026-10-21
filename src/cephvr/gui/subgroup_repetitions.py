"""Compile GUI rules into compact random-access source declarations."""

from secrets import token_hex

from cephvr.gui.arena_movement import patch_arena
from cephvr.gui.program_editing import data_nodes, node_at, validate
from cephvr.gui.projector_layers import layers_for
from cephvr.visual_stimulus.config.models.program_model import Epoch, Group, Program
from cephvr.visual_stimulus.config.models.repetition import RepetitionRule
from cephvr.visual_stimulus.config.repetition_values import resolve_repetition


def rebuild_repetitions(program: Program, scope: tuple[int, ...]) -> Program:
    """Work scales with source members/rules, never enclosing repetitions."""
    group = node_at(program, scope)
    if not isinstance(group, Group):
        return program
    data = program.model_dump(mode="json")
    nodes = data_nodes(data, scope)
    batches: dict[str, list[int]] = {}
    for index, epoch in enumerate(group.body):
        if isinstance(epoch, Epoch) and epoch.batch_id:
            batches.setdefault(epoch.batch_id, []).append(index)
    for positions in batches.values():
        epoch = group.body[positions[0]]
        assert isinstance(epoch, Epoch)
        draft = epoch.subgroup_draft
        if draft is None or any(nodes[i]["repetition_settings"] for i in positions):
            continue
        per_member: dict[int, list[RepetitionRule]] = {i: [] for i in positions}
        updated = []
        for rule in draft.rules:
            if rule.method != 2 or not draft.enabled:
                updated.append(rule)
                continue
            faces = [rule.projector] if rule.projector else list(rule.projectors)
            targets: list[int] = []
            for face in faces:
                layers = layers_for(program, epoch, "" if face == "Rig-wide" else face)
                if rule.layer != -1:
                    if not 0 <= rule.layer < len(layers):
                        raise ValueError("A saved variation target is unavailable")
                    layers = [layers[rule.layer]]
                targets.extend(i for i in layers if i not in targets)
            if not targets:
                raise ValueError("A saved variation target is unavailable")
            key = (
                rule.minimum.strip(),
                rule.maximum.strip(),
                rule.precision.strip(),
                rule.parameter,
                repr((rule.projector, rule.projectors, rule.layer, rule.shared)),
            )
            seed = rule.seed if rule.seed and rule.sample_key == key else token_hex(16)
            updated.append(
                rule.model_copy(update={"seed": seed, "sample_key": key, "samples": ()})
            )
            for offset, position in enumerate(positions):
                for ordinal, layer in enumerate(targets):
                    setting = nodes[position]["settings"][layer]
                    if setting["kind"] == "arena":
                        patch_arena(setting, {rule.parameter: rule.minimum}, data)
                    per_member[position].append(
                        RepetitionRule.model_validate(
                            {
                                "instance_id": setting["instance_id"],
                                "parameter": rule.parameter,
                                "rig_coordinates": rule.rig_coordinates,
                                "rig_angle_version": rule.rig_angle_version,
                                "minimum": rule.minimum,
                                "maximum": rule.maximum,
                                "precision": rule.precision,
                                "seed": seed,
                                "stream": "" if rule.shared else str(ordinal),
                                "offset": offset,
                                "stride": len(positions),
                            }
                        )
                    )
        nodes[positions[0]]["subgroup_draft"] = draft.model_copy(
            update={"rules": tuple(updated)}
        ).model_dump(mode="json")
        for position in positions:
            nodes[position]["repetition_rules"] = [
                r.model_dump(mode="json") for r in per_member[position]
            ]
    result = validate(data)
    # Only the representative occurrence is needed for source editing and colouring.
    for positions in batches.values():
        for position in positions:
            epoch = node_at(result, (*scope, position))
            assert isinstance(epoch, Epoch)
            if epoch.repetition_rules:
                nodes[position]["settings"] = [
                    s.model_dump(mode="json")
                    for s in resolve_repetition(
                        epoch.settings, epoch.repetition_rules, 0
                    )
                ]
    return validate(data)
