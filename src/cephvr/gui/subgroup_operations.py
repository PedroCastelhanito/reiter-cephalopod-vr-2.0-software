"""Atomic subgroup updates that preserve untouched source settings and identities."""

from copy import deepcopy
from typing import Any
from uuid import uuid4

from cephvr.gui.program_editing import (
    data_nodes,
    document_ids,
    node_at,
    unique_id,
    validate,
)
from cephvr.gui.projector_layers import layers_for
from cephvr.gui.stimulus_fades import retime_fades
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Program


def merge_reference(data: dict[str, Any], incoming: dict[str, Any]) -> str:
    """Merge declarations without overwriting siblings' shared definitions."""
    scene_id: str = incoming["sequence"][0]["scene_id"]
    for key, identity in (
        ("assets", "asset_id"),
        ("instances", "instance_id"),
        ("input_channels", "channel_id"),
        ("scenes", "scene_id"),
    ):
        known = {item[identity]: item for item in data[key]}
        for original in incoming[key]:
            item = deepcopy(original)
            old = known.get(item[identity])
            if old == item:
                continue
            if old is not None:
                if key != "scenes":
                    raise ValueError(f"The edit would change a shared {key} definition")
                previous = item[identity]
                item[identity] = unique_id(data, "scene")
                if scene_id == previous:
                    scene_id = item[identity]
            data[key].append(item)
            known[item[identity]] = item
    return scene_id


def patch_value(current: Any, before: Any, after: Any) -> Any:
    """Apply only edited fields; typed function replacements remain atomic."""
    if before == after:
        return deepcopy(current)
    if (
        isinstance(current, dict)
        and isinstance(before, dict)
        and isinstance(after, dict)
        and before.keys() == after.keys() == current.keys()
        and before.get("kind") == after.get("kind") == current.get("kind")
    ):
        result = {k: patch_value(current[k], before[k], after[k]) for k in after}
        if (
            after.get("kind") == "texture"
            and after.get("linked_to") is not None
            and before.get("linked_to") != after["linked_to"]
        ):
            # Linking replaces sampled motion even when the template was stationary.
            for key in ("phase_x", "phase_y", "motion"):
                result[key] = deepcopy(after[key])
        return result
    return deepcopy(after)


def update_subgroup(
    program: Program,
    paths: tuple[tuple[int, ...], ...],
    before: Program,
    reference: Program,
    count: int,
    *,
    variants: Program | None = None,
) -> tuple[Program, tuple[tuple[int, ...], ...]]:
    if (
        not paths
        or count < 1
        or (count > 2000 and (count != len(paths) or variants is not None))
    ):
        raise ValueError("Use 1–2000 epochs in a subgroup")
    scope = paths[0][:-1]
    if any(p[:-1] != scope for p in paths):
        raise ValueError("Select epochs within one group")
    originals: list[Epoch] = []
    for path in paths:
        original = node_at(program, path)
        if not isinstance(original, Epoch):
            raise ValueError("A subgroup contains epochs only")
        originals.append(original)
    identities = {epoch.batch_id for epoch in originals}
    if len(identities) > 1 and (count != len(paths) or variants is not None):
        raise ValueError("Select one subgroup to change its count or variations")
    data = program.model_dump(mode="json")
    incoming = reference.model_dump(mode="json")
    base = before.model_dump(mode="json")["sequence"][0]
    edited = incoming["sequence"][0]
    scene_id = merge_reference(data, incoming)
    old_settings = {s["instance_id"]: s for s in base["settings"]}
    before_epoch, after_epoch = before.sequence[0], reference.sequence[0]
    assert isinstance(before_epoch, Epoch) and isinstance(after_epoch, Epoch)
    duration_changed = before_epoch.duration != after_epoch.duration
    if (
        duration_changed
        and isinstance(before_epoch.duration, Fixed)
        and isinstance(after_epoch.duration, Fixed)
    ):
        retime_fades(
            list(old_settings.values()),
            before_epoch.duration.duration.ns(),
            after_epoch.duration.duration.ns(),
        )
    new_settings = {s["instance_id"]: s for s in edited["settings"]}
    previous_scene = next(s for s in before.scenes if s.scene_id == base["scene_id"])
    edited_scene = next(s for s in reference.scenes if s.scene_id == edited["scene_id"])
    composition_changed = previous_scene != edited_scene
    origins = {
        identity: identity for identity in new_settings if identity in old_settings
    }
    base_epoch, edited_epoch = before.sequence[0], reference.sequence[0]
    assert isinstance(base_epoch, Epoch) and isinstance(edited_epoch, Epoch)
    for index, setting in enumerate(edited_epoch.settings):
        if setting.instance_id in origins:
            continue
        for face in surfaces(setting.model_dump(mode="json")):
            after_layers = layers_for(reference, edited_epoch, face.title())
            before_layers = layers_for(before, base_epoch, face.title())
            ordinal = after_layers.index(index)
            if ordinal < len(before_layers):
                origins[setting.instance_id] = base_epoch.settings[
                    before_layers[ordinal]
                ].instance_id
                break
    identity = originals[0].batch_id or "batch_" + uuid4().hex
    replacements = []
    taken = document_ids(data)
    for i in range(count):
        source = originals[i % len(originals)].model_dump(mode="json")
        epoch = deepcopy(source)
        if variants is not None:
            variant = variants.sequence[i].model_dump(mode="json")
            epoch.update(variant)
            epoch["scene_id"] = scene_id
        else:
            epoch["duration"] = patch_value(
                source["duration"], base["duration"], edited["duration"]
            )
            epoch["batch_label"] = patch_value(
                source["batch_label"], base["batch_label"], edited["batch_label"]
            )
            current_settings = deepcopy(source["settings"])
            original_duration = originals[i % len(originals)].duration
            if (
                duration_changed
                and isinstance(original_duration, Fixed)
                and isinstance(after_epoch.duration, Fixed)
            ):
                retime_fades(
                    current_settings,
                    original_duration.duration.ns(),
                    after_epoch.duration.duration.ns(),
                )
            epoch["settings"] = current_settings
            if base["settings"] != edited["settings"]:
                current = {s["instance_id"]: s for s in current_settings}
                if current.keys() != old_settings.keys():
                    raise ValueError(
                        "Subgroup layers differ; select an individual epoch to change its composition"
                    )
                epoch["settings"] = [
                    patch_value(current[k], old_settings[k], setting)
                    if (k := origins.get(setting["instance_id"], "")) in old_settings
                    else deepcopy(setting)
                    for setting in edited["settings"]
                ]
            if composition_changed:
                epoch["scene_id"] = scene_id
        epoch["epoch_id"] = (
            source["epoch_id"]
            if i < len(originals)
            else unique_id(data, "Epoch", taken=taken)
        )
        epoch["batch_id"] = identity if len(identities) == 1 else source["batch_id"]
        epoch["repetition_settings"] = []
        epoch["repetition_rules"] = []
        replacements.append(epoch)
    nodes = data_nodes(data, scope)
    positions = {p[-1] for p in paths}
    result = []
    selected = []
    cursor = 0
    for index, node in enumerate(nodes):
        if index not in positions:
            result.append(node)
            continue
        if cursor < count:
            selected.append((*scope, len(result)))
            result.append(replacements[cursor])
            cursor += 1
        if index == max(positions):
            while cursor < count:
                selected.append((*scope, len(result)))
                result.append(replacements[cursor])
                cursor += 1
    nodes[:] = result
    return validate(data), tuple(selected)
